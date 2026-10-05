# mypy: disable-error-code="no-untyped-def,type-arg,no-untyped-call,valid-type,misc,name-defined,attr-defined"
# ruff: noqa: E501
from __future__ import annotations

from typing import Any

from django.db.models import F, Q
from django.utils import timezone
from rest_framework import serializers

from dsms.attendance.models import AttendanceRecord
from dsms.contracts.models import SecurityPost, SecuritySite, SiteType
from dsms.deployment.models import DutyAssignment
from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Designation, OperationalZone
from dsms.workforce.models import Employee

from .. import models
from ..tenant_queries import (
    consistent_assignments,
    consistent_corrective_actions,
    consistent_findings,
    consistent_frequency_requirements,
    consistent_inspections,
    consistent_site_visits,
    consistent_templates,
    consistent_visit_plans,
)


def _value(attrs, instance, name):
    return attrs.get(name, getattr(instance, name, None))


def _company_for(model, attrs, instance):
    if model in {models.InspectionResponse}:
        return _value(attrs, instance, "inspection").company
    if model in {models.SiteObservation, models.SiteVisitClientFeedback}:
        return _value(attrs, instance, "site_visit").company
    if model in {
        models.SupervisionAssignment,
        models.SupervisorVisitPlan,
        models.SiteInspection,
        models.InspectionFinding,
        models.CorrectiveAction,
        models.SupervisorDailyReport,
    }:
        branch = _value(attrs, instance, "branch")
        site = _value(attrs, instance, "site")
        if site is not None:
            return site.company
        if branch is not None:
            return branch.company
    return _value(attrs, instance, "company")


