from __future__ import annotations

from django.db.models import F, Q, QuerySet
from django.utils import timezone

from dsms.client_portal.models import ClientPortalMembership
from dsms.deployment.tenant_queries import consistent_employees
from dsms.identity import access
from dsms.identity.models import User
from dsms.workforce.models import Employee

from .models import Notification, NotificationRecipient


def user_company_ids(user: User) -> set[object]:
    ids: set[object] = set(access.get_accessible_company_ids(user))
    ids.update(
        consistent_employees(
            Employee.objects.filter(user=user, employment_status="ACTIVE")
        ).values_list("company_id", flat=True)
    )
    now = timezone.now()
    ids.update(
        ClientPortalMembership.objects.filter(
            user=user,
            status="ACTIVE",
            client__company__is_active=True,
        )
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .values_list("client__company_id", flat=True)
    )
    return ids


def user_belongs_to_company(user: User, company: object | None) -> bool:
    if company is None:
        return True
    return bool(
        user.is_active
        and (user.is_superuser or getattr(company, "id", None) in user_company_ids(user))
    )


def consistent_notifications(queryset: QuerySet[Notification]) -> QuerySet[Notification]:
    return queryset.filter(
        Q(company__isnull=True) | Q(company__is_active=True),
        Q(event__isnull=True)
        | Q(event__company_id=F("company_id"))
        | Q(event__company__isnull=True, company__isnull=True),
        Q(rule__isnull=True) | Q(rule__company__isnull=True) | Q(rule__company_id=F("company_id")),
        Q(template_version__isnull=True)
        | Q(template_version__template__company__isnull=True)
        | Q(template_version__template__company_id=F("company_id")),
    )


def consistent_recipients_for_user(
    queryset: QuerySet[NotificationRecipient], *, user: User
) -> QuerySet[NotificationRecipient]:
    company_ids = user_company_ids(user)
    return (
        queryset.filter(user=user)
        .filter(
            Q(notification__company__isnull=True)
            | Q(
                notification__company_id__in=company_ids,
                notification__company__is_active=True,
            ),
            Q(employee__isnull=True) | Q(employee__company_id=F("notification__company_id")),
            Q(client_portal_membership__isnull=True)
            | Q(client_portal_membership__client__company_id=F("notification__company_id")),
        )
        .filter(notification_id__in=consistent_notifications(Notification.objects.all()))
    )
