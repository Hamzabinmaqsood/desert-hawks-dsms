from rest_framework import serializers

from ..models import AnalyticsDataQualityIssue, AnalyticsMetricDefinition, AnalyticsSnapshot


class MetricDefinitionSerializer(serializers.ModelSerializer[AnalyticsMetricDefinition]):
    supported_dimensions = serializers.SerializerMethodField()

    class Meta:
        model = AnalyticsMetricDefinition
        fields = (
            "code",
            "name",
            "description",
            "category",
            "value_type",
            "aggregation",
            "direction",
            "unit",
            "currency",
            "decimal_places",
            "provider_code",
            "supported_dimensions",
        )

    def get_supported_dimensions(self, obj: AnalyticsMetricDefinition) -> list[str]:
        return [
            name
            for name in ("company", "region", "branch", "client", "contract", "site", "department")
            if getattr(obj, f"supports_{name}")
        ]


class SnapshotSerializer(serializers.ModelSerializer[AnalyticsSnapshot]):
    class Meta:
        model = AnalyticsSnapshot
        fields = "__all__"


class DataQualityIssueSerializer(serializers.ModelSerializer[AnalyticsDataQualityIssue]):
    class Meta:
        model = AnalyticsDataQualityIssue
        fields = "__all__"