class TenantSupervisionSerializer(serializers.ModelSerializer[Any]):
    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        fields = super().get_fields()
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return fields
        verb = "add" if request.method == "POST" else "change"
        model = self.Meta.model
        permission = f"supervision.{verb}_{model._meta.model_name}"
        company_ids = access.get_accessible_company_ids(request.user, permission=permission)
        branch_ids = access.get_accessible_branch_ids(request.user, permission=permission)
        now = timezone.now()
        scoped_users = (
            User.objects.filter(is_active=True)
            .filter(
                Q(is_superuser=True)
                | Q(employee__company_id__in=company_ids)
                | Q(
                    role_assignments__company_id__in=company_ids,
                    role_assignments__is_active=True,
                    role_assignments__starts_at__isnull=True,
                    role_assignments__ends_at__isnull=True,
                )
                | Q(
                    role_assignments__company_id__in=company_ids,
                    role_assignments__is_active=True,
                    role_assignments__starts_at__lte=now,
                    role_assignments__ends_at__isnull=True,
                )
                | Q(
                    role_assignments__company_id__in=company_ids,
                    role_assignments__is_active=True,
                    role_assignments__starts_at__isnull=True,
                    role_assignments__ends_at__gt=now,
                )
                | Q(
                    role_assignments__company_id__in=company_ids,
                    role_assignments__is_active=True,
                    role_assignments__starts_at__lte=now,
                    role_assignments__ends_at__gt=now,
                )
            )
            .distinct()
        )
        relation_querysets = {
            "company": Company.objects.filter(id__in=company_ids, is_active=True),
            "branch": Branch.objects.filter(id__in=branch_ids, company__is_active=True),
            "operational_zone": OperationalZone.objects.filter(
                company_id__in=company_ids, company__is_active=True
            ),
            "site": SecuritySite.objects.filter(
                company_id__in=company_ids,
                managing_branch_id__in=branch_ids,
                company__is_active=True,
                client__company_id=F("company_id"),
                contract__company_id=F("company_id"),
                managing_branch__company_id=F("company_id"),
            ),
            "post": SecurityPost.objects.filter(
                company_id__in=company_ids,
                company__is_active=True,
                client__company_id=F("company_id"),
                site__company_id=F("company_id"),
                client_id=F("site__client_id"),
            ),
            "supervisor": Employee.objects.filter(
                company_id__in=company_ids,
                company__is_active=True,
            ).filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id"))),
            "inspected_employee": Employee.objects.filter(
                company_id__in=company_ids,
                company__is_active=True,
            ).filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id"))),
            "employee": Employee.objects.filter(
                company_id__in=company_ids,
                company__is_active=True,
            ).filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id"))),
            "assigned_to_employee": Employee.objects.filter(
                company_id__in=company_ids,
                company__is_active=True,
            ).filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id"))),
            "assigned_to_user": scoped_users,
            "supervision_assignment": consistent_assignments(
                models.SupervisionAssignment.objects.filter(company_id__in=company_ids)
            ),
            "generated_from_requirement": consistent_frequency_requirements(
                models.VisitFrequencyRequirement.objects.filter(company_id__in=company_ids)
            ),
            "visit_plan": consistent_visit_plans(
                models.SupervisorVisitPlan.objects.filter(company_id__in=company_ids)
            ),
            "site_visit": consistent_site_visits(
                models.SiteVisit.objects.filter(company_id__in=company_ids)
            ),
            "template": consistent_templates(
                models.InspectionTemplate.objects.filter(
                    Q(company__isnull=True) | Q(company_id__in=company_ids)
                )
            ),
            "inspection": consistent_inspections(
                models.SiteInspection.objects.filter(company_id__in=company_ids)
            ),
            "finding": consistent_findings(
                models.InspectionFinding.objects.filter(company_id__in=company_ids)
            ),
            "corrective_action": consistent_corrective_actions(
                models.CorrectiveAction.objects.filter(company_id__in=company_ids)
            ),
            "expected_duty_assignment": DutyAssignment.objects.filter(
                duty_shift__company_id__in=company_ids,
                duty_shift__company__is_active=True,
            ),
            "attendance_record": AttendanceRecord.objects.filter(
                company_id__in=company_ids, company__is_active=True
            ),
            "site_type": SiteType.objects.filter(
                Q(company__isnull=True) | Q(company_id__in=company_ids)
            ),
            "designation": Designation.objects.filter(company_id__in=company_ids),
        }
        for name, queryset in relation_querysets.items():
            field = fields.get(name)
            if isinstance(field, serializers.PrimaryKeyRelatedField) and not field.read_only:
                field.queryset = queryset
        return fields

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)
        model = self.Meta.model
        current = self.instance
        if (
            current is not None
            and "company" in attrs
            and getattr(attrs["company"], "pk", None) != getattr(current, "company_id", None)
        ):
            raise serializers.ValidationError({"company": "Company cannot be changed."})
        company = _company_for(model, attrs, current)
        request = self.context.get("request")
        if model is models.InspectionTemplate and company is None:
            if not request or not request.user.is_superuser:
                raise serializers.ValidationError(
                    {"company": "Only platform administrators may mutate global templates."}
                )
            site_type = _value(attrs, current, "site_type")
            designation = _value(attrs, current, "designation")
            if site_type is not None and site_type.company_id is not None:
                raise serializers.ValidationError(
                    {"site_type": "Global templates require a global Site Type."}
                )
            if designation is not None:
                raise serializers.ValidationError(
                    {"designation": "Global templates cannot reference a tenant Designation."}
                )
            return attrs
        if not isinstance(company, Company) or not company.is_active:
            raise serializers.ValidationError({"company": "An active Company is required."})
        errors: dict[str, str] = {}
        branch = _value(attrs, current, "branch")
        site = _value(attrs, current, "site")
        post = _value(attrs, current, "post")
        supervisor = _value(attrs, current, "supervisor")
        if branch is not None and branch.company_id != company.id:
            errors["branch"] = "Branch must belong to Company."
        if site is not None and (
            site.company_id != company.id
            or site.client.company_id != company.id
            or site.contract.company_id != company.id
            or site.managing_branch.company_id != company.id
            or (branch is not None and site.managing_branch_id != branch.id)
        ):
            errors["site"] = "Site must be tenant-consistent with Company and Branch."
        if post is not None and (
            post.company_id != company.id
            or post.client.company_id != company.id
            or site is None
            or post.site_id != site.id
            or post.client_id != site.client_id
        ):
            errors["post"] = "Post must belong to the resulting Site and Company."
        if supervisor is not None and (
            supervisor.company_id != company.id
            or (supervisor.branch_id is not None and supervisor.branch.company_id != company.id)
        ):
            errors["supervisor"] = "Supervisor must belong to Company."
        if model is models.InspectionTemplate:
            site_type = _value(attrs, current, "site_type")
            designation = _value(attrs, current, "designation")
            if site_type is not None and site_type.company_id not in {None, company.id}:
                errors["site_type"] = "Site Type belongs to another Company."
            if designation is not None and designation.company_id != company.id:
                errors["designation"] = "Designation belongs to another Company."
        zone = _value(attrs, current, "operational_zone")
        if zone is not None and (
            zone.company_id != company.id or (branch is not None and zone.branch_id != branch.id)
        ):
            errors["operational_zone"] = "Operational zone must belong to Branch and Company."
        if model is models.SupervisorVisitPlan:
            assignment = _value(attrs, current, "supervision_assignment")
            requirement = _value(attrs, current, "generated_from_requirement")
            if assignment is not None and (
                assignment.company_id != company.id
                or assignment.supervisor_id != supervisor.id
                or assignment.branch_id != branch.id
            ):
                errors["supervision_assignment"] = "Assignment does not match the visit plan."
            if requirement is not None and requirement.company_id != company.id:
                errors["generated_from_requirement"] = "Requirement belongs to another Company."
        if model is models.SiteInspection:
            visit = _value(attrs, current, "site_visit")
            template = _value(attrs, current, "template")
            employee = _value(attrs, current, "inspected_employee")
            if visit.company_id != company.id or visit.site_id != site.id:
                errors["site_visit"] = "Visit does not match Company and Site."
            if template.company_id not in {None, company.id}:
                errors["template"] = "Template belongs to another Company."
            if employee is not None and (
                employee.company_id != company.id
                or (employee.branch_id is not None and employee.branch.company_id != company.id)
            ):
                errors["inspected_employee"] = "Employee belongs to another Company."
        if model is models.InspectionResponse:
            inspection = _value(attrs, current, "inspection")
            item = _value(attrs, current, "template_item")
            option = _value(attrs, current, "selected_option")
            if item.section.template_id != inspection.template_id:
                errors["template_item"] = "Checklist item does not belong to the template."
            if option is not None and option.item_id != item.id:
                errors["selected_option"] = "Option does not belong to the checklist item."
        if model is models.InspectionFinding:
            inspection = _value(attrs, current, "inspection")
            employee = _value(attrs, current, "employee")
            item = _value(attrs, current, "template_item")
            if inspection.company_id != company.id or inspection.site_id != site.id:
                errors["inspection"] = "Inspection does not match Company and Site."
            if employee is not None and (
                employee.company_id != company.id
                or (employee.branch_id is not None and employee.branch.company_id != company.id)
            ):
                errors["employee"] = "Employee belongs to another Company."
            if item is not None and item.section.template_id != inspection.template_id:
                errors["template_item"] = "Checklist item does not match the inspection template."
        if model is models.CorrectiveAction:
            finding = _value(attrs, current, "finding")
            assignee = _value(attrs, current, "assigned_to_employee")
            assigned_user = _value(attrs, current, "assigned_to_user")
            if finding.company_id != company.id or finding.site_id != site.id:
                errors["finding"] = "Finding does not match Company and Site."
            if assignee is not None and (
                assignee.company_id != company.id
                or (assignee.branch_id is not None and assignee.branch.company_id != company.id)
            ):
                errors["assigned_to_employee"] = "Assignee belongs to another Company."
            if assigned_user is not None and not (
                assigned_user.is_superuser
                or Employee.objects.filter(user=assigned_user, company=company).exists()
                or assigned_user.role_assignments.filter(
                    company=company,
                    is_active=True,
                )
                .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=timezone.now()))
                .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=timezone.now()))
                .exists()
            ):
                errors["assigned_to_user"] = "Assigned user does not belong to Company."
        if model is models.SiteObservation:
            visit = _value(attrs, current, "site_visit")
            if visit.site_id != site.id:
                errors["site_visit"] = "Visit does not match the observation Site."
        if model is models.SupervisorDailyReport and supervisor.company_id != company.id:
            errors["supervisor"] = "Supervisor belongs to another Company."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data: dict[str, object]):
        model = self.Meta.model
        request = self.context["request"]
        if model in {
            models.SupervisionAssignment,
            models.SupervisorVisitPlan,
            models.SiteInspection,
            models.InspectionFinding,
            models.CorrectiveAction,
            models.SiteObservation,
            models.SiteVisitClientFeedback,
            models.SupervisorDailyReport,
        }:
            company = _company_for(model, validated_data, None)
            if hasattr(model, "company"):
                validated_data["company"] = company
        defaults: dict[str, object] = {}
        if model in {models.SupervisionAssignment, models.SupervisorVisitPlan}:
            defaults = {"created_by": request.user}
        elif model is models.SiteInspection:
            defaults = {
                "created_by": request.user,
                "started_at": timezone.now(),
                "template_version": validated_data["template"].version_number,
            }
        elif model is models.InspectionFinding:
            defaults = {
                "identified_by": request.user,
                "identified_at": timezone.now(),
            }
        elif model is models.CorrectiveAction:
            defaults = {
                "assigned_by": request.user,
                "assigned_at": timezone.now(),
            }
        elif model is models.SiteObservation:
            defaults = {"created_by": request.user}
        elif model is models.SiteVisitClientFeedback:
            defaults = {"captured_by": request.user}
        return model.objects.create(**validated_data, **defaults)


