# mypy: disable-error-code="no-untyped-def,type-arg,var-annotated,misc,no-untyped-call"
from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

from dsms.attendance.models import AttendanceRecord
from dsms.attendance.tenant_queries import (
    consistent_attendance_records,
    consistent_duty_assignments,
)
from dsms.contracts.models import SecurityPost, SecuritySite
from dsms.deployment.models import DutyAssignment
from dsms.identity.models import User
from dsms.subscriptions.enforcement import requires_company_module
from dsms.workforce.models import Employee

from .exceptions import SupervisionPermissionError, SupervisionValidationError
from .models import (
    CorrectiveAction,
    GuardObservation,
    InspectionFinding,
    SiteInspection,
    SiteVisit,
    SupervisionAssignment,
    SupervisorVisitPlan,
    VisitFrequencyRequirement,
)
from .tenant_queries import (
    consistent_assignments,
    consistent_corrective_actions,
    consistent_frequency_requirements,
    consistent_inspections,
    consistent_responses,
    consistent_site_visits,
    consistent_visit_plans,
)


def _consistent_sites(queryset):
    return queryset.filter(
        company__is_active=True,
        client__company_id=F("company_id"),
        contract__company_id=F("company_id"),
        contract__client_id=F("client_id"),
        managing_branch__company_id=F("company_id"),
    )


def has_site_responsibility(
    supervisor: Employee, site: SecuritySite, on_date: date | None = None
) -> bool:
    day = on_date or timezone.localdate()
    if not _consistent_sites(SecuritySite.objects.all()).filter(pk=site.pk).exists():
        return False
    return (
        consistent_assignments(SupervisionAssignment.objects.all())
        .filter(
            supervisor=supervisor,
            company=site.company,
            branch=site.managing_branch,
            status="ACTIVE",
            effective_from__lte=day,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=day))
        .filter(
            Q(scope_type="BRANCH")
            | Q(scope_type="OPERATIONAL_ZONE", operational_zone=site.operational_zone)
            | Q(scope_type="SITE", site=site)
        )
        .exists()
    )


def _distance(site, latitude: Decimal, longitude: Decimal) -> Decimal | None:
    if site.latitude is None or site.longitude is None:
        return None
    phi1, phi2 = math.radians(float(site.latitude)), math.radians(float(latitude))
    dphi = math.radians(float(latitude - site.latitude))
    dlambda = math.radians(float(longitude - site.longitude))
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return Decimal(str(6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))).quantize(
        Decimal("0.01")
    )


@transaction.atomic
@requires_company_module("security_supervision", argument="site")
def start_site_visit(
    *,
    actor: User,
    supervisor: Employee,
    site: SecuritySite,
    visit_plan: SupervisorVisitPlan | None = None,
    gps: dict | None = None,
) -> SiteVisit:
    site = _consistent_sites(SecuritySite.objects.all()).get(pk=site.pk)
    supervisor = Employee.objects.select_related("company", "user").get(pk=supervisor.pk)
    if supervisor.company_id != site.company_id or not supervisor.company.is_active:
        raise SupervisionValidationError("Supervisor and site must belong to one active Company.")
    if supervisor.user_id != actor.id and not actor.has_perm("supervision.start_site_visit"):
        raise SupervisionPermissionError("Actor cannot start a visit for this supervisor.")
    if not has_site_responsibility(supervisor, site):
        raise SupervisionPermissionError("Supervisor is not responsible for this site.")
    if (
        SiteVisit.objects.select_for_update()
        .filter(supervisor=supervisor, status="IN_PROGRESS")
        .exists()
    ):
        raise SupervisionValidationError("Supervisor already has an open site visit.")
    now = timezone.now()
    distance = None
    method, result = "SUPERVISOR_MANUAL", "NOT_REQUIRED"
    values = {}
    if gps:
        lat, lon = Decimal(str(gps["latitude"])), Decimal(str(gps["longitude"]))
        if not Decimal("-90") <= lat <= Decimal("90") or not Decimal("-180") <= lon <= Decimal(
            "180"
        ):
            raise SupervisionValidationError("Invalid GPS coordinates.")
        distance = _distance(site, lat, lon)
        method = "GPS"
        result = (
            "VERIFIED"
            if distance is not None
            and site.geofence_radius_meters is not None
            and distance <= site.geofence_radius_meters
            else "WARNING"
        )
        values = {
            "arrival_latitude": lat,
            "arrival_longitude": lon,
            "arrival_accuracy_meters": gps.get("accuracy_meters"),
            "arrival_distance_from_site_meters": distance,
        }
    visit = SiteVisit.objects.create(
        company=site.company,
        supervisor=supervisor,
        visit_plan=visit_plan,
        branch=site.managing_branch,
        site=site,
        started_at=now,
        verification_method=method,
        verification_result=result,
        **values,
    )
    if visit_plan:
        visit_plan = consistent_visit_plans(
            SupervisorVisitPlan.objects.select_for_update(of=("self",))
        ).get(pk=visit_plan.pk)
        if (
            visit_plan.company_id != site.company_id
            or visit_plan.branch_id != site.managing_branch_id
            or visit_plan.supervisor_id != supervisor.id
            or visit_plan.site_id != site.id
            or visit_plan.status not in {"DRAFT", "SCHEDULED"}
        ):
            raise SupervisionValidationError("Visit plan does not match this visit.")
        visit_plan.status = "IN_PROGRESS"
        visit_plan.save(update_fields=["status", "updated_at"])
    return visit


