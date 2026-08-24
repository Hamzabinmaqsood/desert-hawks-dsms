"""Read-side queries for the organization module.

Selectors return querysets (list endpoints) or plain nested data structures
(the hierarchy endpoint) and are responsible for avoiding N+1 queries via
``select_related``/``prefetch_related``.
"""

from collections import defaultdict
from typing import Any
from uuid import UUID

from django.db.models import Prefetch, QuerySet

from dsms.identity import access as identity_access
from dsms.identity.models import User

from .models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
    Region,
)


def get_companies(*, is_active: bool | None = None) -> QuerySet[Company]:
    queryset = Company.objects.all()
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_regions(
    *,
    company_id: UUID | None = None,
    is_active: bool | None = None,
) -> QuerySet[Region]:
    queryset = Region.objects.select_related("company")
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_cities(
    *,
    company_id: UUID | None = None,
    region_id: UUID | None = None,
    is_active: bool | None = None,
) -> QuerySet[City]:
    queryset = City.objects.select_related("company", "region")
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if region_id is not None:
        queryset = queryset.filter(region_id=region_id)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_branches(
    *,
    company_id: UUID | None = None,
    region_id: UUID | None = None,
    city_id: UUID | None = None,
    is_active: bool | None = None,
) -> QuerySet[Branch]:
    queryset = Branch.objects.select_related("company", "region", "city")
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if region_id is not None:
        queryset = queryset.filter(region_id=region_id)
    if city_id is not None:
        queryset = queryset.filter(city_id=city_id)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_departments(
    *,
    company_id: UUID | None = None,
    parent_id: UUID | None = None,
    branch_id: UUID | None = None,
    scope: str | None = None,
    is_active: bool | None = None,
) -> QuerySet[Department]:
    queryset = Department.objects.select_related("company", "parent", "branch")
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if parent_id is not None:
        queryset = queryset.filter(parent_id=parent_id)
    if branch_id is not None:
        queryset = queryset.filter(branch_id=branch_id)
    if scope is not None:
        queryset = queryset.filter(scope=scope)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_designations(
    *,
    company_id: UUID | None = None,
    department_id: UUID | None = None,
    is_active: bool | None = None,
) -> QuerySet[Designation]:
    queryset = Designation.objects.select_related("company", "department")
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if department_id is not None:
        queryset = queryset.filter(department_id=department_id)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_operational_zones(
    *,
    company_id: UUID | None = None,
    branch_id: UUID | None = None,
    is_active: bool | None = None,
) -> QuerySet[OperationalZone]:
    queryset = OperationalZone.objects.select_related("company", "branch")
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if branch_id is not None:
        queryset = queryset.filter(branch_id=branch_id)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


# --------------------------------------------------------------------------
# Scope-filtered querysets (RBAC-aware)
# --------------------------------------------------------------------------
#
# These wrap the base selectors above with an ``id__in``/``field__in`` filter
# derived from the caller's RBAC access scope (see dsms.identity.access).
# City and Designation have no dedicated AccessScopeType of their own, so
# they inherit from their region/company respectively.


def get_accessible_companies(
    user: User | None, *, permission: str | None = None
) -> QuerySet[Company]:
    ids = identity_access.get_accessible_company_ids(user, permission=permission)
    return get_companies().filter(id__in=ids)


def get_accessible_regions(user: User | None, *, permission: str | None = None) -> QuerySet[Region]:
    ids = identity_access.get_accessible_region_ids(user, permission=permission)
    return get_regions().filter(id__in=ids)


def get_accessible_cities(user: User | None, *, permission: str | None = None) -> QuerySet[City]:
    region_ids = identity_access.get_accessible_region_ids(user, permission=permission)
    return get_cities().filter(region_id__in=region_ids)


def get_accessible_branches(
    user: User | None, *, permission: str | None = None
) -> QuerySet[Branch]:
    ids = identity_access.get_accessible_branch_ids(user, permission=permission)
    return get_branches().filter(id__in=ids)


