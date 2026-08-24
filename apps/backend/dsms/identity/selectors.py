"""Read-side queries for the identity/RBAC module."""

from typing import Any
from uuid import UUID

from django.contrib.auth.models import Permission
from django.db.models import QuerySet

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


def get_current_user_context(user: User | None) -> dict[str, Any]:
    """Effective permissions and access-scope summary for the authenticated user."""
    return {
        "permissions": sorted(access.get_effective_permissions(user)),
        "scope": access.get_access_scope_summary(user),
    }
