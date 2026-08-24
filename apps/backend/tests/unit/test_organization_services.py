import pytest

from dsms.organization import services
from dsms.organization.enums import DepartmentScope
from dsms.organization.exceptions import (
    ActiveChildrenExistError,
    DuplicateHeadOfficeError,
    HierarchyMismatchError,
    InactiveRelatedRecordError,
    OrganizationValidationError,
)
from dsms.organization.models import Branch, City, Company, Department, Region
from tests.factories.organization import (
    BranchFactory,
    CityFactory,
    CompanyFactory,
    DepartmentFactory,
    DesignationFactory,
    OperationalZoneFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db


# --------------------------------------------------------------------------
# Company
# --------------------------------------------------------------------------


def test_create_company_succeeds_with_valid_data() -> None:
    company = services.create_company(code="dh-1", legal_name="Desert Hawks Pvt Ltd")
    assert company.pk is not None
    assert company.code == "DH-1"
    assert Company.objects.filter(pk=company.pk).exists()


def test_create_company_rejects_duplicate_code() -> None:
    services.create_company(code="DH-2", legal_name="Existing Co")
    with pytest.raises(OrganizationValidationError):
        services.create_company(code="DH-2", legal_name="Duplicate Co")


def test_update_company_changes_fields() -> None:
    company = CompanyFactory.create()
    updated = services.update_company(company=company, legal_name="New Legal Name")
    assert updated.legal_name == "New Legal Name"


def test_deactivate_and_activate_company() -> None:
    company = CompanyFactory.create()
    deactivated = services.deactivate_company(company=company)
    assert deactivated.is_active is False
    activated = services.activate_company(company=deactivated)
    assert activated.is_active is True


# --------------------------------------------------------------------------
# Region
# --------------------------------------------------------------------------


def test_create_region_rejects_inactive_company() -> None:
    company = CompanyFactory.create(is_active=False)
    with pytest.raises(InactiveRelatedRecordError):
        services.create_region(company=company, code="R1", name="Region 1")


def test_deactivate_region_blocked_by_active_branches() -> None:
    region = RegionFactory.create()
    BranchFactory.create(region=region, company=region.company)
    with pytest.raises(ActiveChildrenExistError):
        services.deactivate_region(region=region)


def test_deactivate_region_succeeds_without_active_branches() -> None:
    region = RegionFactory.create()
    deactivated = services.deactivate_region(region=region)
    assert deactivated.is_active is False


def test_update_region_with_invalid_code_does_not_persist_change() -> None:
    region = RegionFactory.create(name="Original Name")
    with pytest.raises(OrganizationValidationError):
        services.update_region(region=region, code="", name="Should Not Persist")
    refreshed = Region.objects.get(pk=region.pk)
    assert refreshed.name == "Original Name"


# --------------------------------------------------------------------------
# City
# --------------------------------------------------------------------------


def test_create_city_rejects_region_from_different_company() -> None:
    region = RegionFactory.create()
    other_company = CompanyFactory.create()
    with pytest.raises(HierarchyMismatchError):
        services.create_city(
            company=other_company,
            region=region,
            code="CTY-X",
            name="Cross City",
            province_or_state="Sindh",
        )


def test_deactivate_city_blocked_by_active_branches() -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company)
    BranchFactory.create(region=region, company=region.company, city=city)
    with pytest.raises(ActiveChildrenExistError):
        services.deactivate_city(city=city)


# --------------------------------------------------------------------------
# Branch
# --------------------------------------------------------------------------


def test_create_branch_rejects_inactive_city() -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company, is_active=False)
    with pytest.raises(InactiveRelatedRecordError):
        services.create_branch(
            company=region.company,
            region=region,
            city=city,
            code="BR-X",
            name="Branch X",
            address_line_1="1 Street",
        )


def test_create_branch_head_office_conflict_is_rejected() -> None:
    company = CompanyFactory.create()
    region = RegionFactory.create(company=company)
    city = CityFactory.create(region=region, company=company)
    services.create_branch(
        company=company,
        region=region,
        city=city,
        code="HQ1",
        name="Head Office",
        address_line_1="1 Street",
        is_head_office=True,
    )
    city_2 = CityFactory.create(region=region, company=company)
    with pytest.raises(DuplicateHeadOfficeError):
        services.create_branch(
            company=company,
            region=region,
            city=city_2,
            code="HQ2",
            name="Second Head Office",
            address_line_1="2 Street",
            is_head_office=True,
        )


def test_deactivate_branch_blocked_by_active_zones() -> None:
    branch = BranchFactory.create()
    OperationalZoneFactory.create(branch=branch, company=branch.company)
    with pytest.raises(ActiveChildrenExistError):
        services.deactivate_branch(branch=branch)


def test_update_branch_head_office_conflict_does_not_persist_other_changes() -> None:
    company = CompanyFactory.create()
    region = RegionFactory.create(company=company)
    city = CityFactory.create(region=region, company=company)
    services.create_branch(
        company=company,
        region=region,
        city=city,
        code="HQA",
        name="HQ A",
        address_line_1="1 Street",
        is_head_office=True,
    )
    city_2 = CityFactory.create(region=region, company=company)
    branch_2 = services.create_branch(
        company=company,
        region=region,
        city=city_2,
        code="BR2",
        name="Branch 2",
        address_line_1="2 Street",
    )
    with pytest.raises(DuplicateHeadOfficeError):
        services.update_branch(branch=branch_2, name="Renamed Branch", is_head_office=True)
    refreshed = Branch.objects.get(pk=branch_2.pk)
    assert refreshed.name == "Branch 2"
    assert refreshed.is_head_office is False


# --------------------------------------------------------------------------
# Department
# --------------------------------------------------------------------------