def get_accessible_departments(
    user: User | None, *, permission: str | None = None
) -> QuerySet[Department]:
    ids = identity_access.get_accessible_department_ids(user, permission=permission)
    return get_departments().filter(id__in=ids)


def get_accessible_designations(
    user: User | None, *, permission: str | None = None
) -> QuerySet[Designation]:
    company_ids = identity_access.get_fully_accessible_company_ids(user, permission=permission)
    return get_designations().filter(company_id__in=company_ids)


def get_accessible_operational_zones(
    user: User | None, *, permission: str | None = None
) -> QuerySet[OperationalZone]:
    ids = identity_access.get_accessible_operational_zone_ids(user, permission=permission)
    return get_operational_zones().filter(id__in=ids)


def build_department_hierarchy(*, company_id: UUID) -> list[dict[str, Any]]:
    """Build a nested department tree for a single company in one query."""
    departments = list(
        Department.objects.filter(company_id=company_id)
        .select_related("branch")
        .order_by("sort_order", "code")
    )
    by_parent: dict[Any, list[Department]] = defaultdict(list)
    for department in departments:
        by_parent[department.parent_id].append(department)

    def _node(department: Department) -> dict[str, Any]:
        return {
            "id": department.id,
            "code": department.code,
            "name": department.name,
            "scope": department.scope,
            "sort_order": department.sort_order,
            "is_active": department.is_active,
            "branch_id": department.branch_id,
            "branch_name": department.branch.name if department.branch else None,
            "children": [_node(child) for child in by_parent.get(department.id, [])],
        }

    return [_node(department) for department in by_parent.get(None, [])]


def build_company_hierarchy(*, company: Company) -> dict[str, Any]:
    """Build the full nested organization hierarchy for a single company."""
    regions = list(
        Region.objects.filter(company=company)
        .prefetch_related(
            Prefetch("cities", queryset=City.objects.order_by("code")),
            Prefetch(
                "branches",
                queryset=Branch.objects.order_by("code").prefetch_related(
                    Prefetch("operational_zones", queryset=OperationalZone.objects.order_by("code"))
                ),
            ),
        )
        .order_by("code")
    )
    designations = list(
        Designation.objects.filter(company=company)
        .select_related("department")
        .order_by("sort_order", "code")
    )

    return {
        "id": company.id,
        "code": company.code,
        "legal_name": company.legal_name,
        "is_active": company.is_active,
        "regions": [
            {
                "id": region.id,
                "code": region.code,
                "name": region.name,
                "is_active": region.is_active,
                "cities": [
                    {
                        "id": city.id,
                        "code": city.code,
                        "name": city.name,
                        "is_active": city.is_active,
                    }
                    for city in region.cities.all()
                ],
                "branches": [
                    {
                        "id": branch.id,
                        "code": branch.code,
                        "name": branch.name,
                        "is_head_office": branch.is_head_office,
                        "is_active": branch.is_active,
                        "operational_zones": [
                            {
                                "id": zone.id,
                                "code": zone.code,
                                "name": zone.name,
                                "is_active": zone.is_active,
                            }
                            for zone in branch.operational_zones.all()
                        ],
                    }
                    for branch in region.branches.all()
                ],
            }
            for region in regions
        ],
        "departments": build_department_hierarchy(company_id=company.id),
        "designations": [
            {
                "id": designation.id,
                "code": designation.code,
                "name": designation.name,
                "level": designation.level,
                "is_supervisory": designation.is_supervisory,
                "is_active": designation.is_active,
                "department_id": designation.department_id,
                "department_name": (
                    designation.department.name if designation.department else None
                ),
            }
            for designation in designations
        ],
    }


def get_organization_hierarchy(*, company_id: UUID | None = None) -> list[dict[str, Any]]:
    queryset = Company.objects.all().order_by("code")
    if company_id is not None:
        queryset = queryset.filter(id=company_id)
    return [build_company_hierarchy(company=company) for company in queryset]
