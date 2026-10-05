# mypy: disable-error-code="no-untyped-def"
from __future__ import annotations

from django.db.models import Count, F, Prefetch, Q, QuerySet

from .models import DutyAssignment, DutyShift, ReplacementRequest, RosterPeriod
from .tenant_queries import (
    consistent_duty_assignments,
    consistent_duty_shifts,
    consistent_replacement_requests,
    consistent_rosters,
)

ACTIVE_ASSIGNMENT_STATUSES = ("PLANNED", "CONFIRMED")


def get_roster(*, roster_id) -> RosterPeriod:
    assignments = consistent_duty_assignments(
        DutyAssignment.objects.select_related("employee", "deployment")
    )
    shifts = consistent_duty_shifts(
        DutyShift.objects.select_related("site", "post").prefetch_related(
            Prefetch("assignments", queryset=assignments)
        )
    )
    return consistent_rosters(
        RosterPeriod.objects.select_related("company", "branch").prefetch_related(
            Prefetch("duty_shifts", queryset=shifts)
        )
    ).get(pk=roster_id)


def get_assignments(*, roster: RosterPeriod) -> QuerySet[DutyAssignment]:
    return consistent_duty_assignments(
        DutyAssignment.objects.filter(duty_shift__roster_period=roster).select_related(
            "employee", "deployment", "duty_shift__site", "duty_shift__post"
        )
    )


def get_unfilled_positions(*, roster: RosterPeriod) -> QuerySet[DutyShift]:
    return (
        consistent_duty_shifts(DutyShift.objects.filter(roster_period=roster))
        .exclude(status="CANCELLED")
        .annotate(
            assigned_headcount=Count(
                "assignments",
                filter=Q(
                    assignments__in=consistent_duty_assignments(DutyAssignment.objects.all()),
                    assignments__status__in=ACTIVE_ASSIGNMENT_STATUSES,
                ),
            )
        )
        .filter(assigned_headcount__lt=F("required_headcount"))
        .select_related("site", "post", "staffing_requirement")
    )


def get_employee_assignments(*, employee, start=None, end=None) -> QuerySet[DutyAssignment]:
    queryset = consistent_duty_assignments(
        DutyAssignment.objects.filter(employee=employee).select_related(
            "duty_shift__roster_period", "duty_shift__site", "duty_shift__post"
        )
    )
    if start:
        queryset = queryset.filter(duty_shift__ends_at__gt=start)
    if end:
        queryset = queryset.filter(duty_shift__starts_at__lt=end)
    return queryset.order_by("duty_shift__starts_at")


def get_replacement_queue(*, company, branch=None) -> QuerySet[ReplacementRequest]:
    queryset = consistent_replacement_requests(
        ReplacementRequest.objects.filter(status__in=["OPEN", "ASSIGNED"]).select_related(
            "duty_shift__site",
            "duty_shift__post",
            "original_assignment__employee",
            "requested_employee",
            "replacement_employee",
        )
    )
    queryset = queryset.filter(company=company)
    if branch:
        queryset = queryset.filter(duty_shift__branch=branch)
    return queryset.order_by("-priority", "requested_at")
