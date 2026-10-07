# mypy: disable-error-code="no-untyped-def,no-untyped-call"
from datetime import timedelta

from django.db.models import QuerySet
from django.utils import timezone

from .models import Incident, IncidentEscalation, SOSAlert
from .services import command_center_queue
from .tenant_queries import consistent_escalations, consistent_incidents, consistent_sos_alerts


def get_active_incidents(*, company) -> QuerySet[Incident]:
    queryset = consistent_incidents(
        Incident.objects.exclude(status__in=["CLOSED", "CANCELLED"])
        .select_related(
            "company", "branch", "client", "site", "post", "incident_type", "command_center_owner"
        )
        .prefetch_related("responders", "actions", "escalations")
    )
    return queryset.filter(company=company)


def get_command_center_queue(*, company):
    return command_center_queue(get_active_incidents(company=company))


def get_active_sos(*, company) -> QuerySet[SOSAlert]:
    queryset = consistent_sos_alerts(
        SOSAlert.objects.exclude(
            status__in=["CLOSED", "CANCELLED_BY_REPORTER", "FALSE_ALARM_CONFIRMED"]
        ).select_related("employee", "site", "post", "linked_incident")
    )
    return queryset.filter(company=company)


def get_overdue_acknowledgements(*, company, minutes=5) -> QuerySet[Incident]:
    return get_active_incidents(company=company).filter(
        acknowledged_at__isnull=True,
        reported_at__lt=timezone.now() - timedelta(minutes=minutes),
    )


def get_overdue_responses(*, company, minutes=15) -> QuerySet[Incident]:
    return get_active_incidents(company=company).filter(
        responding_at__isnull=True,
        reported_at__lt=timezone.now() - timedelta(minutes=minutes),
    )


def get_recent_escalations(*, company) -> QuerySet[IncidentEscalation]:
    return (
        consistent_escalations(
            IncidentEscalation.objects.select_related("incident", "policy", "actor")
        )
        .filter(incident__company=company)
        .order_by("-triggered_at")
    )
