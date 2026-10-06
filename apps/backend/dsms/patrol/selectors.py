# mypy: disable-error-code="no-untyped-def,no-untyped-call,no-any-return"
from django.db.models import Count, Q, QuerySet

from .models import CheckpointVisit, PatrolException, PatrolRouteCheckpoint, PatrolRun, PatrolTask
from .tenant_queries import (
    consistent_exceptions,
    consistent_route_checkpoints,
    consistent_runs,
    consistent_tasks,
    consistent_visits,
)


def get_patrol_schedule(*, company, start=None, end=None) -> QuerySet[PatrolTask]:
    queryset = consistent_tasks(
        PatrolTask.objects.select_related("site", "patrol_route", "assigned_employee")
    ).filter(company=company)
    if start:
        queryset = queryset.filter(scheduled_start_at__gte=start)
    if end:
        queryset = queryset.filter(scheduled_start_at__lt=end)
    return queryset


def get_active_patrol_runs(*, company) -> QuerySet[PatrolRun]:
    return consistent_runs(
        PatrolRun.objects.filter(status="IN_PROGRESS").select_related(
            "patrol_task", "site", "employee", "route_version"
        )
    ).filter(company=company)


def get_patrol_exceptions(*, company) -> QuerySet[PatrolException]:
    return consistent_exceptions(
        PatrolException.objects.filter(status__in=["OPEN", "ACKNOWLEDGED"]).select_related(
            "patrol_task__site", "patrol_run", "checkpoint_visit"
        )
    ).filter(company=company)


def get_checkpoint_completion(*, company):
    valid_visits = consistent_visits(CheckpointVisit.objects.all())
    valid_route_checkpoints = consistent_route_checkpoints(PatrolRouteCheckpoint.objects.all())
    return (
        consistent_runs(PatrolRun.objects.all())
        .filter(company=company)
        .annotate(
            actual_checkpoints=Count(
                "checkpoint_visits",
                filter=Q(checkpoint_visits__in=valid_visits),
                distinct=True,
            ),
            expected_checkpoints=Count(
                "route_version__route_checkpoints",
                filter=Q(route_version__route_checkpoints__in=valid_route_checkpoints),
                distinct=True,
            ),
        )
        .select_related("patrol_task", "site")
    )
