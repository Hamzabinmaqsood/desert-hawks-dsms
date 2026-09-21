"""Scope-aware RBAC permission engine.

``has_permission`` and the ``get_accessible_*_ids`` helpers are the single
source of truth for "what can this user do, and where" -- other modules
should filter querysets and gate writes through these functions rather than
re-implementing scope logic per view.

Containment rules (see module docstring examples in the task spec):

- GLOBAL matches everywhere.
- COMPANY matches any check that names that company.
- REGION matches any check that names that region.
- BRANCH matches any check that names that branch.
- DEPARTMENT matches only that exact department (no branch/region inheritance).
- OPERATIONAL_ZONE matches only that exact zone.

Callers achieve hierarchy containment by passing the full known ancestor
chain for the resource being checked (e.g. checking a Branch passes both
``company`` and ``region``), *except* for Department and Designation, which
intentionally do not inherit from branch/region per the scope rules above.
"""

import uuid
from typing import Any

from django.contrib.auth.models import Permission
from django.db.models import Q, QuerySet
from django.utils import timezone

from dsms.organization.models import Branch, Company, Department, OperationalZone, Region

from .enums import AccessScopeType
from .models import Role, User, UserRoleAssignment


def filter_queryset_by_scope(queryset: QuerySet[Any], user: User | None) -> QuerySet[Any]:
    """Conservatively scope operational querysets using their nearest organization relation."""
    if not _is_usable(user):
        return queryset.none()
    if user is not None and user.is_superuser:
        return queryset
    names = {field.name for field in queryset.model._meta.fields}
    branch_ids = get_accessible_branch_ids(user)
    for field_name, lookup in (
        ("branch", "branch_id__in"),
        ("managing_branch", "managing_branch_id__in"),
        ("site", "site__managing_branch_id__in"),
        ("duty_shift", "duty_shift__branch_id__in"),
        ("roster_period", "roster_period__branch_id__in"),
        ("attendance_record", "attendance_record__branch_id__in"),
        ("patrol_task", "patrol_task__branch_id__in"),
        ("incident", "incident__branch_id__in"),
    ):
        if field_name in names:
            return queryset.filter(**{lookup: branch_ids})
    if "company" in names:
        return queryset.filter(company_id__in=get_fully_accessible_company_ids(user))
    return queryset.none()


def _is_usable(user: User | None) -> bool:
    return bool(user and user.is_authenticated and user.is_active)


