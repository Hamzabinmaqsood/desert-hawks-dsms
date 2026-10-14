from datetime import timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
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
from dsms.subscriptions import services
from dsms.subscriptions.models import Subscription, SubscriptionStatus
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import PlanFactory

pytestmark = pytest.mark.django_db

COMMERCIAL_CAPABILITIES = (
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


def tenant_admin_roles() -> tuple[Role, Role]:
    organization_admin = RoleFactory.create(code="ORGANIZATION_ADMIN", is_system=True)
    organization_admin.permissions.add(
        *Permission.objects.filter(
            content_type__app_label="organization",
            codename__in=("view_company", "add_company", "change_company"),
        )
    )
    return organization_admin, RoleFactory.create(code="ACCESS_ADMIN", is_system=True)


def assign_tenant_admin(user: User, company: Company, roles: tuple[Role, Role]) -> None:
    for role in roles:
        UserRoleAssignmentFactory.create(
            user=user,
            role=role,
            scope_type=AccessScopeType.COMPANY,
            company=company,
        )


def test_tenant_staff_and_multi_company_admins_cannot_manage_commercial_state() -> None:
    company_a = CompanyFactory.create(code="ALPHA")
    company_b = CompanyFactory.create(code="BRAVO")
    roles = tenant_admin_roles()
    tenant = UserFactory.create()
    tenant_ab = UserFactory.create()
    staff = UserFactory.create(is_staff=True)
    assign_tenant_admin(tenant, company_a, roles)
    assign_tenant_admin(tenant_ab, company_a, roles)
    assign_tenant_admin(tenant_ab, company_b, roles)

    for actor in (UserFactory.create(), tenant, tenant_ab, staff):
        client = authenticated(actor)
        assert client.get(reverse("platform-plan-list")).status_code == 403
        assert client.get(reverse("platform-subscription-list")).status_code == 403
        assert (
            client.post(
                reverse("platform-plan-list"),
                {"code": "CORE", "name": "Core"},
                format="json",
            ).status_code
            == 403
        )


def test_platform_only_operator_manages_allowlisted_domain_without_tenant_authority() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *COMMERCIAL_CAPABILITIES)
    company = CompanyFactory.create(code="ALPHA")
    client = authenticated(operator)

    plan_response = client.post(
        reverse("platform-plan-list"),
        {"code": " core ", "name": "Core", "description": "Provider neutral"},
        format="json",
    )
    assert plan_response.status_code == 201
    assert set(plan_response.data) == {
        "id",
        "code",
        "name",
        "description",
        "is_active",
        "created_at",
        "updated_at",
    }
    assert plan_response.data["code"] == "CORE"

    subscription_response = client.post(
        reverse("platform-subscription-list"),
        {
            "company_id": str(company.id),
            "plan_id": plan_response.data["id"],
            "status": SubscriptionStatus.ACTIVE,
        },
        format="json",
    )
    assert subscription_response.status_code == 201
    subscription_id = subscription_response.data["id"]
    assert set(subscription_response.data) == {
        "id",
        "company",
        "plan",
        "status",
        "starts_at",
        "trial_ends_at",
        "grace_ends_at",
        "suspended_at",
        "terminated_at",
        "created_at",
        "updated_at",
    }
    assert subscription_response.data["company"]["id"] == str(company.id)

    transition = client.post(
        reverse("platform-subscription-transition", args=[subscription_id]),
        {"target_status": SubscriptionStatus.SUSPENDED, "reason": "Manual review"},
        format="json",
    )
    assert transition.status_code == 200
    history = client.get(reverse("platform-subscription-history", args=[subscription_id]))
    assert history.status_code == 200
    assert [event["event_type"] for event in history.data] == ["CREATED", "STATUS_CHANGED"]
    assert set(history.data[0]) == {
        "id",
        "event_type",
        "previous_status",
        "resulting_status",
        "actor_id",
        "reason",
        "occurred_at",
    }

    assert (
        client.delete(reverse("platform-plan-detail", args=[plan_response.data["id"]])).status_code
        == 405
    )
    assert (
        client.patch(
            reverse("platform-subscription-detail", args=[subscription_id]), {}
        ).status_code
        == 405
    )
    assert (
        client.patch(
            reverse("platform-subscription-history", args=[subscription_id]), {}
        ).status_code
        == 405
    )
    assert (
        client.delete(reverse("platform-subscription-history", args=[subscription_id])).status_code
        == 405
    )
    assert client.get(f"/api/v1/organization/companies/{company.id}/").status_code == 403
    assert client.get("/api/v1/workforce/employees/").status_code == 403


def test_duplicate_inactive_plan_and_illegal_transition_are_safe() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *COMMERCIAL_CAPABILITIES)
    company = CompanyFactory.create()
    active = PlanFactory.create()
    inactive = PlanFactory.create(is_active=False)
    client = authenticated(operator)

    first = client.post(
        reverse("platform-subscription-list"),
        {"company_id": str(company.id), "plan_id": str(active.id)},
        format="json",
    )
    assert first.status_code == 201
    duplicate = client.post(
        reverse("platform-subscription-list"),
        {"company_id": str(company.id), "plan_id": str(active.id)},
        format="json",
    )
    assert duplicate.status_code == 409
    inactive_response = client.post(
        reverse("platform-subscription-list"),
        {"company_id": str(CompanyFactory.create().id), "plan_id": str(inactive.id)},
        format="json",
    )
    assert inactive_response.status_code == 400
    illegal = client.post(
        reverse("platform-subscription-transition", args=[first.data["id"]]),
        {"target_status": SubscriptionStatus.ACTIVE},
        format="json",
    )
    assert illegal.status_code == 409
    assert Subscription.objects.get(pk=first.data["id"]).events.count() == 1


