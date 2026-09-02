from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import DecimalField, ExpressionWrapper, F, Q, QuerySet, Sum
from django.utils import timezone

from dsms.workforce.models import Employee

from .enums import AccountType, PaymentStatus, ReceiptType, ReconciliationStatus, WorkflowStatus
from .models import JournalEntry, JournalLine
from .operations_models import (
    BankStatementLine,
    BudgetLine,
    CompanyExpense,
    FinanceApprovalHistory,
    FinanceAttachment,
    PettyCashFund,
    PettyCashTransaction,
)
from .payroll_models import (
    EmployeeAdvance,
    EmployeeCompensation,
    PayrollComponent,
    PayrollRun,
    PayrollVariableInput,
    Payslip,
    PayslipLine,
)
from .procurement_models import (
    PaymentVoucher,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceiptLine,
    PurchaseRequisition,
    Vendor,
    VendorBill,
)

ZERO = Decimal("0.00")
MONEY_FIELD: Any = DecimalField(max_digits=18, decimal_places=2)


def is_inventory_registration_eligible(*, receipt_line: PurchaseReceiptLine) -> bool:
    """Whether an accepted procurement line is an authoritative physical-inventory source."""
    return PurchaseReceiptLine.objects.filter(
        pk=receipt_line.pk,
        receipt__status=WorkflowStatus.APPROVED,
        receipt__receipt_type=ReceiptType.GOODS,
        receipt__purchase_order__status=WorkflowStatus.APPROVED,
        receipt__company_id=F("receipt__purchase_order__company_id"),
        purchase_order_line__purchase_order_id=F("receipt__purchase_order_id"),
        quantity__gt=0,
        accepted_quantity__gt=0,
        accepted_quantity__lte=F("quantity"),
    ).exists()


def _sum(queryset: QuerySet[Any], field: str) -> Decimal:
    return queryset.aggregate(total=Sum(field))["total"] or ZERO


def journal_register(
    *, company_id: Any, date_from: date | None = None, date_to: date | None = None
) -> QuerySet[JournalEntry]:
    items = JournalEntry.objects.filter(company_id=company_id).select_related("accounting_period")
    if date_from:
        items = items.filter(entry_date__gte=date_from)
    if date_to:
        items = items.filter(entry_date__lte=date_to)
    return items.order_by("entry_date", "journal_number")


def general_ledger(*, company_id: Any, account_id: Any | None = None) -> QuerySet[JournalLine]:
    items = JournalLine.objects.filter(
        journal_entry__company_id=company_id, journal_entry__status="POSTED"
    ).select_related("journal_entry", "account", "cost_center")
    return items.filter(account_id=account_id) if account_id else items


def profit_and_loss(*, company_id: Any, date_from: date, date_to: date) -> dict[str, Any]:
    lines = JournalLine.objects.filter(
        journal_entry__company_id=company_id,
        journal_entry__status="POSTED",
        journal_entry__entry_date__range=(date_from, date_to),
    )
    revenue = _sum(lines.filter(account__account_type=AccountType.REVENUE), "credit") - _sum(
        lines.filter(account__account_type=AccountType.REVENUE), "debit"
    )
    expenses = _sum(lines.filter(account__account_type=AccountType.EXPENSE), "debit") - _sum(
        lines.filter(account__account_type=AccountType.EXPENSE), "credit"
    )
    return {
        "revenue": revenue,
        "expenses": expenses,
        "profit": revenue - expenses,
        "automated_revenue_complete": False,
    }


def balance_sheet(*, company_id: Any, date_to: date) -> dict[str, Decimal]:
    lines = JournalLine.objects.filter(
        journal_entry__company_id=company_id,
        journal_entry__status="POSTED",
        journal_entry__entry_date__lte=date_to,
    )
    assets = _sum(lines.filter(account__account_type=AccountType.ASSET), "debit") - _sum(
        lines.filter(account__account_type=AccountType.ASSET), "credit"
    )
    liabilities = _sum(lines.filter(account__account_type=AccountType.LIABILITY), "credit") - _sum(
        lines.filter(account__account_type=AccountType.LIABILITY), "debit"
    )
    equity = _sum(lines.filter(account__account_type=AccountType.EQUITY), "credit") - _sum(
        lines.filter(account__account_type=AccountType.EQUITY), "debit"
    )
    return {"assets": assets, "liabilities": liabilities, "equity": equity}


