from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from dsms.analytics.enums import (
    AnalyticsPeriodType,
    ExecutiveHealthStatus,
    MetricAggregation,
    MetricCategory,
    MetricDirection,
    MetricValueType,
    SnapshotStatus,
)
from dsms.analytics.models import (
    AnalyticsMetricDefinition,
    AnalyticsSnapshot,
    AnalyticsSnapshotValue,
)
from dsms.analytics.providers import (
    AnalyticsMetricResult,
    InvoiceValueProvider,
    MetricProviderRegistry,
    WorkforceHeadcountProvider,
)
from dsms.analytics.services import (
    calculate_metric,
    calculate_snapshot,
    compare_metric_periods,
    create_management_report,
    create_snapshot_revision,
    evaluate_kpi_health,
    publish_snapshot,
    return_snapshot_for_recalculation,
    validate_snapshot,
)
from dsms.audit.models import AuditEvent
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory
from tests.unit.test_billing_core import billing_graph, make_invoice

pytestmark = pytest.mark.django_db


class FixedProvider:
    def __init__(self, value: Decimal | int | str | None = Decimal("12.5")) -> None:
        self.value = value

    def calculate(
        self,
        *,
        metric_definition: Any,
        period_start: date,
        period_end: date,
        **dimensions: Any,
    ) -> AnalyticsMetricResult:
        return AnalyticsMetricResult(
            self.value,
            Decimal("25"),
            Decimal("2"),
            "units",
            2,
            period_start,
            period_end,
            timezone.now(),
        )


def metric_definition(**overrides: Any) -> AnalyticsMetricDefinition:
    values = {
        "code": "TEST.METRIC",
        "name": "Test metric",
        "description": "Current implemented metric behavior",
        "category": MetricCategory.EXECUTIVE,
        "value_type": MetricValueType.DECIMAL,
        "aggregation": MetricAggregation.SUM,
        "direction": MetricDirection.HIGHER_IS_BETTER,
        "provider_code": "test.fixed",
    }
    values.update(overrides)
    return AnalyticsMetricDefinition.objects.create(**values)


def snapshot(**overrides: Any) -> AnalyticsSnapshot:
    values = {
        "company": CompanyFactory.create(),
        "snapshot_type": "EXECUTIVE",
        "period_type": AnalyticsPeriodType.MONTH,
        "period_start": date(2026, 1, 1),
        "period_end": date(2026, 1, 31),
        "as_of_datetime": timezone.now(),
    }
    values.update(overrides)
    return AnalyticsSnapshot.objects.create(**values)


def test_registry_allowlist_and_metric_dimension_guards() -> None:
    registry = MetricProviderRegistry()
    provider = FixedProvider()
    registry.register("  TEST.Provider ", provider)
    assert registry.get("test.provider") is provider
    with pytest.raises(LookupError, match="not allowlisted"):
        registry.get("unknown")

    inactive = cast(Any, SimpleNamespace(is_active=False))
    with pytest.raises(ValidationError, match="Inactive"):
        calculate_metric(
            metric_definition=inactive,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
        )

    definition = metric_definition(supports_branch=False)
    with pytest.raises(ValidationError, match="branch"):
        calculate_metric(
            metric_definition=definition,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            branch=object(),
        )


