from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from dsms.identity import access
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import (
    BranchFactory,
    CompanyFactory,
    DepartmentFactory,
    OperationalZoneFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db


def _permission(codename: str, app_label: str = "organization") -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def _role_with_permissions(*codenames: str, app_label: str = "organization") -> Role:
    role = RoleFactory.create()
    role.permissions.set([_permission(codename, app_label) for codename in codenames])
    return role


# --------------------------------------------------------------------------
# has_permission: baseline behavior
# --------------------------------------------------------------------------


def test_superuser_bypasses_rbac_entirely() -> None:
    user = UserFactory.create(is_superuser=True, is_staff=True)
    assert access.has_permission(user=user, permission="organization.view_branch") is True


def test_inactive_user_has_no_access() -> None:
    user = UserFactory.create(is_active=False)
    assert access.has_permission(user=user, permission="organization.view_branch") is False


def test_anonymous_user_has_no_access() -> None:
    assert access.has_permission(user=None, permission="organization.view_branch") is False


def test_missing_permission_is_denied() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    UserRoleAssignmentFactory.create(user=user, role=role, scope_type=AccessScopeType.GLOBAL)
    assert access.has_permission(user=user, permission="organization.change_branch") is False


def test_global_assignment_grants_permission_everywhere() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    UserRoleAssignmentFactory.create(user=user, role=role, scope_type=AccessScopeType.GLOBAL)
    branch = BranchFactory.create()
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_branch",
            company=branch.company,
            region=branch.region,
            branch=branch,
        )
        is True
    )


# --------------------------------------------------------------------------
# Scope containment
# --------------------------------------------------------------------------


def test_company_scope_grants_access_within_company() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    company = CompanyFactory.create()
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )
    branch = BranchFactory.create(region=RegionFactory.create(company=company))
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_branch",
            company=branch.company,
            region=branch.region,
            branch=branch,
        )
        is True
    )


def test_company_scope_denies_unrelated_company() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    company = CompanyFactory.create()
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )
    other_branch = BranchFactory.create()
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_branch",
            company=other_branch.company,
            region=other_branch.region,
            branch=other_branch,
        )
        is False
    )


def test_region_scope_grants_access_within_region() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    region = RegionFactory.create()
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.REGION,
        company=region.company,
        region=region,
    )
    branch = BranchFactory.create(region=region)
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_branch",
            company=branch.company,
            region=branch.region,
            branch=branch,
        )
        is True
    )


def test_region_scope_denies_branch_in_different_region() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    region = RegionFactory.create()
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.REGION,
        company=region.company,
        region=region,
    )
    other_branch = BranchFactory.create()
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_branch",
            company=other_branch.company,
            region=other_branch.region,
            branch=other_branch,
        )
        is False
    )


def test_branch_scope_grants_access_to_operational_zone_inside_branch() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_operationalzone")
    branch = BranchFactory.create()
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    zone = OperationalZoneFactory.create(branch=branch)
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_operationalzone",
            company=zone.company,
            region=branch.region,
            branch=branch,
            operational_zone=zone,
        )
        is True
    )


def test_branch_scope_denies_zone_in_different_branch() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_operationalzone")
    branch = BranchFactory.create()
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    other_zone = OperationalZoneFactory.create()
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_operationalzone",
            company=other_zone.company,
            region=other_zone.branch.region,
            branch=other_zone.branch,
            operational_zone=other_zone,
        )
        is False
    )


def test_department_scope_does_not_inherit_from_branch_scope() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_department")
    branch = BranchFactory.create()
    department = DepartmentFactory.create(company=branch.company)
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_department",
            company=department.company,
            department=department,
        )
        is False
    )


def test_department_scope_grants_only_that_exact_department() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_department")
    department = DepartmentFactory.create()
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.DEPARTMENT,
        company=department.company,
        department=department,
    )
    other_department = DepartmentFactory.create(company=department.company)
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_department",
            company=department.company,
            department=department,
        )
        is True
    )
    assert (
        access.has_permission(
            user=user,
            permission="organization.view_department",
            company=other_department.company,
            department=other_department,
        )
        is False
    )


# --------------------------------------------------------------------------
# Time-window and activation state
# --------------------------------------------------------------------------


def test_expired_assignment_grants_no_access() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.GLOBAL,
        ends_at=timezone.now() - timedelta(days=1),
    )
    assert access.has_permission(user=user, permission="organization.view_branch") is False


def test_future_assignment_grants_no_access() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.GLOBAL,
        starts_at=timezone.now() + timedelta(days=1),
    )
    assert access.has_permission(user=user, permission="organization.view_branch") is False


def test_inactive_role_grants_no_access() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    role.is_active = False
    role.save(update_fields=["is_active"])
    UserRoleAssignmentFactory.create(user=user, role=role, scope_type=AccessScopeType.GLOBAL)
    assert access.has_permission(user=user, permission="organization.view_branch") is False


def test_inactive_assignment_grants_no_access() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.GLOBAL, is_active=False
    )
    assert access.has_permission(user=user, permission="organization.view_branch") is False


# --------------------------------------------------------------------------
# get_effective_permissions / accessible ids / scope summary
# --------------------------------------------------------------------------


def test_get_effective_permissions_for_superuser_returns_everything() -> None:
    user = UserFactory.create(is_superuser=True)
    permissions = access.get_effective_permissions(user)
    assert "organization.view_branch" in permissions
    assert "identity.manage_roles" in permissions


def test_get_effective_permissions_aggregates_across_assignments() -> None:
    user = UserFactory.create()
    role_a = _role_with_permissions("view_branch")
    role_b = _role_with_permissions("change_branch")
    UserRoleAssignmentFactory.create(user=user, role=role_a, scope_type=AccessScopeType.GLOBAL)
    UserRoleAssignmentFactory.create(user=user, role=role_b, scope_type=AccessScopeType.GLOBAL)
    permissions = access.get_effective_permissions(user)
    assert {"organization.view_branch", "organization.change_branch"} <= permissions


def test_accessible_branch_ids_company_scope_includes_branches_in_company() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    company = CompanyFactory.create()
    region = RegionFactory.create(company=company)
    branch = BranchFactory.create(company=company, region=region)
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )
    assert branch.id in access.get_accessible_branch_ids(user)


def test_accessible_branch_ids_excludes_unrelated_branch() -> None:
    user = UserFactory.create()
    role = _role_with_permissions("view_branch")
    company = CompanyFactory.create()
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )
    unrelated_branch = BranchFactory.create()
    assert unrelated_branch.id not in access.get_accessible_branch_ids(user)


def test_access_scope_summary_for_unassigned_user() -> None:
    user = UserFactory.create()
    summary = access.get_access_scope_summary(user)
    assert summary["is_superuser"] is False
    assert summary["assignments"] == []
    assert summary["accessible_company_ids"] == []
