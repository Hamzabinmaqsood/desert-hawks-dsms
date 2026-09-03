import hashlib
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.finance.enums import AccountType
from dsms.finance.models import AccountingPeriod
from dsms.finance.services import (
    approve_journal,
    create_journal,
    money,
    next_document_number,
    post_journal,
    submit_journal,
)

from .enums import (
    AdjustmentStatus,
    ARTransactionType,
    CollectionActivityType,
    InvoiceStatus,
    ReceiptStatus,
)
from .models import (
    ClientAccountTransaction,
    ClientBillingProfile,
    ClientCollectionActivity,
    ClientCreditNote,
    ClientCreditNoteLine,
    ClientDebitNote,
    ClientDebitNoteLine,
    ClientInvoice,
    ClientInvoiceDocument,
    ClientInvoiceLine,
    ClientReceipt,
    ClientReceiptAllocation,
    ClientReceiptReversal,
)

ZERO = Decimal("0.00")


def _maker_checker(maker_id: Any, actor: Any) -> None:
    if maker_id == actor.id and not actor.is_superuser:
        raise ValidationError("Maker/checker policy prevents self-approval.")


def _post_journal(
    *,
    company: Any,
    entry_date: date,
    description: str,
    maker: Any,
    actor: Any,
    source_type: str,
    source_id: Any,
    lines: list[dict[str, Any]],
) -> Any:
    period = (
        AccountingPeriod.objects.select_related("fiscal_year")
        .filter(
            company=company, start_date__lte=entry_date, end_date__gte=entry_date, status="OPEN"
        )
        .first()
    )
    if not period:
        raise ValidationError("No open accounting period covers this billing transaction.")
    journal = create_journal(
        company=company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=entry_date,
        description=description,
        created_by=maker,
        source_type=source_type,
        source_id=source_id,
        lines=lines,
    )
    journal = submit_journal(journal=journal, actor=maker)
    journal = approve_journal(journal=journal, actor=actor)
    return post_journal(journal=journal, actor=actor)


