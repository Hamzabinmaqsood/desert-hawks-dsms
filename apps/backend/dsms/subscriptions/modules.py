from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from django.core.exceptions import ValidationError


class ModuleClassification(StrEnum):
    GENERAL_BUSINESS = "GENERAL_BUSINESS"
    SHARED_OPERATIONAL = "SHARED_OPERATIONAL"
    SECURITY_VERTICAL = "SECURITY_VERTICAL"


@dataclass(frozen=True)
class TenantModule:
    module_id: str
    display_name: str
    classification: ModuleClassification
    hard_dependencies: tuple[str, ...] = ()
    soft_integrations: tuple[str, ...] = ()
    legacy_default: bool = True


class ModuleRegistryError(ValueError):
    """Base error for invalid module catalog data or requested module sets."""


class DuplicateModuleIDError(ModuleRegistryError):
    pass


class UnknownModuleIDError(ModuleRegistryError):
    def __init__(self, module_ids: Iterable[str]) -> None:
        self.module_ids = tuple(sorted(set(module_ids)))
        super().__init__(f"Unknown module ID(s): {', '.join(self.module_ids)}")


class ModuleDependencyCycleError(ModuleRegistryError):
    pass


class MissingModuleDependencyError(ModuleRegistryError):
    def __init__(self, missing_dependencies: Iterable[str]) -> None:
        self.missing_dependencies = tuple(sorted(set(missing_dependencies)))
        super().__init__(
            f"Missing hard module dependency ID(s): {', '.join(self.missing_dependencies)}"
        )


class ModuleRegistry:
    """Immutable, explicitly ordered tenant product-module catalog."""

    def __init__(self, modules: Iterable[TenantModule]) -> None:
        ordered = tuple(modules)
        by_id: dict[str, TenantModule] = {}
        for module in ordered:
            if module.module_id in by_id:
                raise DuplicateModuleIDError(f"Module ID is already registered: {module.module_id}")
            by_id[module.module_id] = module
        self._modules = ordered
        self._by_id: Mapping[str, TenantModule] = MappingProxyType(by_id)
        self._validate_relations()
        self._validate_acyclic()

    def __iter__(self) -> Iterator[TenantModule]:
        return iter(self._modules)

    def __len__(self) -> int:
        return len(self._modules)

    @property
    def module_ids(self) -> tuple[str, ...]:
        return tuple(module.module_id for module in self._modules)

    @property
    def legacy_default_ids(self) -> tuple[str, ...]:
        return tuple(module.module_id for module in self._modules if module.legacy_default)

    def get(self, module_id: str) -> TenantModule:
        normalized = module_id.strip() if isinstance(module_id, str) else ""
        try:
            return self._by_id[normalized]
        except KeyError as exc:
            raise UnknownModuleIDError((normalized or str(module_id),)) from exc

    def ordered_ids(self, module_ids: Iterable[str]) -> tuple[str, ...]:
        normalized = self.normalize_ids(module_ids)
        requested = set(normalized)
        return tuple(module_id for module_id in self.module_ids if module_id in requested)

    def normalize_ids(self, module_ids: Iterable[str]) -> tuple[str, ...]:
        normalized = tuple(
            module_id.strip() if isinstance(module_id, str) else str(module_id)
            for module_id in module_ids
        )
        unknown = set(normalized) - self._by_id.keys()
        if unknown:
            raise UnknownModuleIDError(unknown)
        requested = set(normalized)
        return tuple(module_id for module_id in self.module_ids if module_id in requested)

    def transitive_hard_dependencies(self, module_id: str) -> tuple[str, ...]:
        module = self.get(module_id)
        found: set[str] = set()
        pending = list(module.hard_dependencies)
        while pending:
            dependency = pending.pop()
            if dependency in found:
                continue
            found.add(dependency)
            pending.extend(self._by_id[dependency].hard_dependencies)
        return tuple(item for item in self.module_ids if item in found)

    def validate_enabled_modules(self, module_ids: Iterable[str]) -> tuple[str, ...]:
        enabled = self.normalize_ids(module_ids)
        enabled_set = set(enabled)
        missing: set[str] = set()
        for module_id in enabled:
            missing.update(set(self.transitive_hard_dependencies(module_id)) - enabled_set)
        if missing:
            raise MissingModuleDependencyError(missing)
        return enabled

    def enabled_dependents(
        self, module_id: str, enabled_module_ids: Iterable[str]
    ) -> tuple[str, ...]:
        self.get(module_id)
        enabled = self.normalize_ids(enabled_module_ids)
        return tuple(
            candidate
            for candidate in enabled
            if candidate != module_id and module_id in self.transitive_hard_dependencies(candidate)
        )

    def _validate_relations(self) -> None:
        known = set(self._by_id)
        for module in self._modules:
            hard = set(module.hard_dependencies)
            soft = set(module.soft_integrations)
            if module.module_id in hard:
                raise ModuleRegistryError(f"Module cannot depend on itself: {module.module_id}")
            unknown = (hard | soft) - known
            if unknown:
                raise UnknownModuleIDError(unknown)

    def _validate_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(module_id: str, path: tuple[str, ...]) -> None:
            if module_id in visiting:
                cycle = " -> ".join((*path, module_id))
                raise ModuleDependencyCycleError(f"Hard dependency cycle: {cycle}")
            if module_id in visited:
                return
            visiting.add(module_id)
            for dependency in self._by_id[module_id].hard_dependencies:
                visit(dependency, (*path, module_id))
            visiting.remove(module_id)
            visited.add(module_id)

        for module_id in self.module_ids:
            visit(module_id, ())


