from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.identity.models import User
from dsms.organization.business_defaults import (
    normalize_document_prefix,
    validate_document_prefix,
)
from dsms.organization.models import Branch, Company, Department
from dsms.subscriptions.enforcement import requires_company_module

from .enums import FinanceEventType, JournalStatus, PeriodStatus
from .exceptions import (
    ClosedPeriodError,
    FinanceValidationError,
    InvalidFinanceTransitionError,
    MakerCheckerError,
    PostedRecordImmutableError,
)
from .models import (
    Account,
    AccountingPeriod,
    CostCenter,
    DocumentSequence,
    FinanceEvent,
    FiscalYear,
    JournalEntry,
    JournalLine,
)

ZERO = Decimal("0.00")


def money(value: Decimal | str | int) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _save(instance: models.Model) -> None:
    try:
        instance.full_clean()
        instance.save()
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        raise FinanceValidationError(detail) from exc
    except IntegrityError as exc:
        raise FinanceValidationError(
            {"detail": ["Financial record conflicts with existing data."]}
        ) from exc


@transaction.atomic
@requires_company_module("finance_core", argument="company")
def create_account(
    *,
    company: Company,
    code: str,
    name: str,
    account_type: str,
    parent: Account | None = None,
    description: str = "",
    allow_posting: bool = True,
    is_control_account: bool = False,
    sort_order: int = 0,
) -> Account:
    account = Account(
        company=company,
        code=code,
        name=name,
        account_type=account_type,
        parent=parent,
        description=description,
        allow_posting=allow_posting,
        is_control_account=is_control_account,
        sort_order=sort_order,
    )
    _save(account)
    return account


@transaction.atomic
@requires_company_module("finance_core", argument="account")
def update_account(*, account: Account, **fields: Any) -> Account:
    if account.journal_lines.filter(journal_entry__status=JournalStatus.POSTED).exists():
        protected = {"company", "code", "account_type", "parent", "allow_posting"}
        if protected & fields.keys():
            raise PostedRecordImmutableError("Posted account configuration cannot be changed.")
    for name, value in fields.items():
        setattr(account, name, value)
    _save(account)
    return account


@transaction.atomic
@requires_company_module("finance_core", argument="company")
def create_fiscal_year(
    *, company: Company, name: str, start_date: date, end_date: date
) -> FiscalYear:
    if (
        FiscalYear.objects.filter(company=company)
        .filter(Q(start_date__lte=end_date, end_date__gte=start_date))
        .exists()
    ):
        raise FinanceValidationError({"dates": ["Fiscal years cannot overlap."]})
    item = FiscalYear(company=company, name=name.strip(), start_date=start_date, end_date=end_date)
    _save(item)
    return item


@transaction.atomic
@requires_company_module("finance_core", argument="fiscal_year")
def create_accounting_period(
    *, fiscal_year: FiscalYear, name: str, start_date: date, end_date: date
) -> AccountingPeriod:
    if start_date < fiscal_year.start_date or end_date > fiscal_year.end_date:
        raise FinanceValidationError({"dates": ["Period must fall within fiscal year."]})
    if (
        AccountingPeriod.objects.filter(company=fiscal_year.company)
        .filter(Q(start_date__lte=end_date, end_date__gte=start_date))
        .exists()
    ):
        raise FinanceValidationError({"dates": ["Accounting periods cannot overlap."]})
    item = AccountingPeriod(
        fiscal_year=fiscal_year,
        company=fiscal_year.company,
        name=name.strip(),
        start_date=start_date,
        end_date=end_date,
    )
    _save(item)
    return item


@transaction.atomic
@requires_company_module("finance_core", argument="company")
def create_cost_center(
    *,
    company: Company,
    code: str,
    name: str,
    branch: Branch | None = None,
    department: Department | None = None,
    description: str = "",
) -> CostCenter:
    item = CostCenter(
        company=company,
        code=code,
        name=name,
        branch=branch,
        department=department,
        description=description,
    )
    _save(item)
    return item