def _pdf_bytes(invoice: ClientInvoice) -> bytes:
    """Create a deterministic private PDF snapshot without external network/rendering."""
    lines = [
        "DESERT HAWKS SECURITY SERVICES",
        f"INVOICE {invoice.invoice_number}",
        f"Invoice date: {invoice.invoice_date}    Due date: {invoice.due_date}",
        f"Bill to: {invoice.billing_name_snapshot}",
        invoice.billing_address_snapshot.replace("\n", " "),
        f"Currency: {invoice.currency}",
    ]
    for line in invoice.lines.order_by("line_number"):
        lines.append(
            f"{line.line_number}. {line.description} | "
            f"{line.quantity} {line.unit} x {line.unit_price} | {line.line_total}"
        )
    lines.extend(
        [
            f"Subtotal: {invoice.subtotal}",
            f"Discount: {invoice.discount_total}",
            f"Tax: {invoice.tax_total}",
            f"Total: {invoice.total_amount}",
            f"Paid: {invoice.amount_paid}",
            f"Balance: {invoice.balance_due}",
            invoice.payment_instructions_snapshot,
            "Page 1 of 1",
        ]
    )
    escaped = [
        text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:115] for text in lines
    ]
    stream = (
        "BT /F1 9 Tf 45 800 Td " + " ".join(f"({text}) Tj 0 -16 Td" for text in escaped) + " ET"
    )
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >> endobj",
        f"4 0 obj << /Length {len(stream.encode())} >> stream\n{stream}\nendstream endobj",
        "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
    ]
    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(output.tell())
        output.write((obj + "\n").encode())
    xref = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode())
    output.write(
        f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return output.getvalue()


def _generate_invoice_document(invoice: ClientInvoice, actor: Any) -> ClientInvoiceDocument:
    payload = _pdf_bytes(invoice)
    document = ClientInvoiceDocument(
        company=invoice.company,
        invoice=invoice,
        revision_number=(invoice.documents.aggregate(max=models.Max("revision_number"))["max"] or 0)
        + 1,
        sha256=hashlib.sha256(payload).hexdigest(),
        generated_by=actor,
        generated_at=timezone.now(),
    )
    document.file.save(f"invoice-{invoice.invoice_number}.pdf", ContentFile(payload), save=False)
    document.save()
    return document


@transaction.atomic
def create_invoice(
    *,
    profile: ClientBillingProfile,
    actor: Any,
    invoice_date: date,
    invoice_type: str,
    lines: list[dict[str, Any]],
    contract: Any = None,
    service_period_start: date | None = None,
    service_period_end: date | None = None,
    client_po_reference: str = "",
    client_reference: str = "",
) -> ClientInvoice:
    if not profile.is_active:
        raise ValidationError("Inactive billing profiles cannot create invoices.")
    profile.full_clean()
    if contract and (
        contract.company_id != profile.company_id or contract.client_id != profile.client_id
    ):
        raise ValidationError({"contract": "Contract belongs to another company or client."})
    if service_period_start and service_period_end and service_period_end < service_period_start:
        raise ValidationError({"service_period_end": "Service period end precedes its start."})
    number = next_document_number(company=profile.company, prefix="INV", year=invoice_date.year)
    invoice = ClientInvoice.objects.create(
        invoice_number=number,
        company=profile.company,
        client=profile.client,
        contract=contract,
        invoice_type=invoice_type,
        currency=profile.currency,
        invoice_date=invoice_date,
        service_period_start=service_period_start,
        service_period_end=service_period_end,
        client_po_reference=client_po_reference.strip(),
        client_reference=client_reference.strip(),
        due_date=invoice_date + timedelta(days=profile.payment_terms_days),
        generated_by=actor,
        billing_name_snapshot=profile.billing_name,
        billing_address_snapshot=profile.billing_address,
        tax_registration_snapshot=profile.tax_registration_number,
        payment_terms_snapshot=profile.payment_terms_days,
        payment_instructions_snapshot=profile.default_payment_instructions,
        notes_snapshot=profile.invoice_notes,
    )
    subtotal = tax_total = discount_total = ZERO
    line_objects = []
    for index, payload in enumerate(lines, start=1):
        _validate_invoice_line_relationships(invoice, payload)
        quantity = Decimal(payload["quantity"])
        unit_price = money(payload["unit_price"])
        discount = money(payload.get("discount_amount", ZERO))
        rate = Decimal(payload.get("tax_rate", ZERO))
        if quantity <= 0 or unit_price < 0 or discount < 0 or rate < 0:
            raise ValidationError("Invoice quantities and monetary inputs must be non-negative.")
        gross = money(quantity * unit_price)
        if discount > gross:
            raise ValidationError("Line discount cannot exceed gross amount.")
        taxable = money(gross - discount)
        tax = money(taxable * rate / Decimal("100"))
        total = money(taxable + tax)
        line_objects.append(
            ClientInvoiceLine(
                invoice=invoice,
                line_number=index,
                description=payload["description"].strip(),
                quantity=quantity,
                unit=payload.get("unit", "SERVICE"),
                unit_price=unit_price,
                gross_amount=gross,
                discount_amount=discount,
                taxable_amount=taxable,
                tax_amount=tax,
                line_total=total,
                revenue_account=payload["revenue_account"],
                cost_center=payload.get("cost_center"),
                contract_service=payload.get("contract_service"),
                site=payload.get("site"),
                billing_rule=payload.get("billing_rule"),
            )
        )
        subtotal += gross
        discount_total += discount
        tax_total += tax
    ClientInvoiceLine.objects.bulk_create(line_objects)
    invoice.subtotal = money(subtotal)
    invoice.discount_total = money(discount_total)
    invoice.tax_total = money(tax_total)
    invoice.total_amount = money(subtotal - discount_total + tax_total)
    invoice.balance_due = invoice.total_amount
    invoice.save(
        update_fields=[
            "subtotal",
            "discount_total",
            "tax_total",
            "total_amount",
            "balance_due",
            "updated_at",
        ]
    )
    record_audit_event(
        action="INVOICE_DRAFT_CREATED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.INFO,
        summary="Client invoice draft created.",
        actor_user=actor,
        company=invoice.company,
        source_object=invoice,
        object_reference=invoice.invoice_number,
    )
    return invoice


def _validate_invoice_line_relationships(invoice: ClientInvoice, payload: dict[str, Any]) -> None:
    account = payload["revenue_account"]
    if account.company_id != invoice.company_id:
        raise ValidationError({"revenue_account": "Account belongs to another company."})
    if account.account_type != AccountType.REVENUE:
        raise ValidationError(
            {"revenue_account": "Revenue account must be an active revenue account."}
        )
    if not account.is_active:
        raise ValidationError(
            {"revenue_account": "Revenue account must be an active revenue account."}
        )
    if not account.allow_posting:
        raise ValidationError({"revenue_account": "Revenue account does not allow posting."})
    cost_center = payload.get("cost_center")
    if cost_center and cost_center.company_id != invoice.company_id:
        raise ValidationError({"cost_center": "Cost centre belongs to another company."})
    service = payload.get("contract_service")
    if service and (
        not invoice.contract_id
        or service.contract_id != invoice.contract_id
        or service.contract.company_id != invoice.company_id
    ):
        raise ValidationError({"contract_service": "Service is not part of the invoice contract."})
    site = payload.get("site")
    if site and (
        site.company_id != invoice.company_id
        or site.client_id != invoice.client_id
        or (invoice.contract_id and site.contract_id != invoice.contract_id)
    ):
        raise ValidationError({"site": "Site is not valid for this invoice."})
    rule = payload.get("billing_rule")
    if rule and (
        rule.billing_schedule.company_id != invoice.company_id
        or rule.billing_schedule.client_id != invoice.client_id
        or (invoice.contract_id and rule.billing_schedule.contract_id != invoice.contract_id)
    ):
        raise ValidationError({"billing_rule": "Billing rule is not valid for this invoice."})


def _line_values(invoice: ClientInvoice, payload: dict[str, Any]) -> dict[str, Any]:
    _validate_invoice_line_relationships(invoice, payload)
    quantity = Decimal(payload["quantity"])
    unit_price = money(payload["unit_price"])
    discount = money(payload.get("discount_amount", ZERO))
    rate = Decimal(payload.get("tax_rate", ZERO))
    if quantity <= 0 or unit_price < 0 or discount < 0 or rate < 0:
        raise ValidationError("Invoice quantities and monetary inputs must be non-negative.")
    gross = money(quantity * unit_price)
    if discount > gross:
        raise ValidationError("Line discount cannot exceed gross amount.")
    taxable = money(gross - discount)
    tax = money(taxable * rate / Decimal("100"))
    return {
        **{key: value for key, value in payload.items() if key != "tax_rate"},
        "description": str(payload["description"]).strip(),
        "quantity": quantity,
        "unit_price": unit_price,
        "gross_amount": gross,
        "discount_amount": discount,
        "taxable_amount": taxable,
        "tax_amount": tax,
        "line_total": money(taxable + tax),
    }


def _recalculate_invoice(invoice: ClientInvoice) -> None:
    totals = invoice.lines.aggregate(
        subtotal=Sum("gross_amount"), discount=Sum("discount_amount"), tax=Sum("tax_amount")
    )
    invoice.subtotal = money(totals["subtotal"] or ZERO)
    invoice.discount_total = money(totals["discount"] or ZERO)
    invoice.tax_total = money(totals["tax"] or ZERO)
    invoice.total_amount = money(invoice.subtotal - invoice.discount_total + invoice.tax_total)
    invoice.balance_due = invoice.total_amount
    invoice.save(
        update_fields=[
            "subtotal",
            "discount_total",
            "tax_total",
            "total_amount",
            "balance_due",
            "updated_at",
        ]
    )


@transaction.atomic
def update_invoice_draft(
    *, invoice: ClientInvoice, actor: Any, values: dict[str, Any]
) -> ClientInvoice:
    item = ClientInvoice.objects.select_for_update().get(pk=invoice.pk)
    if item.status != InvoiceStatus.DRAFT:
        raise ValidationError("Only draft invoices can be edited.")
    contract = values.get("contract", item.contract)
    if contract and (
        contract.company_id != item.company_id or contract.client_id != item.client_id
    ):
        raise ValidationError({"contract": "Contract belongs to another company or client."})
    period_start = values.get("service_period_start", item.service_period_start)
    period_end = values.get("service_period_end", item.service_period_end)
    if period_start and period_end and period_end < period_start:
        raise ValidationError({"service_period_end": "Service period end precedes its start."})
    if "invoice_date" in values:
        item.due_date = values["invoice_date"] + timedelta(days=item.payment_terms_snapshot)
    for field, value in values.items():
        setattr(item, field, value)
    update_fields = [*values.keys(), "updated_at"]
    if "invoice_date" in values:
        update_fields.append("due_date")
    item.save(update_fields=update_fields)
    return item


@transaction.atomic
def add_invoice_line(
    *, invoice: ClientInvoice, actor: Any, values: dict[str, Any]
) -> ClientInvoiceLine:
    item = ClientInvoice.objects.select_for_update().get(pk=invoice.pk)
    if item.status != InvoiceStatus.DRAFT:
        raise ValidationError("Only draft invoice lines can be edited.")
    payload = _line_values(item, values)
    line = ClientInvoiceLine.objects.create(
        invoice=item,
        line_number=(item.lines.aggregate(max=models.Max("line_number"))["max"] or 0) + 1,
        **payload,
    )
    _recalculate_invoice(item)
    return line


@transaction.atomic
def update_invoice_line(
    *, invoice: ClientInvoice, line: ClientInvoiceLine, actor: Any, values: dict[str, Any]
) -> ClientInvoiceLine:
    item = ClientInvoice.objects.select_for_update().get(pk=invoice.pk)
    if item.status != InvoiceStatus.DRAFT:
        raise ValidationError("Only draft invoice lines can be edited.")
    target = ClientInvoiceLine.objects.select_for_update().get(pk=line.pk, invoice=item)
    current = {
        field: getattr(target, field)
        for field in (
            "description",
            "quantity",
            "unit",
            "unit_price",
            "discount_amount",
            "revenue_account",
            "cost_center",
            "contract_service",
            "site",
            "billing_rule",
        )
    }
    current["tax_rate"] = (
        ZERO
        if target.taxable_amount == ZERO
        else money(target.tax_amount * Decimal("100") / target.taxable_amount)
    )
    current.update(values)
    payload = _line_values(item, current)
    for field, value in payload.items():
        if field != "tax_rate":
            setattr(target, field, value)
    target.save()
    _recalculate_invoice(item)
    return target


@transaction.atomic
def delete_invoice_line(*, invoice: ClientInvoice, line: ClientInvoiceLine, actor: Any) -> None:
    item = ClientInvoice.objects.select_for_update().get(pk=invoice.pk)
    if item.status != InvoiceStatus.DRAFT:
        raise ValidationError("Only draft invoice lines can be edited.")
    target = ClientInvoiceLine.objects.get(pk=line.pk, invoice=item)
    target.delete()
    _recalculate_invoice(item)


@transaction.atomic
def submit_invoice(*, invoice: ClientInvoice) -> ClientInvoice:
    locked = ClientInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != InvoiceStatus.DRAFT or not locked.lines.exists():
        raise ValidationError("Only a non-empty draft invoice can be submitted.")
    locked.status = InvoiceStatus.UNDER_REVIEW
    locked.save(update_fields=["status", "updated_at"])
    return locked


@transaction.atomic
def approve_invoice(*, invoice: ClientInvoice, actor: Any) -> ClientInvoice:
    locked = ClientInvoice.objects.select_for_update().get(pk=invoice.pk)
    if locked.status != InvoiceStatus.UNDER_REVIEW:
        raise ValidationError("Invoice is not under review.")
    _maker_checker(locked.generated_by_id, actor)
    locked.status = InvoiceStatus.APPROVED
    locked.approved_by = actor
    locked.approved_at = timezone.now()
    locked.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    record_audit_event(
        action="INVOICE_APPROVED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.HIGH,
        summary="Client invoice approved.",
        actor_user=actor,
        company=locked.company,
        source_object=locked,
        object_reference=locked.invoice_number,
    )
    return locked


@transaction.atomic
def issue_invoice(*, invoice: ClientInvoice, actor: Any) -> ClientInvoice:
    locked = (
        ClientInvoice.objects.select_for_update(of=("self",))
        .select_related("client")
        .get(pk=invoice.pk)
    )
    if locked.status != InvoiceStatus.APPROVED:
        raise ValidationError("Only approved invoices can be issued.")
    if locked.accounting_journal_id:
        return locked
    profile = ClientBillingProfile.objects.select_related(
        "default_receivable_account", "default_tax_account"
    ).get(client=locked.client)
    lines: list[dict[str, Any]] = [
        {"account": profile.default_receivable_account, "debit": locked.total_amount}
    ]
    revenue: dict[Any, Decimal] = {}
    for invoice_line in locked.lines.select_related("revenue_account"):
        revenue[invoice_line.revenue_account] = (
            revenue.get(invoice_line.revenue_account, ZERO) + invoice_line.taxable_amount
        )
    lines.extend(
        {"account": account, "credit": money(amount)} for account, amount in revenue.items()
    )
    if locked.tax_total:
        if not profile.default_tax_account:
            raise ValidationError(
                "A tax liability account is required before issuing this invoice."
            )
        lines.append({"account": profile.default_tax_account, "credit": locked.tax_total})
    journal = _post_journal(
        company=locked.company,
        entry_date=locked.invoice_date,
        description=f"Client invoice {locked.invoice_number}",
        maker=locked.generated_by,
        actor=actor,
        source_type="CLIENT_INVOICE",
        source_id=locked.id,
        lines=lines,
    )
    locked.status = InvoiceStatus.ISSUED
    locked.issued_by = actor
    locked.issued_at = timezone.now()
    locked.accounting_journal = journal
    locked.posted_at = timezone.now()
    locked.save(
        update_fields=[
            "status",
            "issued_by",
            "issued_at",
            "accounting_journal",
            "posted_at",
            "updated_at",
        ]
    )
    ClientAccountTransaction.objects.create(
        company=locked.company,
        client=locked.client,
        transaction_type=ARTransactionType.INVOICE,
        effective_at=timezone.now(),
        debit=locked.total_amount,
        invoice=locked,
        source_reference=locked.invoice_number,
        created_by=actor,
    )
    _generate_invoice_document(locked, actor)
    record_audit_event(
        action="INVOICE_ISSUED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.HIGH,
        summary="Client invoice issued.",
        actor_user=actor,
        company=locked.company,
        source_object=locked,
        object_reference=locked.invoice_number,
    )
    return locked


@transaction.atomic
def confirm_receipt(*, receipt: ClientReceipt, actor: Any) -> ClientReceipt:
    locked = (
        ClientReceipt.objects.select_for_update(of=("self",))
        .select_related("bank_account__ledger_account")
        .get(pk=receipt.pk)
    )
    if locked.status != ReceiptStatus.DRAFT:
        raise ValidationError("Only draft receipts can be confirmed.")
    _maker_checker(locked.received_by_id, actor)
    if not locked.bank_account_id:
        raise ValidationError("A configured bank account is required to confirm the receipt.")
    bank_account = locked.bank_account
    assert bank_account is not None
    profile = ClientBillingProfile.objects.select_related("default_receivable_account").get(
        client=locked.client
    )
    journal = _post_journal(
        company=locked.company,
        entry_date=locked.value_date or locked.received_at.date(),
        description=f"Client receipt {locked.receipt_number}",
        maker=locked.received_by,
        actor=actor,
        source_type="CLIENT_RECEIPT",
        source_id=locked.id,
        lines=[
            {"account": bank_account.ledger_account, "debit": locked.amount},
            {"account": profile.default_receivable_account, "credit": locked.amount},
        ],
    )
    locked.status = ReceiptStatus.CONFIRMED
    locked.confirmed_by = actor
    locked.confirmed_at = timezone.now()
    locked.accounting_journal = journal
    locked.save(
        update_fields=["status", "confirmed_by", "confirmed_at", "accounting_journal", "updated_at"]
    )
    ClientAccountTransaction.objects.create(
        company=locked.company,
        client=locked.client,
        transaction_type=ARTransactionType.RECEIPT,
        effective_at=timezone.now(),
        credit=locked.amount,
        receipt=locked,
        source_reference=locked.receipt_number,
        created_by=actor,
    )
    record_audit_event(
        action="RECEIPT_CONFIRMED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.HIGH,
        summary="Client receipt confirmed.",
        actor_user=actor,
        company=locked.company,
        source_object=locked,
        object_reference=locked.receipt_number,
    )
    return locked


@transaction.atomic
def allocate_receipt(
    *, receipt: ClientReceipt, invoice: ClientInvoice, amount: Decimal, actor: Any
) -> ClientReceiptAllocation:
    locked_receipt = ClientReceipt.objects.select_for_update().get(pk=receipt.pk)
    locked_invoice = ClientInvoice.objects.select_for_update().get(pk=invoice.pk)
    amount = money(amount)
    if locked_receipt.status not in {
        ReceiptStatus.CONFIRMED,
        ReceiptStatus.PARTIALLY_ALLOCATED,
    }:
        raise ValidationError("Receipt is not available for allocation.")
    if locked_receipt.client_id != locked_invoice.client_id:
        raise ValidationError("Receipt and invoice belong to different clients.")
    if locked_receipt.currency != locked_invoice.currency:
        raise ValidationError("Receipt and invoice currencies differ.")
    if amount <= 0 or amount > locked_invoice.balance_due:
        raise ValidationError("Allocation exceeds the invoice balance or is invalid.")
    allocated = locked_receipt.allocations.aggregate(total=Sum("amount"))["total"] or ZERO
    if amount > locked_receipt.amount - allocated:
        raise ValidationError("Allocation exceeds the receipt's unallocated balance.")
    allocation = ClientReceiptAllocation.objects.create(
        receipt=locked_receipt,
        invoice=locked_invoice,
        amount=amount,
        allocated_by=actor,
        allocated_at=timezone.now(),
    )
    locked_invoice.amount_paid = money(locked_invoice.amount_paid + amount)
    locked_invoice.balance_due = money(locked_invoice.total_amount - locked_invoice.amount_paid)
    locked_invoice.status = (
        InvoiceStatus.PAID if locked_invoice.balance_due == ZERO else InvoiceStatus.PARTIALLY_PAID
    )
    locked_invoice.save(update_fields=["amount_paid", "balance_due", "status", "updated_at"])
    remaining = locked_receipt.amount - allocated - amount
    locked_receipt.status = (
        ReceiptStatus.ALLOCATED if remaining == ZERO else ReceiptStatus.PARTIALLY_ALLOCATED
    )
    locked_receipt.save(update_fields=["status", "updated_at"])
    ClientAccountTransaction.objects.create(
        company=locked_invoice.company,
        client=locked_invoice.client,
        transaction_type=ARTransactionType.RECEIPT_ALLOCATION,
        effective_at=timezone.now(),
        debit=amount,
        credit=amount,
        invoice=locked_invoice,
        receipt=locked_receipt,
        allocation=allocation,
        created_by=actor,
    )
    record_audit_event(
        action="RECEIPT_ALLOCATED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.HIGH,
        summary="Client receipt allocated to invoice.",
        actor_user=actor,
        company=locked_invoice.company,
        source_object=allocation,
        metadata_safe={"invoice_id": str(locked_invoice.id), "receipt_id": str(locked_receipt.id)},
    )
    return allocation


@transaction.atomic
def create_credit_note(
    *, invoice: ClientInvoice, actor: Any, reason: str, lines: list[dict[str, Any]]
) -> ClientCreditNote:
    source = ClientInvoice.objects.select_for_update(of=("self",)).get(pk=invoice.pk)
    if source.status not in {
        InvoiceStatus.ISSUED,
        InvoiceStatus.PARTIALLY_PAID,
        InvoiceStatus.PAID,
        InvoiceStatus.DISPUTED,
    }:
        raise ValidationError("Credit notes require a valid issued invoice.")
    note = ClientCreditNote.objects.create(
        company=source.company,
        client=source.client,
        invoice=source,
        note_number=next_document_number(
            company=source.company, prefix="CN", year=timezone.localdate().year
        ),
        note_date=timezone.localdate(),
        currency=source.currency,
        reason=reason.strip(),
        created_by=actor,
    )
    total = ZERO
    for index, payload in enumerate(lines, 1):
        amount, tax = money(payload["amount"]), money(payload.get("tax_amount", ZERO))
        if amount <= 0 or tax < 0:
            raise ValidationError("Credit note amounts must be positive.")
        ClientCreditNoteLine.objects.create(
            credit_note=note,
            line_number=index,
            description=payload["description"].strip(),
            amount=amount,
            tax_amount=tax,
            revenue_account=payload["revenue_account"],
            tax_account=payload.get("tax_account"),
        )
        total += amount + tax
    if total <= 0 or total > source.balance_due:
        raise ValidationError("Credit note exceeds the invoice balance.")
    note.total_amount = money(total)
    note.save(update_fields=["total_amount", "updated_at"])
    return note


@transaction.atomic
def approve_credit_note(*, note: ClientCreditNote, actor: Any) -> ClientCreditNote:
    item = ClientCreditNote.objects.select_for_update(of=("self",)).get(pk=note.pk)
    if item.status not in {AdjustmentStatus.DRAFT, AdjustmentStatus.UNDER_REVIEW}:
        raise ValidationError("Credit note cannot be approved from its current state.")
    _maker_checker(item.created_by_id, actor)
    item.status, item.approved_by = AdjustmentStatus.APPROVED, actor
    item.save(update_fields=["status", "approved_by", "updated_at"])
    return item


@transaction.atomic
def issue_credit_note(*, note: ClientCreditNote, actor: Any) -> ClientCreditNote:
    item = (
        ClientCreditNote.objects.select_for_update(of=("self",))
        .select_related("invoice")
        .get(pk=note.pk)
    )
    if item.status != AdjustmentStatus.APPROVED:
        raise ValidationError("Only approved credit notes can be issued.")
    _maker_checker(item.created_by_id, actor)
    profile = ClientBillingProfile.objects.get(client=item.client)
    journal_lines: list[dict[str, Any]] = []
    for line in item.lines.select_related("revenue_account", "tax_account"):
        journal_lines.append({"account": line.revenue_account, "debit": line.amount})
        if line.tax_amount:
            journal_lines.append(
                {
                    "account": line.tax_account or profile.default_tax_account,
                    "debit": line.tax_amount,
                }
            )
    journal_lines.append(
        {"account": profile.default_receivable_account, "credit": item.total_amount}
    )
    journal = _post_journal(
        company=item.company,
        entry_date=item.note_date,
        description=f"Credit note {item.note_number}",
        maker=item.created_by,
        actor=actor,
        source_type="CLIENT_CREDIT_NOTE",
        source_id=item.id,
        lines=journal_lines,
    )
    item.status, item.issued_by, item.accounting_journal = AdjustmentStatus.ISSUED, actor, journal
    item.save(update_fields=["status", "issued_by", "accounting_journal", "updated_at"])
    invoice = ClientInvoice.objects.select_for_update(of=("self",)).get(pk=item.invoice_id)
    invoice.balance_due = money(invoice.balance_due - item.total_amount)
    invoice.status = (
        InvoiceStatus.PAID if invoice.balance_due == ZERO else InvoiceStatus.PARTIALLY_PAID
    )
    invoice.save(update_fields=["balance_due", "status", "updated_at"])
    ClientAccountTransaction.objects.create(
        company=item.company,
        client=item.client,
        transaction_type=ARTransactionType.CREDIT_NOTE,
        effective_at=timezone.now(),
        credit=item.total_amount,
        invoice=invoice,
        source_reference=item.note_number,
        created_by=actor,
    )
    record_audit_event(
        action="CLIENT_CREDIT_NOTE_ISSUED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.HIGH,
        summary="Client credit note issued.",
        actor_user=actor,
        company=item.company,
        source_object=item,
        object_reference=item.note_number,
    )
    return item


@transaction.atomic
def create_debit_note(
    *,
    profile: ClientBillingProfile,
    actor: Any,
    reason: str,
    lines: list[dict[str, Any]],
    invoice: ClientInvoice | None = None,
) -> ClientDebitNote:
    note = ClientDebitNote.objects.create(
        company=profile.company,
        client=profile.client,
        invoice=invoice,
        note_number=next_document_number(
            company=profile.company, prefix="DN", year=timezone.localdate().year
        ),
        note_date=timezone.localdate(),
        currency=profile.currency,
        reason=reason.strip(),
        created_by=actor,
    )
    total = ZERO
    for index, payload in enumerate(lines, 1):
        amount, tax = money(payload["amount"]), money(payload.get("tax_amount", ZERO))
        if amount <= 0 or tax < 0:
            raise ValidationError("Debit note amounts must be positive.")
        ClientDebitNoteLine.objects.create(
            debit_note=note,
            line_number=index,
            description=payload["description"].strip(),
            amount=amount,
            tax_amount=tax,
            revenue_account=payload["revenue_account"],
            tax_account=payload.get("tax_account"),
        )
        total += amount + tax
    note.total_amount = money(total)
    note.save(update_fields=["total_amount", "updated_at"])
    return note


@transaction.atomic
def approve_debit_note(*, note: ClientDebitNote, actor: Any) -> ClientDebitNote:
    item = ClientDebitNote.objects.select_for_update(of=("self",)).get(pk=note.pk)
    if item.status not in {AdjustmentStatus.DRAFT, AdjustmentStatus.UNDER_REVIEW}:
        raise ValidationError("Debit note cannot be approved.")
    _maker_checker(item.created_by_id, actor)
    item.status, item.approved_by = AdjustmentStatus.APPROVED, actor
    item.save(update_fields=["status", "approved_by", "updated_at"])
    return item


@transaction.atomic
def issue_debit_note(*, note: ClientDebitNote, actor: Any) -> ClientDebitNote:
    item = ClientDebitNote.objects.select_for_update(of=("self",)).get(pk=note.pk)
    if item.status != AdjustmentStatus.APPROVED:
        raise ValidationError("Only approved debit notes can be issued.")
    profile = ClientBillingProfile.objects.get(client=item.client)
    journal_lines: list[dict[str, Any]] = [
        {"account": profile.default_receivable_account, "debit": item.total_amount}
    ]
    for line in item.lines.select_related("revenue_account", "tax_account"):
        journal_lines.append({"account": line.revenue_account, "credit": line.amount})
        if line.tax_amount:
            journal_lines.append(
                {
                    "account": line.tax_account or profile.default_tax_account,
                    "credit": line.tax_amount,
                }
            )
    journal = _post_journal(
        company=item.company,
        entry_date=item.note_date,
        description=f"Debit note {item.note_number}",
        maker=item.created_by,
        actor=actor,
        source_type="CLIENT_DEBIT_NOTE",
        source_id=item.id,
        lines=journal_lines,
    )
    item.status, item.issued_by, item.accounting_journal = AdjustmentStatus.ISSUED, actor, journal
    item.save(update_fields=["status", "issued_by", "accounting_journal", "updated_at"])
    if item.invoice_id:
        invoice = ClientInvoice.objects.select_for_update(of=("self",)).get(pk=item.invoice_id)
        invoice.balance_due = money(invoice.balance_due + item.total_amount)
        invoice.status = (
            InvoiceStatus.ISSUED if invoice.amount_paid == ZERO else InvoiceStatus.PARTIALLY_PAID
        )
        invoice.save(update_fields=["balance_due", "status", "updated_at"])
    ClientAccountTransaction.objects.create(
        company=item.company,
        client=item.client,
        transaction_type=ARTransactionType.DEBIT_NOTE,
        effective_at=timezone.now(),
        debit=item.total_amount,
        invoice=item.invoice,
        source_reference=item.note_number,
        created_by=actor,
    )
    record_audit_event(
        action="CLIENT_DEBIT_NOTE_ISSUED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.HIGH,
        summary="Client debit note issued.",
        actor_user=actor,
        company=item.company,
        source_object=item,
        object_reference=item.note_number,
    )
    return item


@transaction.atomic
def reverse_receipt(*, receipt: ClientReceipt, actor: Any, reason: str) -> ClientReceiptReversal:
    item = (
        ClientReceipt.objects.select_for_update(of=("self",))
        .select_related("accounting_journal", "bank_account__ledger_account")
        .get(pk=receipt.pk)
    )
    if item.status not in {
        ReceiptStatus.CONFIRMED,
        ReceiptStatus.PARTIALLY_ALLOCATED,
        ReceiptStatus.ALLOCATED,
    } or hasattr(item, "reversal"):
        raise ValidationError("Receipt cannot be reversed.")
    _maker_checker(item.received_by_id, actor)
    if len(reason.strip()) < 6:
        raise ValidationError("A meaningful reversal reason is required.")
    bank_account = item.bank_account
    assert bank_account is not None
    for allocation in item.allocations.select_related("invoice"):
        invoice = ClientInvoice.objects.select_for_update(of=("self",)).get(
            pk=allocation.invoice_id
        )
        invoice.amount_paid = money(invoice.amount_paid - allocation.amount)
        invoice.balance_due = money(invoice.total_amount - invoice.amount_paid)
        invoice.status = (
            InvoiceStatus.ISSUED if invoice.amount_paid == ZERO else InvoiceStatus.PARTIALLY_PAID
        )
        invoice.save(update_fields=["amount_paid", "balance_due", "status", "updated_at"])
    profile = ClientBillingProfile.objects.get(client=item.client)
    journal = _post_journal(
        company=item.company,
        entry_date=timezone.localdate(),
        description=f"Receipt reversal {item.receipt_number}",
        maker=item.received_by,
        actor=actor,
        source_type="CLIENT_RECEIPT_REVERSAL",
        source_id=item.id,
        lines=[
            {"account": profile.default_receivable_account, "debit": item.amount},
            {"account": bank_account.ledger_account, "credit": item.amount},
        ],
    )
    reversal = ClientReceiptReversal.objects.create(
        receipt=item, reason=reason.strip(), reversed_by=actor, accounting_journal=journal
    )
    item.status = ReceiptStatus.REVERSED
    item.save(update_fields=["status", "updated_at"])
    ClientAccountTransaction.objects.create(
        company=item.company,
        client=item.client,
        transaction_type=ARTransactionType.REVERSAL,
        effective_at=timezone.now(),
        debit=item.amount,
        receipt=item,
        source_reference=item.receipt_number,
        created_by=actor,
    )
    record_audit_event(
        action="CLIENT_RECEIPT_REVERSED",
        category=AuditCategory.BILLING,
        severity=AuditSeverity.HIGH,
        summary="Client receipt reversed.",
        actor_user=actor,
        company=item.company,
        source_object=item,
        object_reference=item.receipt_number,
    )
    return reversal


@transaction.atomic
def generate_due_draft_invoices(*, as_of: date, actor: Any) -> int:
    from .models import BillingSchedule

    created = 0
    for schedule in BillingSchedule.objects.select_for_update(of=("self",)).filter(
        is_active=True, auto_generate_draft=True, next_billing_date__lte=as_of
    ):
        billing_date = schedule.next_billing_date
        assert billing_date is not None
        if ClientInvoice.objects.filter(
            source_billing_schedule=schedule, invoice_date=billing_date
        ).exists():
            continue
        profile = ClientBillingProfile.objects.get(client=schedule.client)
        lines = [
            {
                "description": rule.description,
                "quantity": rule.minimum_quantity or Decimal("1"),
                "unit": rule.quantity_source or "SERVICE",
                "unit_price": rule.unit_price,
                "tax_rate": rule.tax_code.rate if rule.tax_code else ZERO,
                "revenue_account": rule.revenue_account,
                "cost_center": rule.cost_center,
                "billing_rule": rule,
                "site": rule.site,
                "contract_service": rule.contract_service,
            }
            for rule in schedule.rules.filter(is_active=True)
        ]
        if lines:
            create_invoice(
                profile=profile,
                actor=actor,
                invoice_date=billing_date,
                invoice_type="RECURRING",
                lines=lines,
                contract=schedule.contract,
            )
            schedule.next_billing_date = billing_date + timedelta(days=30)
            schedule.save(update_fields=["next_billing_date", "updated_at"])
            created += 1
    return created


@transaction.atomic
def create_overdue_collection_reminders(*, as_of: date, actor: Any) -> int:
    """Queue one internal, privacy-safe reminder per overdue invoice and day."""
    from dsms.notifications.services import publish_notification_event

    created = 0
    now = timezone.now()
    invoices = ClientInvoice.objects.filter(
        due_date__lt=as_of,
        balance_due__gt=0,
        status__in=[InvoiceStatus.ISSUED, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.DISPUTED],
    ).select_related("company", "client")
    for invoice in invoices:
        if ClientCollectionActivity.objects.filter(
            invoice=invoice,
            activity_type=CollectionActivityType.FOLLOW_UP,
            activity_at__date=as_of,
        ).exists():
            continue
        ClientCollectionActivity.objects.create(
            company=invoice.company,
            client=invoice.client,
            invoice=invoice,
            activity_type=CollectionActivityType.FOLLOW_UP,
            activity_at=now,
            notes="Automated overdue reminder queued for authorized review.",
            actor=actor,
        )
        publish_notification_event(
            event_key=f"billing-overdue:{invoice.id}:{as_of.isoformat()}",
            event_type="CLIENT_INVOICE_OVERDUE",
            source_app="billing",
            source_model="ClientInvoice",
            source_object_id=invoice.id,
            company=invoice.company,
            safe_payload={
                "invoice_number": invoice.invoice_number,
                "client_id": str(invoice.client_id),
                "days_overdue": (as_of - invoice.due_date).days,
            },
        )
        created += 1
    return created
