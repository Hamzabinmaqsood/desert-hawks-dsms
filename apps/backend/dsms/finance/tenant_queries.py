from typing import Any

from django.db.models import F, Q

from .payment_models import (
    PaymentBatch,
    PaymentBeneficiaryProfile,
    PaymentInstruction,
    PaymentProviderSettlement,
)
from .procurement_models import PaymentVoucher, Vendor, VendorBill


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
