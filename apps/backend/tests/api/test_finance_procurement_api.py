from datetime import date
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from dsms.finance.enums import ReceiptType, WorkflowStatus
from dsms.finance.procurement_models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
)
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_vendor_api_redacts_bank_details() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    response = client.post(
        "/api/v1/finance/domain/vendors/",
        {
            "company": str(company.id),
            "code": "V-API",
            "name": "Vendor API",
            "payable_account": str(accounts["payable"].id),
            "bank_details_encrypted": "ciphertext",
        },
        format="json",
    )
    assert response.status_code == 201
    assert "bank_details_encrypted" not in response.data
    assert client.get("/api/v1/finance/domain/vendors/").status_code == 200


def test_approved_receipt_has_no_supported_api_update_path() -> None:
    company = CompanyFactory.create()
    actor = UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    vendor = Vendor.objects.create(
        company=company, code="LOCKED-VENDOR", name="Supplier", payable_account=accounts["payable"]
    )
    requisition = PurchaseRequisition.objects.create(
        company=company,
        requisition_number="LOCKED-REQ",
        required_date=date(2026, 8, 10),
        purpose="Equipment",
        status=WorkflowStatus.APPROVED,
        created_by=actor,
    )
    requisition_line = PurchaseRequisitionLine.objects.create(
        requisition=requisition,
        description="Equipment",
        quantity=Decimal("1"),
        estimated_unit_price=Decimal("100"),
        expense_account=accounts["expense"],
    )
    order = PurchaseOrder.objects.create(
        company=company,
        requisition=requisition,
        vendor=vendor,
        order_number="LOCKED-PO",
        order_date=date(2026, 8, 11),
        status=WorkflowStatus.APPROVED,
        created_by=actor,
    )
    order_line = PurchaseOrderLine.objects.create(
        purchase_order=order,
        requisition_line=requisition_line,
        description="Equipment",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
    )
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="LOCKED-GRN",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        status=WorkflowStatus.APPROVED,
        received_by=actor,
    )
    PurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=order_line,
        quantity=Decimal("1"),
        accepted_quantity=Decimal("1"),
    )
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    response = client.patch(
        f"/api/v1/finance/domain/purchase-receipts/{receipt.id}/",
        {"receipt_date": "2026-09-01", "receipt_type": ReceiptType.SERVICE},
        format="json",
    )
    assert response.status_code == 405
    receipt.refresh_from_db()
    assert receipt.receipt_date == date(2026, 8, 12)
    assert receipt.receipt_type == ReceiptType.GOODS
