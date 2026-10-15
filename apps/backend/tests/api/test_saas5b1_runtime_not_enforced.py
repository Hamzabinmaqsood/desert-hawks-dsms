import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.subscriptions.models import CompanyModulePolicy, CompanyModulePolicyMode
from tests.factories.identity import UserFactory
from tests.factories.subscriptions import SubscriptionFactory

pytestmark = pytest.mark.django_db


def test_zero_module_subscription_does_not_yet_deny_tenant_runtime_api() -> None:
    subscription = SubscriptionFactory.create(
        snapshot_initialized_at=timezone.now(),
        snapshot_plan_entitlement_revision=0,
        entitlement_revision=1,
    )
    CompanyModulePolicy.objects.create(
        company=subscription.company,
        mode=CompanyModulePolicyMode.SUBSCRIPTION,
    )
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))

    response = client.get("/api/v1/finance/accounts/")

    assert response.status_code == 200
