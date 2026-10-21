from typing import Any

from django.db.models import Exists, F, OuterRef, Q

from .payment_models import (
    PaymentBatch,
    PaymentBeneficiaryProfile,
    PaymentInstruction,
    PaymentProviderSettlement,
)
from .procurement_models import (
    PaymentVoucher,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
    VendorBill,
)


def tenant_consistent_purchase_requisitions(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PurchaseRequisition.objects.all()
    invalid_lines = PurchaseRequisitionLine.objects.filter(requisition_id=OuterRef("pk")).exclude(
        expense_account__company_id=OuterRef("company_id")
    )
    return (
        queryset.filter(company__is_active=True)
        .filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id")))
        .filter(Q(department__isnull=True) | Q(department__company_id=F("company_id")))
        .filter(Q(cost_center__isnull=True) | Q(cost_center__company_id=F("company_id")))
        .annotate(_has_invalid_requisition_line=Exists(invalid_lines))
        .filter(_has_invalid_requisition_line=False)
    )


def tenant_consistent_purchase_orders(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PurchaseOrder.objects.all()
    invalid_lines = PurchaseOrderLine.objects.filter(purchase_order_id=OuterRef("pk")).exclude(
        requisition_line__requisition_id=OuterRef("requisition_id")
    )
    return (
        queryset.filter(company__is_active=True)
        .filter(vendor__company_id=F("company_id"), requisition__company_id=F("company_id"))
        .filter(requisition__in=tenant_consistent_purchase_requisitions())
        .annotate(_has_invalid_order_line=Exists(invalid_lines))
        .filter(_has_invalid_order_line=False)
    )


def tenant_consistent_purchase_receipts(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PurchaseReceipt.objects.all()
    invalid_lines = PurchaseReceiptLine.objects.filter(receipt_id=OuterRef("pk")).exclude(
        purchase_order_line__purchase_order_id=OuterRef("purchase_order_id")
    )
    return (
        queryset.filter(company__is_active=True)
        .filter(purchase_order__company_id=F("company_id"))
        .filter(purchase_order__in=tenant_consistent_purchase_orders())
        .annotate(_has_invalid_receipt_line=Exists(invalid_lines))
        .filter(_has_invalid_receipt_line=False)
    )


def tenant_consistent_vendors(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else Vendor.objects.all()
    return queryset.filter(payable_account__company_id=F("company_id"))


def tenant_consistent_vendor_bills(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else VendorBill.objects.all()
    return (
        queryset.filter(vendor__company_id=F("company_id"))
        .filter(Q(purchase_order__isnull=True) | Q(purchase_order__company_id=F("company_id")))
        .filter(Q(journal_entry__isnull=True) | Q(journal_entry__company_id=F("company_id")))
    )


def tenant_consistent_payment_vouchers(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PaymentVoucher.objects.all()
    return queryset.filter(
        Q(vendor_bill__isnull=True)
        | Q(
            vendor_bill__company_id=F("company_id"),
            vendor_bill__vendor__company_id=F("company_id"),
        )
    ).filter(Q(journal_entry__isnull=True) | Q(journal_entry__company_id=F("company_id")))


def tenant_consistent_payment_batches(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PaymentBatch.objects.all()
    return queryset.filter(provider__company_id=F("company_id")).filter(
        Q(payroll_run__isnull=True) | Q(payroll_run__company_id=F("company_id"))
    )


def tenant_consistent_payment_beneficiaries(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PaymentBeneficiaryProfile.objects.all()
    return queryset.filter(
        Q(employee__isnull=False, employee__company_id=F("company_id"), vendor__isnull=True)
        | Q(vendor__isnull=False, vendor__company_id=F("company_id"), employee__isnull=True)
    )


def tenant_consistent_payment_instructions(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PaymentInstruction.objects.all()
    return (
        queryset.filter(beneficiary__company_id=F("batch__company_id"))
        .filter(
            Q(payment_voucher__isnull=True)
            | Q(
                payment_voucher__company_id=F("batch__company_id"),
                payment_voucher__vendor_bill__isnull=True,
            )
            | Q(
                payment_voucher__company_id=F("batch__company_id"),
                payment_voucher__vendor_bill__company_id=F("batch__company_id"),
                payment_voucher__vendor_bill__vendor__company_id=F("batch__company_id"),
            )
        )
        .filter(
            Q(payment_voucher__isnull=True)
            | Q(payment_voucher__journal_entry__isnull=True)
            | Q(payment_voucher__journal_entry__company_id=F("batch__company_id"))
        )
        .filter(
            Q(accounting_journal__isnull=True)
            | Q(accounting_journal__company_id=F("batch__company_id"))
        )
        .filter(
            Q(payslip__isnull=True) | Q(payslip__payroll_run__company_id=F("batch__company_id"))
        )
    )


def tenant_consistent_payment_settlements(queryset: Any = None) -> Any:
    queryset = queryset if queryset is not None else PaymentProviderSettlement.objects.all()
    return queryset.filter(provider__company_id=F("company_id")).filter(
        Q(accounting_journal__isnull=True) | Q(accounting_journal__company_id=F("company_id"))
    )