@transaction.atomic
@requires_company_module("security_supervision", argument="visit")
def end_site_visit(
    *, visit: SiteVisit, actor: User, summary: str = "", gps: dict | None = None
) -> SiteVisit:
    visit = consistent_site_visits(SiteVisit.objects.select_for_update(of=("self",))).get(
        pk=visit.pk
    )
    if visit.status != "IN_PROGRESS":
        raise SupervisionValidationError("Only an open visit can be ended.")
    if visit.supervisor.user_id != actor.id and not actor.has_perm("supervision.end_site_visit"):
        raise SupervisionPermissionError("Actor cannot end this visit.")
    visit.ended_at, visit.visit_summary = timezone.now(), summary
    visit.status = (
        "COMPLETED"
        if consistent_inspections(visit.inspections.all())
        .filter(status__in=["SUBMITTED", "REVIEWED", "CLOSED"])
        .exists()
        else "INCOMPLETE"
    )
    if gps:
        visit.departure_latitude = Decimal(str(gps["latitude"]))
        visit.departure_longitude = Decimal(str(gps["longitude"]))
        visit.departure_accuracy_meters = gps.get("accuracy_meters")
    visit.save()
    if visit.visit_plan:
        visit.visit_plan.status = "COMPLETED" if visit.status == "COMPLETED" else "MISSED"
        visit.visit_plan.save(update_fields=["status", "updated_at"])
    return visit


@transaction.atomic
@requires_company_module("security_supervision", argument="inspection")
def submit_inspection(*, inspection: SiteInspection) -> SiteInspection:
    inspection = consistent_inspections(
        SiteInspection.objects.select_for_update(of=("self",)).prefetch_related(
            "responses__template_item", "responses__selected_option"
        )
    ).get(pk=inspection.pk)
    if inspection.status not in {"DRAFT", "IN_PROGRESS"}:
        raise SupervisionValidationError("Inspection is already finalized.")
    required = set(inspection.template.sections.values_list("items__id", flat=True).filter())
    responses_queryset = consistent_responses(inspection.responses.all())
    if responses_queryset.count() != inspection.responses.count():
        raise SupervisionValidationError("Inspection contains tenant-inconsistent responses.")
    responses = list(responses_queryset)
    if required - {
        response.template_item_id for response in responses if response.template_item.is_required
    }:
        raise SupervisionValidationError("All required checklist items must be answered.")
    total = sum((response.score or Decimal("0")) for response in responses)
    maximum = sum((response.template_item.weight or Decimal("0")) for response in responses)
    inspection.total_score, inspection.maximum_score = total, maximum
    inspection.percentage = (
        (total / maximum * Decimal("100")).quantize(Decimal("0.01")) if maximum else None
    )
    pct = inspection.percentage
    inspection.result = (
        "SATISFACTORY"
        if pct is None or pct >= 80
        else "NEEDS_IMPROVEMENT"
        if pct >= 60
        else "UNSATISFACTORY"
    )
    inspection.status, inspection.submitted_at = "SUBMITTED", timezone.now()
    inspection.save()
    for response in responses:
        if response.is_noncompliant:
            InspectionFinding.objects.get_or_create(
                inspection=inspection,
                template_item=response.template_item,
                defaults={
                    "company": inspection.company,
                    "site": inspection.site,
                    "post": inspection.post,
                    "employee": inspection.inspected_employee,
                    "title": response.template_item.question[:200],
                    "description": response.comment or "Checklist response was noncompliant.",
                    "severity": "MEDIUM",
                    "requires_corrective_action": True,
                    "identified_by": inspection.created_by,
                    "identified_at": timezone.now(),
                },
            )
    return inspection


