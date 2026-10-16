# mypy: disable-error-code="no-untyped-def,no-untyped-call"
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from dsms.deployment.models import DutyAssignment, EmployeeScheduleBlock
from dsms.notifications.services import publish_notification_event
from dsms.subscriptions.enforcement import requires_company_module
from dsms.training.models import TrainingEnrollment

from .models import (
    EmployeeLeavePolicyAssignment,
    Holiday,
    LeaveApprovalAction,
    LeaveBalanceAccount,
    LeaveBalanceTransaction,
    LeaveEvent,
    LeavePolicy,
    LeavePolicyRule,
    LeaveRequest,
)


@dataclass(frozen=True)
class PolicyResolution:
    policy: object
    rule: object
    reason: str


@dataclass(frozen=True)
class AvailabilityResult:
    employee: object
    availability_status: str
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    approved_leave: tuple[object, ...]
    pending_leave: tuple[object, ...]
    schedule_blocks: tuple[object, ...]
    training_conflicts: tuple[object, ...]
    existing_duty_assignments: tuple[object, ...]


def resolve_leave_policy(*, employee, leave_type, at_date):
    assignment = (
        EmployeeLeavePolicyAssignment.objects.filter(employee=employee, effective_from__lte=at_date)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=at_date))
        .select_related("leave_policy")
        .order_by("-effective_from")
        .first()
    )
    policies = LeavePolicy.objects.filter(
        company=employee.company, is_active=True, effective_from__lte=at_date
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=at_date))
    if assignment:
        policies = policies.filter(pk=assignment.leave_policy_id)
    rules = (
        LeavePolicyRule.objects.filter(policy__in=policies, leave_type=leave_type, is_active=True)
        .filter(Q(branch__isnull=True) | Q(branch=employee.branch))
        .filter(Q(department__isnull=True) | Q(department=employee.department))
        .filter(Q(designation__isnull=True) | Q(designation=employee.designation))
        .filter(Q(employee_type="") | Q(employee_type=employee.employee_type))
        .filter(Q(employment_type="") | Q(employment_type=employee.employment_type))
    )
    rule = (
        rules.select_related("policy")
        .order_by("-branch_id", "-department_id", "-designation_id", "-employee_type")
        .first()
    )
    if not rule:
        raise ValueError("No applicable leave policy rule.")
    return PolicyResolution(
        rule.policy, rule, "EXPLICIT_ASSIGNMENT" if assignment else "MOST_SPECIFIC_RULE"
    )


def calculate_leave_units(
    *, employee: Any, leave_type: Any, starts_at: Any, ends_at: Any, policy_rule: Any
) -> Decimal:
    if starts_at >= ends_at:
        raise ValueError("Leave end must be after start.")
    duration_hours = Decimal(str((ends_at - starts_at).total_seconds())) / Decimal("3600")
    if leave_type.unit == "HOURS":
        return duration_hours.quantize(Decimal("0.01"))
    if policy_rule.charge_method == "ROSTERED_DUTY":
        count = DutyAssignment.objects.filter(
            employee=employee,
            status__in=["PLANNED", "CONFIRMED"],
            duty_shift__starts_at__lt=ends_at,
            duty_shift__ends_at__gt=starts_at,
        ).count()
        return Decimal(count)
    start_date, end_date = timezone.localtime(starts_at).date(), timezone.localtime(ends_at).date()
    days = Decimal((end_date - start_date).days + 1)
    if not policy_rule.holidays_are_chargeable:
        holidays = (
            Holiday.objects.filter(
                calendar__company=employee.company,
                status="ACTIVE",
                affects_leave_charging=True,
                date__range=(start_date, end_date),
            )
            .values("date")
            .distinct()
            .count()
        )
        days -= Decimal(holidays)
    return max(days, Decimal("0"))


