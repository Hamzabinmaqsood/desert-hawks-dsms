"""Business transactions for the identity/RBAC module.

Services own create/update/activate/deactivate workflows: they enforce
cross-entity business rules and translate model/database failures into the
domain exceptions defined in :mod:`dsms.identity.exceptions`. Security-
sensitive operations (role management, role assignment) receive an explicit
``actor`` so authorization decisions and future audit trails have a clear
subject.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password as django_validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction

from dsms.audit.models import AuditCategory
from dsms.audit.services import record_audit_event
from dsms.organization.models import Branch, Company, Department, OperationalZone, Region

from . import access
from .enums import AccessScopeType
from .exceptions import (
    DuplicateAssignmentError,
    IdentityError,
    IdentityValidationError,
    InactiveRelatedRecordError,
    ScopeAuthorizationError,
    SelfDeactivationError,
    SuperuserProtectionError,
    SystemRoleProtectedError,
)
from .models import Role, User, UserRoleAssignment


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _validate_password_policy(password: str, *, user: User | None = None) -> None:
    try:
        django_validate_password(password, user=user)
    except DjangoValidationError as exc:
        raise IdentityValidationError({"password": list(exc.messages)}) from exc


def _save(instance: models.Model) -> None:
    try:
        instance.full_clean()
        instance.save()
    except DjangoValidationError as exc:
        errors = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        raise IdentityValidationError(errors) from exc
    except IntegrityError as exc:
        raise IdentityValidationError(str(exc)) from exc


def _apply_fields(instance: models.Model, fields: dict[str, Any]) -> None:
    for name, value in fields.items():
        setattr(instance, name, value)


# --------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------


def create_user(
    *,
    email: str,
    password: str | None = None,
    first_name: str = "",
    last_name: str = "",
    is_staff: bool = False,
    is_active: bool = True,
) -> User:
    normalized_email = _normalize_email(email)
    if User.objects.filter(email__iexact=normalized_email).exists():
        raise IdentityValidationError({"email": ["A user with this email already exists."]})
    if password is not None:
        _validate_password_policy(password)
    with transaction.atomic():
        user = User.objects.create_user(
            email=normalized_email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            is_staff=is_staff,
            is_active=is_active,
        )
    return user


def update_user(*, user: User, **fields: Any) -> User:
    if "is_superuser" in fields:
        raise IdentityValidationError(
            {"is_superuser": ["This field cannot be modified through this API."]}
        )
    if "password" in fields:
        raise IdentityValidationError({"password": ["Use set_user_password to change a password."]})
    if "email" in fields:
        normalized_email = _normalize_email(fields["email"])
        if User.objects.filter(email__iexact=normalized_email).exclude(pk=user.pk).exists():
            raise IdentityValidationError({"email": ["A user with this email already exists."]})
        fields["email"] = normalized_email
    with transaction.atomic():
        _apply_fields(user, fields)
        _save(user)
    return user


def activate_user(*, user: User, actor: User | None = None) -> User:
    with transaction.atomic():
        user.is_active = True
        _save(user)
        record_audit_event(
            action="USER_ACTIVATED",
            category=AuditCategory.IDENTITY,
            summary="User account activated.",
            actor_user=actor,
            source_object=user,
        )
    return user


def deactivate_user(*, user: User, actor: User) -> User:
    if actor.pk == user.pk:
        raise SelfDeactivationError("You cannot deactivate your own account.")
    if user.is_superuser and not actor.is_superuser:
        raise SuperuserProtectionError("Only a superuser can deactivate a superuser account.")
    with transaction.atomic():
        user.is_active = False
        _save(user)
        record_audit_event(
            action="USER_DEACTIVATED",
            category=AuditCategory.IDENTITY,
            summary="User account deactivated.",
            actor_user=actor,
            source_object=user,
        )
    return user


def set_user_password(*, user: User, password: str, actor: User | None = None) -> User:
    _validate_password_policy(password, user=user)
    with transaction.atomic():
        user.set_password(password)
        user.save(update_fields=["password"])
        record_audit_event(
            action="USER_PASSWORD_CHANGED",
            category=AuditCategory.IDENTITY,
            severity="HIGH",
            summary="User password changed.",
            actor_user=actor or user,
            source_object=user,
        )
    return user


# --------------------------------------------------------------------------
# Role
# --------------------------------------------------------------------------


def create_role(
    *,
    code: str,
    name: str,
    company: Company | None = None,
    description: str = "",
    is_system: bool = False,
    is_active: bool = True,
) -> Role:
    if company is not None and not company.is_active:
        raise InactiveRelatedRecordError("Cannot create a role under an inactive company.")
    with transaction.atomic():
        role = Role(
            company=company,
            code=code,
            name=name,
            description=description,
            is_system=is_system,
            is_active=is_active,
        )
        _save(role)
    return role


def _guard_role_mutable(*, role: Role, actor: User) -> None:
    if role.is_system and not actor.is_superuser:
        raise SystemRoleProtectedError("System roles can only be modified by superusers.")


def update_role(*, role: Role, actor: User, **fields: Any) -> Role:
    _guard_role_mutable(role=role, actor=actor)
    if "is_system" in fields and not actor.is_superuser:
        raise SystemRoleProtectedError("Only superusers may change a role's system status.")
    with transaction.atomic():
        _apply_fields(role, fields)
        _save(role)
    return role


def activate_role(*, role: Role, actor: User) -> Role:
    _guard_role_mutable(role=role, actor=actor)
    with transaction.atomic():
        role.is_active = True
        _save(role)
    return role


def deactivate_role(*, role: Role, actor: User) -> Role:
    _guard_role_mutable(role=role, actor=actor)
    with transaction.atomic():
        role.is_active = False
        _save(role)
    return role


def set_role_permissions(*, role: Role, actor: User, permissions: Iterable[Permission]) -> Role:
    _guard_role_mutable(role=role, actor=actor)
    with transaction.atomic():
        role.permissions.set(permissions)
    return role


# --------------------------------------------------------------------------
# Role assignment
# --------------------------------------------------------------------------


def _guard_actor_scope_covers(
    *,
    actor: User,
    company: Company | None,
    region: Region | None,
    branch: Branch | None,
    department: Department | None,
    operational_zone: OperationalZone | None,
) -> None:
    """Ensure ``actor`` can grant access at the given scope.

    A ``UserRoleAssignment`` only stores the single scope field matching its
    ``scope_type`` (e.g. a BRANCH-scoped row has ``region=None``), but a
    REGION-scoped administrator should still be able to grant BRANCH-scoped
    assignments for branches inside their region. We therefore fill in the
    implied ancestor chain from whichever concrete target was given before
    checking the actor's own reach.
    """
    if actor.is_superuser:
        return
    if branch is not None and region is None:
        region = branch.region
    if operational_zone is not None:
        branch = branch or operational_zone.branch
        region = region or operational_zone.branch.region
    if access.has_permission(
        user=actor,
        permission="identity.assign_roles",
        company=company,
        region=region,
        branch=branch,
        department=department,
        operational_zone=operational_zone,
    ):
        return
    raise ScopeAuthorizationError("You are not permitted to grant access at the requested scope.")


def _guard_no_duplicate_assignment(
    *,
    user: User,
    role: Role,
    scope_type: str,
    company: Company | None,
    region: Region | None,
    branch: Branch | None,
    department: Department | None,
    operational_zone: OperationalZone | None,
    exclude_pk: Any = None,
) -> None:
    queryset = UserRoleAssignment.objects.filter(
        user=user,
        role=role,
        scope_type=scope_type,
        is_active=True,
        company=company,
        region=region,
        branch=branch,
        department=department,
        operational_zone=operational_zone,
    )
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if queryset.exists():
        raise DuplicateAssignmentError("An equivalent active role assignment already exists.")


def assign_role(
    *,
    actor: User,
    user: User,
    role: Role,
    scope_type: str,
    company: Company | None = None,
    region: Region | None = None,
    branch: Branch | None = None,
    department: Department | None = None,
    operational_zone: OperationalZone | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    is_active: bool = True,
) -> UserRoleAssignment:
    if not role.is_active:
        raise InactiveRelatedRecordError("Cannot assign an inactive role.")
    if not user.is_active:
        raise InactiveRelatedRecordError("Cannot assign a role to an inactive user.")
    if company is not None and not company.is_active:
        raise InactiveRelatedRecordError("Cannot create an assignment under an inactive company.")
    for label, target in (
        ("region", region),
        ("branch", branch),
        ("department", department),
        ("operational zone", operational_zone),
    ):
        if target is not None and not target.is_active:
            raise InactiveRelatedRecordError(
                f"Cannot create an assignment under an inactive {label}."
            )

    if scope_type == AccessScopeType.GLOBAL and not actor.is_superuser:
        raise ScopeAuthorizationError("Only superusers may create GLOBAL role assignments.")

    _guard_actor_scope_covers(
        actor=actor,
        company=company,
        region=region,
        branch=branch,
        department=department,
        operational_zone=operational_zone,
    )
    _guard_no_duplicate_assignment(
        user=user,
        role=role,
        scope_type=scope_type,
        company=company,
        region=region,
        branch=branch,
        department=department,
        operational_zone=operational_zone,
    )

    with transaction.atomic():
        assignment = UserRoleAssignment(
            user=user,
            role=role,
            scope_type=scope_type,
            company=company,
            region=region,
            branch=branch,
            department=department,
            operational_zone=operational_zone,
            starts_at=starts_at,
            ends_at=ends_at,
            is_active=is_active,
            created_by=actor,
        )
        _save(assignment)
        record_audit_event(
            action="ROLE_ASSIGNED",
            category=AuditCategory.AUTHORIZATION,
            summary="Role assigned to user.",
            actor_user=actor,
            company=company,
            region=region,
            branch=branch,
            source_object=assignment,
            metadata_safe={"role_code": role.code, "scope_type": scope_type},
        )
    return assignment


def update_role_assignment(
    *, assignment: UserRoleAssignment, actor: User, **fields: Any
) -> UserRoleAssignment:
    _apply_fields(assignment, fields)
    _guard_actor_scope_covers(
        actor=actor,
        company=assignment.company,
        region=assignment.region,
        branch=assignment.branch,
        department=assignment.department,
        operational_zone=assignment.operational_zone,
    )
    if assignment.scope_type == AccessScopeType.GLOBAL and not actor.is_superuser:
        raise ScopeAuthorizationError("Only superusers may manage GLOBAL role assignments.")
    _guard_no_duplicate_assignment(
        user=assignment.user,
        role=assignment.role,
        scope_type=assignment.scope_type,
        company=assignment.company,
        region=assignment.region,
        branch=assignment.branch,
        department=assignment.department,
        operational_zone=assignment.operational_zone,
        exclude_pk=assignment.pk,
    )
    with transaction.atomic():
        _save(assignment)
    return assignment


def activate_role_assignment(*, assignment: UserRoleAssignment, actor: User) -> UserRoleAssignment:
    if assignment.scope_type == AccessScopeType.GLOBAL and not actor.is_superuser:
        raise ScopeAuthorizationError("Only superusers may manage GLOBAL role assignments.")
    _guard_actor_scope_covers(
        actor=actor,
        company=assignment.company,
        region=assignment.region,
        branch=assignment.branch,
        department=assignment.department,
        operational_zone=assignment.operational_zone,
    )
    with transaction.atomic():
        assignment.is_active = True
        _save(assignment)
    return assignment


def deactivate_role_assignment(
    *, assignment: UserRoleAssignment, actor: User
) -> UserRoleAssignment:
    if assignment.scope_type == AccessScopeType.GLOBAL and not actor.is_superuser:
        raise ScopeAuthorizationError("Only superusers may manage GLOBAL role assignments.")
    _guard_actor_scope_covers(
        actor=actor,
        company=assignment.company,
        region=assignment.region,
        branch=assignment.branch,
        department=assignment.department,
        operational_zone=assignment.operational_zone,
    )
    with transaction.atomic():
        assignment.is_active = False
        _save(assignment)
        record_audit_event(
            action="ROLE_REVOKED",
            category=AuditCategory.AUTHORIZATION,
            summary="Role assignment revoked.",
            actor_user=actor,
            company=assignment.company,
            region=assignment.region,
            branch=assignment.branch,
            source_object=assignment,
            metadata_safe={"role_code": assignment.role.code, "scope_type": assignment.scope_type},
        )
    return assignment


__all__ = [
    "IdentityError",
    "activate_role",
    "activate_role_assignment",
    "activate_user",
    "assign_role",
    "create_role",
    "create_user",
    "deactivate_role",
    "deactivate_role_assignment",
    "deactivate_user",
    "set_role_permissions",
    "set_user_password",
    "update_role",
    "update_role_assignment",
    "update_user",
]
