from __future__ import annotations

from typing import Any

from django.db import models as django_models
from django.db.models import Q
from rest_framework import serializers

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation
from dsms.workforce.models import Employee

from .. import models
from .security import COMPANY_LOOKUPS

FIELDS: dict[type[django_models.Model], tuple[str, ...]] = {
    models.TrainingCategory: (
        "id",
        "created_at",
        "updated_at",
        "is_active",
        "company",
        "code",
        "name",
        "description",
        "is_system",
        "sort_order",
    ),
    models.TrainingCourse: (
        "id",
        "created_at",
        "updated_at",
        "company",
        "category",
        "code",
        "title",
        "description",
        "objective",
        "delivery_method",
        "duration_hours",
        "validity_months",
        "minimum_pass_percentage",
        "minimum_attendance_percentage",
        "requires_assessment",
        "produces_certificate",
        "is_mandatory_by_default",
        "status",
    ),
    models.TrainingCourseVersion: (
        "id",
        "course",
        "version_number",
        "effective_from",
        "effective_to",
        "syllabus_summary",
        "duration_hours",
        "minimum_pass_percentage",
        "minimum_attendance_percentage",
        "is_current",
        "created_by",
        "created_at",
    ),
    models.QualificationType: (
        "id",
        "created_at",
        "updated_at",
        "is_active",
        "company",
        "code",
        "name",
        "description",
        "category",
        "requires_expiry",
        "is_system",
    ),
    models.EmployeeQualification: (
        "id",
        "created_at",
        "updated_at",
        "employee",
        "company",
        "qualification_type",
        "source",
        "source_training_completion",
        "obtained_on",
        "valid_from",
        "expires_on",
        "status",
        "notes",
        "verified_by",
    ),
    models.TrainingRequirement: (
        "id",
        "created_at",
        "updated_at",
        "is_active",
        "company",
        "code",
        "name",
        "employee_type",
        "designation",
        "department",
        "branch",
        "course",
        "qualification_type",
        "requirement_level",
        "renewal_required",
        "grace_period_days",
        "effective_from",
        "effective_to",
    ),
    models.TrainingRequirementWaiver: (
        "id",
        "created_at",
        "updated_at",
        "employee",
        "training_requirement",
        "valid_from",
        "valid_until",
        "reason",
        "approved_by",
        "revoked_at",
        "revoked_by",
    ),
    models.TrainingVenue: (
        "id",
        "created_at",
        "updated_at",
        "is_active",
        "company",
        "code",
        "name",
        "branch",
        "address",
        "city",
        "capacity",
        "contact_person",
        "phone",
    ),
    models.TrainingInstructor: (
        "id",
        "created_at",
        "updated_at",
        "is_active",
        "company",
        "employee",
        "external_name",
        "external_organization",
        "email",
        "mobile_number",
        "qualifications_summary",
        "is_internal",
    ),
    models.TrainingProgram: (
        "id",
        "created_at",
        "updated_at",
        "is_active",
        "company",
        "code",
        "name",
        "description",
        "employee_type",
        "designation",
    ),
    models.TrainingSession: (
        "id",
        "created_at",
        "updated_at",
        "company",
        "session_number",
        "course",
        "course_version",
        "program",
        "branch",
        "venue",
        "start_datetime",
        "end_datetime",
        "enrollment_deadline",
        "capacity",
        "status",
        "lead_instructor",
        "created_by",
        "notes",
    ),
    models.TrainingEnrollment: (
        "id",
        "created_at",
        "updated_at",
        "session",
        "employee",
        "company",
        "status",
        "enrolled_by",
        "enrolled_at",
        "confirmed_at",
        "notes",
    ),
    models.TrainingAssessment: (
        "id",
        "created_at",
        "updated_at",
        "session",
        "name",
        "assessment_type",
        "maximum_score",
        "passing_score",
        "weight_percentage",
        "assessment_date",
        "is_mandatory",
    ),
    models.EmployeeTrainingAssessmentResult: (
        "id",
        "created_at",
        "updated_at",
        "assessment",
        "enrollment",
        "employee",
        "score",
        "percentage",
        "result",
        "evaluator",
        "evaluated_at",
        "remarks",
    ),
    models.TrainingCompletion: (
        "id",
        "enrollment",
        "employee",
        "course",
        "course_version",
        "session",
        "completed_on",
        "final_percentage",
        "passed",
        "completion_status",
        "approved_by",
        "created_at",
    ),
    models.TrainingCertificate: (
        "id",
        "created_at",
        "updated_at",
        "employee",
        "training_completion",
        "company",
        "certificate_number",
        "qualification_type",
        "employee_document",
        "issued_on",
        "valid_from",
        "expires_on",
        "status",
        "issued_by",
        "revoked_by",
        "revoked_at",
        "revocation_reason",
        "superseded_by",
    ),
    models.ExternalCertification: (
        "id",
        "created_at",
        "updated_at",
        "employee",
        "company",
        "qualification_type",
        "certificate_name",
        "certificate_number",
        "issuing_authority",
        "issued_on",
        "expires_on",
        "verification_status",
        "verified_by",
        "verified_at",
        "employee_document",
    ),
}

