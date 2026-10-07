# mypy: disable-error-code="type-arg,var-annotated,no-untyped-def,no-untyped-call"
from __future__ import annotations

from typing import Any

from django.db.models import Q
from rest_framework import serializers

from dsms.contracts.models import Client, SecurityPost, SecuritySite, ServiceContract
from dsms.deployment.tenant_queries import (
    consistent_employees,
    consistent_posts,
    consistent_sites,
)
from dsms.identity import access
from dsms.organization.models import Branch, Company, OperationalZone
from dsms.workforce.models import Employee

from .. import enums, models
from ..tenant_queries import consistent_incident_types, incident_graph_errors

INCIDENT_FIELDS = (
    "id",
    "incident_number",
    "company",
    "client",
    "contract",
    "site",
    "post",
    "branch",
    "operational_zone",
    "incident_type",
    "severity",
    "priority",
    "status",
    "verification_status",
    "source",
    "reporter_employee",
    "reporter_user",
    "reported_by_name",
    "reported_at",
    "duty_assignment",
    "attendance_record",
    "employee_deployment",
    "site_visit",
    "inspection",
    "patrol_task",
    "patrol_run",
    "checkpoint_visit",
    "patrol_observation",
    "supervision_finding",
    "patrol_exception",
    "title",
    "description",
    "occurred_at",
    "discovered_at",
    "command_center_owner",
    "operations_owner",
    "acknowledged_at",
    "acknowledged_by",
    "triaged_at",
    "responding_at",
    "contained_at",
    "resolved_at",
    "closed_at",
    "resolution_summary",
    "closure_summary",
    "client_notification_required",
    "management_notification_required",
    "post_incident_review_required",
    "created_by",
    "created_at",
    "updated_at",
)

INCIDENT_READ_ONLY_FIELDS = (
    "id",
    "incident_number",
    "severity",
    "priority",
    "status",
    "verification_status",
    "source",
    "reporter_user",
    "reported_at",
    "duty_assignment",
    "attendance_record",
    "employee_deployment",
    "site_visit",
    "inspection",
    "patrol_task",
    "patrol_run",
    "checkpoint_visit",
    "patrol_observation",
    "supervision_finding",
    "patrol_exception",
    "command_center_owner",
    "operations_owner",
    "acknowledged_at",
    "acknowledged_by",
    "triaged_at",
    "responding_at",
    "contained_at",
    "resolved_at",
    "closed_at",
    "resolution_summary",
    "closure_summary",
    "client_notification_required",
    "management_notification_required",
    "post_incident_review_required",
    "created_by",
    "created_at",
    "updated_at",
)


def _value(attrs, instance, name):
    return attrs.get(name, getattr(instance, name, None))


class IncidentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Incident
        fields = (
            "id",
            "incident_number",
            "company",
            "client",
            "site",
            "branch",
            "incident_type",
            "severity",
            "priority",
            "status",
            "verification_status",
            "source",
            "title",
            "reported_at",
            "acknowledged_at",
            "resolved_at",
        )
        read_only_fields = fields


