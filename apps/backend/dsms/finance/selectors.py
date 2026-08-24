from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db.models import DecimalField, F, QuerySet, Sum

from .enums import JournalStatus
from .models import Account, AccountingPeriod, FiscalYear, JournalEntry, JournalLine


def account_list() -> QuerySet[Account]:
    return Account.objects.select_related("company", "parent")


def fiscal_year_list() -> QuerySet[FiscalYear]:
    return FiscalYear.objects.select_related("company")


def period_list() -> QuerySet[AccountingPeriod]:
    return AccountingPeriod.objects.select_related("company", "fiscal_year")


def journal_list() -> QuerySet[JournalEntry]:
    return JournalEntry.objects.select_related(
        "company",
        "fiscal_year",
        "accounting_period",
        "created_by",
        "submitted_by",
        "approved_by",
        "posted_by",
    ).prefetch_related("lines__account", "lines__cost_center")


def ledger_lines(
    *,
    company_id: UUID,
    account_id: UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> QuerySet[JournalLine]:
    queryset = JournalLine.objects.filter(
        journal_entry__company_id=company_id, journal_entry__status=JournalStatus.POSTED
    ).select_related("journal_entry", "account", "cost_center")
    if account_id:
        queryset = queryset.filter(account_id=account_id)
    if date_from:
        queryset = queryset.filter(journal_entry__entry_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(journal_entry__entry_date__lte=date_to)
    return queryset.order_by("journal_entry__entry_date", "created_at")


def trial_balance(*, company_id: UUID, date_to: date | None = None) -> list[dict[str, object]]:
    lines = JournalLine.objects.filter(
        journal_entry__company_id=company_id, journal_entry__status=JournalStatus.POSTED
    )
    if date_to:
        lines = lines.filter(journal_entry__entry_date__lte=date_to)
    rows = (
        lines.values("account_id", "account__code", "account__name", "account__account_type")
        .annotate(total_debit=Sum("debit"), total_credit=Sum("credit"))
        .order_by("account__code")
    )
    return [
        {
            **row,
            "balance": (row["total_debit"] or Decimal("0.00"))
            - (row["total_credit"] or Decimal("0.00")),
        }
        for row in rows
    ]


def account_balance(*, account: Account, date_to: date | None = None) -> Decimal:
    queryset = ledger_lines(company_id=account.company_id, account_id=account.id)
    if date_to:
        queryset = queryset.filter(journal_entry__entry_date__lte=date_to)
    value = queryset.aggregate(
        balance=Sum(
            F("debit") - F("credit"), output_field=DecimalField(max_digits=18, decimal_places=2)
        )
    )["balance"]
    return value or Decimal("0.00")
