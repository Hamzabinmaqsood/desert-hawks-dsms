from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.documents.storage import private_document_storage

from .enums import (
    AdjustmentStatus,
    ARTransactionType,
    BillingCalculationMethod,
    BillingFrequency,
    CollectionActivityType,
    InvoiceStatus,
    InvoiceType,
    PaymentMethod,
    PeriodAlignment,
    ReceiptStatus,
)
from .storage import invoice_pdf_upload_to


class BillingModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class ClientBillingProfile(BillingModel, ActiveModel):
    client = models.OneToOneField("contracts.Client", on_delete=models.PROTECT)
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    billing_name = models.CharField(max_length=200)
    billing_address = models.TextField()
    billing_email = models.EmailField(blank=True)
    billing_phone = models.CharField(max_length=30, blank=True)
    tax_registration_number = models.CharField(max_length=100, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=30)
    currency = models.CharField(max_length=3, default="PKR")
    default_billing_frequency = models.CharField(
        max_length=20, choices=BillingFrequency.choices, default=BillingFrequency.MONTHLY
    )
    default_revenue_account = models.ForeignKey(
        "finance.Account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_revenue_profiles",
    )
    default_receivable_account = models.ForeignKey(
        "finance.Account", on_delete=models.PROTECT, related_name="billing_receivable_profiles"
    )
    default_tax_account = models.ForeignKey(
        "finance.Account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_tax_profiles",
    )
    default_discount_account = models.ForeignKey(
        "finance.Account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_discount_profiles",
    )
    default_payment_instructions = models.TextField(blank=True)
    invoice_notes = models.TextField(blank=True)

    def clean(self) -> None:
        if self.client.company_id != self.company_id:
            raise ValidationError({"client": "Client belongs to another company."})
        for field in (
            "default_revenue_account",
            "default_receivable_account",
            "default_tax_account",
            "default_discount_account",
        ):
            account = getattr(self, field)
            if account and account.company_id != self.company_id:
                raise ValidationError({field: "Account belongs to another company."})