def get_leave_balance(*, employee, leave_type, as_of_datetime=None):
    when = as_of_datetime or timezone.now()
    qs = LeaveBalanceTransaction.objects.filter(
        balance_account__employee=employee,
        balance_account__leave_type=leave_type,
        effective_at__lte=when,
    )
    totals = {
        row["transaction_type"]: row["total"] or Decimal("0")
        for row in qs.values("transaction_type").annotate(total=Sum("units"))
    }
    available = sum(totals.values(), Decimal("0"))
    return {
        "opening": totals.get("OPENING", Decimal("0")),
        "entitled": totals.get("ENTITLEMENT", Decimal("0")),
        "accrued": totals.get("ACCRUAL", Decimal("0")),
        "reserved": -totals.get("RESERVATION", Decimal("0")),
        "taken": -totals.get("LEAVE_TAKEN", Decimal("0")),
        "adjusted": totals.get("ADJUSTMENT_CREDIT", Decimal("0"))
        + totals.get("ADJUSTMENT_DEBIT", Decimal("0")),
        "expired": -totals.get("EXPIRY", Decimal("0")),
        "carried_forward": totals.get("CARRY_FORWARD", Decimal("0")),
        "available": available,
    }


@transaction.atomic
@requires_company_module("leave", argument="employee")
def create_leave_request(
    *, actor, employee, leave_type, starts_at, ends_at, reason, emergency_request=False
):
    if (
        not employee.company.is_active
        or employee.employment_status != "ACTIVE"
        or not getattr(actor, "is_active", False)
        or employee.user_id != actor.id
        or leave_type.status != "ACTIVE"
        or employee.company_id != leave_type.company_id
        and leave_type.company_id
    ):
        raise ValueError("Leave type is unavailable for this employee.")
    resolved = resolve_leave_policy(
        employee=employee, leave_type=leave_type, at_date=timezone.localtime(starts_at).date()
    )
    units = calculate_leave_units(
        employee=employee,
        leave_type=leave_type,
        starts_at=starts_at,
        ends_at=ends_at,
        policy_rule=resolved.rule,
    )
    if resolved.rule.minimum_request_units and units < resolved.rule.minimum_request_units:
        raise ValueError("Requested units are below policy minimum.")
    if resolved.rule.maximum_consecutive_units and units > resolved.rule.maximum_consecutive_units:
        raise ValueError("Requested units exceed policy maximum.")
    return LeaveRequest.objects.create(
        request_number=f"LR-{timezone.now():%Y}-{uuid4().hex[:12].upper()}",
        company=employee.company,
        employee=employee,
        leave_type=leave_type,
        policy=resolved.policy,
        policy_rule=resolved.rule,
        starts_at=starts_at,
        ends_at=ends_at,
        requested_units=units,
        reason=reason,
        emergency_request=emergency_request,
        created_by=actor,
    )


@transaction.atomic
@requires_company_module("leave", argument="request")
def submit_leave_request(*, request, actor):
    item = LeaveRequest.objects.select_for_update().get(pk=request.pk)
    if item.status != "DRAFT" or item.employee.user_id != actor.id:
        raise ValueError("Only the employee may submit their draft request.")
    if item.leave_type.requires_attachment and not item.attachments.exists():
        raise ValueError("Supporting attachment is required.")
    if (
        LeaveRequest.objects.filter(
            employee=item.employee,
            status__in=["SUBMITTED", "UNDER_REVIEW", "APPROVED", "IN_PROGRESS"],
            starts_at__lt=item.ends_at,
            ends_at__gt=item.starts_at,
        )
        .exclude(pk=item.pk)
        .exists()
    ):
        raise ValueError("Leave request overlaps existing leave.")
    item.status, item.submitted_at = "SUBMITTED", timezone.now()
    item.save()
    LeaveEvent.objects.create(
        leave_request=item, event_type="SUBMITTED", actor=actor, occurred_at=timezone.now()
    )
    publish_notification_event(
        event_key=f"leave.request.submitted:{item.id}",
        event_type="LEAVE_APPROVAL_REQUIRED",
        source_app="leave",
        source_model="LeaveRequest",
        source_object_id=item.id,
        company=item.company,
        safe_payload={
            "request_number": item.request_number,
            "message": "A leave request requires review.",
            "actor_user_id": str(actor.id),
        },
    )
    return item


