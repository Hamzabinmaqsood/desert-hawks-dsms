from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.finance.services import next_document_number
from dsms.subscriptions.enforcement import (
    company_has_module,
    require_company_module,
    requires_company_module,
)

from .enums import ExecutiveHealthStatus, MetricDirection, SnapshotStatus
from .models import AnalyticsSnapshot, AnalyticsSnapshotValue, ManagementKPI, ManagementReport
from .providers import AnalyticsMetricResult, _missing, registry


def calculate_metric(
    *, metric_definition: Any, period_start: date, period_end: date, **dimensions: Any
) -> AnalyticsMetricResult:
    if not metric_definition.is_active:
        raise ValidationError("Inactive analytics metrics cannot be calculated.")
    company = dimensions.get("company")
    if company is not None:
        require_company_module(company, "analytics")
        source_module_id = registry.source_module_id(metric_definition.provider_code)
        if not company_has_module(company, source_module_id):
            return _missing(
                period_start,
                period_end,
                f"Source module {source_module_id} is not enabled.",
            )
    supported = {
        "company": metric_definition.supports_company,
        "region": metric_definition.supports_region,
        "branch": metric_definition.supports_branch,
        "client": metric_definition.supports_client,
        "contract": metric_definition.supports_contract,
        "site": metric_definition.supports_site,
        "department": metric_definition.supports_department,
    }
    unsupported = [
        name
        for name, value in dimensions.items()
        if value is not None and name in supported and not supported[name]
    ]
    if unsupported:
        raise ValidationError(f"Metric does not support dimensions: {', '.join(unsupported)}")
    return registry.get(metric_definition.provider_code).calculate(
        metric_definition=metric_definition,
        period_start=period_start,
        period_end=period_end,
        **dimensions,
    )


def evaluate_kpi_health(*, kpi: ManagementKPI, value: Decimal | None) -> str:
    if value is None:
        return ExecutiveHealthStatus.NOT_AVAILABLE
    warning, critical = kpi.warning_threshold, kpi.critical_threshold
    if warning is None or critical is None:
        return ExecutiveHealthStatus.NOT_AVAILABLE
    if kpi.direction == MetricDirection.HIGHER_IS_BETTER:
        if value <= critical:
            return ExecutiveHealthStatus.CRITICAL
        if value <= warning:
            return ExecutiveHealthStatus.ATTENTION
        return ExecutiveHealthStatus.GOOD
    if kpi.direction == MetricDirection.LOWER_IS_BETTER:
        if value >= critical:
            return ExecutiveHealthStatus.CRITICAL
        if value >= warning:
            return ExecutiveHealthStatus.ATTENTION
        return ExecutiveHealthStatus.GOOD
    return ExecutiveHealthStatus.WATCH


def compare_metric_periods(
    *, current: Decimal | None, previous: Decimal | None
) -> dict[str, Decimal | None]:
    if current is None or previous is None:
        absolute = percentage = None
    else:
        absolute = current - previous
        percentage = None if previous == 0 else absolute / abs(previous) * Decimal("100")
    return {
        "current": current,
        "previous": previous,
        "absolute_change": absolute,
        "percentage_change": percentage,
    }


@transaction.atomic
@requires_company_module("analytics", argument="snapshot")
def calculate_snapshot(
    *, snapshot: AnalyticsSnapshot, metric_definitions: Any, actor: Any
) -> AnalyticsSnapshot:
    locked = AnalyticsSnapshot.objects.select_for_update().get(pk=snapshot.pk)
    if locked.status != SnapshotStatus.DRAFT:
        raise ValidationError("Only draft snapshots can be calculated.")
    values = []
    for definition in metric_definitions:
        result = calculate_metric(
            metric_definition=definition,
            period_start=locked.period_start,
            period_end=locked.period_end,
            company=locked.company,
        )
        payload: dict[str, Any] = {"decimal_value": None, "integer_value": None, "text_value": ""}
        if isinstance(result.value, int):
            payload["integer_value"] = result.value
        elif isinstance(result.value, Decimal):
            payload["decimal_value"] = result.value
        elif isinstance(result.value, str):
            payload["text_value"] = result.value
        else:
            payload["text_value"] = "NOT_AVAILABLE"
        values.append(
            AnalyticsSnapshotValue(
                snapshot=locked,
                metric_definition=definition,
                company=locked.company,
                numerator=result.numerator,
                denominator=result.denominator,
                source_count=result.source_count,
                warnings=result.warnings,
                **payload,
            )
        )
    AnalyticsSnapshotValue.objects.bulk_create(values)
    locked.status = SnapshotStatus.CALCULATED
    locked.calculated_at = timezone.now()
    locked.generated_by = actor
    locked.save(update_fields=["status", "calculated_at", "generated_by", "updated_at"])
    return locked


