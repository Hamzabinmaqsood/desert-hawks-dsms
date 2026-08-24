from django.db import models


class AccountType(models.TextChoices):
    ASSET = "ASSET", "Asset"
    LIABILITY = "LIABILITY", "Liability"
    EQUITY = "EQUITY", "Equity"
    REVENUE = "REVENUE", "Revenue"
    EXPENSE = "EXPENSE", "Expense"


class PeriodStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    SOFT_CLOSED = "SOFT_CLOSED", "Soft closed"
    CLOSED = "CLOSED", "Closed"


class JournalStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"
    REJECTED = "REJECTED", "Rejected"


class FinanceEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    UPDATED = "UPDATED", "Updated"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    POSTED = "POSTED", "Posted"
    REVERSED = "REVERSED", "Reversed"
    PERIOD_SOFT_CLOSED = "PERIOD_SOFT_CLOSED", "Period soft closed"
    PERIOD_CLOSED = "PERIOD_CLOSED", "Period closed"
    PERIOD_REOPENED = "PERIOD_REOPENED", "Period reopened"
    CALCULATED = "CALCULATED", "Calculated"
    PAID = "PAID", "Paid"
    CLOSED = "CLOSED", "Closed"
    MATCHED = "MATCHED", "Matched"


class WorkflowStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    POSTED = "POSTED", "Posted"
    PARTIALLY_PAID = "PARTIALLY_PAID", "Partially paid"
    PAID = "PAID", "Paid"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"


class ComponentType(models.TextChoices):
    EARNING = "EARNING", "Earning"
    DEDUCTION = "DEDUCTION", "Deduction"
    EMPLOYER_CONTRIBUTION = "EMPLOYER_CONTRIBUTION", "Employer contribution"


class CalculationType(models.TextChoices):
    FIXED = "FIXED", "Fixed"
    PERCENTAGE = "PERCENTAGE", "Percentage"
    VARIABLE = "VARIABLE", "Approved variable input"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    PAID = "PAID", "Paid"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


class ReceiptType(models.TextChoices):
    GOODS = "GOODS", "Goods"
    SERVICE = "SERVICE", "Service"


class MatchType(models.TextChoices):
    TWO_WAY = "TWO_WAY", "Two-way"
    THREE_WAY = "THREE_WAY", "Three-way"


class PettyCashTransactionType(models.TextChoices):
    OPENING = "OPENING", "Opening"
    DISBURSEMENT = "DISBURSEMENT", "Disbursement"
    REIMBURSEMENT = "REIMBURSEMENT", "Reimbursement"
    RETURN = "RETURN", "Return"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class ReconciliationStatus(models.TextChoices):
    UNMATCHED = "UNMATCHED", "Unmatched"
    SUGGESTED = "SUGGESTED", "Suggested"
    MATCHED = "MATCHED", "Matched"
    IGNORED = "IGNORED", "Ignored"
    EXCEPTION = "EXCEPTION", "Exception"


class ApprovalDocumentType(models.TextChoices):
    PAYROLL = "PAYROLL", "Payroll"
    JOURNAL = "JOURNAL", "Journal"
    PURCHASE_REQUISITION = "PURCHASE_REQUISITION", "Purchase requisition"
    PURCHASE_ORDER = "PURCHASE_ORDER", "Purchase order"
    VENDOR_BILL = "VENDOR_BILL", "Vendor bill"
    PAYMENT_VOUCHER = "PAYMENT_VOUCHER", "Payment voucher"
    EXPENSE = "EXPENSE", "Expense"
    EXPENSE_CLAIM = "EXPENSE_CLAIM", "Expense claim"
    EMPLOYEE_ADVANCE = "EMPLOYEE_ADVANCE", "Employee advance"
    FUND_TRANSFER = "FUND_TRANSFER", "Fund transfer"
    BUDGET = "BUDGET", "Budget"


class ApprovalDecision(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class ExceptionSeverity(models.TextChoices):
    INFO = "INFO", "Information"
    WARNING = "WARNING", "Warning"
    CRITICAL = "CRITICAL", "Critical"