def test_create_department_rejects_inactive_parent() -> None:
    company = CompanyFactory.create()
    parent = DepartmentFactory.create(company=company, is_active=False)
    with pytest.raises(InactiveRelatedRecordError):
        services.create_department(
            company=company,
            parent=parent,
            code="CHILD",
            name="Child Dept",
            scope=DepartmentScope.COMPANY,
        )


def test_create_department_rejects_cross_company_parent() -> None:
    parent = DepartmentFactory.create()
    other_company = CompanyFactory.create()
    with pytest.raises(HierarchyMismatchError):
        services.create_department(
            company=other_company,
            parent=parent,
            code="CHILD2",
            name="Child Dept 2",
            scope=DepartmentScope.COMPANY,
        )


def test_deactivate_department_blocked_by_active_children() -> None:
    parent = DepartmentFactory.create()
    DepartmentFactory.create(company=parent.company, parent=parent)
    with pytest.raises(ActiveChildrenExistError):
        services.deactivate_department(department=parent)


def test_create_branch_scoped_department_requires_branch() -> None:
    company = CompanyFactory.create()
    with pytest.raises(OrganizationValidationError):
        services.create_department(
            company=company,
            code="BRDEPT",
            name="Branch Dept",
            scope=DepartmentScope.BRANCH,
        )


# --------------------------------------------------------------------------
# Designation
# --------------------------------------------------------------------------


def test_create_designation_rejects_department_from_other_company() -> None:
    department = DepartmentFactory.create()
    other_company = CompanyFactory.create()
    with pytest.raises(HierarchyMismatchError):
        services.create_designation(
            company=other_company,
            department=department,
            code="DSG-X",
            name="Guard",
            level=1,
        )


def test_activate_and_deactivate_designation() -> None:
    designation = DesignationFactory.create()
    deactivated = services.deactivate_designation(designation=designation)
    assert deactivated.is_active is False
    activated = services.activate_designation(designation=deactivated)
    assert activated.is_active is True


# --------------------------------------------------------------------------
# Operational Zone
# --------------------------------------------------------------------------


def test_create_operational_zone_rejects_cross_company_branch() -> None:
    branch = BranchFactory.create()
    other_company = CompanyFactory.create()
    with pytest.raises(HierarchyMismatchError):
        services.create_operational_zone(
            company=other_company, branch=branch, code="Z-X", name="Zone X"
        )


def test_create_operational_zone_rejects_inactive_branch() -> None:
    branch = BranchFactory.create(is_active=False)
    with pytest.raises(InactiveRelatedRecordError):
        services.create_operational_zone(
            company=branch.company, branch=branch, code="Z-Y", name="Zone Y"
        )


def test_update_operational_zone_changes_name() -> None:
    zone = OperationalZoneFactory.create()
    updated = services.update_operational_zone(operational_zone=zone, name="Renamed Zone")
    assert updated.name == "Renamed Zone"


def test_activate_operational_zone_succeeds() -> None:
    zone = OperationalZoneFactory.create(is_active=False)
    activated = services.activate_operational_zone(operational_zone=zone)
    assert activated.is_active is True


# --------------------------------------------------------------------------
# Additional happy paths (create/update/activate round-trips)
# --------------------------------------------------------------------------


def test_create_region_and_activate_succeeds() -> None:
    company = CompanyFactory.create()
    region = services.create_region(company=company, code="R-OK", name="Region OK")
    assert region.pk is not None
    region.is_active = False
    region.save(update_fields=["is_active"])
    activated = services.activate_region(region=region)
    assert activated.is_active is True


def test_create_city_and_update_succeeds() -> None:
    region = RegionFactory.create()
    city = services.create_city(
        company=region.company,
        region=region,
        code="CTY-OK",
        name="City OK",
        province_or_state="Sindh",
    )
    assert city.pk is not None
    updated = services.update_city(city=city, name="City Renamed")
    assert updated.name == "City Renamed"


def test_activate_city_succeeds() -> None:
    city = CityFactory.create(is_active=False)
    activated = services.activate_city(city=city)
    assert activated.is_active is True
    assert City.objects.get(pk=city.pk).is_active is True


def test_create_branch_and_activate_succeeds() -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company)
    branch = services.create_branch(
        company=region.company,
        region=region,
        city=city,
        code="BR-OK",
        name="Branch OK",
        address_line_1="1 Street",
    )
    assert branch.pk is not None
    branch.is_active = False
    branch.save(update_fields=["is_active"])
    activated = services.activate_branch(branch=branch)
    assert activated.is_active is True


def test_create_department_and_update_succeeds() -> None:
    company = CompanyFactory.create()
    department = services.create_department(
        company=company, code="DEPT-OK", name="Dept OK", scope=DepartmentScope.COMPANY
    )
    assert department.pk is not None
    updated = services.update_department(department=department, sort_order=5)
    assert updated.sort_order == 5


def test_activate_department_succeeds() -> None:
    department = DepartmentFactory.create(is_active=False)
    activated = services.activate_department(department=department)
    assert activated.is_active is True
    assert Department.objects.get(pk=department.pk).is_active is True


def test_create_designation_and_update_succeeds() -> None:
    company = CompanyFactory.create()
    designation = services.create_designation(
        company=company, code="DSG-OK", name="Designation OK", level=3
    )
    assert designation.pk is not None
    updated = services.update_designation(designation=designation, level=4)
    assert updated.level == 4


def test_create_operational_zone_succeeds() -> None:
    branch = BranchFactory.create()
    zone = services.create_operational_zone(
        company=branch.company, branch=branch, code="Z-OK", name="Zone OK"
    )
    assert zone.pk is not None
