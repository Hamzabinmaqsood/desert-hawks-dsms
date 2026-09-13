from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from dsms.audit.models import AuditEvent
from dsms.billing.enums import InvoiceStatus, InvoiceType, PaymentMethod, ReceiptStatus
from dsms.billing.models import (
    ClientAccountTransaction,
    ClientBillingProfile,
    ClientInvoice,
    ClientInvoiceDocument,
    ClientReceipt,
)
from dsms.billing.selectors import (
    client_statement,
    get_accounts_receivable_ageing,
    get_client_account_balance,
)
from dsms.billing.services import (
    allocate_receipt,
    approve_credit_note,
    approve_debit_note,
    approve_invoice,
    confirm_receipt,
    create_credit_note,
    create_debit_note,
    create_invoice,
    create_overdue_collection_reminders,
    issue_credit_note,
    issue_debit_note,
    issue_invoice,
    reverse_receipt,
    submit_invoice,
)
from dsms.contracts.models import Client, ClientIndustry
from dsms.finance.enums import AccountType
from dsms.finance.models import Account, AccountingPeriod, FiscalYear
from dsms.finance.operations_models import BankAccount
from dsms.notifications.models import NotificationEvent
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def billing_graph() -> dict[str, Any]:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create_batch(2)
    industry = ClientIndustry.objects.create(company=company, code="BANK", name="Banking")
    client = Client.objects.create(
        company=company, client_code="CLIENT-1", legal_name="Client One", industry=industry
    )
    receivable = Account.objects.create(
        company=company,
        code="1100",
        name="Receivable",
        account_type=AccountType.ASSET,
    )
    revenue = Account.objects.create(
        company=company,
        code="4100",
        name="Revenue",
        account_type=AccountType.REVENUE,
    )
    tax = Account.objects.create(
        company=company, code="2100", name="Sales Tax", account_type=AccountType.LIABILITY
    )
    bank_ledger = Account.objects.create(
        company=company, code="1110", name="Bank", account_type=AccountType.ASSET
    )
    bank = BankAccount.objects.create(
        company=company,
        name="Collection Bank",
        bank_name="Test Bank",
        account_number_encrypted="encrypted",
        currency="PKR",
        ledger_account=bank_ledger,
    )
    fiscal_year = FiscalYear.objects.create(
        company=company,
        name="FY2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    AccountingPeriod.objects.create(
        fiscal_year=fiscal_year,
        company=company,
        name="2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    profile = ClientBillingProfile.objects.create(
        company=company,
        client=client,
        billing_name="Client One",
        billing_address="Safe billing address",
        payment_terms_days=15,
        currency="PKR",
        default_receivable_account=receivable,
        default_tax_account=tax,
    )
    return {
        "company": company,
        "maker": maker,
        "checker": checker,
        "client": client,
        "profile": profile,
        "revenue": revenue,
        "bank": bank,
    }


def make_invoice(graph: dict[str, Any], amount: str = "100") -> ClientInvoice:
    return create_invoice(
        profile=graph["profile"],
        actor=graph["maker"],
        invoice_date=date(2026, 8, 1),
        invoice_type=InvoiceType.STANDARD,
        lines=[
            {
                "description": " Guarding service ",
                "quantity": Decimal("2"),
                "unit_price": Decimal(amount),
                "discount_amount": Decimal("10"),
                "tax_rate": Decimal("10"),
                "revenue_account": graph["revenue"],
            }
        ],
    )


def test_invoice_server_totals_snapshots_and_input_guards() -> None:
    graph = billing_graph()
    invoice = make_invoice(graph)
    line = invoice.lines.get()
    assert invoice.subtotal == Decimal("200.00")
    assert invoice.discount_total == Decimal("10.00")
    assert invoice.tax_total == Decimal("19.00")
    assert invoice.total_amount == Decimal("209.00")
    assert invoice.balance_due == Decimal("209.00")
    assert invoice.due_date == date(2026, 8, 16)
    assert invoice.billing_name_snapshot == "Client One"
    assert line.description == "Guarding service"
    assert line.line_total == Decimal("209.00")

    empty = create_invoice(
        profile=graph["profile"],
        actor=graph["maker"],
        invoice_date=date(2026, 8, 1),
        invoice_type=InvoiceType.STANDARD,
        lines=[],
    )
    assert empty.status == InvoiceStatus.DRAFT and not empty.lines.exists()
    graph["profile"].is_active = False
    graph["profile"].save(update_fields=["is_active"])
    with pytest.raises(ValidationError, match="Inactive"):
        make_invoice(graph)


