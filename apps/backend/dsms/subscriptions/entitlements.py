from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from dsms.identity.models import User
from dsms.identity.platform_access import (
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_PLAN_CATALOG,
    has_platform_capability,
)
from dsms.organization.models import Company

from .exceptions import (
    SubscriptionAuthorizationError,
    SubscriptionConflictError,
    SubscriptionValidationError,
)
from .models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    ModuleOverrideState,
    Plan,
    PlanEntitlementEvent,
    PlanEntitlementEventType,
    PlanModuleDefault,
    Subscription,
    SubscriptionEntitlementEvent,
    SubscriptionEntitlementEventType,
    SubscriptionModuleOverride,
    SubscriptionModuleSnapshot,
)
from .modules import (
    TENANT_MODULE_REGISTRY,
    MissingModuleDependencyError,
    UnknownModuleIDError,
)


@dataclass(frozen=True)
class EffectiveModuleResult:
    company_id: UUID
    policy_mode: str
    module_ids: tuple[str, ...]
    entitlement_revision: int
    subscription_id: UUID | None = None
    subscription_status: str | None = None
    snapshot_plan_entitlement_revision: int | None = None
    snapshot_initialized: bool = False
    policy_missing: bool = False


def _require(actor: User, capability: str) -> None:
    if not has_platform_capability(actor, capability):
        raise SubscriptionAuthorizationError(
            "The required platform commercial-subscription permission is missing."
        )


def _normalized_reason(reason: str) -> str:
    normalized = reason.strip()
    if len(normalized) > 255:
        raise SubscriptionValidationError({"reason": ["Reason must not exceed 255 characters."]})
    return normalized


def _validated_module_ids(module_ids: Iterable[str]) -> tuple[str, ...]:
    try:
        return TENANT_MODULE_REGISTRY.validate_enabled_modules(module_ids)
    except UnknownModuleIDError as exc:
        raise SubscriptionValidationError({"unknown_module_ids": list(exc.module_ids)}) from exc
    except MissingModuleDependencyError as exc:
        raise SubscriptionValidationError(
            {"missing_dependency_ids": list(exc.missing_dependencies)}
        ) from exc


def _known_module_id(module_id: str) -> str:
    try:
        return TENANT_MODULE_REGISTRY.get(module_id).module_id
    except UnknownModuleIDError as exc:
        raise SubscriptionValidationError({"unknown_module_ids": list(exc.module_ids)}) from exc


def _normalized_overrides(overrides: Mapping[str, str] | None) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for raw_module_id, state in (overrides or {}).items():
        module_id = _known_module_id(raw_module_id)
        if state not in ModuleOverrideState.values:
            raise SubscriptionValidationError(
                {"override_state": [f"Unknown override state for {module_id}: {state}"]}
            )
        normalized[module_id] = state
    return normalized


def _effective_set(snapshot: Iterable[str], overrides: Mapping[str, str]) -> tuple[str, ...]:
    proposed = set(snapshot)
    for module_id, state in overrides.items():
        if state == ModuleOverrideState.ENABLED:
            proposed.add(module_id)
        else:
            proposed.discard(module_id)
    return _validated_module_ids(proposed)


def _subscription_sets(subscription: Subscription) -> tuple[tuple[str, ...], dict[str, str]]:
    try:
        snapshot = TENANT_MODULE_REGISTRY.normalize_ids(
            subscription.module_snapshot.values_list("module_id", flat=True)
        )
    except UnknownModuleIDError as exc:
        raise SubscriptionValidationError({"unknown_module_ids": list(exc.module_ids)}) from exc
    raw_overrides = dict(subscription.module_overrides.values_list("module_id", "state"))
    overrides = _normalized_overrides(raw_overrides)
    return snapshot, overrides


def resolve_effective_modules(company: Company) -> EffectiveModuleResult:
    """Resolve commercial module data without enforcing it against runtime APIs."""

    try:
        policy = CompanyModulePolicy.objects.only("mode").get(company=company)
        policy_missing = False
    except CompanyModulePolicy.DoesNotExist:
        policy = None
        policy_missing = True

    if policy is None or policy.mode == CompanyModulePolicyMode.LEGACY_FULL:
        return EffectiveModuleResult(
            company_id=company.pk,
            policy_mode=CompanyModulePolicyMode.LEGACY_FULL,
            module_ids=TENANT_MODULE_REGISTRY.legacy_default_ids,
            entitlement_revision=0,
            policy_missing=policy_missing,
        )

    try:
        subscription = Subscription.objects.get(company=company)
    except Subscription.DoesNotExist:
        return EffectiveModuleResult(
            company_id=company.pk,
            policy_mode=CompanyModulePolicyMode.SUBSCRIPTION,
            module_ids=(),
            entitlement_revision=0,
        )

    if subscription.snapshot_initialized_at is None:
        raise SubscriptionConflictError("Subscription module snapshot has not been initialized.")
    snapshot, overrides = _subscription_sets(subscription)
    effective = _effective_set(snapshot, overrides)
    return EffectiveModuleResult(
        company_id=company.pk,
        policy_mode=CompanyModulePolicyMode.SUBSCRIPTION,
        module_ids=effective,
        entitlement_revision=subscription.entitlement_revision,
        subscription_id=subscription.pk,
        subscription_status=subscription.status,
        snapshot_plan_entitlement_revision=subscription.snapshot_plan_entitlement_revision,
        snapshot_initialized=True,
    )