def _event(
    *,
    company: Company,
    event_type: str,
    actor: User,
    journal: JournalEntry | None = None,
    period: AccountingPeriod | None = None,
    reason: str = "",
) -> None:
    FinanceEvent.objects.create(
        company=company,
        event_type=event_type,
        actor=actor,
        journal_entry=journal,
        accounting_period=period,
        reason=reason.strip(),
    )


@transaction.atomic
def next_document_number(*, company: Company, prefix: str, year: int) -> str:
    normalized = normalize_document_prefix(prefix)
    validate_document_prefix(normalized)
    # A new prefix/year has no sequence row to lock yet. Serializing on the
    # owning Company makes first allocation collision-safe while preserving
    # independent allocation between Companies.
    Company.objects.select_for_update().only("pk").get(pk=company.pk)
    sequence, _ = DocumentSequence.objects.select_for_update().get_or_create(
        company=company, prefix=normalized, year=year
    )
    sequence.last_number += 1
    sequence.save(update_fields=["last_number"])
    return f"{normalized}-{year}-{sequence.last_number:06d}"


COMPANY_DOCUMENT_PREFIX_FIELDS = {
    "invoice": "invoice_number_prefix",
    "receipt": "receipt_number_prefix",
    "credit_note": "credit_note_number_prefix",
    "debit_note": "debit_note_number_prefix",
}


def next_company_document_number(*, company: Company, family: str, year: int) -> str:
    try:
        field = COMPANY_DOCUMENT_PREFIX_FIELDS[family]
    except KeyError as exc:
        raise FinanceValidationError({"family": ["Unsupported Company document family."]}) from exc
    return next_document_number(company=company, prefix=getattr(company, field), year=year)


def _validate_period(
    period: AccountingPeriod, entry_date: date, *, allow_soft_closed: bool = False
) -> None:
    if not period.start_date <= entry_date <= period.end_date:
        raise FinanceValidationError({"entry_date": ["Entry date is outside accounting period."]})
    if period.status == PeriodStatus.CLOSED or (
        period.status == PeriodStatus.SOFT_CLOSED and not allow_soft_closed
    ):
        raise ClosedPeriodError("The accounting period does not permit posting.")


@transaction.atomic
@requires_company_module("finance_core", argument="company")
def create_journal(
    *,
    company: Company,
    fiscal_year: FiscalYear,
    accounting_period: AccountingPeriod,
    entry_date: date,
    description: str,
    created_by: User,
    reference: str = "",
    source_type: str = "MANUAL",
    source_id: Any = None,
    lines: list[dict[str, Any]],
) -> JournalEntry:
    if (
        fiscal_year.company_id != company.id
        or accounting_period.company_id != company.id
        or accounting_period.fiscal_year_id != fiscal_year.id
    ):
        raise FinanceValidationError(
            {"company": ["Fiscal year and period must match journal company."]}
        )
    _validate_period(accounting_period, entry_date)
    number = next_document_number(company=company, prefix="JV", year=entry_date.year)
    journal = JournalEntry(
        company=company,
        fiscal_year=fiscal_year,
        accounting_period=accounting_period,
        journal_number=number,
        entry_date=entry_date,
        reference=reference.strip(),
        description=description.strip(),
        source_type=source_type,
        source_id=source_id,
        created_by=created_by,
    )
    _save(journal)
    for payload in lines:
        line = JournalLine(
            journal_entry=journal,
            account=payload["account"],
            cost_center=payload.get("cost_center"),
            description=payload.get("description", "").strip(),
            debit=money(payload.get("debit", ZERO)),
            credit=money(payload.get("credit", ZERO)),
        )
        _save(line)
    _event(company=company, event_type=FinanceEventType.CREATED, actor=created_by, journal=journal)
    return journal