MODULE_CATALOG = (
    TenantModule("people", "People & Employee Records", ModuleClassification.GENERAL_BUSINESS),
    TenantModule(
        "recruitment",
        "Recruitment & Onboarding",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("people",),
    ),
    TenantModule(
        "leave",
        "Leave Management",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("people",),
        soft_integrations=("payroll", "workforce_scheduling"),
    ),
    TenantModule(
        "learning",
        "Learning & Qualifications",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("people",),
        soft_integrations=("workforce_scheduling",),
    ),
    TenantModule(
        "performance",
        "Performance Management",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("people",),
        soft_integrations=("analytics",),
    ),
    TenantModule(
        "hr_case_management",
        "HR Case Management",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("people",),
        soft_integrations=("finance_core",),
    ),
    TenantModule(
        "client_contracts",
        "Clients & Contracts",
        ModuleClassification.GENERAL_BUSINESS,
        soft_integrations=("people", "billing_receivables", "client_portal"),
    ),
    TenantModule(
        "finance_core",
        "Finance & Accounting",
        ModuleClassification.GENERAL_BUSINESS,
        soft_integrations=("analytics",),
    ),
    TenantModule(
        "billing_receivables",
        "Billing & Receivables",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("client_contracts", "finance_core"),
        soft_integrations=("client_portal", "analytics"),
    ),
    TenantModule(
        "procurement_payables",
        "Procurement & Payables",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("finance_core",),
        soft_integrations=("asset_management", "analytics"),
    ),
    TenantModule(
        "payroll",
        "Payroll",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("people", "finance_core"),
        soft_integrations=("attendance", "leave"),
    ),
    TenantModule(
        "asset_management",
        "Asset Management",
        ModuleClassification.GENERAL_BUSINESS,
        soft_integrations=(
            "people",
            "client_contracts",
            "procurement_payables",
            "finance_core",
        ),
    ),
    TenantModule(
        "client_portal",
        "Client Portal",
        ModuleClassification.GENERAL_BUSINESS,
        hard_dependencies=("client_contracts",),
        soft_integrations=("billing_receivables", "security_incidents"),
    ),
    TenantModule(
        "analytics",
        "Analytics & Management Reporting",
        ModuleClassification.GENERAL_BUSINESS,
        soft_integrations=(
            "people",
            "recruitment",
            "leave",
            "learning",
            "performance",
            "hr_case_management",
            "client_contracts",
            "finance_core",
            "billing_receivables",
            "procurement_payables",
            "payroll",
            "asset_management",
            "client_portal",
            "workforce_scheduling",
            "attendance",
            "security_operations",
            "security_patrol",
            "security_supervision",
            "security_incidents",
        ),
    ),
    TenantModule(
        "workforce_scheduling",
        "Workforce Scheduling",
        ModuleClassification.SHARED_OPERATIONAL,
        hard_dependencies=("people", "security_operations"),
        soft_integrations=("leave", "learning", "attendance"),
    ),
    TenantModule(
        "attendance",
        "Attendance & Time",
        ModuleClassification.SHARED_OPERATIONAL,
        hard_dependencies=("people", "workforce_scheduling", "security_operations"),
        soft_integrations=("payroll", "leave"),
    ),
    TenantModule(
        "security_operations",
        "Security Operations",
        ModuleClassification.SECURITY_VERTICAL,
        hard_dependencies=("people", "client_contracts"),
        soft_integrations=("workforce_scheduling", "learning", "asset_management"),
    ),
    TenantModule(
        "security_patrol",
        "Patrol Management",
        ModuleClassification.SECURITY_VERTICAL,
        hard_dependencies=("security_operations",),
        soft_integrations=("workforce_scheduling", "security_incidents"),
    ),
    TenantModule(
        "security_supervision",
        "Security Supervision",
        ModuleClassification.SECURITY_VERTICAL,
        hard_dependencies=("security_operations",),
        soft_integrations=("attendance", "security_incidents"),
    ),
    TenantModule(
        "security_incidents",
        "Security Incidents & SOS",
        ModuleClassification.SECURITY_VERTICAL,
        hard_dependencies=("security_operations",),
        soft_integrations=(
            "security_patrol",
            "security_supervision",
            "attendance",
            "client_portal",
        ),
    ),
)

TENANT_MODULE_REGISTRY = ModuleRegistry(MODULE_CATALOG)


def validate_registered_module_id(module_id: str) -> None:
    try:
        TENANT_MODULE_REGISTRY.get(module_id)
    except UnknownModuleIDError as exc:
        raise ValidationError(f"Unknown tenant module ID: {module_id}") from exc
