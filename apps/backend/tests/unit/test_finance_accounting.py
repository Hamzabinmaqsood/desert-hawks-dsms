from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import selectors, services
from dsms.finance.enums import AccountType, JournalStatus, PeriodStatus
from dsms.finance.exceptions import (
    ClosedPeriodError,
    FinanceValidationError,
    MakerCheckerError,
    PostedRecordImmutableError,
)
from dsms.finance.models import FinanceEvent, JournalEntry
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():  # type: ignore[no-untyped-def]
    company = CompanyFactory.create()
    maker = UserFactory.create()
    checker = UserFactory.create()
    year = services.create_fiscal_year(
        company=company, name="FY 2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    period = services.create_accounting_period(
        fiscal_year=year,
        name="August 2026",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )
    cash = services.create_account(
        company=company, code=" 1000 ", name=" Cash ", account_type=AccountType.ASSET
    )
    equity = services.create_account(
        company=company, code="3000", name="Capital", account_type=AccountType.EQUITY
    )
    expense = services.create_account(
        company=company, code="5000", name="Expense", account_type=AccountType.EXPENSE
    )
    payable = services.create_account(
        company=company, code="2000", name="Payable", account_type=AccountType.LIABILITY
    )
    return company, maker, checker, year, period, cash, equity, expense, payable


def journal(setup, *, balanced: bool = True) -> JournalEntry:  # type: ignore[no-untyped-def]
    company, maker, _, year, period, cash, equity, _, _ = setup
    return services.create_journal(
        company=company,
        fiscal_year=year,
        accounting_period=period,
        entry_date=date(2026, 8, 18),
        description="Opening",
        created_by=maker,
        lines=[
            {"account": cash, "debit": Decimal("100.00")},
            {"account": equity, "credit": Decimal("100.00") if balanced else Decimal("90.00")},
        ],
    )


def test_account_normalization_uniqueness_and_hierarchy(setup) -> None:  # type: ignore[no-untyped-def]
    company, *_rest, cash, _equity, _expense, _payable = setup
    assert cash.code == "1000" and cash.name == "Cash"
    with pytest.raises(FinanceValidationError):
        services.create_account(
            company=company, code="1000", name="Duplicate", account_type=AccountType.ASSET
        )
    parent = services.create_account(
        company=company,
        code="1100",
        name="Current Assets",
        account_type=AccountType.ASSET,
        allow_posting=False,
    )
    child = services.create_account(
        company=company, code="1110", name="Bank", account_type=AccountType.ASSET, parent=parent
    )
    parent.parent = child
    with pytest.raises(FinanceValidationError):
        services.update_account(account=parent, parent=child)


def test_cross_company_and_inactive_parent_rejected() -> None:
    parent = services.create_account(
        company=CompanyFactory.create(), code="1000", name="Assets", account_type=AccountType.ASSET
    )
    with pytest.raises(FinanceValidationError):
        services.create_account(
            company=CompanyFactory.create(),
            code="1010",
            name="Cash",
            account_type=AccountType.ASSET,
            parent=parent,
        )
    parent.is_active = False
    parent.save(update_fields=["is_active"])
    with pytest.raises(FinanceValidationError):
        services.create_account(
            company=parent.company,
            code="1020",
            name="Bank",
            account_type=AccountType.ASSET,
            parent=parent,
        )


def test_fiscal_year_and_period_overlap_rejected(setup) -> None:  # type: ignore[no-untyped-def]
    company, *_ = setup
    with pytest.raises(FinanceValidationError):
        services.create_fiscal_year(
            company=company, name="Overlap", start_date=date(2026, 6, 1), end_date=date(2027, 5, 31)
        )


def test_unbalanced_journal_cannot_submit(setup) -> None:  # type: ignore[no-untyped-def]
    item = journal(setup, balanced=False)
    with pytest.raises(FinanceValidationError):
        services.submit_journal(journal=item, actor=setup[1])


def test_journal_maker_checker_posting_and_ledger(setup) -> None:  # type: ignore[no-untyped-def]
    item = journal(setup)
    item = services.submit_journal(journal=item, actor=setup[1])
    with pytest.raises(MakerCheckerError):
        services.approve_journal(journal=item, actor=setup[1])
    item = services.approve_journal(journal=item, actor=setup[2])
    item = services.post_journal(journal=item, actor=setup[2])
    assert item.status == JournalStatus.POSTED
    assert item.total_debit == item.total_credit == Decimal("100.00")
    assert selectors.account_balance(account=setup[5]) == Decimal("100.00")
    balances = [row["balance"] for row in selectors.trial_balance(company_id=setup[0].id)]
    assert balances == [Decimal("100.00"), Decimal("-100.00")]


def test_post_is_idempotent(setup) -> None:  # type: ignore[no-untyped-def]
    item = services.submit_journal(journal=journal(setup), actor=setup[1])
    item = services.approve_journal(journal=item, actor=setup[2])
    first = services.post_journal(journal=item, actor=setup[2])
    second = services.post_journal(journal=first, actor=setup[2])
    assert first.id == second.id


def test_closed_period_blocks_posting(setup) -> None:  # type: ignore[no-untyped-def]
    item = services.submit_journal(journal=journal(setup), actor=setup[1])
    item = services.approve_journal(journal=item, actor=setup[2])
    setup[4].status = PeriodStatus.CLOSED
    setup[4].save(update_fields=["status"])
    with pytest.raises(ClosedPeriodError):
        services.post_journal(journal=item, actor=setup[2])


def test_period_close_and_reopen_are_audited(setup) -> None:  # type: ignore[no-untyped-def]
    period = services.soft_close_accounting_period(period=setup[4], actor=setup[2])
    assert period.status == PeriodStatus.SOFT_CLOSED
    period = services.close_accounting_period(period=period, actor=setup[2])
    assert period.status == PeriodStatus.CLOSED
    with pytest.raises(FinanceValidationError):
        services.reopen_accounting_period(period=period, actor=setup[2], reason="")
    period = services.reopen_accounting_period(period=period, actor=setup[2], reason="Correction")
    assert period.status == PeriodStatus.OPEN
    assert FinanceEvent.objects.filter(accounting_period=period).count() == 3


def test_reversal_preserves_original_and_balances(setup) -> None:  # type: ignore[no-untyped-def]
    superuser = UserFactory.create(is_superuser=True)
    item = services.submit_journal(journal=journal(setup), actor=setup[1])
    item = services.approve_journal(journal=item, actor=setup[2])
    item = services.post_journal(journal=item, actor=setup[2])
    reversal = services.reverse_journal(
        journal=item, actor=superuser, reversal_date=date(2026, 8, 19), reason="Correction"
    )
    item.refresh_from_db()
    assert item.status == JournalStatus.REVERSED and item.reversed_by_entry == reversal
    assert reversal.status == JournalStatus.POSTED
    assert reversal.total_debit == reversal.total_credit


def test_posted_account_protected_fields_immutable(setup) -> None:  # type: ignore[no-untyped-def]
    item = services.submit_journal(journal=journal(setup), actor=setup[1])
    item = services.approve_journal(journal=item, actor=setup[2])
    services.post_journal(journal=item, actor=setup[2])
    with pytest.raises(PostedRecordImmutableError):
        services.update_account(account=setup[5], code="CHANGED")


def test_document_number_sequence_does_not_use_row_count(setup) -> None:  # type: ignore[no-untyped-def]
    first = services.next_document_number(company=setup[0], prefix="JV", year=2026)
    second = services.next_document_number(company=setup[0], prefix="JV", year=2026)
    assert first.endswith("000001") and second.endswith("000002")
