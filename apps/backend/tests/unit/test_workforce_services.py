from collections.abc import Callable
from datetime import date

import pytest

from dsms.organization.enums import DepartmentScope
from dsms.workforce import selectors, services
from dsms.workforce.enums import AddressType, EmployeeType, EmploymentStatus, EmploymentType
from dsms.workforce.exceptions import (
    HierarchyMismatchError,
    InactiveRelatedRecordError,
    InvalidStatusTransitionError,
    UserAlreadyLinkedError,
    WorkforceValidationError,
)
from dsms.workforce.models import Employee, EmployeeAssignmentHistory, EmployeeStatusHistory
from tests.factories.identity import UserFactory
from tests.factories.organization import (
    BranchFactory,
    CompanyFactory,
    DepartmentFactory,
    DesignationFactory,
)
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db
TODAY = date(2026, 8, 18)


def create_employee(**overrides: object) -> Employee:
    actor = overrides.pop("actor", UserFactory.create())
    company = overrides.pop("company", CompanyFactory.create())
    values = {
        "actor": actor,
        "company": company,
        "employee_number": " dh-000001 ",
        "first_name": " Ahmed ",
        "last_name": " Khan ",
        "mobile_number": "+923001234567",
        "employee_type": EmployeeType.SECURITY_GUARD,
        "employment_type": EmploymentType.PERMANENT,
        "joining_date": TODAY,
        **overrides,
    }
    return services.create_employee(**values)  # type: ignore[arg-type]


def test_create_employee_normalizes_and_creates_initial_assignment() -> None:
    employee = create_employee(national_identity_number="35202-1234567-1")
    assert employee.employee_number == "DH-000001"
    assert employee.full_name == "Ahmed Khan"
    assert str(employee) == "DH-000001 - Ahmed Khan"
    assert employee.masked_national_identity_number == "*****-*******-1"
    assert (
        EmployeeAssignmentHistory.objects.filter(employee=employee, effective_to=None).count() == 1
    )


def test_duplicate_employee_number_and_identity_are_domain_errors() -> None:
    company = CompanyFactory.create()
    create_employee(company=company, national_identity_number="3520212345671")
    with pytest.raises(WorkforceValidationError):
        create_employee(company=company, employee_number="DH-000001")
    with pytest.raises(WorkforceValidationError):
        create_employee(
            company=company,
            employee_number="DH-000002",
            national_identity_number="35202-1234567-1",
        )


def test_creation_rejects_inactive_company_and_cross_company_org() -> None:
    with pytest.raises(InactiveRelatedRecordError):
        create_employee(company=CompanyFactory.create(is_active=False))
    branch = BranchFactory.create()
    with pytest.raises(HierarchyMismatchError):
        create_employee(company=CompanyFactory.create(), branch=branch)


def test_branch_department_and_designation_consistency() -> None:
    branch = BranchFactory.create()
    department = DepartmentFactory.create(
        company=branch.company, branch=branch, scope=DepartmentScope.BRANCH
    )
    other_branch = BranchFactory.create(company=branch.company, region=branch.region)
    with pytest.raises(HierarchyMismatchError):
        create_employee(company=branch.company, branch=other_branch, department=department)
    designation = DesignationFactory.create(company=branch.company, department=department)
    employee = create_employee(
        company=branch.company,
        branch=branch,
        department=department,
        designation=designation,
    )
    assert employee.department == department


def test_user_linking_is_explicit_and_validated() -> None:
    employee = EmployeeFactory.create()
    user = UserFactory.create()
    services.link_employee_user(employee=employee, user=user)
    assert employee.user == user
    with pytest.raises(UserAlreadyLinkedError):
        services.link_employee_user(employee=EmployeeFactory.create(), user=user)
    services.unlink_employee_user(employee=employee)
    assert employee.user is None
    with pytest.raises(InactiveRelatedRecordError):
        services.link_employee_user(employee=employee, user=UserFactory.create(is_active=False))


