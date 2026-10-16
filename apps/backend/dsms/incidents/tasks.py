# mypy: disable-error-code="no-untyped-def,no-untyped-call"
from celery import shared_task
from django.utils import timezone

from dsms.subscriptions.enforcement import company_ids_with_module

from .models import Incident, IncidentException
from .services import resolve_incident_escalation_policy
from .tenant_queries import consistent_incidents


@shared_task
def reconcile_incident_slas():
    now = timezone.now()
    created = 0
    incidents = consistent_incidents(
        Incident.objects.filter(
            company_id__in=company_ids_with_module("security_incidents")
        ).exclude(status__in=["CLOSED", "CANCELLED"])
    )
    for incident in incidents:
        policy = resolve_incident_escalation_policy(incident)
        if not policy:
            continue
        checks = (
            (
                "ACKNOWLEDGEMENT_OVERDUE",
                policy.acknowledgement_target_minutes,
                incident.acknowledged_at,
            ),
            ("RESPONSE_OVERDUE", policy.response_start_target_minutes, incident.responding_at),
        )
        for kind, minutes, completed in checks:
            if (
                minutes is not None
                and completed is None
                and now >= incident.reported_at + __import__("datetime").timedelta(minutes=minutes)
            ):
                _, made = IncidentException.objects.get_or_create(
                    incident=incident,
                    exception_type=kind,
                    resolved_at__isnull=True,
                    defaults={"detected_at": now, "details": kind.replace("_", " ").title()},
                )
                created += int(made)
    return created