@transaction.atomic
@requires_company_module("analytics", argument="snapshot")
def publish_snapshot(*, snapshot: AnalyticsSnapshot, actor: Any) -> AnalyticsSnapshot:
    locked = AnalyticsSnapshot.objects.select_for_update().get(pk=snapshot.pk)
    if locked.status != SnapshotStatus.VALIDATED:
        raise ValidationError("Only a separately validated snapshot can be published.")
    if locked.generated_by_id == actor.id or locked.validated_by_id == actor.id:
        raise ValidationError("Snapshot publication requires maker/checker separation.")
    locked.status = SnapshotStatus.PUBLISHED
    locked.published_at = timezone.now()
    locked.save(update_fields=["status", "published_at", "updated_at"])
    record_audit_event(
        action="ANALYTICS_SNAPSHOT_PUBLISHED",
        category=AuditCategory.ANALYTICS,
        severity=AuditSeverity.HIGH,
        summary="Analytics snapshot published.",
        actor_user=actor,
        company=locked.company,
        source_object=locked,
    )
    return locked


@transaction.atomic
@requires_company_module("analytics", argument="snapshot")
def validate_snapshot(*, snapshot: AnalyticsSnapshot, actor: Any) -> AnalyticsSnapshot:
    locked = (
        AnalyticsSnapshot.objects.select_for_update().prefetch_related("values").get(pk=snapshot.pk)
    )
    if locked.status != SnapshotStatus.CALCULATED:
        raise ValidationError("Only calculated snapshots can be validated.")
    if locked.generated_by_id == actor.id:
        raise ValidationError("Snapshot generator cannot validate their own snapshot.")
    if not locked.values.exists():
        raise ValidationError("Snapshot has no calculated metric values.")
    unavailable = [
        value.metric_definition_id
        for value in locked.values.all()
        if value.text_value == "NOT_AVAILABLE"
    ]
    if unavailable:
        raise ValidationError(
            {"metrics": [f"Required metrics are unavailable: {len(unavailable)}"]}
        )
    locked.status = SnapshotStatus.VALIDATED
    locked.validated_by = actor
    locked.validated_at = timezone.now()
    locked.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])
    record_audit_event(
        action="ANALYTICS_SNAPSHOT_VALIDATED",
        category=AuditCategory.ANALYTICS,
        summary="Analytics snapshot validated.",
        actor_user=actor,
        company=locked.company,
        source_object=locked,
    )
    return locked


@transaction.atomic
@requires_company_module("analytics", argument="snapshot")
def return_snapshot_for_recalculation(
    *, snapshot: AnalyticsSnapshot, actor: Any, reason: str
) -> AnalyticsSnapshot:
    locked = AnalyticsSnapshot.objects.select_for_update().get(pk=snapshot.pk)
    if locked.status not in {SnapshotStatus.CALCULATED, SnapshotStatus.VALIDATED}:
        raise ValidationError("Snapshot cannot be returned from its current state.")
    if not reason.strip():
        raise ValidationError("A recalculation reason is required.")
    locked.values.all().delete()
    locked.status = SnapshotStatus.DRAFT
    locked.validated_by = None
    locked.validated_at = None
    locked.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])
    return locked


@transaction.atomic
@requires_company_module("analytics", argument="original")
def create_snapshot_revision(
    *, original: AnalyticsSnapshot, generated_by: Any
) -> AnalyticsSnapshot:
    if original.status not in {SnapshotStatus.PUBLISHED, SnapshotStatus.STALE}:
        raise ValidationError("Only published or stale snapshots can be revised.")
    revision = AnalyticsSnapshot.objects.create(
        company=original.company,
        snapshot_type=original.snapshot_type,
        period_type=original.period_type,
        period_start=original.period_start,
        period_end=original.period_end,
        as_of_datetime=timezone.now(),
        generated_by=generated_by,
        supersedes=original,
    )
    record_audit_event(
        action="ANALYTICS_SNAPSHOT_REVISED",
        category=AuditCategory.ANALYTICS,
        summary="Analytics snapshot revision created.",
        actor_user=generated_by,
        company=original.company,
        source_object=revision,
        metadata_safe={"supersedes_id": str(original.id)},
    )
    return revision


@transaction.atomic
@requires_company_module("analytics", argument="company")
def create_management_report(
    *, company: Any, snapshot: AnalyticsSnapshot, report_type: str, title: str, actor: Any
) -> ManagementReport:
    if snapshot.status != SnapshotStatus.PUBLISHED or snapshot.company_id != company.id:
        raise ValidationError("A published company snapshot is required.")
    number = next_document_number(company=company, prefix="MIS", year=snapshot.period_end.year)
    report = ManagementReport.objects.create(
        company=company,
        report_number=number,
        report_type=report_type,
        title=title,
        period_start=snapshot.period_start,
        period_end=snapshot.period_end,
        snapshot=snapshot,
        generated_by=actor,
    )
    record_audit_event(
        action="MANAGEMENT_REPORT_GENERATED",
        category=AuditCategory.ANALYTICS,
        summary="Management report generated.",
        actor_user=actor,
        company=company,
        source_object=report,
        object_reference=report.report_number,
    )
    return report
