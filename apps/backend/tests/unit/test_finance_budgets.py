from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import domain_selectors, domain_services, services
from dsms.finance.enums import WorkflowStatus
from dsms.finance.operations_models import Budget, BudgetLine
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_approved_budget_reports_actual_variance() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    year, period, accounts = accounting_setup(company)
    budget = Budget.objects.create(
        company=company,
        name="Operating 2026",
        fiscal_year=year,
        status=WorkflowStatus.SUBMITTED,
        created_by=maker,
    )
    line = BudgetLine.objects.create(
        budget=budget,
        account=accounts["expense"],
        accounting_period=period,
        approved_amount=Decimal("1000"),
    )
    domain_services.approve_budget(budget=budget, actor=checker)
    journal = services.create_journal(
        company=company,
        fiscal_year=year,
        accounting_period=period,
        entry_date=date(2026, 8, 5),
        description="Spend",
        created_by=maker,
        lines=[
            {"account": accounts["expense"], "debit": Decimal("250")},
            {"account": accounts["cash"], "credit": Decimal("250")},
        ],
    )
    journal = services.submit_journal(journal=journal, actor=maker)
    journal = services.approve_journal(journal=journal, actor=checker)
    services.post_journal(journal=journal, actor=checker)
    row = domain_selectors.budget_vs_actual(company_id=company.id)[0]
    assert row["budget_line"] == line.id
    assert row["actual"] == Decimal("250")
    assert row["variance"] == Decimal("750")
    assert row["variance_percentage"] == Decimal("75")
