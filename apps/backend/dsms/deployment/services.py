# mypy: disable-error-code="attr-defined,no-untyped-call"
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.contracts.enums import ClientStatus, ContractStatus, PostStatus, SiteStatus
from dsms.contracts.models import SecurityPost, SecuritySite, SiteCalendarException
from dsms.contracts.selectors import get_active_staffing_requirements
from dsms.documents.enums import DocumentStatus
from dsms.identity.models import User
from dsms.leave.services import evaluate_employee_availability
from dsms.training.enums import ReadinessStatus
from dsms.training.services import evaluate_employee_readiness
from dsms.workforce.enums import EmploymentStatus
from dsms.workforce.models import Employee

from .enums import (
    AssignmentType,
    DeploymentStatus,
    DutyAssignmentStatus,
    EligibilityStatus,
    RosterChangeType,
    RosterStatus,
)
from .exceptions import AssignmentConflict, IneligibleEmployee, RosterTransitionError
from .models import (
    DutyAssignment,
    DutyShift,
    EmployeeDeployment,
    EmployeeScheduleBlock,
    ReplacementRequest,
    RosterChangeEvent,
    RosterPeriod,
    SchedulingPolicy,
)


@dataclass(frozen=True)
class EligibilityResult:
    employee: Employee
    status: str
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    requirements_checked: int
    planned_hours: Decimal


def employee_planned_hours(employee: Employee, date_from: date, date_to: date) -> Decimal:
    assignments = DutyAssignment.objects.filter(
        employee=employee,
        status__in=[DutyAssignmentStatus.PLANNED, DutyAssignmentStatus.CONFIRMED],
        duty_shift__duty_date__range=(date_from, date_to),
    ).select_related("duty_shift")
    seconds = sum(
        Decimal(str((item.duty_shift.ends_at - item.duty_shift.starts_at).total_seconds()))
        for item in assignments
    )
    return (seconds / Decimal("3600")).quantize(Decimal("0.01"))