@pytest.mark.parametrize(
    ("direction", "value", "expected"),
    [
        (MetricDirection.HIGHER_IS_BETTER, Decimal("4"), ExecutiveHealthStatus.CRITICAL),
        (MetricDirection.HIGHER_IS_BETTER, Decimal("7"), ExecutiveHealthStatus.ATTENTION),
        (MetricDirection.HIGHER_IS_BETTER, Decimal("12"), ExecutiveHealthStatus.GOOD),
        (MetricDirection.LOWER_IS_BETTER, Decimal("12"), ExecutiveHealthStatus.CRITICAL),
        (MetricDirection.LOWER_IS_BETTER, Decimal("7"), ExecutiveHealthStatus.ATTENTION),
        (MetricDirection.LOWER_IS_BETTER, Decimal("4"), ExecutiveHealthStatus.GOOD),
        (MetricDirection.INFORMATIONAL, Decimal("7"), ExecutiveHealthStatus.WATCH),
    ],
)
def test_kpi_health_boundaries(direction: str, value: Decimal, expected: str) -> None:
    kpi = cast(
        Any,
        SimpleNamespace(
            warning_threshold=Decimal("8")
            if direction == MetricDirection.HIGHER_IS_BETTER
            else Decimal("6"),
            critical_threshold=Decimal("5")
            if direction == MetricDirection.HIGHER_IS_BETTER
            else Decimal("10"),
            direction=direction,
        ),
    )
    assert evaluate_kpi_health(kpi=kpi, value=value) == expected


def test_kpi_health_and_period_comparison_not_available_edges() -> None:
    kpi = cast(
        Any,
        SimpleNamespace(
            warning_threshold=None,
            critical_threshold=None,
            direction=MetricDirection.HIGHER_IS_BETTER,
        ),
    )
    assert evaluate_kpi_health(kpi=kpi, value=None) == ExecutiveHealthStatus.NOT_AVAILABLE
    assert evaluate_kpi_health(kpi=kpi, value=Decimal("1")) == ExecutiveHealthStatus.NOT_AVAILABLE
    assert compare_metric_periods(current=Decimal("12"), previous=Decimal("8")) == {
        "current": Decimal("12"),
        "previous": Decimal("8"),
        "absolute_change": Decimal("4"),
        "percentage_change": Decimal("50"),
    }
    assert (
        compare_metric_periods(current=Decimal("2"), previous=Decimal("0"))["percentage_change"]
        is None
    )
    assert compare_metric_periods(current=None, previous=Decimal("1"))["absolute_change"] is None


def test_workforce_provider_requires_company_and_counts_period_employees() -> None:
    provider = WorkforceHeadcountProvider()
    missing = provider.calculate(
        metric_definition=object(),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )
    assert missing.value is None
    assert missing.data_quality == "NOT_AVAILABLE"
    assert "Company" in missing.warnings[0]

    company = CompanyFactory.create()
    EmployeeFactory.create(company=company, joining_date=date(2025, 1, 1))
    EmployeeFactory.create(company=company, joining_date=date(2027, 1, 1))
    result = provider.calculate(
        metric_definition=object(),
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
        company=company,
    )
    assert result.value == 1
    assert result.source_count == 1


@pytest.mark.parametrize(
    ("value", "field", "expected"),
    [
        (12, "integer_value", 12),
        (Decimal("3.5"), "decimal_value", Decimal("3.5")),
        ("explainable", "text_value", "explainable"),
        (None, "text_value", "NOT_AVAILABLE"),
    ],
)
def test_snapshot_calculation_stores_typed_explainable_values(
    monkeypatch: pytest.MonkeyPatch, value: object, field: str, expected: object
) -> None:
    item = snapshot()
    definition = metric_definition(code=f"TEST.{field}")
    monkeypatch.setattr(
        "dsms.analytics.services.registry.get",
        lambda code: FixedProvider(cast(Decimal | int | str | None, value)),
    )
    actor = UserFactory.create()

    calculated = calculate_snapshot(snapshot=item, metric_definitions=[definition], actor=actor)

    stored = AnalyticsSnapshotValue.objects.get(snapshot=calculated)
    assert calculated.status == SnapshotStatus.CALCULATED
    assert getattr(stored, field) == expected
    assert stored.numerator == Decimal("25")
    assert stored.denominator == Decimal("2")
    assert stored.source_count == 2
    with pytest.raises(ValidationError, match="Only draft"):
        calculate_snapshot(snapshot=calculated, metric_definitions=[], actor=actor)


