from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department

from .enums import AccountType, FinanceEventType, JournalStatus, PeriodStatus


class Account(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="finance_accounts")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    account_type = models.CharField(max_length=20, choices=AccountType.choices)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    description = models.TextField(blank=True)
    allow_posting = models.BooleanField(default=True)
    is_control_account = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["company", "code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_finance_account_code")
        ]
        permissions = [("manage_chart_of_accounts", "Can manage chart of accounts")]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.parent_id:
            parent = self.parent
            assert parent is not None
            if parent.company_id != self.company_id:
                errors["parent"] = "Parent account must belong to the same company."
            elif not parent.is_active:
                errors["parent"] = "Inactive account cannot be a parent."
            elif parent.account_type != self.account_type:
                errors["account_type"] = "Child and parent account types must match."
            ancestor: Account | None = parent
            while ancestor is not None:
                if ancestor.pk == self.pk:
                    errors["parent"] = "Account hierarchy cannot contain a cycle."
                    break
                ancestor = ancestor.parent
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        super().save(*args, **kwargs)


class FiscalYear(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="fiscal_years")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_fiscal_year_name"),
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")), name="fiscal_year_dates_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company.code} / {self.name}"


class AccountingPeriod(UUIDModel, TimeStampedModel):
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name="periods")
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="accounting_periods"
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=PeriodStatus.choices, default=PeriodStatus.OPEN
    )

    class Meta:
        ordering = ["start_date"]
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uniq_accounting_period_name"),
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")),
                name="accounting_period_dates_valid",
            ),
        ]
        permissions = [
            ("manage_fiscal_periods", "Can manage fiscal periods"),
            ("post_soft_closed_period", "Can post into soft-closed periods"),
        ]

    def __str__(self) -> str:
        return f"{self.company.code} / {self.name}"


class CostCenter(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="cost_centers")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    branch = models.ForeignKey(
        Branch, null=True, blank=True, on_delete=models.PROTECT, related_name="cost_centers"
    )
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.PROTECT, related_name="cost_centers"
    )
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["company", "code"]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_cost_center_code")
        ]

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.branch_id and self.branch is not None and self.branch.company_id != self.company_id:
            errors["branch"] = "Branch must belong to cost center company."
        if (
            self.department_id
            and self.department is not None
            and self.department.company_id != self.company_id
        ):
            errors["department"] = "Department must belong to cost center company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        super().save(*args, **kwargs)


class DocumentSequence(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="finance_sequences")
    prefix = models.CharField(max_length=10)
    year = models.PositiveIntegerField()
    last_number = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "prefix", "year"], name="uniq_finance_sequence"
            )
        ]


class JournalEntry(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="journal_entries")
    fiscal_year = models.ForeignKey(
        FiscalYear, on_delete=models.PROTECT, related_name="journal_entries"
    )
    accounting_period = models.ForeignKey(
        AccountingPeriod, on_delete=models.PROTECT, related_name="journal_entries"
    )
    journal_number = models.CharField(max_length=30)
    entry_date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    source_type = models.CharField(max_length=50, default="MANUAL")
    source_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=JournalStatus.choices, default=JournalStatus.DRAFT
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_journals")
    submitted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="submitted_journals"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_journals"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="posted_journals"
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_by_entry = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reverses_entry"
    )

    class Meta:
        ordering = ["-entry_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "journal_number"], name="uniq_journal_number"
            )
        ]
        indexes = [
            models.Index(
                fields=["company", "entry_date", "status"], name="journal_company_date_idx"
            )
        ]
        permissions = [
            ("create_journal", "Can create journals"),
            ("approve_journal", "Can approve journals"),
            ("post_journal", "Can post journals"),
            ("reverse_journal", "Can reverse journals"),
            ("view_financial_reports", "Can view financial reports"),
            ("view_financial_dashboard", "Can view financial dashboard"),
            ("view_finance_audit", "Can view finance audit"),
            ("manage_payroll", "Can manage payroll"),
            ("manage_procurement", "Can manage procurement"),
            ("manage_expenses", "Can manage expenses"),
            ("manage_banking", "Can manage banking and reconciliation"),
            ("manage_budgets", "Can manage budgets"),
            ("approve_finance", "Can approve finance transactions"),
            ("view_sensitive_finance_data", "Can view sensitive finance data"),
            ("manage_finance_attachments", "Can manage private finance attachments"),
        ]

    @property
    def total_debit(self) -> Decimal:
        return sum((line.debit for line in self.lines.all()), Decimal("0.00"))

    @property
    def total_credit(self) -> Decimal:
        return sum((line.credit for line in self.lines.all()), Decimal("0.00"))

    def __str__(self) -> str:
        return self.journal_number


class JournalLine(UUIDModel):
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="journal_lines")
    cost_center = models.ForeignKey(
        CostCenter, null=True, blank=True, on_delete=models.PROTECT, related_name="journal_lines"
    )
    description = models.CharField(max_length=255, blank=True)
    debit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    credit = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)),
                name="journal_line_one_side",
            )
        ]
        indexes = [
            models.Index(fields=["account", "journal_entry"], name="journal_line_account_idx")
        ]

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if (
            self.account_id
            and self.journal_entry_id
            and self.account.company_id != self.journal_entry.company_id
        ):
            errors["account"] = "Account must belong to journal company."
        if self.account_id and (not self.account.is_active or not self.account.allow_posting):
            errors["account"] = "Account is inactive or does not allow posting."
        if (
            self.cost_center_id
            and self.cost_center is not None
            and self.cost_center.company_id != self.journal_entry.company_id
        ):
            errors["cost_center"] = "Cost center must belong to journal company."
        if errors:
            raise ValidationError(errors)


class FinanceEvent(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="finance_events")
    journal_entry = models.ForeignKey(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="events"
    )
    accounting_period = models.ForeignKey(
        AccountingPeriod, null=True, blank=True, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(max_length=40, choices=FinanceEventType.choices)
    actor = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="finance_events"
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


# Domain models live in focused files but are imported here so Django discovers
# them under the single ``finance`` app and callers retain one public model module.
from .operations_models import (  # noqa: E402, F401
    ApprovalPolicy,
    ApprovalStep,
    BankAccount,
    BankStatement,
    BankStatementLine,
    Budget,
    BudgetLine,
    CashAccount,
    CompanyExpense,
    ExpenseCategory,
    ExpenseClaim,
    ExpenseClaimLine,
    FinanceApprovalHistory,
    FinanceAttachment,
    FundTransfer,
    PettyCashFund,
    PettyCashTransaction,
    RecurringExpenseTemplate,
)
from .payment_models import (  # noqa: E402, F401
    PaymentAccountingProfile,
    PaymentBatch,
    PaymentBeneficiaryProfile,
    PaymentDestinationChange,
    PaymentInstruction,
    PaymentInstructionAllocation,
    PaymentProviderConfiguration,
    PaymentProviderSettlement,
    PaymentProviderSettlementLine,
    PaymentProviderTransaction,
)
from .payroll_models import (  # noqa: E402, F401
    EmployeeAdvance,
    EmployeeAdvanceRecovery,
    EmployeeCompensation,
    EmployeePaymentProfile,
    PayrollComponent,
    PayrollPaymentBatch,
    PayrollPaymentItem,
    PayrollPeriod,
    PayrollRun,
    PayrollVariableInput,
    Payslip,
    PayslipLine,
    SalaryStructure,
    SalaryStructureComponent,
    StatutoryScheme,
    TaxBracket,
    TaxScheme,
)
from .procurement_models import (  # noqa: E402, F401
    PaymentVoucher,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)