def evaluate_deployment_eligibility(
    *,
    employee: Employee,
    site: SecuritySite,
    post: SecurityPost | None = None,
    duty_shift: DutyShift | None = None,
    duty_start: datetime | None = None,
    duty_end: datetime | None = None,
    as_of_datetime: datetime | None = None,
) -> EligibilityResult:
    moment = as_of_datetime or timezone.now()
    blocking: list[str] = []
    warnings: list[str] = []
    if employee.company_id != site.company_id:
        blocking.append("CROSS_COMPANY_MISMATCH")
    if employee.employment_status != EmploymentStatus.ACTIVE or not employee.is_active:
        blocking.append("EMPLOYEE_INACTIVE")
    if site.client.status != ClientStatus.ACTIVE or site.contract.status != ContractStatus.ACTIVE:
        blocking.append("CONTRACT_INACTIVE")
    if site.status != SiteStatus.ACTIVE:
        blocking.append("SITE_INACTIVE")
    if post and post.status != PostStatus.ACTIVE:
        blocking.append("POST_INACTIVE")
    readiness = evaluate_employee_readiness(employee=employee, as_of_date=moment.date())
    if readiness.status == ReadinessStatus.NOT_READY:
        blocking.append("READINESS_NOT_READY")
    if post:
        for qualification_requirement in post.qualification_requirements.filter(
            is_active=True
        ).select_related("qualification_type"):
            if (
                not employee.qualifications.filter(
                    qualification_type=qualification_requirement.qualification_type, status="VALID"
                )
                .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=moment.date()))
                .exists()
            ):
                blocking.append("MISSING_QUALIFICATION")
        for credential_requirement in post.credential_requirements.filter(
            is_active=True
        ).select_related("document_type"):
            documents = employee.documents.filter(
                document_type=credential_requirement.document_type
            )
            if credential_requirement.must_be_verified:
                documents = documents.filter(status=DocumentStatus.VERIFIED)
            if credential_requirement.must_be_unexpired:
                documents = documents.filter(
                    Q(expires_on__isnull=True) | Q(expires_on__gte=moment.date())
                )
            if not documents.exists():
                any_document = employee.documents.filter(
                    document_type=credential_requirement.document_type
                ).first()
                blocking.append(
                    "DOCUMENT_PENDING_VERIFICATION"
                    if any_document and any_document.status in {"DRAFT", "PENDING_VERIFICATION"}
                    else "EXPIRED_CREDENTIAL"
                    if any_document
                    and any_document.expires_on
                    and any_document.expires_on < moment.date()
                    else "MISSING_CREDENTIAL"
                )
    planned = Decimal("0")
    if duty_shift:
        availability = evaluate_employee_availability(
            employee=employee,
            starts_at=duty_shift.starts_at,
            ends_at=duty_shift.ends_at,
        )
        if "APPROVED_LEAVE" in availability.blocking_reasons:
            blocking.append("APPROVED_LEAVE")
        if "PENDING_LEAVE_OVERLAP" in availability.warnings:
            warnings.append("PENDING_LEAVE_OVERLAP")
        if employee.employee_type != duty_shift.employee_type:
            blocking.append("EMPLOYEE_TYPE_MISMATCH")
        if duty_shift.designation_id and employee.designation_id != duty_shift.designation_id:
            blocking.append("DESIGNATION_MISMATCH")
        if EmployeeScheduleBlock.objects.filter(
            employee=employee,
            is_active=True,
            starts_at__lt=duty_shift.ends_at,
            ends_at__gt=duty_shift.starts_at,
        ).exists():
            blocking.append("SCHEDULE_BLOCK")
        if (
            DutyAssignment.objects.filter(
                employee=employee,
                status__in=[DutyAssignmentStatus.PLANNED, DutyAssignmentStatus.CONFIRMED],
                duty_shift__starts_at__lt=duty_shift.ends_at,
                duty_shift__ends_at__gt=duty_shift.starts_at,
            )
            .exclude(duty_shift=duty_shift)
            .exists()
        ):
            blocking.append("SHIFT_OVERLAP")
        week_start = duty_shift.duty_date - timedelta(days=duty_shift.duty_date.weekday())
        planned = employee_planned_hours(employee, week_start, week_start + timedelta(days=6))
        policy = SchedulingPolicy.objects.filter(company=employee.company, is_active=True).first()
        if employee.branch_id != duty_shift.branch_id and not (
            policy and policy.allow_cross_branch_deployment
        ):
            blocking.append("CROSS_BRANCH_RESTRICTED")
        if (
            policy
            and policy.maximum_planned_hours_per_week
            and planned >= policy.maximum_planned_hours_per_week
        ):
            blocking.append("WEEKLY_HOUR_LIMIT")
    elif duty_start and duty_end:
        availability = evaluate_employee_availability(
            employee=employee, starts_at=duty_start, ends_at=duty_end
        )
        blocking.extend(availability.blocking_reasons)
        warnings.extend(availability.warnings)
    status = (
        EligibilityStatus.INELIGIBLE
        if blocking
        else EligibilityStatus.ELIGIBLE_WITH_WARNING
        if warnings
        else EligibilityStatus.ELIGIBLE
    )
    return EligibilityResult(
        employee, status, tuple(sorted(set(blocking))), tuple(warnings), len(blocking), planned
    )


