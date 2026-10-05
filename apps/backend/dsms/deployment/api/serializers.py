# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,no-untyped-call,operator"
# ruff: noqa: E501
from __future__ import annotations

from typing import Any

from django.db.models import F, Q
from rest_framework import serializers

from dsms.contracts.models import (
    Client,
    SecurityPost,
    SecuritySite,
    ServiceContract,
    StaffingRequirement,
)
from dsms.identity import access
from dsms.organization.models import Branch, Company, Designation, OperationalZone
from dsms.workforce.models import Employee

from .. import models
from ..enums import ReplacementPriority
from ..tenant_queries import (
    consistent_duty_assignments,
    consistent_duty_shifts,
    consistent_employee_deployments,
    consistent_employees,
    consistent_pools,
    consistent_posts,
    consistent_rosters,
    consistent_sites,
    consistent_staffing_requirements,
)


def _value(attrs, instance, name):
    return attrs.get(name, getattr(instance, name, None))


def _company_for(model, attrs, instance):
    if model is models.EmployeeDeployment:
        return _value(attrs, instance, "site").company
    if model is models.DeploymentPool:
        return _value(attrs, instance, "branch").company
    if model is models.DeploymentPoolMembership:
        return _value(attrs, instance, "pool").company
    if model is models.RosterPeriod:
        return _value(attrs, instance, "branch").company
    if model is models.DutyShift:
        return _value(attrs, instance, "roster_period").company
    if model is models.EmployeeScheduleBlock:
        return _value(attrs, instance, "employee").company
    return _value(attrs, instance, "company")