def test_revocation_inactive_user_and_unauthenticated_requests_fail_closed() -> None:
    operator = UserFactory.create()
    grant_platform(operator, VIEW_PLAN_CATALOG, MANAGE_PLAN_CATALOG)
    client = authenticated(operator)
    assert client.get(reverse("platform-plan-list")).status_code == 200

    operator.user_permissions.remove(permission(VIEW_PLAN_CATALOG))
    assert client.get(reverse("platform-plan-list")).status_code == 403
    operator.user_permissions.add(permission(VIEW_PLAN_CATALOG))
    operator.is_active = False
    operator.save(update_fields=["is_active"])
    assert client.get(reverse("platform-plan-list")).status_code == 403

    anonymous = APIClient()
    assert anonymous.get(reverse("platform-plan-list")).status_code == 401
    assert anonymous.get(reverse("platform-subscription-list")).status_code == 401


def test_subscription_status_does_not_enforce_tenant_access_or_company_activity() -> None:
    company = CompanyFactory.create(code="ALPHA", is_active=True)
    roles = tenant_admin_roles()
    tenant_admin = UserFactory.create()
    assign_tenant_admin(tenant_admin, company, roles)
    tenant_client = authenticated(tenant_admin)
    company_url = f"/api/v1/organization/companies/{company.id}/"

    assert tenant_client.get(company_url).status_code == 200
    operator = UserFactory.create()
    grant_platform(operator, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    subscription = services.create_subscription(
        actor=operator,
        company=company,
        plan=PlanFactory.create(),
    )
    assert tenant_client.get(company_url).status_code == 200
    services.transition_subscription(
        actor=operator,
        subscription=subscription,
        target_status=SubscriptionStatus.SUSPENDED,
    )
    assert tenant_client.get(company_url).status_code == 200
    company.refresh_from_db()
    assert company.is_active is True

    inactive = CompanyFactory.create(is_active=False)
    assign_tenant_admin(tenant_admin, inactive, roles)
    assert tenant_client.get(f"/api/v1/organization/companies/{inactive.id}/").status_code != 200


def test_mixed_operator_can_manage_commercial_but_not_peer_tenant_resources() -> None:
    company_a = CompanyFactory.create(code="ALPHA")
    company_b = CompanyFactory.create(code="BRAVO")
    roles = tenant_admin_roles()
    operator = UserFactory.create()
    assign_tenant_admin(operator, company_a, roles)
    grant_platform(operator, *COMMERCIAL_CAPABILITIES)
    client = authenticated(operator)

    created = client.post(
        reverse("platform-subscription-list"),
        {"company_id": str(company_b.id), "plan_id": str(PlanFactory.create().id)},
        format="json",
    )
    assert created.status_code == 201
    assert client.get(f"/api/v1/organization/companies/{company_a.id}/").status_code == 200
    assert client.get(f"/api/v1/organization/companies/{company_b.id}/").status_code == 404


def test_provisioning_remains_independent_of_commercial_subscription() -> None:
    organization_admin, access_admin = tenant_admin_roles()
    assert organization_admin.is_system and access_admin.is_system
    actor = UserFactory.create(is_staff=True, is_superuser=True)
    client = authenticated(actor)
    response = client.post(
        reverse("tenant-provisioning-list"),
        {
            "idempotency_key": str(uuid4()),
            "company": {
                "code": "NEWCO",
                "legal_name": "New Company Limited",
                "country_code": "PK",
                "timezone": "Asia/Karachi",
                "default_currency": "PKR",
            },
            "initial_admin": {"email": "admin@newco.example"},
        },
        format="json",
    )
    assert response.status_code == 201
    assert not Subscription.objects.filter(company_id=response.data["company"]["id"]).exists()


def test_trial_and_grace_dates_are_explicit_at_api_boundary() -> None:
    operator = UserFactory.create()
    grant_platform(operator, *COMMERCIAL_CAPABILITIES)
    client = authenticated(operator)
    plan = PlanFactory.create()
    company = CompanyFactory.create()

    missing_trial_end = client.post(
        reverse("platform-subscription-list"),
        {
            "company_id": str(company.id),
            "plan_id": str(plan.id),
            "status": SubscriptionStatus.TRIAL,
        },
        format="json",
    )
    assert missing_trial_end.status_code == 400

    starts_at = timezone.now()
    created = client.post(
        reverse("platform-subscription-list"),
        {
            "company_id": str(company.id),
            "plan_id": str(plan.id),
            "status": SubscriptionStatus.TRIAL,
            "starts_at": starts_at.isoformat(),
            "trial_ends_at": (starts_at + timedelta(days=3)).isoformat(),
        },
        format="json",
    )
    assert created.status_code == 201
    missing_grace_end = client.post(
        reverse("platform-subscription-transition", args=[created.data["id"]]),
        {"target_status": SubscriptionStatus.GRACE},
        format="json",
    )
    assert missing_grace_end.status_code == 400
