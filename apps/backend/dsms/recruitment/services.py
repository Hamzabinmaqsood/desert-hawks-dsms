from __future__ import annotations

from django.db import models, transaction
from django.utils import timezone

from dsms.identity.models import User
from dsms.workforce.models import Employee
from dsms.workforce.services import create_employee

from .enums import (
    ApplicationStatus,
    CandidateStatus,
    ChecklistStatus,
    OfferStatus,
    OnboardingStatus,
    RequisitionStatus,
    VacancyStatus,
    VerificationStatus,
)
from .exceptions import HiringConflict, InvalidTransition, MakerCheckerViolation
from .models import (
    ApplicationStatusHistory,
    BackgroundCheck,
    CandidateApplication,
    EmploymentOffer,
    ManpowerRequisition,
    OnboardingCase,
    OnboardingChecklistItem,
    OnboardingChecklistTemplate,
    Vacancy,
)


def change_application_status(
    *, application: CandidateApplication, status: str, actor: User | None, reason: str = ""
) -> CandidateApplication:
    previous = application.status
    if previous == status:
        return application
    with transaction.atomic():
        application.status = status
        application.save(update_fields=["status", "updated_at"])
        ApplicationStatusHistory.objects.create(
            application=application,
            previous_status=previous,
            new_status=status,
            reason=reason,
            changed_by=actor,
        )
    return application


@transaction.atomic
def submit_requisition(*, requisition: ManpowerRequisition, actor: User) -> ManpowerRequisition:
    requisition = ManpowerRequisition.objects.select_for_update().get(pk=requisition.pk)
    if requisition.status != RequisitionStatus.DRAFT:
        raise InvalidTransition("Only draft requisitions can be submitted.")
    requisition.status = RequisitionStatus.SUBMITTED
    requisition.save(update_fields=["status", "updated_at"])
    return requisition


@transaction.atomic
def approve_requisition(
    *, requisition: ManpowerRequisition, actor: User, approved_headcount: int
) -> ManpowerRequisition:
    requisition = ManpowerRequisition.objects.select_for_update().get(pk=requisition.pk)
    if requisition.requested_by_id == actor.id:
        raise MakerCheckerViolation("A requisition creator cannot approve their own request.")
    if requisition.status != RequisitionStatus.SUBMITTED:
        raise InvalidTransition("Only submitted requisitions can be approved.")
    if approved_headcount < 1 or approved_headcount > requisition.requested_headcount:
        raise InvalidTransition("Approved headcount must be within the requested headcount.")
    requisition.status = RequisitionStatus.APPROVED
    requisition.approved_headcount = approved_headcount
    requisition.approved_by = actor
    requisition.approved_at = timezone.now()
    requisition.save(
        update_fields=["status", "approved_headcount", "approved_by", "approved_at", "updated_at"]
    )
    return requisition


@transaction.atomic
def open_vacancy(*, vacancy: Vacancy) -> Vacancy:
    vacancy = (
        Vacancy.objects.select_for_update()
        .select_related("manpower_requisition")
        .get(pk=vacancy.pk)
    )
    if vacancy.manpower_requisition and vacancy.manpower_requisition.status not in {
        RequisitionStatus.APPROVED,
        RequisitionStatus.OPEN,
    }:
        raise InvalidTransition("Vacancy requires an approved requisition.")
    vacancy.status = VacancyStatus.OPEN
    vacancy.save(update_fields=["status", "updated_at"])
    return vacancy


@transaction.atomic
def approve_offer(*, offer: EmploymentOffer, actor: User) -> EmploymentOffer:
    offer = EmploymentOffer.objects.select_for_update().get(pk=offer.pk)
    if offer.created_by_id == actor.id:
        raise MakerCheckerViolation("Offer creator cannot approve their own offer.")
    if offer.status != OfferStatus.SUBMITTED:
        raise InvalidTransition("Only submitted offers can be approved.")
    offer.status, offer.approved_by, offer.approved_at = OfferStatus.APPROVED, actor, timezone.now()
    offer.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return offer


@transaction.atomic
def accept_offer(*, offer: EmploymentOffer, actor: User | None = None) -> EmploymentOffer:
    offer = (
        EmploymentOffer.objects.select_for_update().select_related("application").get(pk=offer.pk)
    )
    if offer.status != OfferStatus.ISSUED:
        raise InvalidTransition("Only issued offers can be accepted.")
    if offer.offer_expiry_date and offer.offer_expiry_date < timezone.localdate():
        raise InvalidTransition("Expired offers cannot be accepted.")
    offer.status, offer.accepted_at = OfferStatus.ACCEPTED, timezone.now()
    offer.save(update_fields=["status", "accepted_at", "updated_at"])
    change_application_status(
        application=offer.application, status=ApplicationStatus.OFFER_ACCEPTED, actor=actor
    )
    return offer


@transaction.atomic
def begin_onboarding(
    *,
    offer: EmploymentOffer,
    assigned_to: User | None = None,
    template: OnboardingChecklistTemplate | None = None,
) -> OnboardingCase:
    offer = (
        EmploymentOffer.objects.select_for_update()
        .select_related("application__candidate")
        .get(pk=offer.pk)
    )
    if offer.status != OfferStatus.ACCEPTED:
        raise InvalidTransition("Onboarding requires an accepted offer.")
    case = OnboardingCase.objects.create(
        application=offer.application,
        candidate=offer.application.candidate,
        accepted_offer=offer,
        company=offer.company,
        branch=offer.branch,
        department=offer.department,
        designation=offer.designation,
        proposed_joining_date=offer.proposed_joining_date,
        assigned_to=assigned_to,
    )
    if template:
        OnboardingChecklistItem.objects.bulk_create(
            [
                OnboardingChecklistItem(
                    onboarding_case=case,
                    template_item=item,
                    name=item.name,
                    description=item.description,
                    is_mandatory=item.is_mandatory,
                )
                for item in template.items.all()
            ]
        )
    change_application_status(
        application=offer.application, status=ApplicationStatus.ONBOARDING, actor=assigned_to
    )
    return case


