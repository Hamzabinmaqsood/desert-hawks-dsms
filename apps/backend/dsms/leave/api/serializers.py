# mypy: disable-error-code="type-arg"
from rest_framework import serializers

from dsms.leave.models import LeaveRequest, LeaveType


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
