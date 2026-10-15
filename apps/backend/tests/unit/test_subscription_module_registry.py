import pytest

from dsms.subscriptions.modules import (
    MODULE_CATALOG,
    TENANT_MODULE_REGISTRY,
    DuplicateModuleIDError,
    MissingModuleDependencyError,
    ModuleClassification,
    ModuleDependencyCycleError,
    ModuleRegistry,
    ModuleRegistryError,
    TenantModule,
    UnknownModuleIDError,
)

EXPECTED_MODULE_IDS = (
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
    "analytics",
    "workforce_scheduling",
    "attendance",
    "security_operations",
    "security_patrol",
    "security_supervision",
    "security_incidents",
)


def test_catalog_has_exact_stable_ids_metadata_and_legacy_defaults() -> None:
    assert TENANT_MODULE_REGISTRY.module_ids == EXPECTED_MODULE_IDS
    assert tuple(module.module_id for module in MODULE_CATALOG) == EXPECTED_MODULE_IDS
    assert TENANT_MODULE_REGISTRY.legacy_default_ids == EXPECTED_MODULE_IDS
    assert {module.classification for module in TENANT_MODULE_REGISTRY} == {
        ModuleClassification.GENERAL_BUSINESS,
        ModuleClassification.SHARED_OPERATIONAL,
        ModuleClassification.SECURITY_VERTICAL,
    }
    assert all(module.display_name and module.legacy_default for module in TENANT_MODULE_REGISTRY)


def test_authoritative_dependencies_are_deterministic_and_transitive() -> None:
    assert TENANT_MODULE_REGISTRY.get("billing_receivables").hard_dependencies == (
        "client_contracts",
        "finance_core",
    )
    assert TENANT_MODULE_REGISTRY.get("workforce_scheduling").hard_dependencies == (
        "people",
        "security_operations",
    )
    assert TENANT_MODULE_REGISTRY.transitive_hard_dependencies("attendance") == (
        "people",
        "client_contracts",
        "workforce_scheduling",
        "security_operations",
    )
    assert TENANT_MODULE_REGISTRY.ordered_ids(reversed(EXPECTED_MODULE_IDS)) == EXPECTED_MODULE_IDS


def test_unknown_and_missing_dependencies_are_rejected_without_auto_enable() -> None:
    with pytest.raises(UnknownModuleIDError) as unknown:
        TENANT_MODULE_REGISTRY.get("not_a_module")
    assert unknown.value.module_ids == ("not_a_module",)

    with pytest.raises(MissingModuleDependencyError) as missing:
        TENANT_MODULE_REGISTRY.validate_enabled_modules(("security_patrol",))
    assert missing.value.missing_dependencies == (
        "client_contracts",
        "people",
        "security_operations",
    )


def test_invalid_disable_reports_all_enabled_transitive_dependents() -> None:
    enabled = (
        "people",
        "client_contracts",
        "finance_core",
        "billing_receivables",
        "procurement_payables",
        "payroll",
    )
    assert TENANT_MODULE_REGISTRY.enabled_dependents("finance_core", enabled) == (
        "billing_receivables",
        "procurement_payables",
        "payroll",
    )


def test_registry_initialization_rejects_duplicate_unknown_self_and_cycles() -> None:
    general = ModuleClassification.GENERAL_BUSINESS
    with pytest.raises(DuplicateModuleIDError):
        ModuleRegistry((TenantModule("a", "A", general), TenantModule("a", "B", general)))
    with pytest.raises(UnknownModuleIDError):
        ModuleRegistry((TenantModule("a", "A", general, hard_dependencies=("missing",)),))
    with pytest.raises(ModuleRegistryError, match="itself"):
        ModuleRegistry((TenantModule("a", "A", general, hard_dependencies=("a",)),))
    with pytest.raises(ModuleDependencyCycleError):
        ModuleRegistry(
            (
                TenantModule("a", "A", general, hard_dependencies=("b",)),
                TenantModule("b", "B", general, hard_dependencies=("a",)),
            )
        )