def get_active_role_assignments(user: User | None) -> QuerySet[UserRoleAssignment]:
    """Active, currently-in-window assignments for ``user``.

    Empty for anonymous/inactive users. Does not special-case superusers --
    callers that need the "superuser bypasses RBAC" rule check that
    separately (as ``has_permission`` and the accessor functions below do).
    """
    if not _is_usable(user):
        return UserRoleAssignment.objects.none()
    now = timezone.now()
    return (
        UserRoleAssignment.objects.filter(user=user, is_active=True, role__is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
        .filter(Q(scope_type=AccessScopeType.GLOBAL) | Q(company__is_active=True))
        .select_related("role", "company", "region", "branch", "department", "operational_zone")
        .prefetch_related("role__permissions__content_type")
    )


def _role_permission_codes(role: Role) -> set[str]:
    return {f"{perm.content_type.app_label}.{perm.codename}" for perm in role.permissions.all()}


def get_effective_permissions(user: User | None) -> set[str]:
    """All permission codes (``app_label.codename``) granted anywhere, ignoring scope."""
    if not _is_usable(user):
        return set()
    if user is not None and user.is_superuser:
        return {
            f"{perm.content_type.app_label}.{perm.codename}"
            for perm in Permission.objects.select_related("content_type")
        }
    codes: set[str] = set()
    for assignment in get_active_role_assignments(user):
        codes |= _role_permission_codes(assignment.role)
    return codes


def _assignment_matches_scope(
    assignment: UserRoleAssignment,
    *,
    company: Company | None,
    region: Region | None,
    branch: Branch | None,
    department: Department | None,
    operational_zone: OperationalZone | None,
) -> bool:
    scope = assignment.scope_type
    if scope == AccessScopeType.GLOBAL:
        return True
    if scope == AccessScopeType.COMPANY:
        return company is not None and assignment.company_id == company.id
    if scope == AccessScopeType.REGION:
        return region is not None and assignment.region_id == region.id
    if scope == AccessScopeType.BRANCH:
        return branch is not None and assignment.branch_id == branch.id
    if scope == AccessScopeType.DEPARTMENT:
        return department is not None and assignment.department_id == department.id
    if scope == AccessScopeType.OPERATIONAL_ZONE:
        return (
            operational_zone is not None and assignment.operational_zone_id == operational_zone.id
        )
    return False


def has_permission(
    *,
    user: User | None,
    permission: str,
    company: Company | None = None,
    region: Region | None = None,
    branch: Branch | None = None,
    department: Department | None = None,
    operational_zone: OperationalZone | None = None,
) -> bool:
    """Whether ``user`` holds ``permission`` at (or covering) the given scope.

    Superusers always return True; inactive/anonymous users always False.
    Passing no scope kwargs checks whether the permission is granted
    *anywhere* (useful for a coarse "can they ever do this" gate).
    """
    if not _is_usable(user):
        return False
    if user is not None and user.is_superuser:
        return True
    target_company = company
    if target_company is None:
        for scoped_object in (region, branch, department, operational_zone):
            if scoped_object is not None:
                target_company = scoped_object.company
                break
    if target_company is not None and not target_company.is_active:
        return False
    for assignment in get_active_role_assignments(user):
        if permission not in _role_permission_codes(assignment.role):
            continue
        if _assignment_matches_scope(
            assignment,
            company=company,
            region=region,
            branch=branch,
            department=department,
            operational_zone=operational_zone,
        ):
            return True
    return False


def _filtered_assignments(user: User | None, *, permission: str | None) -> list[UserRoleAssignment]:
    assignments = list(get_active_role_assignments(user))
    if permission is None:
        return assignments
    return [a for a in assignments if permission in _role_permission_codes(a.role)]


def get_accessible_company_ids(
    user: User | None, *, permission: str | None = None
) -> set[uuid.UUID]:
    if not _is_usable(user):
        return set()
    if user is not None and user.is_superuser:
        return set(Company.objects.values_list("id", flat=True))
    ids: set[uuid.UUID] = set()
    for assignment in _filtered_assignments(user, permission=permission):
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return set(Company.objects.filter(is_active=True).values_list("id", flat=True))
        if assignment.company_id:
            ids.add(assignment.company_id)
    return set(Company.objects.filter(id__in=ids, is_active=True).values_list("id", flat=True))


def get_fully_accessible_company_ids(
    user: User | None, *, permission: str | None = None
) -> set[uuid.UUID]:
    """Companies where the user holds GLOBAL or COMPANY-level access.

    Stricter than :func:`get_accessible_company_ids`, which also includes
    companies merely *visible* through a narrower (region/branch/...)
    assignment. Used for resources with no dedicated scope type of their
    own (e.g. City, Designation) that should only inherit from a true
    company-wide (or broader) grant.
    """
    if not _is_usable(user):
        return set()
    if user is not None and user.is_superuser:
        return set(Company.objects.values_list("id", flat=True))
    ids: set[uuid.UUID] = set()
    for assignment in _filtered_assignments(user, permission=permission):
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return set(Company.objects.filter(is_active=True).values_list("id", flat=True))
        if assignment.scope_type == AccessScopeType.COMPANY and assignment.company_id:
            ids.add(assignment.company_id)
    return set(Company.objects.filter(id__in=ids, is_active=True).values_list("id", flat=True))


def get_accessible_region_ids(
    user: User | None, *, permission: str | None = None
) -> set[uuid.UUID]:
    if not _is_usable(user):
        return set()
    if user is not None and user.is_superuser:
        return set(Region.objects.values_list("id", flat=True))
    ids: set[uuid.UUID] = set()
    company_ids: set[uuid.UUID] = set()
    for assignment in _filtered_assignments(user, permission=permission):
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return set(Region.objects.filter(company__is_active=True).values_list("id", flat=True))
        if assignment.scope_type == AccessScopeType.COMPANY and assignment.company_id:
            company_ids.add(assignment.company_id)
        elif assignment.scope_type == AccessScopeType.REGION and assignment.region_id:
            ids.add(assignment.region_id)
    if company_ids:
        ids |= set(Region.objects.filter(company_id__in=company_ids).values_list("id", flat=True))
    return set(
        Region.objects.filter(id__in=ids, company__is_active=True).values_list("id", flat=True)
    )


def get_accessible_branch_ids(
    user: User | None, *, permission: str | None = None
) -> set[uuid.UUID]:
    if not _is_usable(user):
        return set()
    if user is not None and user.is_superuser:
        return set(Branch.objects.values_list("id", flat=True))
    ids: set[uuid.UUID] = set()
    company_ids: set[uuid.UUID] = set()
    region_ids: set[uuid.UUID] = set()
    for assignment in _filtered_assignments(user, permission=permission):
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return set(Branch.objects.filter(company__is_active=True).values_list("id", flat=True))
        if assignment.scope_type == AccessScopeType.COMPANY and assignment.company_id:
            company_ids.add(assignment.company_id)
        elif assignment.scope_type == AccessScopeType.REGION and assignment.region_id:
            region_ids.add(assignment.region_id)
        elif assignment.scope_type == AccessScopeType.BRANCH and assignment.branch_id:
            ids.add(assignment.branch_id)
    if company_ids:
        ids |= set(Branch.objects.filter(company_id__in=company_ids).values_list("id", flat=True))
    if region_ids:
        ids |= set(Branch.objects.filter(region_id__in=region_ids).values_list("id", flat=True))
    return set(
        Branch.objects.filter(id__in=ids, company__is_active=True).values_list("id", flat=True)
    )


def get_accessible_department_ids(
    user: User | None, *, permission: str | None = None
) -> set[uuid.UUID]:
    if not _is_usable(user):
        return set()
    if user is not None and user.is_superuser:
        return set(Department.objects.values_list("id", flat=True))
    ids: set[uuid.UUID] = set()
    company_ids: set[uuid.UUID] = set()
    for assignment in _filtered_assignments(user, permission=permission):
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return set(
                Department.objects.filter(company__is_active=True).values_list("id", flat=True)
            )
        if assignment.scope_type == AccessScopeType.COMPANY and assignment.company_id:
            company_ids.add(assignment.company_id)
        elif assignment.scope_type == AccessScopeType.DEPARTMENT and assignment.department_id:
            ids.add(assignment.department_id)
    if company_ids:
        ids |= set(
            Department.objects.filter(company_id__in=company_ids).values_list("id", flat=True)
        )
    return set(
        Department.objects.filter(id__in=ids, company__is_active=True).values_list("id", flat=True)
    )


def get_accessible_operational_zone_ids(
    user: User | None, *, permission: str | None = None
) -> set[uuid.UUID]:
    if not _is_usable(user):
        return set()
    if user is not None and user.is_superuser:
        return set(OperationalZone.objects.values_list("id", flat=True))
    ids: set[uuid.UUID] = set()
    company_ids: set[uuid.UUID] = set()
    region_ids: set[uuid.UUID] = set()
    branch_ids: set[uuid.UUID] = set()
    for assignment in _filtered_assignments(user, permission=permission):
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return set(
                OperationalZone.objects.filter(company__is_active=True).values_list("id", flat=True)
            )
        if assignment.scope_type == AccessScopeType.COMPANY and assignment.company_id:
            company_ids.add(assignment.company_id)
        elif assignment.scope_type == AccessScopeType.REGION and assignment.region_id:
            region_ids.add(assignment.region_id)
        elif assignment.scope_type == AccessScopeType.BRANCH and assignment.branch_id:
            branch_ids.add(assignment.branch_id)
        elif (
            assignment.scope_type == AccessScopeType.OPERATIONAL_ZONE
            and assignment.operational_zone_id
        ):
            ids.add(assignment.operational_zone_id)
    if company_ids:
        ids |= set(
            OperationalZone.objects.filter(company_id__in=company_ids).values_list("id", flat=True)
        )
    if region_ids:
        ids |= set(
            OperationalZone.objects.filter(branch__region_id__in=region_ids).values_list(
                "id", flat=True
            )
        )
    if branch_ids:
        ids |= set(
            OperationalZone.objects.filter(branch_id__in=branch_ids).values_list("id", flat=True)
        )
    return set(
        OperationalZone.objects.filter(id__in=ids, company__is_active=True).values_list(
            "id", flat=True
        )
    )


def get_access_scope_summary(user: User | None) -> dict[str, Any]:
    """A serializable snapshot of what ``user`` can generally reach, for the /me endpoints."""
    if not _is_usable(user):
        return {
            "is_superuser": False,
            "accessible_company_ids": [],
            "accessible_region_ids": [],
            "accessible_branch_ids": [],
            "accessible_department_ids": [],
            "accessible_operational_zone_ids": [],
            "assignments": [],
        }
    assert user is not None
    assignments = list(get_active_role_assignments(user))
    return {
        "is_superuser": user.is_superuser,
        "accessible_company_ids": sorted(get_accessible_company_ids(user), key=str),
        "accessible_region_ids": sorted(get_accessible_region_ids(user), key=str),
        "accessible_branch_ids": sorted(get_accessible_branch_ids(user), key=str),
        "accessible_department_ids": sorted(get_accessible_department_ids(user), key=str),
        "accessible_operational_zone_ids": sorted(
            get_accessible_operational_zone_ids(user), key=str
        ),
        "assignments": [
            {
                "id": assignment.id,
                "role_code": assignment.role.code,
                "role_name": assignment.role.name,
                "scope_type": assignment.scope_type,
                "company_id": assignment.company_id,
                "region_id": assignment.region_id,
                "branch_id": assignment.branch_id,
                "department_id": assignment.department_id,
                "operational_zone_id": assignment.operational_zone_id,
            }
            for assignment in assignments
        ],
    }