def validate_balanced(journal: JournalEntry) -> None:
    lines = list(journal.lines.all())
    if len(lines) < 2:
        raise FinanceValidationError({"lines": ["A journal requires at least two lines."]})
    debit = sum((line.debit for line in lines), ZERO)
    credit = sum((line.credit for line in lines), ZERO)
    if debit != credit:
        raise FinanceValidationError({"lines": ["Total debit must equal total credit."]})


@transaction.atomic
@requires_company_module("finance_core", argument="journal")
def submit_journal(*, journal: JournalEntry, actor: User) -> JournalEntry:
    journal = JournalEntry.objects.select_for_update().get(pk=journal.pk)
    if journal.status != JournalStatus.DRAFT:
        raise InvalidFinanceTransitionError("Only draft journals can be submitted.")
    validate_balanced(journal)
    journal.status = JournalStatus.SUBMITTED
    journal.submitted_by = actor
    journal.submitted_at = timezone.now()
    journal.save(update_fields=["status", "submitted_by", "submitted_at", "updated_at"])
    _event(
        company=journal.company, event_type=FinanceEventType.SUBMITTED, actor=actor, journal=journal
    )
    return journal


@transaction.atomic
@requires_company_module("finance_core", argument="journal")
def approve_journal(*, journal: JournalEntry, actor: User) -> JournalEntry:
    journal = JournalEntry.objects.select_for_update().get(pk=journal.pk)
    if journal.status != JournalStatus.SUBMITTED:
        raise InvalidFinanceTransitionError("Only submitted journals can be approved.")
    if not actor.is_superuser and journal.created_by_id == actor.id:
        raise MakerCheckerError("Journal maker cannot approve their own journal.")
    validate_balanced(journal)
    journal.status = JournalStatus.APPROVED
    journal.approved_by = actor
    journal.approved_at = timezone.now()
    journal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _event(
        company=journal.company, event_type=FinanceEventType.APPROVED, actor=actor, journal=journal
    )
    return journal


@transaction.atomic
@requires_company_module("finance_core", argument="journal")
def reject_journal(*, journal: JournalEntry, actor: User, reason: str) -> JournalEntry:
    journal = JournalEntry.objects.select_for_update().get(pk=journal.pk)
    if journal.status != JournalStatus.SUBMITTED or not reason.strip():
        raise InvalidFinanceTransitionError("Submitted journal and rejection reason are required.")
    journal.status = JournalStatus.REJECTED
    journal.save(update_fields=["status", "updated_at"])
    _event(
        company=journal.company,
        event_type=FinanceEventType.REJECTED,
        actor=actor,
        journal=journal,
        reason=reason,
    )
    return journal


@transaction.atomic
@requires_company_module("finance_core", argument="journal")
def post_journal(
    *, journal: JournalEntry, actor: User, allow_soft_closed: bool = False
) -> JournalEntry:
    journal = (
        JournalEntry.objects.select_for_update()
        .select_related("accounting_period")
        .get(pk=journal.pk)
    )
    if journal.status == JournalStatus.POSTED:
        return journal
    if journal.status != JournalStatus.APPROVED:
        raise InvalidFinanceTransitionError("Only approved journals can be posted.")
    if not actor.is_superuser and journal.created_by_id == actor.id:
        raise MakerCheckerError("Journal maker cannot post their own journal.")
    _validate_period(
        journal.accounting_period, journal.entry_date, allow_soft_closed=allow_soft_closed
    )
    validate_balanced(journal)
    journal.status = JournalStatus.POSTED
    journal.posted_by = actor
    journal.posted_at = timezone.now()
    journal.save(update_fields=["status", "posted_by", "posted_at", "updated_at"])
    _event(
        company=journal.company, event_type=FinanceEventType.POSTED, actor=actor, journal=journal
    )
    record_audit_event(
        action="JOURNAL_POSTED",
        category=AuditCategory.FINANCE,
        severity=AuditSeverity.HIGH,
        summary="Journal entry posted.",
        actor_user=actor,
        company=journal.company,
        source_object=journal,
        object_reference=journal.journal_number,
    )
    return journal


