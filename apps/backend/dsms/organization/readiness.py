from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import UUID

from django.core.exceptions import ValidationError

from dsms.analytics.models import AnalyticsPrivacyPolicy
from dsms.finance.enums import AccountType, PeriodStatus
from dsms.finance.models import Account, AccountingPeriod, FiscalYear
from dsms.finance.operations_models import BankAccount, CashAccount
from dsms.finance.payment_models import PaymentAccountingProfile, PaymentProviderConfiguration
from dsms.identity.models import UserRoleAssignment
from dsms.organization.business_defaults import (
    DOCUMENT_PREFIX_PATTERN,
    company_local_date,
    normalize_currency_code,
    normalize_document_prefix,
    validate_currency_code,
    validate_timezone_name,
)
from dsms.organization.models import Company

TENANT_ADMIN_ROLE_CODES = ("ORGANIZATION_ADMIN", "ACCESS_ADMIN")


class ReadinessSeverity:
    BLOCKER = "BLOCKER"
    WARNING = "WARNING"


class ReadinessStatus:
    READY = "READY"
    ACTION_REQUIRED = "ACTION_REQUIRED"
    CONFIGURED = "CONFIGURED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class ReadinessCode:
    MISSING_TENANT_ADMINISTRATOR = "MISSING_TENANT_ADMINISTRATOR"
    INCOMPLETE_BUSINESS_DEFAULTS = "INCOMPLETE_BUSINESS_DEFAULTS"
    MISSING_CHART_OF_ACCOUNTS = "MISSING_CHART_OF_ACCOUNTS"
    INCOMPLETE_CHART_OF_ACCOUNTS = "INCOMPLETE_CHART_OF_ACCOUNTS"
    MISSING_FISCAL_YEAR = "MISSING_FISCAL_YEAR"
    NO_OPEN_ACCOUNTING_PERIOD = "NO_OPEN_ACCOUNTING_PERIOD"
    MISSING_REVENUE_ACCOUNT = "MISSING_REVENUE_ACCOUNT"
    MISSING_RECEIVABLE_ACCOUNT = "MISSING_RECEIVABLE_ACCOUNT"
    MISSING_SETTLEMENT_ACCOUNT = "MISSING_SETTLEMENT_ACCOUNT"
    MISSING_EXPENSE_ACCOUNT = "MISSING_EXPENSE_ACCOUNT"
    MISSING_PAYABLE_CONTROL_ACCOUNT = "MISSING_PAYABLE_CONTROL_ACCOUNT"
    MISSING_DISBURSEMENT_ACCOUNT = "MISSING_DISBURSEMENT_ACCOUNT"
    MISSING_PAYMENT_ACCOUNTING_PROFILE = "MISSING_PAYMENT_ACCOUNTING_PROFILE"
    INVALID_PAYMENT_ACCOUNTING_PROFILE = "INVALID_PAYMENT_ACCOUNTING_PROFILE"
    NO_PAYMENT_PROVIDER_CONFIGURED = "NO_PAYMENT_PROVIDER_CONFIGURED"
    ANALYTICS_PRIVACY_NOT_CONFIGURED = "ANALYTICS_PRIVACY_NOT_CONFIGURED"


@dataclass(frozen=True)
class ReadinessItem:
    code: str
    category: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CategoryCheck:
    status: str
    summary: str
    items: list[ReadinessItem] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "items": [item.as_dict() for item in self.items],
        }


@dataclass(frozen=True)
class CompanyOperationalReadiness:
    company_id: UUID
    company_code: str
    status: str
    blocker_count: int
    warning_count: int
    blockers: list[ReadinessItem]
    warnings: list[ReadinessItem]
    checks: dict[str, CategoryCheck]

    def as_dict(self) -> dict[str, Any]:
        return {
            "company_id": str(self.company_id),
            "company_code": self.company_code,
            "status": self.status,
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "blockers": [b.as_dict() for b in self.blockers],
            "warnings": [w.as_dict() for w in self.warnings],
            "checks": {key: check.as_dict() for key, check in self.checks.items()},
        }


