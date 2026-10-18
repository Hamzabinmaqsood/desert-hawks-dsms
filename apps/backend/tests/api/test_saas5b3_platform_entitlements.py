from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User
from dsms.identity.platform_access import (
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_PLAN_CATALOG,
    VIEW_COMMERCIAL_SUBSCRIPTIONS,
    VIEW_PLAN_CATALOG,
)
from dsms.organization.models import Company
from dsms.subscriptions import entitlements, services
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    ModuleOverrideState,
    SubscriptionEntitlementEventType,
    SubscriptionModuleOverride,
)
from dsms.subscriptions.modules import TENANT_MODULE_REGISTRY
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory

pytestmark = pytest.mark.django_db

ALL_CAPABILITIES = (
    VIEW_PLAN_CATALOG,
    MANAGE_PLAN_CATALOG,
    VIEW_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
)


def authenticated(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def permission(capability: str) -> Permission:
    app_label, codename = capability.split(".", maxsplit=1)
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def grant_platform(user: User, *capabilities: str) -> None:
    user.user_permissions.add(*(permission(capability) for capability in capabilities))


def tenant_admin(user: User, company: Company) -> None:
    role: Role = RoleFactory.create(code=f"TENANT_ADMIN_{uuid4().hex[:8]}")
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def legacy_subscription(actor: User, module_ids: tuple[str, ...]):  # type: ignore[no-untyped-def]
    plan = PlanFactory.create()
    entitlements.set_plan_module_defaults(actor=actor, plan=plan, module_ids=module_ids)
    plan.refresh_from_db()
    company = CompanyFactory.create()
    CompanyModulePolicy.objects.create(company=company, mode=CompanyModulePolicyMode.LEGACY_FULL)
    subscription = services.create_subscription(actor=actor, company=company, plan=plan)
    return company, plan, subscription


def test_module_catalog_is_ordered_and_platform_only() -> None:
    viewer = UserFactory.create()
    grant_platform(viewer, VIEW_PLAN_CATALOG)
    response = authenticated(viewer).get(reverse("platform-module-catalog"))

    assert response.status_code == 200
    assert [item["id"] for item in response.data] == list(TENANT_MODULE_REGISTRY.module_ids)
    assert set(response.data[0]) == {
        "id",
        "display_name",
        "classification",
        "hard_dependencies",
        "legacy_default",
    }

    company = CompanyFactory.create()
    second_company = CompanyFactory.create()
    ordinary = UserFactory.create()
    admin = UserFactory.create()
    staff = UserFactory.create(is_staff=True)
    tenant_admin(admin, company)
    tenant_admin(admin, second_company)
    for actor in (ordinary, admin, staff):
        assert authenticated(actor).get(reverse("platform-module-catalog")).status_code == 403

    viewer.user_permissions.remove(permission(VIEW_PLAN_CATALOG))
    assert authenticated(viewer).get(reverse("platform-module-catalog")).status_code == 403
    assert APIClient().get(reverse("platform-module-catalog")).status_code == 401


def test_superuser_break_glass_and_inactive_user_boundary() -> None:
    assert (
        authenticated(UserFactory.create(is_superuser=True))
        .get(reverse("platform-module-catalog"))
        .status_code
        == 200
    )
    inactive = UserFactory.create(is_active=False)
    grant_platform(inactive, VIEW_PLAN_CATALOG)
    assert authenticated(inactive).get(reverse("platform-module-catalog")).status_code == 403


def test_plan_entitlement_update_is_revisioned_but_not_live_inherited() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *ALL_CAPABILITIES)
    company, plan, subscription = legacy_subscription(operator, ("people",))
    entitlements.convert_company_to_subscription_entitlements(actor=operator, company=company)
    captured_revision = subscription.entitlement_revision
    client = authenticated(operator)
    url = reverse("platform-plan-entitlements", args=[plan.pk])

    before = client.get(url)
    assert before.status_code == 200
    assert before.data["enabled_module_ids"] == ["people"]
    updated = client.put(
        url,
        {
            "enabled_module_ids": ["people", "finance_core"],
            "reason": "Offer finance",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["entitlement_revision"] == 2
    assert "existing subscriptions retain" in updated.data["snapshot_notice"]
    unchanged = entitlements.resolve_effective_modules(company)
    assert unchanged.module_ids == ("people",)
    assert unchanged.entitlement_revision == captured_revision + 1

    no_op = client.put(
        url,
        {"enabled_module_ids": ["people", "finance_core"], "reason": "No change"},
        format="json",
    )
    assert no_op.status_code == 200
    assert no_op.data["entitlement_revision"] == 2


@pytest.mark.parametrize(
    ("module_ids", "error_key"),
    [
        (["not_a_module"], "unknown_module_ids"),
        (["billing_receivables"], "missing_dependency_ids"),
    ],
)
def test_plan_entitlement_validation_is_server_authoritative(
    module_ids: list[str], error_key: str
) -> None:
    operator = UserFactory.create()
    grant_platform(operator, MANAGE_PLAN_CATALOG)
    response = authenticated(operator).put(
        reverse("platform-plan-entitlements", args=[PlanFactory.create().pk]),
        {"enabled_module_ids": module_ids},
        format="json",
    )
    assert response.status_code == 400
    assert error_key in response.data


def test_subscription_detail_and_batch_override_replacement_are_audited() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *ALL_CAPABILITIES)
    company, _plan, subscription = legacy_subscription(
        operator, ("people", "client_contracts", "finance_core", "billing_receivables")
    )
    tenant_admin(operator, company)
    entitlements.convert_company_to_subscription_entitlements(actor=operator, company=company)
    client = authenticated(operator)
    detail_url = reverse("platform-subscription-entitlements", args=[subscription.pk])
    override_url = reverse("platform-subscription-overrides", args=[subscription.pk])

    detail = client.get(detail_url)
    assert detail.status_code == 200
    assert detail.data["policy_mode"] == CompanyModulePolicyMode.SUBSCRIPTION
    assert detail.data["snapshot_module_ids"] == [
        "people",
        "client_contracts",
        "finance_core",
        "billing_receivables",
    ]

    starting_revision = detail.data["entitlement_revision"]
    updated = client.put(
        override_url,
        {
            "enabled_module_ids": ["analytics"],
            "disabled_module_ids": [],
            "reason": "Analytics pilot",
        },
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["entitlement_revision"] == starting_revision + 1
    assert updated.data["overrides"] == [
        {"module_id": "analytics", "state": ModuleOverrideState.ENABLED}
    ]
    assert subscription.entitlement_events.filter(
        event_type=SubscriptionEntitlementEventType.OVERRIDE_ENABLED,
        module_id="analytics",
    ).exists()

    cleared = client.put(
        override_url,
        {"enabled_module_ids": [], "disabled_module_ids": [], "reason": "End pilot"},
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.data["entitlement_revision"] == starting_revision + 2
    assert cleared.data["overrides"] == []
    assert not SubscriptionModuleOverride.objects.filter(subscription=subscription).exists()
    assert subscription.entitlement_events.filter(
        event_type=SubscriptionEntitlementEventType.OVERRIDE_CLEARED,
        module_id="analytics",
    ).exists()


def test_override_batch_rejects_contradiction_and_invalid_dependency_atomically() -> None:
    operator = UserFactory.create()
    grant_platform(operator, MANAGE_PLAN_CATALOG, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    company, _plan, subscription = legacy_subscription(
        operator, ("people", "client_contracts", "finance_core", "billing_receivables")
    )
    entitlements.convert_company_to_subscription_entitlements(actor=operator, company=company)
    subscription.refresh_from_db()
    url = reverse("platform-subscription-overrides", args=[subscription.pk])
    client = authenticated(operator)
    starting_revision = subscription.entitlement_revision
    history_count = subscription.entitlement_events.count()

    contradictory = client.put(
        url,
        {"enabled_module_ids": ["analytics"], "disabled_module_ids": ["analytics"]},
        format="json",
    )
    assert contradictory.status_code == 400
    invalid = client.put(
        url,
        {"enabled_module_ids": [], "disabled_module_ids": ["finance_core"]},
        format="json",
    )
    assert invalid.status_code == 400
    subscription.refresh_from_db()
    assert subscription.entitlement_revision == starting_revision
    assert subscription.entitlement_events.count() == history_count
    assert not subscription.module_overrides.exists()


def test_apply_plan_revision_is_explicit_and_preserves_valid_overrides() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *ALL_CAPABILITIES)
    company, plan, subscription = legacy_subscription(operator, ("people",))
    entitlements.convert_company_to_subscription_entitlements(
        actor=operator,
        company=company,
        overrides={"analytics": ModuleOverrideState.ENABLED},
    )
    entitlements.set_plan_module_defaults(
        actor=operator, plan=plan, module_ids=("people", "finance_core")
    )

    client = authenticated(operator)
    rejected = client.post(
        reverse("platform-subscription-apply-plan-revision", args=[subscription.pk]),
        {"reason": ""},
        format="json",
    )
    assert rejected.status_code == 400

    response = client.post(
        reverse("platform-subscription-apply-plan-revision", args=[subscription.pk]),
        {"reason": "Apply revision"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["snapshot_plan_entitlement_revision"] == 2
    assert response.data["effective_module_ids"] == ["people", "finance_core", "analytics"]
    assert response.data["overrides"] == [
        {"module_id": "analytics", "state": ModuleOverrideState.ENABLED}
    ]


def test_apply_plan_revision_rejects_invalid_preserved_override_without_history() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *ALL_CAPABILITIES)
    original = ("people", "client_contracts", "security_operations", "security_patrol")
    company, plan, subscription = legacy_subscription(operator, original)
    entitlements.convert_company_to_subscription_entitlements(
        actor=operator,
        company=company,
        overrides={"security_patrol": ModuleOverrideState.ENABLED},
    )
    subscription.refresh_from_db()
    old_snapshot_revision = subscription.snapshot_plan_entitlement_revision
    history_count = subscription.entitlement_events.count()
    entitlements.set_plan_module_defaults(
        actor=operator, plan=plan, module_ids=("people", "client_contracts")
    )

    response = authenticated(operator).post(
        reverse("platform-subscription-apply-plan-revision", args=[subscription.pk]),
        {"reason": "Invalid update"},
        format="json",
    )
    assert response.status_code == 400
    subscription.refresh_from_db()
    assert subscription.snapshot_plan_entitlement_revision == old_snapshot_revision
    assert subscription.entitlement_events.count() == history_count


def test_legacy_activation_is_atomic_explicit_and_conflict_safe() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *ALL_CAPABILITIES)
    company, plan, subscription = legacy_subscription(
        operator, ("people", "client_contracts", "finance_core", "billing_receivables")
    )
    url = reverse("platform-subscription-activate-entitlements", args=[subscription.pk])
    client = authenticated(operator)

    preview = client.get(reverse("platform-subscription-entitlements", args=[subscription.pk]))
    assert preview.status_code == 200
    assert preview.data["policy_mode"] == CompanyModulePolicyMode.LEGACY_FULL
    assert preview.data["plan_module_ids"] == [
        "people",
        "client_contracts",
        "finance_core",
        "billing_receivables",
    ]
    activated = client.post(
        url,
        {
            "enabled_module_ids": ["analytics"],
            "disabled_module_ids": [],
            "reason": "Activate contracted modules",
        },
        format="json",
    )
    assert activated.status_code == 200
    assert activated.data["policy_mode"] == CompanyModulePolicyMode.SUBSCRIPTION
    assert activated.data["snapshot_initialized"] is True
    assert activated.data["effective_module_ids"][-1] == "analytics"
    assert activated.data["plan_entitlement_revision"] == plan.entitlement_revision

    conflict = client.post(url, {"reason": "Duplicate"}, format="json")
    assert conflict.status_code == 409


def test_legacy_activation_validation_rolls_back_all_entitlement_state() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *ALL_CAPABILITIES)
    company, _plan, subscription = legacy_subscription(operator, ("people",))
    response = authenticated(operator).post(
        reverse("platform-subscription-activate-entitlements", args=[subscription.pk]),
        {
            "enabled_module_ids": ["security_patrol"],
            "reason": "Invalid activation",
        },
        format="json",
    )
    assert response.status_code == 400
    assert (
        CompanyModulePolicy.objects.get(company=company).mode == CompanyModulePolicyMode.LEGACY_FULL
    )
    subscription.refresh_from_db()
    assert subscription.snapshot_initialized_at is None
    assert subscription.module_snapshot.count() == 0
    assert subscription.module_overrides.count() == 0
    assert subscription.entitlement_events.count() == 0


def test_tenant_membership_never_authorizes_subscription_entitlement_detail() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *ALL_CAPABILITIES)
    company, _plan, subscription = legacy_subscription(operator, ("people",))
    tenant = UserFactory.create()
    tenant_admin(tenant, company)
    assert (
        authenticated(tenant)
        .get(reverse("platform-subscription-entitlements", args=[subscription.pk]))
        .status_code
        == 403
    )