def accounts_payable_aging(*, company_id: Any, as_of: date) -> list[dict[str, Any]]:
    rows = []
    for bill in VendorBill.objects.filter(
        company_id=company_id, total_amount__gt=F("paid_amount")
    ).select_related("vendor"):
        days = max((as_of - bill.due_date).days, 0)
        bucket = (
            "current"
            if days == 0
            else "1_30"
            if days <= 30
            else "31_60"
            if days <= 60
            else "61_90"
            if days <= 90
            else "over_90"
        )
        rows.append(
            {
                "bill": bill.id,
                "vendor": bill.vendor.name,
                "due_date": bill.due_date,
                "outstanding": bill.outstanding_amount,
                "bucket": bucket,
            }
        )
    return rows


def budget_vs_actual(*, company_id: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in BudgetLine.objects.filter(
        budget__company_id=company_id, budget__status=WorkflowStatus.APPROVED
    ).select_related("account", "accounting_period", "cost_center"):
        actual = _sum(
            JournalLine.objects.filter(
                journal_entry__company_id=company_id,
                journal_entry__status="POSTED",
                journal_entry__accounting_period=line.accounting_period,
                account=line.account,
                cost_center=line.cost_center,
            ),
            "debit",
        ) - _sum(
            JournalLine.objects.filter(
                journal_entry__company_id=company_id,
                journal_entry__status="POSTED",
                journal_entry__accounting_period=line.accounting_period,
                account=line.account,
                cost_center=line.cost_center,
            ),
            "credit",
        )
        variance = line.approved_amount - actual
        percentage = (
            variance / line.approved_amount * Decimal("100") if line.approved_amount else ZERO
        )
        rows.append(
            {
                "budget_line": line.id,
                "account": line.account.code,
                "budget": line.approved_amount,
                "actual": actual,
                "variance": variance,
                "variance_percentage": percentage,
            }
        )
    return rows


def finance_exceptions(*, company_id: Any, as_of: date | None = None) -> list[dict[str, Any]]:
    today = as_of or timezone.localdate()
    exceptions: list[dict[str, Any]] = []
    employees = set(Vendor.objects.none().values_list("id", flat=True))
    del employees
    for employee in Employee.objects.filter(company_id=company_id, exit_date__isnull=True):
        if (
            not EmployeeCompensation.objects.filter(employee=employee, effective_from__lte=today)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today))
            .exists()
        ):
            exceptions.append(
                {
                    "code": "MISSING_COMPENSATION",
                    "object_id": employee.id,
                    "message": "Employee has no current compensation.",
                }
            )
    for item in PayrollVariableInput.objects.filter(
        payroll_period__company_id=company_id, status=WorkflowStatus.DRAFT
    ):
        exceptions.append(
            {
                "code": "UNAPPROVED_PAYROLL_INPUT",
                "object_id": item.id,
                "message": "Payroll input is not approved.",
            }
        )
    for component in PayrollComponent.objects.filter(company_id=company_id, is_active=True):
        missing = component.payable_account_id is None or (
            component.component_type in ["EARNING", "EMPLOYER_CONTRIBUTION"]
            and component.expense_account_id is None
        )
        if missing:
            exceptions.append(
                {
                    "code": "MISSING_PAYROLL_ACCOUNT_MAPPING",
                    "object_id": component.id,
                    "message": "Payroll component has incomplete account mapping.",
                }
            )
    for slip in Payslip.objects.filter(payroll_run__company_id=company_id, net_pay__lt=ZERO):
        exceptions.append(
            {
                "code": "INVALID_NET_PAY",
                "object_id": slip.id,
                "message": "Payslip has negative net pay.",
            }
        )
    for bill in VendorBill.objects.filter(
        company_id=company_id, due_date__lt=today, total_amount__gt=F("paid_amount")
    ):
        exceptions.append(
            {"code": "OVERDUE_BILL", "object_id": bill.id, "message": "Vendor bill is overdue."}
        )
    for bill in VendorBill.objects.filter(company_id=company_id).exclude(match_exception=""):
        exceptions.append(
            {"code": "BILL_MATCH_EXCEPTION", "object_id": bill.id, "message": bill.match_exception}
        )
    for expense in CompanyExpense.objects.filter(
        company_id=company_id,
        category__receipt_required=True,
        amount__gte=F("category__receipt_threshold"),
    ):
        if not FinanceAttachment.objects.filter(object_id=expense.id).exists():
            exceptions.append(
                {
                    "code": "EXPENSE_MISSING_RECEIPT",
                    "object_id": expense.id,
                    "message": "Expense requires a receipt attachment.",
                }
            )
    resolved_ids = FinanceApprovalHistory.objects.filter(
        company_id=company_id, decision__in=["APPROVED", "REJECTED"]
    ).values("object_id")
    for approval in FinanceApprovalHistory.objects.filter(
        company_id=company_id,
        decision="SUBMITTED",
        created_at__lt=timezone.now() - timedelta(days=7),
    ).exclude(object_id__in=resolved_ids):
        exceptions.append(
            {
                "code": "STALE_APPROVAL",
                "object_id": approval.object_id,
                "message": "Approval has remained pending for more than seven days.",
            }
        )
    for line in BankStatementLine.objects.filter(
        statement__bank_account__company_id=company_id,
        status__in=[ReconciliationStatus.UNMATCHED, ReconciliationStatus.EXCEPTION],
        transaction_date__lt=today - timedelta(days=7),
    ):
        exceptions.append(
            {
                "code": "UNRECONCILED_BANK_ITEM",
                "object_id": line.id,
                "message": "Bank item remains unreconciled.",
            }
        )
    for voucher in PaymentVoucher.objects.filter(
        company_id=company_id, status=WorkflowStatus.APPROVED, journal_entry__isnull=True
    ):
        exceptions.append(
            {
                "code": "UNPOSTED_APPROVED_VOUCHER",
                "object_id": voucher.id,
                "message": "Approved voucher is not posted.",
            }
        )
    for row in budget_vs_actual(company_id=company_id):
        if row["variance"] < ZERO:
            exceptions.append(
                {
                    "code": "BUDGET_OVERRUN",
                    "object_id": row["budget_line"],
                    "message": "Actual spending exceeds approved budget.",
                }
            )
    for advance in EmployeeAdvance.objects.filter(
        employee__company_id=company_id,
        amount__gt=F("recovered_amount"),
        created_at__date__lt=today - timedelta(days=30),
    ):
        exceptions.append(
            {
                "code": "UNPAID_EMPLOYEE_ADVANCE",
                "object_id": advance.id,
                "message": "Employee advance remains outstanding.",
            }
        )
    return exceptions


