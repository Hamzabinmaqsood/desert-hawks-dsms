# mypy: disable-error-code="no-untyped-def,type-arg,var-annotated,misc,union-attr,arg-type"
import math
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dsms.attendance.models import AttendanceRecord
from dsms.identity import access
from dsms.identity.models import User
from dsms.workforce.models import Employee

from .exceptions import PatrolPermissionError, PatrolValidationError
from .models import (
    CheckpointQRCredential,
    CheckpointVisit,
    PatrolCheckpoint,
    PatrolEvent,
    PatrolException,
    PatrolPolicy,
    PatrolRun,
    PatrolTask,
)


@dataclass(frozen=True)
class EligibilityResult:
    status: str
    reasons: tuple[str, ...]


def resolve_patrol_policy(
    *, company: Any, branch: Any = None, site: Any = None, at_datetime: Any = None
) -> PatrolPolicy | None:
    day = (at_datetime or timezone.now()).date()
    policies = PatrolPolicy.objects.filter(
        company=company, is_active=True, effective_from__lte=day
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=day))
    for filters in (
        {"site": site},
        {"site__isnull": True, "branch": branch},
        {"site__isnull": True, "branch__isnull": True},
    ):
        if policy := policies.filter(**filters).order_by("-effective_from").first():
            return policy
    return None


def _distance(
    latitude: Decimal, longitude: Decimal, target_latitude: Decimal, target_longitude: Decimal
) -> Decimal:
    phi1, phi2 = math.radians(float(target_latitude)), math.radians(float(latitude))
    dphi, dlambda = (
        math.radians(float(latitude - target_latitude)),
        math.radians(float(longitude - target_longitude)),
    )
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return Decimal(str(6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value)))).quantize(
        Decimal("0.01")
    )


@transaction.atomic
def rotate_checkpoint_qr(*, checkpoint: PatrolCheckpoint, actor: User, expires_at=None):
    CheckpointQRCredential.objects.select_for_update().filter(
        checkpoint=checkpoint, is_active=True
    ).update(is_active=False, revoked_at=timezone.now())
    token = secrets.token_urlsafe(32)
    credential = CheckpointQRCredential.objects.create(
        checkpoint=checkpoint,
        credential_id=uuid.uuid4(),
        token_hash=make_password(token),
        token_hint=token[-6:],
        generated_by=actor,
        generated_at=timezone.now(),
        expires_at=expires_at,
    )
    return credential, token


def verify_checkpoint_qr(
    *, credential: CheckpointQRCredential, checkpoint: PatrolCheckpoint, token: str
) -> bool:
    now = timezone.now()
    return bool(
        credential.checkpoint_id == checkpoint.id
        and credential.is_active
        and credential.revoked_at is None
        and (credential.expires_at is None or credential.expires_at >= now)
        and check_password(token, credential.token_hash)
    )


def evaluate_patrol_eligibility(
    *, employee: Employee, patrol_task: PatrolTask
) -> EligibilityResult:
    reasons = []
    if employee.company_id != patrol_task.company_id:
        reasons.append("EMPLOYEE_COMPANY_MISMATCH")
    if employee.employment_status != "ACTIVE":
        reasons.append("EMPLOYEE_NOT_ACTIVE")
    requirement = patrol_task.patrol_requirement
    if (
        requirement
        and requirement.assigned_employee_type
        and employee.employee_type != requirement.assigned_employee_type
    ):
        reasons.append("EMPLOYEE_TYPE_MISMATCH")
    policy = resolve_patrol_policy(
        company=patrol_task.company,
        branch=patrol_task.branch,
        site=patrol_task.site,
        at_datetime=patrol_task.scheduled_start_at,
    )
    if (
        policy
        and policy.require_employee_on_active_duty_assignment
        and not patrol_task.duty_assignment_id
    ):
        reasons.append("DUTY_ASSIGNMENT_REQUIRED")
    if policy and policy.require_employee_attendance_checked_in:
        attendance = AttendanceRecord.objects.filter(
            duty_assignment=patrol_task.duty_assignment,
            actual_check_in_at__isnull=False,
            actual_check_out_at__isnull=True,
        ).exists()
        if not attendance:
            reasons.append("ATTENDANCE_CHECK_IN_REQUIRED")
    return EligibilityResult("INELIGIBLE" if reasons else "ELIGIBLE", tuple(reasons))