@transaction.atomic
def generate_roster_demand(
    *, roster_period: RosterPeriod, actor: User | None = None
) -> dict[str, int]:
    roster = RosterPeriod.objects.select_for_update().get(pk=roster_period.pk)
    if roster.status not in {RosterStatus.DRAFT, RosterStatus.GENERATED}:
        raise RosterTransitionError("Only draft/generated rosters accept demand generation.")
    generated = skipped = 0
    day = roster.period_start
    while day <= roster.period_end:
        for requirement in get_active_staffing_requirements(
            on_date=day, company=roster.company, branch=roster.branch
        ):
            if (
                requirement.days.exists()
                and not requirement.days.filter(weekday=day.strftime("%A").upper()).exists()
            ):
                continue
            if SiteCalendarException.objects.filter(
                site=requirement.site, date=day, is_closed=True
            ).exists():
                skipped += 1
                continue
            zone = ZoneInfo(requirement.site.timezone)
            starts = datetime.combine(day, requirement.start_time, tzinfo=zone)
            end_day = (
                day + timedelta(days=1)
                if requirement.crosses_midnight or requirement.end_time <= requirement.start_time
                else day
            )
            ends = datetime.combine(end_day, requirement.end_time, tzinfo=zone)
            _, created = DutyShift.objects.get_or_create(
                roster_period=roster,
                staffing_requirement=requirement,
                duty_date=day,
                starts_at=starts,
                defaults={
                    "company": roster.company,
                    "branch": roster.branch,
                    "client": requirement.contract.client,
                    "contract": requirement.contract,
                    "site": requirement.site,
                    "post": requirement.post,
                    "ends_at": ends,
                    "required_headcount": requirement.required_headcount,
                    "employee_type": requirement.employee_type,
                    "designation": requirement.designation,
                    "armed_required": requirement.armed_required,
                    "supervisor_required": requirement.supervisor_required,
                },
            )
            generated += int(created)
            skipped += int(not created)
        day += timedelta(days=1)
    roster.status, roster.generated_at, roster.generated_by = (
        RosterStatus.GENERATED,
        timezone.now(),
        actor,
    )
    roster.save(update_fields=["status", "generated_at", "generated_by", "updated_at"])
    return {"generated": generated, "skipped": skipped}


@transaction.atomic
def assign_employee_to_shift(
    *,
    duty_shift: DutyShift,
    employee: Employee,
    actor: User,
    assignment_type: str = AssignmentType.REGULAR,
    allow_overstaffing: bool = False,
) -> DutyAssignment:
    shift = (
        DutyShift.objects.select_for_update()
        .select_related("site__client", "site__contract", "post", "roster_period")
        .get(pk=duty_shift.pk)
    )
    # Serialize all assignment decisions for this employee, even across different shifts.
    employee = Employee.objects.select_for_update().get(pk=employee.pk)
    if shift.roster_period.status in {
        RosterStatus.PUBLISHED,
        RosterStatus.LOCKED,
        RosterStatus.CLOSED,
    }:
        raise RosterTransitionError(
            "Published or locked rosters require a controlled change workflow."
        )
    assigned = shift.assignments.filter(
        status__in=[DutyAssignmentStatus.PLANNED, DutyAssignmentStatus.CONFIRMED]
    ).count()
    if assigned >= shift.required_headcount and not allow_overstaffing:
        raise AssignmentConflict("Duty shift required headcount is already filled.")
    eligibility = evaluate_deployment_eligibility(
        employee=employee,
        site=shift.site,
        post=shift.post,
        duty_shift=shift,
        as_of_datetime=shift.starts_at,
    )
    if eligibility.status == EligibilityStatus.INELIGIBLE:
        raise IneligibleEmployee(",".join(eligibility.blocking_reasons))
    deployment = EmployeeDeployment.objects.filter(
        employee=employee, site=shift.site, status=DeploymentStatus.ACTIVE
    ).first()
    assignment = DutyAssignment.objects.create(
        duty_shift=shift,
        employee=employee,
        deployment=deployment,
        assignment_type=assignment_type,
        assigned_by=actor,
    )
    RosterChangeEvent.objects.create(
        roster_period=shift.roster_period,
        duty_shift=shift,
        duty_assignment=assignment,
        change_type=RosterChangeType.ASSIGNED,
        actor=actor,
        new_employee=employee,
    )
    return assignment


def _roster_event(roster: RosterPeriod, actor: User, kind: str, reason: str = "") -> None:
    RosterChangeEvent.objects.create(
        roster_period=roster, change_type=kind, actor=actor, reason=reason
    )


