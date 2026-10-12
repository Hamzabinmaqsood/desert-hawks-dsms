from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User
from dsms.identity.platform_access import (
    PLATFORM_CAPABILITIES,
    PROVISION_TENANT,
    VIEW_PLATFORM_TENANT_DIRECTORY,
    VIEW_TENANT_PROVISIONING,
)
from dsms.organization.models import Company
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def authenticated(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def permission(code: str) -> Permission:
    app_label, codename = code.split(".", maxsplit=1)
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
    access_admin = RoleFactory.create(code="ACCESS_ADMIN", is_system=True)
    return organization_admin, access_admin


def assign_tenant_admin(user: User, company: Company, roles: tuple[Role, Role]) -> None:
    for role in roles:
        UserRoleAssignmentFactory.create(
            user=user,
            role=role,
            scope_type=AccessScopeType.COMPANY,
            company=company,
        )


def payload(code: str = "BRAVO") -> dict[str, object]:
    return {
        "idempotency_key": str(uuid4()),
        "company": {
            "code": code,
            "legal_name": f"{code.title()} Security Limited",
            "country_code": "PK",
            "timezone": "Asia/Karachi",
            "default_currency": "PKR",
        },
        "initial_admin": {"email": f"admin@{code.lower()}.example"},
    }


def test_staff_and_single_or_multi_company_admins_are_not_platform_operators() -> None:
    roles = tenant_admin_roles()
    company_a = CompanyFactory.create(code="ALPHA")
    company_b = CompanyFactory.create(code="BRAVO")
    staff = UserFactory.create(is_staff=True)
    tenant_a = UserFactory.create()
    tenant_ab = UserFactory.create()
    assign_tenant_admin(tenant_a, company_a, roles)
    assign_tenant_admin(tenant_ab, company_a, roles)
    assign_tenant_admin(tenant_ab, company_b, roles)

    for actor in (staff, tenant_a, tenant_ab):
        client = authenticated(actor)
        assert (
            client.post(reverse("tenant-provisioning-list"), payload(), format="json").status_code
            == 403
        )
        assert client.get(reverse("platform-tenant-directory")).status_code == 403
        assert client.get(reverse("tenant-provisioning-detail", args=[uuid4()])).status_code == 403


def test_platform_only_operator_provisions_and_reads_safe_metadata_without_tenant_access() -> None:
    tenant_admin_roles()
    operator = UserFactory.create(is_staff=False, is_superuser=False)
    grant_platform(operator, *PLATFORM_CAPABILITIES)
    client = authenticated(operator)

    response = client.post(reverse("tenant-provisioning-list"), payload(), format="json")
    assert response.status_code == 201
    company_id = response.data["company"]["id"]
    assert operator.role_assignments.count() == 0

    detail = client.get(reverse("tenant-provisioning-detail", args=[response.data["id"]]))
    assert detail.status_code == 200
    directory = client.get(reverse("platform-tenant-directory"))
    assert directory.status_code == 200
    assert directory.data[0]["id"] == company_id
    assert set(directory.data[0]) == {
        "id",
        "code",
        "legal_name",
        "trade_name",
        "is_active",
        "country_code",
        "timezone",
        "default_currency",
        "operational_status",
        "blocker_count",
        "blocker_codes",
        "created_at",
    }

    scopes = client.get("/api/v1/auth/me/access-scopes/")
    assert scopes.status_code == 200
    assert scopes.data["accessible_company_ids"] == []
    assert scopes.data["assignments"] == []
    assert client.get(f"/api/v1/organization/companies/{company_id}/").status_code == 403
    assert client.get("/api/v1/auth/company-branding/").status_code == 404
    assert client.get("/api/v1/workforce/employees/").status_code == 403
    assert client.get("/api/v1/billing/invoices/").status_code == 403


def test_mixed_operator_keeps_company_b_outside_tenant_resource_scope() -> None:
    roles = tenant_admin_roles()
    company_a = CompanyFactory.create(code="ALPHA")
    operator = UserFactory.create()
    assign_tenant_admin(operator, company_a, roles)
    grant_platform(operator, *PLATFORM_CAPABILITIES)
    client = authenticated(operator)

    provisioned = client.post(reverse("tenant-provisioning-list"), payload(), format="json")
    assert provisioned.status_code == 201
    company_b_id = provisioned.data["company"]["id"]

    assert client.get(f"/api/v1/organization/companies/{company_a.pk}/").status_code == 200
    assert client.get(f"/api/v1/organization/companies/{company_b_id}/").status_code == 404
    assert operator.role_assignments.filter(company=company_a).count() == 2
    assert operator.role_assignments.filter(company_id=company_b_id).count() == 0


def test_platform_capabilities_are_independent_and_revocation_is_immediate() -> None:
    tenant_admin_roles()
    operator = UserFactory.create()
    grant_platform(operator, PROVISION_TENANT)
    client = authenticated(operator)

    provisioned = client.post(reverse("tenant-provisioning-list"), payload(), format="json")
    assert provisioned.status_code == 201
    detail_url = reverse("tenant-provisioning-detail", args=[provisioned.data["id"]])
    assert client.get(detail_url).status_code == 403
    assert client.get(reverse("platform-tenant-directory")).status_code == 403

    grant_platform(operator, VIEW_TENANT_PROVISIONING, VIEW_PLATFORM_TENANT_DIRECTORY)
    assert client.get(detail_url).status_code == 200
    assert client.get(reverse("platform-tenant-directory")).status_code == 200

    operator.user_permissions.remove(permission(VIEW_TENANT_PROVISIONING))
    assert client.get(detail_url).status_code == 403
    operator.is_active = False
    operator.save(update_fields=["is_active"])
    assert client.get(reverse("platform-tenant-directory")).status_code == 403


def test_platform_capability_projection_is_safe_and_current() -> None:
    operator = UserFactory.create()
    grant_platform(operator, PROVISION_TENANT, VIEW_TENANT_PROVISIONING)
    client = authenticated(operator)

    response = client.get("/api/v1/auth/me/platform-capabilities/")
    assert response.status_code == 200
    assert response.data == {
        "capabilities": sorted([PROVISION_TENANT, VIEW_TENANT_PROVISIONING]),
        "can_access_platform_admin": True,
    }

    operator.user_permissions.clear()
    response = client.get("/api/v1/auth/me/platform-capabilities/")
    assert response.status_code == 200
    assert response.data == {"capabilities": [], "can_access_platform_admin": False}


def test_platform_endpoints_require_authentication() -> None:
    client = APIClient()
    assert (
        client.post(reverse("tenant-provisioning-list"), payload(), format="json").status_code
        == 401
    )
    assert client.get(reverse("tenant-provisioning-detail", args=[uuid4()])).status_code == 401
    assert client.get(reverse("platform-tenant-directory")).status_code == 401
    assert client.get("/api/v1/auth/me/platform-capabilities/").status_code == 401
