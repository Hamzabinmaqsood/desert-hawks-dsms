from __future__ import annotations

from typing import Any

from django.db import models as django_models
from rest_framework import serializers

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation
from dsms.workforce.models import Employee

from .. import models
from .security import COMPANY_LOOKUPS

FIELDS: dict[type[django_models.Model], tuple[str, ...]] = {
    models.ManpowerRequisition: (
        "id",
        "created_at",
        "updated_at",
        "company",
        "branch",
        "department",
        "designation",
        "employee_type",
        "employment_type",
        "requested_headcount",
        "required_by_date",
        "reason",
        "replacement_for_employee",
        "budget_reference",
        "requested_by",
        "status",
        "approved_headcount",
        "approved_by",
        "approved_at",
        "rejection_reason",
    ),
    models.Vacancy: (
        "id",
        "created_at",
        "updated_at",
        "company",
        "manpower_requisition",
        "branch",
        "department",
        "designation",
        "employee_type",
        "employment_type",
        "vacancy_code",
        "title",
        "description",
        "number_of_positions",
        "positions_filled",
        "opening_date",
        "closing_date",
        "minimum_age",
        "maximum_age",
        "minimum_experience_months",
        "minimum_education",
        "location_text",
        "is_public",
        "status",
        "created_by",
    ),
    models.Candidate: (
        "id",
        "created_at",
        "updated_at",
        "candidate_number",
        "company",
        "first_name",
        "middle_name",
        "last_name",
        "father_or_spouse_name",
        "gender",
        "date_of_birth",
        "national_identity_number",
        "national_identity_expiry",
        "nationality",
        "marital_status",
        "mobile_number",
        "alternate_mobile_number",
        "email",
        "current_address",
        "permanent_address",
        "city",
        "province_or_state",
        "source_type",
        "referred_by_employee",
        "status",
        "notes",
    ),
    models.CandidateApplication: (
        "id",
        "created_at",
        "updated_at",
        "application_number",
        "candidate",
        "vacancy",
        "company",
        "status",
        "applied_at",
        "source_type",
        "expected_salary",
        "availability_date",
        "current_employer",
        "current_job_title",
        "total_experience_months",
        "recruiter",
        "rejection_reason",
        "withdrawal_reason",
        "hired_employee",
    ),
    models.CandidateScreening: (
        "id",
        "created_at",
        "updated_at",
        "application",
        "screened_by",
        "screened_at",
        "age_eligible",
        "education_eligible",
        "experience_eligible",
        "identity_available",
        "physically_eligible",
        "communication_rating",
        "notes",
        "decision",
    ),
    models.Interview: (
        "id",
        "created_at",
        "updated_at",
        "application",
        "interview_number",
        "interview_type",
        "scheduled_at",
        "location",
        "status",
        "conducted_at",
        "overall_score",
        "recommendation",
        "remarks",
        "created_by",
    ),
    models.CandidateAssessment: (
        "id",
        "created_at",
        "updated_at",
        "application",
        "assessment_type",
        "assessment_date",
        "maximum_score",
        "obtained_score",
        "result",
        "assessed_by",
        "notes",
    ),
    models.CandidateReference: (
        "id",
        "created_at",
        "updated_at",
        "candidate",
        "name",
        "relationship",
        "organization",
        "designation",
        "mobile_number",
        "email",
        "years_known",
    ),
    models.BackgroundCheck: (
        "id",
        "created_at",
        "updated_at",
        "application",
        "check_type",
        "status",
        "initiated_at",
        "completed_at",
        "verified_by",
        "result_summary",
        "failure_reason",
        "waiver_reason",
    ),
    models.CandidateDocument: (
        "id",
        "created_at",
        "updated_at",
        "candidate",
        "application",
        "document_type",
        "document_number",
        "issue_date",
        "expiry_date",
        "status",
        "uploaded_by",
    ),
    models.EmploymentOffer: (
        "id",
        "created_at",
        "updated_at",
        "application",
        "offer_number",
        "company",
        "designation",
        "branch",
        "department",
        "employment_type",
        "proposed_joining_date",
        "offered_base_salary",
        "probation_months",
        "offer_expiry_date",
        "terms_summary",
        "status",
        "created_by",
        "approved_by",
        "approved_at",
        "issued_at",
        "accepted_at",
        "declined_at",
        "decline_reason",
        "withdrawn_at",
        "withdrawal_reason",
    ),
    models.OnboardingCase: (
        "id",
        "created_at",
        "updated_at",
        "application",
        "candidate",
        "accepted_offer",
        "company",
        "branch",
        "department",
        "designation",
        "proposed_employee_number",
        "proposed_joining_date",
        "status",
        "assigned_to",
        "ready_to_hire_at",
        "hired_at",
    ),
    models.OnboardingChecklistTemplate: (
        "id",
        "created_at",
        "updated_at",
        "is_active",
        "company",
        "code",
        "name",
        "employee_type",
        "designation",
    ),
}

