import pytest
from django.contrib.auth.models import Permission

from dsms.identity import services
from dsms.identity.enums import AccessScopeType
from dsms.identity.exceptions import (
    DuplicateAssignmentError,
    IdentityValidationError,
    InactiveRelatedRecordError,
    ScopeAuthorizationError,
    SelfDeactivationError,
    SuperuserProtectionError,
    SystemRoleProtectedError,
)
from dsms.identity.models import Role
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory, RegionFactory

pytestmark = pytest.mark.django_db


def _permission(codename: str, app_label: str = "organization") -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _role_with_permissions(*codenames: str, app_label: str = "identity") -> Role:
    role = RoleFactory.create()
    role.permissions.set([_permission(codename, app_label) for codename in codenames])
    return role


# --------------------------------------------------------------------------
# User services
# --------------------------------------------------------------------------


def test_create_user_succeeds() -> None:
    user = services.create_user(email="New.User@Example.com", password="StrongTestPassword123!")
    assert user.email == "new.user@example.com"
    assert user.check_password("StrongTestPassword123!")


def test_create_user_rejects_duplicate_email() -> None:
    services.create_user(email="dup@example.com", password="StrongTestPassword123!")
    with pytest.raises(IdentityValidationError):
        services.create_user(email="DUP@example.com", password="StrongTestPassword123!")


def test_create_user_enforces_password_policy() -> None:
    with pytest.raises(IdentityValidationError):
        services.create_user(email="weak@example.com", password="12345678")


def test_update_user_changes_fields() -> None:
    user = UserFactory.create()
    updated = services.update_user(user=user, first_name="Updated")
    assert updated.first_name == "Updated"


def test_update_user_rejects_is_superuser() -> None:
    user = UserFactory.create()
    with pytest.raises(IdentityValidationError):
        services.update_user(user=user, is_superuser=True)


def test_update_user_rejects_password_field() -> None:
    user = UserFactory.create()
    with pytest.raises(IdentityValidationError):
        services.update_user(user=user, password="NewStrongPassword123!")


def test_activate_and_deactivate_user() -> None:
    user = UserFactory.create()
    actor = UserFactory.create()
    deactivated = services.deactivate_user(user=user, actor=actor)
    assert deactivated.is_active is False
    activated = services.activate_user(user=deactivated)
    assert activated.is_active is True


def test_user_cannot_deactivate_self() -> None:
    user = UserFactory.create()
    with pytest.raises(SelfDeactivationError):
        services.deactivate_user(user=user, actor=user)


def test_non_superuser_cannot_deactivate_superuser() -> None:
    superuser = UserFactory.create(is_superuser=True)
    actor = UserFactory.create()
    with pytest.raises(SuperuserProtectionError):
        services.deactivate_user(user=superuser, actor=actor)


def test_superuser_can_deactivate_superuser() -> None:
    superuser = UserFactory.create(is_superuser=True)
    actor = UserFactory.create(is_superuser=True)
    deactivated = services.deactivate_user(user=superuser, actor=actor)
    assert deactivated.is_active is False


def test_set_user_password_succeeds() -> None:
    user = UserFactory.create()
    updated = services.set_user_password(user=user, password="AnotherStrongPassword123!")
    assert updated.check_password("AnotherStrongPassword123!")


def test_set_user_password_enforces_policy() -> None:
    user = UserFactory.create()
    with pytest.raises(IdentityValidationError):
        services.set_user_password(user=user, password="password")


# --------------------------------------------------------------------------
# Role services
# --------------------------------------------------------------------------


def test_create_role_succeeds() -> None:
    role = services.create_role(code="custom-role", name="Custom Role")
    assert role.code == "CUSTOM-ROLE"


def test_create_role_rejects_inactive_company() -> None:
    company = CompanyFactory.create(is_active=False)
    with pytest.raises(InactiveRelatedRecordError):
        services.create_role(code="R1", name="Role 1", company=company)


def test_non_superuser_cannot_modify_system_role() -> None:
    role = RoleFactory.create(is_system=True)
    actor = UserFactory.create()
    with pytest.raises(SystemRoleProtectedError):
        services.update_role(role=role, actor=actor, name="Renamed")


