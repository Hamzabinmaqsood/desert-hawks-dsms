import uuid
from decimal import Decimal
from pathlib import Path

from django.db import models

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.documents.storage import PrivateDocumentStorage
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department
from dsms.workforce.models import Employee

from .enums import (
    ApprovalDecision,
    ApprovalDocumentType,
    PaymentStatus,
    PettyCashTransactionType,
    ReconciliationStatus,
    WorkflowStatus,
)
from .models import Account, AccountingPeriod, CostCenter, JournalEntry


def finance_upload_to(instance: object, filename: str) -> str:
    return f"finance/{uuid.uuid4().hex[:2]}/{uuid.uuid4()}{Path(filename).suffix.lower()}"


class ExpenseCategory(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="expense_categories"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="expense_categories"
    )
    receipt_required = models.BooleanField(default=True)
    receipt_threshold = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_expense_category")
        ]


class CompanyExpense(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="company_expenses")
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="company_expenses"
    )
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="company_expenses"
    )
    cost_center = models.ForeignKey(
        CostCenter, null=True, blank=True, on_delete=models.PROTECT, related_name="expenses"
    )
    expense_number = models.CharField(max_length=30)
    expense_date = models.DateField()
    description = models.TextField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_company_expenses"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_company_expenses",
    )
    journal_entry = models.OneToOneField(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="company_expense",
    )


class ExpenseClaim(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="expense_claims")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="expense_claims")
    claim_number = models.CharField(max_length=30)
    claim_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_expense_claims"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_expense_claims",
    )
    journal_entry = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="expense_claim"
    )


class ExpenseClaimLine(UUIDModel):
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.PROTECT, related_name="lines")
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="claim_lines"
    )
    expense_date = models.DateField()
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="expense_claim_lines"
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expense_claim_lines",
    )
    cost_center = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="expense_claim_lines",
    )


class RecurringExpenseTemplate(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="recurring_expenses"
    )
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="recurring_templates"
    )
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    frequency = models.CharField(max_length=20, default="MONTHLY")
    next_due_date = models.DateField()
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="recurring_expenses"
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recurring_expenses",
    )
    cost_center = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="recurring_expenses",
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_recurring_expenses",
    )


class FinanceAttachment(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="finance_attachments"
    )
    document_type = models.CharField(max_length=40, choices=ApprovalDocumentType.choices)
    object_id = models.UUIDField()
    file = models.FileField(storage=PrivateDocumentStorage(), upload_to=finance_upload_to)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="finance_attachments"
    )


class PettyCashFund(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="petty_cash_funds")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    custodian = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="petty_cash_funds"
    )
    cash_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="petty_cash_funds"
    )
    limit_amount = models.DecimalField(max_digits=18, decimal_places=2)


class PettyCashTransaction(UUIDModel, TimeStampedModel):
    fund = models.ForeignKey(PettyCashFund, on_delete=models.PROTECT, related_name="transactions")
    transaction_type = models.CharField(max_length=20, choices=PettyCashTransactionType.choices)
    transaction_date = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    description = models.CharField(max_length=255)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="petty_cash_transactions"
    )
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="petty_cash_transactions",
    )


class CashAccount(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="cash_accounts")
    name = models.CharField(max_length=120)
    ledger_account = models.OneToOneField(
        Account, on_delete=models.PROTECT, related_name="cash_account"
    )
    custodian = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="cash_accounts"
    )


class BankAccount(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="bank_accounts")
    name = models.CharField(max_length=120)
    bank_name = models.CharField(max_length=120)
    account_number_encrypted = models.TextField()
    iban_encrypted = models.TextField(blank=True)
    currency = models.CharField(max_length=3, default="PKR")
    ledger_account = models.OneToOneField(
        Account, on_delete=models.PROTECT, related_name="bank_account"
    )


class FundTransfer(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="fund_transfers")
    transfer_number = models.CharField(max_length=30)
    transfer_date = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    source_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="outgoing_transfers"
    )
    destination_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="incoming_transfers"
    )
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_fund_transfers"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_fund_transfers",
    )
    journal_entry = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="fund_transfer"
    )


class BankStatement(UUIDModel, TimeStampedModel):
    bank_account = models.ForeignKey(
        BankAccount, on_delete=models.PROTECT, related_name="statements"
    )
    statement_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=18, decimal_places=2)
    import_hash = models.CharField(max_length=64, unique=True)
    imported_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="imported_bank_statements"
    )


class BankStatementLine(UUIDModel, TimeStampedModel):
    statement = models.ForeignKey(BankStatement, on_delete=models.PROTECT, related_name="lines")
    transaction_date = models.DateField()
    reference = models.CharField(max_length=120, blank=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=ReconciliationStatus.choices, default=ReconciliationStatus.UNMATCHED
    )
    suggested_journal = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="suggested_bank_lines",
    )
    matched_journal = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="matched_bank_lines",
    )
    reconciled_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="reconciled_bank_lines"
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)


class Budget(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="budgets")
    name = models.CharField(max_length=120)
    fiscal_year = models.ForeignKey(
        "finance.FiscalYear", on_delete=models.PROTECT, related_name="budgets"
    )
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_budgets")
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_budgets"
    )


class BudgetLine(UUIDModel):
    budget = models.ForeignKey(Budget, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="budget_lines")
    cost_center = models.ForeignKey(
        CostCenter, null=True, blank=True, on_delete=models.PROTECT, related_name="budget_lines"
    )
    accounting_period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name="budget_lines"
    )
    approved_amount = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["budget", "account", "cost_center", "accounting_period"],
                name="uniq_budget_dimension",
            )
        ]


class ApprovalPolicy(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="finance_approval_policies"
    )
    document_type = models.CharField(max_length=40, choices=ApprovalDocumentType.choices)
    name = models.CharField(max_length=120)
    minimum_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    maximum_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)


class ApprovalStep(UUIDModel):
    policy = models.ForeignKey(ApprovalPolicy, on_delete=models.PROTECT, related_name="steps")
    sequence = models.PositiveIntegerField()
    role_code = models.CharField(max_length=50)
    required = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["policy", "sequence"], name="uniq_approval_step")
        ]


class FinanceApprovalHistory(UUIDModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="finance_approval_history"
    )
    document_type = models.CharField(max_length=40, choices=ApprovalDocumentType.choices)
    object_id = models.UUIDField()
    step = models.ForeignKey(
        ApprovalStep, null=True, blank=True, on_delete=models.PROTECT, related_name="history"
    )
    decision = models.CharField(max_length=20, choices=ApprovalDecision.choices)
    actor = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="finance_approval_actions"
    )
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
