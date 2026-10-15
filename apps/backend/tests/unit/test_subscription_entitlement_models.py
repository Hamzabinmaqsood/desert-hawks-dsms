from typing import cast

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction

from dsms.billing.models import ClientBillingProfile, ClientInvoice, ClientReceipt
from dsms.common.integrity.coverage import (
    DERIVED_CHILD_FAMILIES,
    GLOBAL_NON_TENANT_MODELS,
    NO_INDEPENDENT_TENANT_RELATIONS,
)
from dsms.finance.models import Account, JournalEntry
from dsms.finance.payment_models import PaymentAccountingProfile
from dsms.finance.procurement_models import PaymentVoucher, VendorBill
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    ModuleOverrideState,
    PlanEntitlementEvent,
    PlanEntitlementEventType,
    PlanModuleDefault,
    SubscriptionEntitlementEvent,
    SubscriptionEntitlementEventType,
    SubscriptionModuleOverride,
    SubscriptionModuleSnapshot,
)
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory, SubscriptionFactory

pytestmark = pytest.mark.django_db


def test_company_policy_is_unique_and_modes_are_validated() -> None:
    company = CompanyFactory.create()
    policy = CompanyModulePolicy.objects.create(company=company)
    assert policy.mode == CompanyModulePolicyMode.LEGACY_FULL

    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyModulePolicy.objects.create(company=company)

    policy.mode = "UNKNOWN"
    with pytest.raises(ValidationError):
        policy.full_clean()


def test_normalized_module_rows_have_database_uniqueness_and_valid_states() -> None:
    plan = PlanFactory.create()
    PlanModuleDefault.objects.create(plan=plan, module_id="people")
    with pytest.raises(IntegrityError), transaction.atomic():
        PlanModuleDefault.objects.create(plan=plan, module_id="people")

    subscription = SubscriptionFactory.create(plan=plan)
    SubscriptionModuleSnapshot.objects.create(
        subscription=subscription,
        module_id="people",
        source_plan_entitlement_revision=0,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        SubscriptionModuleSnapshot.objects.create(
            subscription=subscription,
            module_id="people",
            source_plan_entitlement_revision=0,
        )

    override = SubscriptionModuleOverride.objects.create(
        subscription=subscription,
        module_id="analytics",
        state=ModuleOverrideState.ENABLED,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        SubscriptionModuleOverride.objects.create(
            subscription=subscription,
            module_id="analytics",
            state=ModuleOverrideState.DISABLED,
        )
    override.state = "UNKNOWN"
    with pytest.raises(ValidationError):
        override.full_clean()


def test_model_validation_rejects_unknown_code_registry_ids() -> None:
    plan = PlanFactory.create()
    subscription = SubscriptionFactory.create(plan=plan)
    actor = UserFactory.create()
    candidates = (
        PlanModuleDefault(plan=plan, module_id="unknown"),
        PlanEntitlementEvent(
            plan=plan,
            event_type=PlanEntitlementEventType.MODULE_ENABLED,
            module_id="unknown",
            previous_state="DISABLED",
            resulting_state="ENABLED",
            plan_entitlement_revision=1,
            actor=actor,
        ),
        SubscriptionModuleSnapshot(
            subscription=subscription,
            module_id="unknown",
            source_plan_entitlement_revision=1,
        ),
        SubscriptionModuleOverride(
            subscription=subscription,
            module_id="unknown",
            state=ModuleOverrideState.ENABLED,
        ),
        SubscriptionEntitlementEvent(
            subscription=subscription,
            event_type=SubscriptionEntitlementEventType.OVERRIDE_ENABLED,
            module_id="unknown",
            previous_state="INHERITED",
            resulting_state="ENABLED",
            subscription_entitlement_revision=1,
            actor=actor,
        ),
    )
    for candidate in candidates:
        with pytest.raises(ValidationError, match="Unknown tenant module ID"):
            candidate.full_clean(validate_unique=False)


def test_entitlement_history_is_append_only() -> None:
    actor = UserFactory.create()
    plan = PlanFactory.create()
    plan_event = PlanEntitlementEvent.objects.create(
        plan=plan,
        event_type=PlanEntitlementEventType.MODULE_ENABLED,
        module_id="people",
        previous_state="DISABLED",
        resulting_state="ENABLED",
        plan_entitlement_revision=1,
        actor=actor,
    )
    subscription = SubscriptionFactory.create(plan=plan)
    subscription_event = SubscriptionEntitlementEvent.objects.create(
        subscription=subscription,
        event_type=SubscriptionEntitlementEventType.SNAPSHOT_INITIALIZED,
        previous_state="UNINITIALIZED",
        resulting_state="INITIALIZED",
        plan_entitlement_revision=1,
        subscription_entitlement_revision=1,
        actor=actor,
    )

    for event in (plan_event, subscription_event):
        event.reason = "changed"
        with pytest.raises(ValidationError, match="immutable"):
            event.save()
        with pytest.raises(ValidationError, match="cannot be deleted"):
            event.delete()
    with pytest.raises(ValidationError, match="immutable"):
        PlanEntitlementEvent.objects.filter(pk=plan_event.pk).update(reason="changed")
    with pytest.raises(ValidationError, match="immutable"):
        SubscriptionEntitlementEvent.objects.filter(pk=subscription_event.pk).update(
            reason="changed"
        )


def test_subscription_children_derive_company_and_manifest_classification() -> None:
    subscription = SubscriptionFactory.create()
    snapshot = SubscriptionModuleSnapshot.objects.create(
        subscription=subscription,
        module_id="people",
        source_plan_entitlement_revision=0,
    )
    override = SubscriptionModuleOverride.objects.create(
        subscription=subscription,
        module_id="analytics",
        state=ModuleOverrideState.ENABLED,
    )
    event = SubscriptionEntitlementEvent.objects.create(
        subscription=subscription,
        event_type=SubscriptionEntitlementEventType.OVERRIDE_ENABLED,
        module_id="analytics",
        previous_state="INHERITED",
        resulting_state="ENABLED",
        subscription_entitlement_revision=1,
        actor=UserFactory.create(),
    )
    for child in (snapshot, override, event):
        assert child.company_id == subscription.company_id
        assert "company" not in {field.name for field in child._meta.concrete_fields}
        assert child._meta.label in DERIVED_CHILD_FAMILIES

    assert "subscriptions.CompanyModulePolicy" in NO_INDEPENDENT_TENANT_RELATIONS
    assert "subscriptions.PlanModuleDefault" in GLOBAL_NON_TENANT_MODELS
    assert "subscriptions.PlanEntitlementEvent" in GLOBAL_NON_TENANT_MODELS


def test_entitlement_models_have_no_tenant_ar_ap_relationships() -> None:
    blocked = {
        model._meta.label
        for model in (
            ClientInvoice,
            ClientReceipt,
            ClientBillingProfile,
            VendorBill,
            PaymentVoucher,
            PaymentAccountingProfile,
            Account,
            JournalEntry,
        )
    }
    entitlement_models = (
        CompanyModulePolicy,
        PlanModuleDefault,
        PlanEntitlementEvent,
        SubscriptionModuleSnapshot,
        SubscriptionModuleOverride,
        SubscriptionEntitlementEvent,
    )
    for model in entitlement_models:
        related_labels = {
            cast(type[models.Model], field.related_model)._meta.label
            for field in model._meta.concrete_fields
            if getattr(field, "related_model", None) not in (None, "self")
        }
        assert related_labels.isdisjoint(blocked)
