# mypy: disable-error-code="arg-type,attr-defined,misc,no-untyped-call,no-untyped-def"
from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from dsms.attendance.models import AttendancePeriod, AttendancePolicy, AttendanceRecord
from dsms.attendance.services import (
    approve_attendance_period,
    build_payroll_timekeeping_input,
    check_in_for_duty,
    check_out_from_duty,
    generate_expected_attendance,
    lock_attendance_period,
    verify_attendance,
)
from dsms.contracts.models import (
    Client,
    ClientIndustry,
    SecurityPost,
    SecuritySite,
    ServiceContract,
    StaffingRequirement,
)
from dsms.contracts.selectors import get_effective_staffing_demand
from dsms.deployment.enums import AssignmentType, RosterStatus
from dsms.deployment.models import DutyShift, RosterPeriod
from dsms.deployment.services import (
    approve_roster,
    assign_employee_to_shift,
    lock_roster,
    publish_roster,
    submit_roster,
)
from dsms.finance.payroll_models import PayrollPeriod
from dsms.incidents.models import IncidentType
from dsms.incidents.services import acknowledge_sos, resolve_sos, transition_incident, trigger_sos
from dsms.workforce.enums import EmployeeType, EmploymentStatus
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def operational_context():
    creator, checker = UserFactory(), UserFactory()
    branch = BranchFactory()
    industry = ClientIndustry.objects.create(company=branch.company, code="OPS", name="Operations")
    client = Client.objects.create(
        company=branch.company,
        client_code="OPS",
        legal_name="Operational Client",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=branch.company,
        client=client,
        contract_number="OPS-CTR",
        contract_type="FIXED_TERM",
        title="Operational coverage",
        start_date=date.today(),
        status="ACTIVE",
        created_by=creator,
    )
    site = SecuritySite.objects.create(
        company=branch.company,
        client=client,
        contract=contract,
        site_code="OPS-SITE",
        name="Operational Site",
        managing_branch=branch,
        address_line_1="Test",
        city_name="Islamabad",
        risk_level="MEDIUM",
        status="ACTIVE",
    )
    post = SecurityPost.objects.create(
        company=branch.company,
        client=client,
        site=site,
        post_code="GATE",
        name="Gate",
        status="ACTIVE",
    )
    return creator, checker, branch, contract, site, post


def test_effective_contract_demand_preserves_historical_headcount() -> None:
    _, _, branch, contract, site, post = operational_context()
    today = date.today()
    StaffingRequirement.objects.create(
        company=branch.company,
        contract=contract,
        site=site,
        post=post,
        requirement_code="OPS-OLD",
        employee_type=EmployeeType.SECURITY_GUARD,
        required_headcount=10,
        coverage_type="FIXED",
        start_time="08:00",
        end_time="20:00",
        effective_from=today - timedelta(days=30),
        effective_to=today,
        status="ACTIVE",
    )
    StaffingRequirement.objects.create(
        company=branch.company,
        contract=contract,
        site=site,
        post=post,
        requirement_code="OPS-NEW",
        employee_type=EmployeeType.SECURITY_GUARD,
        required_headcount=12,
        coverage_type="FIXED",
        start_time="08:00",
        end_time="20:00",
        effective_from=today + timedelta(days=1),
        status="ACTIVE",
    )
    assert get_effective_staffing_demand(site=site, date=today)[0].required_headcount == 10
    assert (
        get_effective_staffing_demand(site=site, date=today + timedelta(days=1))[
            0
        ].required_headcount
        == 12
    )