@transaction.atomic
def submit_roster(*, roster: RosterPeriod, actor: User) -> RosterPeriod:
    obj = RosterPeriod.objects.select_for_update().get(pk=roster.pk)
    if obj.status not in {RosterStatus.DRAFT, RosterStatus.GENERATED}:
        raise RosterTransitionError("Only a draft/generated roster may be submitted.")
    if not obj.duty_shifts.exists():
        raise RosterTransitionError("A roster without contractual duty shifts cannot be submitted.")
    obj.status, obj.submitted_by, obj.submitted_at = (
        RosterStatus.UNDER_REVIEW,
        actor,
        timezone.now(),
    )
    obj.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])
    return obj


@transaction.atomic
def approve_roster(*, roster: RosterPeriod, actor: User) -> RosterPeriod:
    obj = RosterPeriod.objects.select_for_update().get(pk=roster.pk)
    if obj.status != RosterStatus.UNDER_REVIEW:
        raise RosterTransitionError("Only a submitted roster may be approved.")
    if obj.created_by_id == actor.id or obj.submitted_by_id == actor.id:
        raise RosterTransitionError("Roster approval requires an independent checker.")
    obj.status, obj.approved_by, obj.approved_at = RosterStatus.APPROVED, actor, timezone.now()
    obj.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    record_audit_event(
        action="ROSTER_APPROVED",
        category=AuditCategory.DEPLOYMENT,
        severity=AuditSeverity.HIGH,
        summary="Roster approved.",
        actor_user=actor,
        company=obj.company,
        branch=obj.branch,
        source_object=obj,
        object_reference=obj.roster_number,
    )
    return obj


@transaction.atomic
def publish_roster(*, roster: RosterPeriod, actor: User) -> RosterPeriod:
    obj = RosterPeriod.objects.select_for_update().get(pk=roster.pk)
    if obj.status != RosterStatus.APPROVED:
        raise RosterTransitionError("Only an approved roster may be published.")
    obj.status, obj.published_by, obj.published_at = RosterStatus.PUBLISHED, actor, timezone.now()
    obj.save(update_fields=["status", "published_by", "published_at", "updated_at"])
    obj.duty_shifts.exclude(status="CANCELLED").update(status="PUBLISHED")
    _roster_event(obj, actor, RosterChangeType.PUBLISHED)
    record_audit_event(
        action="ROSTER_PUBLISHED",
        category=AuditCategory.DEPLOYMENT,
        severity=AuditSeverity.HIGH,
        summary="Roster published.",
        actor_user=actor,
        company=obj.company,
        branch=obj.branch,
        source_object=obj,
        object_reference=obj.roster_number,
    )
    return obj


@transaction.atomic
def lock_roster(*, roster: RosterPeriod, actor: User) -> RosterPeriod:
    obj = RosterPeriod.objects.select_for_update().get(pk=roster.pk)
    if obj.status != RosterStatus.PUBLISHED:
        raise RosterTransitionError("Only a published roster may be locked.")
    obj.status, obj.locked_by, obj.locked_at = RosterStatus.LOCKED, actor, timezone.now()
    obj.save(update_fields=["status", "locked_by", "locked_at", "updated_at"])
    _roster_event(obj, actor, RosterChangeType.LOCKED)
    record_audit_event(
        action="ROSTER_LOCKED",
        category=AuditCategory.DEPLOYMENT,
        severity=AuditSeverity.HIGH,
        summary="Roster locked.",
        actor_user=actor,
        company=obj.company,
        branch=obj.branch,
        source_object=obj,
        object_reference=obj.roster_number,
    )
    return obj


