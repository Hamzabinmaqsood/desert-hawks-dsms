from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models, transaction

from .enums import AccountType, MatchType, WorkflowStatus
from .models import Account
from .procurement_models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceiptLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)

ZERO = Decimal("0.00")
ALLOWED_VENDOR_BILL_ACCOUNT_TYPES = (AccountType.EXPENSE, AccountType.ASSET)


def validate_vendor_bill_header(
    *, company_id: Any, vendor: Vendor, purchase_order: PurchaseOrder | None
) -> None:
    errors: dict[str, str] = {}
    if vendor.company_id != company_id:
        errors["vendor"] = "Vendor must belong to the Bill company."
    if not vendor.is_active:
        errors["vendor"] = "Vendor must be active."
    if purchase_order:
        if purchase_order.company_id != company_id:
            errors["purchase_order"] = "Purchase order must belong to the Bill company."
        elif purchase_order.vendor_id != vendor.id:
            errors["purchase_order"] = "Purchase order must belong to the selected Vendor."
        elif purchase_order.status != WorkflowStatus.APPROVED:
            errors["purchase_order"] = "Purchase order must be approved."
    if errors:
        raise ValidationError(errors)


def validate_vendor_bill_account(*, bill: VendorBill, account: Account) -> None:
    if account.company_id != bill.company_id:
        raise ValidationError({"expense_account": "Account must belong to the Bill company."})
    if (
        not account.is_active
        or not account.allow_posting
        or account.account_type not in ALLOWED_VENDOR_BILL_ACCOUNT_TYPES
    ):
        raise ValidationError(
            {"expense_account": "Select an active posting EXPENSE or ASSET account."}
        )


def validate_vendor_bill_line(
    *,
    bill: VendorBill,
    account: Account,
    purchase_order_line: PurchaseOrderLine | None,
    receipt_line: PurchaseReceiptLine | None,
) -> None:
    validate_vendor_bill_account(bill=bill, account=account)
    errors: dict[str, str] = {}
    if bill.purchase_order_id:
        if not purchase_order_line:
            errors["purchase_order_line"] = "A line from the Bill purchase order is required."
        elif purchase_order_line.purchase_order_id != bill.purchase_order_id:
            errors["purchase_order_line"] = "Purchase-order line belongs to another order."
    elif purchase_order_line:
        errors["purchase_order_line"] = "Set a purchase order on the Bill before linking a line."
    if purchase_order_line and purchase_order_line.purchase_order.company_id != bill.company_id:
        errors["purchase_order_line"] = "Purchase-order line belongs to another company."
    if receipt_line:
        if receipt_line.receipt.company_id != bill.company_id:
            errors["receipt_line"] = "Receipt line belongs to another company."
        elif receipt_line.receipt.status != WorkflowStatus.APPROVED:
            errors["receipt_line"] = "Receipt must be approved."
        elif (
            not purchase_order_line or receipt_line.purchase_order_line_id != purchase_order_line.id
        ):
            errors["receipt_line"] = "Receipt line does not match the purchase-order line."
    if bill.match_type == MatchType.THREE_WAY and not receipt_line:
        errors["receipt_line"] = "Three-way matching requires an approved receipt line."
    if errors:
        raise ValidationError(errors)


def _recalculate(locked: VendorBill) -> VendorBill:
    totals = locked.lines.aggregate(
        subtotal=models.Sum(models.F("quantity") * models.F("unit_price")),
        tax=models.Sum("tax_amount"),
    )
    locked.subtotal = totals["subtotal"] or ZERO
    locked.tax_amount = totals["tax"] or ZERO
    locked.total_amount = locked.subtotal + locked.tax_amount
    locked.save(update_fields=["subtotal", "tax_amount", "total_amount", "updated_at"])
    return locked


def _draft_bill(bill: VendorBill) -> VendorBill:
    locked = VendorBill.objects.select_for_update().get(pk=bill.pk)
    if locked.status != WorkflowStatus.DRAFT:
        raise ValidationError("Only draft Vendor Bills can be edited.")
    return locked


@transaction.atomic
def update_vendor_bill_draft(*, bill: VendorBill, values: dict[str, Any]) -> VendorBill:
    locked = _draft_bill(bill)
    vendor = values.get("vendor", locked.vendor)
    purchase_order = values.get("purchase_order", locked.purchase_order)
    validate_vendor_bill_header(
        company_id=locked.company_id, vendor=vendor, purchase_order=purchase_order
    )
    for field, value in values.items():
        setattr(locked, field, value)
    for line in locked.lines.select_related(
        "expense_account", "purchase_order_line__purchase_order", "receipt_line__receipt"
    ):
        validate_vendor_bill_line(
            bill=locked,
            account=line.expense_account,
            purchase_order_line=line.purchase_order_line,
            receipt_line=line.receipt_line,
        )
    locked.save(update_fields=[*values, "updated_at"])
    return locked


@transaction.atomic
def add_vendor_bill_line(*, bill: VendorBill, values: dict[str, Any]) -> VendorBillLine:
    locked = _draft_bill(bill)
    validate_vendor_bill_line(
        bill=locked,
        account=values["expense_account"],
        purchase_order_line=values.get("purchase_order_line"),
        receipt_line=values.get("receipt_line"),
    )
    line = VendorBillLine.objects.create(vendor_bill=locked, **values)
    _recalculate(locked)
    return line


@transaction.atomic
def update_vendor_bill_line(
    *, bill: VendorBill, line: VendorBillLine, values: dict[str, Any]
) -> VendorBillLine:
    locked = _draft_bill(bill)
    target = VendorBillLine.objects.select_for_update().get(pk=line.pk, vendor_bill=locked)
    account = values.get("expense_account", target.expense_account)
    po_line = values.get("purchase_order_line", target.purchase_order_line)
    receipt_line = values.get("receipt_line", target.receipt_line)
    validate_vendor_bill_line(
        bill=locked, account=account, purchase_order_line=po_line, receipt_line=receipt_line
    )
    for field, value in values.items():
        setattr(target, field, value)
    target.save(update_fields=list(values))
    _recalculate(locked)
    return target


@transaction.atomic
def delete_vendor_bill_line(*, bill: VendorBill, line: VendorBillLine) -> VendorBill:
    locked = _draft_bill(bill)
    target = VendorBillLine.objects.select_for_update().get(pk=line.pk, vendor_bill=locked)
    target.delete()
    return _recalculate(locked)
