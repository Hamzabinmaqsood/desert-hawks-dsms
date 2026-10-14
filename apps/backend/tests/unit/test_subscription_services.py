from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from dsms.identity.models import User
from dsms.identity.platform_access import (
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_PLAN_CATALOG,
)
from dsms.subscriptions import services
from dsms.subscriptions.exceptions import (
    SubscriptionConflictError,
    SubscriptionTransitionError,
    SubscriptionValidationError,
)
from dsms.subscriptions.models import SubscriptionEvent, SubscriptionEventType, SubscriptionStatus
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory

pytestmark = pytest.mark.django_db


def grant(user: User, *capabilities: str) -> None:
    for capability in capabilities:
        app_label, codename = capability.split(".", maxsplit=1)
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )


def commercial_actor() -> User:
    actor = UserFactory.create()
    grant(actor, MANAGE_PLAN_CATALOG, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    return actor


def test_create_subscription_writes_initial_event_without_mutating_company() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create(is_active=True)
    plan = PlanFactory.create()

    subscription = services.create_subscription(actor=actor, company=company, plan=plan)

    event = subscription.events.get()
    assert event.event_type == SubscriptionEventType.CREATED
    assert event.previous_status == ""
    assert event.resulting_status == SubscriptionStatus.ACTIVE
    assert event.actor == actor
    company.refresh_from_db()
    assert company.is_active is True


def test_inactive_plan_is_retained_but_cannot_receive_new_subscription() -> None:
    actor = commercial_actor()
    first_company = CompanyFactory.create()
    plan = PlanFactory.create()
    existing = services.create_subscription(actor=actor, company=first_company, plan=plan)

    services.update_plan(actor=actor, plan=plan, is_active=False)
    existing.refresh_from_db()
    assert existing.plan_id == plan.id
    with pytest.raises(SubscriptionValidationError, match="invalid"):
        services.create_subscription(
            actor=actor,
            company=CompanyFactory.create(),
            plan=plan,
        )


def test_transition_graph_is_explicit_and_company_activity_is_unchanged() -> None:
    actor = commercial_actor()
    company = CompanyFactory.create(is_active=True)
    starts_at = timezone.now()
    subscription = services.create_subscription(
        actor=actor,
        company=company,
        plan=PlanFactory.create(),
        status=SubscriptionStatus.TRIAL,
        starts_at=starts_at,
        trial_ends_at=starts_at + timedelta(days=7),
    )

    transitioned = services.transition_subscription(
        actor=actor,
        subscription=subscription,
        target_status=SubscriptionStatus.ACTIVE,
        reason="Trial completed",
    )
    assert transitioned.status == SubscriptionStatus.ACTIVE
    assert list(
        transitioned.events.values_list("previous_status", "resulting_status", "reason")
    ) == [
        ("", SubscriptionStatus.TRIAL, ""),
        (SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE, "Trial completed"),
    ]
    company.refresh_from_db()
    assert company.is_active is True

    with pytest.raises(SubscriptionTransitionError, match="not allowed"):
        services.transition_subscription(
            actor=actor,
            subscription=transitioned,
            target_status=SubscriptionStatus.ACTIVE,
        )


def test_history_failure_rolls_back_status_change() -> None:
    actor = commercial_actor()
    subscription = services.create_subscription(
        actor=actor,
        company=CompanyFactory.create(),
        plan=PlanFactory.create(),
    )

    with (
        patch.object(SubscriptionEvent.objects, "create", side_effect=RuntimeError("injected")),
        pytest.raises(RuntimeError, match="injected"),
    ):
        services.transition_subscription(
            actor=actor,
            subscription=subscription,
            target_status=SubscriptionStatus.SUSPENDED,
        )

    subscription.refresh_from_db()
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert subscription.suspended_at is None
    assert subscription.events.count() == 1


def test_duplicate_normalized_plan_and_subscription_fail_predictably() -> None:
    actor = commercial_actor()
    services.create_plan(actor=actor, code=" core ", name="Core")
    with pytest.raises(SubscriptionConflictError, match="normalized code"):
        services.create_plan(actor=actor, code="core", name="Duplicate")

    company = CompanyFactory.create()
    plan = PlanFactory.create()
    services.create_subscription(actor=actor, company=company, plan=plan)
    with pytest.raises(SubscriptionConflictError, match="already has"):
        services.create_subscription(actor=actor, company=company, plan=plan)
