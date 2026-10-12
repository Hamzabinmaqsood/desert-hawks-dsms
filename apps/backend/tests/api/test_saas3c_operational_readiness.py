from __future__ import annotations

from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.finance.enums import AccountType, PeriodStatus
from dsms.finance.models import Account, AccountingPeriod, FiscalYear
from dsms.finance.operations_models import BankAccount, CashAccount
from dsms.finance.payment_models import (
    PaymentAccountingProfile,
    PaymentProviderConfiguration,
    ProviderType,
)
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User
from dsms.identity.platform_access import (
    PLATFORM_CAPABILITIES,
    VIEW_PLATFORM_TENANT_DIRECTORY,
)
from dsms.organization.business_defaults import company_local_date
from dsms.organization.models import Company
from dsms.organization.provisioning import (
    InitialAdminData,
    ProvisionCompanyRequest,
    ProvisionedCompanyData,
    provision_company,
)
from dsms.organization.readiness import (
    ReadinessCode,
    ReadinessSeverity,
    ReadinessStatus,
    get_company_operational_readiness,
)
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db

CONTEXT_URL = "/api/v1/auth/company-context/"
READINESS_URL = "/api/v1/auth/company-operational-readiness/"
DIRECTORY_URL = reverse("platform-tenant-directory")


def authenticated(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def permission(code: str) -> Permission:
    app_label, codename = code.split(".", maxsplit=1)
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def grant_platform(user: User, *capabilities: str) -> None:
    user.user_permissions.add(*(permission(capability) for capability in capabilities))


def tenant_admin_roles() -> tuple[Role, Role]:
    organization_admin = RoleFactory.create(code="ORGANIZATION_ADMIN", is_system=True)
    organization_admin.permissions.add(
        *Permission.objects.filter(
            content_type__app_label="organization",
            codename__in=("view_company", "add_company", "change_company"),
        )
    )
    access_admin = RoleFactory.create(code="ACCESS_ADMIN", is_system=True)
    return organization_admin, access_admin


def assign_tenant_admin(user: User, company: Company, roles: tuple[Role, Role]) -> None:
    for role in roles:
        UserRoleAssignmentFactory.create(
            user=user,
            role=role,
            scope_type=AccessScopeType.COMPANY,
            company=company,
        )


def select_context(client: APIClient, company: Company) -> None:
    response = client.put(CONTEXT_URL, {"company_id": str(company.id)}, format="json")
    assert response.status_code == 200, response.data


def setup_complete_accounting(company: Company) -> dict[str, Any]:
    today = company_local_date(company)
    year = FiscalYear.objects.create(
        company=company,
        name=f"FY {today.year}",
        start_date=date(today.year, 1, 1),
        end_date=date(today.year, 12, 31),
    )
    period = AccountingPeriod.objects.create(
        company=company,
        fiscal_year=year,
        name=f"Period {today.month}-{today.year}",
        start_date=date(today.year, today.month, 1),
        end_date=date(today.year, 12, 31),
        status=PeriodStatus.OPEN,
    )
    accounts = {
        "asset": Account.objects.create(
            company=company,
            code="1000",
            name="Operating Cash",
            account_type=AccountType.ASSET,
            allow_posting=True,
        ),
        "receivable": Account.objects.create(
            company=company,
            code="1100",
            name="Trade Receivables",
            account_type=AccountType.ASSET,
            allow_posting=True,
            is_control_account=True,
        ),
        "liability": Account.objects.create(
            company=company,
            code="2000",
            name="Trade Payables",
            account_type=AccountType.LIABILITY,
            allow_posting=True,
            is_control_account=True,
        ),
        "payroll_payable": Account.objects.create(
            company=company,
            code="2100",
            name="Payroll Payable",
            account_type=AccountType.LIABILITY,
            allow_posting=True,
            is_control_account=True,
        ),
        "clearing": Account.objects.create(
            company=company,
            code="2200",
            name="Gateway Clearing",
            account_type=AccountType.LIABILITY,
            allow_posting=True,
            is_control_account=True,
        ),
        "equity": Account.objects.create(
            company=company,
            code="3000",
            name="Shareholder Equity",
            account_type=AccountType.EQUITY,
            allow_posting=True,
        ),
        "revenue": Account.objects.create(
            company=company,
            code="4000",
            name="Security Services Revenue",
            account_type=AccountType.REVENUE,
            allow_posting=True,
        ),
        "expense": Account.objects.create(
            company=company,
            code="5000",
            name="Operating Expense",
            account_type=AccountType.EXPENSE,
            allow_posting=True,
        ),
        "fee": Account.objects.create(
            company=company,
            code="5100",
            name="Provider Fees",
            account_type=AccountType.EXPENSE,
            allow_posting=True,
        ),
    }
    bank = BankAccount.objects.create(
        company=company,
        name="Main Treasury",
        account_number_encrypted="encrypted-account-number",
        iban_encrypted="encrypted-iban",
        bank_name="National Bank",
        currency=company.default_currency,
        ledger_account=accounts["asset"],
    )
    CashAccount.objects.create(
        company=company,
        name="Branch Petty Cash",
        ledger_account=accounts["asset"],
    )
    payment_profile = PaymentAccountingProfile.objects.create(
        company=company,
        payroll_payable_account=accounts["payroll_payable"],
        vendor_payable_account=accounts["liability"],
        gateway_clearing_account=accounts["clearing"],
        bank_account=accounts["asset"],
        provider_fee_account=accounts["fee"],
    )
    provider_config = PaymentProviderConfiguration.objects.create(
        company=company,
        code="MANUAL-BANK",
        provider_type=ProviderType.MANUAL,
        display_name="Manual bank settlement",
        currency=company.default_currency,
        adapter_code="manual",
        created_by=UserFactory.create(),
    )
    return {
        "fiscal_year": year,
        "period": period,
        "accounts": accounts,
        "bank_account": bank,
        "payment_profile": payment_profile,
        "provider_config": provider_config,
    }


def test_provisioned_minimal_company_readiness() -> None:
    tenant_admin_roles()
    operator = UserFactory.create(is_staff=False)
    grant_platform(operator, *PLATFORM_CAPABILITIES)

    result = provision_company(
        actor=operator,
        idempotency_key=uuid4(),
        request=ProvisionCompanyRequest(
            company=ProvisionedCompanyData(
                code="NOVO",
                legal_name="Novo Security Services Limited",
                country_code="PK",
                timezone="Asia/Karachi",
                default_currency="PKR",
            ),
            initial_admin=InitialAdminData(email="admin@novo.example"),
        ),
    )
    assert result.provisioning_request.company is not None
    company = result.provisioning_request.company
    admin = result.provisioning_request.initial_admin
    assert admin is not None

    client = authenticated(admin)
    select_context(client, company)

    response = client.get(READINESS_URL)
    assert response.status_code == 200
    data = response.data

    assert data["company_code"] == "NOVO"
    assert data["status"] == ReadinessStatus.ACTION_REQUIRED
    assert data["blocker_count"] >= 6
    assert data["warning_count"] >= 4

    checks = data["checks"]
    assert checks["tenant_administration"]["status"] == ReadinessStatus.READY
    assert checks["numbering_and_defaults"]["status"] == ReadinessStatus.READY
    assert checks["analytics_and_privacy"]["status"] == ReadinessStatus.NOT_CONFIGURED
    assert checks["general_ledger"]["status"] == ReadinessStatus.ACTION_REQUIRED
    assert checks["billing_and_receivables"]["status"] == ReadinessStatus.ACTION_REQUIRED
    assert checks["accounts_payable"]["status"] == ReadinessStatus.ACTION_REQUIRED
    assert checks["payment_disbursements"]["status"] == ReadinessStatus.NOT_CONFIGURED
    assert checks["external_integrations"]["status"] == ReadinessStatus.NOT_CONFIGURED

    blocker_codes = {b["code"] for b in data["blockers"]}
    assert ReadinessCode.MISSING_CHART_OF_ACCOUNTS in blocker_codes
    assert ReadinessCode.MISSING_FISCAL_YEAR in blocker_codes
    assert ReadinessCode.NO_OPEN_ACCOUNTING_PERIOD in blocker_codes
    assert ReadinessCode.MISSING_REVENUE_ACCOUNT in blocker_codes
    assert ReadinessCode.MISSING_RECEIVABLE_ACCOUNT in blocker_codes
    assert ReadinessCode.MISSING_EXPENSE_ACCOUNT in blocker_codes
    assert ReadinessCode.MISSING_PAYABLE_CONTROL_ACCOUNT in blocker_codes

    assert not Account.objects.filter(company=company).exists()
    assert not BankAccount.objects.filter(company=company).exists()
    assert not CashAccount.objects.filter(company=company).exists()
    assert not PaymentAccountingProfile.objects.filter(company=company).exists()

    from dsms.organization.api.provisioning_serializers import (
        TenantProvisioningResultSerializer,
    )

    prov_serializer = TenantProvisioningResultSerializer(result.provisioning_request)
    assert (
        prov_serializer.data["operational_readiness"]["status"] == ReadinessStatus.ACTION_REQUIRED
    )
    assert prov_serializer.data["operational_readiness"]["blocker_count"] == data["blocker_count"]


def test_legacy_company_readiness() -> None:
    roles = tenant_admin_roles()
    company = CompanyFactory.create(code="LEGACY", country_code="PK", timezone="Asia/Karachi")
    admin = UserFactory.create()
    assign_tenant_admin(admin, company, roles)

    setup_complete_accounting(company)

    client = authenticated(admin)
    select_context(client, company)

    response = client.get(READINESS_URL)
    assert response.status_code == 200
    data = response.data

    assert data["status"] == ReadinessStatus.READY
    assert data["blocker_count"] == 0
    assert len(data["blockers"]) == 0
    assert data["checks"]["general_ledger"]["status"] == ReadinessStatus.READY
    assert data["checks"]["billing_and_receivables"]["status"] == ReadinessStatus.READY
    assert data["checks"]["accounts_payable"]["status"] == ReadinessStatus.READY
    assert data["checks"]["payment_disbursements"]["status"] == ReadinessStatus.READY
    assert data["checks"]["external_integrations"]["status"] == ReadinessStatus.CONFIGURED


def test_ab_selected_context_isolation() -> None:
    roles = tenant_admin_roles()
    company_a = CompanyFactory.create(code="ALPHA", country_code="PK", timezone="Asia/Karachi")
    company_b = CompanyFactory.create(code="BRAVO", country_code="PK", timezone="Asia/Karachi")

    setup_complete_accounting(company_a)
    # Company B remains unconfigured (minimal)

    user_ab = UserFactory.create()
    assign_tenant_admin(user_ab, company_a, roles)
    assign_tenant_admin(user_ab, company_b, roles)

    client = authenticated(user_ab)

    select_context(client, company_a)
    resp_a = client.get(READINESS_URL)
    assert resp_a.status_code == 200
    assert resp_a.data["company_code"] == "ALPHA"
    assert resp_a.data["status"] == ReadinessStatus.READY
    assert resp_a.data["blocker_count"] == 0

    select_context(client, company_b)
    resp_b = client.get(READINESS_URL)
    assert resp_b.status_code == 200
    assert resp_b.data["company_code"] == "BRAVO"
    assert resp_b.data["status"] == ReadinessStatus.ACTION_REQUIRED
    assert resp_b.data["blocker_count"] > 0

    select_context(client, company_a)
    resp_a2 = client.get(READINESS_URL)
    assert resp_a2.status_code == 200
    assert resp_a2.data["company_code"] == "ALPHA"
    assert resp_a2.data["status"] == ReadinessStatus.READY
    assert resp_a2.data["blocker_count"] == 0


def test_tenant_admin_visibility() -> None:
    roles = tenant_admin_roles()
    company = CompanyFactory.create(code="ECHO")
    admin = UserFactory.create()
    assign_tenant_admin(admin, company, roles)

    client = authenticated(admin)
    select_context(client, company)

    response = client.get(READINESS_URL)
    assert response.status_code == 200


def test_ordinary_user_visibility_according_to_permissions() -> None:
    company = CompanyFactory.create(code="FOXTROT")
    guard_role = RoleFactory.create(code="GUARD", is_system=False, company=company)
    # Role has NO organization permissions
    ordinary_user = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=ordinary_user,
        role=guard_role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )

    client = authenticated(ordinary_user)
    select_context(client, company)

    response = client.get(READINESS_URL)
    assert response.status_code == 403
    assert "Company operational readiness view permission is required." in str(response.data)