def dashboard_summary(*, company_id: Any) -> dict[str, Any]:
    posted = JournalLine.objects.filter(
        journal_entry__company_id=company_id, journal_entry__status="POSTED"
    )
    bank_cash = _sum(posted.filter(account__account_type=AccountType.ASSET), "debit") - _sum(
        posted.filter(account__account_type=AccountType.ASSET), "credit"
    )
    return {
        "payroll_cost": _sum(
            PayrollRun.objects.filter(
                company_id=company_id,
                status__in=[WorkflowStatus.APPROVED, WorkflowStatus.POSTED, WorkflowStatus.CLOSED],
            ),
            "gross_total",
        ),
        "payroll_payable": _sum(
            PayrollRun.objects.filter(company_id=company_id).exclude(status=WorkflowStatus.CLOSED),
            "net_total",
        ),
        "expenses": _sum(
            CompanyExpense.objects.filter(
                company_id=company_id,
                status__in=[WorkflowStatus.APPROVED, WorkflowStatus.POSTED, WorkflowStatus.PAID],
            ),
            "amount",
        ),
        "vendor_payable": sum(
            (bill.outstanding_amount for bill in VendorBill.objects.filter(company_id=company_id)),
            ZERO,
        ),
        "outstanding_employee_advances": sum(
            (
                advance.outstanding_amount
                for advance in EmployeeAdvance.objects.filter(employee__company_id=company_id)
            ),
            ZERO,
        ),
        "pending_requisitions": PurchaseRequisition.objects.filter(
            company_id=company_id, status=WorkflowStatus.SUBMITTED
        ).count(),
        "pending_pos": PurchaseOrder.objects.filter(
            company_id=company_id, status=WorkflowStatus.SUBMITTED
        ).count(),
        "pending_vendor_bills": VendorBill.objects.filter(
            company_id=company_id, status=WorkflowStatus.SUBMITTED
        ).count(),
        "pending_payments": PaymentVoucher.objects.filter(
            company_id=company_id, payment_status=PaymentStatus.PENDING
        ).count(),
        "bank_cash_position": bank_cash,
        "budget_vs_actual": budget_vs_actual(company_id=company_id),
        "unreconciled_bank_transactions": BankStatementLine.objects.filter(
            statement__bank_account__company_id=company_id
        )
        .exclude(status__in=[ReconciliationStatus.MATCHED, ReconciliationStatus.IGNORED])
        .count(),
        "pending_approvals": FinanceApprovalHistory.objects.filter(
            company_id=company_id, decision="SUBMITTED"
        ).count()
        - FinanceApprovalHistory.objects.filter(
            company_id=company_id, decision__in=["APPROVED", "REJECTED"]
        ).count(),
        "finance_exceptions": len(finance_exceptions(company_id=company_id)),
    }


