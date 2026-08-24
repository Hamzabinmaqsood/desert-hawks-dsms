# mypy: disable-error-code="no-untyped-def,no-untyped-call"
from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

from .models import Incident, IncidentEscalation, SOSAlert
from .services import command_center_queue


def get_active_incidents(*, company=None) -> QuerySet[Incident]:
    queryset = (
        Incident.objects.exclude(status__in=["CLOSED", "CANCELLED"])
        .select_related(
            "company", "branch", "client", "site", "post", "incident_type", "command_center_owner"
        )
        .prefetch_related("responders", "actions", "escalations")
    )
    return queryset.filter(company=company) if company else queryset


def get_command_center_queue(*, company=None):
    return command_center_queue(get_active_incidents(company=company))


def get_active_sos(*, company=None) -> QuerySet[SOSAlert]:
    queryset = SOSAlert.objects.exclude(
        status__in=["CLOSED", "CANCELLED_BY_REPORTER", "FALSE_ALARM_CONFIRMED"]
    ).select_related("employee", "site", "post", "linked_incident")
    return queryset.filter(company=company) if company else queryset


def get_overdue_acknowledgements(*, company=None, minutes=5) -> QuerySet[Incident]:
    return get_active_incidents(company=company).filter(
        acknowledged_at__isnull=True,
        reported_at__lt=timezone.now() - timedelta(minutes=minutes),
    )


def get_overdue_responses(*, company=None, minutes=15) -> QuerySet[Incident]:
    return get_active_incidents(company=company).filter(
        responding_at__isnull=True,
        reported_at__lt=timezone.now() - timedelta(minutes=minutes),
    )


def get_recent_escalations(*, company=None) -> QuerySet[IncidentEscalation]:
    queryset = IncidentEscalation.objects.select_related("incident", "policy", "actor")
    if company:
        queryset = queryset.filter(incident__company=company)
    return queryset.order_by("-triggered_at")