class TaxCode(BillingModel, ActiveModel):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    rate = models.DecimalField(max_digits=8, decimal_places=4)
    tax_account = models.ForeignKey("finance.Account", on_delete=models.PROTECT)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="billing_tax_company_code_uniq"
            ),
            models.CheckConstraint(condition=Q(rate__gte=0), name="billing_tax_rate_nonnegative"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class BillingSchedule(BillingModel, ActiveModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    client = models.ForeignKey("contracts.Client", on_delete=models.PROTECT)
    contract = models.ForeignKey("contracts.ServiceContract", on_delete=models.PROTECT)
    frequency = models.CharField(max_length=20, choices=BillingFrequency.choices)
    billing_day = models.PositiveSmallIntegerField(null=True, blank=True)
    period_alignment = models.CharField(max_length=20, choices=PeriodAlignment.choices)
    first_billing_date = models.DateField()
    next_billing_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    generate_days_before_period_end = models.PositiveIntegerField(null=True, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=30)
    auto_generate_draft = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    def clean(self) -> None:
        if self.client.company_id != self.company_id or self.contract.company_id != self.company_id:
            raise ValidationError("Schedule company, client, and contract must agree.")
        if self.contract.client_id != self.client_id:
            raise ValidationError({"contract": "Contract belongs to another client."})
        if self.billing_day is not None and not 1 <= self.billing_day <= 31:
            raise ValidationError({"billing_day": "Billing day must be between 1 and 31."})


class BillingRule(BillingModel, ActiveModel):
    billing_schedule = models.ForeignKey(
        BillingSchedule, on_delete=models.PROTECT, related_name="rules"
    )
    contract_service = models.ForeignKey(
        "contracts.ContractService", null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    description = models.CharField(max_length=255)
    calculation_method = models.CharField(max_length=30, choices=BillingCalculationMethod.choices)
    quantity_source = models.CharField(max_length=40)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    minimum_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    maximum_quantity = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    tax_code = models.ForeignKey(TaxCode, null=True, blank=True, on_delete=models.PROTECT)
    revenue_account = models.ForeignKey("finance.Account", on_delete=models.PROTECT)
    cost_center = models.ForeignKey(
        "finance.CostCenter", null=True, blank=True, on_delete=models.PROTECT
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)


class ClientInvoice(BillingModel):
    invoice_number = models.CharField(max_length=40)
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    client = models.ForeignKey(
        "contracts.Client", on_delete=models.PROTECT, related_name="invoices"
    )
    contract = models.ForeignKey(
        "contracts.ServiceContract", null=True, blank=True, on_delete=models.PROTECT
    )
    invoice_type = models.CharField(max_length=20, choices=InvoiceType.choices)
    currency = models.CharField(max_length=3, default="PKR")
    invoice_date = models.DateField()
    service_period_start = models.DateField(null=True, blank=True)
    service_period_end = models.DateField(null=True, blank=True)
    due_date = models.DateField()
    client_po_reference = models.CharField(max_length=100, blank=True)
    client_reference = models.CharField(max_length=100, blank=True)
    source_billing_schedule = models.ForeignKey(
        BillingSchedule, null=True, blank=True, on_delete=models.PROTECT
    )
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    discount_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    adjustment_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    balance_due = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20, choices=InvoiceStatus.choices, default=InvoiceStatus.DRAFT
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="generated_invoices"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_invoices",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_client_invoices",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="issued_client_invoices",
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="voided_client_invoices",
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    billing_name_snapshot = models.CharField(max_length=200)
    billing_address_snapshot = models.TextField()
    tax_registration_snapshot = models.CharField(max_length=100, blank=True)
    payment_terms_snapshot = models.PositiveIntegerField()
    payment_instructions_snapshot = models.TextField(blank=True)
    notes_snapshot = models.TextField(blank=True)
    accounting_journal = models.OneToOneField(
        "finance.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="client_invoice",
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "invoice_number"], name="billing_invoice_number_uniq"
            ),
            models.CheckConstraint(
                condition=Q(due_date__gte=models.F("invoice_date")),
                name="billing_invoice_due_valid",
            ),
            models.CheckConstraint(
                condition=Q(balance_due__gte=0), name="billing_invoice_balance_nonnegative"
            ),
        ]
        permissions = [
            ("approve_invoice", "Can approve client invoices"),
            ("issue_invoice", "Can issue client invoices"),
            ("void_invoice", "Can void client invoices"),
            ("download_invoice", "Can download private invoice PDFs"),
        ]

    @property
    def is_overdue(self) -> bool:
        from django.utils import timezone

        return (
            self.balance_due > 0
            and self.due_date < timezone.localdate()
            and self.status not in {InvoiceStatus.VOIDED, InvoiceStatus.CANCELLED}
        )


class ClientInvoiceLine(UUIDModel):
    invoice = models.ForeignKey(ClientInvoice, on_delete=models.PROTECT, related_name="lines")
    line_number = models.PositiveIntegerField()
    contract_service = models.ForeignKey(
        "contracts.ContractService", null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    billing_rule = models.ForeignKey(BillingRule, null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit = models.CharField(max_length=30)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    gross_amount = models.DecimalField(max_digits=18, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    taxable_amount = models.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2)
    revenue_account = models.ForeignKey("finance.Account", on_delete=models.PROTECT)
    cost_center = models.ForeignKey(
        "finance.CostCenter", null=True, blank=True, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "line_number"], name="billing_invoice_line_uniq"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="billing_invoice_line_qty_positive"
            ),
            models.CheckConstraint(
                condition=Q(line_total__gte=0), name="billing_invoice_line_total_nonnegative"
            ),
        ]


class ClientReceipt(BillingModel):
    receipt_number = models.CharField(max_length=40)
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    client = models.ForeignKey(
        "contracts.Client", on_delete=models.PROTECT, related_name="receipts"
    )
    received_at = models.DateTimeField()
    value_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="PKR")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_method = models.CharField(max_length=30, choices=PaymentMethod.choices)
    bank_account = models.ForeignKey(
        "finance.BankAccount", null=True, blank=True, on_delete=models.PROTECT
    )
    cheque_reference = models.CharField(max_length=100, blank=True)
    external_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=30, choices=ReceiptStatus.choices, default=ReceiptStatus.DRAFT
    )
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="received_client_payments"
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="confirmed_client_payments",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    accounting_journal = models.OneToOneField(
        "finance.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="client_receipt",
    )
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "receipt_number"], name="billing_receipt_number_uniq"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="billing_receipt_amount_positive"
            ),
        ]
        permissions = [
            ("confirm_receipt", "Can confirm client receipts"),
            ("allocate_receipt", "Can allocate client receipts"),
            ("reverse_receipt", "Can reverse client receipts"),
        ]


class ClientReceiptAllocation(UUIDModel):
    receipt = models.ForeignKey(ClientReceipt, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(ClientInvoice, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    allocated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    allocated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="billing_allocation_positive")
        ]


