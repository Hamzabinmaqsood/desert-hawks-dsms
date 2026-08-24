# mypy: disable-error-code="no-untyped-def"
from django.db.models import Count, QuerySet

from .models import PatrolException, PatrolRun, PatrolTask


def get_patrol_schedule(*, start=None, end=None, company=None) -> QuerySet[PatrolTask]:
    queryset = PatrolTask.objects.select_related("site", "patrol_route", "assigned_employee")
    if start:
        queryset = queryset.filter(scheduled_start_at__gte=start)
    if end:
        queryset = queryset.filter(scheduled_start_at__lt=end)
    return queryset.filter(company=company) if company else queryset


def get_active_patrol_runs(*, company=None) -> QuerySet[PatrolRun]:
    queryset = PatrolRun.objects.filter(status="IN_PROGRESS").select_related(
        "patrol_task", "site", "employee", "route_version"
    )
    return queryset.filter(company=company) if company else queryset


def get_patrol_exceptions(*, company=None) -> QuerySet[PatrolException]:
    queryset = PatrolException.objects.filter(status__in=["OPEN", "ACKNOWLEDGED"]).select_related(
        "patrol_task__site", "patrol_run", "checkpoint_visit"
    )
    return queryset.filter(company=company) if company else queryset


def get_checkpoint_completion(*, company=None):
    queryset = PatrolRun.objects.annotate(
        actual_checkpoints=Count("checkpoint_visits", distinct=True),
        expected_checkpoints=Count("route_version__route_checkpoints", distinct=True),
    ).select_related("patrol_task", "site")
    return queryset.filter(company=company) if company else queryset
