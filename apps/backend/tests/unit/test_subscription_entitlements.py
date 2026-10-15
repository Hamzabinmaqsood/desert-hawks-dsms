from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from dsms.identity.models import User
from dsms.identity.platform_access import (
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_PLAN_CATALOG,
)
from dsms.organization.models import Company
from dsms.subscriptions import entitlements, services
from dsms.subscriptions.exceptions import (
    SubscriptionConflictError,
    SubscriptionValidationError,
)
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    ModuleOverrideState,
    PlanEntitlementEvent,
    SubscriptionEntitlementEvent,
    SubscriptionEntitlementEventType,
    SubscriptionModuleOverride,
    SubscriptionModuleSnapshot,
    SubscriptionStatus,
)
from dsms.subscriptions.modules import TENANT_MODULE_REGISTRY
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory, SubscriptionFactory

pytestmark = pytest.mark.django_db


def commercial_actor() -> User:
    actor = UserFactory.create()
    for capability in (MANAGE_PLAN_CATALOG, MANAGE_COMMERCIAL_SUBSCRIPTIONS):
        app_label, codename = capability.split(".", maxsplit=1)
        actor.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return actor


def policy_for(
    company: Company,
    mode: str = CompanyModulePolicyMode.LEGACY_FULL,
) -> CompanyModulePolicy:
    return CompanyModulePolicy.objects.create(company=company, mode=mode)


def test_legacy_and_missing_policy_resolve_full_catalog_and_ignore_subscription() -> None:
    company = CompanyFactory.create()
    missing = entitlements.resolve_effective_modules(company)
    assert missing.policy_mode == CompanyModulePolicyMode.LEGACY_FULL
    assert missing.policy_missing is True
    assert missing.module_ids == TENANT_MODULE_REGISTRY.legacy_default_ids

    policy_for(company)
    SubscriptionFactory.create(company=company)
    legacy = entitlements.resolve_effective_modules(company)
    assert legacy.policy_missing is False
    assert legacy.module_ids == TENANT_MODULE_REGISTRY.legacy_default_ids
    assert legacy.subscription_id is None


def test_subscription_policy_without_subscription_is_safe_empty_set() -> None:
    company = CompanyFactory.create()
    policy_for(company, CompanyModulePolicyMode.SUBSCRIPTION)

    result = entitlements.resolve_effective_modules(company)

    assert result.policy_mode == CompanyModulePolicyMode.SUBSCRIPTION
    assert result.module_ids == ()
    assert result.entitlement_revision == 0
    assert result.snapshot_initialized is False


def test_plan_defaults_are_transactional_revisioned_and_audited() -> None:
    actor = commercial_actor()
    plan = PlanFactory.create()
    desired = ("people", "client_contracts", "finance_core", "billing_receivables")

    changed = entitlements.set_plan_module_defaults(
        actor=actor,
        plan=plan,
        module_ids=reversed(desired),
        reason="Initial product set",
    )
    assert changed.entitlement_revision == 1
    assert tuple(changed.module_defaults.values_list("module_id", flat=True)) == (
        "billing_receivables",
        "client_contracts",
        "finance_core",
        "people",
    )
    assert set(changed.entitlement_events.values_list("module_id", flat=True)) == set(desired)
    assert set(changed.entitlement_events.values_list("actor_id", flat=True)) == {actor.id}

    unchanged = entitlements.set_plan_module_defaults(
        actor=actor,
        plan=plan,
        module_ids=desired,
    )
    assert unchanged.entitlement_revision == 1
    assert PlanEntitlementEvent.objects.filter(plan=plan).count() == len(desired)


def test_plan_history_failure_rolls_back_defaults_and_revision() -> None:
    actor = commercial_actor()
    plan = PlanFactory.create()
    with (
        patch.object(PlanEntitlementEvent.objects, "create", side_effect=RuntimeError("injected")),
        pytest.raises(RuntimeError, match="injected"),
    ):
        entitlements.set_plan_module_defaults(
            actor=actor,
            plan=plan,
            module_ids=("people",),
        )

    plan.refresh_from_db()
    assert plan.entitlement_revision == 0
    assert plan.module_defaults.count() == 0
    assert plan.entitlement_events.count() == 0