def _check_tenant_administration(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    items: list[ReadinessItem] = []
    has_admin = (
        UserRoleAssignment.objects.filter(
            company=company,
            is_active=True,
            user__is_active=True,
            role__is_active=True,
        )
        .filter(role__code__in=TENANT_ADMIN_ROLE_CODES)
        .exists()
    )

    if not has_admin:
        has_admin = UserRoleAssignment.objects.filter(
            company=company,
            is_active=True,
            user__is_active=True,
            role__is_active=True,
            role__permissions__codename="change_company",
            role__permissions__content_type__app_label="organization",
        ).exists()

    if not has_admin:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_TENANT_ADMINISTRATOR,
                category="tenant_administration",
                severity=ReadinessSeverity.BLOCKER,
                message="No active tenant administrator is assigned to this company.",
            )
        )
        return (
            ReadinessStatus.ACTION_REQUIRED,
            "Tenant administrator role assignment is required.",
            items,
        )

    return ReadinessStatus.READY, "Active tenant administrator assigned.", items


def _check_numbering_and_defaults(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    items: list[ReadinessItem] = []
    issues: list[str] = []

    try:
        validate_timezone_name(company.timezone)
    except ValidationError:
        issues.append("timezone")

    try:
        validate_currency_code(normalize_currency_code(company.default_currency))
    except ValidationError:
        issues.append("default_currency")

    if len(company.country_code.strip()) != 2:
        issues.append("country_code")

    for prefix_name in (
        "invoice_number_prefix",
        "receipt_number_prefix",
        "credit_note_number_prefix",
        "debit_note_number_prefix",
    ):
        raw_val = getattr(company, prefix_name, "")
        normalized = normalize_document_prefix(raw_val)
        if not DOCUMENT_PREFIX_PATTERN.fullmatch(normalized):
            issues.append(prefix_name)

    if issues:
        items.append(
            ReadinessItem(
                code=ReadinessCode.INCOMPLETE_BUSINESS_DEFAULTS,
                category="numbering_and_defaults",
                severity=ReadinessSeverity.BLOCKER,
                message="Core business defaults or document prefixes are incomplete.",
                details={"incomplete_fields": issues},
            )
        )
        return (
            ReadinessStatus.ACTION_REQUIRED,
            "Core business defaults or document prefixes require configuration.",
            items,
        )

    return (
        ReadinessStatus.READY,
        "Business defaults and document sequence numbering configured.",
        items,
    )


def _check_general_ledger(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    items: list[ReadinessItem] = []
    accounts = Account.objects.filter(company=company, is_active=True, allow_posting=True)
    account_types = set(accounts.values_list("account_type", flat=True))

    if not accounts.exists():
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_CHART_OF_ACCOUNTS,
                category="general_ledger",
                severity=ReadinessSeverity.BLOCKER,
                message="No active posting accounts exist in the chart of accounts.",
            )
        )
    else:
        required_core = {
            str(AccountType.ASSET),
            str(AccountType.LIABILITY),
            str(AccountType.EQUITY),
        }
        missing_core = required_core - set(account_types)
        if missing_core:
            items.append(
                ReadinessItem(
                    code=ReadinessCode.INCOMPLETE_CHART_OF_ACCOUNTS,
                    category="general_ledger",
                    severity=ReadinessSeverity.BLOCKER,
                    message=(
                        "Chart of accounts is missing core balance sheet account types: "
                        f"{', '.join(sorted(missing_core))}."
                    ),
                    details={"missing_types": sorted(missing_core)},
                )
            )

    has_fiscal_year = FiscalYear.objects.filter(company=company, is_active=True).exists()
    if not has_fiscal_year:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_FISCAL_YEAR,
                category="general_ledger",
                severity=ReadinessSeverity.BLOCKER,
                message="No active fiscal year is configured.",
            )
        )

    today = company_local_date(company)
    has_open_period = AccountingPeriod.objects.filter(
        company=company,
        status=PeriodStatus.OPEN,
        start_date__lte=today,
        end_date__gte=today,
    ).exists()

    if not has_open_period:
        items.append(
            ReadinessItem(
                code=ReadinessCode.NO_OPEN_ACCOUNTING_PERIOD,
                category="general_ledger",
                severity=ReadinessSeverity.BLOCKER,
                message="No open accounting period covers current financial transactions.",
                details={"as_of_date": str(today)},
            )
        )

    if items:
        return (
            ReadinessStatus.ACTION_REQUIRED,
            "Chart of accounts or open accounting period required for ledger postings.",
            items,
        )

    return (
        ReadinessStatus.READY,
        "Chart of accounts and open fiscal period are ready for journal entries.",
        items,
    )


