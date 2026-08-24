# mypy: disable-error-code="no-untyped-def"
from __future__ import annotations

from django.db.models import Count, F, Q, QuerySet

from .models import DutyAssignment, DutyShift, ReplacementRequest, RosterPeriod

ACTIVE_ASSIGNMENT_STATUSES = ("PLANNED", "CONFIRMED")


def get_roster(*, roster_id) -> RosterPeriod:
    return (
        RosterPeriod.objects.select_related("company", "branch")
        .prefetch_related(
            "duty_shifts__site",
            "duty_shifts__post",
            "duty_shifts__assignments__employee",
        )
        .get(pk=roster_id)
    )


def get_assignments(*, roster: RosterPeriod) -> QuerySet[DutyAssignment]:
    return DutyAssignment.objects.filter(duty_shift__roster_period=roster).select_related(
        "employee", "deployment", "duty_shift__site", "duty_shift__post"
    )


def get_unfilled_positions(*, roster: RosterPeriod) -> QuerySet[DutyShift]:
    return (
        DutyShift.objects.filter(roster_period=roster)
        .exclude(status="CANCELLED")
        .annotate(
            assigned_headcount=Count(
                "assignments", filter=Q(assignments__status__in=ACTIVE_ASSIGNMENT_STATUSES)
            )
        )
        .filter(assigned_headcount__lt=F("required_headcount"))
        .select_related("site", "post", "staffing_requirement")
    )


def get_employee_assignments(*, employee, start=None, end=None) -> QuerySet[DutyAssignment]:
    queryset = DutyAssignment.objects.filter(employee=employee).select_related(
        "duty_shift__roster_period", "duty_shift__site", "duty_shift__post"
    )
    if start:
        queryset = queryset.filter(duty_shift__ends_at__gt=start)
    if end:
        queryset = queryset.filter(duty_shift__starts_at__lt=end)
    return queryset.order_by("duty_shift__starts_at")


def get_replacement_queue(*, company=None, branch=None) -> QuerySet[ReplacementRequest]:
    queryset = ReplacementRequest.objects.filter(status__in=["OPEN", "ASSIGNED"]).select_related(
        "duty_shift__site",
        "duty_shift__post",
        "original_assignment__employee",
        "requested_employee",
        "replacement_employee",
    )
    if company:
        queryset = queryset.filter(company=company)
    if branch:
        queryset = queryset.filter(duty_shift__branch=branch)
    return queryset.order_by("-priority", "requested_at")
