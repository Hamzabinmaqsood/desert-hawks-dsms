# mypy: disable-error-code="type-arg,var-annotated"
from rest_framework import serializers

from dsms.incidents import models


class IncidentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Incident
        fields = [
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
        ]


class IncidentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.Incident
        exclude = []
        read_only_fields = [
            "incident_number",
            "status",
            "acknowledged_at",
            "triaged_at",
            "responding_at",
            "contained_at",
            "resolved_at",
            "closed_at",
            "created_by",
            "created_at",
            "updated_at",
        ]


class SOSSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SOSAlert
        exclude = ["latitude", "longitude", "accuracy_meters"]


class SensitiveSOSSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.SOSAlert
        fields = "__all__"


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.IncidentEvent
        fields = "__all__"


class EvidenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.IncidentEvidence
        exclude = ["file"]
        read_only_fields = ["sha256_hash", "file_size", "mime_type", "created_at"]


class TriggerSOSSerializer(serializers.Serializer):
    employee = serializers.UUIDField()
    client_event_id = serializers.UUIDField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False)
    accuracy_meters = serializers.DecimalField(max_digits=8, decimal_places=2, required=False)
    message = serializers.CharField(required=False, allow_blank=True)


class TransitionSerializer(serializers.Serializer):
    summary = serializers.CharField(required=False, allow_blank=True)