def test_leave_and_suspension_lifecycle_and_history() -> None:
    actor = UserFactory.create()
    employee = EmployeeFactory.create()
    services.activate_employee(employee=employee, effective_date=TODAY, changed_by=actor)
    services.place_employee_on_leave(employee=employee, effective_date=TODAY, changed_by=actor)
    services.return_employee_from_leave(employee=employee, effective_date=TODAY, changed_by=actor)
    services.suspend_employee(employee=employee, effective_date=TODAY, changed_by=actor)
    services.reinstate_employee(employee=employee, effective_date=TODAY, changed_by=actor)
    assert employee.employment_status == EmploymentStatus.ACTIVE
    assert EmployeeStatusHistory.objects.filter(employee=employee).count() == 5


@pytest.mark.parametrize(
    ("command", "status"),
    [
        (services.resign_employee, EmploymentStatus.RESIGNED),
        (services.terminate_employee, EmploymentStatus.TERMINATED),
        (services.retire_employee, EmploymentStatus.RETIRED),
        (services.mark_employee_absconded, EmploymentStatus.ABSCONDED),
    ],
)
def test_terminal_statuses_require_exit_and_deactivate(
    command: Callable[..., Employee], status: str
) -> None:
    actor = UserFactory.create()
    employee = EmployeeFactory.create(employment_status=EmploymentStatus.ACTIVE, is_active=True)
    command(
        employee=employee,
        effective_date=TODAY,
        exit_date=TODAY,
        changed_by=actor,
        reason="Lifecycle event",
    )
    assert employee.employment_status == status
    assert employee.exit_date == TODAY
    assert employee.is_active is False


def test_invalid_status_transition_rejected_without_history() -> None:
    employee = EmployeeFactory.create()
    with pytest.raises(InvalidStatusTransitionError):
        services.suspend_employee(
            employee=employee, effective_date=TODAY, changed_by=UserFactory.create()
        )
    assert not EmployeeStatusHistory.objects.filter(employee=employee).exists()


def test_terminal_status_rejects_exit_before_effective_date() -> None:
    employee = EmployeeFactory.create(employment_status=EmploymentStatus.ACTIVE, is_active=True)
    with pytest.raises(WorkforceValidationError):
        services.resign_employee(
            employee=employee,
            effective_date=TODAY,
            exit_date=date(2026, 8, 17),
            changed_by=UserFactory.create(),
        )


def test_assignment_change_closes_previous_row() -> None:
    actor = UserFactory.create()
    employee = create_employee(actor=actor)
    branch = BranchFactory.create(company=employee.company)
    services.change_employee_organization(
        employee=employee, actor=actor, effective_from=TODAY, branch=branch, reason="Transfer"
    )
    rows = list(EmployeeAssignmentHistory.objects.filter(employee=employee))
    assert len(rows) == 2
    assert sum(row.effective_to is None for row in rows) == 1
    assert employee.branch == branch


def test_address_and_emergency_contact_primary_rules() -> None:
    employee = EmployeeFactory.create()
    first = services.add_employee_address(
        employee=employee,
        address_type=AddressType.CURRENT,
        address_line_1=" 1 Main Road ",
        city=" Lahore ",
        country_code="pk",
        is_primary=True,
    )
    second = services.add_employee_address(
        employee=employee,
        address_type=AddressType.CURRENT,
        address_line_1="2 Main Road",
        city="Lahore",
        is_primary=True,
    )
    first.refresh_from_db()
    assert not first.is_primary and second.is_primary and first.country_code == "PK"
    one = services.add_emergency_contact(
        employee=employee,
        name=" Father ",
        relationship=" Father ",
        mobile_number="03001234567",
        is_primary=True,
    )
    two = services.add_emergency_contact(
        employee=employee,
        name="Brother",
        relationship="Brother",
        mobile_number="03007654321",
        is_primary=True,
    )
    one.refresh_from_db()
    assert not one.is_primary and two.is_primary and one.name == "Father"


def test_selectors_cover_common_employee_groups() -> None:
    guard = EmployeeFactory.create(employment_status=EmploymentStatus.ACTIVE, is_active=True)
    supervisor = EmployeeFactory.create(employee_type=EmployeeType.SUPERVISOR)
    assert selectors.get_employee(employee_id=guard.id) == guard
    assert selectors.employees_by_company(company_id=guard.company_id).count() == 1
    assert selectors.active_employees().filter(pk=guard.pk).exists()
    assert selectors.guards().filter(pk=guard.pk).exists()
    assert selectors.supervisors().filter(pk=supervisor.pk).exists()
