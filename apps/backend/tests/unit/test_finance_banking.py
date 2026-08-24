from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import domain_services, services
from dsms.finance.enums import ReconciliationStatus
from dsms.finance.exceptions import FinanceValidationError
from dsms.finance.operations_models import BankAccount
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_csv_import_suggests_but_requires_manual_reconciliation() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    year, period, accounts = accounting_setup(company)
    journal = services.create_journal(
        company=company,
        fiscal_year=year,
        accounting_period=period,
        entry_date=date(2026, 8, 18),
        description="Deposit",
        created_by=maker,
        lines=[
            {"account": accounts["bank"], "debit": Decimal("100")},
            {"account": accounts["equity"], "credit": Decimal("100")},
        ],
    )
    journal = services.submit_journal(journal=journal, actor=maker)
    journal = services.approve_journal(journal=journal, actor=checker)
    journal = services.post_journal(journal=journal, actor=checker)
    bank = BankAccount.objects.create(
        company=company,
        name="Operating",
        bank_name="Test Bank",
        account_number_encrypted="ciphertext",
        ledger_account=accounts["bank"],
    )
    content = b"date,description,amount,reference\n2026-08-18,Deposit,100.00,DEP-1\n"
    statement = domain_services.import_bank_csv(bank_account=bank, content=content, actor=maker)
    line = statement.lines.get()
    assert line.status == ReconciliationStatus.SUGGESTED and line.matched_journal is None
    line = domain_services.reconcile_bank_line(line=line, journal=journal, actor=checker)
    assert line.status == ReconciliationStatus.MATCHED and line.reconciled_by == checker
    with pytest.raises(FinanceValidationError):
        domain_services.import_bank_csv(bank_account=bank, content=content, actor=maker)
