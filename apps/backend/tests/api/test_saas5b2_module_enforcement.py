import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from dsms.identity.enums import AccessScopeType
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    SubscriptionModuleSnapshot,
)
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import SubscriptionFactory

pytestmark = pytest.mark.django_db

CONTEXT_URL = "/api/v1/auth/company-context/"


def configure_subscription(company, *module_ids: str):  # type: ignore[no-untyped-def]
    subscription = SubscriptionFactory.create(
        company=company,
        snapshot_initialized_at=timezone.now(),
        snapshot_plan_entitlement_revision=0,
        entitlement_revision=11,
    )
    CompanyModulePolicy.objects.create(
        company=company,
        mode=CompanyModulePolicyMode.SUBSCRIPTION,
    )
    SubscriptionModuleSnapshot.objects.bulk_create(
        [
            SubscriptionModuleSnapshot(
                subscription=subscription,
                module_id=module_id,
                source_plan_entitlement_revision=0,
            )
            for module_id in module_ids
        ]
    )
    return subscription


def authenticated_superuser() -> tuple[APIClient, object]:
    user = UserFactory.create(is_staff=True, is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    return client, user


def test_selected_company_capability_context_is_tenant_safe_and_revisioned() -> None:
    company = CompanyFactory.create()
    configure_subscription(company, "finance_core")
    client, _user = authenticated_superuser()

    response = client.get(CONTEXT_URL)

    assert response.status_code == 200
    assert response.data["effective_modules"] == ["finance_core"]
    assert response.data["entitlement_revision"] == 11
    assert "plan" not in response.data
    assert "subscription" not in response.data


def test_company_switch_a_to_b_to_a_never_unions_capabilities() -> None:
    company_a = CompanyFactory.create(code="SWITCH-A")
    company_b = CompanyFactory.create(code="SWITCH-B")
    configure_subscription(company_a, "finance_core")
    configure_subscription(company_b)
    client, _user = authenticated_superuser()

    selected_a = client.put(CONTEXT_URL, {"company_id": company_a.id}, format="json")
    selected_b = client.put(CONTEXT_URL, {"company_id": company_b.id}, format="json")
    reselected_a = client.put(CONTEXT_URL, {"company_id": company_a.id}, format="json")

    assert selected_a.data["effective_modules"] == ["finance_core"]
    assert selected_b.data["effective_modules"] == []
    assert reselected_a.data["effective_modules"] == ["finance_core"]


def test_legacy_context_exposes_the_ordered_full_catalog_without_writes() -> None:
    company = CompanyFactory.create()
    client, _user = authenticated_superuser()

    response = client.get(CONTEXT_URL)

    assert response.status_code == 200
    assert len(response.data["effective_modules"]) == 20
    assert response.data["entitlement_revision"] == 0
    assert not CompanyModulePolicy.objects.filter(company=company).exists()


def test_multi_company_legacy_collection_preserves_existing_scoped_access() -> None:
    company_a = CompanyFactory.create(code="LEGACY-A")
    company_b = CompanyFactory.create(code="LEGACY-B")
    account_a = Account.objects.create(
        company=company_a, code="LA100", name="Legacy A", account_type=AccountType.ASSET
    )
    account_b = Account.objects.create(
        company=company_b, code="LB100", name="Legacy B", account_type=AccountType.ASSET
    )
    client, _user = authenticated_superuser()

    response = client.get("/api/v1/finance/accounts/")

    assert response.status_code == 200
    assert {row["id"] for row in response.data["results"]} == {
        str(account_a.id),
        str(account_b.id),
    }


def test_multi_company_subscription_collection_requires_authoritative_selection() -> None:
    company_a = CompanyFactory.create(code="SUBSCRIPTION-A")
    CompanyFactory.create(code="LEGACY-B")
    configure_subscription(company_a, "finance_core")
    client, _user = authenticated_superuser()

    response = client.get("/api/v1/finance/accounts/")

    assert response.status_code == 403
    assert response.data["code"] != "module_not_enabled"


def test_selected_a_and_b_keep_collection_and_resource_entitlements_isolated() -> None:
    company_a = CompanyFactory.create(code="MODULE-A")
    company_b = CompanyFactory.create(code="MODULE-B")
    subscription_a = configure_subscription(company_a)
    configure_subscription(company_b, "finance_core")
    account_a = Account.objects.create(
        company=company_a, code="A100", name="A cash", account_type=AccountType.ASSET
    )
    account_b = Account.objects.create(
        company=company_b, code="B100", name="B cash", account_type=AccountType.ASSET
    )
    client, _user = authenticated_superuser()

    assert client.put(CONTEXT_URL, {"company_id": company_a.id}, format="json").status_code == 200
    denied_list = client.get("/api/v1/finance/accounts/")
    assert denied_list.status_code == 403
    assert denied_list.data["code"] == "module_not_enabled"
    assert client.get(f"/api/v1/finance/accounts/{account_a.id}/").status_code == 403
    assert client.get(f"/api/v1/finance/accounts/{account_b.id}/").status_code == 200
    assert Account.objects.filter(pk=account_a.pk).exists()

    SubscriptionModuleSnapshot.objects.create(
        subscription=subscription_a,
        module_id="finance_core",
        source_plan_entitlement_revision=0,
    )
    subscription_a.entitlement_revision = 12
    subscription_a.save(update_fields=["entitlement_revision", "updated_at"])
    assert client.get(f"/api/v1/finance/accounts/{account_a.id}/").status_code == 200

    selected_b = client.put(CONTEXT_URL, {"company_id": company_b.id}, format="json")
    assert selected_b.status_code == 200
    assert selected_b.data["effective_modules"] == ["finance_core"]
    allowed = client.get("/api/v1/finance/accounts/")
    assert allowed.status_code == 200
    assert [row["id"] for row in allowed.data["results"]] == [str(account_b.id)]


def test_module_entitlement_does_not_grant_rbac_permission() -> None:
    company = CompanyFactory.create()
    configure_subscription(company, "finance_core")
    user = UserFactory.create()
    role = RoleFactory.create(company=company)
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/v1/finance/accounts/")

    assert response.status_code == 403
    assert response.data["code"] != "module_not_enabled"


@pytest.mark.parametrize(
    ("url", "required_module"),
    [
        ("/api/v1/contracts/sites/", "security_operations"),
        ("/api/v1/contracts/posts/", "security_operations"),
        ("/api/v1/deployment/deployments/", "security_operations"),
        ("/api/v1/patrol/tasks/", "security_patrol"),
        ("/api/v1/supervision/visits/", "security_supervision"),
        ("/api/v1/incidents/incidents/", "security_incidents"),
    ],
)
def test_direct_security_api_calls_require_their_specific_module(
    url: str, required_module: str
) -> None:
    company = CompanyFactory.create()
    configure_subscription(company)
    client, _user = authenticated_superuser()

    response = client.get(url)

    assert response.status_code == 403
    assert response.data["code"] == "module_not_enabled"
    assert response.data["required_modules"] == [required_module]


def test_security_enabled_company_retains_normal_read_access() -> None:
    company = CompanyFactory.create()
    configure_subscription(
        company,
        "people",
        "client_contracts",
        "security_operations",
        "security_patrol",
        "security_supervision",
        "security_incidents",
    )
    client, _user = authenticated_superuser()

    for url in (
        "/api/v1/contracts/sites/",
        "/api/v1/deployment/deployments/",
        "/api/v1/patrol/tasks/",
        "/api/v1/supervision/visits/",
        "/api/v1/incidents/incidents/",
    ):
        assert client.get(url).status_code == 200