class TenantDeploymentSerializer(serializers.ModelSerializer[Any]):
    """Constrain writable relations and validate the complete resulting graph."""

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        fields = super().get_fields()
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return fields
        verb = "add" if request.method == "POST" else "change"
        model = self.Meta.model
        permission = f"deployment.{verb}_{model._meta.model_name}"
        company_ids = access.get_accessible_company_ids(request.user, permission=permission)
        full_company_ids = access.get_fully_accessible_company_ids(
            request.user, permission=permission
        )
        branch_ids = access.get_accessible_branch_ids(request.user, permission=permission)
        relation_querysets = {
            "company": Company.objects.filter(id__in=company_ids, is_active=True),
            "branch": Branch.objects.filter(id__in=branch_ids, company__is_active=True),
            "managing_branch": Branch.objects.filter(id__in=branch_ids, company__is_active=True),
            "operational_zone": OperationalZone.objects.filter(
                branch_id__in=branch_ids,
                company__is_active=True,
                branch__company_id=F("company_id"),
            ),
            "employee": consistent_employees(Employee.objects.filter(company_id__in=company_ids)),
            "requested_employee": consistent_employees(
                Employee.objects.filter(company_id__in=company_ids)
            ),
            "replacement_employee": consistent_employees(
                Employee.objects.filter(company_id__in=company_ids)
            ),
            "client": Client.objects.filter(company_id__in=company_ids, company__is_active=True),
            "contract": ServiceContract.objects.filter(
                company_id__in=company_ids,
                company__is_active=True,
                client__company_id=F("company_id"),
            ),
            "site": consistent_sites(
                SecuritySite.objects.filter(managing_branch_id__in=branch_ids)
            ),
            "post": consistent_posts(
                SecurityPost.objects.filter(site__managing_branch_id__in=branch_ids)
            ),
            "primary_post": consistent_posts(
                SecurityPost.objects.filter(site__managing_branch_id__in=branch_ids)
            ),
            "pool": consistent_pools(
                models.DeploymentPool.objects.filter(branch_id__in=branch_ids)
            ),
            "roster_period": consistent_rosters(
                models.RosterPeriod.objects.filter(branch_id__in=branch_ids)
            ),
            "staffing_requirement": consistent_staffing_requirements(
                StaffingRequirement.objects.filter(site__managing_branch_id__in=branch_ids)
            ),
            "shift_template": models.ShiftTemplate.objects.filter(
                Q(branch_id__in=branch_ids)
                | Q(branch__isnull=True, company_id__in=full_company_ids)
            ),
            "designation": Designation.objects.filter(company_id__in=company_ids),
            "duty_shift": consistent_duty_shifts(
                models.DutyShift.objects.filter(branch_id__in=branch_ids)
            ),
            "deployment": consistent_employee_deployments(
                models.EmployeeDeployment.objects.filter(managing_branch_id__in=branch_ids)
            ),
            "original_assignment": consistent_duty_assignments(
                models.DutyAssignment.objects.filter(duty_shift__branch_id__in=branch_ids)
            ),
            "replaces_assignment": consistent_duty_assignments(
                models.DutyAssignment.objects.filter(duty_shift__branch_id__in=branch_ids)
            ),
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
        company = _company_for(model, attrs, current)
        if not isinstance(company, Company) or not company.is_active:
            raise serializers.ValidationError({"company": "An active Company is required."})
        if current is not None and hasattr(current, "company_id"):
            if current.company_id != company.id:
                raise serializers.ValidationError({"company": "Company cannot be changed."})
            if "company" in attrs and getattr(attrs["company"], "pk", None) != current.company_id:
                raise serializers.ValidationError({"company": "Company cannot be changed."})

        errors: dict[str, str] = {}
        if model is models.EmployeeDeployment:
            employee = _value(attrs, current, "employee")
            client = _value(attrs, current, "client")
            contract = _value(attrs, current, "contract")
            site = _value(attrs, current, "site")
            post = _value(attrs, current, "primary_post")
            branch = _value(attrs, current, "managing_branch")
            if employee.company_id != company.id:
                errors["employee"] = "Employee belongs to another Company."
            if client.company_id != company.id:
                errors["client"] = "Client belongs to another Company."
            if contract.company_id != company.id or contract.client_id != client.id:
                errors["contract"] = "Contract does not match Company and Client."
            if (
                site.company_id != company.id
                or site.client_id != client.id
                or site.contract_id != contract.id
                or site.managing_branch_id != branch.id
            ):
                errors["site"] = "Site does not match the deployment hierarchy."
            if branch.company_id != company.id:
                errors["managing_branch"] = "Branch belongs to another Company."
            if post is not None and (
                post.company_id != company.id
                or post.client_id != client.id
                or post.site_id != site.id
            ):
                errors["primary_post"] = "Primary Post does not belong to the deployment Site."
        elif model is models.DeploymentPool:
            branch = _value(attrs, current, "branch")
            zone = _value(attrs, current, "operational_zone")
            if branch.company_id != company.id:
                errors["branch"] = "Branch belongs to another Company."
            if zone is not None and (zone.company_id != company.id or zone.branch_id != branch.id):
                errors["operational_zone"] = "Operational Zone does not match Branch and Company."
        elif model is models.DeploymentPoolMembership:
            pool = _value(attrs, current, "pool")
            employee = _value(attrs, current, "employee")
            if employee.company_id != pool.company_id:
                errors["employee"] = "Employee belongs to another Company."
        elif model is models.ShiftTemplate:
            branch = _value(attrs, current, "branch")
            if branch is not None and branch.company_id != company.id:
                errors["branch"] = "Branch belongs to another Company."
        elif model is models.RosterPeriod:
            branch = _value(attrs, current, "branch")
            start = _value(attrs, current, "period_start")
            end = _value(attrs, current, "period_end")
            if branch.company_id != company.id:
                errors["branch"] = "Branch belongs to another Company."
            if start and end and end < start:
                errors["period_end"] = "End cannot precede start."
        elif model is models.DutyShift:
            roster = _value(attrs, current, "roster_period")
            branch = _value(attrs, current, "branch") or roster.branch
            client = _value(attrs, current, "client")
            contract = _value(attrs, current, "contract")
            site = _value(attrs, current, "site")
            post = _value(attrs, current, "post")
            requirement = _value(attrs, current, "staffing_requirement")
            template = _value(attrs, current, "shift_template")
            designation = _value(attrs, current, "designation")
            starts = _value(attrs, current, "starts_at")
            ends = _value(attrs, current, "ends_at")
            if roster.company_id != company.id or roster.branch_id != branch.id:
                errors["roster_period"] = "Roster does not match Company and Branch."
            if branch.company_id != company.id:
                errors["branch"] = "Branch belongs to another Company."
            if client.company_id != company.id:
                errors["client"] = "Client belongs to another Company."
            if contract.company_id != company.id or contract.client_id != client.id:
                errors["contract"] = "Contract does not match Company and Client."
            if (
                site.company_id != company.id
                or site.client_id != client.id
                or site.contract_id != contract.id
                or site.managing_branch_id != branch.id
            ):
                errors["site"] = "Site does not match the shift hierarchy."
            if (
                post.company_id != company.id
                or post.client_id != client.id
                or post.site_id != site.id
            ):
                errors["post"] = "Post does not belong to the shift Site."
            if requirement is not None and (
                requirement.company_id != company.id
                or requirement.contract_id != contract.id
                or requirement.site_id != site.id
                or requirement.post_id != post.id
            ):
                errors["staffing_requirement"] = "Staffing Requirement does not match the shift."
            if template is not None and (
                template.company_id != company.id
                or (template.branch_id is not None and template.branch_id != branch.id)
            ):
                errors["shift_template"] = "Shift Template does not match Company and Branch."
            if designation is not None and designation.company_id != company.id:
                errors["designation"] = "Designation belongs to another Company."
            if starts and ends and ends <= starts:
                errors["ends_at"] = "Shift end must be after its start."
        elif model is models.EmployeeScheduleBlock:
            employee = _value(attrs, current, "employee")
            starts = _value(attrs, current, "starts_at")
            ends = _value(attrs, current, "ends_at")
            if employee.company_id != company.id:
                errors["employee"] = "Employee belongs to another Company."
            if starts and ends and ends <= starts:
                errors["ends_at"] = "Block end must be after its start."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data: dict[str, object]):
        model = self.Meta.model
        request = self.context["request"]
        if model in {
            models.EmployeeDeployment,
            models.DeploymentPool,
            models.RosterPeriod,
            models.DutyShift,
            models.EmployeeScheduleBlock,
        }:
            validated_data["company"] = _company_for(model, validated_data, None)
        if model is models.DutyShift:
            validated_data["branch"] = validated_data["roster_period"].branch
        defaults: dict[str, object] = {}
        if model in {models.EmployeeDeployment, models.RosterPeriod, models.EmployeeScheduleBlock}:
            defaults["created_by"] = request.user
        return model.objects.create(**validated_data, **defaults)


