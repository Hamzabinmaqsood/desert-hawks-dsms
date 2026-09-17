from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import RequestFactory

from dsms.finance import domain_selectors, domain_services
from dsms.finance.admin import ProtectedFinanceAdmin
from dsms.finance.enums import MatchType, ReceiptType, WorkflowStatus
from dsms.finance.exceptions import FinanceValidationError
from dsms.finance.procurement_models import (
    PaymentVoucher,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def procurement():  # type: ignore[no-untyped-def]
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    vendor = Vendor.objects.create(
        company=company,
        code="V-1",
        name="Supplier",
        payable_account=accounts["payable"],
    )
    requisition = PurchaseRequisition.objects.create(
        company=company,
        requisition_number="PRQ-1",
        required_date=date(2026, 8, 10),
        purpose="Equipment",
        created_by=maker,
    )
    req_line = PurchaseRequisitionLine.objects.create(
        requisition=requisition,
        description="Radios",
        quantity=Decimal("10"),
        estimated_unit_price=Decimal("100"),
        expense_account=accounts["expense"],
    )
    requisition = domain_services.submit_finance_document(
        obj=requisition, actor=maker, document_type="PURCHASE_REQUISITION"
    )
    requisition = domain_services.approve_finance_document(
        obj=requisition, actor=checker, document_type="PURCHASE_REQUISITION"
    )
    order = PurchaseOrder.objects.create(
        company=company,
        requisition=requisition,
        vendor=vendor,
        order_number="PO-1",
        order_date=date(2026, 8, 11),
        created_by=maker,
    )
    order_line = PurchaseOrderLine.objects.create(
        purchase_order=order,
        requisition_line=req_line,
        description="Radios",
        quantity=Decimal("10"),
        unit_price=Decimal("100"),
    )
    order = domain_services.submit_finance_document(
        obj=order, actor=maker, document_type="PURCHASE_ORDER"
    )
    order = domain_services.approve_finance_document(
        obj=order, actor=checker, document_type="PURCHASE_ORDER"
    )
    return company, maker, checker, accounts, vendor, order, order_line


def test_partial_receipts_and_overreceipt_prevention(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, _checker, _accounts, _vendor, order, line = procurement
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="GRN-1",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    PurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=line,
        quantity=Decimal("6"),
        accepted_quantity=Decimal("6"),
    )
    domain_services.confirm_receipt(receipt=receipt)
    excess = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="GRN-2",
        receipt_date=date(2026, 8, 13),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    PurchaseReceiptLine.objects.create(
        receipt=excess,
        purchase_order_line=line,
        quantity=Decimal("5"),
        accepted_quantity=Decimal("5"),
    )
    with pytest.raises(FinanceValidationError):
        domain_services.confirm_receipt(receipt=excess)


def test_three_way_match_bill_payment_and_outstanding(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, checker, accounts, vendor, order, line = procurement
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="GRN-1",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    receipt_line = PurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=line,
        quantity=Decimal("10"),
        accepted_quantity=Decimal("10"),
    )
    domain_services.confirm_receipt(receipt=receipt)
    bill = VendorBill.objects.create(
        company=company,
        vendor=vendor,
        purchase_order=order,
        vendor_invoice_number="INV-1",
        bill_number="BILL-1",
        bill_date=date(2026, 8, 15),
        due_date=date(2026, 9, 15),
        match_type=MatchType.THREE_WAY,
        status=WorkflowStatus.SUBMITTED,
        subtotal=Decimal("1000"),
        total_amount=Decimal("1000"),
        created_by=maker,
    )
    VendorBillLine.objects.create(
        vendor_bill=bill,
        purchase_order_line=line,
        receipt_line=receipt_line,
        description="Radios",
        quantity=Decimal("10"),
        unit_price=Decimal("100"),
        expense_account=accounts["expense"],
    )
    bill = domain_services.approve_and_post_vendor_bill(bill=bill, actor=checker)
    assert bill.status == WorkflowStatus.POSTED
    assert bill.journal_entry and bill.journal_entry.total_debit == bill.journal_entry.total_credit
    voucher = PaymentVoucher.objects.create(
        company=company,
        vendor_bill=bill,
        voucher_number="PV-1",
        payment_date=date(2026, 8, 18),
        amount=Decimal("400"),
        status=WorkflowStatus.APPROVED,
        created_by=maker,
        approved_by=checker,
    )
    domain_services.pay_vendor_voucher(
        voucher=voucher, actor=checker, cash_account=accounts["cash"], reference="BANK-1"
    )
    bill.refresh_from_db()
    assert bill.status == WorkflowStatus.PARTIALLY_PAID
    assert bill.outstanding_amount == Decimal("600.00")


def test_duplicate_invoice_and_overpayment_are_blocked(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, checker, accounts, vendor, order, _line = procurement
    bill = VendorBill.objects.create(
        company=company,
        vendor=vendor,
        vendor_invoice_number="DUP",
        bill_number="B1",
        bill_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        total_amount=Decimal("100"),
        status=WorkflowStatus.APPROVED,
        created_by=maker,
        approved_by=checker,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        VendorBill.objects.create(
            company=company,
            vendor=vendor,
            vendor_invoice_number="DUP",
            bill_number="B2",
            bill_date=date(2026, 8, 1),
            due_date=date(2026, 8, 31),
            created_by=maker,
        )
    voucher = PaymentVoucher.objects.create(
        company=company,
        vendor_bill=bill,
        voucher_number="PV-X",
        payment_date=date(2026, 8, 2),
        amount=Decimal("101"),
        status=WorkflowStatus.APPROVED,
        created_by=maker,
        approved_by=checker,
    )
    with pytest.raises(FinanceValidationError):
        domain_services.pay_vendor_voucher(
            voucher=voucher, actor=checker, cash_account=accounts["cash"], reference="X"
        )


@pytest.mark.parametrize(
    ("quantity", "accepted", "field"),
    [
        (Decimal("0"), Decimal("0"), "quantity"),
        (Decimal("-1"), Decimal("0"), "quantity"),
        (Decimal("1"), Decimal("-1"), "accepted_quantity"),
        (Decimal("1"), Decimal("2"), "accepted_quantity"),
    ],
)
def test_receipt_line_quantity_model_validation(
    procurement: Any, quantity: Decimal, accepted: Decimal, field: str
) -> None:
    company, maker, _checker, _accounts, _vendor, order, order_line = procurement
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number=f"INVALID-{quantity}-{accepted}",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    line = PurchaseReceiptLine(
        receipt=receipt,
        purchase_order_line=order_line,
        quantity=quantity,
        accepted_quantity=accepted,
    )
    with pytest.raises(ValidationError) as exc_info:
        line.full_clean(validate_unique=False, validate_constraints=False)
    assert field in exc_info.value.message_dict


@pytest.mark.parametrize(
    ("quantity", "accepted"),
    [
        (Decimal("0"), Decimal("0")),
        (Decimal("-1"), Decimal("0")),
        (Decimal("1"), Decimal("-1")),
        (Decimal("1"), Decimal("2")),
    ],
)
def test_receipt_line_quantity_database_constraints(
    procurement: Any, quantity: Decimal, accepted: Decimal
) -> None:
    company, maker, _checker, _accounts, _vendor, order, order_line = procurement
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number=f"DB-INVALID-{quantity}-{accepted}",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PurchaseReceiptLine.objects.create(
            receipt=receipt,
            purchase_order_line=order_line,
            quantity=quantity,
            accepted_quantity=accepted,
        )


def test_receipt_rejects_duplicate_po_line_but_allows_separate_receipts(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, _checker, _accounts, _vendor, order, order_line = procurement
    first = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="DUP-LINE-1",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    PurchaseReceiptLine.objects.create(
        receipt=first,
        purchase_order_line=order_line,
        quantity=Decimal("4"),
        accepted_quantity=Decimal("4"),
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PurchaseReceiptLine.objects.create(
            receipt=first,
            purchase_order_line=order_line,
            quantity=Decimal("1"),
            accepted_quantity=Decimal("1"),
        )
    second = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="DUP-LINE-2",
        receipt_date=date(2026, 8, 13),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    PurchaseReceiptLine.objects.create(
        receipt=second,
        purchase_order_line=order_line,
        quantity=Decimal("6"),
        accepted_quantity=Decimal("6"),
    )
    assert PurchaseReceiptLine.objects.filter(purchase_order_line=order_line).count() == 2


def test_confirmation_validates_po_state_company_and_line_relationship(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, _checker, _accounts, vendor, order, order_line = procurement
    order.status = WorkflowStatus.DRAFT
    order.save(update_fields=["status"])
    draft_po_receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="DRAFT-PO",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    PurchaseReceiptLine.objects.create(
        receipt=draft_po_receipt,
        purchase_order_line=order_line,
        quantity=1,
        accepted_quantity=1,
    )
    with pytest.raises(FinanceValidationError) as exc_info:
        domain_services.confirm_receipt(receipt=draft_po_receipt)
    assert "approved purchase order" in str(exc_info.value.detail)

    order.status = WorkflowStatus.APPROVED
    order.save(update_fields=["status"])
    other_company = CompanyFactory.create()
    wrong_company_receipt = PurchaseReceipt.objects.create(
        company=other_company,
        purchase_order=order,
        receipt_number="WRONG-COMPANY",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    PurchaseReceiptLine.objects.create(
        receipt=wrong_company_receipt,
        purchase_order_line=order_line,
        quantity=1,
        accepted_quantity=1,
    )
    with pytest.raises(FinanceValidationError) as exc_info:
        domain_services.confirm_receipt(receipt=wrong_company_receipt)
    assert "same company" in str(exc_info.value.detail)

    other_order = PurchaseOrder.objects.create(
        company=company,
        requisition=order.requisition,
        vendor=vendor,
        order_number="PO-OTHER",
        order_date=date(2026, 8, 11),
        status=WorkflowStatus.APPROVED,
        created_by=maker,
    )
    other_line = PurchaseOrderLine.objects.create(
        purchase_order=other_order,
        requisition_line=order_line.requisition_line,
        description="Other radios",
        quantity=1,
        unit_price=Decimal("100"),
    )
    cross_po_receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="CROSS-PO",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    PurchaseReceiptLine.objects.create(
        receipt=cross_po_receipt,
        purchase_order_line=other_line,
        quantity=1,
        accepted_quantity=1,
    )
    with pytest.raises(FinanceValidationError) as exc_info:
        domain_services.confirm_receipt(receipt=cross_po_receipt)
    assert "another purchase order" in str(exc_info.value.detail)


def test_partial_receipts_exactly_fill_order_and_inventory_eligibility(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, _checker, _accounts, _vendor, order, order_line = procurement
    lines = []
    for number, receipt_type, quantity in (
        ("ELIGIBLE-4", ReceiptType.GOODS, Decimal("4")),
        ("ELIGIBLE-6", ReceiptType.GOODS, Decimal("6")),
    ):
        receipt = PurchaseReceipt.objects.create(
            company=company,
            purchase_order=order,
            receipt_number=number,
            receipt_date=date(2026, 8, 12),
            receipt_type=receipt_type,
            received_by=maker,
        )
        line = PurchaseReceiptLine.objects.create(
            receipt=receipt,
            purchase_order_line=order_line,
            quantity=quantity,
            accepted_quantity=quantity,
        )
        domain_services.confirm_receipt(receipt=receipt)
        lines.append(line)
    assert all(
        domain_selectors.is_inventory_registration_eligible(receipt_line=line) for line in lines
    )


def test_service_receipt_can_confirm_but_is_not_inventory_eligible(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, _checker, _accounts, _vendor, order, order_line = procurement
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="SERVICE-RECEIPT",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.SERVICE,
        received_by=maker,
    )
    line = PurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=order_line,
        quantity=1,
        accepted_quantity=1,
    )
    confirmed = domain_services.confirm_receipt(receipt=receipt)
    line.refresh_from_db()
    assert confirmed.status == WorkflowStatus.APPROVED
    assert not domain_selectors.is_inventory_registration_eligible(receipt_line=line)


def test_approved_receipt_line_is_readonly_in_supported_admin(procurement) -> None:  # type: ignore[no-untyped-def]
    company, maker, _checker, _accounts, _vendor, order, order_line = procurement
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="ADMIN-LOCKED",
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=maker,
    )
    line = PurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=order_line,
        quantity=1,
        accepted_quantity=1,
    )
    domain_services.confirm_receipt(receipt=receipt)
    line.refresh_from_db()
    model_admin = admin.site._registry[PurchaseReceiptLine]
    assert isinstance(model_admin, ProtectedFinanceAdmin)
    request = RequestFactory().get("/admin/")
    request.user = UserFactory.create(is_superuser=True)
    assert set(model_admin.get_readonly_fields(request, line)) == {
        field.name for field in PurchaseReceiptLine._meta.fields
    }
