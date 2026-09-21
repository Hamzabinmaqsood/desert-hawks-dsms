"""Read-side queries for the identity/RBAC module."""

from typing import Any
from uuid import UUID

from django.contrib.auth.models import Permission
from django.db.models import Q, QuerySet
from django.utils import timezone

from . import access
from .models import Role, User, UserRoleAssignment


def get_users(
    *,
    is_active: bool | None = None,
    is_staff: bool | None = None,
) -> QuerySet[User]:
    queryset = User.objects.all()
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    if is_staff is not None:
        queryset = queryset.filter(is_staff=is_staff)
    return queryset


def get_roles(
    *,
    company_id: UUID | None = None,
    is_system: bool | None = None,
    is_active: bool | None = None,
) -> QuerySet[Role]:
    queryset = Role.objects.select_related("company").prefetch_related("permissions__content_type")
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if is_system is not None:
        queryset = queryset.filter(is_system=is_system)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_role_assignments(
    *,
    user_id: UUID | None = None,
    role_id: UUID | None = None,
    company_id: UUID | None = None,
    scope_type: str | None = None,
    is_active: bool | None = None,
) -> QuerySet[UserRoleAssignment]:
    queryset = UserRoleAssignment.objects.select_related(
        "user",
        "role",
        "company",
        "region",
        "branch",
        "department",
        "operational_zone",
        "created_by",
    )
    if user_id is not None:
        queryset = queryset.filter(user_id=user_id)
    if role_id is not None:
        queryset = queryset.filter(role_id=role_id)
    if company_id is not None:
        queryset = queryset.filter(company_id=company_id)
    if scope_type is not None:
        queryset = queryset.filter(scope_type=scope_type)
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    return queryset


def get_permissions(
    *,
    app_label: str | None = None,
    model: str | None = None,
    search: str | None = None,
) -> QuerySet[Permission]:
    queryset = Permission.objects.select_related("content_type").order_by(
        "content_type__app_label", "content_type__model", "codename"
    )
    if app_label is not None:
        queryset = queryset.filter(content_type__app_label=app_label)
    if model is not None:
        queryset = queryset.filter(content_type__model=model)
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset


def get_access_matrix() -> list[dict[str, Any]]:
    """Every active role with the permission codenames it grants, for admin review."""
    roles = get_roles(is_active=True).order_by("company__code", "code")
    return [
        {
            "role_id": role.id,
            "role_code": role.code,
            "role_name": role.name,
            "company_id": role.company_id,
            "company_code": role.company.code if role.company else None,
            "is_system": role.is_system,
            "permissions": sorted(
                f"{perm.content_type.app_label}.{perm.codename}" for perm in role.permissions.all()
            ),
        }
        for role in roles
    ]


def _assignment_scope_q(*, actor: User, permission: str) -> Q:
    """Assignment rows whose concrete scope is covered by ``actor``."""
    if actor.is_superuser or access.has_permission(user=actor, permission=permission):
        return Q()
    return (
        Q(
            scope_type="COMPANY",
            company_id__in=access.get_fully_accessible_company_ids(actor, permission=permission),
        )
        | Q(
            scope_type="REGION",
            region_id__in=access.get_accessible_region_ids(actor, permission=permission),
        )
        | Q(
            scope_type="BRANCH",
            branch_id__in=access.get_accessible_branch_ids(actor, permission=permission),
        )
        | Q(
            scope_type="DEPARTMENT",
            department_id__in=access.get_accessible_department_ids(actor, permission=permission),
        )
        | Q(
            scope_type="OPERATIONAL_ZONE",
            operational_zone_id__in=access.get_accessible_operational_zone_ids(
                actor, permission=permission
            ),
        )
    )


def get_accessible_role_assignments(
    *, actor: User, permission: str
) -> QuerySet[UserRoleAssignment]:
    queryset = get_role_assignments()
    if actor.is_superuser:
        return queryset
    return queryset.filter(_assignment_scope_q(actor=actor, permission=permission)).filter(
        Q(scope_type="GLOBAL") | Q(company__is_active=True)
    )


def get_accessible_users(*, actor: User, permission: str) -> QuerySet[User]:
    if actor.is_superuser or access.has_permission(user=actor, permission=permission):
        return get_users()
    now = timezone.now()
    assignments = (
        UserRoleAssignment.objects.filter(
            _assignment_scope_q(actor=actor, permission=permission),
            is_active=True,
            role__is_active=True,
        )
        .filter(Q(scope_type="GLOBAL") | Q(company__is_active=True))
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    )
    return get_users().filter(role_assignments__in=assignments).distinct()


def get_accessible_roles(*, actor: User, permission: str) -> QuerySet[Role]:
    queryset = get_roles()
    if actor.is_superuser:
        return queryset
    company_ids = access.get_fully_accessible_company_ids(actor, permission=permission)
    return queryset.filter(Q(company__isnull=True) | Q(company_id__in=company_ids)).filter(
        Q(company__isnull=True) | Q(company__is_active=True)
    )


def get_accessible_access_matrix(*, actor: User) -> list[dict[str, Any]]:
    roles = get_accessible_roles(actor=actor, permission="identity.view_access_matrix").filter(
        is_active=True
    )
    return [
        {
            "role_id": role.id,
            "role_code": role.code,
            "role_name": role.name,
            "company_id": role.company_id,
            "company_code": role.company.code if role.company else None,
            "is_system": role.is_system,
            "permissions": sorted(
                f"{perm.content_type.app_label}.{perm.codename}" for perm in role.permissions.all()
            ),
        }
        for role in roles
    ]


def get_current_user_context(user: User | None) -> dict[str, Any]:
    """Effective permissions and access-scope summary for the authenticated user."""
    return {
        "permissions": sorted(access.get_effective_permissions(user)),
        "scope": access.get_access_scope_summary(user),
    }
