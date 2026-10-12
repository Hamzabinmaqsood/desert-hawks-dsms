import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel


class ProviderType(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    BANK = "BANK", "Bank"
    EASYPAISA = "EASYPAISA", "Easypaisa"
    TEST = "TEST", "Test"
    OTHER = "OTHER", "Other"


class BeneficiaryStatus(models.TextChoices):
    REQUESTED = "REQUESTED", "Requested"
    UNDER_VERIFICATION = "UNDER_VERIFICATION", "Under verification"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    ACTIVATED = "ACTIVATED", "Activated"
    SUPERSEDED = "SUPERSEDED", "Superseded"


class PaymentBatchStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
    APPROVED = "APPROVED", "Approved"
    QUEUED = "QUEUED", "Queued"
    PROCESSING = "PROCESSING", "Processing"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    PARTIAL = "PARTIAL", "Partial"
    EXCEPTION = "EXCEPTION", "Exception"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentInstructionStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    PROCESSING = "PROCESSING", "Processing"
    SUBMITTED = "SUBMITTED", "Submitted"
    ACCEPTED = "ACCEPTED", "Accepted"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"
    REVERSED = "REVERSED", "Reversed"
    REQUIRES_REVIEW = "REQUIRES_REVIEW", "Requires review"


class ProviderTransactionStatus(models.TextChoices):
    CREATED = "CREATED", "Created"
    SUBMITTED = "SUBMITTED", "Submitted"
    ACCEPTED = "ACCEPTED", "Accepted"
    PENDING = "PENDING", "Pending"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    REVERSED = "REVERSED", "Reversed"
    UNKNOWN = "UNKNOWN", "Unknown"


class SettlementStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    PROCESSING = "PROCESSING", "Processing"
    PARTIALLY_RECONCILED = "PARTIALLY_RECONCILED", "Partially reconciled"
    RECONCILED = "RECONCILED", "Reconciled"
    EXCEPTION = "EXCEPTION", "Exception"
    CLOSED = "CLOSED", "Closed"


class PaymentProviderConfiguration(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    provider_type = models.CharField(max_length=20, choices=ProviderType.choices)
    display_name = models.CharField(max_length=120)
    currency = models.CharField(max_length=3, default="PKR")
    adapter_code = models.CharField(max_length=80)
    secret_reference = models.CharField(max_length=200, blank=True)
    safe_configuration = models.JSONField(default=dict, blank=True)
    supports_status_query = models.BooleanField(default=False)
    supports_idempotency = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_payment_provider_code")
        ]
        permissions = [("manage_payment_providers", "Can manage payment providers")]


class PaymentBeneficiaryProfile(UUIDModel, TimeStampedModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    employee = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    vendor = models.ForeignKey("finance.Vendor", null=True, blank=True, on_delete=models.PROTECT)
    provider_type = models.CharField(max_length=20, choices=ProviderType.choices)
    currency = models.CharField(max_length=3, default="PKR")
    destination_encrypted = models.TextField()
    destination_masked = models.CharField(max_length=80)
    account_title = models.CharField(max_length=150)
    status = models.CharField(
        max_length=30, choices=BeneficiaryStatus.choices, default=BeneficiaryStatus.REQUESTED
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_destinations"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="verified_destinations",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_destinations",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(employee__isnull=False, vendor__isnull=True)
                    | Q(employee__isnull=True, vendor__isnull=False)
                ),
                name="payment_beneficiary_exactly_one_owner",
            ),
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(is_active=True, employee__isnull=False),
                name="uniq_active_employee_destination",
            ),
            models.UniqueConstraint(
                fields=["vendor"],
                condition=Q(is_active=True, vendor__isnull=False),
                name="uniq_active_vendor_destination",
            ),
        ]
        permissions = [
            ("view_sensitive_payment_destination", "Can view sensitive payment destinations"),
            ("approve_payment_destination", "Can approve payment destination changes"),
        ]


