from datetime import timedelta
from typing import cast

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from dsms.billing.models import ClientInvoice, ClientReceipt
from dsms.common.integrity.coverage import DERIVED_CHILD_FAMILIES, NO_INDEPENDENT_TENANT_RELATIONS
from dsms.finance.models import Account, JournalEntry
from dsms.finance.procurement_models import PaymentVoucher, VendorBill
from dsms.subscriptions.models import (
    Plan,
    Subscription,
    SubscriptionEvent,
    SubscriptionEventType,
    SubscriptionStatus,
)
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory, SubscriptionFactory

pytestmark = pytest.mark.django_db


def test_plan_code_is_normalized_and_unique() -> None:
    plan = Plan.objects.create(code=" starter ", name="Starter")
    assert plan.code == "STARTER"

    with pytest.raises(IntegrityError), transaction.atomic():
        Plan.objects.create(code="starter", name="Duplicate")


def test_company_may_have_no_subscription_and_one_to_one_is_database_enforced() -> None:
    company = CompanyFactory.create()
    assert not Subscription.objects.filter(company=company).exists()

    SubscriptionFactory.create(company=company)
    with pytest.raises(IntegrityError), transaction.atomic():
        SubscriptionFactory.create(company=company)

    subscription = Subscription.objects.get(company=company)
    with pytest.raises(ValidationError, match="cannot be deleted"):
        subscription.delete()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        Subscription.objects.filter(pk=subscription.pk).delete()


def test_lifecycle_dates_are_validated() -> None:
    now = timezone.now()
    subscription = Subscription(
        company=CompanyFactory.create(),
        plan=PlanFactory.create(),
        status=SubscriptionStatus.TRIAL,
        starts_at=now,
    )
    with pytest.raises(ValidationError, match="explicit trial end"):
        subscription.full_clean()

    subscription.trial_ends_at = now - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="cannot precede"):
        subscription.full_clean()

    subscription.status = SubscriptionStatus.GRACE
    subscription.trial_ends_at = None
    subscription.grace_ends_at = now - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="must follow"):
        subscription.full_clean()


def test_subscription_event_ownership_is_derived_and_history_is_append_only() -> None:
    subscription = SubscriptionFactory.create()
    event = SubscriptionEvent.objects.create(
        subscription=subscription,
        event_type=SubscriptionEventType.CREATED,
        previous_status="",
        resulting_status=SubscriptionStatus.ACTIVE,
        actor=UserFactory.create(),
    )

    assert event.company_id == subscription.company_id
    assert "company" not in {field.name for field in SubscriptionEvent._meta.concrete_fields}
    event.reason = "changed"
    with pytest.raises(ValidationError, match="immutable"):
        event.save()
    with pytest.raises(ValidationError, match="immutable"):
        SubscriptionEvent.objects.filter(pk=event.pk).update(reason="changed")
    with pytest.raises(ValidationError, match="cannot be deleted"):
        SubscriptionEvent.objects.filter(pk=event.pk).delete()


def test_commercial_models_have_no_tenant_ar_ap_relationships() -> None:
    blocked = {
        model._meta.label
        for model in (
            ClientInvoice,
            ClientReceipt,
            VendorBill,
            PaymentVoucher,
            Account,
            JournalEntry,
        )
    }
    for model in (Plan, Subscription, SubscriptionEvent):
        related_labels = {
            cast(type[models.Model], field.related_model)._meta.label
            for field in model._meta.concrete_fields
            if getattr(field, "related_model", None) not in (None, "self")
        }
        assert related_labels.isdisjoint(blocked)

    assert "company" not in {field.name for field in Plan._meta.concrete_fields}
    assert {
        field.name
        for field in Subscription._meta.concrete_fields
        if getattr(field, "related_model", None) is not None
    } == {"company", "plan"}
    assert "subscriptions.Subscription" in NO_INDEPENDENT_TENANT_RELATIONS
    assert "subscriptions.SubscriptionEvent" in DERIVED_CHILD_FAMILIES