@transaction.atomic
def assign_employee_to_patrol(*, patrol_task: PatrolTask, employee: Employee, actor: User):
    task = PatrolTask.objects.select_for_update().get(pk=patrol_task.pk)
    result = evaluate_patrol_eligibility(employee=employee, patrol_task=task)
    if result.status == "INELIGIBLE":
        raise PatrolValidationError(", ".join(result.reasons))
    if employee.user_id == actor.id and not access.has_permission(
        user=actor,
        permission="patrol.assign_patroltask",
        company=employee.company,
        branch=employee.branch,
    ):
        raise PatrolPermissionError("Employees cannot self-assign patrols.")
    task.assigned_employee = employee
    task.status = "READY"
    task.save()
    return task


@transaction.atomic
def start_patrol(
    *,
    actor: User,
    patrol_task: PatrolTask,
    event_time=None,
    gps=None,
    client_event_id=None,
    device_metadata=None,
):
    task = (
        PatrolTask.objects.select_for_update()
        .select_related("assigned_employee__user", "site", "branch")
        .get(pk=patrol_task.pk)
    )
    if client_event_id and (
        event := PatrolEvent.objects.filter(client_event_id=client_event_id)
        .select_related("patrol_run")
        .first()
    ):
        return event.patrol_run
    if not task.assigned_employee_id or task.assigned_employee.user_id != actor.id:
        raise PatrolPermissionError("Only the assigned employee may start this patrol.")
    if task.status not in {"SCHEDULED", "READY"}:
        raise PatrolValidationError("Patrol task cannot be started.")
    eligibility = evaluate_patrol_eligibility(employee=task.assigned_employee, patrol_task=task)
    if eligibility.status == "INELIGIBLE":
        raise PatrolValidationError(", ".join(eligibility.reasons))
    observed = event_time or timezone.now()
    values = {}
    policy = resolve_patrol_policy(
        company=task.company, branch=task.branch, site=task.site, at_datetime=observed
    )
    if gps:
        lat, lon = Decimal(str(gps["latitude"])), Decimal(str(gps["longitude"]))
        values = {
            "start_latitude": lat,
            "start_longitude": lon,
            "start_accuracy_meters": gps.get("accuracy_meters"),
        }
        if task.site.latitude is not None and task.site.longitude is not None:
            values["start_distance_from_site_meters"] = _distance(
                lat, lon, task.site.latitude, task.site.longitude
            )
    elif policy and policy.require_gps:
        raise PatrolValidationError("GPS is required to start this patrol.")
    mandatory = task.route_version.route_checkpoints.filter(is_mandatory=True).count()
    total = task.route_version.route_checkpoints.count()
    run = PatrolRun.objects.create(
        patrol_task=task,
        company=task.company,
        site=task.site,
        employee=task.assigned_employee,
        duty_assignment=task.duty_assignment,
        route_version=task.route_version,
        started_at=observed,
        mandatory_checkpoint_count=mandatory,
        total_checkpoint_count=total,
        started_offline=observed < timezone.now() - timedelta(minutes=1),
        **values,
    )
    PatrolEvent.objects.create(
        patrol_run=run,
        event_type="START",
        actor_user=actor,
        employee=task.assigned_employee,
        observed_at=observed,
        client_event_id=client_event_id,
        is_offline_submission=run.started_offline,
        device_platform=(device_metadata or {}).get("platform", ""),
        app_version=(device_metadata or {}).get("app_version", ""),
    )
    task.status = "IN_PROGRESS"
    task.save(update_fields=["status", "updated_at"])
    return run


