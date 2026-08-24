from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import QuerySet, Sum
from django.utils import timezone

from .enums import InvoiceStatus
from .models import ClientAccountTransaction, ClientInvoice, ClientReceipt

ZERO = Decimal("0.00")


def get_client_account_balance(client: Any, as_of_date: date | None = None) -> dict[str, Decimal]:
    invoices = ClientInvoice.objects.filter(client=client).exclude(
        status__in=[InvoiceStatus.VOIDED, InvoiceStatus.CANCELLED]
    )
    receipts = ClientReceipt.objects.filter(client=client).exclude(
        status__in=["REVERSED", "CANCELLED"]
    )
    if as_of_date:
        invoices = invoices.filter(invoice_date__lte=as_of_date)
        receipts = receipts.filter(received_at__date__lte=as_of_date)
    invoiced = invoices.aggregate(total=Sum("total_amount"))["total"] or ZERO
    payments = invoices.aggregate(total=Sum("amount_paid"))["total"] or ZERO
    receipt_total = receipts.aggregate(total=Sum("amount"))["total"] or ZERO
    allocated = receipts.aggregate(total=Sum("allocations__amount"))["total"] or ZERO
    return {
        "invoiced": invoiced,
        "credit_notes": ZERO,
        "debit_notes": ZERO,
        "payments": payments,
        "unallocated_receipts": receipt_total - allocated,
        "outstanding": invoiced - payments,
    }


def get_accounts_receivable_ageing(
    *, company: Any, as_of_date: date | None = None, client: Any = None
) -> dict[str, Decimal]:
    as_of = as_of_date or timezone.localdate()
    result = {
        "CURRENT": ZERO,
        "1-30": ZERO,
        "31-60": ZERO,
        "61-90": ZERO,
        "91-120": ZERO,
        "120+": ZERO,
    }
    invoices = ClientInvoice.objects.filter(company=company, balance_due__gt=0)
    if client is not None:
        invoices = invoices.filter(client=client)
    rows = invoices.exclude(status__in=[InvoiceStatus.VOIDED, InvoiceStatus.CANCELLED]).values(
        "due_date", "balance_due"
    )
    for row in rows:
        days = (as_of - row["due_date"]).days
        bucket = (
            "CURRENT"
            if days <= 0
            else "1-30"
            if days <= 30
            else "31-60"
            if days <= 60
            else "61-90"
            if days <= 90
            else "91-120"
            if days <= 120
            else "120+"
        )
        result[bucket] += row["balance_due"]
    return result


def client_statement(*, client: Any) -> QuerySet[ClientAccountTransaction]:
    return (
        ClientAccountTransaction.objects.filter(client=client)
        .select_related("invoice", "receipt", "created_by")
        .order_by("effective_at", "created_at")
    )
