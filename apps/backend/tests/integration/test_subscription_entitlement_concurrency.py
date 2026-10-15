from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID

import pytest
from django.contrib.auth.models import Permission
from django.db import close_old_connections

from dsms.identity.models import User
from dsms.identity.platform_access import (
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_PLAN_CATALOG,
)
from dsms.subscriptions import entitlements
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    ModuleOverrideState,
    Plan,
    Subscription,
)
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory, SubscriptionFactory

pytestmark = pytest.mark.django_db(transaction=True)


def commercial_actor() -> User:
    actor = UserFactory.create()
    for capability in (MANAGE_PLAN_CATALOG, MANAGE_COMMERCIAL_SUBSCRIPTIONS):
        app_label, codename = capability.split(".", maxsplit=1)
        actor.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return actor


def test_concurrent_plan_default_updates_serialize_revision_and_history() -> None:
    actor = commercial_actor()
    plan = PlanFactory.create()
    barrier = Barrier(2)

    def update(actor_id: UUID, plan_id: UUID, module_id: str) -> int:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            updated = entitlements.set_plan_module_defaults(
                actor=User.objects.get(pk=actor_id),
                plan=Plan.objects.get(pk=plan_id),
                module_ids=(module_id,),
                reason=f"Concurrent {module_id}",
            )
            return updated.entitlement_revision
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        revisions = list(
            pool.map(
                lambda module_id: update(actor.id, plan.id, module_id),
                ("people", "client_contracts"),
            )
        )

    plan.refresh_from_db()
    assert sorted(revisions) == [1, 2]
    assert plan.entitlement_revision == 2
    assert plan.module_defaults.count() == 1
    assert set(plan.entitlement_events.values_list("plan_entitlement_revision", flat=True)) == {
        1,
        2,
    }
    assert plan.entitlement_events.count() == 3


def test_concurrent_subscription_overrides_preserve_both_updates() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create()
    CompanyModulePolicy.objects.create(company=company)
    plan = PlanFactory.create()
    entitlements.set_plan_module_defaults(
        actor=actor,
        plan=plan,
        module_ids=("people", "finance_core"),
    )
    subscription = SubscriptionFactory.create(company=company, plan=plan)
    entitlements.convert_company_to_subscription_entitlements(actor=actor, company=company)
    barrier = Barrier(2)

    def enable(actor_id: UUID, subscription_id: UUID, module_id: str) -> int:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            result = entitlements.set_subscription_module_override(
                actor=User.objects.get(pk=actor_id),
                subscription=Subscription.objects.get(pk=subscription_id),
                module_id=module_id,
                state=ModuleOverrideState.ENABLED,
                reason=f"Concurrent {module_id}",
            )
            return result.entitlement_revision
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        revisions = list(
            pool.map(
                lambda module_id: enable(actor.id, subscription.id, module_id),
                ("asset_management", "analytics"),
            )
        )

    subscription.refresh_from_db()
    assert sorted(revisions) == [2, 3]
    assert subscription.entitlement_revision == 3
    assert set(subscription.module_overrides.values_list("module_id", flat=True)) == {
        "asset_management",
        "analytics",
    }
    assert entitlements.resolve_effective_modules(company).module_ids == (
        "people",
        "finance_core",
        "asset_management",
        "analytics",
    )