class EmployeeActionSerializer(serializers.Serializer):
    employee = serializers.UUIDField()


class ReplacementRequestActionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=30, default="OTHER")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    priority = serializers.ChoiceField(choices=ReplacementPriority.choices, default="NORMAL")


FIELD_MAP = {
    models.EmployeeDeployment: (
        "id",
        "company",
        "employee",
        "client",
        "contract",
        "site",
        "primary_post",
        "managing_branch",
        "deployment_type",
        "effective_from",
        "effective_to",
        "status",
        "is_primary",
        "reason",
        "created_by",
        "approved_by",
        "activated_at",
        "ended_at",
        "created_at",
        "updated_at",
    ),
    models.DeploymentPool: (
        "id",
        "company",
        "branch",
        "operational_zone",
        "code",
        "name",
        "description",
        "is_active",
        "created_at",
        "updated_at",
    ),
    models.DeploymentPoolMembership: (
        "id",
        "pool",
        "employee",
        "effective_from",
        "effective_to",
        "priority",
        "is_active",
        "created_at",
        "updated_at",
    ),
    models.ShiftTemplate: (
        "id",
        "company",
        "branch",
        "code",
        "name",
        "start_time",
        "end_time",
        "crosses_midnight",
        "planned_break_minutes",
        "nominal_hours",
        "description",
        "is_active",
        "created_at",
        "updated_at",
    ),
    models.SchedulingPolicy: (
        "id",
        "company",
        "name",
        "minimum_rest_hours",
        "maximum_planned_hours_per_day",
        "maximum_planned_hours_per_week",
        "maximum_consecutive_duty_days",
        "overtime_warning_hours_per_week",
        "allow_cross_branch_deployment",
        "allow_readiness_warning_assignment",
        "allow_overtime_assignment",
        "require_published_roster_confirmation",
        "is_active",
        "created_at",
        "updated_at",
    ),
    models.RosterPeriod: (
        "id",
        "company",
        "branch",
        "roster_number",
        "name",
        "period_start",
        "period_end",
        "status",
        "version_number",
        "generated_at",
        "generated_by",
        "submitted_by",
        "submitted_at",
        "approved_by",
        "approved_at",
        "published_by",
        "published_at",
        "locked_by",
        "locked_at",
        "notes",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.DutyShift: (
        "id",
        "roster_period",
        "company",
        "branch",
        "client",
        "contract",
        "site",
        "post",
        "staffing_requirement",
        "shift_template",
        "duty_date",
        "starts_at",
        "ends_at",
        "required_headcount",
        "employee_type",
        "designation",
        "armed_required",
        "supervisor_required",
        "is_adhoc",
        "adhoc_reason",
        "status",
        "created_at",
        "updated_at",
    ),
    models.DutyAssignment: (
        "id",
        "duty_shift",
        "employee",
        "deployment",
        "assignment_type",
        "status",
        "assigned_by",
        "assigned_at",
        "confirmed_at",
        "replaces_assignment",
        "replacement_reason",
        "notes",
        "created_at",
        "updated_at",
    ),
    models.EmployeeScheduleBlock: (
        "id",
        "employee",
        "company",
        "block_type",
        "starts_at",
        "ends_at",
        "reason",
        "source_reference",
        "created_by",
        "is_active",
        "created_at",
        "updated_at",
    ),
    models.ReplacementRequest: (
        "id",
        "company",
        "duty_shift",
        "original_assignment",
        "requested_employee",
        "replacement_employee",
        "reason",
        "description",
        "priority",
        "status",
        "requested_by",
        "requested_at",
        "assigned_by",
        "approved_by",
        "completed_at",
        "created_at",
        "updated_at",
    ),
    models.RosterChangeEvent: (
        "id",
        "roster_period",
        "duty_shift",
        "duty_assignment",
        "change_type",
        "actor",
        "reason",
        "previous_employee",
        "new_employee",
        "created_at",
    ),
    models.RosterAvailabilityConflict: (
        "id",
        "company",
        "duty_assignment",
        "leave_request",
        "conflict_type",
        "status",
        "detected_at",
        "replacement_request",
        "resolved_at",
        "created_at",
        "updated_at",
    ),
}


READ_ONLY = {
    models.EmployeeDeployment: (
        "id",
        "company",
        "status",
        "created_by",
        "approved_by",
        "activated_at",
        "ended_at",
        "created_at",
        "updated_at",
    ),
    models.DeploymentPool: ("id", "company", "created_at", "updated_at"),
    models.DeploymentPoolMembership: ("id", "created_at", "updated_at"),
    models.ShiftTemplate: ("id", "created_at", "updated_at"),
    models.SchedulingPolicy: ("id", "created_at", "updated_at"),
    models.RosterPeriod: (
        "id",
        "company",
        "status",
        "version_number",
        "generated_at",
        "generated_by",
        "submitted_by",
        "submitted_at",
        "approved_by",
        "approved_at",
        "published_by",
        "published_at",
        "locked_by",
        "locked_at",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.DutyShift: ("id", "company", "branch", "status", "created_at", "updated_at"),
    models.DutyAssignment: FIELD_MAP[models.DutyAssignment],
    models.EmployeeScheduleBlock: ("id", "company", "created_by", "created_at", "updated_at"),
    models.ReplacementRequest: FIELD_MAP[models.ReplacementRequest],
    models.RosterChangeEvent: FIELD_MAP[models.RosterChangeEvent],
    models.RosterAvailabilityConflict: FIELD_MAP[models.RosterAvailabilityConflict],
}


def serializer_for(model_class):
    class Serializer(TenantDeploymentSerializer):
        class Meta:
            model = model_class
            fields = FIELD_MAP[model_class]
            read_only_fields = READ_ONLY[model_class]

    Serializer.__name__ = f"{model_class.__name__}Serializer"
    Serializer.__qualname__ = Serializer.__name__
    return Serializer


SERIALIZERS = {model.__name__: serializer_for(model) for model in FIELD_MAP}