def test_snapshot_maker_checker_validation_publication_and_revision() -> None:
    generator, validator, publisher = UserFactory.create_batch(3)
    item = snapshot(generated_by=generator, status=SnapshotStatus.CALCULATED)
    definition = metric_definition()
    AnalyticsSnapshotValue.objects.create(
        snapshot=item, metric_definition=definition, company=item.company, integer_value=2
    )
    with pytest.raises(ValidationError, match="generator"):
        validate_snapshot(snapshot=item, actor=generator)

    validated = validate_snapshot(snapshot=item, actor=validator)
    assert validated.status == SnapshotStatus.VALIDATED
    with pytest.raises(ValidationError, match="maker/checker"):
        publish_snapshot(snapshot=validated, actor=validator)

    published = publish_snapshot(snapshot=validated, actor=publisher)
    assert published.status == SnapshotStatus.PUBLISHED
    assert AuditEvent.objects.filter(action="ANALYTICS_SNAPSHOT_PUBLISHED").exists()
    revision = create_snapshot_revision(original=published, generated_by=generator)
    assert revision.supersedes == published
    assert revision.status == SnapshotStatus.DRAFT
    assert AuditEvent.objects.filter(
        action="ANALYTICS_SNAPSHOT_REVISED", source_object_id=str(revision.id)
    ).exists()


def test_snapshot_validation_and_recalculation_guards() -> None:
    generator, validator = UserFactory.create_batch(2)
    item = snapshot(generated_by=generator, status=SnapshotStatus.CALCULATED)
    with pytest.raises(ValidationError, match="no calculated"):
        validate_snapshot(snapshot=item, actor=validator)
    definition = metric_definition()
    AnalyticsSnapshotValue.objects.create(
        snapshot=item,
        metric_definition=definition,
        company=item.company,
        text_value="NOT_AVAILABLE",
    )
    with pytest.raises(ValidationError, match="unavailable"):
        validate_snapshot(snapshot=item, actor=validator)
    with pytest.raises(ValidationError, match="reason"):
        return_snapshot_for_recalculation(snapshot=item, actor=validator, reason=" ")
    returned = return_snapshot_for_recalculation(
        snapshot=item, actor=validator, reason="Source corrected"
    )
    assert returned.status == SnapshotStatus.DRAFT
    assert not returned.values.exists()
    with pytest.raises(ValidationError, match="published or stale"):
        create_snapshot_revision(original=returned, generated_by=generator)


def test_management_report_requires_published_company_snapshot_and_is_audited() -> None:
    actor = UserFactory.create()
    item = snapshot(status=SnapshotStatus.DRAFT)
    with pytest.raises(ValidationError, match="published company snapshot"):
        create_management_report(
            company=item.company,
            snapshot=item,
            report_type="MONTHLY_EXECUTIVE",
            title="August report",
            actor=actor,
        )
    item.status = SnapshotStatus.PUBLISHED
    item.save(update_fields=["status"])
    report = create_management_report(
        company=item.company,
        snapshot=item,
        report_type="MONTHLY_EXECUTIVE",
        title="August report",
        actor=actor,
    )
    assert report.report_number.startswith("MIS-")
    assert report.snapshot == item
    event = AuditEvent.objects.get(action="MANAGEMENT_REPORT_GENERATED")
    assert event.actor_user == actor
    assert event.source_object_id == str(report.id)


def test_invoice_provider_blocks_mixed_currency_and_reports_single_currency_total() -> None:
    graph = billing_graph()
    first = make_invoice(graph)
    first.status = "ISSUED"
    first.save(update_fields=["status"])
    definition = cast(Any, SimpleNamespace(currency=""))
    provider = InvoiceValueProvider()
    result = provider.calculate(
        metric_definition=definition,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        company=graph["company"],
    )
    assert result.value == Decimal("209")
    assert result.unit == "PKR"

    second = make_invoice(graph)
    second.status = "ISSUED"
    second.currency = "USD"
    second.save(update_fields=["status", "currency"])
    mixed = provider.calculate(
        metric_definition=definition,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        company=graph["company"],
    )
    assert mixed.value is None
    assert mixed.data_quality == "NOT_AVAILABLE"
    assert "Multiple currencies" in mixed.warnings[0]
