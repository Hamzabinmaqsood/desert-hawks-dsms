from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.documents.storage import private_document_storage

from .enums import (
    AnalyticsPeriodType,
    DataQualityIssueStatus,
    ExecutiveHealthStatus,
    MetricAggregation,
    MetricCategory,
    MetricDirection,
    MetricValueType,
    SnapshotStatus,
)


class AnalyticsModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class AnalyticsMetricDefinition(AnalyticsModel, ActiveModel):
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=180)
    description = models.TextField()
    category = models.CharField(max_length=30, choices=MetricCategory.choices)
    value_type = models.CharField(max_length=20, choices=MetricValueType.choices)
    aggregation = models.CharField(max_length=30, choices=MetricAggregation.choices)
    direction = models.CharField(max_length=30, choices=MetricDirection.choices)
    unit = models.CharField(max_length=30, blank=True)
    currency = models.CharField(max_length=3, blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    provider_code = models.CharField(max_length=100)
    is_system = models.BooleanField(default=False)
    supports_company = models.BooleanField(default=True)
    supports_region = models.BooleanField(default=False)
    supports_branch = models.BooleanField(default=False)
    supports_client = models.BooleanField(default=False)
    supports_contract = models.BooleanField(default=False)
    supports_site = models.BooleanField(default=False)
    supports_department = models.BooleanField(default=False)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        self.provider_code = self.provider_code.strip().lower()
        super().save(*args, **kwargs)


class ManagementKPI(AnalyticsModel, ActiveModel):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=180)
    metric_definition = models.ForeignKey(AnalyticsMetricDefinition, on_delete=models.PROTECT)
    target_value = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    warning_threshold = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    critical_threshold = models.DecimalField(max_digits=20, decimal_places=4, null=True, blank=True)
    direction = models.CharField(max_length=30, choices=MetricDirection.choices)
    period_type = models.CharField(max_length=20, choices=AnalyticsPeriodType.choices)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        permissions = [
            ("view_executive_dashboard", "Can view executive analytics dashboards"),
            ("view_data_quality", "Can view analytics data-quality issues"),
            ("manage_analytics", "Can manage analytics definitions and snapshots"),
            ("export_analytics", "Can request and download analytics exports"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="analytics_kpi_company_code_uniq"
            )
        ]


class DashboardDefinition(AnalyticsModel, ActiveModel):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=180)
    audience = models.CharField(max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="analytics_dashboard_company_code_uniq"
            )
        ]


class DashboardWidget(UUIDModel):
    dashboard = models.ForeignKey(
        DashboardDefinition, on_delete=models.PROTECT, related_name="widgets"
    )
    kpi = models.ForeignKey(ManagementKPI, on_delete=models.PROTECT)
    title = models.CharField(max_length=180)
    sort_order = models.PositiveIntegerField(default=0)
    drilldown_path = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["dashboard", "kpi"], name="analytics_dashboard_kpi_uniq"
            )
        ]


class AnalyticsSnapshot(AnalyticsModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    snapshot_type = models.CharField(max_length=40)
    period_type = models.CharField(max_length=20, choices=AnalyticsPeriodType.choices)
    period_start = models.DateField()
    period_end = models.DateField()
    as_of_datetime = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=SnapshotStatus.choices, default=SnapshotStatus.DRAFT
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="generated_analytics_snapshots",
    )
    calculated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="validated_analytics_snapshots",
    )
    validated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    source_version_hash = models.CharField(max_length=64, blank=True)
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="revisions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "snapshot_type", "period_type", "period_start", "period_end"],
                condition=Q(supersedes__isnull=True),
                name="analytics_base_snapshot_period_uniq",
            ),
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")),
                name="analytics_snapshot_dates_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["company", "status", "period_end"], name="analytics_snapshot_lookup_idx"
            )
        ]