class PaymentDestinationChange(UUIDModel, TimeStampedModel):
    profile = models.ForeignKey(
        PaymentBeneficiaryProfile, on_delete=models.PROTECT, related_name="change_history"
    )
    previous_profile = models.ForeignKey(
        PaymentBeneficiaryProfile,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseding_changes",
    )
    status = models.CharField(max_length=30, choices=BeneficiaryStatus.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason_safe = models.CharField(max_length=250, blank=True)


class PaymentAccountingProfile(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.OneToOneField("organization.Company", on_delete=models.PROTECT)
    payroll_payable_account = models.ForeignKey(
        "finance.Account", on_delete=models.PROTECT, related_name="payment_payroll_profiles"
    )
    vendor_payable_account = models.ForeignKey(
        "finance.Account", on_delete=models.PROTECT, related_name="payment_vendor_profiles"
    )
    gateway_clearing_account = models.ForeignKey(
        "finance.Account", on_delete=models.PROTECT, related_name="payment_clearing_profiles"
    )
    bank_account = models.ForeignKey(
        "finance.Account", on_delete=models.PROTECT, related_name="payment_bank_profiles"
    )
    provider_fee_account = models.ForeignKey(
        "finance.Account", on_delete=models.PROTECT, related_name="payment_fee_profiles"
    )

    def clean(self) -> None:
        errors: dict[str, str] = {}
        for field_name in (
            "payroll_payable_account",
            "vendor_payable_account",
            "gateway_clearing_account",
            "bank_account",
            "provider_fee_account",
        ):
            account = getattr(self, field_name)
            if account.company_id != self.company_id:
                errors[field_name] = "Account must belong to the payment profile company."
            elif not account.is_active or not account.allow_posting:
                errors[field_name] = "Account must be active and allow posting."
        if errors:
            raise ValidationError(errors)


class PaymentBatch(UUIDModel, TimeStampedModel):
    batch_number = models.CharField(max_length=40)
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    batch_type = models.CharField(
        max_length=20, choices=[("PAYROLL", "Payroll"), ("VENDOR", "Vendor")]
    )
    payroll_run = models.ForeignKey(
        "finance.PayrollRun", null=True, blank=True, on_delete=models.PROTECT
    )
    provider = models.ForeignKey(PaymentProviderConfiguration, on_delete=models.PROTECT)
    currency = models.CharField(max_length=3, default="PKR")
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    instruction_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=30, choices=PaymentBatchStatus.choices, default=PaymentBatchStatus.DRAFT
    )
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prepared_payment_batches"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_payment_batches",
    )
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="released_payment_batches",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "batch_number"], name="uniq_payment_batch_number"
            ),
            models.UniqueConstraint(
                fields=["payroll_run"],
                condition=Q(payroll_run__isnull=False),
                name="uniq_payroll_disbursement_batch",
            ),
        ]
        permissions = [
            ("prepare_payment_batch", "Can prepare payment batches"),
            ("approve_payment_batch", "Can approve payment batches"),
            ("release_payment_batch", "Can release payment batches"),
            ("retry_payment", "Can retry failed payments"),
        ]