REPORT_QUERYSETS = {
    "expense-register": lambda company_id: CompanyExpense.objects.filter(company_id=company_id),
    "expense-by-category": lambda company_id: (
        CompanyExpense.objects.filter(company_id=company_id)
        .values("category__name")
        .annotate(total=Sum("amount"))
    ),
    "expense-by-branch": lambda company_id: (
        CompanyExpense.objects.filter(company_id=company_id)
        .values("branch__name")
        .annotate(total=Sum("amount"))
    ),
    "expense-by-department": lambda company_id: (
        CompanyExpense.objects.filter(company_id=company_id)
        .values("department__name")
        .annotate(total=Sum("amount"))
    ),
    "expense-by-cost-center": lambda company_id: (
        CompanyExpense.objects.filter(company_id=company_id)
        .values("cost_center__name")
        .annotate(total=Sum("amount"))
    ),
    "payroll-register": lambda company_id: PayrollRun.objects.filter(company_id=company_id),
    "payroll-component-summary": lambda company_id: (
        PayslipLine.objects.filter(payslip__payroll_run__company_id=company_id)
        .values("component__code", "component__name", "component_type")
        .annotate(total=Sum("amount"))
    ),
    "payroll-cost-by-branch": lambda company_id: (
        Payslip.objects.filter(payroll_run__company_id=company_id)
        .values("employee__branch__name")
        .annotate(total=Sum("gross_pay"))
    ),
    "payroll-cost-by-department": lambda company_id: (
        Payslip.objects.filter(payroll_run__company_id=company_id)
        .values("employee__department__name")
        .annotate(total=Sum("gross_pay"))
    ),
    "employee-advance-register": lambda company_id: EmployeeAdvance.objects.filter(
        employee__company_id=company_id
    ),
    "vendor-register": lambda company_id: Vendor.objects.filter(company_id=company_id),
    "vendor-ledger": lambda company_id: (
        VendorBill.objects.filter(company_id=company_id)
        .values("vendor__code", "vendor__name")
        .annotate(billed=Sum("total_amount"), paid=Sum("paid_amount"))
    ),
    "outstanding-bills": lambda company_id: VendorBill.objects.filter(
        company_id=company_id, total_amount__gt=F("paid_amount")
    ),
    "payment-register": lambda company_id: PaymentVoucher.objects.filter(company_id=company_id),
    "purchase-requisition-register": lambda company_id: PurchaseRequisition.objects.filter(
        company_id=company_id
    ),
    "purchase-order-register": lambda company_id: PurchaseOrder.objects.filter(
        company_id=company_id
    ),
    "po-commitment": lambda company_id: (
        PurchaseOrderLine.objects.filter(
            purchase_order__company_id=company_id,
            purchase_order__status=WorkflowStatus.APPROVED,
        )
        .values("purchase_order__order_number")
        .annotate(
            committed=Sum(
                ExpressionWrapper(F("quantity") * F("unit_price"), output_field=MONEY_FIELD)
            )
        )
    ),
    "petty-cash-register": lambda company_id: PettyCashFund.objects.filter(company_id=company_id),
    "cash-book": lambda company_id: PettyCashTransaction.objects.filter(
        fund__company_id=company_id
    ),
    "bank-book": lambda company_id: BankStatementLine.objects.filter(
        statement__bank_account__company_id=company_id
    ),
    "bank-reconciliation": lambda company_id: BankStatementLine.objects.filter(
        statement__bank_account__company_id=company_id
    ),
    "pending-approval": lambda company_id: FinanceApprovalHistory.objects.filter(
        company_id=company_id, decision="SUBMITTED"
    ),
    "unmatched-bank-transactions": lambda company_id: BankStatementLine.objects.filter(
        statement__bank_account__company_id=company_id
    ).exclude(status=ReconciliationStatus.MATCHED),
}