@transaction.atomic
def set_plan_module_defaults(
    *,
    actor: User,
    plan: Plan,
    module_ids: Iterable[str],
    reason: str = "",
) -> Plan:
    _require(actor, MANAGE_PLAN_CATALOG)
    desired = _validated_module_ids(module_ids)
    normalized_reason = _normalized_reason(reason)
    locked = Plan.objects.select_for_update().get(pk=plan.pk)
    previous = TENANT_MODULE_REGISTRY.normalize_ids(
        locked.module_defaults.values_list("module_id", flat=True)
    )
    if previous == desired:
        return locked

    previous_set = set(previous)
    desired_set = set(desired)
    locked.module_defaults.filter(module_id__in=previous_set - desired_set).delete()
    PlanModuleDefault.objects.bulk_create(
        [
            PlanModuleDefault(plan=locked, module_id=module_id)
            for module_id in desired
            if module_id not in previous_set
        ]
    )
    locked.entitlement_revision += 1
    locked.save(update_fields=["entitlement_revision", "updated_at"])

    batch_id = uuid4()
    for module_id in TENANT_MODULE_REGISTRY.module_ids:
        if module_id in desired_set - previous_set:
            PlanEntitlementEvent.objects.create(
                plan=locked,
                event_type=PlanEntitlementEventType.MODULE_ENABLED,
                module_id=module_id,
                previous_state=ModuleOverrideState.DISABLED,
                resulting_state=ModuleOverrideState.ENABLED,
                plan_entitlement_revision=locked.entitlement_revision,
                actor=actor,
                reason=normalized_reason,
                batch_id=batch_id,
            )
        elif module_id in previous_set - desired_set:
            PlanEntitlementEvent.objects.create(
                plan=locked,
                event_type=PlanEntitlementEventType.MODULE_DISABLED,
                module_id=module_id,
                previous_state=ModuleOverrideState.ENABLED,
                resulting_state=ModuleOverrideState.DISABLED,
                plan_entitlement_revision=locked.entitlement_revision,
                actor=actor,
                reason=normalized_reason,
                batch_id=batch_id,
            )
    return locked


def _locked_policy(company_id: UUID) -> CompanyModulePolicy:
    try:
        return CompanyModulePolicy.objects.select_for_update().get(company_id=company_id)
    except CompanyModulePolicy.DoesNotExist as exc:
        raise SubscriptionConflictError(
            "Company module policy is missing; repair rollout metadata before mutation."
        ) from exc


def _require_subscription_policy(policy: CompanyModulePolicy) -> None:
    if policy.mode != CompanyModulePolicyMode.SUBSCRIPTION:
        raise SubscriptionConflictError(
            "Company has not been converted to Subscription module policy."
        )


def _require_initialized(subscription: Subscription) -> None:
    if subscription.snapshot_initialized_at is None:
        raise SubscriptionConflictError("Subscription module snapshot has not been initialized.")


def _create_snapshot(
    *, subscription: Subscription, module_ids: Iterable[str], plan_revision: int
) -> None:
    SubscriptionModuleSnapshot.objects.bulk_create(
        [
            SubscriptionModuleSnapshot(
                subscription=subscription,
                module_id=module_id,
                source_plan_entitlement_revision=plan_revision,
            )
            for module_id in TENANT_MODULE_REGISTRY.ordered_ids(module_ids)
        ]
    )


def _create_subscription_event(
    *,
    subscription: Subscription,
    event_type: str,
    actor: User,
    revision: int,
    reason: str,
    batch_id: UUID,
    previous_state: str,
    resulting_state: str,
    module_id: str = "",
) -> SubscriptionEntitlementEvent:
    return SubscriptionEntitlementEvent.objects.create(
        subscription=subscription,
        event_type=event_type,
        module_id=module_id,
        previous_state=previous_state,
        resulting_state=resulting_state,
        plan_entitlement_revision=subscription.snapshot_plan_entitlement_revision,
        subscription_entitlement_revision=revision,
        actor=actor,
        reason=reason,
        batch_id=batch_id,
    )