COMMON_READ_ONLY = ("id", "created_at", "updated_at")
READ_ONLY: dict[type[django_models.Model], tuple[str, ...]] = {
    model: COMMON_READ_ONLY for model in FIELDS
}
READ_ONLY.update(
    {
        models.TrainingCategory: COMMON_READ_ONLY + ("is_system",),
        models.TrainingCourse: COMMON_READ_ONLY + ("status",),
        models.TrainingCourseVersion: ("id", "created_by", "created_at"),
        models.QualificationType: COMMON_READ_ONLY + ("is_system",),
        models.EmployeeQualification: COMMON_READ_ONLY + ("status", "verified_by"),
        models.TrainingRequirementWaiver: COMMON_READ_ONLY
        + (
            "approved_by",
            "revoked_at",
            "revoked_by",
        ),
        models.TrainingSession: COMMON_READ_ONLY + ("status", "created_by"),
        models.TrainingEnrollment: COMMON_READ_ONLY
        + (
            "status",
            "enrolled_by",
            "enrolled_at",
            "confirmed_at",
        ),
        models.EmployeeTrainingAssessmentResult: COMMON_READ_ONLY
        + (
            "percentage",
            "result",
            "evaluator",
            "evaluated_at",
        ),
        models.TrainingCompletion: FIELDS[models.TrainingCompletion],
        models.TrainingCertificate: FIELDS[models.TrainingCertificate],
        models.ExternalCertification: COMMON_READ_ONLY
        + ("verification_status", "verified_by", "verified_at"),
    }
)

PRIMARY_RELATION: dict[type[django_models.Model], str] = {
    models.TrainingCourseVersion: "course",
    models.TrainingRequirementWaiver: "employee",
    models.TrainingAssessment: "session",
    models.EmployeeTrainingAssessmentResult: "enrollment",
    models.TrainingCompletion: "enrollment",
}

TENANT_RELATIONS: dict[type[django_models.Model], tuple[str, ...]] = {
    models.TrainingCourse: ("category",),
    models.TrainingCourseVersion: ("course",),
    models.QualificationType: ("category",),
    models.EmployeeQualification: ("employee", "qualification_type", "source_training_completion"),
    models.TrainingRequirement: (
        "designation",
        "department",
        "branch",
        "course",
        "qualification_type",
    ),
    models.TrainingRequirementWaiver: ("employee", "training_requirement"),
    models.TrainingVenue: ("branch",),
    models.TrainingInstructor: ("employee",),
    models.TrainingProgram: ("designation",),
    models.TrainingSession: (
        "course",
        "course_version",
        "program",
        "branch",
        "venue",
        "lead_instructor",
    ),
    models.TrainingEnrollment: ("session", "employee"),
    models.TrainingAssessment: ("session",),
    models.EmployeeTrainingAssessmentResult: ("assessment", "enrollment", "employee"),
    models.TrainingCompletion: ("enrollment", "employee", "course", "course_version", "session"),
    models.TrainingCertificate: (
        "employee",
        "training_completion",
        "qualification_type",
        "employee_document",
        "superseded_by",
    ),
    models.ExternalCertification: ("employee", "qualification_type", "employee_document"),
}

ALLOW_GLOBAL_RELATION_FIELDS = {"category", "course", "course_version", "qualification_type"}


def _company_id(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Company):
        return value.pk
    if hasattr(value, "company_id"):
        return value.company_id
    for name in ("employee", "session", "enrollment", "course", "training_requirement"):
        parent = getattr(value, name, None)
        if parent is not None:
            return _company_id(parent)
    return None


class TenantSafeTrainingSerializer(serializers.ModelSerializer[Any]):
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
        for name, field in self.fields.items():
            if not isinstance(field, serializers.PrimaryKeyRelatedField) or field.queryset is None:
                continue
            lookup = relation_lookups.get(field.queryset.model)
            if lookup:
                condition = Q(**{f"{lookup}__in": company_ids})
                if name in ALLOW_GLOBAL_RELATION_FIELDS:
                    condition |= Q(**{f"{lookup}__isnull": True})
                field.queryset = field.queryset.filter(condition)

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
            allowed = (company_id, None) if name in ALLOW_GLOBAL_RELATION_FIELDS else (company_id,)
            if related is not None and related_company_id not in allowed:
                errors[name] = "Must belong to the same company."
        session = attrs.get("session", getattr(instance, "session", None))
        course = attrs.get("course", getattr(instance, "course", None))
        course_version = attrs.get("course_version", getattr(instance, "course_version", None))
        if (
            course_version is not None
            and course is not None
            and course_version.course_id != course.pk
        ):
            errors["course_version"] = "Must belong to the selected course."
        enrollment = attrs.get("enrollment", getattr(instance, "enrollment", None))
        employee = attrs.get("employee", getattr(instance, "employee", None))
        if (
            enrollment is not None
            and employee is not None
            and enrollment.employee_id != employee.pk
        ):
            errors["employee"] = "Must match the enrollment employee."
        assessment = attrs.get("assessment", getattr(instance, "assessment", None))
        if (
            assessment is not None
            and enrollment is not None
            and assessment.session_id != enrollment.session_id
        ):
            errors["assessment"] = "Must belong to the enrollment session."
        if session is not None and enrollment is not None and enrollment.session_id != session.pk:
            errors["enrollment"] = "Must belong to the selected session."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


def serializer_for(model: type[django_models.Model]) -> type[TenantSafeTrainingSerializer]:
    meta = type(
        "Meta", (), {"model": model, "fields": FIELDS[model], "read_only_fields": READ_ONLY[model]}
    )
    return type(f"{model.__name__}Serializer", (TenantSafeTrainingSerializer,), {"Meta": meta})


SERIALIZERS = {model.__name__: serializer_for(model) for model in FIELDS}