class AnalyticsSnapshotValue(UUIDModel):
    snapshot = models.ForeignKey(AnalyticsSnapshot, on_delete=models.PROTECT, related_name="values")
    metric_definition = models.ForeignKey(AnalyticsMetricDefinition, on_delete=models.PROTECT)
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    region = models.ForeignKey(
        "organization.Region", null=True, blank=True, on_delete=models.PROTECT
    )
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    client = models.ForeignKey("contracts.Client", null=True, blank=True, on_delete=models.PROTECT)
    contract = models.ForeignKey(
        "contracts.ServiceContract", null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    department = models.ForeignKey(
        "organization.Department", null=True, blank=True, on_delete=models.PROTECT
    )
    integer_value = models.BigIntegerField(null=True, blank=True)
    decimal_value = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    text_value = models.TextField(blank=True)
    numerator = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    denominator = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    health_status = models.CharField(
        max_length=20, choices=ExecutiveHealthStatus.choices, blank=True
    )
    source_count = models.PositiveBigIntegerField(null=True, blank=True)
    warnings = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "snapshot",
                    "metric_definition",
                    "branch",
                    "client",
                    "contract",
                    "site",
                    "department",
                ],
                name="analytics_snapshot_value_uniq",
            )
        ]

    def clean(self) -> None:
        values = [
            self.integer_value is not None,
            self.decimal_value is not None,
            bool(self.text_value),
        ]
        if sum(values) != 1:
            raise ValidationError("Exactly one metric value representation is required.")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if (
            self.pk
            and type(self)
            .objects.filter(pk=self.pk, snapshot__status=SnapshotStatus.PUBLISHED)
            .exists()
        ):
            raise ValidationError("Published analytics values are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.snapshot.status == SnapshotStatus.PUBLISHED:
            raise ValidationError("Published analytics values cannot be deleted.")
        return super().delete(*args, **kwargs)


class AnalyticsDataQualityIssue(AnalyticsModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    metric_definition = models.ForeignKey(
        AnalyticsMetricDefinition, null=True, blank=True, on_delete=models.PROTECT
    )
    source_app = models.CharField(max_length=50)
    issue_code = models.CharField(max_length=80)
    severity = models.CharField(max_length=20)
    description = models.TextField()
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    client = models.ForeignKey("contracts.Client", null=True, blank=True, on_delete=models.PROTECT)
    site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    detected_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=DataQualityIssueStatus.choices, default=DataQualityIssueStatus.OPEN
    )

    class Meta:
        indexes = [
            models.Index(
                fields=["company", "status", "severity"], name="analytics_quality_lookup_idx"
            )
        ]


class AnalyticsCostAllocationPolicy(AnalyticsModel, ActiveModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="analytics_cost_policy_code_uniq"
            )
        ]


class AnalyticsCostAllocationRule(UUIDModel):
    policy = models.ForeignKey(
        AnalyticsCostAllocationPolicy, on_delete=models.PROTECT, related_name="rules"
    )
    cost_source = models.CharField(max_length=40)
    allocation_method = models.CharField(max_length=30)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AnalyticsPrivacyPolicy(AnalyticsModel, ActiveModel):
    company = models.OneToOneField("organization.Company", on_delete=models.PROTECT)
    minimum_group_size = models.PositiveIntegerField(default=5)
    suppress_performance_distributions = models.BooleanField(default=True)
    suppress_hr_case_breakdowns = models.BooleanField(default=True)
    suppress_salary_aggregates = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class ManagementReport(AnalyticsModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    report_number = models.CharField(max_length=40)
    report_type = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    period_start = models.DateField()
    period_end = models.DateField()
    snapshot = models.ForeignKey(AnalyticsSnapshot, on_delete=models.PROTECT)
    executive_narrative = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="DRAFT")
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_management_reports",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_management_reports",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_management_reports",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="revisions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "report_number"], name="analytics_report_number_uniq"
            )
        ]


class ManagementReportMetric(UUIDModel):
    report = models.ForeignKey(ManagementReport, on_delete=models.PROTECT, related_name="metrics")
    section = models.CharField(max_length=50)
    metric_definition = models.ForeignKey(AnalyticsMetricDefinition, on_delete=models.PROTECT)
    label = models.CharField(max_length=180)
    decimal_value = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True)
    text_value = models.TextField(blank=True)
    data_quality = models.CharField(max_length=30)
    warnings = models.JSONField(default=list)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and type(self).objects.filter(pk=self.pk, report__status="PUBLISHED").exists():
            raise ValidationError("Published management report metrics are immutable.")
        super().save(*args, **kwargs)


def analytics_export_upload_to(instance: object, filename: str) -> str:
    import uuid

    return f"analytics-exports/{uuid.uuid4().hex[:2]}/{uuid.uuid4()}.csv"


class AnalyticsExportJob(AnalyticsModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    export_type = models.CharField(max_length=50)
    filters = models.JSONField(default=dict)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, default="PENDING")
    file = models.FileField(
        storage=private_document_storage,
        upload_to=analytics_export_upload_to,
        null=True,
        blank=True,
    )
    expires_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["company", "status", "created_at"], name="analytics_export_lookup_idx"
            )
        ]
