from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.identity.models import Role, User
from dsms.organization.models import Company, TenantProvisioningRequest
from tests.factories.identity import RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


def tenant_admin_roles() -> tuple[Role, Role]:
    organization_admin = RoleFactory.create(code="ORGANIZATION_ADMIN", is_system=True)
    organization_admin.permissions.add(
        *Permission.objects.filter(
            content_type__app_label="organization",
            codename__in=("view_company", "add_company"),
        )
    )
    access_admin = RoleFactory.create(code="ACCESS_ADMIN", is_system=True)
    return organization_admin, access_admin


def payload(
    *, code: str = "ALPHA", email: str = "admin@alpha.example", key: object | None = None
) -> dict[str, object]:
    return {
        "idempotency_key": str(key or uuid4()),
        "company": {
            "code": code,
            "legal_name": f"{code.title()} Security Limited",
            "trade_name": f"{code.title()} Security",
            "registration_number": f"REG-{code}",
            "tax_number": f"TAX-{code}",
            "country_code": "PK",
            "timezone": "Asia/Karachi",
            "default_currency": "PKR",
            "brand_tagline": f"{code.title()} assurance",
            "brand_primary_color": "#123456",
            "brand_accent_color": "#ABCDEF",
            "invoice_number_prefix": f"{code[:3]}I",
            "receipt_number_prefix": f"{code[:3]}R",
            "credit_note_number_prefix": f"{code[:3]}C",
            "debit_note_number_prefix": f"{code[:3]}D",
        },
        "initial_admin": {
            "email": email,
            "first_name": code.title(),
            "last_name": "Administrator",
        },
    }


def authenticated_client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_unauthenticated_and_tenant_users_cannot_provision_or_probe() -> None:
    url = reverse("tenant-provisioning-list")
    detail = reverse("tenant-provisioning-detail", args=[uuid4()])
    assert APIClient().post(url, payload(), format="json").status_code == 401
    assert APIClient().get(detail).status_code == 401

    tenant_user = UserFactory.create()
    client = authenticated_client(tenant_user)
    assert client.post(url, payload(), format="json").status_code == 403
    assert client.get(detail).status_code == 403

    inactive_superuser = UserFactory.create(is_staff=True, is_superuser=True, is_active=False)
    client.force_authenticate(inactive_superuser)
    assert client.post(url, payload(), format="json").status_code == 403
    assert TenantProvisioningRequest.objects.count() == 0
    assert Company.objects.count() == 0


def test_platform_superuser_provisions_and_replays_same_result() -> None:
    tenant_admin_roles()
    actor = UserFactory.create(is_staff=True, is_superuser=True)
    client = authenticated_client(actor)
    request_payload = payload()

    first = client.post(reverse("tenant-provisioning-list"), request_payload, format="json")
    second = client.post(reverse("tenant-provisioning-list"), request_payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.data["id"] == first.data["id"]
    assert second.data["company"]["id"] == first.data["company"]["id"]
    assert first.data["company"]["brand_primary_color"] == "#123456"
    assert first.data["initial_admin"]["is_superuser"] is False
    assert first.data["initial_admin"]["is_staff"] is False
    assert Company.objects.filter(code="ALPHA").count() == 1

    detail = client.get(reverse("tenant-provisioning-detail", args=[first.data["id"]]))
    assert detail.status_code == 200
    assert detail.data["status"] == "SUCCEEDED"


def test_conflicting_retry_returns_safe_409_and_preserves_alpha() -> None:
    tenant_admin_roles()
    actor = UserFactory.create(is_staff=True, is_superuser=True)
    client = authenticated_client(actor)
    key = uuid4()
    assert (
        client.post(
            reverse("tenant-provisioning-list"), payload(key=key), format="json"
        ).status_code
        == 201
    )

    response = client.post(
        reverse("tenant-provisioning-list"),
        payload(code="BRAVO", email="admin@bravo.example", key=key),
        format="json",
    )

    assert response.status_code == 409
    assert response.data["code"] == "provisioning_conflict"
    assert "fingerprint" not in str(response.data).lower()
    assert Company.objects.filter(code="ALPHA").count() == 1
    assert Company.objects.filter(code="BRAVO").count() == 0


def test_provisioned_tenant_admin_cannot_create_or_read_peer_company() -> None:
    tenant_admin_roles()
    actor = UserFactory.create(is_staff=True, is_superuser=True)
    platform = authenticated_client(actor)
    alpha = platform.post(reverse("tenant-provisioning-list"), payload(code="ALPHA"), format="json")
    bravo = platform.post(
        reverse("tenant-provisioning-list"),
        payload(code="BRAVO", email="admin@bravo.example"),
        format="json",
    )
    assert alpha.status_code == bravo.status_code == 201

    alpha_admin = User.objects.get(pk=alpha.data["initial_admin"]["id"])
    tenant = authenticated_client(alpha_admin)
    assert (
        tenant.get(f"/api/v1/organization/companies/{alpha.data['company']['id']}/").status_code
        == 200
    )
    assert (
        tenant.get(f"/api/v1/organization/companies/{bravo.data['company']['id']}/").status_code
        == 404
    )
    raw_peer = tenant.post(
        "/api/v1/organization/companies/",
        {
            "code": "CHARLIE",
            "legal_name": "Charlie Security",
            "country_code": "PK",
            "timezone": "Asia/Karachi",
            "default_currency": "PKR",
        },
        format="json",
    )
    assert raw_peer.status_code == 403
    assert Company.objects.filter(code="CHARLIE").count() == 0


def test_platform_status_lookup_returns_404_without_enumerating_to_tenant() -> None:
    actor = UserFactory.create(is_staff=True, is_superuser=True)
    missing = reverse("tenant-provisioning-detail", args=[uuid4()])
    assert authenticated_client(actor).get(missing).status_code == 404
    assert authenticated_client(UserFactory.create()).get(missing).status_code == 403
