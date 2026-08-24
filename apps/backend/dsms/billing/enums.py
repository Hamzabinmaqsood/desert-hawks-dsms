from django.db import models


class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    ISSUED = "ISSUED", "Issued"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
    PAID = "PAID", "Paid"
    DISPUTED = "DISPUTED", "Disputed"
    VOIDED = "VOIDED", "Voided"
    CANCELLED = "CANCELLED", "Cancelled"


class InvoiceType(models.TextChoices):
    STANDARD = "STANDARD", "Standard"
    RECURRING = "RECURRING", "Recurring"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    FINAL = "FINAL", "Final"
    OTHER = "OTHER", "Other"


class BillingFrequency(models.TextChoices):
    ONE_TIME = "ONE_TIME", "One time"
    WEEKLY = "WEEKLY", "Weekly"
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Quarterly"
    ANNUAL = "ANNUAL", "Annual"
    CUSTOM = "CUSTOM", "Custom"


class PeriodAlignment(models.TextChoices):
    ADVANCE = "ADVANCE", "Advance"
    ARREARS = "ARREARS", "Arrears"
    CUSTOM = "CUSTOM", "Custom"


class BillingCalculationMethod(models.TextChoices):
    FIXED_AMOUNT = "FIXED_AMOUNT", "Fixed amount"
    MONTHLY_FIXED = "MONTHLY_FIXED", "Monthly fixed"
    PER_POSITION = "PER_POSITION", "Per position"
    PER_GUARD_SHIFT = "PER_GUARD_SHIFT", "Per guard shift"
    PER_HOUR = "PER_HOUR", "Per hour"
    PER_DAY = "PER_DAY", "Per day"
    CUSTOM_MANUAL = "CUSTOM_MANUAL", "Custom manual"


class ReceiptStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CONFIRMED = "CONFIRMED", "Confirmed"
    PARTIALLY_ALLOCATED = "PARTIALLY_ALLOCATED", "Partially allocated"
    ALLOCATED = "ALLOCATED", "Allocated"
    REVERSED = "REVERSED", "Reversed"
    CANCELLED = "CANCELLED", "Cancelled"


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "BANK_TRANSFER", "Bank transfer"
    EASYPAISA = "EASYPAISA", "Easypaisa"
    JAZZCASH = "JAZZCASH", "JazzCash"
    CHEQUE = "CHEQUE", "Cheque"
    CASH = "CASH", "Cash"
    CARD = "CARD", "Card"
    ONLINE_GATEWAY = "ONLINE_GATEWAY", "Online gateway"
    OTHER = "OTHER", "Other"


class ARTransactionType(models.TextChoices):
    INVOICE = "INVOICE", "Invoice"
    DEBIT_NOTE = "DEBIT_NOTE", "Debit note"
    CREDIT_NOTE = "CREDIT_NOTE", "Credit note"
    RECEIPT = "RECEIPT", "Receipt"
    RECEIPT_ALLOCATION = "RECEIPT_ALLOCATION", "Receipt allocation"
    REVERSAL = "REVERSAL", "Reversal"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class AdjustmentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    ISSUED = "ISSUED", "Issued"
    ALLOCATED = "ALLOCATED", "Allocated"
    VOIDED = "VOIDED", "Voided"


class CollectionActivityType(models.TextChoices):
    CALL = "CALL", "Call"
    EMAIL = "EMAIL", "Email"
    MEETING = "MEETING", "Meeting"
    PAYMENT_PROMISE = "PAYMENT_PROMISE", "Payment promise"
    DISPUTE = "DISPUTE", "Dispute"
    FOLLOW_UP = "FOLLOW_UP", "Follow up"
    OTHER = "OTHER", "Other"