@transaction.atomic
@requires_company_module("security_supervision", argument="site_visit")
def verify_guard_during_visit(
    *,
    site_visit: SiteVisit,
    post: SecurityPost,
    employee: Employee | None,
    observed_at: datetime,
    actor: User,
) -> dict:
    site_visit = consistent_site_visits(SiteVisit.objects.all()).get(pk=site_visit.pk)
    if (
        not site_visit.company.is_active
        or post.company_id != site_visit.company_id
        or post.site_id != site_visit.site_id
        or post.client_id != site_visit.site.client_id
        or (
            employee is not None
            and (
                employee.company_id != site_visit.company_id
                or (
                    employee.branch_id is not None
                    and employee.branch is not None
                    and employee.branch.company_id != site_visit.company_id
                )
            )
        )
    ):
        raise SupervisionValidationError("Guard verification relations are tenant-inconsistent.")
    if site_visit.status != "IN_PROGRESS" or post.site_id != site_visit.site_id:
        raise SupervisionValidationError("Guard verification must occur at the active visit site.")
    assignments = consistent_duty_assignments(
        DutyAssignment.objects.filter(
            duty_shift__site=site_visit.site,
            duty_shift__post=post,
            duty_shift__starts_at__lte=observed_at,
            duty_shift__ends_at__gte=observed_at,
        ).select_related("employee")
    )
    expected = assignments.filter(employee=employee).first() if employee else assignments.first()
    if employee and expected:
        verification, observation = "MATCHED", "PRESENT_AS_SCHEDULED"
    elif employee and assignments.exists():
        verification, observation = "REPLACEMENT_MATCH", "REPLACEMENT_PRESENT"
    elif employee:
        verification, observation = "UNSCHEDULED_EMPLOYEE", "UNSCHEDULED_EMPLOYEE_PRESENT"
    elif expected:
        verification, observation = "SCHEDULED_BUT_NOT_FOUND", "NOT_FOUND"
    else:
        verification, observation = "NO_ACTIVE_ASSIGNMENT", "UNABLE_TO_VERIFY"
    attendance = (
        consistent_attendance_records(
            AttendanceRecord.objects.filter(duty_assignment=expected)
        ).first()
        if expected
        else None
    )
    GuardObservation.objects.create(
        company=site_visit.company,
        site_visit=site_visit,
        site=site_visit.site,
        post=post,
        employee=employee,
        expected_duty_assignment=expected,
        attendance_record=attendance,
        observation_status=observation,
        observed_at=observed_at,
        created_by=actor,
    )
    return {
        "scheduled_employee": str(expected.employee_id) if expected else None,
        "observed_employee": str(employee.id) if employee else None,
        "post": str(post.id),
        "roster_status": getattr(expected, "status", None),
        "attendance_status": getattr(attendance, "status", None),
        "verification_status": verification,
        "warnings": [],
    }


def mark_missed_visits(*, at: datetime | None = None) -> int:
    now = at or timezone.now()
    return (
        consistent_visit_plans(SupervisorVisitPlan.objects.filter(status="SCHEDULED"))
        .filter(
            Q(planned_end_at__lt=now) | Q(planned_end_at__isnull=True, planned_date__lt=now.date())
        )
        .update(status="MISSED")
    )


