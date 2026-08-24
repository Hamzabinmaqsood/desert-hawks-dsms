from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from dsms.finance import domain_services
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