def test_explicit_zero_module_conversion_is_initialized_and_separated() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create(is_active=True)
    policy = policy_for(company)
    plan = PlanFactory.create()
    subscription = services.create_subscription(actor=actor, company=company, plan=plan)
    status = subscription.status

    result = entitlements.convert_company_to_subscription_entitlements(
        actor=actor,
        company=company,
        reason="Commercial conversion",
    )

    policy.refresh_from_db()
    subscription.refresh_from_db()
    company.refresh_from_db()
    assert policy.mode == CompanyModulePolicyMode.SUBSCRIPTION
    assert subscription.snapshot_initialized_at is not None
    assert subscription.snapshot_plan_entitlement_revision == 0
    assert subscription.entitlement_revision == 1
    assert subscription.module_snapshot.count() == 0
    assert result.module_ids == ()
    assert result.snapshot_initialized is True
    assert subscription.status == status
    assert company.is_active is True
    assert set(subscription.entitlement_events.values_list("event_type", flat=True)) == {
        SubscriptionEntitlementEventType.SNAPSHOT_INITIALIZED,
        SubscriptionEntitlementEventType.POLICY_CONVERTED,
    }


def test_conversion_captures_plan_and_proposed_valid_overrides() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create()
    policy_for(company)
    plan = PlanFactory.create()
    entitlements.set_plan_module_defaults(
        actor=actor,
        plan=plan,
        module_ids=("people", "finance_core"),
    )
    subscription = services.create_subscription(actor=actor, company=company, plan=plan)

    result = entitlements.convert_company_to_subscription_entitlements(
        actor=actor,
        company=company,
        overrides={"analytics": ModuleOverrideState.ENABLED},
    )

    assert result.module_ids == ("people", "finance_core", "analytics")
    assert set(subscription.module_snapshot.values_list("module_id", flat=True)) == {
        "people",
        "finance_core",
    }
    assert subscription.module_overrides.get().module_id == "analytics"
    assert set(subscription.entitlement_events.values_list("actor_id", flat=True)) == {actor.id}


def test_conversion_failure_rolls_back_policy_snapshot_and_history() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create()
    policy = policy_for(company)
    subscription = SubscriptionFactory.create(company=company)

    with (
        patch.object(
            SubscriptionEntitlementEvent.objects,
            "create",
            side_effect=RuntimeError("injected"),
        ),
        pytest.raises(RuntimeError, match="injected"),
    ):
        entitlements.convert_company_to_subscription_entitlements(
            actor=actor,
            company=company,
        )

    policy.refresh_from_db()
    subscription.refresh_from_db()
    assert policy.mode == CompanyModulePolicyMode.LEGACY_FULL
    assert subscription.snapshot_initialized_at is None
    assert subscription.entitlement_revision == 0
    assert SubscriptionModuleSnapshot.objects.filter(subscription=subscription).count() == 0
    assert SubscriptionEntitlementEvent.objects.filter(subscription=subscription).count() == 0


def test_override_enable_disable_clear_and_dependency_rejections_are_atomic() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create()
    policy_for(company)
    plan = PlanFactory.create()
    entitlements.set_plan_module_defaults(
        actor=actor,
        plan=plan,
        module_ids=(
            "people",
            "client_contracts",
            "finance_core",
            "billing_receivables",
        ),
    )
    subscription = services.create_subscription(actor=actor, company=company, plan=plan)
    entitlements.convert_company_to_subscription_entitlements(actor=actor, company=company)

    enabled = entitlements.set_subscription_module_override(
        actor=actor,
        subscription=subscription,
        module_id="analytics",
        state=ModuleOverrideState.ENABLED,
    )
    assert "analytics" in enabled.module_ids
    disabled = entitlements.set_subscription_module_override(
        actor=actor,
        subscription=subscription,
        module_id="analytics",
        state=ModuleOverrideState.DISABLED,
    )
    assert "analytics" not in disabled.module_ids
    cleared = entitlements.clear_subscription_module_override(
        actor=actor,
        subscription=subscription,
        module_id="analytics",
    )
    assert "analytics" not in cleared.module_ids
    assert not SubscriptionModuleOverride.objects.filter(
        subscription=subscription, module_id="analytics"
    ).exists()

    subscription.refresh_from_db()
    revision = subscription.entitlement_revision
    history_count = subscription.entitlement_events.count()
    with pytest.raises(SubscriptionValidationError) as missing:
        entitlements.set_subscription_module_override(
            actor=actor,
            subscription=subscription,
            module_id="security_patrol",
            state=ModuleOverrideState.ENABLED,
        )
    assert missing.value.errors["missing_dependency_ids"] == ["security_operations"]
    with pytest.raises(SubscriptionValidationError) as dependent:
        entitlements.set_subscription_module_override(
            actor=actor,
            subscription=subscription,
            module_id="finance_core",
            state=ModuleOverrideState.DISABLED,
        )
    assert dependent.value.errors["missing_dependency_ids"] == ["finance_core"]
    subscription.refresh_from_db()
    assert subscription.entitlement_revision == revision
    assert subscription.entitlement_events.count() == history_count