class PaymentInstruction(UUIDModel, TimeStampedModel):
    batch = models.ForeignKey(PaymentBatch, on_delete=models.PROTECT, related_name="instructions")
    beneficiary = models.ForeignKey(PaymentBeneficiaryProfile, on_delete=models.PROTECT)
    payslip = models.ForeignKey("finance.Payslip", null=True, blank=True, on_delete=models.PROTECT)
    payment_voucher = models.ForeignKey(
        "finance.PaymentVoucher", null=True, blank=True, on_delete=models.PROTECT
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    currency = models.CharField(max_length=3)
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(
        max_length=30,
        choices=PaymentInstructionStatus.choices,
        default=PaymentInstructionStatus.QUEUED,
    )
    provider_status = models.CharField(
        max_length=20,
        choices=ProviderTransactionStatus.choices,
        default=ProviderTransactionStatus.CREATED,
    )
    provider_reference = models.CharField(max_length=150, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    failure_code = models.CharField(max_length=80, blank=True)
    safe_failure_message = models.CharField(max_length=250, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    accounting_journal = models.OneToOneField(
        "finance.JournalEntry", null=True, blank=True, on_delete=models.PROTECT
    )

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_instruction_positive"),
            models.CheckConstraint(
                condition=(
                    Q(payslip__isnull=False, payment_voucher__isnull=True)
                    | Q(payslip__isnull=True, payment_voucher__isnull=False)
                ),
                name="payment_instruction_one_obligation",
            ),
            models.UniqueConstraint(
                fields=["payslip"],
                condition=Q(payslip__isnull=False),
                name="uniq_payslip_payment_instruction",
            ),
            models.UniqueConstraint(
                fields=["payment_voucher"],
                condition=Q(payment_voucher__isnull=False),
                name="uniq_voucher_payment_instruction",
            ),
            models.UniqueConstraint(
                fields=["batch", "provider_reference"],
                condition=~Q(provider_reference=""),
                name="uniq_batch_provider_reference",
            ),
        ]


class PaymentInstructionAllocation(UUIDModel):
    instruction = models.ForeignKey(
        PaymentInstruction, on_delete=models.PROTECT, related_name="bill_allocations"
    )
    vendor_bill = models.ForeignKey("finance.VendorBill", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instruction", "vendor_bill"], name="uniq_payment_bill_allocation"
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="payment_bill_allocation_positive"
            ),
        ]


class PaymentProviderTransaction(UUIDModel, TimeStampedModel):
    instruction = models.ForeignKey(
        PaymentInstruction, on_delete=models.PROTECT, related_name="provider_transactions"
    )
    attempt_number = models.PositiveIntegerField()
    provider_reference = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=ProviderTransactionStatus.choices)
    submitted_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=80, blank=True)
    safe_failure_message = models.CharField(max_length=250, blank=True)
    safe_response = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["instruction", "attempt_number"], name="uniq_payment_attempt"
            ),
            models.UniqueConstraint(
                fields=["instruction", "provider_reference"],
                condition=~Q(provider_reference=""),
                name="uniq_instruction_provider_reference",
            ),
        ]


class PaymentProviderSettlement(UUIDModel, TimeStampedModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    provider = models.ForeignKey(PaymentProviderConfiguration, on_delete=models.PROTECT)
    settlement_reference = models.CharField(max_length=100)
    settlement_date = models.DateField()
    currency = models.CharField(max_length=3)
    gross_amount = models.DecimalField(max_digits=18, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=30, choices=SettlementStatus.choices, default=SettlementStatus.OPEN
    )
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reconciled_provider_settlements",
    )
    accounting_journal = models.OneToOneField(
        "finance.JournalEntry", null=True, blank=True, on_delete=models.PROTECT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "settlement_reference"], name="uniq_provider_settlement"
            ),
            models.CheckConstraint(
                condition=Q(gross_amount__gt=0, fee_amount__gte=0),
                name="payment_settlement_amounts_valid",
            ),
            models.CheckConstraint(
                condition=Q(net_amount=models.F("gross_amount") + models.F("fee_amount")),
                name="payment_settlement_outflow_total_valid",
            ),
        ]
        permissions = [
            ("import_payment_settlement", "Can import payment settlements"),
            ("reconcile_payment_settlement", "Can reconcile payment settlements"),
        ]


class PaymentProviderSettlementLine(UUIDModel):
    settlement = models.ForeignKey(
        PaymentProviderSettlement, on_delete=models.PROTECT, related_name="lines"
    )
    provider_reference = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    fee_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    currency = models.CharField(max_length=3)
    instruction = models.ForeignKey(
        PaymentInstruction, null=True, blank=True, on_delete=models.PROTECT
    )
    status = models.CharField(
        max_length=30,
        choices=[("UNMATCHED", "Unmatched"), ("MATCHED", "Matched"), ("EXCEPTION", "Exception")],
        default="UNMATCHED",
    )
    exception_code = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["settlement", "provider_reference"], name="uniq_settlement_provider_line"
            )
        ]