FIELD_MAP = {
    models.SupervisionAssignment: (
        "id",
        "company",
        "supervisor",
        "scope_type",
        "branch",
        "operational_zone",
        "site",
        "effective_from",
        "effective_to",
        "status",
        "is_primary",
        "created_by",
        "approved_by",
        "approved_at",
        "notes",
        "created_at",
        "updated_at",
    ),
    models.VisitFrequencyRequirement: (
        "id",
        "company",
        "branch",
        "operational_zone",
        "site",
        "name",
        "visits_required",
        "frequency_period",
        "effective_from",
        "effective_to",
        "priority",
        "is_active",
        "created_at",
        "updated_at",
    ),
    models.SupervisorVisitPlan: (
        "id",
        "company",
        "supervisor",
        "supervision_assignment",
        "branch",
        "site",
        "planned_date",
        "planned_start_at",
        "planned_end_at",
        "priority",
        "purpose",
        "status",
        "generated_from_requirement",
        "created_by",
        "approved_by",
        "approved_at",
        "cancellation_reason",
        "created_at",
        "updated_at",
    ),
    models.SiteVisit: (
        "id",
        "company",
        "supervisor",
        "visit_plan",
        "branch",
        "site",
        "started_at",
        "ended_at",
        "status",
        "verification_method",
        "verification_result",
        "arrival_latitude",
        "arrival_longitude",
        "arrival_accuracy_meters",
        "arrival_distance_from_site_meters",
        "departure_latitude",
        "departure_longitude",
        "departure_accuracy_meters",
        "visit_summary",
        "client_contact_met",
        "client_contact_name",
        "created_at",
        "updated_at",
    ),
    models.InspectionTemplate: (
        "id",
        "company",
        "code",
        "name",
        "scope",
        "description",
        "site_type",
        "designation",
        "employee_type",
        "is_system",
        "is_active",
        "version_number",
        "effective_from",
        "effective_to",
        "created_at",
        "updated_at",
    ),
    models.SiteInspection: (
        "id",
        "company",
        "site_visit",
        "site",
        "post",
        "inspected_employee",
        "template",
        "template_version",
        "scope",
        "status",
        "started_at",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "result",
        "total_score",
        "maximum_score",
        "percentage",
        "summary",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.InspectionResponse: (
        "id",
        "inspection",
        "template_item",
        "boolean_value",
        "text_value",
        "numeric_value",
        "selected_option",
        "score",
        "is_noncompliant",
        "comment",
        "created_at",
        "updated_at",
    ),
    models.GuardObservation: (
        "id",
        "company",
        "site_visit",
        "site",
        "post",
        "employee",
        "expected_duty_assignment",
        "attendance_record",
        "observation_status",
        "observed_at",
        "uniform_compliant",
        "grooming_compliant",
        "identity_badge_available",
        "alert_and_attentive",
        "understands_post_instructions",
        "required_equipment_available",
        "remarks",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.InspectionFinding: (
        "id",
        "company",
        "inspection",
        "site",
        "post",
        "employee",
        "template_item",
        "title",
        "description",
        "severity",
        "status",
        "requires_corrective_action",
        "requires_incident_escalation",
        "target_resolution_date",
        "identified_by",
        "identified_at",
        "acknowledged_by",
        "acknowledged_at",
        "resolved_at",
        "resolution_summary",
        "created_at",
        "updated_at",
    ),
    models.CorrectiveAction: (
        "id",
        "company",
        "finding",
        "site",
        "post",
        "title",
        "description",
        "priority",
        "assigned_to_user",
        "assigned_to_employee",
        "assigned_by",
        "assigned_at",
        "due_at",
        "status",
        "started_at",
        "completed_at",
        "completion_notes",
        "verification_required",
        "verified_by",
        "verified_at",
        "verification_notes",
        "created_at",
        "updated_at",
    ),
    models.SiteObservation: (
        "id",
        "site_visit",
        "site",
        "post",
        "category",
        "title",
        "description",
        "severity",
        "requires_follow_up",
        "created_by",
        "created_at",
    ),
    models.SiteVisitClientFeedback: (
        "id",
        "site_visit",
        "contact_name",
        "designation",
        "feedback",
        "satisfaction_rating",
        "requires_follow_up",
        "captured_by",
        "created_at",
    ),
    models.SupervisorDailyReport: (
        "id",
        "company",
        "supervisor",
        "report_date",
        "branch",
        "status",
        "summary",
        "key_issues",
        "unresolved_items",
        "support_required",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "review_comments",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
    ),
}

READ_ONLY = {
    models.SupervisionAssignment: (
        "id",
        "company",
        "status",
        "created_by",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
    ),
    models.VisitFrequencyRequirement: ("id", "created_at", "updated_at"),
    models.SupervisorVisitPlan: (
        "id",
        "company",
        "status",
        "created_by",
        "approved_by",
        "approved_at",
        "cancellation_reason",
        "created_at",
        "updated_at",
    ),
    models.SiteVisit: FIELD_MAP[models.SiteVisit],
    models.InspectionTemplate: ("id", "is_system", "created_at", "updated_at"),
    models.SiteInspection: (
        "id",
        "company",
        "template_version",
        "status",
        "started_at",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "result",
        "total_score",
        "maximum_score",
        "percentage",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.InspectionResponse: ("id", "score", "is_noncompliant", "created_at", "updated_at"),
    models.GuardObservation: FIELD_MAP[models.GuardObservation],
    models.InspectionFinding: (
        "id",
        "company",
        "site",
        "status",
        "identified_by",
        "identified_at",
        "acknowledged_by",
        "acknowledged_at",
        "resolved_at",
        "resolution_summary",
        "created_at",
        "updated_at",
    ),
    models.CorrectiveAction: (
        "id",
        "company",
        "site",
        "assigned_by",
        "assigned_at",
        "status",
        "started_at",
        "completed_at",
        "completion_notes",
        "verified_by",
        "verified_at",
        "verification_notes",
        "created_at",
        "updated_at",
    ),
    models.SiteObservation: ("id", "created_by", "created_at"),
    models.SiteVisitClientFeedback: ("id", "captured_by", "created_at"),
    models.SupervisorDailyReport: (
        "id",
        "company",
        "status",
        "submitted_at",
        "reviewed_by",
        "reviewed_at",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
    ),
}


def serializer_for(model_class):
    class Serializer(TenantSupervisionSerializer):
        class Meta:
            model = model_class
            fields = FIELD_MAP[model_class]
            read_only_fields = READ_ONLY[model_class]

    Serializer.__name__ = f"{model_class.__name__}Serializer"
    Serializer.__qualname__ = Serializer.__name__
    return Serializer


SERIALIZERS = {model.__name__: serializer_for(model) for model in FIELD_MAP}


class FieldEvidenceSerializer(serializers.ModelSerializer[models.FieldEvidence]):
    """Private, immutable metadata only; the storage path is never published."""

    class Meta:
        model = models.FieldEvidence
        fields = (
            "id",
            "company",
            "site_visit",
            "inspection",
            "finding",
            "corrective_action",
            "original_filename",
            "file_size",
            "mime_type",
            "sha256_hash",
            "caption",
            "captured_at",
            "uploaded_by",
            "created_at",
        )
        read_only_fields = fields


SERIALIZERS["FieldEvidence"] = FieldEvidenceSerializer


class SiteVisitSerializer(SERIALIZERS["SiteVisit"]):
    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not request or not access.has_permission(
            user=request.user,
            permission="supervision.view_sensitive_visit_location",
            company=instance.company,
            branch=instance.branch,
        ):
            for field in (
                "arrival_latitude",
                "arrival_longitude",
                "departure_latitude",
                "departure_longitude",
                "arrival_accuracy_meters",
                "departure_accuracy_meters",
            ):
                data.pop(field, None)
        return data


SERIALIZERS["SiteVisit"] = SiteVisitSerializer