class IncidentDetailSerializer(serializers.ModelSerializer):
    """Explicit direct-report surface; operational-source links are workflow-owned."""

    class Meta:
        model = models.Incident
        fields = INCIDENT_FIELDS
        read_only_fields = INCIDENT_READ_ONLY_FIELDS
        extra_kwargs = {"company": {"required": False}, "branch": {"required": False}}

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return fields
        permission = (
            "incidents.report_incident" if request.method == "POST" else "incidents.manage_incident"
        )
        company_ids = access.get_accessible_company_ids(request.user, permission=permission)
        branch_ids = access.get_accessible_branch_ids(request.user, permission=permission)
        relations = {
            "company": Company.objects.filter(pk__in=company_ids, is_active=True),
            "branch": Branch.objects.filter(pk__in=branch_ids, company__is_active=True),
            "client": Client.objects.filter(company_id__in=company_ids, company__is_active=True),
            "contract": ServiceContract.objects.filter(
                company_id__in=company_ids, company__is_active=True
            ),
            "site": consistent_sites(
                SecuritySite.objects.filter(managing_branch_id__in=branch_ids)
            ),
            "post": consistent_posts(
                SecurityPost.objects.filter(site__managing_branch_id__in=branch_ids)
            ),
            "operational_zone": OperationalZone.objects.filter(
                branch_id__in=branch_ids, company__is_active=True
            ),
            "incident_type": consistent_incident_types(
                models.IncidentType.objects.filter(
                    Q(company_id__in=company_ids) | Q(company__isnull=True), is_active=True
                )
            ),
            "reporter_employee": consistent_employees(
                Employee.objects.filter(company_id__in=company_ids)
            ),
        }
        for name, queryset in relations.items():
            field = fields.get(name)
            if isinstance(field, serializers.PrimaryKeyRelatedField) and not field.read_only:
                field.queryset = queryset
        return fields

    def validate(self, attrs):
        attrs = super().validate(attrs)
        current = self.instance
        site = _value(attrs, current, "site")
        if site is not None:
            derived = {
                "company": site.company,
                "branch": site.managing_branch,
                "client": site.client,
                "contract": site.contract,
            }
            for name, expected in derived.items():
                supplied = _value(attrs, current, name)
                if supplied is not None and supplied.pk != expected.pk:
                    raise serializers.ValidationError(
                        {name: f"{name.replace('_', ' ').title()} does not match the Site."}
                    )
                attrs[name] = expected
        company = _value(attrs, current, "company")
        branch = _value(attrs, current, "branch")
        incident_type = _value(attrs, current, "incident_type")
        if company is None or branch is None:
            raise serializers.ValidationError(
                {"company": "Company and Branch are required when no Site is supplied."}
            )
        if incident_type is None:
            raise serializers.ValidationError({"incident_type": "Incident Type is required."})
        if current is not None and current.company_id != company.id:
            raise serializers.ValidationError({"company": "Company cannot be changed."})
        context = {
            name: _value(attrs, current, name)
            for name in (
                "client",
                "contract",
                "site",
                "post",
                "operational_zone",
                "reporter_employee",
                "duty_assignment",
                "attendance_record",
                "employee_deployment",
                "site_visit",
                "inspection",
                "patrol_task",
                "patrol_run",
                "checkpoint_visit",
                "patrol_observation",
                "patrol_exception",
                "supervision_finding",
            )
        }
        errors = incident_graph_errors(
            company=company, branch=branch, incident_type=incident_type, context=context
        )
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class SensitiveSOSSerializer(serializers.ModelSerializer):
    location_fields = ("latitude", "longitude", "accuracy_meters")

    class Meta:
        model = models.SOSAlert
        fields = (
            "id",
            "sos_number",
            "company",
            "employee",
            "duty_assignment",
            "attendance_record",
            "site",
            "post",
            "patrol_run",
            "activation_method",
            "status",
            "triggered_at",
            "received_at",
            "latitude",
            "longitude",
            "accuracy_meters",
            "message",
            "acknowledged_at",
            "linked_incident",
            "cancelled_at",
            "cancellation_reason",
            "false_alarm_reason",
            "created_at",
        )
        read_only_fields = fields

    def to_representation(self, instance: Any) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        if not request or not access.has_permission(
            user=request.user,
            permission="incidents.view_sensitive_incident_location",
            company=instance.company,
            branch=instance.employee.branch,
        ):
            for name in self.location_fields:
                data.pop(name, None)
        return data


SOSSerializer = SensitiveSOSSerializer


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.IncidentEvent
        fields = (
            "id",
            "incident",
            "event_type",
            "actor_user",
            "actor_employee",
            "event_time",
            "server_recorded_at",
            "title",
            "description",
            "previous_status",
            "new_status",
            "created_at",
        )
        read_only_fields = fields


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.IncidentEvidence
        fields = (
            "id",
            "company",
            "incident",
            "evidence_type",
            "original_filename",
            "file_size",
            "mime_type",
            "captured_at",
            "uploaded_by",
            "description",
            "created_at",
        )
        read_only_fields = fields


class TriggerSOSSerializer(serializers.Serializer):
    employee = serializers.UUIDField()
    client_event_id = serializers.UUIDField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    accuracy_meters = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    message = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if ("latitude" in attrs) != ("longitude" in attrs):
            raise serializers.ValidationError("Latitude and longitude must be supplied together.")
        return attrs


class TransitionSerializer(serializers.Serializer):
    summary = serializers.CharField(required=False, allow_blank=True)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True, allow_blank=False)


class ResponderSerializer(serializers.Serializer):
    user = serializers.UUIDField(required=False)
    employee = serializers.UUIDField(required=False)
    responder_role = serializers.ChoiceField(choices=enums.ResponderRole.choices)

    def validate(self, attrs):
        if not attrs.get("user") and not attrs.get("employee"):
            raise serializers.ValidationError("A User or Employee responder is required.")
        return attrs


class IncidentActionSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.ChoiceField(
        choices=enums.IncidentActionPriority.choices, default="NORMAL"
    )


class EscalationSerializer(serializers.Serializer):
    escalation_type = serializers.CharField(max_length=50, default="MANUAL")
    reason = serializers.CharField(required=False, allow_blank=True)