@transaction.atomic
def verify_patrol_checkpoint(
    *,
    actor: User,
    patrol_run: PatrolRun,
    checkpoint: PatrolCheckpoint,
    event_time,
    gps=None,
    qr_token=None,
    nfc_payload=None,
    client_event_id=None,
    device_metadata=None,
):
    run = (
        PatrolRun.objects.select_for_update()
        .select_related("employee__user", "patrol_task__branch")
        .get(pk=patrol_run.pk)
    )
    if client_event_id and (
        event := PatrolEvent.objects.filter(client_event_id=client_event_id).first()
    ):
        return event.checkpointvisit
    if run.status != "IN_PROGRESS" or run.employee.user_id != actor.id:
        raise PatrolPermissionError("Patrol is not active for this employee.")
    route_checkpoint = run.route_version.route_checkpoints.filter(checkpoint=checkpoint).first()
    if not route_checkpoint:
        raise PatrolValidationError("Checkpoint is not part of the assigned route version.")
    policy = resolve_patrol_policy(
        company=run.company, branch=run.patrol_task.branch, site=run.site, at_datetime=event_time
    )
    token_result, credential = "NOT_REQUIRED", None
    if qr_token:
        credential = (
            checkpoint.qr_credentials.filter(is_active=True).order_by("-generated_at").first()
        )
        token_result = (
            "VERIFIED"
            if credential
            and verify_checkpoint_qr(credential=credential, checkpoint=checkpoint, token=qr_token)
            else "FAILED"
        )
    elif policy and policy.require_checkpoint_token:
        token_result = "FAILED"
    gps_result, distance, allowed = "NOT_REQUIRED", None, None
    if gps:
        lat, lon = Decimal(str(gps["latitude"])), Decimal(str(gps["longitude"]))
        if (
            checkpoint.latitude is not None
            and checkpoint.longitude is not None
            and checkpoint.geofence_radius_meters
        ):
            distance = _distance(lat, lon, checkpoint.latitude, checkpoint.longitude)
            allowed = Decimal(
                checkpoint.geofence_radius_meters
                + (policy.checkpoint_geofence_tolerance_meters if policy else 0)
            )
            gps_result = "VERIFIED" if distance <= allowed else "FAILED"
    elif checkpoint.requires_gps or (policy and policy.require_gps):
        gps_result = "FAILED"
    results = {gps_result, token_result} - {"NOT_REQUIRED"}
    overall = "FAILED" if "FAILED" in results else "VERIFIED" if results else "WARNING"
    previous = run.checkpoint_visits.count()
    order_warning = (
        run.route_version.order_mode == "STRICT" and route_checkpoint.sequence != previous + 1
    )
    if order_warning and overall == "VERIFIED":
        overall = "WARNING"
    event = PatrolEvent.objects.create(
        patrol_run=run,
        event_type="CHECKPOINT",
        actor_user=actor,
        employee=run.employee,
        observed_at=event_time,
        client_event_id=client_event_id,
        is_offline_submission=event_time < timezone.now() - timedelta(minutes=1),
        device_platform=(device_metadata or {}).get("platform", ""),
        app_version=(device_metadata or {}).get("app_version", ""),
    )
    visit = CheckpointVisit.objects.create(
        patrol_run=run,
        patrol_event=event,
        route_checkpoint=route_checkpoint,
        checkpoint=checkpoint,
        sequence_observed=previous + 1,
        observed_at=event_time,
        status=overall,
        gps_result=gps_result,
        token_result=token_result,
        overall_verification_result=overall,
        latitude=Decimal(str(gps["latitude"])) if gps else None,
        longitude=Decimal(str(gps["longitude"])) if gps else None,
        accuracy_meters=gps.get("accuracy_meters") if gps else None,
        distance_meters=distance,
        allowed_radius_meters=allowed,
        verification_method="QR" if qr_token else "NFC" if nfc_payload else "GPS",
        qr_credential=credential,
        is_offline_submission=event.is_offline_submission,
    )
    for kind, condition in (
        ("CHECKPOINT_OUT_OF_ORDER", order_warning),
        ("QR_INVALID", token_result == "FAILED"),
        ("OUTSIDE_CHECKPOINT_GEOFENCE", gps_result == "FAILED"),
    ):
        if condition:
            PatrolException.objects.get_or_create(
                patrol_task=run.patrol_task,
                patrol_run=run,
                checkpoint_visit=visit,
                exception_type=kind,
                defaults={
                    "company": run.company,
                    "severity": "MEDIUM",
                    "detected_at": timezone.now(),
                    "message": kind.replace("_", " ").title(),
                },
            )
    _recalculate(run)
    return visit


