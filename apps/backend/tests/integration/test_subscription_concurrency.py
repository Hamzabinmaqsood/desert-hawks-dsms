from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import UUID

import pytest
from django.contrib.auth.models import Permission
from django.db import close_old_connections
from django.utils import timezone

from dsms.identity.models import User
from dsms.identity.platform_access import MANAGE_COMMERCIAL_SUBSCRIPTIONS
from dsms.organization.models import Company
from dsms.subscriptions import services
from dsms.subscriptions.exceptions import SubscriptionConflictError, SubscriptionTransitionError
from dsms.subscriptions.models import Plan, Subscription, SubscriptionEvent, SubscriptionStatus
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory

pytestmark = pytest.mark.django_db(transaction=True)


def platform_actor() -> User:
    actor = UserFactory.create()
    app_label, codename = MANAGE_COMMERCIAL_SUBSCRIPTIONS.split(".", maxsplit=1)
    actor.user_permissions.add(
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
    )
    return actor


def test_concurrent_creation_preserves_one_subscription_and_one_initial_event() -> None:
    actor = platform_actor()
    company = CompanyFactory.create()
    plan = PlanFactory.create()
    barrier = Barrier(2)

    def create(actor_id: UUID, company_id: UUID, plan_id: UUID) -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            services.create_subscription(
                actor=User.objects.get(pk=actor_id),
                company=Company.objects.get(pk=company_id),
                plan=Plan.objects.get(pk=plan_id),
            )
            return "created"
        except SubscriptionConflictError:
            return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: create(actor.id, company.id, plan.id),
                range(2),
            )
        )

    assert sorted(results) == ["conflict", "created"]
    assert Subscription.objects.filter(company=company).count() == 1
    assert SubscriptionEvent.objects.count() == 1


def test_concurrent_transition_serializes_to_one_valid_event_chain() -> None:
    actor = platform_actor()
    starts_at = timezone.now()
    subscription = services.create_subscription(
        actor=actor,
        company=CompanyFactory.create(),
        plan=PlanFactory.create(),
        status=SubscriptionStatus.TRIAL,
        starts_at=starts_at,
        trial_ends_at=starts_at + timedelta(days=7),
    )
    barrier = Barrier(2)

    def activate(actor_id: UUID, subscription_id: UUID) -> str:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            services.transition_subscription(
                actor=User.objects.get(pk=actor_id),
                subscription=Subscription.objects.get(pk=subscription_id),
                target_status=SubscriptionStatus.ACTIVE,
            )
            return "transitioned"
        except SubscriptionTransitionError:
            return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: activate(actor.id, subscription.id), range(2)))

    assert sorted(results) == ["conflict", "transitioned"]
    subscription.refresh_from_db()
    assert subscription.status == SubscriptionStatus.ACTIVE
    assert list(subscription.events.values_list("previous_status", "resulting_status")) == [
        ("", SubscriptionStatus.TRIAL),
        (SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE),
    ]