def test_platform_only_safe_summary_boundary() -> None:
    roles = tenant_admin_roles()
    company = CompanyFactory.create(code="GOLF")
    assign_tenant_admin(UserFactory.create(), company, roles)
    setup_complete_accounting(company)

    operator = UserFactory.create(is_staff=False)
    grant_platform(operator, VIEW_PLATFORM_TENANT_DIRECTORY)

    client = authenticated(operator)

    # 1. Platform operator can view safe summary in platform tenant directory
    dir_response = client.get(DIRECTORY_URL)
    assert dir_response.status_code == 200
    matching = [row for row in dir_response.data if row["code"] == "GOLF"]
    assert len(matching) == 1
    golf_entry = matching[0]

    assert golf_entry["operational_status"] == ReadinessStatus.READY
    assert golf_entry["blocker_count"] == 0
    assert golf_entry["blocker_codes"] == []
    # Verify no financial account details leak
    assert "accounts" not in golf_entry
    assert "balances" not in golf_entry
    assert "bank_accounts" not in golf_entry

    # 2. Platform operator cannot access tenant readiness endpoint (no active company context)
    tenant_response = client.get(READINESS_URL)
    assert tenant_response.status_code == 404
    assert "No active Company context is selected." in str(tenant_response.data)


def test_platform_operator_cannot_edit_tenant_finance_config() -> None:
    company = CompanyFactory.create(code="HOTEL")
    operator = UserFactory.create(is_staff=False)
    grant_platform(operator, *PLATFORM_CAPABILITIES)

    client = authenticated(operator)

    # Readiness is deliberately read-only; there is no bootstrap mutation endpoint.
    resp = client.post(READINESS_URL)
    assert resp.status_code == 405
    patch_resp = client.patch(READINESS_URL, {"display_name": "Unauthorized"}, format="json")
    assert patch_resp.status_code == 405

    # 2. Attempt account creation via tenant finance API -> 403
    account_resp = client.post(
        "/api/v1/finance/accounts/",
        {
            "company": str(company.id),
            "code": "9999",
            "name": "Unauthorized Account",
            "account_type": "ASSET",
        },
        format="json",
    )
    assert account_resp.status_code == 403


