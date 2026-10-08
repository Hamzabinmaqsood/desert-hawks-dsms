# mypy: disable-error-code="no-untyped-def,type-arg"
from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.contracts.models import SecurityPost, SecuritySite
from dsms.deployment.enums import DutyAssignmentStatus, RosterStatus
from dsms.deployment.models import DutyAssignment
from dsms.identity.models import User
from dsms.leave.models import LeaveRequest
from dsms.organization.models import Branch, Company

from .enums import (
    AttendanceEventType,
    AttendanceOutcome,
    AttendancePeriodStatus,
    AttendanceRecordStatus,
    CorrectionStatus,
    QRStationStatus,
    VerificationMethod,
    VerificationResult,
)
from .exceptions import AttendancePermissionError, AttendanceValidationError
from .models import (
    AttendanceChangeEvent,
    AttendanceCorrectionRequest,
    AttendanceEvent,
    AttendanceException,
    AttendancePayrollExport,
    AttendancePeriod,
    AttendancePolicy,
    AttendanceQRStation,
    AttendanceRecord,
    AttendanceVerification,
)
from .tenant_queries import (
    consistent_attendance_events,
    consistent_attendance_periods,
    consistent_attendance_policies,
    consistent_attendance_records,
    consistent_duty_assignments,
    consistent_payroll_exports,
    consistent_qr_stations,
)


@dataclass(frozen=True)
class GeofenceResult:
    distance_meters: Decimal | None
    allowed_radius: Decimal | None
    accuracy_status: str
    inside_geofence: bool
    result: str


def resolve_attendance_policy(
    *,
    company: Company,
    branch: Branch | None,
    site: SecuritySite | None,
    post: SecurityPost | None,
    at_datetime: datetime,
) -> AttendancePolicy | None:
    day = timezone.localdate(at_datetime)
    policies = consistent_attendance_policies(
        AttendancePolicy.objects.filter(company=company, is_active=True, effective_from__lte=day)
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=day))
    for filters in (
        {"post": post},
        {"site": site, "post__isnull": True},
        {"branch": branch, "site__isnull": True, "post__isnull": True},
        {"branch__isnull": True, "site__isnull": True, "post__isnull": True},
    ):
        if next_policy := policies.filter(**filters).order_by("-effective_from").first():
            return next_policy
    return None


def evaluate_geofence(
    *,
    site: SecuritySite,
    latitude: Decimal,
    longitude: Decimal,
    accuracy_meters: Decimal | None,
    policy: AttendancePolicy,
) -> GeofenceResult:
    if not Decimal("-90") <= latitude <= Decimal("90") or not Decimal(
        "-180"
    ) <= longitude <= Decimal("180"):
        raise AttendanceValidationError("Invalid GPS coordinates.")
    if site.latitude is None or site.longitude is None or site.geofence_radius_meters is None:
        return GeofenceResult(None, None, "UNCONFIGURED", False, VerificationResult.FAILED)
    phi1, phi2 = math.radians(float(site.latitude)), math.radians(float(latitude))
    dphi, dlambda = (
        math.radians(float(latitude - site.latitude)),
        math.radians(float(longitude - site.longitude)),
    )
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    distance = Decimal(str(6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))).quantize(
        Decimal("0.01")
    )
    allowed = Decimal(site.geofence_radius_meters + policy.additional_geofence_tolerance_meters)
    low_accuracy = (
        policy.maximum_gps_accuracy_meters is not None
        and accuracy_meters is not None
        and accuracy_meters > policy.maximum_gps_accuracy_meters
    )
    inside = distance <= allowed
    result = (
        VerificationResult.WARNING
        if low_accuracy and inside
        else VerificationResult.PASSED
        if inside
        else VerificationResult.FAILED
    )
    return GeofenceResult(
        distance, allowed, "LOW" if low_accuracy else "ACCEPTABLE", inside, result
    )


def generate_qr_station_token(*, station: AttendanceQRStation) -> str:
    station = consistent_qr_stations(AttendanceQRStation.objects.all()).get(pk=station.pk)
    token = secrets.token_urlsafe(32)
    station.token_hash = make_password(token)
    station.token_hint = token[-6:]
    station.generated_at = timezone.now()
    station.save(update_fields=["token_hash", "token_hint", "generated_at", "updated_at"])
    return token