def test_superuser_can_modify_system_role() -> None:
    role = RoleFactory.create(is_system=True)
    actor = UserFactory.create(is_superuser=True)
    updated = services.update_role(role=role, actor=actor, name="Renamed")
    assert updated.name == "Renamed"


def test_non_superuser_cannot_deactivate_system_role() -> None:
    role = RoleFactory.create(is_system=True)
    actor = UserFactory.create()
    with pytest.raises(SystemRoleProtectedError):
        services.deactivate_role(role=role, actor=actor)


def test_non_superuser_can_deactivate_custom_role() -> None:
    role = RoleFactory.create(is_system=False)
    actor = UserFactory.create()
    deactivated = services.deactivate_role(role=role, actor=actor)
    assert deactivated.is_active is False


def test_set_role_permissions_blocked_for_system_role() -> None:
    role = RoleFactory.create(is_system=True)
    actor = UserFactory.create()
    with pytest.raises(SystemRoleProtectedError):
        services.set_role_permissions(
            role=role, actor=actor, permissions=[_permission("view_branch")]
        )


def test_set_role_permissions_succeeds_for_custom_role() -> None:
    role = RoleFactory.create()
    actor = UserFactory.create()
    updated = services.set_role_permissions(
        role=role, actor=actor, permissions=[_permission("view_branch")]
    )
    assert updated.permissions.filter(codename="view_branch").exists()


# --------------------------------------------------------------------------
# Role assignment services -- role management security / scope limiting
# --------------------------------------------------------------------------


def test_superuser_can_bootstrap_global_assignment() -> None:
    superuser = UserFactory.create(is_superuser=True)
    target_user = UserFactory.create()
    role = RoleFactory.create()
    assignment = services.assign_role(
        actor=superuser, user=target_user, role=role, scope_type=AccessScopeType.GLOBAL
    )
    assert assignment.scope_type == AccessScopeType.GLOBAL
    assert assignment.created_by_id == superuser.id


def test_non_superuser_cannot_create_global_assignment() -> None:
    actor = UserFactory.create()
    role_a = _role_with_permissions("assign_roles")
    UserRoleAssignmentFactory.create(user=actor, role=role_a, scope_type=AccessScopeType.GLOBAL)
    target_user = UserFactory.create()
    role = RoleFactory.create()
    with pytest.raises(ScopeAuthorizationError):
        services.assign_role(
            actor=actor, user=target_user, role=role, scope_type=AccessScopeType.GLOBAL
        )


def test_actor_without_assign_roles_permission_is_denied() -> None:
    actor = UserFactory.create()
    target_user = UserFactory.create()
    role = RoleFactory.create()
    company = CompanyFactory.create()
    with pytest.raises(ScopeAuthorizationError):
        services.assign_role(
            actor=actor,
            user=target_user,
            role=role,
            scope_type=AccessScopeType.COMPANY,
            company=company,
        )


def test_branch_scoped_administrator_cannot_assign_company_wide_role() -> None:
    branch = BranchFactory.create()
    assign_roles_role = _role_with_permissions("assign_roles")
    actor = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=actor,
        role=assign_roles_role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    target_user = UserFactory.create()
    granted_role = RoleFactory.create()
    with pytest.raises(ScopeAuthorizationError):
        services.assign_role(
            actor=actor,
            user=target_user,
            role=granted_role,
            scope_type=AccessScopeType.COMPANY,
            company=branch.company,
        )


def test_branch_scoped_administrator_can_assign_role_within_own_branch() -> None:
    branch = BranchFactory.create()
    assign_roles_role = _role_with_permissions("assign_roles")
    actor = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=actor,
        role=assign_roles_role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    target_user = UserFactory.create()
    granted_role = RoleFactory.create()
    assignment = services.assign_role(
        actor=actor,
        user=target_user,
        role=granted_role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    assert assignment.branch_id == branch.id


def test_company_scoped_administrator_cannot_assign_in_a_different_company() -> None:
    company = CompanyFactory.create()
    other_company = CompanyFactory.create()
    assign_roles_role = _role_with_permissions("assign_roles")
    actor = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=actor, role=assign_roles_role, scope_type=AccessScopeType.COMPANY, company=company
    )
    target_user = UserFactory.create()
    granted_role = RoleFactory.create()
    with pytest.raises(ScopeAuthorizationError):
        services.assign_role(
            actor=actor,
            user=target_user,
            role=granted_role,
            scope_type=AccessScopeType.COMPANY,
            company=other_company,
        )


