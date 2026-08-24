# mypy: disable-error-code="misc,arg-type,attr-defined,comparison-overlap"
from datetime import date, timedelta

import pytest
from django.utils import timezone

from dsms.contracts.models import (
    Client,
    ClientIndustry,
    SecurityPost,
    SecuritySite,
    ServiceContract,
)
from dsms.deployment.enums import AssignmentType, RosterStatus
from dsms.deployment.exceptions import IneligibleEmployee
from dsms.deployment.models import DutyShift, RosterPeriod
from dsms.deployment.services import assign_employee_to_shift, get_shift_coverage
from dsms.workforce.enums import EmployeeType, EmploymentStatus
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_assignment_prevents_overlap_and_reports_planned_coverage() -> None:
    actor = UserFactory()
    branch = BranchFactory()
    company = branch.company
    employee = EmployeeFactory(
        company=company, branch=branch, employment_status=EmploymentStatus.ACTIVE
    )
    industry = ClientIndustry.objects.create(company=company, code="BANK", name="Bank")
    client = Client.objects.create(
        company=company,
        client_code="ABC",
        legal_name="ABC Bank",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=company,
        client=client,
        contract_number="CTR-D",
        contract_type="FIXED_TERM",
        title="Guarding",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        status="ACTIVE",
        created_by=actor,
    )
    site = SecuritySite.objects.create(
        company=company,
        client=client,
        contract=contract,
        site_code="SITE-D",
        name="Blue Area",
        managing_branch=branch,
        address_line_1="Blue Area",
        city_name="Islamabad",
        risk_level="HIGH",
        status="ACTIVE",
    )
    post = SecurityPost.objects.create(
        company=company, client=client, site=site, post_code="MAIN", name="Main", status="ACTIVE"
    )
    roster = RosterPeriod.objects.create(
        company=company,
        branch=branch,
        roster_number="ROS-1",
        name="Test",
        period_start=date.today(),
        period_end=date.today(),
        status=RosterStatus.GENERATED,
        created_by=actor,
    )
    start = timezone.now() + timedelta(days=1)
    shift = DutyShift.objects.create(
        roster_period=roster,
        company=company,
        branch=branch,
        client=client,
        contract=contract,
        site=site,
        post=post,
        duty_date=start.date(),
        starts_at=start,
        ends_at=start + timedelta(hours=12),
        required_headcount=1,
        employee_type=EmployeeType.SECURITY_GUARD,
    )
    assignment = assign_employee_to_shift(
        duty_shift=shift, employee=employee, actor=actor, assignment_type=AssignmentType.REGULAR
    )
    assert assignment.employee == employee
    assert get_shift_coverage(shift)["coverage_percentage"] == 100
    overlapping = DutyShift.objects.create(
        roster_period=roster,
        company=company,
        branch=branch,
        client=client,
        contract=contract,
        site=site,
        post=post,
        duty_date=start.date(),
        starts_at=start + timedelta(hours=1),
        ends_at=start + timedelta(hours=5),
        required_headcount=1,
        employee_type=EmployeeType.SECURITY_GUARD,
    )
    with pytest.raises(IneligibleEmployee, match="SHIFT_OVERLAP"):
        assign_employee_to_shift(duty_shift=overlapping, employee=employee, actor=actor)
