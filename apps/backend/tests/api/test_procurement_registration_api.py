from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.unit.test_procurement_inventory_registration import graph

pytestmark = pytest.mark.django_db


def assign(user: Any, company: Any, *permissions: str) -> None:
    role = RoleFactory.create()
    role.permissions.set(Permission.objects.filter(codename__in=permissions))
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )


def payload(item: Any, store: Any, line: Any, key: Any) -> dict[str, str]:
    return {
        "receipt_line": str(line.pk),
        "asset_item": str(item.pk),
        "destination_store": str(store.pk),
        "idempotency_key": str(key),
        "quantity": "4.000",
    }


def test_procurement_registration_requires_authentication() -> None:
    client = APIClient()
    assert client.get("/api/v1/assets/procurement-registrations/").status_code == 401
    assert client.post("/api/v1/assets/procurement-registrations/", {}).status_code == 401
    client.force_authenticate(UserFactory.create())
    assert client.get("/api/v1/assets/procurement-registrations/").status_code == 403


def test_quantity_create_replay_history_and_financial_masking() -> None:
    company, _actor, item, store, line = graph()
    user = UserFactory.create()
    assign(
        user,
        company,
        "receive_asset_stock",
        "view_purchasereceipt",
        "view_procurementinventoryregistration",
    )
    client = APIClient()
    client.force_authenticate(user)
    body = payload(item, store, line, uuid4())
    created = client.post("/api/v1/assets/procurement-registrations/", body, format="json")
    assert created.status_code == 201
    assert created.data["replayed"] is False
    assert created.data["unit_cost_snapshot"] is None
    replay = client.post("/api/v1/assets/procurement-registrations/", body, format="json")
    assert replay.status_code == 200 and replay.data["replayed"] is True
    listed = client.get("/api/v1/assets/procurement-registrations/")
    assert listed.status_code == 200 and listed.data["count"] == 1
    assert (
        client.patch(
            f"/api/v1/assets/procurement-registrations/{created.data['id']}/",
            {"quantity": "1"},
            format="json",
        ).status_code
        == 405
    )


def test_changed_payload_conflicts_and_superuser_sees_cost() -> None:
    _company, _actor, item, store, line = graph()
    user = UserFactory.create(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    key = uuid4()
    assert (
        client.post(
            "/api/v1/assets/procurement-registrations/",
            payload(item, store, line, key),
            format="json",
        ).status_code
        == 201
    )
    changed = payload(item, store, line, key)
    changed["quantity"] = "5.000"
    conflict = client.post("/api/v1/assets/procurement-registrations/", changed, format="json")
    assert conflict.status_code == 409
    detail = client.get("/api/v1/assets/procurement-registrations/").data["results"][0]
    assert Decimal(detail["unit_cost_snapshot"]) == Decimal("25.50")


def test_cross_company_source_probe_is_404() -> None:
    company, _actor, item, store, line = graph()
    user = UserFactory.create()
    other_company, *_rest = graph()
    assign(user, other_company, "receive_asset_stock", "view_purchasereceipt")
    client = APIClient()
    client.force_authenticate(user)
    assert (
        client.post(
            "/api/v1/assets/procurement-registrations/",
            payload(item, store, line, uuid4()),
            format="json",
        ).status_code
        == 404
    )
    assert company != other_company