class ClientAccountTransaction(UUIDModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    client = models.ForeignKey(
        "contracts.Client", on_delete=models.PROTECT, related_name="ar_transactions"
    )
    transaction_type = models.CharField(max_length=30, choices=ARTransactionType.choices)
    effective_at = models.DateTimeField()
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    invoice = models.ForeignKey(ClientInvoice, null=True, blank=True, on_delete=models.PROTECT)
    receipt = models.ForeignKey(ClientReceipt, null=True, blank=True, on_delete=models.PROTECT)
    allocation = models.OneToOneField(
        ClientReceiptAllocation, null=True, blank=True, on_delete=models.PROTECT
    )
    source_reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["client", "effective_at"], name="billing_ar_client_time_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(debit__gte=0, credit__gte=0), name="billing_ar_values_nonnegative"
            ),
            models.CheckConstraint(condition=~Q(debit=0, credit=0), name="billing_ar_nonzero"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("AR transactions are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("AR transactions cannot be deleted.")


class ClientCreditNote(BillingModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    client = models.ForeignKey("contracts.Client", on_delete=models.PROTECT)
    invoice = models.ForeignKey(
        ClientInvoice, on_delete=models.PROTECT, related_name="credit_notes"
    )
    note_number = models.CharField(max_length=40)
    note_date = models.DateField()
    currency = models.CharField(max_length=3, default="PKR")
    reason = models.TextField()
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=30, choices=AdjustmentStatus.choices, default=AdjustmentStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_credit_notes"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_credit_notes",
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="issued_credit_notes",
    )
    accounting_journal = models.OneToOneField(
        "finance.JournalEntry", null=True, blank=True, on_delete=models.PROTECT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "note_number"], name="uniq_client_credit_note"
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0), name="client_credit_note_nonnegative"
            ),
        ]
        permissions = [
            ("approve_credit_note", "Can approve credit notes"),
            ("issue_credit_note", "Can issue credit notes"),
        ]


class ClientCreditNoteLine(UUIDModel):
    credit_note = models.ForeignKey(
        ClientCreditNote, on_delete=models.PROTECT, related_name="lines"
    )
    line_number = models.PositiveIntegerField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    revenue_account = models.ForeignKey("finance.Account", on_delete=models.PROTECT)
    tax_account = models.ForeignKey(
        "finance.Account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="credit_note_tax_lines",
    )
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["credit_note", "line_number"], name="uniq_credit_note_line"
            )
        ]


class ClientDebitNote(BillingModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    client = models.ForeignKey("contracts.Client", on_delete=models.PROTECT)
    invoice = models.ForeignKey(
        ClientInvoice, null=True, blank=True, on_delete=models.PROTECT, related_name="debit_notes"
    )
    note_number = models.CharField(max_length=40)
    note_date = models.DateField()
    currency = models.CharField(max_length=3, default="PKR")
    reason = models.TextField()
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=30, choices=AdjustmentStatus.choices, default=AdjustmentStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_debit_notes"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_debit_notes",
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="issued_debit_notes",
    )
    accounting_journal = models.OneToOneField(
        "finance.JournalEntry", null=True, blank=True, on_delete=models.PROTECT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "note_number"], name="uniq_client_debit_note"
            ),
            models.CheckConstraint(
                condition=Q(total_amount__gte=0), name="client_debit_note_nonnegative"
            ),
        ]
        permissions = [
            ("approve_debit_note", "Can approve debit notes"),
            ("issue_debit_note", "Can issue debit notes"),
        ]


class ClientDebitNoteLine(UUIDModel):
    debit_note = models.ForeignKey(ClientDebitNote, on_delete=models.PROTECT, related_name="lines")
    line_number = models.PositiveIntegerField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    revenue_account = models.ForeignKey("finance.Account", on_delete=models.PROTECT)
    tax_account = models.ForeignKey(
        "finance.Account",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="debit_note_tax_lines",
    )
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["debit_note", "line_number"], name="uniq_debit_note_line"
            )
        ]


class ClientReceiptReversal(BillingModel):
    receipt = models.OneToOneField(ClientReceipt, on_delete=models.PROTECT, related_name="reversal")
    reason = models.TextField()
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    accounting_journal = models.OneToOneField(
        "finance.JournalEntry", null=True, blank=True, on_delete=models.PROTECT
    )


class ClientCollectionActivity(BillingModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    client = models.ForeignKey(
        "contracts.Client", on_delete=models.PROTECT, related_name="collection_activities"
    )
    invoice = models.ForeignKey(
        ClientInvoice,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="collection_activities",
    )
    activity_type = models.CharField(max_length=30, choices=CollectionActivityType.choices)
    activity_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    promised_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    promised_date = models.DateField(null=True, blank=True)
    next_follow_up = models.DateTimeField(null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class ClientInvoiceDocument(BillingModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    invoice = models.ForeignKey(ClientInvoice, on_delete=models.PROTECT, related_name="documents")
    revision_number = models.PositiveIntegerField()
    file = models.FileField(
        storage=private_document_storage, upload_to=invoice_pdf_upload_to, max_length=255
    )
    sha256 = models.CharField(max_length=64)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    generated_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "revision_number"], name="uniq_invoice_document_revision"
            )
        ]
