# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,no-untyped-call,operator"
from __future__ import annotations

from typing import Any, ClassVar, cast

from django.db.models import Q
from rest_framework import serializers

from dsms.contracts.models import Client, SecurityPost, SecuritySite
from dsms.deployment.models import DutyAssignment
from dsms.deployment.tenant_queries import (
    consistent_duty_assignments,
    consistent_employees,
    consistent_posts,
    consistent_sites,
)
from dsms.identity import access
from dsms.organization.models import Branch, Company, Designation
from dsms.workforce.models import Employee

from .. import models
from ..tenant_queries import (
    consistent_checkpoints,
    consistent_requirements,
    consistent_route_versions,
    consistent_routes,
    consistent_runs,
    consistent_visits,
)


def _value(attrs, instance, name):
    return attrs.get(name, getattr(instance, name, None))


def _company_for(model, attrs, instance):
    if model in {models.PatrolCheckpoint, models.PatrolRoute, models.PatrolRequirement}:
        return _value(attrs, instance, "site").company
    if model is models.PatrolObservation:
        return _value(attrs, instance, "patrol_run").company
    if model is models.PatrolPolicy:
        site = _value(attrs, instance, "site")
        branch = _value(attrs, instance, "branch")
        return (
            getattr(site, "company", None)
            or getattr(branch, "company", None)
            or _value(attrs, instance, "company")
        )
    return _value(attrs, instance, "company")


class SensitiveLocationMixin:
    location_fields: ClassVar[tuple[str, ...]] = ()
    location_permission = "patrol.view_sensitive_patrol_location"

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)  # type: ignore[misc]
        request = self.context.get("request")
        company = getattr(instance, "company", None)
        branch = None
        if isinstance(instance, models.PatrolCheckpoint):
            branch = instance.site.managing_branch
        elif isinstance(instance, models.PatrolRun):
            branch = instance.patrol_task.branch
        elif isinstance(instance, models.CheckpointVisit):
            company = instance.patrol_run.company
            branch = instance.patrol_run.patrol_task.branch
        if not request or not access.has_permission(
            user=request.user,
            permission=self.location_permission,
            company=company,
            branch=branch,
        ):
            for field_name in self.location_fields:
                data.pop(field_name, None)
        return cast(dict[str, Any], data)