READ_ONLY: dict[type[django_models.Model], tuple[str, ...]] = {
    models.ManpowerRequisition: (
        "id",
        "created_at",
        "updated_at",
        "requested_by",
        "status",
        "approved_headcount",
        "approved_by",
        "approved_at",
        "rejection_reason",
    ),
    models.Vacancy: ("id", "created_at", "updated_at", "positions_filled", "status", "created_by"),
    models.Candidate: ("id", "created_at", "updated_at", "candidate_number", "status"),
    models.CandidateApplication: (
        "id",
        "created_at",
        "updated_at",
        "application_number",
        "status",
        "applied_at",
        "recruiter",
        "hired_employee",
    ),
    models.CandidateScreening: ("id", "created_at", "updated_at", "screened_by", "screened_at"),
    models.Interview: ("id", "created_at", "updated_at", "status", "conducted_at", "created_by"),
    models.CandidateAssessment: ("id", "created_at", "updated_at", "assessed_by"),
    models.CandidateReference: ("id", "created_at", "updated_at"),
    models.BackgroundCheck: (
        "id",
        "created_at",
        "updated_at",
        "status",
        "initiated_at",
        "completed_at",
        "verified_by",
    ),
    models.CandidateDocument: ("id", "created_at", "updated_at", "status", "uploaded_by"),
    models.EmploymentOffer: (
        "id",
        "created_at",
        "updated_at",
        "offer_number",
        "status",
        "created_by",
        "approved_by",
        "approved_at",
        "issued_at",
        "accepted_at",
        "declined_at",
        "withdrawn_at",
    ),
    models.OnboardingCase: (
        "id",
        "created_at",
        "updated_at",
        "status",
        "assigned_to",
        "ready_to_hire_at",
        "hired_at",
    ),
    models.OnboardingChecklistTemplate: ("id", "created_at", "updated_at"),
}

PRIMARY_RELATION: dict[type[django_models.Model], str] = {
    models.CandidateScreening: "application",
    models.Interview: "application",
    models.CandidateAssessment: "application",
    models.CandidateReference: "candidate",
    models.BackgroundCheck: "application",
    models.CandidateDocument: "candidate",
}

TENANT_RELATIONS: dict[type[django_models.Model], tuple[str, ...]] = {
    models.ManpowerRequisition: ("branch", "department", "designation", "replacement_for_employee"),
    models.Vacancy: ("manpower_requisition", "branch", "department", "designation"),
    models.Candidate: ("referred_by_employee",),
    models.CandidateApplication: ("candidate", "vacancy", "hired_employee"),
    models.CandidateScreening: ("application",),
    models.Interview: ("application",),
    models.CandidateAssessment: ("application",),
    models.CandidateReference: ("candidate",),
    models.BackgroundCheck: ("application",),
    models.CandidateDocument: ("candidate", "application"),
    models.EmploymentOffer: ("application", "designation", "branch", "department"),
    models.OnboardingCase: (
        "application",
        "candidate",
        "accepted_offer",
        "branch",
        "department",
        "designation",
    ),
    models.OnboardingChecklistTemplate: ("designation",),
}


def _company_id(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Company):
        return value.pk
    if hasattr(value, "company_id"):
        return value.company_id
    for name in ("application", "candidate"):
        parent = getattr(value, name, None)
        if parent is not None:
            return _company_id(parent)
    return None


