from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import F, Q, QuerySet

from dsms.identity import access
from dsms.identity.models import User

from .. import models as training_models

COMPANY_LOOKUPS: dict[type[models.Model], str] = {
    training_models.TrainingCategory: "company",
    training_models.TrainingCourse: "company",
    training_models.TrainingCourseVersion: "course__company",
    training_models.QualificationType: "company",
    training_models.EmployeeQualification: "company",
    training_models.TrainingRequirement: "company",
    training_models.TrainingRequirementWaiver: "employee__company",
    training_models.TrainingVenue: "company",
    training_models.TrainingInstructor: "company",
    training_models.TrainingProgram: "company",
    training_models.TrainingSession: "company",
    training_models.TrainingEnrollment: "company",
    training_models.TrainingAssessment: "session__company",
    training_models.EmployeeTrainingAssessmentResult: "enrollment__company",
    training_models.TrainingCompletion: "enrollment__company",
    training_models.TrainingCertificate: "company",
    training_models.ExternalCertification: "company",
}

BRANCH_LOOKUPS: dict[type[models.Model], str] = {
    training_models.TrainingRequirement: "branch",
    training_models.TrainingVenue: "branch",
    training_models.TrainingSession: "branch",
    training_models.TrainingEnrollment: "employee__branch",
    training_models.TrainingAssessment: "session__branch",
    training_models.EmployeeTrainingAssessmentResult: "employee__branch",
    training_models.TrainingCompletion: "employee__branch",
    training_models.EmployeeQualification: "employee__branch",
    training_models.TrainingCertificate: "employee__branch",
    training_models.ExternalCertification: "employee__branch",
    training_models.TrainingRequirementWaiver: "employee__branch",
}

GLOBAL_READ_MODELS = {
    training_models.TrainingCategory,
    training_models.TrainingCourse,
    training_models.TrainingCourseVersion,
    training_models.QualificationType,
}

CONSISTENCY_FILTERS: dict[type[models.Model], tuple[Q, ...]] = {
    training_models.TrainingCourse: (
        Q(category__company__isnull=True) | Q(category__company_id=F("company_id")),
    ),
    training_models.QualificationType: (
        Q(category__isnull=True)
        | Q(category__company__isnull=True)
        | Q(category__company_id=F("company_id")),
    ),
    training_models.EmployeeQualification: (
        Q(employee__company_id=F("company_id")),
        Q(qualification_type__company__isnull=True)
        | Q(qualification_type__company_id=F("company_id")),
        Q(source_training_completion__isnull=True)
        | Q(source_training_completion__enrollment__company_id=F("company_id")),
    ),
    training_models.TrainingRequirement: (
        Q(designation__isnull=True) | Q(designation__company_id=F("company_id")),
        Q(department__isnull=True) | Q(department__company_id=F("company_id")),
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id")),
        Q(course__isnull=True)
        | Q(course__company__isnull=True)
        | Q(course__company_id=F("company_id")),
        Q(qualification_type__isnull=True)
        | Q(qualification_type__company__isnull=True)
        | Q(qualification_type__company_id=F("company_id")),
    ),
    training_models.TrainingVenue: (
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id")),
    ),
    training_models.TrainingInstructor: (
        Q(employee__isnull=True) | Q(employee__company_id=F("company_id")),
    ),
    training_models.TrainingProgram: (
        Q(designation__isnull=True) | Q(designation__company_id=F("company_id")),
    ),
    training_models.TrainingSession: (
        Q(course__company__isnull=True) | Q(course__company_id=F("company_id")),
        Q(course_version__course_id=F("course_id")),
        Q(program__isnull=True) | Q(program__company_id=F("company_id")),
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id")),
        Q(venue__isnull=True) | Q(venue__company_id=F("company_id")),
        Q(lead_instructor__isnull=True) | Q(lead_instructor__company_id=F("company_id")),
    ),
    training_models.TrainingEnrollment: (
        Q(session__company_id=F("company_id")),
        Q(employee__company_id=F("company_id")),
    ),
    training_models.EmployeeTrainingAssessmentResult: (
        Q(assessment__session_id=F("enrollment__session_id")),
        Q(employee_id=F("enrollment__employee_id")),
    ),
    training_models.TrainingCompletion: (
        Q(employee_id=F("enrollment__employee_id")),
        Q(session_id=F("enrollment__session_id")),
        Q(course_id=F("session__course_id")),
        Q(course_version_id=F("session__course_version_id")),
    ),
    training_models.TrainingCertificate: (
        Q(employee__company_id=F("company_id")),
        Q(training_completion__isnull=True)
        | Q(training_completion__enrollment__company_id=F("company_id")),
        Q(employee_document__isnull=True) | Q(employee_document__company_id=F("company_id")),
        Q(superseded_by__isnull=True) | Q(superseded_by__company_id=F("company_id")),
        Q(qualification_type__isnull=True)
        | Q(qualification_type__company__isnull=True)
        | Q(qualification_type__company_id=F("company_id")),
    ),
    training_models.ExternalCertification: (
        Q(employee__company_id=F("company_id")),
        Q(employee_document__isnull=True) | Q(employee_document__company_id=F("company_id")),
        Q(qualification_type__company__isnull=True)
        | Q(qualification_type__company_id=F("company_id")),
    ),
    training_models.TrainingRequirementWaiver: (
        Q(training_requirement__company_id=F("employee__company_id")),
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
        scope |= Q(
            **{
                f"{branch_lookup}_id__in": access.get_accessible_branch_ids(
                    user, permission=permission
                )
            }
        )
    if model in GLOBAL_READ_MODELS:
        scope |= Q(**{f"{company_lookup}__isnull": True})
    active_scope = Q(**{f"{company_lookup}__isnull": True}) | Q(
        **{f"{company_lookup}__is_active": True}
    )
    queryset = queryset.filter(scope).filter(active_scope)
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