@pytest.mark.parametrize(
    "line_override",
    [
        {"quantity": Decimal("0")},
        {"unit_price": Decimal("-1")},
        {"discount_amount": Decimal("-1")},
        {"tax_rate": Decimal("-1")},
        {"discount_amount": Decimal("201")},
    ],
)
def test_invoice_rejects_invalid_server_calculation_inputs(line_override: dict[str, Any]) -> None:
    graph = billing_graph()
    line = {
        "description": "Service",
        "quantity": Decimal("2"),
        "unit_price": Decimal("100"),
        "discount_amount": Decimal("0"),
        "tax_rate": Decimal("0"),
        "revenue_account": graph["revenue"],
    }
    line.update(line_override)
    with pytest.raises(ValidationError):
        create_invoice(
            profile=graph["profile"],
            actor=graph["maker"],
            invoice_date=date(2026, 8, 1),
            invoice_type=InvoiceType.STANDARD,
            lines=[line],
        )


def test_invoice_maker_checker_issue_ar_and_audit() -> None:
    graph = billing_graph()
    invoice = make_invoice(graph)
    submitted = submit_invoice(invoice=invoice)
    assert submitted.status == InvoiceStatus.UNDER_REVIEW
    with pytest.raises(ValidationError, match="self-approval"):
        approve_invoice(invoice=submitted, actor=graph["maker"])
    approved = approve_invoice(invoice=submitted, actor=graph["checker"])
    assert approved.status == InvoiceStatus.APPROVED
    issued = issue_invoice(invoice=approved, actor=graph["checker"])
    assert issued.status == InvoiceStatus.ISSUED
    ar = ClientAccountTransaction.objects.get(invoice=issued)
    assert ar.debit == Decimal("209.00")
    assert ar.credit == 0
    assert AuditEvent.objects.filter(action="INVOICE_APPROVED").exists()
    assert AuditEvent.objects.filter(action="INVOICE_ISSUED").exists()
    ar.debit = 1
    with pytest.raises(ValidationError, match="immutable"):
        ar.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        ar.delete()
    with pytest.raises(ValidationError, match="Only approved"):
        issue_invoice(invoice=issued, actor=graph["checker"])


def test_receipt_confirmation_allocation_bounds_and_statuses() -> None:
    graph = billing_graph()
    invoice = issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(graph)), actor=graph["checker"]
        ),
        actor=graph["checker"],
    )
    receipt = ClientReceipt.objects.create(
        receipt_number="REC-001",
        company=graph["company"],
        client=graph["client"],
        received_at=timezone.now(),
        currency="PKR",
        amount=Decimal("209"),
        payment_method=PaymentMethod.BANK_TRANSFER,
        received_by=graph["maker"],
        bank_account=graph["bank"],
        external_reference="SAFE-REF",
    )
    with pytest.raises(ValidationError, match="self-approval"):
        confirm_receipt(receipt=receipt, actor=graph["maker"])
    confirmed = confirm_receipt(receipt=receipt, actor=graph["checker"])
    assert confirmed.status == ReceiptStatus.CONFIRMED
    assert AuditEvent.objects.filter(action="RECEIPT_CONFIRMED").exists()
    with pytest.raises(ValidationError, match="invalid"):
        allocate_receipt(
            receipt=confirmed, invoice=invoice, amount=Decimal("0"), actor=graph["checker"]
        )
    first = allocate_receipt(
        receipt=confirmed, invoice=invoice, amount=Decimal("100"), actor=graph["checker"]
    )
    invoice.refresh_from_db()
    confirmed.refresh_from_db()
    assert first.amount == Decimal("100")
    assert invoice.status == InvoiceStatus.PARTIALLY_PAID
    assert confirmed.status == ReceiptStatus.PARTIALLY_ALLOCATED
    allocate_receipt(
        receipt=confirmed, invoice=invoice, amount=Decimal("109"), actor=graph["checker"]
    )
    invoice.refresh_from_db()
    confirmed.refresh_from_db()
    assert invoice.status == InvoiceStatus.PAID
    assert confirmed.status == ReceiptStatus.ALLOCATED
    assert AuditEvent.objects.filter(action="RECEIPT_ALLOCATED").count() == 2