class TenantSafeRecruitmentSerializer(serializers.ModelSerializer[Any]):
    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)
        if isinstance(instance, models.Candidate):
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if not isinstance(user, User) or not access.has_permission(
                user=user,
                permission="recruitment.view_candidate_sensitive_data",
                company=instance.company,
            ):
                for field_name in (
                    "national_identity_number",
                    "national_identity_expiry",
                    "date_of_birth",
                    "current_address",
                    "permanent_address",
                ):
                    data.pop(field_name, None)
        if isinstance(instance, models.EmploymentOffer):
            request = self.context.get("request")
            user = getattr(request, "user", None)
            if not isinstance(user, User) or not access.has_permission(
                user=user,
                permission="recruitment.view_offer_salary",
                company=instance.company,
            ):
                data.pop("offered_base_salary", None)
        return data

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not isinstance(user, User) or user.is_superuser:
            return
        view = self.context.get("view")
        permission = view.get_scope_permission() if view is not None else None
        company_ids = access.get_accessible_company_ids(user, permission=permission)
        relation_lookups: dict[type[django_models.Model], str] = {
            Branch: "company_id",
            Department: "company_id",
            Designation: "company_id",
            Employee: "company_id",
            **{model: f"{lookup}_id" for model, lookup in COMPANY_LOOKUPS.items()},
        }
        company_field = self.fields.get("company")
        if isinstance(company_field, serializers.PrimaryKeyRelatedField):
            company_field.queryset = Company.objects.filter(pk__in=company_ids, is_active=True)
        for field in self.fields.values():
            if not isinstance(field, serializers.PrimaryKeyRelatedField) or field.queryset is None:
                continue
            lookup = relation_lookups.get(field.queryset.model)
            if lookup:
                field.queryset = field.queryset.filter(**{f"{lookup}__in": company_ids})

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        model = self.Meta.model
        instance = self.instance
        if any(field.name == "company" for field in model._meta.fields):  # type: ignore[attr-defined]
            company = attrs.get("company", getattr(instance, "company", None))
            if instance is not None and "company" in attrs and attrs["company"] != instance.company:
                raise serializers.ValidationError(
                    {"company": "Company ownership cannot be changed after creation."}
                )
        else:
            primary = PRIMARY_RELATION[model]
            if (
                instance is not None
                and primary in attrs
                and attrs[primary] != getattr(instance, primary)
            ):
                raise serializers.ValidationError(
                    {primary: "Tenant ownership cannot be changed after creation."}
                )
            company = attrs.get(primary, getattr(instance, primary, None))
        company_id = _company_id(company)
        errors: dict[str, str] = {}
        for name in TENANT_RELATIONS.get(model, ()):
            related = attrs.get(name, getattr(instance, name, None))
            related_company_id = _company_id(related)
            if related is not None and related_company_id not in (None, company_id):
                errors[name] = "Must belong to the same company."
        if model is models.CandidateDocument:
            application = attrs.get("application", getattr(instance, "application", None))
            candidate = attrs.get("candidate", getattr(instance, "candidate", None))
            if (
                application is not None
                and candidate is not None
                and application.candidate_id != candidate.pk
            ):
                errors["application"] = "Must belong to the selected candidate."
        if model is models.OnboardingCase:
            application = attrs.get("application", getattr(instance, "application", None))
            candidate = attrs.get("candidate", getattr(instance, "candidate", None))
            offer = attrs.get("accepted_offer", getattr(instance, "accepted_offer", None))
            if (
                application is not None
                and candidate is not None
                and application.candidate_id != candidate.pk
            ):
                errors["candidate"] = "Must match the selected application."
            if (
                application is not None
                and offer is not None
                and offer.application_id != application.pk
            ):
                errors["accepted_offer"] = "Must belong to the selected application."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def serializer_for(model: type[django_models.Model]) -> type[TenantSafeRecruitmentSerializer]:
    meta = type(
        "Meta", (), {"model": model, "fields": FIELDS[model], "read_only_fields": READ_ONLY[model]}
    )
    return type(f"{model.__name__}Serializer", (TenantSafeRecruitmentSerializer,), {"Meta": meta})


ManpowerRequisitionSerializer = serializer_for(models.ManpowerRequisition)
VacancySerializer = serializer_for(models.Vacancy)
CandidateSerializer = serializer_for(models.Candidate)
CandidateApplicationSerializer = serializer_for(models.CandidateApplication)
CandidateScreeningSerializer = serializer_for(models.CandidateScreening)
InterviewSerializer = serializer_for(models.Interview)
CandidateAssessmentSerializer = serializer_for(models.CandidateAssessment)
CandidateReferenceSerializer = serializer_for(models.CandidateReference)
BackgroundCheckSerializer = serializer_for(models.BackgroundCheck)
CandidateDocumentSerializer = serializer_for(models.CandidateDocument)
EmploymentOfferSerializer = serializer_for(models.EmploymentOffer)
OnboardingCaseSerializer = serializer_for(models.OnboardingCase)
OnboardingChecklistTemplateSerializer = serializer_for(models.OnboardingChecklistTemplate)
