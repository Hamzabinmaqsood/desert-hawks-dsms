# mypy: disable-error-code="type-arg"
from rest_framework import serializers

from .. import models


class AttendanceQRStationSerializer(serializers.ModelSerializer[models.AttendanceQRStation]):
    class Meta:
        model = models.AttendanceQRStation
        exclude = ["token_hash"]
        read_only_fields = ["token_hint", "generated_at", "rotated_at", "revoked_at"]


class AttendanceRecordSerializer(serializers.ModelSerializer[models.AttendanceRecord]):
    class Meta:
        model = models.AttendanceRecord
        fields = "__all__"
        read_only_fields = [
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
        ]


def serializer_for(model: type) -> type[serializers.ModelSerializer]:
    class ItemSerializer(serializers.ModelSerializer):
        class Meta:
            fields = "__all__"
            read_only_fields = (
                "status",
                "submitted_by",
                "submitted_at",
                "approved_by",
                "approved_at",
                "locked_by",
                "locked_at",
                "closed_by",
                "closed_at",
                "reviewed_by",
                "reviewed_at",
                "exported_at",
                "adjustment_required",
            )

    ItemSerializer.Meta.model = model
    ItemSerializer.__name__ = f"{model.__name__}Serializer"
    ItemSerializer.__qualname__ = ItemSerializer.__name__
    return ItemSerializer


SERIALIZERS = {
    m.__name__: serializer_for(m)
    for m in (
        models.AttendancePolicy,
        models.AttendancePeriod,
        models.AttendanceEvent,
        models.AttendanceVerification,
        models.AttendanceException,
        models.AttendanceCorrectionRequest,
        models.AttendanceChangeEvent,
        models.AttendancePayrollExport,
    )
}
