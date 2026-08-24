from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import domain_selectors, services
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_profit_loss_balance_sheet_and_dashboard_use_posted_entries() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    year, period, accounts = accounting_setup(company)
    journal = services.create_journal(
        company=company,
        fiscal_year=year,
        accounting_period=period,
        entry_date=date(2026, 8, 1),
        description="Expense",
        created_by=maker,
        lines=[
            {"account": accounts["expense"], "debit": Decimal("80")},
            {"account": accounts["cash"], "credit": Decimal("80")},
        ],
    )
    journal = services.submit_journal(journal=journal, actor=maker)
    journal = services.approve_journal(journal=journal, actor=checker)
    services.post_journal(journal=journal, actor=checker)
    pnl = domain_selectors.profit_and_loss(
        company_id=company.id, date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)
    )
    assert pnl["expenses"] == Decimal("80") and pnl["automated_revenue_complete"] is False
    assert domain_selectors.balance_sheet(company_id=company.id, date_to=date(2026, 8, 31))[
        "assets"
    ] == Decimal("-80")
    assert domain_selectors.dashboard_summary(company_id=company.id)[
        "bank_cash_position"
    ] == Decimal("-80")


def test_exception_center_detects_missing_compensation() -> None:
    company = CompanyFactory.create()
    employee = EmployeeFactory.create(company=company)
    rows = domain_selectors.finance_exceptions(company_id=company.id, as_of=date(2026, 8, 18))
    assert {
        "code": "MISSING_COMPENSATION",
        "object_id": employee.id,
        "message": "Employee has no current compensation.",
    } in rows