def _recalculate(run: PatrolRun) -> None:
    run.visited_checkpoint_count = run.checkpoint_visits.values("checkpoint").distinct().count()
    mandatory_ids = run.route_version.route_checkpoints.filter(is_mandatory=True).values_list(
        "checkpoint_id", flat=True
    )
    run.verified_mandatory_count = (
        run.checkpoint_visits.filter(
            checkpoint_id__in=mandatory_ids, overall_verification_result="VERIFIED"
        )
        .values("checkpoint")
        .distinct()
        .count()
    )
    run.completion_percentage = (
        (
            Decimal(run.verified_mandatory_count) / Decimal(run.mandatory_checkpoint_count) * 100
        ).quantize(Decimal("0.01"))
        if run.mandatory_checkpoint_count
        else Decimal("100.00")
    )
    run.save(
        update_fields=[
            "visited_checkpoint_count",
            "verified_mandatory_count",
            "completion_percentage",
            "updated_at",
        ]
    )


@transaction.atomic
def complete_patrol(
    *, actor: User, patrol_run: PatrolRun, event_time=None, gps=None, client_event_id=None
):
    run = (
        PatrolRun.objects.select_for_update()
        .select_related("employee__user", "patrol_task")
        .get(pk=patrol_run.pk)
    )
    if run.status != "IN_PROGRESS":
        raise PatrolValidationError("Patrol is not active.")
    if run.employee.user_id != actor.id:
        raise PatrolPermissionError("Only the assigned employee may complete this patrol.")
    _recalculate(run)
    now = event_time or timezone.now()
    complete = run.verified_mandatory_count == run.mandatory_checkpoint_count
    run.status = "COMPLETED" if complete else "INCOMPLETE"
    run.ended_at = now
    if gps:
        run.end_latitude, run.end_longitude, run.end_accuracy_meters = (
            Decimal(str(gps["latitude"])),
            Decimal(str(gps["longitude"])),
            gps.get("accuracy_meters"),
        )
    run.save()
    PatrolEvent.objects.create(
        patrol_run=run,
        event_type="END",
        actor_user=actor,
        employee=run.employee,
        observed_at=now,
        client_event_id=client_event_id,
    )
    run.patrol_task.status = run.status
    run.patrol_task.save(update_fields=["status", "updated_at"])
    if not complete:
        PatrolException.objects.get_or_create(
            patrol_task=run.patrol_task,
            patrol_run=run,
            checkpoint_visit=None,
            exception_type="ROUTE_INCOMPLETE",
            defaults={
                "company": run.company,
                "severity": "HIGH",
                "detected_at": timezone.now(),
                "message": "Mandatory checkpoints were not verified.",
            },
        )
    return run


def mark_missed_patrols(*, at=None):
    now = at or timezone.now()
    tasks = PatrolTask.objects.filter(status__in=["SCHEDULED", "READY"], scheduled_end_at__lt=now)
    count = tasks.update(status="MISSED")
    for task in PatrolTask.objects.filter(status="MISSED", scheduled_end_at__lt=now):
        PatrolException.objects.get_or_create(
            patrol_task=task,
            patrol_run=None,
            checkpoint_visit=None,
            exception_type="MISSED_PATROL",
            defaults={
                "company": task.company,
                "severity": "HIGH",
                "detected_at": now,
                "message": "Scheduled patrol was missed.",
            },
        )
    return count