def test_receipt_allocation_rejects_client_currency_and_available_balance_mismatch() -> None:
    graph = billing_graph()
    invoice = make_invoice(graph)
    invoice.status = InvoiceStatus.ISSUED
    invoice.save(update_fields=["status"])
    receipt = ClientReceipt.objects.create(
        receipt_number="REC-002",
        company=graph["company"],
        client=graph["client"],
        received_at=timezone.now(),
        currency="USD",
        amount=Decimal("50"),
        payment_method=PaymentMethod.CASH,
        received_by=graph["maker"],
        status=ReceiptStatus.CONFIRMED,
    )
    with pytest.raises(ValidationError, match="currencies"):
        allocate_receipt(
            receipt=receipt, invoice=invoice, amount=Decimal("10"), actor=graph["checker"]
        )

    receipt.currency = invoice.currency
    receipt.save(update_fields=["currency"])
    invoice.status = InvoiceStatus.DRAFT
    invoice.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="not available"):
        allocate_receipt(
            receipt=receipt, invoice=invoice, amount=Decimal("10"), actor=graph["checker"]
        )


def test_billing_balances_ageing_and_statement_are_derived_from_ledger() -> None:
    graph = billing_graph()
    invoice = make_invoice(graph)
    invoice.status = InvoiceStatus.ISSUED
    invoice.invoice_date = date(2026, 5, 15)
    invoice.due_date = date(2026, 6, 1)
    invoice.amount_paid = Decimal("25")
    invoice.balance_due = Decimal("184")
    invoice.save(update_fields=["status", "invoice_date", "due_date", "amount_paid", "balance_due"])
    receipt = ClientReceipt.objects.create(
        receipt_number="REC-AGE",
        company=graph["company"],
        client=graph["client"],
        received_at=timezone.now(),
        currency="PKR",
        amount=Decimal("40"),
        payment_method=PaymentMethod.CASH,
        received_by=graph["maker"],
        status=ReceiptStatus.CONFIRMED,
    )
    ClientAccountTransaction.objects.create(
        company=graph["company"],
        client=graph["client"],
        transaction_type="INVOICE",
        effective_at=timezone.now(),
        debit=invoice.total_amount,
        invoice=invoice,
        created_by=graph["maker"],
    )
    balance = get_client_account_balance(graph["client"])
    assert balance["invoiced"] == Decimal("209")
    assert balance["payments"] == Decimal("25")
    assert balance["unallocated_receipts"] == Decimal("40")
    ageing = get_accounts_receivable_ageing(company=graph["company"], as_of_date=date(2026, 8, 15))
    assert ageing["61-90"] == Decimal("184")
    assert list(client_statement(client=graph["client"]))[0].invoice == invoice
    assert receipt.status == ReceiptStatus.CONFIRMED
    receipt.currency = "PKR"
    receipt.save(update_fields=["currency"])
    with pytest.raises(ValidationError, match="unallocated"):
        allocate_receipt(
            receipt=receipt, invoice=invoice, amount=Decimal("60"), actor=graph["checker"]
        )

    other = billing_graph()
    other_invoice = make_invoice(other)
    with pytest.raises(ValidationError, match="different clients"):
        allocate_receipt(
            receipt=receipt,
            invoice=other_invoice,
            amount=Decimal("10"),
            actor=graph["checker"],
        )