@transaction.atomic
@requires_company_module("finance_core", argument="journal")
def reverse_journal(
    *, journal: JournalEntry, actor: User, reversal_date: date, reason: str
) -> JournalEntry:
    original = (
        JournalEntry.objects.select_for_update()
        .prefetch_related("lines__account", "lines__cost_center")
        .get(pk=journal.pk)
    )
    if original.status != JournalStatus.POSTED or original.reversed_by_entry_id:
        raise InvalidFinanceTransitionError("Only an unreversed posted journal can be reversed.")
    if not actor.is_superuser and original.created_by_id == actor.id:
        raise MakerCheckerError("Original journal maker cannot authorize its reversal.")
    period = AccountingPeriod.objects.get(
        company=original.company, start_date__lte=reversal_date, end_date__gte=reversal_date
    )
    reversal = create_journal(
        company=original.company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=reversal_date,
        description=f"Reversal of {original.journal_number}: {reason}",
        created_by=original.created_by,
        reference=original.journal_number,
        source_type="REVERSAL",
        source_id=original.id,
        lines=[
            {
                "account": line.account,
                "cost_center": line.cost_center,
                "description": line.description,
                "debit": line.credit,
                "credit": line.debit,
            }
            for line in original.lines.all()
        ],
    )
    reversal = submit_journal(journal=reversal, actor=actor)
    reversal.status = JournalStatus.APPROVED
    reversal.approved_by = actor
    reversal.approved_at = timezone.now()
    reversal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    reversal = post_journal(journal=reversal, actor=actor)
    original.status = JournalStatus.REVERSED
    original.reversed_by_entry = reversal
    original.save(update_fields=["status", "reversed_by_entry", "updated_at"])
    _event(
        company=original.company,
        event_type=FinanceEventType.REVERSED,
        actor=actor,
        journal=original,
        reason=reason,
    )
    record_audit_event(
        action="JOURNAL_REVERSED",
        category=AuditCategory.FINANCE,
        severity=AuditSeverity.HIGH,
        summary="Journal entry reversed.",
        actor_user=actor,
        company=original.company,
        source_object=original,
        object_reference=original.journal_number,
        metadata_safe={"reversal_journal_id": str(reversal.id)},
    )
    return reversal


def _change_period(
    *, period: AccountingPeriod, actor: User, status: str, event_type: str, reason: str = ""
) -> AccountingPeriod:
    with transaction.atomic():
        locked = AccountingPeriod.objects.select_for_update().get(pk=period.pk)
        locked.status = status
        locked.save(update_fields=["status", "updated_at"])
        _event(
            company=locked.company, event_type=event_type, actor=actor, period=locked, reason=reason
        )
        return locked


@requires_company_module("finance_core", argument="period")
def soft_close_accounting_period(*, period: AccountingPeriod, actor: User) -> AccountingPeriod:
    return _change_period(
        period=period,
        actor=actor,
        status=PeriodStatus.SOFT_CLOSED,
        event_type=FinanceEventType.PERIOD_SOFT_CLOSED,
    )


@requires_company_module("finance_core", argument="period")
def close_accounting_period(*, period: AccountingPeriod, actor: User) -> AccountingPeriod:
    if period.journal_entries.filter(
        status__in=[JournalStatus.SUBMITTED, JournalStatus.APPROVED]
    ).exists():
        raise FinanceValidationError(
            {"period": ["Unposted journals must be resolved before close."]}
        )
    return _change_period(
        period=period,
        actor=actor,
        status=PeriodStatus.CLOSED,
        event_type=FinanceEventType.PERIOD_CLOSED,
    )


@requires_company_module("finance_core", argument="period")
def reopen_accounting_period(
    *, period: AccountingPeriod, actor: User, reason: str
) -> AccountingPeriod:
    if not reason.strip():
        raise FinanceValidationError({"reason": ["Reopening reason is required."]})
    return _change_period(
        period=period,
        actor=actor,
        status=PeriodStatus.OPEN,
        event_type=FinanceEventType.PERIOD_REOPENED,
        reason=reason,
    )