def test_missing_required_configuration_produces_blocker() -> None:
    company = CompanyFactory.create(code="INDIA")
    admin = UserFactory.create()
    roles = tenant_admin_roles()
    assign_tenant_admin(admin, company, roles)

    readiness = get_company_operational_readiness(company)
    assert readiness.status == ReadinessStatus.ACTION_REQUIRED

    blocker_codes = {b.code for b in readiness.blockers}
    assert ReadinessCode.MISSING_CHART_OF_ACCOUNTS in blocker_codes
    assert ReadinessCode.MISSING_FISCAL_YEAR in blocker_codes
    assert ReadinessCode.NO_OPEN_ACCOUNTING_PERIOD in blocker_codes


def test_optional_config_produces_warning_not_blocker() -> None:
    company = CompanyFactory.create(code="JULIET")
    admin = UserFactory.create()
    roles = tenant_admin_roles()
    assign_tenant_admin(admin, company, roles)

    setup = setup_complete_accounting(company)
    # Remove payment provider configuration
    setup["provider_config"].delete()

    readiness = get_company_operational_readiness(company)
    # External integrations should produce warning, not blocker
    ext_items = readiness.checks["external_integrations"].items
    assert len(ext_items) == 1
    assert ext_items[0].severity == ReadinessSeverity.WARNING
    assert ext_items[0].code == ReadinessCode.NO_PAYMENT_PROVIDER_CONFIGURED
    # Company is still READY because payment provider is optional (manual payments available)
    assert readiness.status == ReadinessStatus.READY


