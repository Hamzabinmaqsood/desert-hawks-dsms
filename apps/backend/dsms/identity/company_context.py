"""Server-authoritative selected Company context.

The selected Company is user-interface context only.  Resource querysets,
permissions, and resulting-state validation remain the authorization boundary.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db.models import QuerySet
from django.http import Http404

from dsms.organization.models import Company

from . import access
from .enums import AccessScopeType
from .models import User, UserRoleAssignment

SELECTED_COMPANY_SESSION_KEY = "selected_company_id"


def _assignment_company_is_consistent(assignment: UserRoleAssignment) -> bool:
    """Reject historically corrupt assignment/organization relationships."""

    if assignment.scope_type == AccessScopeType.GLOBAL:
        return assignment.role.company_id is None
    company_id = assignment.company_id
    if company_id is None:
        return False
    if assignment.role.company_id not in {None, company_id}:
        return False
    if assignment.scope_type == AccessScopeType.COMPANY:
        return True
    if assignment.scope_type == AccessScopeType.REGION:
        return bool(assignment.region and assignment.region.company_id == company_id)
    if assignment.scope_type == AccessScopeType.BRANCH:
        return bool(
            assignment.branch
            and assignment.branch.company_id == company_id
            and assignment.branch.region.company_id == company_id
            and assignment.branch.city.company_id == company_id
            and assignment.branch.city.region_id == assignment.branch.region_id
        )
    if assignment.scope_type == AccessScopeType.DEPARTMENT:
        return bool(assignment.department and assignment.department.company_id == company_id)
    if assignment.scope_type == AccessScopeType.OPERATIONAL_ZONE:
        return bool(
            assignment.operational_zone
            and assignment.operational_zone.company_id == company_id
            and assignment.operational_zone.branch.company_id == company_id
        )
    return False


def get_selectable_companies(user: User) -> QuerySet[Company]:
    """Active Companies available to the user through current, valid RBAC."""

    if not user.is_authenticated or not user.is_active:
        return Company.objects.none()
    if user.is_superuser:
        # Platform administrators use the ordinary tenant UX only for active
        # Companies.  Inactive-tenant support/impersonation is intentionally
        # outside SaaS-2A.
        return Company.objects.filter(is_active=True).order_by("code")

    assignments = access.get_active_role_assignments(user).select_related(
        "role__company",
        "region",
        "branch__region",
        "branch__city",
        "department",
        "operational_zone__branch",
    )
    company_ids: set[UUID] = set()
    has_global_access = False
    for assignment in assignments:
        if not _assignment_company_is_consistent(assignment):
            continue
        if assignment.scope_type == AccessScopeType.GLOBAL:
            has_global_access = True
            break
        if assignment.company_id is not None:
            company_ids.add(assignment.company_id)
    if has_global_access:
        return Company.objects.filter(is_active=True).order_by("code")
    return Company.objects.filter(id__in=company_ids, is_active=True).order_by("code")


def clear_selected_company(request: Any) -> None:
    if SELECTED_COMPANY_SESSION_KEY in request.session:
        del request.session[SELECTED_COMPANY_SESSION_KEY]


def get_selected_company(request: Any) -> Company | None:
    """Resolve and revalidate the selected Company, clearing stale context."""

    raw_company_id = request.session.get(SELECTED_COMPANY_SESSION_KEY)
    if not raw_company_id:
        return None
    try:
        company_id = UUID(str(raw_company_id))
    except (TypeError, ValueError):
        clear_selected_company(request)
        return None
    company = get_selectable_companies(request.user).filter(pk=company_id).first()
    if company is None:
        clear_selected_company(request)
    return company


def select_company(request: Any, company_id: UUID) -> Company:
    """Select an active, currently accessible Company without enumeration."""

    company = get_selectable_companies(request.user).filter(pk=company_id).first()
    if company is None:
        raise Http404
    request.session[SELECTED_COMPANY_SESSION_KEY] = str(company.id)
    return company


def build_company_context(request: Any) -> dict[str, Any]:
    companies = list(get_selectable_companies(request.user))
    selected_company = get_selected_company(request)
    if selected_company is None and len(companies) == 1:
        selected_company = select_company(request, companies[0].id)
    return {
        "user": request.user,
        "companies": companies,
        "selected_company": selected_company,
        "selection_required": bool(companies) and selected_company is None,
    }
