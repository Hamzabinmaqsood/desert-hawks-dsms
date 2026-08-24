from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dsms.organization.enums import DepartmentScope
from dsms.organization.models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
)
from tests.factories.organization import (
    BranchFactory,
    CityFactory,
    CompanyFactory,
    DepartmentFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db


def test_company_code_is_normalized_to_uppercase() -> None:
    company = CompanyFactory.create(code="  abc-1  ")
    assert company.code == "ABC-1"


def test_company_code_must_be_unique() -> None:
    CompanyFactory.create(code="DUP1")
    with pytest.raises(ValidationError):
        Company(code="DUP1", legal_name="Another Co").full_clean()


def test_region_code_unique_within_company() -> None:
    company = CompanyFactory.create()
    RegionFactory.create(company=company, code="NORTH")
    duplicate = RegionFactory.build(company=company, code="NORTH", name="Duplicate")
    with pytest.raises(ValidationError):
        duplicate.full_clean()


def test_region_code_can_repeat_across_companies() -> None:
    RegionFactory.create(code="NORTH")
    other_company = CompanyFactory.create()
    region = RegionFactory.build(company=other_company, code="NORTH", name="Other North")
    region.full_clean()  # should not raise


def test_city_rejects_region_from_a_different_company() -> None:
    region = RegionFactory.create()
    other_company = CompanyFactory.create()
    city = City(
        company=other_company,
        region=region,
        code="CTY1",
        name="Somewhere",
        province_or_state="Punjab",
    )
    with pytest.raises(ValidationError):
        city.full_clean()


def test_branch_rejects_city_from_a_different_region() -> None:
    region = RegionFactory.create()
    other_region = RegionFactory.create(company=region.company)
    city = CityFactory.create(region=other_region, company=region.company)
    branch = Branch(
        company=region.company,
        region=region,
        city=city,
        code="BR1",
        name="Mismatched Branch",
        address_line_1="1 Street",
    )
    with pytest.raises(ValidationError):
        branch.full_clean()


def test_only_one_active_head_office_per_company() -> None:
    company = CompanyFactory.create()
    BranchFactory.create(region=RegionFactory.create(company=company), is_head_office=True)
    region = RegionFactory.create(company=company)
    city = CityFactory.create(region=region, company=company)
    second = Branch(
        company=company,
        region=region,
        city=city,
        code="HQ2",
        name="Second HQ",
        address_line_1="2 Street",
        is_head_office=True,
    )
    with pytest.raises(ValidationError):
        second.full_clean()


@pytest.mark.parametrize("latitude", [Decimal("-91"), Decimal("91")])
def test_branch_latitude_must_be_within_range(latitude: Decimal) -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company)
    branch = Branch(
        company=region.company,
        region=region,
        city=city,
        code="BR-LAT",
        name="Lat Branch",
        address_line_1="1 Street",
        latitude=latitude,
    )
    with pytest.raises(ValidationError):
        branch.full_clean()


@pytest.mark.parametrize("longitude", [Decimal("-181"), Decimal("181")])
def test_branch_longitude_must_be_within_range(longitude: Decimal) -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company)
    branch = Branch(
        company=region.company,
        region=region,
        city=city,
        code="BR-LNG",
        name="Lng Branch",
        address_line_1="1 Street",
        longitude=longitude,
    )
    with pytest.raises(ValidationError):
        branch.full_clean()


def test_department_direct_parent_cycle_is_rejected() -> None:
    company = CompanyFactory.create()
    department = DepartmentFactory.create(company=company)
    department.parent = department
    with pytest.raises(ValidationError):
        department.full_clean()


def test_department_indirect_parent_cycle_is_rejected() -> None:
    company = CompanyFactory.create()
    grandparent = DepartmentFactory.create(company=company)
    parent = DepartmentFactory.create(company=company, parent=grandparent)
    grandparent.parent = parent
    with pytest.raises(ValidationError):
        grandparent.full_clean()


def test_department_company_scope_must_not_have_branch() -> None:
    branch = BranchFactory.create()
    department = Department(
        company=branch.company,
        code="D1",
        name="Company Scoped",
        scope=DepartmentScope.COMPANY,
        branch=branch,
    )
    with pytest.raises(ValidationError):
        department.full_clean()


def test_department_branch_scope_requires_branch() -> None:
    company = CompanyFactory.create()
    department = Department(
        company=company, code="D2", name="Branch Scoped", scope=DepartmentScope.BRANCH
    )
    with pytest.raises(ValidationError):
        department.full_clean()


def test_department_rejects_parent_from_a_different_company() -> None:
    parent = DepartmentFactory.create()
    other_company = CompanyFactory.create()
    child = Department(
        company=other_company,
        parent=parent,
        code="CHILD1",
        name="Cross Company Child",
        scope=DepartmentScope.COMPANY,
    )
    with pytest.raises(ValidationError):
        child.full_clean()


def test_designation_level_must_be_positive() -> None:
    company = CompanyFactory.create()
    designation = Designation(company=company, code="DSG1", name="Guard", level=0)
    with pytest.raises(ValidationError):
        designation.full_clean()


def test_designation_department_must_belong_to_same_company() -> None:
    department = DepartmentFactory.create()
    other_company = CompanyFactory.create()
    designation = Designation(
        company=other_company, department=department, code="DSG2", name="Guard", level=1
    )
    with pytest.raises(ValidationError):
        designation.full_clean()


def test_operational_zone_branch_must_belong_to_same_company() -> None:
    branch = BranchFactory.create()
    other_company = CompanyFactory.create()
    zone = OperationalZone(company=other_company, branch=branch, code="Z1", name="Zone 1")
    with pytest.raises(ValidationError):
        zone.full_clean()
