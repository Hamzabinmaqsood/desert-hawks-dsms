from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from django.db.models import Sum
from django.utils import timezone


@dataclass(frozen=True)
class AnalyticsMetricResult:
    value: Decimal | int | str | None
    numerator: Decimal | None
    denominator: Decimal | None
    unit: str
    source_count: int
    source_period_start: date
    source_period_end: date
    calculated_at: Any
    warnings: list[str] = field(default_factory=list)
    data_quality: str = "COMPLETE"
    metadata_safe: dict[str, Any] = field(default_factory=dict)


class AnalyticsMetricProvider(Protocol):
    def calculate(
        self,
        *,
        metric_definition: Any,
        period_start: date,
        period_end: date,
        **dimensions: Any,
    ) -> AnalyticsMetricResult: ...


class MetricProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, AnalyticsMetricProvider] = {}

    def register(self, code: str, provider: AnalyticsMetricProvider) -> None:
        self._providers[code.strip().lower()] = provider

    def get(self, code: str) -> AnalyticsMetricProvider:
        try:
            return self._providers[code.strip().lower()]
        except KeyError as exc:
            raise LookupError(f"Analytics provider {code!r} is not allowlisted.") from exc


registry = MetricProviderRegistry()


class WorkforceHeadcountProvider:
    def calculate(
        self, *, metric_definition: Any, period_start: date, period_end: date, **dimensions: Any
    ) -> AnalyticsMetricResult:
        from dsms.deployment.tenant_queries import consistent_employees
        from dsms.workforce.models import Employee

        company = dimensions.get("company")
        if company is None:
            return _missing(period_start, period_end, "Company dimension is required.")
        qs = consistent_employees(
            Employee.objects.filter(company=company, joining_date__lte=period_end)
        ).filter(models.Q(exit_date__isnull=True) | models.Q(exit_date__gte=period_start))
        for name in ("branch", "department"):
            value = dimensions.get(name)
            if value is not None:
                qs = qs.filter(**{name: value})
        count = qs.count()
        return AnalyticsMetricResult(
            count, None, None, "employees", count, period_start, period_end, timezone.now()
        )


class InvoiceValueProvider:
    def calculate(
        self, *, metric_definition: Any, period_start: date, period_end: date, **dimensions: Any
    ) -> AnalyticsMetricResult:
        from dsms.billing.api.security import consistent_queryset
        from dsms.billing.models import ClientInvoice

        company = dimensions.get("company")
        qs = consistent_queryset(
            ClientInvoice.objects.filter(
                company=company, invoice_date__range=(period_start, period_end)
            )
        ).exclude(status__in=["DRAFT", "CANCELLED", "VOIDED"])
        currency = metric_definition.currency
        if currency:
            qs = qs.filter(currency=currency)
        currencies = list(qs.values_list("currency", flat=True).distinct()[:2])
        if len(currencies) > 1:
            return _missing(
                period_start,
                period_end,
                "Multiple currencies cannot be summed without approved FX conversion.",
            )
        total = qs.aggregate(total=Sum("total_amount"))["total"]
        return AnalyticsMetricResult(
            total or Decimal("0"),
            None,
            None,
            currency or (currencies[0] if currencies else ""),
            qs.count(),
            period_start,
            period_end,
            timezone.now(),
        )


class CollectionsProvider:
    def calculate(
        self, *, metric_definition: Any, period_start: date, period_end: date, **dimensions: Any
    ) -> AnalyticsMetricResult:
        from dsms.billing.api.security import consistent_queryset
        from dsms.billing.models import ClientReceipt

        qs = consistent_queryset(
            ClientReceipt.objects.filter(
                company=dimensions.get("company"),
                received_at__date__range=(period_start, period_end),
            )
        ).exclude(status__in=["DRAFT", "CANCELLED", "REVERSED"])
        if metric_definition.currency:
            qs = qs.filter(currency=metric_definition.currency)
        currencies = list(qs.values_list("currency", flat=True).distinct()[:2])
        if len(currencies) > 1:
            return _missing(
                period_start,
                period_end,
                "Multiple currencies cannot be summed without approved FX conversion.",
            )
        total = qs.aggregate(total=Sum("amount"))["total"]
        return AnalyticsMetricResult(
            total or Decimal("0"),
            None,
            None,
            metric_definition.currency or (currencies[0] if currencies else ""),
            qs.count(),
            period_start,
            period_end,
            timezone.now(),
        )


class OutstandingARProvider:
    def calculate(
        self, *, metric_definition: Any, period_start: date, period_end: date, **dimensions: Any
    ) -> AnalyticsMetricResult:
        from dsms.billing.api.security import consistent_queryset
        from dsms.billing.models import ClientInvoice

        qs = consistent_queryset(
            ClientInvoice.objects.filter(
                company=dimensions.get("company"),
                invoice_date__lte=period_end,
                balance_due__gt=0,
            )
        ).exclude(status__in=["CANCELLED", "VOIDED"])
        if metric_definition.currency:
            qs = qs.filter(currency=metric_definition.currency)
        currencies = list(qs.values_list("currency", flat=True).distinct()[:2])
        if len(currencies) > 1:
            return _missing(
                period_start, period_end, "Outstanding AR contains multiple currencies."
            )
        total = qs.aggregate(total=Sum("balance_due"))["total"]
        return AnalyticsMetricResult(
            total or Decimal("0"),
            None,
            None,
            metric_definition.currency or (currencies[0] if currencies else ""),
            qs.count(),
            period_start,
            period_end,
            timezone.now(),
        )


def _missing(period_start: date, period_end: date, warning: str) -> AnalyticsMetricResult:
    return AnalyticsMetricResult(
        None,
        None,
        None,
        "",
        0,
        period_start,
        period_end,
        timezone.now(),
        [warning],
        "NOT_AVAILABLE",
    )


from django.db import models  # noqa: E402

registry.register("workforce.total_employees", WorkforceHeadcountProvider())
registry.register("finance.invoice_value", InvoiceValueProvider())
registry.register("finance.collections", CollectionsProvider())
registry.register("finance.outstanding_ar", OutstandingARProvider())
