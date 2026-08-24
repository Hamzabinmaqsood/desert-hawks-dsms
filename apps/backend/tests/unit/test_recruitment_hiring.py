# mypy: disable-error-code="misc,arg-type"
from datetime import date

import pytest

from dsms.recruitment.enums import (
    ApplicationStatus,
    CandidateStatus,
    OfferStatus,
    OnboardingStatus,
    RequisitionStatus,
    SourceType,
    VacancyStatus,
)
from dsms.recruitment.exceptions import HiringConflict, MakerCheckerViolation
from dsms.recruitment.models import (
    Candidate,
    CandidateApplication,
    EmploymentOffer,
    ManpowerRequisition,
    OnboardingCase,
    Vacancy,
)
from dsms.recruitment.services import approve_requisition, hire_candidate
from dsms.workforce.enums import EmployeeType, EmploymentType
from dsms.workforce.models import EmployeeAssignmentHistory
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory, DesignationFactory

pytestmark = pytest.mark.django_db


def test_requisition_enforces_maker_checker() -> None:
    company = CompanyFactory()
    designation = DesignationFactory(company=company)
    maker = UserFactory()
    requisition = ManpowerRequisition.objects.create(
        company=company,
        designation=designation,
        employee_type=EmployeeType.SECURITY_GUARD,
        employment_type=EmploymentType.PERMANENT,
        requested_headcount=1,
        reason="Growth",
        requested_by=maker,
        status=RequisitionStatus.SUBMITTED,
    )
    with pytest.raises(MakerCheckerViolation):
        approve_requisition(requisition=requisition, actor=maker, approved_headcount=1)


def test_hire_candidate_is_atomic_unique_and_creates_assignment_history() -> None:
    company = CompanyFactory()
    designation = DesignationFactory(company=company)
    actor = UserFactory()
    requisition = ManpowerRequisition.objects.create(
        company=company,
        designation=designation,
        employee_type=EmployeeType.SECURITY_GUARD,
        employment_type=EmploymentType.PERMANENT,
        requested_headcount=1,
        approved_headcount=1,
        reason="Growth",
        requested_by=actor,
        status=RequisitionStatus.APPROVED,
    )
    vacancy = Vacancy.objects.create(
        company=company,
        manpower_requisition=requisition,
        designation=designation,
        employee_type=EmployeeType.SECURITY_GUARD,
        employment_type=EmploymentType.PERMANENT,
        vacancy_code="guard-1",
        title="Guard",
        description="Guard vacancy",
        number_of_positions=1,
        opening_date=date.today(),
        status=VacancyStatus.OPEN,
        created_by=actor,
    )
    candidate = Candidate.objects.create(
        candidate_number="CAN-0001",
        company=company,
        first_name="Ali",
        mobile_number="03001234567",
        source_type=SourceType.WEBSITE,
    )
    application = CandidateApplication.objects.create(
        application_number="APP-0001",
        candidate=candidate,
        vacancy=vacancy,
        company=company,
        status=ApplicationStatus.ONBOARDING,
        source_type=SourceType.WEBSITE,
    )
    offer = EmploymentOffer.objects.create(
        application=application,
        offer_number="OFF-0001",
        company=company,
        designation=designation,
        employment_type=EmploymentType.PERMANENT,
        proposed_joining_date=date.today(),
        status=OfferStatus.ACCEPTED,
        created_by=actor,
    )
    onboarding = OnboardingCase.objects.create(
        application=application,
        candidate=candidate,
        accepted_offer=offer,
        company=company,
        designation=designation,
        proposed_employee_number="EMP-9001",
        proposed_joining_date=date.today(),
        status=OnboardingStatus.READY_TO_HIRE,
    )

    employee = hire_candidate(onboarding=onboarding, actor=actor)

    application.refresh_from_db()
    candidate.refresh_from_db()
    vacancy.refresh_from_db()
    requisition.refresh_from_db()
    onboarding.refresh_from_db()
    assert employee.user_id is None
    assert EmployeeAssignmentHistory.objects.filter(employee=employee).count() == 1
    assert application.status == ApplicationStatus.HIRED
    assert candidate.status == CandidateStatus.HIRED
    assert vacancy.status == VacancyStatus.FILLED
    assert requisition.status == RequisitionStatus.FILLED
    assert onboarding.status == OnboardingStatus.COMPLETED
    with pytest.raises(HiringConflict):
        hire_candidate(onboarding=onboarding, actor=actor)
