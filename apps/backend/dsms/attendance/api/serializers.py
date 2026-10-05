# mypy: disable-error-code="type-arg,attr-defined,operator"
from __future__ import annotations

from typing import Any

from django.db.models import F
from django.utils import timezone
from rest_framework import serializers

from dsms.contracts.models import SecurityPost, SecuritySite
from dsms.identity import access
from dsms.organization.models import Branch, Company

from .. import models


class TenantAttendanceSerializer(serializers.ModelSerializer[Any]):
    """Scope writable organization relations and forbid implicit re-tenancy."""

    def get_fields(self) -> dict[str, serializers.Field[Any, Any, Any, Any]]:
        fields = super().get_fields()
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return fields
        verb = "add" if request.method == "POST" else "change"
        model = self.Meta.model
        permission = f"attendance.{verb}_{model._meta.model_name}"
        company_ids = access.get_accessible_company_ids(request.user, permission=permission)
        scoped = {
            "company": Company.objects.filter(id__in=company_ids, is_active=True),
            "branch": Branch.objects.filter(
                id__in=access.get_accessible_branch_ids(request.user, permission=permission),
                company__is_active=True,
            ),
            "site": SecuritySite.objects.filter(
                company_id__in=company_ids,
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
        }
        for name, queryset in scoped.items():
            field = fields.get(name)
            if isinstance(field, serializers.PrimaryKeyRelatedField) and not field.read_only:
                field.queryset = queryset
        return fields

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)
        current = self.instance
        company = attrs.get("company") or getattr(current, "company", None)
        if (
            current is not None
            and "company" in attrs
            and getattr(attrs["company"], "pk", None) != getattr(current, "company_id", None)
        ):
            raise serializers.ValidationError({"company": "Company cannot be changed."})
        if not isinstance(company, Company) or not company.is_active:
            raise serializers.ValidationError({"company": "An active Company is required."})
        branch = attrs.get("branch", getattr(current, "branch", None))
        site = attrs.get("site", getattr(current, "site", None))
        post = attrs.get("post", getattr(current, "post", None))
        errors: dict[str, str] = {}
        if branch is not None and branch.company_id != company.id:
            errors["branch"] = "Branch must belong to Company."
        if site is not None:
            if (
                site.company_id != company.id
                or site.client.company_id != company.id
                or site.contract.company_id != company.id
                or site.managing_branch.company_id != company.id
            ):
                errors["site"] = "Site must be tenant-consistent with Company."
            elif branch is not None and site.managing_branch_id != branch.id:
                errors["site"] = "Site must belong to Branch."
        if post is not None:
            if post.company_id != company.id or post.client.company_id != company.id:
                errors["post"] = "Post must belong to Company."
            elif site is None or post.site_id != site.id or post.client_id != site.client_id:
                errors["post"] = "Post must belong to Site."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class AttendancePolicySerializer(TenantAttendanceSerializer):
    class Meta:
        model = models.AttendancePolicy
        fields = (
            "id",
            "company",
            "branch",
            "site",
            "post",
            "name",
            "effective_from",
            "effective_to",
            "early_check_in_window_minutes",
            "late_grace_minutes",
            "early_departure_grace_minutes",
            "late_check_out_window_minutes",
            "missing_check_in_review_after_minutes",
            "require_gps",
            "require_qr",
            "require_face",
            "allow_supervisor_verification",
            "allow_manual_correction",
            "allow_offline_submission",
            "maximum_gps_accuracy_meters",
            "additional_geofence_tolerance_meters",
            "maximum_offline_age_minutes",
            "offline_requires_review",
            "rounding_increment_minutes",
            "rounding_mode",
            "overtime_requires_approval",
            "breaks_enabled",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class AttendanceQRStationSerializer(TenantAttendanceSerializer):
    class Meta:
        model = models.AttendanceQRStation
        fields = (
            "id",
            "company",
            "site",
            "post",
            "station_code",
            "name",
            "status",
            "token_hint",
            "generated_by",
            "generated_at",
            "rotated_at",
            "revoked_at",
            "expires_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "token_hint",
            "generated_by",
            "generated_at",
            "rotated_at",
            "revoked_at",
            "created_at",
            "updated_at",
        )

    def create(self, validated_data: dict[str, object]) -> models.AttendanceQRStation:
        request = self.context["request"]
        return models.AttendanceQRStation.objects.create(
            **validated_data,
            token_hash="",
            generated_by=request.user,
            generated_at=timezone.now(),
        )


class AttendancePeriodSerializer(TenantAttendanceSerializer):
    class Meta:
        model = models.AttendancePeriod
        fields = (
            "id",
            "company",
            "branch",
            "period_start",
            "period_end",
            "name",
            "status",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "approved_at",
            "locked_by",
            "locked_at",
            "closed_by",
            "closed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "approved_at",
            "locked_by",
            "locked_at",
            "closed_by",
            "closed_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)
        start = attrs.get("period_start", getattr(self.instance, "period_start", None))
        end = attrs.get("period_end", getattr(self.instance, "period_end", None))
        if start and end and end < start:
            raise serializers.ValidationError({"period_end": "End cannot precede start."})
        return attrs


class AttendanceRecordSerializer(serializers.ModelSerializer[models.AttendanceRecord]):
    class Meta:
        model = models.AttendanceRecord
        fields = (
            "id",
            "company",
            "branch",
            "client",
            "site",
            "post",
            "employee",
            "duty_assignment",
            "attendance_period",
            "scheduled_start_at",
            "scheduled_end_at",
            "actual_check_in_at",
            "actual_check_out_at",
            "approved_check_in_at",
            "approved_check_out_at",
            "late_minutes",
            "early_departure_minutes",
            "actual_worked_minutes",
            "approved_worked_minutes",
            "approved_overtime_minutes",
            "status",
            "outcome",
            "reviewed_by",
            "reviewed_at",
            "approved_by",
            "approved_at",
            "locked_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AttendanceEventSerializer(serializers.ModelSerializer[models.AttendanceEvent]):
    class Meta:
        model = models.AttendanceEvent
        fields = (
            "id",
            "attendance_record",
            "event_type",
            "subject_employee",
            "actor_user",
            "observed_at",
            "received_at",
            "client_event_id",
            "is_offline_submission",
            "device_platform",
            "app_version",
            "notes",
            "created_at",
        )
        read_only_fields = fields


class AttendanceVerificationSerializer(serializers.ModelSerializer[models.AttendanceVerification]):
    class Meta:
        model = models.AttendanceVerification
        fields = (
            "id",
            "attendance_event",
            "method",
            "result",
            "latitude",
            "longitude",
            "accuracy_meters",
            "distance_from_site_meters",
            "geofence_radius_meters",
            "qr_station",
            "provider_reference",
            "face_match_result",
            "liveness_result",
            "confidence_score",
            "verified_by",
            "failure_code",
            "created_at",
        )
        read_only_fields = fields

    def to_representation(self, instance: models.AttendanceVerification) -> dict[str, object]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        record = instance.attendance_event.attendance_record
        if not request or not access.has_permission(
            user=request.user,
            permission="attendance.view_sensitive_location_data",
            company=record.company,
            branch=record.branch,
        ):
            for field in (
                "latitude",
                "longitude",
                "accuracy_meters",
                "distance_from_site_meters",
                "geofence_radius_meters",
            ):
                data.pop(field, None)
        if not request or not access.has_permission(
            user=request.user,
            permission="attendance.view_biometric_verification_details",
            company=record.company,
            branch=record.branch,
        ):
            for field in (
                "provider_reference",
                "face_match_result",
                "liveness_result",
                "confidence_score",
                "failure_code",
            ):
                data.pop(field, None)
        return data


class AttendanceExceptionSerializer(serializers.ModelSerializer[models.AttendanceException]):
    class Meta:
        model = models.AttendanceException
        fields = (
            "id",
            "attendance_record",
            "attendance_event",
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
        )
        read_only_fields = fields


class AttendanceCorrectionSerializer(
    serializers.ModelSerializer[models.AttendanceCorrectionRequest]
):
    class Meta:
        model = models.AttendanceCorrectionRequest
        fields = (
            "id",
            "attendance_record",
            "requested_by",
            "requested_at",
            "reason",
            "proposed_check_in_at",
            "proposed_check_out_at",
            "proposed_outcome",
            "proposed_approved_worked_minutes",
            "proposed_overtime_minutes",
            "status",
            "reviewed_by",
            "reviewed_at",
            "review_notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AttendanceChangeEventSerializer(serializers.ModelSerializer[models.AttendanceChangeEvent]):
    class Meta:
        model = models.AttendanceChangeEvent
        fields = (
            "id",
            "attendance_record",
            "attendance_period",
            "event_type",
            "actor",
            "reason",
            "created_at",
        )
        read_only_fields = fields


class AttendancePayrollExportSerializer(
    serializers.ModelSerializer[models.AttendancePayrollExport]
):
    class Meta:
        model = models.AttendancePayrollExport
        fields = (
            "id",
            "attendance_period",
            "payroll_period",
            "employee",
            "source_version",
            "quantities",
            "exported_by",
            "exported_at",
            "adjustment_required",
        )
        read_only_fields = fields


SERIALIZERS = {
    "AttendancePolicy": AttendancePolicySerializer,
    "AttendancePeriod": AttendancePeriodSerializer,
    "AttendanceEvent": AttendanceEventSerializer,
    "AttendanceVerification": AttendanceVerificationSerializer,
    "AttendanceException": AttendanceExceptionSerializer,
    "AttendanceCorrectionRequest": AttendanceCorrectionSerializer,
    "AttendanceChangeEvent": AttendanceChangeEventSerializer,
    "AttendancePayrollExport": AttendancePayrollExportSerializer,
}
