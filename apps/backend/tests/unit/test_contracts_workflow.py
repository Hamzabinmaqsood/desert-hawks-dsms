# mypy: disable-error-code="misc,arg-type,attr-defined"
from datetime import date, time, timedelta
from decimal import Decimal

import pytest

from dsms.contracts.enums import (
    ContractStatus,
    ContractType,
    CoverageType,
    SiteRiskLevel,
    StaffingRequirementStatus,
)
from dsms.contracts.exceptions import ContractMakerCheckerViolation
from dsms.contracts.models import (
    Client,
    ClientIndustry,
    SecurityPost,
    SecuritySite,
    ServiceContract,
    StaffingRequirement,
    StaffingRequirementDay,
)
from dsms.contracts.selectors import contractual_demand_summary
from dsms.contracts.services import (
    activate_contract,
    activate_security_post,
    activate_security_site,
    activate_staffing_requirement,
    approve_contract,
    submit_contract_for_approval,
)
from dsms.workforce.enums import EmployeeType
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory, CompanyFactory

pytestmark = pytest.mark.django_db


def test_contract_site_post_and_staffing_demand_cycle() -> None:
    company = CompanyFactory()
    branch = BranchFactory(company=company)
    maker, checker = UserFactory(), UserFactory()
    industry = ClientIndustry.objects.create(company=company, code="BANKING", name="Banking")
    client = Client.objects.create(
        company=company,
        client_code="abc",
        legal_name="ABC Bank Ltd.",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=company,
        client=client,
        contract_number="CTR-1",
        contract_type=ContractType.FIXED_TERM,
        title="Guarding",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=365),
        created_by=maker,
    )
    submit_contract_for_approval(contract=contract)
    with pytest.raises(ContractMakerCheckerViolation):
        approve_contract(contract=contract, actor=maker)
    contract = approve_contract(contract=contract, actor=checker)
    contract = activate_contract(contract=contract)
    site = SecuritySite.objects.create(
        company=company,
        client=client,
        contract=contract,
        site_code="site-1",
        name="ABC Bank Blue Area",
        managing_branch=branch,
        address_line_1="Blue Area",
        city_name="Islamabad",
        latitude=Decimal("33.710000"),
        longitude=Decimal("73.060000"),
        geofence_radius_meters=100,
        risk_level=SiteRiskLevel.HIGH,
    )
    site = activate_security_site(site=site)
    post = SecurityPost.objects.create(
        company=company, client=client, site=site, post_code="MAIN", name="Main Entrance"
    )
    post = activate_security_post(post=post)
    requirement = StaffingRequirement.objects.create(
        company=company,
        contract=contract,
        site=site,
        post=post,
        requirement_code="REQ-1",
        employee_type=EmployeeType.SECURITY_GUARD,
        required_headcount=2,
        coverage_type=CoverageType.CUSTOM,
        start_time=time(8),
        end_time=time(20),
        effective_from=date.today(),
    )
    for weekday in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"):
        StaffingRequirementDay.objects.create(staffing_requirement=requirement, weekday=weekday)
    requirement = activate_staffing_requirement(requirement=requirement)
    assert requirement.status == StaffingRequirementStatus.ACTIVE
    assert contract.status == ContractStatus.ACTIVE
    assert (
        contractual_demand_summary(company_id=str(company.pk))["total_required_guard_positions"]
        == 2
    )
    assert not hasattr(requirement, "employee")
