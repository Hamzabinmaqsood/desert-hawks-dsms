from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol


@dataclass(frozen=True)
class KPIProviderResult:
    value: Decimal | None
    unit: str
    source_period: tuple[str, str]
    source_count: int
    source_reference: dict[str, Any]
    is_complete: bool
    warnings: list[str] = field(default_factory=list)


class PerformanceKPIProvider(Protocol):
    def calculate(
        self, *, employee: Any, cycle: Any, kpi_definition: Any, target: Any
    ) -> KPIProviderResult: ...


class KPIProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, PerformanceKPIProvider] = {}

    def register(self, code: str, provider: PerformanceKPIProvider) -> None:
        self._providers[code.strip().upper()] = provider

    def get(self, code: str) -> PerformanceKPIProvider:
        try:
            return self._providers[code.strip().upper()]
        except KeyError as exc:
            raise LookupError(f"No deterministic KPI provider is registered for {code}.") from exc


provider_registry = KPIProviderRegistry()


class ManualKPIProvider:
    def calculate(
        self, *, employee: Any, cycle: Any, kpi_definition: Any, target: Any
    ) -> KPIProviderResult:
        return KPIProviderResult(
            value=None,
            unit=kpi_definition.unit,
            source_period=(str(cycle.period_start), str(cycle.period_end)),
            source_count=0,
            source_reference={"provider": "MANUAL", "employee_id": str(employee.id)},
            is_complete=False,
            warnings=["A human-entered factual value is required."],
        )


provider_registry.register("MANUAL", ManualKPIProvider())