def test_flow_a_roster_attendance_and_quantities_only_payroll_handoff() -> None:
    creator, checker, branch, contract, site, post = operational_context()
    guard_user = UserFactory()
    guard = EmployeeFactory(
        company=branch.company,
        branch=branch,
        user=guard_user,
        employee_type=EmployeeType.SECURITY_GUARD,
        employment_status=EmploymentStatus.ACTIVE,
    )
    start = timezone.now() + timedelta(hours=1)
    roster = RosterPeriod.objects.create(
        company=branch.company,
        branch=branch,
        roster_number="OPS-ROS",
        name="Operational",
        period_start=start.date(),
        period_end=start.date(),
        status=RosterStatus.GENERATED,
        created_by=creator,
    )
    shift = DutyShift.objects.create(
        roster_period=roster,
        company=branch.company,
        branch=branch,
        client=site.client,
        contract=contract,
        site=site,
        post=post,
        duty_date=start.date(),
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        required_headcount=1,
        employee_type=EmployeeType.SECURITY_GUARD,
    )
    assignment = assign_employee_to_shift(
        duty_shift=shift, employee=guard, actor=creator, assignment_type=AssignmentType.REGULAR
    )
    submit_roster(roster=roster, actor=creator)
    approve_roster(roster=roster, actor=checker)
    publish_roster(roster=roster, actor=checker)
    lock_roster(roster=roster, actor=checker)
    AttendancePolicy.objects.create(
        company=branch.company, site=site, name="Operational policy", effective_from=date.today()
    )
    period = AttendancePeriod.objects.create(
        company=branch.company,
        branch=branch,
        period_start=start.date(),
        period_end=start.date(),
        name="Operational period",
        submitted_by=creator,
    )
    assert generate_expected_attendance(attendance_period=period) == 1
    assert generate_expected_attendance(attendance_period=period) == 0
    check_in_for_duty(user=guard_user, duty_assignment=assignment, event_time=start)
    check_out_from_duty(
        user=guard_user, duty_assignment=assignment, event_time=start + timedelta(hours=8)
    )
    record = verify_attendance(
        record=AttendanceRecord.objects.get(duty_assignment=assignment), actor=creator
    )
    approve_attendance_period(period=period, actor=checker)
    lock_attendance_period(period=period, actor=checker)
    payroll_period = PayrollPeriod.objects.create(
        company=branch.company,
        name="Operational payroll",
        start_date=start.date(),
        end_date=start.date(),
        payment_date=start.date() + timedelta(days=1),
    )
    first = build_payroll_timekeeping_input(
        attendance_period=period, payroll_period=payroll_period, employee=guard, actor=checker
    )
    second = build_payroll_timekeeping_input(
        attendance_period=period, payroll_period=payroll_period, employee=guard, actor=checker
    )
    assert first.pk == second.pk
    assert first.quantities["approved_worked_hours"] == "8"
    assert "salary" not in first.quantities and "deduction" not in first.quantities
    record.refresh_from_db()
    assert record.status == "LOCKED"


def test_flow_b_sos_acknowledgement_resolution_and_timeline() -> None:
    actor, command_user, branch, _, site, _ = operational_context()
    guard = EmployeeFactory(
        company=branch.company,
        branch=branch,
        user=actor,
        employee_type=EmployeeType.SECURITY_GUARD,
        employment_status=EmploymentStatus.ACTIVE,
    )
    IncidentType.objects.create(
        company=branch.company,
        code="SOS_EMERGENCY",
        name="SOS",
        default_severity="CRITICAL",
        default_priority="EMERGENCY",
        is_active=True,
    )
    request_id = uuid4()
    sos = trigger_sos(
        actor=actor,
        employee=guard,
        client_event_id=request_id,
        location={"latitude": "33.71", "longitude": "73.06"},
        message="Test only",
    )
    assert trigger_sos(actor=actor, employee=guard, client_event_id=request_id).pk == sos.pk
    acknowledge_sos(sos=sos, actor=command_user)
    incident = sos.linked_incident
    incident.refresh_from_db()
    transition_incident(incident=incident, actor=command_user, new_status="RESPONDING")
    transition_incident(incident=incident, actor=command_user, new_status="CONTAINED")
    transition_incident(
        incident=incident, actor=command_user, new_status="RESOLVED", summary="Fake drill resolved"
    )
    resolve_sos(sos=sos, actor=command_user, reason="Fake drill completed")
    incident.refresh_from_db()
    assert incident.events.filter(event_type="ACKNOWLEDGED").exists()
    assert incident.events.filter(event_type="RESOLVED").exists()
    sos.refresh_from_db()
    assert sos.status == "CLOSED"
