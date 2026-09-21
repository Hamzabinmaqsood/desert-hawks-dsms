from typing import Any

from django.db.models import Count, QuerySet

from .enums import ApplicationStatus, OfferStatus, OnboardingStatus, VacancyStatus
from .models import CandidateApplication, EmploymentOffer, OnboardingCase, Vacancy


def recruitment_summary(*, company_ids: list[Any] | None = None) -> dict[str, int]:
    applications = CandidateApplication.objects.all()
    vacancies = Vacancy.objects.all()
    offers = EmploymentOffer.objects.all()
    onboarding = OnboardingCase.objects.all()
    if company_ids is not None:
        applications = applications.filter(company_id__in=company_ids)
        vacancies = vacancies.filter(company_id__in=company_ids)
        offers = offers.filter(company_id__in=company_ids)
        onboarding = onboarding.filter(company_id__in=company_ids)
    return {
        "open_vacancies": vacancies.filter(status=VacancyStatus.OPEN).count(),
        "active_applications": applications.exclude(
            status__in=[
                ApplicationStatus.HIRED,
                ApplicationStatus.REJECTED,
                ApplicationStatus.WITHDRAWN,
                ApplicationStatus.CANCELLED,
            ]
        ).count(),
        "offers_pending": offers.filter(
            status__in=[
                OfferStatus.DRAFT,
                OfferStatus.SUBMITTED,
                OfferStatus.APPROVED,
                OfferStatus.ISSUED,
            ]
        ).count(),
        "onboarding_in_progress": onboarding.filter(status=OnboardingStatus.IN_PROGRESS).count(),
        "ready_to_hire": onboarding.filter(status=OnboardingStatus.READY_TO_HIRE).count(),
        "hired": applications.filter(status=ApplicationStatus.HIRED).count(),
    }


def recruitment_funnel(*, company_ids: list[Any] | None = None) -> QuerySet[Any, Any]:
    queryset = CandidateApplication.objects.all()
    if company_ids is not None:
        queryset = queryset.filter(company_id__in=company_ids)
    return queryset.values("status").annotate(count=Count("id")).order_by("status")


def recruitment_exceptions(*, company_ids: list[Any] | None = None) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    stale = CandidateApplication.objects.filter(
        status=ApplicationStatus.ONBOARDING, onboarding__status=OnboardingStatus.BLOCKED
    )
    expired = EmploymentOffer.objects.filter(
        status=OfferStatus.ISSUED,
        offer_expiry_date__lt=__import__("django").utils.timezone.localdate(),
    )
    if company_ids is not None:
        stale, expired = (
            stale.filter(company_id__in=company_ids),
            expired.filter(company_id__in=company_ids),
        )
    results.extend(
        {"code": "BLOCKED_ONBOARDING", "severity": "HIGH", "object_id": str(item.pk)}
        for item in stale
    )
    results.extend(
        {"code": "EXPIRED_ISSUED_OFFER", "severity": "WARNING", "object_id": str(item.pk)}
        for item in expired
    )
    return results
