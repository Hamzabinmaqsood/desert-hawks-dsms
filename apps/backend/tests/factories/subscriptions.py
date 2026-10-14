import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from dsms.organization.models import Company
from dsms.subscriptions.models import Plan, Subscription, SubscriptionStatus
from tests.factories.organization import CompanyFactory


class PlanFactory(DjangoModelFactory[Plan]):
    class Meta:
        model = Plan

    code = factory.Sequence(lambda n: f"PLAN{n:04d}")
    name = factory.Sequence(lambda n: f"Commercial Plan {n}")
    is_active = True


class SubscriptionFactory(DjangoModelFactory[Subscription]):
    class Meta:
        model = Subscription

    company: Company = factory.SubFactory(CompanyFactory)  # type: ignore[assignment]
    plan: Plan = factory.SubFactory(PlanFactory)  # type: ignore[assignment]
    status = SubscriptionStatus.ACTIVE
    starts_at = factory.LazyFunction(timezone.now)
    trial_ends_at = None
    grace_ends_at = None
    suspended_at = None
    terminated_at = None