def test_plan_edits_are_snapshot_not_live_inheritance_and_apply_is_explicit() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create()
    policy_for(company)
    plan = PlanFactory.create()
    entitlements.set_plan_module_defaults(actor=actor, plan=plan, module_ids=("people",))
    subscription = services.create_subscription(actor=actor, company=company, plan=plan)
    entitlements.convert_company_to_subscription_entitlements(
        actor=actor,
        company=company,
        overrides={"analytics": ModuleOverrideState.DISABLED},
    )
    subscription.refresh_from_db()
    captured_revision = subscription.entitlement_revision

    entitlements.set_plan_module_defaults(
        actor=actor,
        plan=plan,
        module_ids=("people", "asset_management"),
    )
    unchanged = entitlements.resolve_effective_modules(company)
    assert unchanged.module_ids == ("people",)
    assert unchanged.entitlement_revision == captured_revision
    assert not subscription.entitlement_events.filter(
        event_type=SubscriptionEntitlementEventType.PLAN_REVISION_APPLIED
    ).exists()

    applied = entitlements.apply_plan_entitlement_revision(
        actor=actor,
        subscription=subscription,
        reason="Apply reviewed Plan change",
    )
    assert applied.module_ids == ("people", "asset_management")
    assert (
        SubscriptionModuleOverride.objects.get(
            subscription=subscription, module_id="analytics"
        ).state
        == ModuleOverrideState.DISABLED
    )
    assert (
        subscription.entitlement_events.filter(
            event_type=SubscriptionEntitlementEventType.PLAN_REVISION_APPLIED,
            actor=actor,
        ).count()
        == 1
    )


def test_invalid_preserved_override_blocks_plan_revision_application() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create()
    policy_for(company)
    plan = PlanFactory.create()
    original = ("people", "client_contracts", "security_operations", "security_patrol")
    entitlements.set_plan_module_defaults(actor=actor, plan=plan, module_ids=original)
    subscription = services.create_subscription(actor=actor, company=company, plan=plan)
    entitlements.convert_company_to_subscription_entitlements(
        actor=actor,
        company=company,
        overrides={"security_patrol": ModuleOverrideState.ENABLED},
    )
    entitlements.set_plan_module_defaults(
        actor=actor,
        plan=plan,
        module_ids=("people", "client_contracts"),
    )
    before = set(subscription.module_snapshot.values_list("module_id", flat=True))

    with pytest.raises(SubscriptionValidationError) as invalid:
        entitlements.apply_plan_entitlement_revision(actor=actor, subscription=subscription)
    assert invalid.value.errors["missing_dependency_ids"] == ["security_operations"]
    assert set(subscription.module_snapshot.values_list("module_id", flat=True)) == before


def test_inactive_plan_and_subscription_status_do_not_enforce_or_mutate_entitlements() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create()
    policy_for(company)
    plan = PlanFactory.create()
    entitlements.set_plan_module_defaults(actor=actor, plan=plan, module_ids=("people",))
    subscription = services.create_subscription(actor=actor, company=company, plan=plan)
    entitlements.convert_company_to_subscription_entitlements(actor=actor, company=company)
    services.update_plan(actor=actor, plan=plan, is_active=False)
    assert entitlements.resolve_effective_modules(company).module_ids == ("people",)

    suspended = services.transition_subscription(
        actor=actor,
        subscription=subscription,
        target_status=SubscriptionStatus.SUSPENDED,
    )
    suspended_result = entitlements.resolve_effective_modules(company)
    assert suspended_result.module_ids == ("people",)
    assert suspended_result.subscription_status == SubscriptionStatus.SUSPENDED
    terminated = services.transition_subscription(
        actor=actor,
        subscription=suspended,
        target_status=SubscriptionStatus.TERMINATED,
    )
    terminated_result = entitlements.resolve_effective_modules(company)
    assert terminated_result.module_ids == ("people",)
    assert terminated_result.subscription_status == SubscriptionStatus.TERMINATED
    assert terminated.entitlement_revision == 1


def test_subscription_policy_requires_initialized_snapshot_but_unknown_ids_never_resolve() -> None:
    company = CompanyFactory.create()
    policy_for(company, CompanyModulePolicyMode.SUBSCRIPTION)
    subscription = SubscriptionFactory.create(company=company)
    with pytest.raises(SubscriptionConflictError, match="not been initialized"):
        entitlements.resolve_effective_modules(company)

    subscription.snapshot_initialized_at = timezone.now()
    subscription.snapshot_plan_entitlement_revision = 0
    subscription.save(
        update_fields=["snapshot_initialized_at", "snapshot_plan_entitlement_revision"]
    )
    SubscriptionModuleSnapshot.objects.create(
        subscription=subscription,
        module_id="historical_unknown",
        source_plan_entitlement_revision=0,
    )
    with pytest.raises(SubscriptionValidationError) as invalid:
        entitlements.resolve_effective_modules(company)
    assert invalid.value.errors["unknown_module_ids"] == ["historical_unknown"]