@transaction.atomic
def convert_company_to_subscription_entitlements(
    *,
    actor: User,
    company: Company,
    overrides: Mapping[str, str] | None = None,
    reason: str = "",
) -> EffectiveModuleResult:
    _require(actor, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    normalized_reason = _normalized_reason(reason)
    proposed_overrides = _normalized_overrides(overrides)
    policy = _locked_policy(company.pk)
    if policy.mode != CompanyModulePolicyMode.LEGACY_FULL:
        raise SubscriptionConflictError("Company is already using Subscription module policy.")
    try:
        subscription = Subscription.objects.select_for_update().get(company_id=company.pk)
    except Subscription.DoesNotExist as exc:
        raise SubscriptionConflictError(
            "Company requires an existing Subscription before policy conversion."
        ) from exc
    plan = Plan.objects.select_for_update().get(pk=subscription.plan_id)
    if not plan.is_active:
        raise SubscriptionValidationError(
            {"plan_id": ["Inactive Plans cannot initialize Subscription entitlements."]}
        )
    if subscription.snapshot_initialized_at is not None:
        raise SubscriptionConflictError("Subscription module snapshot is already initialized.")
    if subscription.module_snapshot.exists() or subscription.module_overrides.exists():
        raise SubscriptionConflictError(
            "Uninitialized Subscription contains unexpected entitlement rows."
        )

    snapshot = _validated_module_ids(plan.module_defaults.values_list("module_id", flat=True))
    effective = _effective_set(snapshot, proposed_overrides)
    _create_snapshot(
        subscription=subscription,
        module_ids=snapshot,
        plan_revision=plan.entitlement_revision,
    )
    SubscriptionModuleOverride.objects.bulk_create(
        [
            SubscriptionModuleOverride(
                subscription=subscription,
                module_id=module_id,
                state=state,
            )
            for module_id, state in proposed_overrides.items()
        ]
    )
    subscription.snapshot_initialized_at = timezone.now()
    subscription.snapshot_plan_entitlement_revision = plan.entitlement_revision
    subscription.entitlement_revision += 1
    subscription.save(
        update_fields=[
            "snapshot_initialized_at",
            "snapshot_plan_entitlement_revision",
            "entitlement_revision",
            "updated_at",
        ]
    )
    policy.mode = CompanyModulePolicyMode.SUBSCRIPTION
    policy.save(update_fields=["mode", "updated_at"])

    batch_id = uuid4()
    _create_subscription_event(
        subscription=subscription,
        event_type=SubscriptionEntitlementEventType.SNAPSHOT_INITIALIZED,
        actor=actor,
        revision=subscription.entitlement_revision,
        reason=normalized_reason,
        batch_id=batch_id,
        previous_state="UNINITIALIZED",
        resulting_state="INITIALIZED",
    )
    for module_id in TENANT_MODULE_REGISTRY.ordered_ids(proposed_overrides):
        state = proposed_overrides[module_id]
        _create_subscription_event(
            subscription=subscription,
            event_type=(
                SubscriptionEntitlementEventType.OVERRIDE_ENABLED
                if state == ModuleOverrideState.ENABLED
                else SubscriptionEntitlementEventType.OVERRIDE_DISABLED
            ),
            actor=actor,
            revision=subscription.entitlement_revision,
            reason=normalized_reason,
            batch_id=batch_id,
            previous_state="INHERITED",
            resulting_state=state,
            module_id=module_id,
        )
    _create_subscription_event(
        subscription=subscription,
        event_type=SubscriptionEntitlementEventType.POLICY_CONVERTED,
        actor=actor,
        revision=subscription.entitlement_revision,
        reason=normalized_reason,
        batch_id=batch_id,
        previous_state=CompanyModulePolicyMode.LEGACY_FULL,
        resulting_state=CompanyModulePolicyMode.SUBSCRIPTION,
    )
    return EffectiveModuleResult(
        company_id=company.pk,
        policy_mode=CompanyModulePolicyMode.SUBSCRIPTION,
        module_ids=effective,
        entitlement_revision=subscription.entitlement_revision,
        subscription_id=subscription.pk,
        subscription_status=subscription.status,
        snapshot_plan_entitlement_revision=plan.entitlement_revision,
        snapshot_initialized=True,
    )


@transaction.atomic
def apply_plan_entitlement_revision(
    *, actor: User, subscription: Subscription, reason: str = ""
) -> EffectiveModuleResult:
    _require(actor, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    normalized_reason = _normalized_reason(reason)
    policy = _locked_policy(subscription.company_id)
    _require_subscription_policy(policy)
    locked = Subscription.objects.select_for_update().get(pk=subscription.pk)
    _require_initialized(locked)
    plan = Plan.objects.select_for_update().get(pk=locked.plan_id)
    proposed_snapshot = _validated_module_ids(
        plan.module_defaults.values_list("module_id", flat=True)
    )
    current_snapshot, overrides = _subscription_sets(locked)
    effective = _effective_set(proposed_snapshot, overrides)
    if (
        current_snapshot == proposed_snapshot
        and locked.snapshot_plan_entitlement_revision == plan.entitlement_revision
    ):
        return resolve_effective_modules(locked.company)

    previous_plan_revision = locked.snapshot_plan_entitlement_revision
    locked.module_snapshot.all().delete()
    _create_snapshot(
        subscription=locked,
        module_ids=proposed_snapshot,
        plan_revision=plan.entitlement_revision,
    )
    locked.snapshot_plan_entitlement_revision = plan.entitlement_revision
    locked.entitlement_revision += 1
    locked.save(
        update_fields=[
            "snapshot_plan_entitlement_revision",
            "entitlement_revision",
            "updated_at",
        ]
    )
    _create_subscription_event(
        subscription=locked,
        event_type=SubscriptionEntitlementEventType.PLAN_REVISION_APPLIED,
        actor=actor,
        revision=locked.entitlement_revision,
        reason=normalized_reason,
        batch_id=uuid4(),
        previous_state=f"PLAN_REVISION:{previous_plan_revision}",
        resulting_state=f"PLAN_REVISION:{plan.entitlement_revision}",
    )
    return EffectiveModuleResult(
        company_id=locked.company_id,
        policy_mode=CompanyModulePolicyMode.SUBSCRIPTION,
        module_ids=effective,
        entitlement_revision=locked.entitlement_revision,
        subscription_id=locked.pk,
        subscription_status=locked.status,
        snapshot_plan_entitlement_revision=plan.entitlement_revision,
        snapshot_initialized=True,
    )


@transaction.atomic
def set_subscription_module_override(
    *,
    actor: User,
    subscription: Subscription,
    module_id: str,
    state: str,
    reason: str = "",
) -> EffectiveModuleResult:
    _require(actor, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    normalized_reason = _normalized_reason(reason)
    normalized_module_id = _known_module_id(module_id)
    if state not in ModuleOverrideState.values:
        raise SubscriptionValidationError({"override_state": ["Unknown override state."]})
    policy = _locked_policy(subscription.company_id)
    _require_subscription_policy(policy)
    locked = Subscription.objects.select_for_update().get(pk=subscription.pk)
    _require_initialized(locked)
    snapshot, overrides = _subscription_sets(locked)
    previous_state = overrides.get(normalized_module_id)
    if previous_state == state:
        return resolve_effective_modules(locked.company)
    proposed = dict(overrides)
    proposed[normalized_module_id] = state
    effective = _effective_set(snapshot, proposed)

    SubscriptionModuleOverride.objects.update_or_create(
        subscription=locked,
        module_id=normalized_module_id,
        defaults={"state": state},
    )
    locked.entitlement_revision += 1
    locked.save(update_fields=["entitlement_revision", "updated_at"])
    _create_subscription_event(
        subscription=locked,
        event_type=(
            SubscriptionEntitlementEventType.OVERRIDE_ENABLED
            if state == ModuleOverrideState.ENABLED
            else SubscriptionEntitlementEventType.OVERRIDE_DISABLED
        ),
        actor=actor,
        revision=locked.entitlement_revision,
        reason=normalized_reason,
        batch_id=uuid4(),
        previous_state=previous_state or "INHERITED",
        resulting_state=state,
        module_id=normalized_module_id,
    )
    return EffectiveModuleResult(
        company_id=locked.company_id,
        policy_mode=CompanyModulePolicyMode.SUBSCRIPTION,
        module_ids=effective,
        entitlement_revision=locked.entitlement_revision,
        subscription_id=locked.pk,
        subscription_status=locked.status,
        snapshot_plan_entitlement_revision=locked.snapshot_plan_entitlement_revision,
        snapshot_initialized=True,
    )


@transaction.atomic
def replace_subscription_module_overrides(
    *,
    actor: User,
    subscription: Subscription,
    overrides: Mapping[str, str],
    reason: str = "",
) -> EffectiveModuleResult:
    """Replace the complete override set as one audited, revisioned operation."""

    _require(actor, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    normalized_reason = _normalized_reason(reason)
    proposed = _normalized_overrides(overrides)
    policy = _locked_policy(subscription.company_id)
    _require_subscription_policy(policy)
    locked = Subscription.objects.select_for_update().get(pk=subscription.pk)
    _require_initialized(locked)
    snapshot, previous = _subscription_sets(locked)
    effective = _effective_set(snapshot, proposed)
    if previous == proposed:
        return resolve_effective_modules(locked.company)

    locked.module_overrides.all().delete()
    SubscriptionModuleOverride.objects.bulk_create(
        [
            SubscriptionModuleOverride(
                subscription=locked,
                module_id=module_id,
                state=proposed[module_id],
            )
            for module_id in TENANT_MODULE_REGISTRY.ordered_ids(proposed)
        ]
    )
    locked.entitlement_revision += 1
    locked.save(update_fields=["entitlement_revision", "updated_at"])

    batch_id = uuid4()
    changed_ids = TENANT_MODULE_REGISTRY.ordered_ids(set(previous) | set(proposed))
    for module_id in changed_ids:
        previous_state = previous.get(module_id)
        resulting_state = proposed.get(module_id)
        if previous_state == resulting_state:
            continue
        if resulting_state is None:
            event_type = SubscriptionEntitlementEventType.OVERRIDE_CLEARED
            event_result = "INHERITED"
        elif resulting_state == ModuleOverrideState.ENABLED:
            event_type = SubscriptionEntitlementEventType.OVERRIDE_ENABLED
            event_result = resulting_state
        else:
            event_type = SubscriptionEntitlementEventType.OVERRIDE_DISABLED
            event_result = resulting_state
        _create_subscription_event(
            subscription=locked,
            event_type=event_type,
            actor=actor,
            revision=locked.entitlement_revision,
            reason=normalized_reason,
            batch_id=batch_id,
            previous_state=previous_state or "INHERITED",
            resulting_state=event_result,
            module_id=module_id,
        )

    return EffectiveModuleResult(
        company_id=locked.company_id,
        policy_mode=CompanyModulePolicyMode.SUBSCRIPTION,
        module_ids=effective,
        entitlement_revision=locked.entitlement_revision,
        subscription_id=locked.pk,
        subscription_status=locked.status,
        snapshot_plan_entitlement_revision=locked.snapshot_plan_entitlement_revision,
        snapshot_initialized=True,
    )


@transaction.atomic
def clear_subscription_module_override(
    *,
    actor: User,
    subscription: Subscription,
    module_id: str,
    reason: str = "",
) -> EffectiveModuleResult:
    _require(actor, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    normalized_reason = _normalized_reason(reason)
    normalized_module_id = _known_module_id(module_id)
    policy = _locked_policy(subscription.company_id)
    _require_subscription_policy(policy)
    locked = Subscription.objects.select_for_update().get(pk=subscription.pk)
    _require_initialized(locked)
    snapshot, overrides = _subscription_sets(locked)
    previous_state = overrides.get(normalized_module_id)
    if previous_state is None:
        return resolve_effective_modules(locked.company)
    proposed = dict(overrides)
    del proposed[normalized_module_id]
    effective = _effective_set(snapshot, proposed)

    locked.module_overrides.filter(module_id=normalized_module_id).delete()
    locked.entitlement_revision += 1
    locked.save(update_fields=["entitlement_revision", "updated_at"])
    _create_subscription_event(
        subscription=locked,
        event_type=SubscriptionEntitlementEventType.OVERRIDE_CLEARED,
        actor=actor,
        revision=locked.entitlement_revision,
        reason=normalized_reason,
        batch_id=uuid4(),
        previous_state=previous_state,
        resulting_state="INHERITED",
        module_id=normalized_module_id,
    )
    return EffectiveModuleResult(
        company_id=locked.company_id,
        policy_mode=CompanyModulePolicyMode.SUBSCRIPTION,
        module_ids=effective,
        entitlement_revision=locked.entitlement_revision,
        subscription_id=locked.pk,
        subscription_status=locked.status,
        snapshot_plan_entitlement_revision=locked.snapshot_plan_entitlement_revision,
        snapshot_initialized=True,
    )


def entitlement_model_labels() -> tuple[str, ...]:
    """Stable structural surface used by integrity and separation regressions."""

    models: tuple[type[Any], ...] = (
        CompanyModulePolicy,
        PlanModuleDefault,
        PlanEntitlementEvent,
        SubscriptionModuleSnapshot,
        SubscriptionModuleOverride,
        SubscriptionEntitlementEvent,
    )
    return tuple(model._meta.label for model in models)
