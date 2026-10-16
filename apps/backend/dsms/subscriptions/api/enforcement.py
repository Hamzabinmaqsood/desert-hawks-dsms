from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, cast

from django.db import models
from django.http import Http404
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from dsms.identity.company_context import get_selectable_companies, get_selected_company
from dsms.identity.models import User
from dsms.organization.models import Company
from dsms.subscriptions.models import CompanyModulePolicy, CompanyModulePolicyMode

from ..enforcement import (
    ModuleNotEnabled,
    company_from_resource,
    company_has_module,
    require_company_modules,
)
from ..modules import TENANT_MODULE_REGISTRY


def company_for_resource(value: Any, *, _seen: set[int] | None = None) -> Company | None:
    return company_from_resource(value, _seen=_seen)


def declared_module_ids(view: APIView) -> tuple[str, ...]:
    declared = getattr(view, "required_module_ids", ())
    if isinstance(declared, str):
        declared = (declared,)
    return TENANT_MODULE_REGISTRY.ordered_ids(declared)


def _request_companies(request: Request) -> list[Company]:
    selected = get_selected_company(request)
    if selected is not None:
        return [selected]
    return list(get_selectable_companies(cast(User, request.user)))


def _all_legacy_compatible(companies: Iterable[Company]) -> bool:
    """Preserve pre-entitlement multi-Company behavior only for LEGACY_FULL tenants."""

    company_ids = tuple(company.pk for company in companies)
    return not CompanyModulePolicy.objects.filter(
        company_id__in=company_ids,
        mode=CompanyModulePolicyMode.SUBSCRIPTION,
    ).exists()


class HasTenantModules(BasePermission):
    """Coarse request gate; queryset/object/service checks remain authoritative."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        required = declared_module_ids(view)
        if not required or getattr(view, "swagger_fake_view", False):
            return True
        # Let the existing scoped queryset resolve detail/action resources first.
        # This preserves the repository's foreign-resource 404 contract; the
        # owning Company's modules are then checked by has_object_permission.
        if getattr(view, "detail", False):
            return True
        companies = _request_companies(request)
        if not companies:
            return True
        if len(companies) == 1:
            require_company_modules(companies[0], required, request=request)
            return True
        if _all_legacy_compatible(companies):
            cast(Any, request)._tenant_module_legacy_multi_company = True
            return True
        raise PermissionDenied("Select a Company before accessing tenant product functionality.")

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        required = declared_module_ids(view)
        company = company_for_resource(obj)
        if required and company is not None:
            require_company_modules(company, required, request=request)
        return True


class TenantModuleViewMixin:
    """Explicit DRF integration for a module-owned routed surface."""

    required_module_ids: tuple[str, ...] = ()
    module_company_lookup = "company_id"
    module_allow_global_rows = False

    def get_permissions(self) -> list[Any]:
        permissions = list(super().get_permissions())  # type: ignore[misc]
        permissions.append(HasTenantModules())
        return permissions

    def get_module_company_lookup(self) -> str:
        return self.module_company_lookup

    def filter_queryset(self, queryset: Any) -> Any:
        queryset = super().filter_queryset(queryset)  # type: ignore[misc]
        required = declared_module_ids(self)  # type: ignore[arg-type]
        lookup = self.get_module_company_lookup()
        if not required or not lookup or getattr(self, "swagger_fake_view", False):
            return queryset
        request = self.request  # type: ignore[attr-defined]
        # Existing resource scope is the authority for detail/action requests.
        # Resolve it before applying selected-Company collection context so an
        # inaccessible foreign resource remains 404 and an accessible resource
        # is checked against its own Company's entitlement in object permission.
        if getattr(self, "detail", False):
            return queryset
        authoritative = _request_companies(request)
        if len(authoritative) == 1:
            selected_scope = models.Q(**{lookup: authoritative[0].pk})
            if self.module_allow_global_rows:
                selected_scope |= models.Q(**{f"{lookup}__isnull": True})
            queryset = queryset.filter(selected_scope)
        if getattr(request, "_tenant_module_legacy_multi_company", False):
            return queryset
        raw_ids = queryset.order_by().values_list(lookup, flat=True).distinct()
        company_ids = {company_id for company_id in raw_ids if company_id is not None}
        companies = Company.objects.filter(pk__in=company_ids, is_active=True)
        allowed = [
            company.pk
            for company in companies
            if all(
                company_has_module(company, module_id, request=request) for module_id in required
            )
        ]
        condition = models.Q(**{f"{lookup}__in": allowed})
        if self.module_allow_global_rows:
            condition |= models.Q(**{f"{lookup}__isnull": True})
        return queryset.filter(condition)

    def require_modules_for(self, value: Any) -> None:
        company = company_for_resource(value)
        if company is not None:
            require_company_modules(
                company,
                declared_module_ids(self),  # type: ignore[arg-type]
                request=self.request,  # type: ignore[attr-defined]
            )


def require_request_company_modules(
    request: Request, company: Company, module_ids: Iterable[str]
) -> None:
    require_company_modules(company, module_ids, request=request)


def entitled_company_ids(
    request: Request,
    company_ids: Iterable[Any] | None,
    module_ids: Iterable[str],
) -> list[Any]:
    """Filter an already-authorized Company set before aggregate/report queries."""

    requested_company_ids = None if company_ids is None else tuple(company_ids)
    required = TENANT_MODULE_REGISTRY.ordered_ids(module_ids)
    authoritative = _request_companies(request)
    if not authoritative:
        return []
    if len(authoritative) > 1 and _all_legacy_compatible(authoritative):
        authoritative_ids = tuple(company.pk for company in authoritative)
        if requested_company_ids is None:
            return list(authoritative_ids)
        requested = {str(company_id) for company_id in requested_company_ids}
        return [company_id for company_id in authoritative_ids if str(company_id) in requested]
    if len(authoritative) != 1:
        raise PermissionDenied("Select a Company before accessing tenant product functionality.")
    company = authoritative[0]
    if requested_company_ids is not None and str(company.pk) not in {
        str(company_id) for company_id in requested_company_ids
    }:
        raise Http404
    companies = Company.objects.filter(pk=company.pk, is_active=True)
    if requested_company_ids is not None:
        companies = companies.filter(pk__in=requested_company_ids)
    allowed = [
        company.pk
        for company in companies
        if all(company_has_module(company, module_id, request=request) for module_id in required)
    ]
    if requested_company_ids and not allowed:
        raise ModuleNotEnabled(required)
    return allowed


def module_api_surface(*module_ids: str) -> Callable[[Any], Any]:
    """Declare a function-based DRF view for route-accountability metadata."""

    required = TENANT_MODULE_REGISTRY.ordered_ids(module_ids)

    def decorate(view: Any) -> Any:
        target = getattr(view, "cls", view)
        target.required_module_ids = required
        return view

    return decorate