def test_assign_role_rejects_inactive_role() -> None:
    superuser = UserFactory.create(is_superuser=True)
    target_user = UserFactory.create()
    role = RoleFactory.create(is_active=False)
    with pytest.raises(InactiveRelatedRecordError):
        services.assign_role(
            actor=superuser, user=target_user, role=role, scope_type=AccessScopeType.GLOBAL
        )


def test_assign_role_rejects_inactive_user() -> None:
    superuser = UserFactory.create(is_superuser=True)
    target_user = UserFactory.create(is_active=False)
    role = RoleFactory.create()
    with pytest.raises(InactiveRelatedRecordError):
        services.assign_role(
            actor=superuser, user=target_user, role=role, scope_type=AccessScopeType.GLOBAL
        )


def test_assign_role_rejects_inactive_company() -> None:
    superuser = UserFactory.create(is_superuser=True)
    target_user = UserFactory.create()
    role = RoleFactory.create()
    company = CompanyFactory.create(is_active=False)
    with pytest.raises(InactiveRelatedRecordError):
        services.assign_role(
            actor=superuser,
            user=target_user,
            role=role,
            scope_type=AccessScopeType.COMPANY,
            company=company,
        )


def test_assign_role_prevents_duplicate_active_assignment() -> None:
    superuser = UserFactory.create(is_superuser=True)
    target_user = UserFactory.create()
    role = RoleFactory.create()
    services.assign_role(
        actor=superuser, user=target_user, role=role, scope_type=AccessScopeType.GLOBAL
    )
    with pytest.raises(DuplicateAssignmentError):
        services.assign_role(
            actor=superuser, user=target_user, role=role, scope_type=AccessScopeType.GLOBAL
        )


def test_assign_role_allows_same_role_at_different_scope() -> None:
    superuser = UserFactory.create(is_superuser=True)
    target_user = UserFactory.create()
    role = RoleFactory.create()
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    services.assign_role(
        actor=superuser,
        user=target_user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company_a,
    )
    second = services.assign_role(
        actor=superuser,
        user=target_user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company_b,
    )
    assert second.company_id == company_b.id


def test_activate_and_deactivate_role_assignment_respect_scope_guard() -> None:
    branch = BranchFactory.create()
    assign_roles_role = _role_with_permissions("assign_roles")
    actor = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=actor,
        role=assign_roles_role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    assignment = UserRoleAssignmentFactory.create(
        role=RoleFactory.create(),
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    deactivated = services.deactivate_role_assignment(assignment=assignment, actor=actor)
    assert deactivated.is_active is False
    activated = services.activate_role_assignment(assignment=deactivated, actor=actor)
    assert activated.is_active is True


def test_deactivate_role_assignment_denied_outside_actor_scope() -> None:
    branch_a = BranchFactory.create()
    branch_b = BranchFactory.create()
    assign_roles_role = _role_with_permissions("assign_roles")
    actor = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=actor,
        role=assign_roles_role,
        scope_type=AccessScopeType.BRANCH,
        company=branch_a.company,
        branch=branch_a,
    )
    assignment = UserRoleAssignmentFactory.create(
        role=RoleFactory.create(),
        scope_type=AccessScopeType.BRANCH,
        company=branch_b.company,
        branch=branch_b,
    )
    with pytest.raises(ScopeAuthorizationError):
        services.deactivate_role_assignment(assignment=assignment, actor=actor)


def test_region_scoped_administrator_can_assign_branch_role_within_region() -> None:
    region = RegionFactory.create()
    branch = BranchFactory.create(region=region, company=region.company)
    assign_roles_role = _role_with_permissions("assign_roles")
    actor = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=actor,
        role=assign_roles_role,
        scope_type=AccessScopeType.REGION,
        company=region.company,
        region=region,
    )
    target_user = UserFactory.create()
    granted_role = RoleFactory.create()
    assignment = services.assign_role(
        actor=actor,
        user=target_user,
        role=granted_role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    assert assignment.branch_id == branch.id
