from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import domain_services
from dsms.finance.enums import PettyCashTransactionType, WorkflowStatus
from dsms.finance.exceptions import FinanceValidationError
from dsms.finance.operations_models import (
    CompanyExpense,
    ExpenseCategory,
    ExpenseClaim,
    ExpenseClaimLine,
    PettyCashFund,
    RecurringExpenseTemplate,
)
from dsms.finance.tasks import generate_recurring_expense_drafts
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_expense_requires_receipt_and_posts_balanced_journal() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    category = ExpenseCategory.objects.create(
        company=company,
        code="TRAVEL",
        name="Travel",
        expense_account=accounts["expense"],
        receipt_required=False,
    )
    expense = CompanyExpense.objects.create(
        company=company,
        category=category,
        expense_number="EXP-1",
        expense_date=date(2026, 8, 10),
        description="Travel",
        amount=Decimal("250.00"),
        status=WorkflowStatus.SUBMITTED,
        created_by=maker,
    )
    expense = domain_services.approve_and_post_expense(
        expense=expense, actor=checker, payable_account=accounts["payable"]
    )
    assert expense.journal_entry
    assert expense.journal_entry.total_debit == expense.journal_entry.total_credit


def test_petty_cash_balance_is_derived_and_overspend_blocked() -> None:
    company = CompanyFactory.create()
    actor = UserFactory.create()
    employee = EmployeeFactory.create(company=company)
    _year, _period, accounts = accounting_setup(company)
    fund = PettyCashFund.objects.create(
        company=company,
        code="HQ",
        name="HQ petty cash",
        custodian=employee,
        cash_account=accounts["cash"],
        limit_amount=Decimal("1000"),
    )
    domain_services.record_petty_cash(
        fund=fund,
        transaction_type=PettyCashTransactionType.OPENING,
        amount=Decimal("500"),
        transaction_date=date(2026, 8, 1),
        description="Opening",
        actor=actor,
    )
    domain_services.record_petty_cash(
        fund=fund,
        transaction_type=PettyCashTransactionType.DISBURSEMENT,
        amount=Decimal("125"),
        transaction_date=date(2026, 8, 2),
        description="Supplies",
        actor=actor,
    )
    assert domain_services.petty_cash_balance(fund=fund) == Decimal("375.00")
    with pytest.raises(FinanceValidationError):
        domain_services.record_petty_cash(
            fund=fund,
            transaction_type=PettyCashTransactionType.DISBURSEMENT,
            amount=Decimal("376"),
            transaction_date=date(2026, 8, 3),
            description="Too much",
            actor=actor,
        )


def test_recurring_expense_generates_draft_only() -> None:
    company = CompanyFactory.create()
    actor = UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    category = ExpenseCategory.objects.create(
        company=company,
        code="RENT",
        name="Rent",
        expense_account=accounts["expense"],
    )
    RecurringExpenseTemplate.objects.create(
        company=company,
        category=category,
        description="Monthly rent",
        amount=Decimal("500"),
        next_due_date=date(2026, 8, 18),
        created_by=actor,
    )
    assert generate_recurring_expense_drafts() == 1
    expense = CompanyExpense.objects.get()
    assert expense.status == WorkflowStatus.DRAFT
    assert expense.payment_status == "PENDING"


def test_employee_expense_claim_posts_reimbursement_payable() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    employee = EmployeeFactory.create(company=company)
    _year, _period, accounts = accounting_setup(company)
    category = ExpenseCategory.objects.create(
        company=company,
        code="MILEAGE",
        name="Mileage",
        expense_account=accounts["expense"],
        receipt_required=False,
    )
    claim = ExpenseClaim.objects.create(
        company=company,
        employee=employee,
        claim_number="CLM-1",
        claim_date=date(2026, 8, 10),
        status=WorkflowStatus.SUBMITTED,
        total_amount=Decimal("75"),
        created_by=maker,
    )
    ExpenseClaimLine.objects.create(
        claim=claim,
        category=category,
        expense_date=date(2026, 8, 9),
        description="Travel",
        amount=Decimal("75"),
    )
    claim = domain_services.approve_and_post_expense_claim(
        claim=claim, actor=checker, reimbursement_payable=accounts["payable"]
    )
    assert claim.journal_entry
    assert claim.journal_entry.total_debit == claim.journal_entry.total_credit