def test_readiness_updates_immediately_after_configuration_change() -> None:
    company = CompanyFactory.create(code="KILO")
    admin = UserFactory.create()
    roles = tenant_admin_roles()
    assign_tenant_admin(admin, company, roles)

    setup = setup_complete_accounting(company)
    period = setup["period"]

    client = authenticated(admin)
    select_context(client, company)

    # Initial state is READY
    resp1 = client.get(READINESS_URL)
    assert resp1.status_code == 200
    assert resp1.data["status"] == ReadinessStatus.READY
    assert resp1.data["blocker_count"] == 0

    # Close the accounting period
    period.status = PeriodStatus.CLOSED
    period.save(update_fields=["status"])

    # Immediate check reflects ACTION_REQUIRED without stale caching
    resp2 = client.get(READINESS_URL)
    assert resp2.status_code == 200
    assert resp2.data["status"] == ReadinessStatus.ACTION_REQUIRED
    assert resp2.data["blocker_count"] == 1
    assert resp2.data["blockers"][0]["code"] == ReadinessCode.NO_OPEN_ACCOUNTING_PERIOD

    # Reopen period
    period.status = PeriodStatus.OPEN
    period.save(update_fields=["status"])

    # Immediate check reflects READY again
    resp3 = client.get(READINESS_URL)
    assert resp3.status_code == 200
    assert resp3.data["status"] == ReadinessStatus.READY
    assert resp3.data["blocker_count"] == 0


def test_cross_company_profile_account_relation_rejected() -> None:
    company_a = CompanyFactory.create(code="LIMA")
    company_b = CompanyFactory.create(code="MIKE")

    setup_a = setup_complete_accounting(company_a)
    setup_b = setup_complete_accounting(company_b)

    # New cross-Company linkages are rejected by model validation.
    profile_a = setup_a["payment_profile"]
    profile_a.bank_account = setup_b["accounts"]["asset"]
    with pytest.raises(ValidationError, match="payment profile company"):
        profile_a.full_clean()

    # Historical corruption bypassing model validation remains visible as a blocker.
    PaymentAccountingProfile.objects.filter(pk=profile_a.pk).update(
        bank_account=setup_b["accounts"]["asset"]
    )

    readiness = get_company_operational_readiness(company_a)
    assert readiness.status == ReadinessStatus.ACTION_REQUIRED

    blocker_codes = {b.code for b in readiness.blockers}
    assert ReadinessCode.INVALID_PAYMENT_ACCOUNTING_PROFILE in blocker_codes
    assert "cross-company" in readiness.checks["payment_disbursements"].items[0].message