@transaction.atomic
def mark_ready_to_hire(*, onboarding: OnboardingCase, actor: User) -> OnboardingCase:
    onboarding = OnboardingCase.objects.select_for_update().get(pk=onboarding.pk)
    incomplete = (
        onboarding.checklist_items.filter(is_mandatory=True)
        .exclude(status__in=[ChecklistStatus.COMPLETED, ChecklistStatus.WAIVED])
        .exists()
    )
    if incomplete:
        raise InvalidTransition("All mandatory onboarding items must be completed or waived.")
    onboarding.status, onboarding.ready_to_hire_at = OnboardingStatus.READY_TO_HIRE, timezone.now()
    onboarding.save(update_fields=["status", "ready_to_hire_at", "updated_at"])
    return onboarding


@transaction.atomic
def verify_background_check(
    *, check: BackgroundCheck, actor: User, summary: str = ""
) -> BackgroundCheck:
    check = BackgroundCheck.objects.select_for_update().get(pk=check.pk)
    check.status, check.verified_by, check.completed_at, check.result_summary = (
        VerificationStatus.VERIFIED,
        actor,
        timezone.now(),
        summary,
    )
    check.save(
        update_fields=["status", "verified_by", "completed_at", "result_summary", "updated_at"]
    )
    return check


@transaction.atomic
def hire_candidate(
    *, onboarding: OnboardingCase, actor: User, employee_number: str | None = None
) -> Employee:
    case = (
        OnboardingCase.objects.select_for_update(of=("self",))
        .select_related(
            "application__candidate",
            "application__vacancy__manpower_requisition",
            "accepted_offer",
            "company",
            "branch",
            "department",
            "designation",
        )
        .get(pk=onboarding.pk)
    )
    application = CandidateApplication.objects.select_for_update().get(pk=case.application_id)
    vacancy = Vacancy.objects.select_for_update().get(pk=application.vacancy_id)
    candidate = application.candidate
    if (
        case.status != OnboardingStatus.READY_TO_HIRE
        or case.accepted_offer.status != OfferStatus.ACCEPTED
    ):
        raise HiringConflict("Accepted offer and READY_TO_HIRE onboarding are required.")
    if application.hired_employee_id or application.status == ApplicationStatus.HIRED:
        raise HiringConflict("This application has already been hired.")
    if (
        vacancy.status not in {VacancyStatus.OPEN}
        or vacancy.positions_filled >= vacancy.number_of_positions
    ):
        raise HiringConflict("Vacancy has no remaining approved position.")
    if (
        case.checklist_items.filter(is_mandatory=True)
        .exclude(status__in=[ChecklistStatus.COMPLETED, ChecklistStatus.WAIVED])
        .exists()
    ):
        raise HiringConflict("Required onboarding checklist items remain incomplete.")
    number = employee_number or case.proposed_employee_number
    if not number:
        raise HiringConflict("An employee number is required.")
    if Employee.objects.filter(company=case.company, employee_number__iexact=number).exists():
        raise HiringConflict("Employee number is already in use.")
    offer = case.accepted_offer
    employee = create_employee(
        actor=actor,
        company=case.company,
        employee_number=number,
        first_name=candidate.first_name,
        middle_name=candidate.middle_name,
        last_name=candidate.last_name,
        father_or_spouse_name=candidate.father_or_spouse_name,
        gender=candidate.gender,
        date_of_birth=candidate.date_of_birth,
        marital_status=candidate.marital_status,
        nationality=candidate.nationality,
        national_identity_number=candidate.national_identity_number or "",
        national_identity_expiry=candidate.national_identity_expiry,
        personal_email=candidate.email,
        mobile_number=candidate.mobile_number,
        alternate_mobile_number=candidate.alternate_mobile_number,
        employee_type=vacancy.employee_type,
        employment_type=offer.employment_type,
        joining_date=offer.proposed_joining_date,
        branch=case.branch,
        department=case.department,
        designation=case.designation,
        notes=f"Hired from application {application.application_number}",
    )
    application.hired_employee = employee
    application.save(update_fields=["hired_employee", "updated_at"])
    change_application_status(application=application, status=ApplicationStatus.HIRED, actor=actor)
    candidate.status = CandidateStatus.HIRED
    candidate.save(update_fields=["status", "updated_at"])
    vacancy.positions_filled += 1
    if vacancy.positions_filled == vacancy.number_of_positions:
        vacancy.status = VacancyStatus.FILLED
    vacancy.save(update_fields=["positions_filled", "status", "updated_at"])
    requisition = vacancy.manpower_requisition
    if requisition:
        filled = (
            Vacancy.objects.filter(manpower_requisition=requisition).aggregate(
                total=models.Sum("positions_filled")
            )["total"]
            or 0
        )
        if requisition.approved_headcount and filled >= requisition.approved_headcount:
            requisition.status = RequisitionStatus.FILLED
            requisition.save(update_fields=["status", "updated_at"])
    case.status, case.hired_at = OnboardingStatus.COMPLETED, timezone.now()
    case.save(update_fields=["status", "hired_at", "updated_at"])
    return employee