def test_issued_invoice_pdf_credit_and_debit_notes_post_balanced_corrections() -> None:
    graph = billing_graph()
    invoice = issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(graph)), actor=graph["checker"]
        ),
        actor=graph["checker"],
    )
    document = ClientInvoiceDocument.objects.get(invoice=invoice)
    assert document.file.name.endswith("revision-1.pdf")
    assert document.file.read(8).startswith(b"%PDF-1.4")

    credit = create_credit_note(
        invoice=invoice,
        actor=graph["maker"],
        reason="Service correction",
        lines=[
            {
                "description": "Correction",
                "amount": Decimal("25"),
                "revenue_account": graph["revenue"],
            }
        ],
    )
    with pytest.raises(ValidationError, match="self-approval"):
        approve_credit_note(note=credit, actor=graph["maker"])
    credit = issue_credit_note(
        note=approve_credit_note(note=credit, actor=graph["checker"]),
        actor=graph["checker"],
    )
    assert credit.accounting_journal is not None
    assert credit.accounting_journal.total_debit == credit.accounting_journal.total_credit
    invoice.refresh_from_db()
    assert invoice.balance_due == Decimal("184.00")

    debit = create_debit_note(
        profile=graph["profile"],
        invoice=invoice,
        actor=graph["maker"],
        reason="Additional service",
        lines=[
            {
                "description": "Extra duty",
                "amount": Decimal("10"),
                "revenue_account": graph["revenue"],
            }
        ],
    )
    debit = issue_debit_note(
        note=approve_debit_note(note=debit, actor=graph["checker"]),
        actor=graph["checker"],
    )
    assert debit.accounting_journal is not None
    assert debit.accounting_journal.total_debit == debit.accounting_journal.total_credit
    invoice.refresh_from_db()
    assert invoice.balance_due == Decimal("194.00")


def test_receipt_reversal_restores_invoice_and_posts_reversal() -> None:
    graph = billing_graph()
    invoice = issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(graph)), actor=graph["checker"]
        ),
        actor=graph["checker"],
    )
    receipt = ClientReceipt.objects.create(
        receipt_number="REC-REV",
        company=graph["company"],
        client=graph["client"],
        received_at=timezone.now(),
        currency="PKR",
        amount=Decimal("100"),
        payment_method=PaymentMethod.BANK_TRANSFER,
        bank_account=graph["bank"],
        received_by=graph["maker"],
    )
    receipt = confirm_receipt(receipt=receipt, actor=graph["checker"])
    allocate_receipt(
        receipt=receipt, invoice=invoice, amount=Decimal("100"), actor=graph["checker"]
    )
    with pytest.raises(ValidationError, match="meaningful"):
        reverse_receipt(receipt=receipt, actor=graph["checker"], reason="bad")
    reversal = reverse_receipt(
        receipt=receipt, actor=graph["checker"], reason="Bank transfer recalled"
    )
    invoice.refresh_from_db()
    receipt.refresh_from_db()
    assert invoice.balance_due == invoice.total_amount
    assert receipt.status == ReceiptStatus.REVERSED
    assert reversal.accounting_journal is not None
    assert reversal.accounting_journal.total_debit == reversal.accounting_journal.total_credit


def test_overdue_collection_reminder_is_daily_idempotent_and_privacy_safe() -> None:
    graph = billing_graph()
    invoice = make_invoice(graph)
    invoice.status = InvoiceStatus.ISSUED
    invoice.due_date = date(2026, 8, 1)
    invoice.save(update_fields=["status", "due_date"])
    reminder_date = date(2026, 8, 21)
    reminder_at = timezone.make_aware(datetime(2026, 8, 21, 12))
    with patch("dsms.billing.services.timezone.now", return_value=reminder_at):
        assert create_overdue_collection_reminders(as_of=reminder_date, actor=graph["maker"]) == 1
        assert create_overdue_collection_reminders(as_of=reminder_date, actor=graph["maker"]) == 0
    event = NotificationEvent.objects.get(
        company=invoice.company, event_type="CLIENT_INVOICE_OVERDUE"
    )
    assert "billing_address" not in event.safe_payload
    assert event.safe_payload["invoice_number"] == invoice.invoice_number