@transaction.atomic
@requires_company_module("leave", argument="request")
def finalize_leave_approval(*, request, actor, approval_step=None, comments=""):
    item = (
        LeaveRequest.objects.select_for_update()
        .select_related("employee", "leave_type", "policy_rule")
        .get(pk=request.pk)
    )
    if item.created_by_id == actor.id:
        raise ValueError("A requester cannot approve their own leave.")
    if item.status not in {"SUBMITTED", "UNDER_REVIEW"}:
        raise ValueError("Leave request is not awaiting approval.")
    if (
        LeaveRequest.objects.select_for_update()
        .filter(
            employee=item.employee,
            status__in=["APPROVED", "IN_PROGRESS"],
            starts_at__lt=item.ends_at,
            ends_at__gt=item.starts_at,
        )
        .exclude(pk=item.pk)
        .exists()
    ):
        raise ValueError("Approved leave overlap detected.")
    if item.leave_type.requires_balance:
        account = (
            LeaveBalanceAccount.objects.select_for_update()
            .filter(
                employee=item.employee,
                leave_type=item.leave_type,
                entitlement_period__period_start__lte=item.starts_at.date(),
                entitlement_period__period_end__gte=item.starts_at.date(),
            )
            .first()
        )
        if not account:
            raise ValueError("No leave balance account covers this request.")
        balance = get_leave_balance(employee=item.employee, leave_type=item.leave_type)
        if (
            balance["available"] < item.requested_units
            and not item.policy_rule.allow_negative_balance
        ):
            raise ValueError("Insufficient leave balance.")
        LeaveBalanceTransaction.objects.get_or_create(
            balance_account=account,
            source_reference=f"RESERVATION:{item.id}",
            defaults={
                "transaction_type": "RESERVATION",
                "units": -item.requested_units,
                "effective_at": timezone.now(),
                "leave_request": item,
                "created_by": actor,
                "reason": "Approved leave reservation",
            },
        )
    item.status, item.approved_units, item.approved_by, item.approved_at = (
        "APPROVED",
        item.requested_units,
        actor,
        timezone.now(),
    )
    item.save()
    if approval_step:
        LeaveApprovalAction.objects.create(
            leave_request=item,
            approval_step=approval_step,
            actor=actor,
            decision="APPROVED",
            comments=comments,
            acted_at=timezone.now(),
        )
    LeaveEvent.objects.create(
        leave_request=item, event_type="APPROVED", actor=actor, occurred_at=timezone.now()
    )
    detect_leave_roster_conflicts(leave_request=item)
    return item


@transaction.atomic
@requires_company_module("leave", argument="request")
def approve_leave_cancellation(*, request, actor):
    item = LeaveRequest.objects.select_for_update().get(pk=request.pk)
    if item.status not in {"APPROVED", "CANCEL_REQUESTED"}:
        raise ValueError("Leave cannot be cancelled in this state.")
    reservation = item.balance_transactions.filter(transaction_type="RESERVATION").first()
    if reservation:
        LeaveBalanceTransaction.objects.get_or_create(
            balance_account=reservation.balance_account,
            source_reference=f"RELEASE:{item.id}",
            defaults={
                "transaction_type": "RESERVATION_RELEASE",
                "units": -reservation.units,
                "effective_at": timezone.now(),
                "leave_request": item,
                "created_by": actor,
                "reason": "Leave cancellation release",
            },
        )
    item.status, item.cancelled_by, item.cancelled_at = "CANCELLED", actor, timezone.now()
    item.save()
    LeaveEvent.objects.create(
        leave_request=item, event_type="CANCELLED", actor=actor, occurred_at=timezone.now()
    )
    return item