@transaction.atomic
def create_replacement_request(
    *,
    original_assignment: DutyAssignment,
    actor: User,
    reason: str,
    description: str = "",
    priority: str = "NORMAL",
) -> ReplacementRequest:
    assignment = (
        DutyAssignment.objects.select_for_update()
        .select_related("duty_shift")
        .get(pk=original_assignment.pk)
    )
    if assignment.status not in {DutyAssignmentStatus.PLANNED, DutyAssignmentStatus.CONFIRMED}:
        raise AssignmentConflict("Only an active assignment can be replaced.")
    request, _ = ReplacementRequest.objects.get_or_create(
        original_assignment=assignment,
        status="OPEN",
        defaults={
            "company": assignment.duty_shift.company,
            "duty_shift": assignment.duty_shift,
            "requested_employee": assignment.employee,
            "reason": reason,
            "description": description,
            "priority": priority,
            "requested_by": actor,
        },
    )
    return request


@transaction.atomic
def assign_replacement(
    *, replacement_request: ReplacementRequest, employee: Employee, actor: User
) -> DutyAssignment:
    request = (
        ReplacementRequest.objects.select_for_update()
        .select_related("duty_shift", "original_assignment")
        .get(pk=replacement_request.pk)
    )
    if request.status not in {"OPEN", "ASSIGNED"}:
        raise AssignmentConflict("Replacement request is no longer open.")
    if not request.original_assignment_id:
        raise AssignmentConflict("A replacement requires an original assignment.")
    Employee.objects.select_for_update().get(pk=employee.pk)
    original = DutyAssignment.objects.select_for_update().get(pk=request.original_assignment_id)
    eligibility = evaluate_deployment_eligibility(
        employee=employee,
        site=request.duty_shift.site,
        post=request.duty_shift.post,
        duty_shift=request.duty_shift,
        as_of_datetime=request.duty_shift.starts_at,
    )
    if eligibility.status == EligibilityStatus.INELIGIBLE:
        raise IneligibleEmployee(",".join(eligibility.blocking_reasons))
    replacement = DutyAssignment.objects.create(
        duty_shift=request.duty_shift,
        employee=employee,
        deployment=None,
        assignment_type=AssignmentType.REPLACEMENT,
        status=DutyAssignmentStatus.CONFIRMED,
        assigned_by=actor,
        replaces_assignment=original,
        replacement_reason=request.reason,
    )
    original.status = DutyAssignmentStatus.REPLACED
    original.save(update_fields=["status", "updated_at"])
    request.replacement_employee, request.assigned_by = employee, actor
    request.approved_by, request.status, request.completed_at = actor, "COMPLETED", timezone.now()
    request.save(
        update_fields=[
            "replacement_employee",
            "assigned_by",
            "approved_by",
            "status",
            "completed_at",
            "updated_at",
        ]
    )
    _roster_event(
        request.duty_shift.roster_period, actor, RosterChangeType.REPLACED, request.reason
    )
    record_audit_event(
        action="ROSTER_REPLACEMENT_APPROVED",
        category=AuditCategory.DEPLOYMENT,
        severity=AuditSeverity.HIGH,
        summary="Roster replacement approved.",
        actor_user=actor,
        company=request.company,
        branch=request.duty_shift.branch,
        source_object=request,
        metadata_safe={"reason": request.reason},
    )
    return replacement


def get_shift_coverage(duty_shift: DutyShift) -> dict[str, Decimal | int]:
    assigned = duty_shift.assignments.filter(
        status__in=[DutyAssignmentStatus.PLANNED, DutyAssignmentStatus.CONFIRMED]
    ).count()
    confirmed = duty_shift.assignments.filter(status=DutyAssignmentStatus.CONFIRMED).count()
    return {
        "required_headcount": duty_shift.required_headcount,
        "assigned_headcount": assigned,
        "confirmed_headcount": confirmed,
        "shortage": max(duty_shift.required_headcount - assigned, 0),
        "approved_extra": max(assigned - duty_shift.required_headcount, 0),
        "coverage_percentage": (
            Decimal(assigned) / Decimal(duty_shift.required_headcount) * 100
        ).quantize(Decimal("0.01")),
    }