def _check_billing_and_receivables(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    items: list[ReadinessItem] = []

    has_revenue = Account.objects.filter(
        company=company, account_type=AccountType.REVENUE, is_active=True, allow_posting=True
    ).exists()
    if not has_revenue:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_REVENUE_ACCOUNT,
                category="billing_and_receivables",
                severity=ReadinessSeverity.BLOCKER,
                message="No active revenue account is configured for client invoicing.",
            )
        )

    has_receivable = Account.objects.filter(
        company=company,
        account_type=AccountType.ASSET,
        is_active=True,
        allow_posting=True,
        is_control_account=True,
    ).exists()
    if not has_receivable:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_RECEIVABLE_ACCOUNT,
                category="billing_and_receivables",
                severity=ReadinessSeverity.BLOCKER,
                message="No active posting asset control account is available for receivables.",
            )
        )

    has_settlement = (
        BankAccount.objects.filter(company=company, is_active=True).exists()
        or CashAccount.objects.filter(company=company, is_active=True).exists()
    )
    if not has_settlement:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_SETTLEMENT_ACCOUNT,
                category="billing_and_receivables",
                severity=ReadinessSeverity.WARNING,
                message="No active bank or cash account is configured to receive payments.",
            )
        )

    blockers = [item for item in items if item.severity == ReadinessSeverity.BLOCKER]
    if blockers:
        return (
            ReadinessStatus.ACTION_REQUIRED,
            "Invoicing prerequisites require active revenue and receivable accounts.",
            items,
        )

    return ReadinessStatus.READY, "Invoicing and receivables controls configured.", items


def _check_accounts_payable(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    items: list[ReadinessItem] = []

    has_expense = Account.objects.filter(
        company=company, account_type=AccountType.EXPENSE, is_active=True, allow_posting=True
    ).exists()
    if not has_expense:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_EXPENSE_ACCOUNT,
                category="accounts_payable",
                severity=ReadinessSeverity.BLOCKER,
                message="No active expense account is configured for vendor bills or expenses.",
            )
        )

    has_payable = Account.objects.filter(
        company=company,
        account_type=AccountType.LIABILITY,
        is_active=True,
        allow_posting=True,
        is_control_account=True,
    ).exists()
    if not has_payable:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_PAYABLE_CONTROL_ACCOUNT,
                category="accounts_payable",
                severity=ReadinessSeverity.BLOCKER,
                message="No active posting liability control account is available for payables.",
            )
        )

    has_disbursement = (
        BankAccount.objects.filter(company=company, is_active=True).exists()
        or CashAccount.objects.filter(company=company, is_active=True).exists()
    )
    if not has_disbursement:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_DISBURSEMENT_ACCOUNT,
                category="accounts_payable",
                severity=ReadinessSeverity.WARNING,
                message="No active bank or cash account is configured for vendor disbursements.",
            )
        )

    blockers = [item for item in items if item.severity == ReadinessSeverity.BLOCKER]
    if blockers:
        return (
            ReadinessStatus.ACTION_REQUIRED,
            "Accounts payable prerequisites require active expense and payable accounts.",
            items,
        )

    return ReadinessStatus.READY, "Vendor billing and payable controls configured.", items