def evaluate_employee_availability(*, employee, starts_at, ends_at):
    approved = tuple(
        LeaveRequest.objects.filter(
            employee=employee,
            status__in=["APPROVED", "IN_PROGRESS"],
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )
    )
    pending = tuple(
        LeaveRequest.objects.filter(
            employee=employee,
            status__in=["SUBMITTED", "UNDER_REVIEW"],
            starts_at__lt=ends_at,
            ends_at__gt=starts_at,
        )
    )
    blocks = tuple(
        EmployeeScheduleBlock.objects.filter(
            employee=employee, is_active=True, starts_at__lt=ends_at, ends_at__gt=starts_at
        )
    )
    duties = tuple(
        DutyAssignment.objects.filter(
            employee=employee,
            status__in=["PLANNED", "CONFIRMED"],
            duty_shift__starts_at__lt=ends_at,
            duty_shift__ends_at__gt=starts_at,
        )
    )
    training = tuple(
        TrainingEnrollment.objects.filter(
            employee=employee,
            status__in=["ENROLLED", "CONFIRMED"],
            session__start_datetime__lt=ends_at,
            session__end_datetime__gt=starts_at,
        )
    )
    blocking = (
        ([] if employee.employment_status == "ACTIVE" else ["EMPLOYMENT_STATUS"])
        + (["APPROVED_LEAVE"] if approved else [])
        + (["SCHEDULE_BLOCK"] if blocks else [])
    )
    warnings = (
        (["PENDING_LEAVE_OVERLAP"] if pending else [])
        + (["TRAINING_CONFLICT"] if training else [])
        + (["DUTY_ASSIGNMENT_CONFLICT"] if duties else [])
    )
    status = (
        "UNAVAILABLE_APPROVED_LEAVE"
        if approved
        else "UNAVAILABLE_OTHER"
        if blocking
        else "PARTIALLY_AVAILABLE"
        if pending or duties or training
        else "AVAILABLE"
    )
    return AvailabilityResult(
        employee,
        status,
        tuple(blocking),
        tuple(warnings),
        approved,
        pending,
        blocks,
        training,
        duties,
    )


@transaction.atomic
def detect_leave_roster_conflicts(*, leave_request):
    from dsms.deployment.models import RosterAvailabilityConflict

    assignments = DutyAssignment.objects.filter(
        employee=leave_request.employee,
        status__in=["PLANNED", "CONFIRMED"],
        duty_shift__roster_period__status__in=["PUBLISHED", "LOCKED"],
        duty_shift__starts_at__lt=leave_request.ends_at,
        duty_shift__ends_at__gt=leave_request.starts_at,
    ).select_related("duty_shift")
    conflicts = []
    for assignment in assignments:
        conflict, _ = RosterAvailabilityConflict.objects.get_or_create(
            duty_assignment=assignment,
            leave_request=leave_request,
            defaults={"company": leave_request.company},
        )
        conflicts.append(conflict)
    return tuple(conflicts)


@transaction.atomic
@requires_company_module("leave", argument="conflict")
def create_replacement_request_from_leave(*, conflict, actor):
    from dsms.deployment.models import RosterAvailabilityConflict
    from dsms.deployment.services import create_replacement_request

    item = (
        RosterAvailabilityConflict.objects.select_for_update()
        .select_related("duty_assignment__duty_shift", "leave_request")
        .get(pk=conflict.pk)
    )
    if item.replacement_request_id:
        return item.replacement_request
    replacement = create_replacement_request(
        original_assignment=item.duty_assignment,
        actor=actor,
        reason="LEAVE",
        description=f"Approved leave conflict {item.leave_request.request_number}",
        priority="URGENT",
    )
    item.replacement_request = replacement
    item.status = "REPLACEMENT_REQUESTED"
    item.save(update_fields=["replacement_request", "status", "updated_at"])
    return replacement
