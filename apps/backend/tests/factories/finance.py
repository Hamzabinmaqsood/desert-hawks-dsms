from datetime import date

from dsms.finance import services
from dsms.finance.enums import AccountType
from dsms.finance.models import Account, AccountingPeriod, FiscalYear
from dsms.organization.models import Company


def accounting_setup(company: Company) -> tuple[FiscalYear, AccountingPeriod, dict[str, Account]]:
    year = services.create_fiscal_year(
        company=company,
        name="FY 2026",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    period = services.create_accounting_period(
        fiscal_year=year,
        name="August 2026",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    accounts = {
        "cash": services.create_account(
            company=company, code="1000", name="Cash", account_type=AccountType.ASSET
        ),
        "bank": services.create_account(
            company=company, code="1010", name="Bank", account_type=AccountType.ASSET
        ),
        "payable": services.create_account(
            company=company,
            code="2000",
            name="Payable",
            account_type=AccountType.LIABILITY,
        ),
        "deduction": services.create_account(
            company=company,
            code="2010",
            name="Deduction Payable",
            account_type=AccountType.LIABILITY,
        ),
        "equity": services.create_account(
            company=company, code="3000", name="Equity", account_type=AccountType.EQUITY
        ),
        "expense": services.create_account(
            company=company,
            code="5000",
            name="Expense",
            account_type=AccountType.EXPENSE,
        ),
    }
    return year, period, accounts