def verify_attendance_qr(
    *,
    station: AttendanceQRStation,
    submitted_token: str,
    site: SecuritySite,
    post: SecurityPost | None = None,
) -> bool:
    now = timezone.now()
    return bool(
        station.company.is_active
        and station.company_id == site.company_id
        and station.status == QRStationStatus.ACTIVE
        and station.revoked_at is None
        and (station.expires_at is None or station.expires_at >= now)
        and station.site_id == site.id
        and (station.post_id is None or station.post_id == getattr(post, "id", None))
        and check_password(submitted_token, station.token_hash)
    )


@transaction.atomic
def check_in_for_duty(
    *,
    user: User,
    duty_assignment: DutyAssignment,
    event_time: datetime,
    gps: dict | None = None,
    qr: dict | None = None,
    client_event_id=None,
    device_metadata: dict | None = None,
) -> AttendanceRecord:
    assignment = consistent_duty_assignments(
        DutyAssignment.objects.select_for_update(of=("self",)).select_related(
            "employee__user",
            "duty_shift__roster_period",
            "duty_shift__site__client",
            "duty_shift__site__contract",
            "duty_shift__post",
        )
    ).get(pk=duty_assignment.pk)
    if assignment.employee.user_id != user.id:
        raise AttendancePermissionError(
            "A user may only check in for their linked employee record."
        )
    if assignment.status not in {
        DutyAssignmentStatus.PLANNED,
        DutyAssignmentStatus.CONFIRMED,
    } or assignment.duty_shift.roster_period.status not in {
        RosterStatus.PUBLISHED,
        RosterStatus.LOCKED,
    }:
        raise AttendanceValidationError("Assignment is not available for attendance.")
    if client_event_id and (
        existing := consistent_attendance_events(
            AttendanceEvent.objects.filter(client_event_id=client_event_id, actor_user=user)
        )
        .select_related("attendance_record")
        .first()
    ):
        return existing.attendance_record
    shift = assignment.duty_shift
    policy = resolve_attendance_policy(
        company=shift.company,
        branch=shift.branch,
        site=shift.site,
        post=shift.post,
        at_datetime=event_time,
    )
    if not policy:
        raise AttendanceValidationError("No effective attendance policy is configured.")
    record, _ = AttendanceRecord.objects.get_or_create(
        duty_assignment=assignment,
        defaults={
            "company": shift.company,
            "branch": shift.branch,
            "client": shift.client,
            "site": shift.site,
            "post": shift.post,
            "employee": assignment.employee,
            "scheduled_start_at": shift.starts_at,
            "scheduled_end_at": shift.ends_at,
        },
    )
    consistent_record = (
        consistent_attendance_records(AttendanceRecord.objects.select_for_update(of=("self",)))
        .filter(pk=record.pk)
        .first()
    )
    if consistent_record is None:
        raise AttendanceValidationError("Existing attendance data is tenant-inconsistent.")
    record = consistent_record
    event = AttendanceEvent.objects.create(
        attendance_record=record,
        event_type=AttendanceEventType.CHECK_IN,
        subject_employee=assignment.employee,
        actor_user=user,
        observed_at=event_time,
        client_event_id=client_event_id,
        is_offline_submission=False,
        device_platform=(device_metadata or {}).get("platform", ""),
        app_version=(device_metadata or {}).get("app_version", ""),
    )
    verified = True
    if policy.require_gps:
        if not gps:
            result = GeofenceResult(None, None, "MISSING", False, VerificationResult.FAILED)
        else:
            result = evaluate_geofence(
                site=shift.site,
                latitude=Decimal(str(gps["latitude"])),
                longitude=Decimal(str(gps["longitude"])),
                accuracy_meters=Decimal(str(gps["accuracy_meters"]))
                if gps.get("accuracy_meters") is not None
                else None,
                policy=policy,
            )
        AttendanceVerification.objects.create(
            attendance_event=event,
            method=VerificationMethod.GPS,
            result=result.result,
            latitude=gps.get("latitude") if gps else None,
            longitude=gps.get("longitude") if gps else None,
            accuracy_meters=gps.get("accuracy_meters") if gps else None,
            distance_from_site_meters=result.distance_meters,
            geofence_radius_meters=int(result.allowed_radius) if result.allowed_radius else None,
            failure_code="OUTSIDE_GEOFENCE" if not result.inside_geofence else "",
        )
        verified &= result.result == VerificationResult.PASSED
    if policy.require_qr:
        station = None
        if qr:
            station = (
                consistent_qr_stations(AttendanceQRStation.objects.all())
                .filter(pk=qr["station_id"], company=shift.company, site=shift.site)
                .first()
            )
        qr_valid = bool(
            qr
            and station
            and verify_attendance_qr(
                station=station,
                submitted_token=qr["token"],
                site=shift.site,
                post=shift.post,
            )
        )
        AttendanceVerification.objects.create(
            attendance_event=event,
            method=VerificationMethod.QR,
            result=VerificationResult.PASSED if qr_valid else VerificationResult.FAILED,
        )
        verified &= qr_valid
    late = max(
        int((event_time - shift.starts_at).total_seconds() // 60) - policy.late_grace_minutes, 0
    )
    record.actual_check_in_at = event_time
    record.late_minutes = late
    record.outcome = (
        AttendanceOutcome.UNVERIFIED
        if not verified
        else AttendanceOutcome.LATE
        if late
        else AttendanceOutcome.ON_TIME
    )
    record.status = (
        AttendanceRecordStatus.IN_PROGRESS if verified else AttendanceRecordStatus.EXCEPTION
    )
    record.save(
        update_fields=["actual_check_in_at", "late_minutes", "outcome", "status", "updated_at"]
    )
    if not verified:
        AttendanceException.objects.get_or_create(
            attendance_record=record,
            exception_type="VERIFICATION_FAILED",
            status="OPEN",
            defaults={
                "attendance_event": event,
                "severity": "HIGH",
                "detected_at": timezone.now(),
                "message": "Required check-in verification did not pass.",
            },
        )
    return record


@transaction.atomic
def check_out_from_duty(
    *, user: User, duty_assignment: DutyAssignment, event_time: datetime, client_event_id=None
) -> AttendanceRecord:
    assignment = consistent_duty_assignments(
        DutyAssignment.objects.select_for_update(of=("self",)).select_related("employee__user")
    ).get(pk=duty_assignment.pk)
    if assignment.employee.user_id != user.id:
        raise AttendancePermissionError("A user may only check out their linked employee record.")
    if client_event_id and (
        existing := consistent_attendance_events(
            AttendanceEvent.objects.filter(client_event_id=client_event_id, actor_user=user)
        )
        .select_related("attendance_record")
        .first()
    ):
        return existing.attendance_record
    record = consistent_attendance_records(
        AttendanceRecord.objects.select_for_update(of=("self",))
    ).get(duty_assignment=assignment)
    if not record.actual_check_in_at or record.actual_check_out_at:
        raise AttendanceValidationError("A single prior check-in is required.")
    AttendanceEvent.objects.create(
        attendance_record=record,
        event_type=AttendanceEventType.CHECK_OUT,
        subject_employee=assignment.employee,
        actor_user=user,
        observed_at=event_time,
        client_event_id=client_event_id,
    )
    record.actual_check_out_at = event_time
    record.actual_worked_minutes = max(
        int((event_time - record.actual_check_in_at).total_seconds() // 60), 0
    )
    record.early_departure_minutes = max(
        int((record.scheduled_end_at - event_time).total_seconds() // 60), 0
    )
    if record.outcome == AttendanceOutcome.LATE and record.early_departure_minutes:
        record.outcome = AttendanceOutcome.LATE_AND_EARLY
    elif record.early_departure_minutes:
        record.outcome = AttendanceOutcome.EARLY_DEPARTURE
    record.status = (
        AttendanceRecordStatus.COMPLETED
        if not record.exceptions.filter(status="OPEN").exists()
        else AttendanceRecordStatus.EXCEPTION
    )
    record.save(
        update_fields=[
            "actual_check_out_at",
            "actual_worked_minutes",
            "early_departure_minutes",
            "outcome",
            "status",
            "updated_at",
        ]
    )
    return record


@transaction.atomic
def generate_expected_attendance(*, attendance_period: AttendancePeriod) -> int:
    period = consistent_attendance_periods(
        AttendancePeriod.objects.select_for_update(of=("self",))
    ).get(pk=attendance_period.pk)
    if period.status not in {AttendancePeriodStatus.OPEN, AttendancePeriodStatus.UNDER_REVIEW}:
        raise AttendanceValidationError(
            "Expected attendance can only be generated in an open period."
        )
    assignments = consistent_duty_assignments(
        DutyAssignment.objects.filter(
            duty_shift__roster_period__status__in=[RosterStatus.PUBLISHED, RosterStatus.LOCKED],
            duty_shift__duty_date__range=(period.period_start, period.period_end),
            status__in=[DutyAssignmentStatus.PLANNED, DutyAssignmentStatus.CONFIRMED],
        ).select_related("employee", "duty_shift")
    )
    if period.company_id:
        assignments = assignments.filter(duty_shift__company=period.company)
    if period.branch_id:
        assignments = assignments.filter(duty_shift__branch=period.branch)
    created = 0
    for assignment in assignments:
        shift = assignment.duty_shift
        approved_leave = LeaveRequest.objects.filter(
            employee=assignment.employee,
            status__in=["APPROVED", "IN_PROGRESS"],
            starts_at__lt=shift.ends_at,
            ends_at__gt=shift.starts_at,
        ).exists()
        _, was_created = AttendanceRecord.objects.get_or_create(
            duty_assignment=assignment,
            defaults={
                "attendance_period": period,
                "company": shift.company,
                "branch": shift.branch,
                "client": shift.client,
                "site": shift.site,
                "post": shift.post,
                "employee": assignment.employee,
                "scheduled_start_at": shift.starts_at,
                "scheduled_end_at": shift.ends_at,
                "status": AttendanceRecordStatus.COMPLETED
                if approved_leave
                else AttendanceRecordStatus.PENDING,
                "outcome": AttendanceOutcome.EXCUSED if approved_leave else "",
            },
        )
        created += int(was_created)
    return created


@transaction.atomic
def verify_attendance(*, record: AttendanceRecord, actor: User) -> AttendanceRecord:
    obj = consistent_attendance_records(
        AttendanceRecord.objects.select_for_update(of=("self",))
    ).get(pk=record.pk)
    if obj.status in {AttendanceRecordStatus.LOCKED, AttendanceRecordStatus.PENDING}:
        raise AttendanceValidationError("Attendance is not ready for supervisor verification.")
    obj.status, obj.reviewed_by, obj.reviewed_at = (
        AttendanceRecordStatus.UNDER_REVIEW,
        actor,
        timezone.now(),
    )
    obj.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    AttendanceChangeEvent.objects.create(
        attendance_record=obj, event_type="SUPERVISOR_VERIFIED", actor=actor
    )
    record_audit_event(
        action="ATTENDANCE_VERIFIED",
        category=AuditCategory.ATTENDANCE,
        severity=AuditSeverity.INFO,
        summary="Attendance verified by supervisor.",
        actor_user=actor,
        company=obj.company,
        branch=obj.branch,
        source_object=obj,
    )
    return obj


@transaction.atomic
def request_attendance_correction(
    *,
    record: AttendanceRecord,
    actor: User,
    reason: str,
    proposed_check_in_at=None,
    proposed_check_out_at=None,
    proposed_outcome="",
    proposed_approved_worked_minutes=None,
    proposed_overtime_minutes=None,
) -> AttendanceCorrectionRequest:
    obj = consistent_attendance_records(
        AttendanceRecord.objects.select_for_update(of=("self",))
    ).get(pk=record.pk)
    if obj.status == AttendanceRecordStatus.LOCKED:
        raise AttendanceValidationError(
            "Locked attendance requires a post-lock adjustment workflow."
        )
    correction = AttendanceCorrectionRequest.objects.create(
        attendance_record=obj,
        requested_by=actor,
        reason=reason,
        proposed_check_in_at=proposed_check_in_at,
        proposed_check_out_at=proposed_check_out_at,
        proposed_outcome=proposed_outcome,
        proposed_approved_worked_minutes=proposed_approved_worked_minutes,
        proposed_overtime_minutes=proposed_overtime_minutes,
        status=CorrectionStatus.SUBMITTED,
    )
    AttendanceChangeEvent.objects.create(
        attendance_record=obj, event_type="CORRECTION_REQUESTED", actor=actor, reason=reason
    )
    return correction


@transaction.atomic
def approve_attendance_correction(
    *, correction: AttendanceCorrectionRequest, actor: User, notes: str = ""
) -> AttendanceRecord:
    item = (
        AttendanceCorrectionRequest.objects.select_for_update()
        .select_related("attendance_record")
        .get(pk=correction.pk)
    )
    record = consistent_attendance_records(
        AttendanceRecord.objects.select_for_update(of=("self",))
    ).get(pk=item.attendance_record_id)
    if item.status != CorrectionStatus.SUBMITTED or item.requested_by_id == actor.id:
        raise AttendanceValidationError("A submitted correction requires an independent checker.")
    if record.status == AttendanceRecordStatus.LOCKED:
        raise AttendanceValidationError("Locked attendance cannot be silently corrected.")
    original = {
        "check_in": str(record.actual_check_in_at),
        "check_out": str(record.actual_check_out_at),
        "outcome": record.outcome,
        "worked_minutes": record.approved_worked_minutes,
        "overtime_minutes": record.approved_overtime_minutes,
    }
    for target, value in (
        ("actual_check_in_at", item.proposed_check_in_at),
        ("actual_check_out_at", item.proposed_check_out_at),
        ("outcome", item.proposed_outcome),
        ("approved_worked_minutes", item.proposed_approved_worked_minutes),
        ("approved_overtime_minutes", item.proposed_overtime_minutes),
    ):
        if value not in (None, ""):
            setattr(record, target, value)
    record.save()
    item.status, item.reviewed_by, item.reviewed_at, item.review_notes = (
        CorrectionStatus.APPROVED,
        actor,
        timezone.now(),
        notes,
    )
    item.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
    AttendanceChangeEvent.objects.create(
        attendance_record=record, event_type="CORRECTION_APPROVED", actor=actor, reason=item.reason
    )
    record_audit_event(
        action="ATTENDANCE_CORRECTION_APPROVED",
        category=AuditCategory.ATTENDANCE,
        severity=AuditSeverity.HIGH,
        summary="Attendance correction approved.",
        actor_user=actor,
        company=record.company,
        branch=record.branch,
        source_object=record,
        metadata_safe={"original": original, "correction_id": str(item.id)},
    )
    return record


@transaction.atomic
def approve_attendance_period(*, period: AttendancePeriod, actor: User) -> AttendancePeriod:
    obj = consistent_attendance_periods(
        AttendancePeriod.objects.select_for_update(of=("self",))
    ).get(pk=period.pk)
    if obj.status not in {AttendancePeriodStatus.OPEN, AttendancePeriodStatus.UNDER_REVIEW}:
        raise AttendanceValidationError("Attendance period is not reviewable.")
    if obj.submitted_by_id == actor.id:
        raise AttendanceValidationError(
            "Attendance period approval requires an independent checker."
        )
    if obj.records.filter(
        status__in=[
            AttendanceRecordStatus.PENDING,
            AttendanceRecordStatus.IN_PROGRESS,
            AttendanceRecordStatus.EXCEPTION,
        ]
    ).exists():
        raise AttendanceValidationError("Unresolved attendance records prevent approval.")
    records = consistent_attendance_records(obj.records.select_for_update(of=("self",)))
    if records.count() != obj.records.count():
        raise AttendanceValidationError("Attendance period contains inconsistent records.")
    for record in records.exclude(outcome=AttendanceOutcome.EXCUSED):
        record.status = AttendanceRecordStatus.APPROVED
        record.approved_by, record.approved_at = actor, timezone.now()
        record.approved_check_in_at = record.approved_check_in_at or record.actual_check_in_at
        record.approved_check_out_at = record.approved_check_out_at or record.actual_check_out_at
        if record.approved_worked_minutes is None:
            record.approved_worked_minutes = record.actual_worked_minutes or 0
        record.save()
    obj.status, obj.approved_by, obj.approved_at = (
        AttendancePeriodStatus.APPROVED,
        actor,
        timezone.now(),
    )
    obj.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    record_audit_event(
        action="ATTENDANCE_PERIOD_APPROVED",
        category=AuditCategory.ATTENDANCE,
        severity=AuditSeverity.HIGH,
        summary="Attendance period approved.",
        actor_user=actor,
        company=obj.company,
        branch=obj.branch,
        source_object=obj,
    )
    return obj


@transaction.atomic
def lock_attendance_period(*, period: AttendancePeriod, actor: User) -> AttendancePeriod:
    obj = consistent_attendance_periods(
        AttendancePeriod.objects.select_for_update(of=("self",))
    ).get(pk=period.pk)
    if obj.status != AttendancePeriodStatus.APPROVED:
        raise AttendanceValidationError("Only an approved attendance period may be locked.")
    records = consistent_attendance_records(obj.records.all())
    if records.count() != obj.records.count():
        raise AttendanceValidationError("Attendance period contains inconsistent records.")
    records.update(status=AttendanceRecordStatus.LOCKED, locked_at=timezone.now())
    obj.status, obj.locked_by, obj.locked_at = AttendancePeriodStatus.LOCKED, actor, timezone.now()
    obj.save(update_fields=["status", "locked_by", "locked_at", "updated_at"])
    record_audit_event(
        action="ATTENDANCE_PERIOD_LOCKED",
        category=AuditCategory.ATTENDANCE,
        severity=AuditSeverity.HIGH,
        summary="Attendance period locked.",
        actor_user=actor,
        company=obj.company,
        branch=obj.branch,
        source_object=obj,
    )
    return obj


@transaction.atomic
def build_payroll_timekeeping_input(
    *, attendance_period: AttendancePeriod, payroll_period, employee, actor: User
):
    period = consistent_attendance_periods(
        AttendancePeriod.objects.select_for_update(of=("self",))
    ).get(pk=attendance_period.pk)
    if period.status != AttendancePeriodStatus.LOCKED:
        raise AttendanceValidationError("Only locked attendance may be exported to payroll.")
    if (
        payroll_period.company_id != period.company_id
        or employee.company_id != period.company_id
        or (employee.branch_id is not None and employee.branch.company_id != period.company_id)
        or not period.company.is_active
    ):
        raise AttendanceValidationError("Payroll export relations must belong to one Company.")
    records = consistent_attendance_records(period.records.all()).filter(
        employee=employee, status=AttendanceRecordStatus.LOCKED
    )
    scheduled = sum(
        max(int((r.scheduled_end_at - r.scheduled_start_at).total_seconds() // 60), 0)
        for r in records
    )
    worked = sum(r.approved_worked_minutes or 0 for r in records)
    overtime = sum(r.approved_overtime_minutes for r in records)
    excused = records.filter(outcome=AttendanceOutcome.EXCUSED).count()
    approved_leave = LeaveRequest.objects.filter(
        employee=employee,
        status__in=["APPROVED", "IN_PROGRESS"],
        starts_at__date__lte=period.period_end,
        ends_at__date__gte=period.period_start,
    ).select_related("leave_type")
    paid_leave = sum(
        (item.approved_units or 0)
        for item in approved_leave
        if item.leave_type.pay_treatment == "PAID"
    )
    unpaid_leave = sum(
        (item.approved_units or 0)
        for item in approved_leave
        if item.leave_type.pay_treatment == "UNPAID"
    )
    quantities = {
        "scheduled_hours": str(Decimal(scheduled) / 60),
        "approved_worked_hours": str(Decimal(worked) / 60),
        "regular_hours": str(Decimal(max(worked - overtime, 0)) / 60),
        "approved_overtime_hours": str(Decimal(overtime) / 60),
        "approved_absence_units": excused,
        "paid_leave_units": str(paid_leave),
        "unpaid_leave_units": str(unpaid_leave),
        "late_minutes": sum(r.late_minutes for r in records),
    }
    export, _ = AttendancePayrollExport.objects.get_or_create(
        attendance_period=period,
        payroll_period=payroll_period,
        employee=employee,
        source_version=1,
        defaults={"quantities": quantities, "exported_by": actor},
    )
    record_audit_event(
        action="ATTENDANCE_PAYROLL_HANDOFF",
        category=AuditCategory.ATTENDANCE,
        severity=AuditSeverity.HIGH,
        summary="Approved timekeeping quantities exported.",
        actor_user=actor,
        company=period.company,
        branch=period.branch,
        source_object=export,
    )
    return export


@transaction.atomic
def flag_post_lock_adjustment(*, record: AttendanceRecord, actor: User, reason: str) -> None:
    obj = consistent_attendance_records(
        AttendanceRecord.objects.select_for_update(of=("self",))
    ).get(pk=record.pk)
    if obj.status != AttendanceRecordStatus.LOCKED:
        raise AttendanceValidationError("Only locked attendance uses the adjustment handoff.")
    AttendanceChangeEvent.objects.create(
        attendance_record=obj,
        attendance_period=obj.attendance_period,
        event_type="PAYROLL_ADJUSTMENT_REQUIRED",
        actor=actor,
        reason=reason,
    )
    if obj.attendance_period_id:
        consistent_payroll_exports(
            AttendancePayrollExport.objects.filter(
                attendance_period_id=obj.attendance_period_id, employee=obj.employee
            )
        ).update(adjustment_required=True)
    record_audit_event(
        action="PAYROLL_ADJUSTMENT_REQUIRED",
        category=AuditCategory.ATTENDANCE,
        severity=AuditSeverity.HIGH,
        summary="Post-lock attendance adjustment requires payroll review.",
        actor_user=actor,
        company=obj.company,
        branch=obj.branch,
        source_object=obj,
        metadata_safe={"reason": reason},
    )
