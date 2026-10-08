# mypy: disable-error-code="no-untyped-def"
from django.http import Http404

from dsms.contracts.api.security import consistent_queryset as consistent_contract_queryset

from .models import ClientPortalMembership
from .tenant_queries import active_memberships


def resolve_membership(*, user, client_id, permission=None):
    membership = (
        active_memberships(ClientPortalMembership.objects.all())
        .select_related("client", "role")
        .prefetch_related("role__permissions", "site_access", "contract_access")
        .filter(user=user, client_id=client_id)
        .first()
    )
    if not membership:
        raise Http404
    if permission and not membership.role.permissions.filter(codename=permission).exists():
        raise Http404
    return membership


def restrict_sites(queryset, membership):
    queryset = consistent_contract_queryset(queryset).filter(client=membership.client)
    if membership.access_mode == "SELECTED_SITES":
        queryset = queryset.filter(
            id__in=membership.site_access.filter(is_active=True).values("site_id")
        )
    return queryset


def can_access_site(membership, site):
    return (
        consistent_contract_queryset(type(site).objects.filter(pk=site.pk)).exists()
        and (site.client_id == membership.client_id)
        and (
            membership.access_mode == "ALL_CLIENT_SITES"
            or membership.site_access.filter(site=site, is_active=True).exists()
        )
    )


def can_access_contract(membership, contract):
    if not consistent_contract_queryset(type(contract).objects.filter(pk=contract.pk)).exists():
        return False
    if contract.client_id != membership.client_id:
        return False
    restrictions = membership.contract_access.filter(is_active=True)
    return not restrictions.exists() or restrictions.filter(contract=contract).exists()