@transaction.atomic
@requires_company_module("security_supervision", argument="action")
def transition_corrective_action(
    *, action: CorrectiveAction, actor: User, target: str, notes: str = ""
) -> CorrectiveAction:
    action = consistent_corrective_actions(
        CorrectiveAction.objects.select_for_update(of=("self",))
    ).get(pk=action.pk)
    allowed = {
        "OPEN": {"ASSIGNED", "CANCELLED"},
        "ASSIGNED": {"IN_PROGRESS", "CANCELLED"},
        "IN_PROGRESS": {"PENDING_VERIFICATION", "CLOSED"},
        "PENDING_VERIFICATION": {"VERIFIED", "IN_PROGRESS"},
        "VERIFIED": {"CLOSED"},
    }
    if target not in allowed.get(action.status, set()):
        raise SupervisionValidationError("Invalid corrective action transition.")
    if target == "VERIFIED" and action.verification_required and action.assigned_by_id == actor.id:
        raise SupervisionPermissionError("Maker-checker prevents self-verification.")
    now = timezone.now()
    if target == "IN_PROGRESS":
        action.started_at = now
    if target == "PENDING_VERIFICATION":
        action.completed_at, action.completion_notes = now, notes
    if target == "VERIFIED":
        action.verified_by, action.verified_at, action.verification_notes = actor, now, notes
    action.status = target
    action.save()
    return action


@requires_company_module("security_supervision", argument="supervisor")
def generate_supervisor_visit_plan(
    *, supervisor: Employee, date_from: date, date_to: date, created_by: User | None = None
):
    if date_to < date_from:
        raise SupervisionValidationError("Invalid planning range.")
    assignments = consistent_assignments(
        SupervisionAssignment.objects.filter(
            supervisor=supervisor, status="ACTIVE", effective_from__lte=date_to
        ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=date_from))
    )
    sites = _consistent_sites(
        SecuritySite.objects.filter(
            Q(supervisionassignment__in=[]) if False else Q(company=supervisor.company)
        )
    )
    site_ids = set()
    for assignment in assignments:
        query = sites.filter(managing_branch=assignment.branch)
        if assignment.scope_type == "SITE":
            query = query.filter(pk=assignment.site_id)
        elif assignment.scope_type == "OPERATIONAL_ZONE":
            query = query.filter(operational_zone=assignment.operational_zone)
        site_ids.update(query.values_list("id", flat=True))
    plans = []
    actor = created_by or supervisor.user
    for site in _consistent_sites(SecuritySite.objects.filter(id__in=site_ids)):
        rule = (
            consistent_frequency_requirements(
                VisitFrequencyRequirement.objects.filter(
                    company=site.company, is_active=True, effective_from__lte=date_to
                )
            )
            .filter(
                Q(site=site)
                | Q(site__isnull=True, operational_zone=site.operational_zone)
                | Q(site__isnull=True, operational_zone__isnull=True, branch=site.managing_branch)
            )
            .order_by(
                models.Case(
                    models.When(site=site, then=0),
                    models.When(operational_zone=site.operational_zone, then=1),
                    default=2,
                )
            )
            .first()
        )
        if not rule:
            continue
        day = date_from
        while day <= date_to:
            plan, made = SupervisorVisitPlan.objects.get_or_create(
                supervisor=supervisor,
                site=site,
                planned_date=day,
                defaults={
                    "company": site.company,
                    "branch": site.managing_branch,
                    "priority": rule.priority,
                    "purpose": rule.name,
                    "status": "DRAFT",
                    "generated_from_requirement": rule,
                    "created_by": actor,
                },
            )
            if made:
                plans.append(plan)
            day += timedelta(days={"DAY": 1, "WEEK": 7, "MONTH": 30}[rule.frequency_period])
    return plans


def evidence_metadata(upload) -> dict:
    allowed = {"image/jpeg", "image/png", "application/pdf"}
    if upload.content_type not in allowed:
        raise SupervisionValidationError("Unsupported evidence file type.")
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    return {
        "original_filename": upload.name,
        "file_size": upload.size,
        "mime_type": upload.content_type,
        "sha256_hash": digest.hexdigest(),
    }
