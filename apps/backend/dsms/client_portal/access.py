# mypy: disable-error-code="no-untyped-def"
from django.db import models
from django.http import Http404
from django.utils import timezone

from .models import ClientPortalMembership


def resolve_membership(*, user, client_id, permission=None):
    now = timezone.now()
    membership = (
        ClientPortalMembership.objects.select_related("client", "role")
        .prefetch_related("role__permissions", "site_access", "contract_access")
        .filter(user=user, client_id=client_id, status="ACTIVE", role__is_active=True)
        .filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
        .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))
        .first()
    )
    if not membership:
        raise Http404
    if permission and not membership.role.permissions.filter(codename=permission).exists():
        raise Http404
    return membership


def restrict_sites(queryset, membership):
    queryset = queryset.filter(client=membership.client)
    if membership.access_mode == "SELECTED_SITES":
        queryset = queryset.filter(
            id__in=membership.site_access.filter(is_active=True).values("site_id")
        )
    return queryset


def can_access_site(membership, site):
    return site.client_id == membership.client_id and (
        membership.access_mode == "ALL_CLIENT_SITES"
        or membership.site_access.filter(site=site, is_active=True).exists()
    )


def can_access_contract(membership, contract):
    if contract.client_id != membership.client_id:
        return False
    restrictions = membership.contract_access.filter(is_active=True)
    return not restrictions.exists() or restrictions.filter(contract=contract).exists()
