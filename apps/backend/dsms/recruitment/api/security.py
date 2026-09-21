from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import F, Q, QuerySet

from dsms.identity import access
from dsms.identity.models import User

from .. import models as recruitment_models

COMPANY_LOOKUPS: dict[type[models.Model], str] = {
    recruitment_models.ManpowerRequisition: "company",
    recruitment_models.Vacancy: "company",
    recruitment_models.Candidate: "company",
    recruitment_models.CandidateApplication: "company",
    recruitment_models.CandidateScreening: "application__company",
    recruitment_models.Interview: "application__company",
    recruitment_models.CandidateAssessment: "application__company",
    recruitment_models.CandidateReference: "candidate__company",
    recruitment_models.BackgroundCheck: "application__company",
    recruitment_models.CandidateDocument: "candidate__company",
    recruitment_models.EmploymentOffer: "company",
    recruitment_models.OnboardingCase: "company",
    recruitment_models.OnboardingChecklistTemplate: "company",
}

BRANCH_LOOKUPS: dict[type[models.Model], str] = {
    recruitment_models.ManpowerRequisition: "branch",
    recruitment_models.Vacancy: "branch",
    recruitment_models.CandidateApplication: "vacancy__branch",
    recruitment_models.CandidateScreening: "application__vacancy__branch",
    recruitment_models.Interview: "application__vacancy__branch",
    recruitment_models.CandidateAssessment: "application__vacancy__branch",
    recruitment_models.BackgroundCheck: "application__vacancy__branch",
    recruitment_models.EmploymentOffer: "branch",
    recruitment_models.OnboardingCase: "branch",
}

GLOBAL_READ_MODELS = {recruitment_models.OnboardingChecklistTemplate}

CONSISTENCY_FILTERS: dict[type[models.Model], tuple[Q, ...]] = {
    recruitment_models.ManpowerRequisition: (
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id")),
        Q(department__isnull=True) | Q(department__company_id=F("company_id")),
        Q(designation__isnull=True) | Q(designation__company_id=F("company_id")),
        Q(replacement_for_employee__isnull=True)
        | Q(replacement_for_employee__company_id=F("company_id")),
    ),
    recruitment_models.Vacancy: (
        Q(manpower_requisition__isnull=True) | Q(manpower_requisition__company_id=F("company_id")),
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id")),
        Q(department__isnull=True) | Q(department__company_id=F("company_id")),
        Q(designation__company_id=F("company_id")),
    ),
    recruitment_models.Candidate: (
        Q(referred_by_employee__isnull=True) | Q(referred_by_employee__company_id=F("company_id")),
    ),
    recruitment_models.CandidateApplication: (
        Q(candidate__company_id=F("company_id")) | Q(candidate__company__isnull=True),
        Q(vacancy__company_id=F("company_id")),
        Q(hired_employee__isnull=True) | Q(hired_employee__company_id=F("company_id")),
    ),
    recruitment_models.CandidateScreening: (
        Q(application__candidate__company_id=F("application__company_id"))
        | Q(application__candidate__company__isnull=True),
        Q(application__vacancy__company_id=F("application__company_id")),
    ),
    recruitment_models.Interview: (
        Q(application__candidate__company_id=F("application__company_id"))
        | Q(application__candidate__company__isnull=True),
        Q(application__vacancy__company_id=F("application__company_id")),
    ),
    recruitment_models.CandidateAssessment: (
        Q(application__candidate__company_id=F("application__company_id"))
        | Q(application__candidate__company__isnull=True),
        Q(application__vacancy__company_id=F("application__company_id")),
    ),
    recruitment_models.BackgroundCheck: (
        Q(application__candidate__company_id=F("application__company_id"))
        | Q(application__candidate__company__isnull=True),
        Q(application__vacancy__company_id=F("application__company_id")),
    ),
    recruitment_models.CandidateDocument: (
        Q(application__isnull=True) | Q(application__company_id=F("candidate__company_id")),
    ),
    recruitment_models.EmploymentOffer: (
        Q(application__company_id=F("company_id")),
        Q(application__candidate__company_id=F("company_id"))
        | Q(application__candidate__company__isnull=True),
        Q(application__vacancy__company_id=F("company_id")),
        Q(designation__company_id=F("company_id")),
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id")),
        Q(department__isnull=True) | Q(department__company_id=F("company_id")),
    ),
    recruitment_models.OnboardingCase: (
        Q(application__company_id=F("company_id")),
        Q(application__candidate__company_id=F("company_id"))
        | Q(application__candidate__company__isnull=True),
        Q(application__vacancy__company_id=F("company_id")),
        Q(candidate_id=F("application__candidate_id")),
        Q(accepted_offer__application_id=F("application_id")),
        Q(candidate__company_id=F("company_id")) | Q(candidate__company__isnull=True),
        Q(accepted_offer__company_id=F("company_id")),
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id")),
        Q(department__isnull=True) | Q(department__company_id=F("company_id")),
        Q(designation__company_id=F("company_id")),
    ),
    recruitment_models.OnboardingChecklistTemplate: (
        Q(designation__isnull=True) | Q(designation__company_id=F("company_id")),
    ),
}


def _value(instance: Any, lookup: str) -> Any:
    value = instance
    for part in lookup.split("__"):
        value = getattr(value, part, None)
        if value is None:
            return None
    return value


def company_for(instance: models.Model) -> Any:
    return _value(instance, COMPANY_LOOKUPS[type(instance)])


def branch_for(instance: models.Model) -> Any:
    lookup = BRANCH_LOOKUPS.get(type(instance))
    return _value(instance, lookup) if lookup else None


def scoped_queryset(queryset: QuerySet[Any], *, user: User, permission: str) -> QuerySet[Any]:
    model = queryset.model
    if user.is_superuser:
        return queryset
    company_lookup = COMPANY_LOOKUPS[model]
    full_company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    scope = Q(**{f"{company_lookup}_id__in": full_company_ids})
    branch_lookup = BRANCH_LOOKUPS.get(model)
    if branch_lookup:
        branch_ids = access.get_accessible_branch_ids(user, permission=permission)
        scope |= Q(**{f"{branch_lookup}_id__in": branch_ids})
    if model in GLOBAL_READ_MODELS:
        scope |= Q(**{f"{company_lookup}__isnull": True})
    queryset = (
        queryset.filter(scope).filter(**{f"{company_lookup}__is_active": True})
        if model not in GLOBAL_READ_MODELS
        else queryset.filter(scope).filter(
            Q(**{f"{company_lookup}__isnull": True}) | Q(**{f"{company_lookup}__is_active": True})
        )
    )
    for condition in CONSISTENCY_FILTERS.get(model, ()):
        queryset = queryset.filter(condition)
    queryset = queryset.distinct()
    return queryset if queryset.ordered else queryset.order_by("pk")


def scope_kwargs(instance: models.Model) -> dict[str, Any]:
    company = company_for(instance)
    branch = branch_for(instance)
    return {
        "company": company,
        "region": branch.region if branch is not None else None,
        "branch": branch,
        "department": getattr(instance, "department", None),
    }