def _check_payment_disbursements(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    items: list[ReadinessItem] = []
    profile = (
        PaymentAccountingProfile.objects.filter(company=company, is_active=True)
        .select_related(
            "payroll_payable_account",
            "vendor_payable_account",
            "gateway_clearing_account",
            "bank_account",
            "provider_fee_account",
        )
        .first()
    )

    if profile is None:
        items.append(
            ReadinessItem(
                code=ReadinessCode.MISSING_PAYMENT_ACCOUNTING_PROFILE,
                category="payment_disbursements",
                severity=ReadinessSeverity.WARNING,
                message=(
                    "Payment accounting profile is not configured; "
                    "automated batch disbursement is disabled."
                ),
            )
        )
        return (
            ReadinessStatus.NOT_CONFIGURED,
            "Payment accounting profile is not configured for automated batches.",
            items,
        )

    linked_accounts = [
        profile.payroll_payable_account,
        profile.vendor_payable_account,
        profile.gateway_clearing_account,
        profile.bank_account,
        profile.provider_fee_account,
    ]
    invalid_accounts: list[str] = []
    for acc in linked_accounts:
        if acc.company_id != company.id or not acc.is_active or not acc.allow_posting:
            invalid_accounts.append(acc.code)

    if invalid_accounts:
        items.append(
            ReadinessItem(
                code=ReadinessCode.INVALID_PAYMENT_ACCOUNTING_PROFILE,
                category="payment_disbursements",
                severity=ReadinessSeverity.BLOCKER,
                message=(
                    "Payment accounting profile references invalid, inactive, "
                    "or cross-company accounts."
                ),
                details={"invalid_accounts": invalid_accounts},
            )
        )
        return (
            ReadinessStatus.ACTION_REQUIRED,
            "Payment accounting profile has invalid account linkages.",
            items,
        )

    return (
        ReadinessStatus.READY,
        "Payment accounting profile configured for batch disbursement.",
        items,
    )


def _check_external_integrations(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    items: list[ReadinessItem] = []
    has_provider = PaymentProviderConfiguration.objects.filter(
        company=company, is_active=True
    ).exists()

    if not has_provider:
        items.append(
            ReadinessItem(
                code=ReadinessCode.NO_PAYMENT_PROVIDER_CONFIGURED,
                category="external_integrations",
                severity=ReadinessSeverity.WARNING,
                message=(
                    "No payment provider is configured; manual payment entry remains operational."
                ),
            )
        )
        return (
            ReadinessStatus.NOT_CONFIGURED,
            "External payment providers not configured.",
            items,
        )

    return ReadinessStatus.CONFIGURED, "External payment provider integration active.", items


def _check_analytics_and_privacy(company: Company) -> tuple[str, str, list[ReadinessItem]]:
    has_policy = AnalyticsPrivacyPolicy.objects.filter(company=company, is_active=True).exists()
    if has_policy:
        return ReadinessStatus.CONFIGURED, "Analytics privacy policy configured.", []

    item = ReadinessItem(
        code=ReadinessCode.ANALYTICS_PRIVACY_NOT_CONFIGURED,
        category="analytics_and_privacy",
        severity=ReadinessSeverity.WARNING,
        message=(
            "No analytics privacy policy is configured; analytics reporting remains "
            "tenant configuration."
        ),
    )
    return (
        ReadinessStatus.NOT_CONFIGURED,
        "Analytics privacy policy is not configured.",
        [item],
    )


def get_company_operational_readiness(company: Company) -> CompanyOperationalReadiness:
    """Deterministically derive the current operational readiness of a Company."""
    checks_raw = {
        "tenant_administration": _check_tenant_administration(company),
        "numbering_and_defaults": _check_numbering_and_defaults(company),
        "general_ledger": _check_general_ledger(company),
        "billing_and_receivables": _check_billing_and_receivables(company),
        "accounts_payable": _check_accounts_payable(company),
        "payment_disbursements": _check_payment_disbursements(company),
        "external_integrations": _check_external_integrations(company),
        "analytics_and_privacy": _check_analytics_and_privacy(company),
    }

    all_blockers: list[ReadinessItem] = []
    all_warnings: list[ReadinessItem] = []
    checks: dict[str, CategoryCheck] = {}

    for name, (status, summary, items) in checks_raw.items():
        checks[name] = CategoryCheck(status=status, summary=summary, items=items)
        for item in items:
            if item.severity == ReadinessSeverity.BLOCKER:
                all_blockers.append(item)
            elif item.severity == ReadinessSeverity.WARNING:
                all_warnings.append(item)

    overall_status = (
        ReadinessStatus.READY if len(all_blockers) == 0 else ReadinessStatus.ACTION_REQUIRED
    )

    return CompanyOperationalReadiness(
        company_id=company.pk,
        company_code=company.code,
        status=overall_status,
        blocker_count=len(all_blockers),
        warning_count=len(all_warnings),
        blockers=all_blockers,
        warnings=all_warnings,
        checks=checks,
    )
