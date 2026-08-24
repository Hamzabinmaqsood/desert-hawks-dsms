from datetime import timedelta
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, UserRoleAssignment
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import (
    BranchFactory,
    CompanyFactory,
    DepartmentFactory,
    OperationalZoneFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db


def _build_assignment(**overrides: Any) -> UserRoleAssignment:
    """Build (unsaved) an assignment, but with real saved user/role so that
    ``full_clean()``'s foreign-key existence checks succeed."""
    overrides.setdefault("user", UserFactory.create())
    overrides.setdefault("role", RoleFactory.create())
    return UserRoleAssignmentFactory.build(**overrides)


# --------------------------------------------------------------------------
# Role
# --------------------------------------------------------------------------


def test_role_code_is_normalized_to_uppercase() -> None:
    role = RoleFactory.create(code="  custom-role  ")
    assert role.code == "CUSTOM-ROLE"


def test_system_role_code_must_be_globally_unique() -> None:
    RoleFactory.create(company=None, code="SYS1")
    duplicate = Role(company=None, code="SYS1", name="Duplicate System Role")
    with pytest.raises(ValidationError):
        duplicate.full_clean()


def test_company_role_code_unique_within_company() -> None:
    company = CompanyFactory.create()
    RoleFactory.create(company=company, code="LOCAL1")
    duplicate = Role(company=company, code="LOCAL1", name="Duplicate")
    with pytest.raises(ValidationError):
        duplicate.full_clean()


def test_company_role_code_can_repeat_across_companies() -> None:
    RoleFactory.create(company=CompanyFactory.create(), code="SHARED")
    other_company = CompanyFactory.create()
    role = Role(company=other_company, code="SHARED", name="Shared Elsewhere")
    role.full_clean()  # should not raise


def test_role_code_can_match_between_system_and_company_role() -> None:
    RoleFactory.create(company=None, code="SAME")
    company = CompanyFactory.create()
    role = Role(company=company, code="SAME", name="Company Version")
    role.full_clean()  # should not raise: distinct uniqueness scopes


# --------------------------------------------------------------------------
# UserRoleAssignment
# --------------------------------------------------------------------------


def test_valid_global_assignment_passes_validation() -> None:
    assignment = _build_assignment(scope_type=AccessScopeType.GLOBAL)
    assignment.full_clean()


def test_global_assignment_rejects_populated_company() -> None:
    company = CompanyFactory.create()
    assignment = _build_assignment(scope_type=AccessScopeType.GLOBAL, company=company)
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_company_scope_requires_company() -> None:
    assignment = _build_assignment(scope_type=AccessScopeType.COMPANY)
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_company_scope_forbids_region() -> None:
    company = CompanyFactory.create()
    region = RegionFactory.create(company=company)
    assignment = _build_assignment(
        scope_type=AccessScopeType.COMPANY, company=company, region=region
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_valid_company_assignment_passes_validation() -> None:
    company = CompanyFactory.create()
    assignment = _build_assignment(scope_type=AccessScopeType.COMPANY, company=company)
    assignment.full_clean()


def test_region_scope_rejects_region_from_different_company() -> None:
    company = CompanyFactory.create()
    other_region = RegionFactory.create()  # belongs to a different company
    assignment = _build_assignment(
        scope_type=AccessScopeType.REGION, company=company, region=other_region
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_valid_region_assignment_passes_validation() -> None:
    region = RegionFactory.create()
    assignment = _build_assignment(
        scope_type=AccessScopeType.REGION, company=region.company, region=region
    )
    assignment.full_clean()


def test_branch_scope_rejects_branch_from_different_company() -> None:
    company = CompanyFactory.create()
    other_branch = BranchFactory.create()
    assignment = _build_assignment(
        scope_type=AccessScopeType.BRANCH, company=company, branch=other_branch
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_valid_branch_assignment_passes_validation() -> None:
    branch = BranchFactory.create()
    assignment = _build_assignment(
        scope_type=AccessScopeType.BRANCH, company=branch.company, branch=branch
    )
    assignment.full_clean()


def test_department_scope_rejects_department_from_different_company() -> None:
    company = CompanyFactory.create()
    other_department = DepartmentFactory.create()
    assignment = _build_assignment(
        scope_type=AccessScopeType.DEPARTMENT, company=company, department=other_department
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_valid_department_assignment_passes_validation() -> None:
    department = DepartmentFactory.create()
    assignment = _build_assignment(
        scope_type=AccessScopeType.DEPARTMENT, company=department.company, department=department
    )
    assignment.full_clean()


def test_operational_zone_scope_rejects_zone_from_different_company() -> None:
    company = CompanyFactory.create()
    other_zone = OperationalZoneFactory.create()
    assignment = _build_assignment(
        scope_type=AccessScopeType.OPERATIONAL_ZONE, company=company, operational_zone=other_zone
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_valid_operational_zone_assignment_passes_validation() -> None:
    zone = OperationalZoneFactory.create()
    assignment = _build_assignment(
        scope_type=AccessScopeType.OPERATIONAL_ZONE,
        company=zone.company,
        operational_zone=zone,
    )
    assignment.full_clean()


def test_ends_at_must_be_after_starts_at() -> None:
    now = timezone.now()
    assignment = _build_assignment(
        scope_type=AccessScopeType.GLOBAL, starts_at=now, ends_at=now - timedelta(days=1)
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_valid_start_end_window_passes_validation() -> None:
    now = timezone.now()
    assignment = _build_assignment(
        scope_type=AccessScopeType.GLOBAL, starts_at=now, ends_at=now + timedelta(days=30)
    )
    assignment.full_clean()


def test_role_company_must_match_assignment_company() -> None:
    role_company = CompanyFactory.create()
    assignment_company = CompanyFactory.create()
    role = RoleFactory.create(company=role_company)
    assignment = _build_assignment(
        role=role, scope_type=AccessScopeType.COMPANY, company=assignment_company
    )
    with pytest.raises(ValidationError):
        assignment.full_clean()


def test_system_role_usable_at_any_company_scope() -> None:
    system_role = RoleFactory.create(company=None, is_system=True)
    company = CompanyFactory.create()
    assignment = _build_assignment(
        role=system_role, scope_type=AccessScopeType.COMPANY, company=company
    )
    assignment.full_clean()  # should not raise


def test_city_and_designation_have_no_dedicated_scope_type() -> None:
    # Sanity check that AccessScopeType intentionally excludes CITY/DESIGNATION/CLIENT/SITE.
    values = {choice.value for choice in AccessScopeType}
    assert values == {"GLOBAL", "COMPANY", "REGION", "BRANCH", "DEPARTMENT", "OPERATIONAL_ZONE"}