class TenantPatrolSerializer(serializers.ModelSerializer[Any]):
    """Scope writable relations and validate the complete Patrol graph."""

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        fields = super().get_fields()
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return fields
        verb = "add" if request.method == "POST" else "change"
        model = self.Meta.model
        permission = f"patrol.{verb}_{model._meta.model_name}"
        company_ids = access.get_accessible_company_ids(request.user, permission=permission)
        full_company_ids = access.get_fully_accessible_company_ids(
            request.user, permission=permission
        )
        branch_ids = access.get_accessible_branch_ids(request.user, permission=permission)
        relation_querysets = {
            "company": Company.objects.filter(id__in=company_ids, is_active=True),
            "branch": Branch.objects.filter(id__in=branch_ids, company__is_active=True),
            "client": Client.objects.filter(company_id__in=company_ids, company__is_active=True),
            "site": consistent_sites(
                SecuritySite.objects.filter(managing_branch_id__in=branch_ids)
            ),
            "post": consistent_posts(
                SecurityPost.objects.filter(site__managing_branch_id__in=branch_ids)
            ),
            "assigned_designation": Designation.objects.filter(company_id__in=company_ids),
            "patrol_route": consistent_routes(
                models.PatrolRoute.objects.filter(site__managing_branch_id__in=branch_ids)
            ),
            "patrol_requirement": consistent_requirements(
                models.PatrolRequirement.objects.filter(branch_id__in=branch_ids)
            ),
            "route_version": consistent_route_versions(
                models.PatrolRouteVersion.objects.filter(
                    patrol_route__site__managing_branch_id__in=branch_ids
                )
            ),
            "checkpoint": consistent_checkpoints(
                models.PatrolCheckpoint.objects.filter(site__managing_branch_id__in=branch_ids)
            ),
            "assigned_employee": consistent_employees(
                Employee.objects.filter(
                    Q(branch_id__in=branch_ids)
                    | Q(branch__isnull=True, company_id__in=full_company_ids)
                )
            ),
            "supervisor": consistent_employees(
                Employee.objects.filter(
                    Q(branch_id__in=branch_ids)
                    | Q(branch__isnull=True, company_id__in=full_company_ids)
                )
            ),
            "duty_assignment": consistent_duty_assignments(
                DutyAssignment.objects.filter(duty_shift__branch_id__in=branch_ids)
            ),
            "patrol_run": consistent_runs(
                models.PatrolRun.objects.filter(patrol_task__branch_id__in=branch_ids)
            ),
            "checkpoint_visit": consistent_visits(
                models.CheckpointVisit.objects.filter(
                    patrol_run__patrol_task__branch_id__in=branch_ids
                )
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
            supplied_company = attrs.get("company")
            if supplied_company is not None and getattr(supplied_company, "pk", None) != company.id:
                raise serializers.ValidationError({"company": "Company cannot be changed."})

        errors: dict[str, str] = {}
        if model is models.PatrolPolicy:
            branch = _value(attrs, current, "branch")
            site = _value(attrs, current, "site")
            if branch is not None and branch.company_id != company.id:
                errors["branch"] = "Branch belongs to another Company."
            if site is not None and (
                site.company_id != company.id
                or (branch is not None and site.managing_branch_id != branch.id)
            ):
                errors["site"] = "Site does not match Company and Branch."
        elif model is models.PatrolCheckpoint:
            site = _value(attrs, current, "site")
            client = site.client
            post = _value(attrs, current, "post")
            if client.company_id != company.id:
                errors["client"] = "Client belongs to another Company."
            if site.company_id != company.id or site.client_id != client.id:
                errors["site"] = "Site does not match Company and Client."
            if post is not None and (
                post.company_id != company.id
                or post.client_id != client.id
                or post.site_id != site.id
            ):
                errors["post"] = "Post does not belong to the Checkpoint Site."
        elif model is models.PatrolRoute:
            site = _value(attrs, current, "site")
            client = site.client
            if client.company_id != company.id:
                errors["client"] = "Client belongs to another Company."
            if site.company_id != company.id or site.client_id != client.id:
                errors["site"] = "Site does not match Company and Client."
        elif model is models.PatrolRequirement:
            branch = _value(attrs, current, "branch")
            site = _value(attrs, current, "site")
            client = site.client
            route = _value(attrs, current, "patrol_route")
            designation = _value(attrs, current, "assigned_designation")
            if branch.company_id != company.id:
                errors["branch"] = "Branch belongs to another Company."
            if client.company_id != company.id:
                errors["client"] = "Client belongs to another Company."
            if (
                site.company_id != company.id
                or site.client_id != client.id
                or site.managing_branch_id != branch.id
            ):
                errors["site"] = "Site does not match Company, Client and Branch."
            if (
                route.company_id != company.id
                or route.client_id != client.id
                or route.site_id != site.id
            ):
                errors["patrol_route"] = "Route does not match the Requirement Site."
            if designation is not None and designation.company_id != company.id:
                errors["assigned_designation"] = "Designation belongs to another Company."
        elif model is models.PatrolObservation:
            run = _value(attrs, current, "patrol_run")
            site = run.site
            visit = _value(attrs, current, "checkpoint_visit")
            checkpoint = _value(attrs, current, "checkpoint")
            post = _value(attrs, current, "post")
            if run.company_id != company.id or site.id != run.site_id:
                errors["patrol_run"] = "Run and Site do not share the same Company context."
            if visit is not None and visit.patrol_run_id != run.id:
                errors["checkpoint_visit"] = "Checkpoint Visit does not belong to this Run."
            if checkpoint is not None and checkpoint.site_id != site.id:
                errors["checkpoint"] = "Checkpoint does not belong to this Site."
            if (
                visit is not None
                and checkpoint is not None
                and visit.checkpoint_id != checkpoint.id
            ):
                errors["checkpoint_visit"] = "Checkpoint Visit does not match the Checkpoint."
            if post is not None and post.site_id != site.id:
                errors["post"] = "Post does not belong to this Site."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def create(self, validated_data: dict[str, object]):
        model = self.Meta.model
        request = self.context["request"]
        if model in {
            models.PatrolPolicy,
            models.PatrolCheckpoint,
            models.PatrolRoute,
            models.PatrolRequirement,
            models.PatrolObservation,
        }:
            validated_data["company"] = _company_for(model, validated_data, None)
        if model in {models.PatrolCheckpoint, models.PatrolRoute, models.PatrolRequirement}:
            validated_data["client"] = validated_data["site"].client
        if model is models.PatrolObservation:
            validated_data["site"] = validated_data["patrol_run"].site
        if model in {models.PatrolRoute, models.PatrolRequirement, models.PatrolObservation}:
            validated_data["created_by"] = request.user
        return model.objects.create(**validated_data)


class PatrolCheckpointSerializer(SensitiveLocationMixin, TenantPatrolSerializer):
    location_permission = "patrol.view_sensitive_checkpoint_location"
    location_fields = ("latitude", "longitude", "geofence_radius_meters")

    class Meta:
        model = models.PatrolCheckpoint
        fields = (
            "id",
            "company",
            "client",
            "site",
            "post",
            "checkpoint_code",
            "name",
            "description",
            "checkpoint_type",
            "location_description",
            "latitude",
            "longitude",
            "geofence_radius_meters",
            "status",
            "supports_qr",
            "supports_nfc",
            "requires_gps",
            "is_sensitive_location",
            "instructions",
            "sort_order",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("company", "client", "created_at", "updated_at")


class PatrolRunSerializer(SensitiveLocationMixin, serializers.ModelSerializer[models.PatrolRun]):
    location_fields = (
        "start_latitude",
        "start_longitude",
        "start_accuracy_meters",
        "start_distance_from_site_meters",
        "end_latitude",
        "end_longitude",
        "end_accuracy_meters",
    )

    class Meta:
        model = models.PatrolRun
        fields = (
            "id",
            "patrol_task",
            "company",
            "site",
            "employee",
            "duty_assignment",
            "route_version",
            "started_at",
            "ended_at",
            "status",
            "start_latitude",
            "start_longitude",
            "start_accuracy_meters",
            "start_distance_from_site_meters",
            "end_latitude",
            "end_longitude",
            "end_accuracy_meters",
            "mandatory_checkpoint_count",
            "verified_mandatory_count",
            "total_checkpoint_count",
            "visited_checkpoint_count",
            "completion_percentage",
            "started_offline",
            "completed_offline",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class CheckpointVisitSerializer(
    SensitiveLocationMixin, serializers.ModelSerializer[models.CheckpointVisit]
):
    location_fields = (
        "latitude",
        "longitude",
        "accuracy_meters",
        "distance_meters",
        "allowed_radius_meters",
    )

    class Meta:
        model = models.CheckpointVisit
        fields = (
            "id",
            "patrol_run",
            "patrol_event",
            "route_checkpoint",
            "checkpoint",
            "sequence_observed",
            "observed_at",
            "received_at",
            "status",
            "gps_result",
            "token_result",
            "overall_verification_result",
            "latitude",
            "longitude",
            "accuracy_meters",
            "distance_meters",
            "allowed_radius_meters",
            "verification_method",
            "expected_at",
            "early_minutes",
            "late_minutes",
            "is_offline_submission",
            "remarks",
            "created_at",
        )
        read_only_fields = fields


FIELD_MAP = {
    models.PatrolPolicy: (
        "id",
        "company",
        "branch",
        "site",
        "name",
        "effective_from",
        "effective_to",
        "early_start_tolerance_minutes",
        "late_start_tolerance_minutes",
        "checkpoint_early_tolerance_minutes",
        "checkpoint_late_tolerance_minutes",
        "patrol_completion_tolerance_minutes",
        "require_gps",
        "require_checkpoint_token",
        "allow_qr",
        "allow_nfc",
        "allow_supervisor_verification",
        "allow_manual_verification",
        "allow_offline_submission",
        "maximum_gps_accuracy_meters",
        "checkpoint_geofence_tolerance_meters",
        "maximum_offline_age_minutes",
        "offline_requires_review",
        "allow_flexible_checkpoint_order",
        "require_all_mandatory_checkpoints",
        "require_employee_on_active_duty_assignment",
        "require_employee_attendance_checked_in",
        "require_evidence_on_failed_checkpoint",
        "is_active",
        "created_at",
        "updated_at",
    ),
    models.CheckpointQRCredential: (
        "id",
        "checkpoint",
        "credential_id",
        "token_hint",
        "generated_by",
        "generated_at",
        "rotated_at",
        "expires_at",
        "revoked_at",
        "is_active",
        "created_at",
    ),
    models.CheckpointNFCCredential: (
        "id",
        "checkpoint",
        "public_identifier",
        "status",
        "generated_by",
        "generated_at",
        "revoked_at",
        "notes",
    ),
    models.PatrolRoute: (
        "id",
        "company",
        "client",
        "site",
        "route_code",
        "name",
        "description",
        "order_mode",
        "expected_duration_minutes",
        "status",
        "current_version_number",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.PatrolRouteVersion: (
        "id",
        "patrol_route",
        "version_number",
        "effective_from",
        "effective_to",
        "order_mode",
        "expected_duration_minutes",
        "is_current",
        "created_by",
        "created_at",
    ),
    models.PatrolRouteCheckpoint: (
        "id",
        "route_version",
        "checkpoint",
        "sequence",
        "is_mandatory",
        "expected_offset_minutes",
        "earliest_offset_minutes",
        "latest_offset_minutes",
        "minimum_dwell_seconds",
        "notes",
        "created_at",
    ),
    models.PatrolRequirement: (
        "id",
        "company",
        "branch",
        "client",
        "site",
        "patrol_route",
        "requirement_code",
        "effective_from",
        "effective_to",
        "status",
        "start_time",
        "expected_duration_minutes",
        "frequency_per_day",
        "assigned_employee_type",
        "assigned_designation",
        "priority",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.PatrolRequirementDay: ("id", "patrol_requirement", "weekday"),
    models.PatrolRequirementTime: ("id", "patrol_requirement", "sequence", "start_time"),
    models.PatrolTask: (
        "id",
        "company",
        "branch",
        "client",
        "site",
        "patrol_requirement",
        "patrol_route",
        "route_version",
        "task_number",
        "scheduled_start_at",
        "scheduled_end_at",
        "assigned_employee",
        "duty_assignment",
        "supervisor",
        "priority",
        "status",
        "is_adhoc",
        "adhoc_reason",
        "generated_at",
        "generated_by",
        "created_at",
        "updated_at",
    ),
    models.PatrolEvent: (
        "id",
        "patrol_run",
        "event_type",
        "actor_user",
        "employee",
        "observed_at",
        "received_at",
        "is_offline_submission",
        "device_platform",
        "app_version",
        "notes",
        "created_at",
    ),
    models.PatrolEvidence: (
        "id",
        "company",
        "patrol_run",
        "checkpoint_visit",
        "observation",
        "original_filename",
        "file_size",
        "mime_type",
        "caption",
        "captured_at",
        "uploaded_by",
        "created_at",
    ),
    models.PatrolObservation: (
        "id",
        "company",
        "patrol_run",
        "checkpoint_visit",
        "site",
        "checkpoint",
        "post",
        "category",
        "title",
        "description",
        "severity",
        "requires_follow_up",
        "requires_incident_escalation",
        "observed_at",
        "created_by",
        "created_at",
        "updated_at",
    ),
    models.PatrolException: (
        "id",
        "company",
        "patrol_task",
        "patrol_run",
        "checkpoint_visit",
        "exception_type",
        "severity",
        "status",
        "detected_at",
        "message",
        "acknowledged_by",
        "acknowledged_at",
        "resolved_by",
        "resolved_at",
        "resolution_notes",
        "created_at",
        "updated_at",
    ),
    models.PatrolReview: (
        "id",
        "patrol_run",
        "reviewed_by",
        "reviewed_at",
        "review_result",
        "comments",
        "created_at",
    ),
}


READ_ONLY_MODELS = {
    models.CheckpointQRCredential,
    models.CheckpointNFCCredential,
    models.PatrolRouteVersion,
    models.PatrolRouteCheckpoint,
    models.PatrolRequirementDay,
    models.PatrolRequirementTime,
    models.PatrolTask,
    models.PatrolEvent,
    models.PatrolEvidence,
    models.PatrolException,
    models.PatrolReview,
}


def _serializer(model, name):
    fields = FIELD_MAP[model]
    if model in READ_ONLY_MODELS:
        read_only = fields
    else:
        protected = {"created_by", "created_at", "updated_at"}
        if model is not models.PatrolPolicy:
            protected.add("company")
        if model in {models.PatrolRoute, models.PatrolRequirement}:
            protected.update({"client", "status"})
        if model is models.PatrolRoute:
            protected.add("current_version_number")
        if model is models.PatrolObservation:
            protected.add("site")
        read_only = tuple(field for field in fields if field in protected)
    meta = type("Meta", (), {"model": model, "fields": fields, "read_only_fields": read_only})
    return type(name, (TenantPatrolSerializer,), {"Meta": meta})


SERIALIZERS: dict[str, type[serializers.ModelSerializer[Any]]] = {
    model.__name__: _serializer(model, f"{model.__name__}Serializer") for model in FIELD_MAP
}
SERIALIZERS["PatrolCheckpoint"] = PatrolCheckpointSerializer
SERIALIZERS["PatrolRun"] = PatrolRunSerializer
SERIALIZERS["CheckpointVisit"] = CheckpointVisitSerializer


class EmployeeActionSerializer(serializers.Serializer):
    employee = serializers.UUIDField()


class StartPatrolSerializer(serializers.Serializer):
    patrol_task = serializers.UUIDField()
    gps = serializers.DictField(required=False)
    client_event_id = serializers.UUIDField(required=False)
    device_metadata = serializers.DictField(required=False)


class VerifyCheckpointSerializer(serializers.Serializer):
    checkpoint = serializers.UUIDField()
    gps = serializers.DictField(required=False)
    qr_token = serializers.CharField(required=False, allow_blank=False, write_only=True)
    nfc_payload = serializers.CharField(required=False, allow_blank=False, write_only=True)
    client_event_id = serializers.UUIDField(required=False)


class CompletePatrolSerializer(serializers.Serializer):
    gps = serializers.DictField(required=False)
    client_event_id = serializers.UUIDField(required=False)
