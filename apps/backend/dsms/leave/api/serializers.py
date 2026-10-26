# mypy: disable-error-code="type-arg"
from typing import Any

from rest_framework import serializers

from dsms.identity import access
from dsms.leave.models import Holiday, LeaveRequest, LeaveType


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = [
            "id",
            "code",
            "name",
            "unit",
            "pay_treatment",
            "requires_balance",
            "requires_attachment",
            "allow_partial_day",
            "status",
        ]


class LeaveRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "request_number",
            "employee",
            "leave_type",
            "starts_at",
            "ends_at",
            "requested_units",
            "approved_units",
            "reason",
            "status",
            "emergency_request",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "cancellation_requested_at",
            "cancelled_at",
            "recalled_at",
            "created_at",
        ]
        read_only_fields = [
            "request_number",
            "employee",
            "requested_units",
            "approved_units",
            "status",
            "submitted_at",
            "approved_at",
            "rejected_at",
            "cancellation_requested_at",
            "cancelled_at",
            "recalled_at",
        ]


class AvailabilitySerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class LeaveDecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class LeaveBalanceSerializer(serializers.Serializer):
    leave_type = serializers.UUIDField()
    leave_type_name = serializers.CharField()
    unit = serializers.CharField()
    opening = serializers.DecimalField(max_digits=12, decimal_places=2)
    entitled = serializers.DecimalField(max_digits=12, decimal_places=2)
    accrued = serializers.DecimalField(max_digits=12, decimal_places=2)
    reserved = serializers.DecimalField(max_digits=12, decimal_places=2)
    taken = serializers.DecimalField(max_digits=12, decimal_places=2)
    adjusted = serializers.DecimalField(max_digits=12, decimal_places=2)
    expired = serializers.DecimalField(max_digits=12, decimal_places=2)
    carried_forward = serializers.DecimalField(max_digits=12, decimal_places=2)
    available = serializers.DecimalField(max_digits=12, decimal_places=2)


class ManagerLeaveRequestSerializer(LeaveRequestSerializer):
    employee_name = serializers.SerializerMethodField()
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta(LeaveRequestSerializer.Meta):
        fields = LeaveRequestSerializer.Meta.fields + ["employee_name", "leave_type_name"]

    def get_employee_name(self, instance: LeaveRequest) -> str:
        return instance.employee.full_name

    def to_representation(self, instance: LeaveRequest) -> dict[str, Any]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not access.has_permission(
            user=user,
            permission="leave.view_sensitive_leave_details",
            company=instance.company,
            branch=instance.employee.branch,
            department=instance.employee.department,
        ):
            data.pop("reason", None)
        return data


class TeamLeaveSerializer(serializers.ModelSerializer):
    employee_name = serializers.SerializerMethodField()
    leave_type_name = serializers.CharField(source="leave_type.name", read_only=True)

    class Meta:
        model = LeaveRequest
        fields = [
            "id",
            "request_number",
            "employee_name",
            "leave_type_name",
            "starts_at",
            "ends_at",
            "status",
        ]

    def get_employee_name(self, instance: LeaveRequest) -> str:
        return instance.employee.full_name


class HolidaySerializer(serializers.ModelSerializer):
    calendar_name = serializers.CharField(source="calendar.name", read_only=True)

    class Meta:
        model = Holiday
        fields = [
            "id",
            "date",
            "name",
            "holiday_type",
            "is_full_day",
            "starts_at",
            "ends_at",
            "calendar_name",
        ]
