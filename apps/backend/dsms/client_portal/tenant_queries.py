"""Fail-closed tenant-consistency predicates for client portal resources."""

from django.db.models import F, Q, QuerySet
from django.utils import timezone

from .models import ClientPortalMembership, ClientServiceReport, ClientServiceRequest


def consistent_memberships(
    queryset: QuerySet[ClientPortalMembership],
) -> QuerySet[ClientPortalMembership]:
    return queryset.filter(
        client__company__is_active=True,
        role__is_active=True,
    ).filter(Q(client_contact__isnull=True) | Q(client_contact__client_id=F("client_id")))


def active_memberships(
    queryset: QuerySet[ClientPortalMembership],
) -> QuerySet[ClientPortalMembership]:
    now = timezone.now()
    return (
        consistent_memberships(queryset)
        .filter(status="ACTIVE")
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
    )


def consistent_reports(
    queryset: QuerySet[ClientServiceReport],
) -> QuerySet[ClientServiceReport]:
    return (
        queryset.filter(
            company__is_active=True,
            client__company_id=F("company_id"),
        )
        .filter(
            Q(contract__isnull=True)
            | Q(
                contract__company_id=F("company_id"),
                contract__client_id=F("client_id"),
            )
        )
        .filter(
            Q(supersedes__isnull=True)
            | Q(
                supersedes__company_id=F("company_id"),
                supersedes__client_id=F("client_id"),
            )
        )
    )


def consistent_service_requests(
    queryset: QuerySet[ClientServiceRequest],
) -> QuerySet[ClientServiceRequest]:
    return (
        queryset.filter(
            client__company__is_active=True,
            created_by_membership__client_id=F("client_id"),
        )
        .filter(
            Q(contract__isnull=True)
            | Q(
                contract__company_id=F("client__company_id"),
                contract__client_id=F("client_id"),
            )
        )
        .filter(
            Q(site__isnull=True)
            | Q(
                site__company_id=F("client__company_id"),
                site__client_id=F("client_id"),
            )
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(
                linked_incident__company_id=F("client__company_id"),
                linked_incident__client_id=F("client_id"),
            )
        )
    )
