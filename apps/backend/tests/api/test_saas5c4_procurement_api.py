# mypy: disable-error-code="arg-type"
from datetime import date

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.finance.enums import WorkflowStatus
from dsms.finance.procurement_models import (
    PurchaseOrder,
    PurchaseReceipt,
    PurchaseRequisition,
    Vendor,
)
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from tests.factories.finance import accounting_setup
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def grant(user: User, company: object, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.add(
        *Permission.objects.filter(content_type__app_label="finance", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def api(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_dedicated_procurement_journey_uses_explicit_scoped_apis() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    vendor = Vendor.objects.create(
        company=company,
        code="SUP-1",
        name="General Supplier",
        payable_account=accounts["payable"],
    )
    maker, checker = UserFactory.create(), UserFactory.create()
    grant(
        maker,
        company,
        "view_purchaserequisition",
        "add_purchaserequisition",
        "change_purchaserequisition",
        "view_purchaseorder",
        "add_purchaseorder",
        "change_purchaseorder",
        "view_purchasereceipt",
        "add_purchasereceipt",
        "change_purchasereceipt",
    )
    grant(
        checker,
        company,
        "view_purchaserequisition",
        "view_purchaseorder",
        "view_purchasereceipt",
        "approve_finance",
    )
    maker_api, checker_api = api(maker), api(checker)

    requisition = maker_api.post(
        "/api/v1/finance/purchase-requisitions/",
        {
            "company": str(company.id),
            "requisition_number": "PR-100",
            "required_date": date(2026, 11, 1),
            "purpose": "Office equipment",
            "lines": [
                {
                    "description": "Laptop",
                    "quantity": "2.0000",
                    "estimated_unit_price": "1000.00",
                    "expense_account": str(accounts["expense"].id),
                }
            ],
        },
        format="json",
    )
    assert requisition.status_code == 201, requisition.data
    assert set(requisition.data).isdisjoint({"approved_at", "bank_details_encrypted"})
    requisition_id = requisition.data["id"]
    requisition_line_id = requisition.data["lines"][0]["id"]
    assert (
        maker_api.post(
            f"/api/v1/finance/purchase-requisitions/{requisition_id}/submit/"
        ).status_code
        == 200
    )
    approved_requisition = checker_api.post(
        f"/api/v1/finance/purchase-requisitions/{requisition_id}/approve/"
    )
    assert approved_requisition.status_code == 200
    assert approved_requisition.data["status"] == WorkflowStatus.APPROVED

    order = maker_api.post(
        "/api/v1/finance/purchase-orders/",
        {
            "company": str(company.id),
            "requisition": requisition_id,
            "vendor": str(vendor.id),
            "order_number": "PO-100",
            "order_date": date(2026, 10, 20),
            "lines": [
                {
                    "requisition_line": requisition_line_id,
                    "description": "Laptop",
                    "quantity": "2.0000",
                    "unit_price": "950.00",
                    "tax_amount": "0.00",
                }
            ],
        },
        format="json",
    )
    assert order.status_code == 201, order.data
    order_id = order.data["id"]
    order_line_id = order.data["lines"][0]["id"]
    assert maker_api.post(f"/api/v1/finance/purchase-orders/{order_id}/submit/").status_code == 200
    assert (
        checker_api.post(f"/api/v1/finance/purchase-orders/{order_id}/approve/").status_code == 200
    )

    receipt = maker_api.post(
        "/api/v1/finance/purchase-receipts/",
        {
            "company": str(company.id),
            "purchase_order": order_id,
            "receipt_number": "GRN-100",
            "receipt_date": date(2026, 10, 21),
            "receipt_type": "GOODS",
            "lines": [
                {
                    "purchase_order_line": order_line_id,
                    "quantity": "1.0000",
                    "accepted_quantity": "1.0000",
                    "notes": "Partial delivery",
                }
            ],
        },
        format="json",
    )
    assert receipt.status_code == 201, receipt.data
    confirmed = maker_api.post(f"/api/v1/finance/purchase-receipts/{receipt.data['id']}/confirm/")
    assert confirmed.status_code == 200, confirmed.data
    assert confirmed.data["status"] == WorkflowStatus.APPROVED
    assert PurchaseRequisition.objects.get(pk=requisition_id).company == company
    assert PurchaseOrder.objects.get(pk=order_id).vendor == vendor
    assert str(PurchaseReceipt.objects.get(pk=receipt.data["id"]).purchase_order_id) == order_id

    over_receipt = maker_api.post(
        "/api/v1/finance/purchase-receipts/",
        {
            "company": str(company.id),
            "purchase_order": order_id,
            "receipt_number": "GRN-101",
            "receipt_date": date(2026, 10, 22),
            "receipt_type": "GOODS",
            "lines": [
                {
                    "purchase_order_line": order_line_id,
                    "quantity": "2.0000",
                    "accepted_quantity": "2.0000",
                }
            ],
        },
        format="json",
    )
    assert over_receipt.status_code == 400
    assert "remaining order quantity" in str(over_receipt.data)


def test_procurement_rejects_cross_company_graph_even_with_a_and_b_access() -> None:
    company_a, company_b = CompanyFactory.create(), CompanyFactory.create()
    _ay, _ap, accounts_a = accounting_setup(company_a)
    _by, _bp, accounts_b = accounting_setup(company_b)
    vendor_b = Vendor.objects.create(
        company=company_b,
        code="B-SUP",
        name="Foreign supplier",
        payable_account=accounts_b["payable"],
    )
    user = UserFactory.create()
    permissions = (
        "view_purchaserequisition",
        "add_purchaserequisition",
        "view_purchaseorder",
        "add_purchaseorder",
        "view_purchasereceipt",
        "add_purchasereceipt",
    )
    grant(user, company_a, *permissions)
    grant(user, company_b, *permissions)
    client = api(user)
    rejected_line = client.post(
        "/api/v1/finance/purchase-requisitions/",
        {
            "company": str(company_a.id),
            "requisition_number": "A-CROSS",
            "required_date": date(2026, 11, 1),
            "purpose": "Cross company probe",
            "lines": [
                {
                    "description": "Foreign account",
                    "quantity": "1",
                    "estimated_unit_price": "1",
                    "expense_account": str(accounts_b["expense"].id),
                }
            ],
        },
        format="json",
    )
    assert rejected_line.status_code == 400

    requisition_a = PurchaseRequisition.objects.create(
        company=company_a,
        requisition_number="A-APPROVED",
        required_date=date(2026, 11, 1),
        purpose="Valid source",
        status=WorkflowStatus.APPROVED,
        created_by=user,
    )
    rejected_vendor = client.post(
        "/api/v1/finance/purchase-orders/",
        {
            "company": str(company_a.id),
            "requisition": str(requisition_a.id),
            "vendor": str(vendor_b.id),
            "order_number": "A-PO-CROSS",
            "order_date": date(2026, 10, 20),
            "lines": [],
        },
        format="json",
    )
    assert rejected_vendor.status_code == 400


def test_foreign_and_historically_corrupt_procurement_rows_are_non_enumerating() -> None:
    company_a, company_b = CompanyFactory.create(), CompanyFactory.create()
    user = UserFactory.create()
    grant(user, company_a, "view_purchaserequisition")
    valid = PurchaseRequisition.objects.create(
        company=company_a,
        requisition_number="A-VALID",
        required_date=date(2026, 11, 1),
        purpose="Visible",
        created_by=user,
    )
    foreign = PurchaseRequisition.objects.create(
        company=company_b,
        requisition_number="B-HIDDEN",
        required_date=date(2026, 11, 1),
        purpose="Hidden",
        created_by=user,
    )
    client = api(user)
    listed = client.get("/api/v1/finance/purchase-requisitions/")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.data["results"]] == [str(valid.id)]
    assert client.get(f"/api/v1/finance/purchase-requisitions/{foreign.id}/").status_code == 404
