from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TypedDict

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.billing.enums import InvoiceStatus, InvoiceType, PaymentMethod, ReceiptStatus
from dsms.billing.models import ClientBillingProfile, ClientInvoice, ClientReceipt
from dsms.billing.services import allocate_receipt, create_invoice
from dsms.contracts.models import Client, ClientIndustry
from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from dsms.finance.operations_models import BankAccount
from dsms.finance.payment_models import PaymentProviderConfiguration, ProviderType
from dsms.finance.payment_services import request_payment_destination_change
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from dsms.organization import services as organization_services
from dsms.organization.models import Company
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory, RegionFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db

CONTEXT_URL = "/api/v1/auth/company-context/"
SETTINGS_URL = "/api/v1/auth/company-business-settings/"


class BillingGraph(TypedDict):
    client: Client
    receivable: Account
    revenue: Account


def grant_company(user: User, company: Company, *permission_codes: str) -> None:
    role = RoleFactory.create(company=company)
    query = None
    for code in permission_codes:
        app_label, codename = code.split(".", 1)
        condition = Permission.objects.filter(content_type__app_label=app_label, codename=codename)
        query = condition if query is None else query.union(condition)
    if query is not None:
        role.permissions.set(query)
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def select(client: APIClient, company: Company) -> None:
    assert client.put(CONTEXT_URL, {"company_id": company.id}, format="json").status_code == 200


def accounting_graph(company: Company, suffix: str) -> BillingGraph:
    industry = ClientIndustry.objects.create(
        company=company, code=f"IND-{suffix}", name=f"Industry {suffix}"
    )
    client = Client.objects.create(
        company=company,
        client_code=f"CLIENT-{suffix}",
        legal_name=f"Client {suffix}",
        industry=industry,
    )
    receivable = Account.objects.create(
        company=company,
        code=f"11{suffix}",
        name=f"Receivable {suffix}",
        account_type=AccountType.ASSET,
    )
    revenue = Account.objects.create(
        company=company,
        code=f"41{suffix}",
        name=f"Revenue {suffix}",
        account_type=AccountType.REVENUE,
    )
    return {"client": client, "receivable": receivable, "revenue": revenue}


def create_profile(
    client: APIClient, company: Company, graph: BillingGraph, suffix: str
) -> ClientBillingProfile:
    response = client.post(
        "/api/v1/billing/billing-profiles/",
        {
            "company": str(company.id),
            "client": str(graph["client"].id),
            "billing_name": f"Billing {suffix}",
            "billing_address": "Safe address",
            "default_receivable_account": str(graph["receivable"].id),
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return ClientBillingProfile.objects.get(pk=response.data["id"])


def invoice(profile: ClientBillingProfile, revenue: Account, actor: User) -> ClientInvoice:
    return create_invoice(
        profile=profile,
        actor=actor,
        invoice_date=date(2026, 10, 9),
        invoice_type=InvoiceType.STANDARD,
        lines=[
            {
                "description": "Service",
                "quantity": Decimal("1"),
                "unit_price": Decimal("100"),
                "revenue_account": revenue,
            }
        ],
    )


def test_omitted_currency_derives_from_actual_company_and_old_records_do_not_change() -> None:
    company = CompanyFactory.create(default_currency="USD", invoice_number_prefix="AINV")
    actor = UserFactory.create(is_superuser=True)
    api = APIClient()
    api.force_authenticate(actor)
    first_graph = accounting_graph(company, "01")
    first_profile = create_profile(api, company, first_graph, "01")
    first_invoice = invoice(first_profile, first_graph["revenue"], actor)

    assert first_profile.currency == "USD"
    assert first_invoice.currency == "USD"
    assert first_invoice.invoice_number == "AINV-2026-000001"

    organization_services.update_company(
        company=company, default_currency="AED", invoice_number_prefix="A-INV"
    )
    second_graph = accounting_graph(company, "02")
    second_profile = create_profile(api, company, second_graph, "02")
    second_invoice = invoice(second_profile, second_graph["revenue"], actor)
    first_invoice.refresh_from_db()

    assert first_invoice.currency == "USD"
    assert first_invoice.invoice_number == "AINV-2026-000001"
    assert second_profile.currency == "AED"
    assert second_invoice.currency == "AED"
    assert second_invoice.invoice_number == "A-INV-2026-000001"

    organization_services.update_company(company=company, invoice_number_prefix="AINV")
    third_graph = accounting_graph(company, "03")
    third_invoice = invoice(
        create_profile(api, company, third_graph, "03"), third_graph["revenue"], actor
    )
    first_invoice.refresh_from_db()
    second_invoice.refresh_from_db()

    assert first_invoice.invoice_number == "AINV-2026-000001"
    assert second_invoice.invoice_number == "A-INV-2026-000001"
    assert third_invoice.invoice_number == "AINV-2026-000002"


def test_company_a_and_b_defaults_and_numbering_do_not_cross() -> None:
    company_a = CompanyFactory.create(default_currency="USD", invoice_number_prefix="AINV")
    company_b = CompanyFactory.create(default_currency="GBP", invoice_number_prefix="BINV")
    actor = UserFactory.create(is_superuser=True)
    api = APIClient()
    api.force_authenticate(actor)
    graph_a = accounting_graph(company_a, "11")
    graph_b = accounting_graph(company_b, "12")
    invoice_a = invoice(create_profile(api, company_a, graph_a, "11"), graph_a["revenue"], actor)
    invoice_b = invoice(create_profile(api, company_b, graph_b, "12"), graph_b["revenue"], actor)

    assert (invoice_a.currency, invoice_a.invoice_number) == ("USD", "AINV-2026-000001")
    assert (invoice_b.currency, invoice_b.invoice_number) == ("GBP", "BINV-2026-000001")


def test_contract_banking_provider_and_direct_beneficiary_paths_derive_company_currency() -> None:
    company = CompanyFactory.create(default_currency="GBP")
    actor = UserFactory.create(is_superuser=True)
    api = APIClient()
    api.force_authenticate(actor)
    graph = accounting_graph(company, "31")

    contract_response = api.post(
        "/api/v1/contracts/contracts/",
        {
            "company": str(company.id),
            "client": str(graph["client"].id),
            "contract_number": "CON-31",
            "contract_type": "FIXED_TERM",
            "title": "Company-currency contract",
            "start_date": "2026-10-09",
        },
        format="json",
    )
    assert contract_response.status_code == 201, contract_response.data
    assert contract_response.data["currency"] == "GBP"

    provider_response = api.post(
        "/api/v1/finance/payment-providers/",
        {
            "company": str(company.id),
            "code": "BANK-31",
            "provider_type": ProviderType.BANK,
            "display_name": "Company bank",
            "adapter_code": "TEST_SUCCESS",
        },
        format="json",
    )
    assert provider_response.status_code == 201, provider_response.data
    provider = PaymentProviderConfiguration.objects.get(pk=provider_response.data["id"])
    assert provider.currency == "GBP"

    ledger = Account.objects.create(
        company=company, code="1031", name="Settlement bank", account_type=AccountType.ASSET
    )
    bank_response = api.post(
        "/api/v1/finance/domain/bank-accounts/",
        {
            "company": str(company.id),
            "name": "Settlement",
            "bank_name": "Bank",
            "account_number_encrypted": "encrypted",
            "ledger_account": str(ledger.id),
            "is_active": True,
        },
        format="json",
    )
    assert bank_response.status_code == 201, bank_response.data
    assert bank_response.data["currency"] == "GBP"

    employee = EmployeeFactory.create(company=company)
    beneficiary = request_payment_destination_change(
        company=company,
        actor=actor,
        employee=employee,
        destination="03123456789",
        account_title="Employee",
        provider_type=ProviderType.BANK,
    )
    assert beneficiary.currency == "GBP"


def test_city_direct_service_derives_company_locale_defaults() -> None:
    company = CompanyFactory.create(country_code="AE", timezone="Asia/Dubai")
    region = RegionFactory.create(company=company)
    city = organization_services.create_city(
        company=company,
        region=region,
        code="DXB",
        name="Dubai",
        province_or_state="Dubai",
    )
    assert (city.country_code, city.timezone) == ("AE", "Asia/Dubai")


def test_company_api_requires_explicit_business_configuration() -> None:
    actor = UserFactory.create(is_superuser=True)
    api = APIClient()
    api.force_authenticate(actor)
    missing = api.post(
        "/api/v1/organization/companies/",
        {"code": "NEW", "legal_name": "New Company"},
        format="json",
    )
    assert missing.status_code == 400
    assert set(missing.data) >= {"timezone", "default_currency", "country_code"}

    created = api.post(
        "/api/v1/organization/companies/",
        {
            "code": "NEW",
            "legal_name": "New Company",
            "timezone": "Europe/London",
            "default_currency": "GBP",
            "country_code": "GB",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert created.data["default_currency"] == "GBP"
    assert created.data["timezone"] == "Europe/London"


def test_receipt_omission_uses_company_currency_and_cross_currency_bank_is_rejected() -> None:
    company = CompanyFactory.create(default_currency="AED", receipt_number_prefix="AREC")
    actor = UserFactory.create(is_superuser=True)
    api = APIClient()
    api.force_authenticate(actor)
    graph = accounting_graph(company, "21")
    create_profile(api, company, graph, "21")
    ledger = Account.objects.create(
        company=company, code="1021", name="Bank", account_type=AccountType.ASSET
    )
    bank = BankAccount.objects.create(
        company=company,
        name="AED Bank",
        bank_name="Bank",
        account_number_encrypted="encrypted",
        currency="AED",
        ledger_account=ledger,
    )
    payload = {
        "company": str(company.id),
        "client": str(graph["client"].id),
        "received_at": timezone.make_aware(datetime(2026, 10, 9, 12, 0)),
        "amount": "50.00",
        "payment_method": PaymentMethod.BANK_TRANSFER,
        "bank_account": str(bank.id),
    }
    response = api.post("/api/v1/billing/receipts/", payload, format="json")
    assert response.status_code == 201, response.data
    receipt = ClientReceipt.objects.get(pk=response.data["id"])
    assert receipt.currency == "AED"
    assert receipt.receipt_number == "AREC-2026-000001"

    payload["currency"] = "USD"
    rejected = api.post("/api/v1/billing/receipts/", payload, format="json")
    assert rejected.status_code == 400
    assert "currency" in rejected.data


def test_old_source_currency_remains_authoritative_after_company_default_changes() -> None:
    company = CompanyFactory.create(default_currency="PKR", invoice_number_prefix="AINV")
    actor = UserFactory.create(is_superuser=True)
    api = APIClient()
    api.force_authenticate(actor)
    graph = accounting_graph(company, "41")
    profile = create_profile(api, company, graph, "41")
    old_invoice = invoice(profile, graph["revenue"], actor)
    old_invoice.status = InvoiceStatus.ISSUED
    old_invoice.save(update_fields=["status"])

    organization_services.update_company(company=company, default_currency="USD")
    ledger = Account.objects.create(
        company=company, code="1041", name="PKR settlement", account_type=AccountType.ASSET
    )
    pkr_bank = BankAccount.objects.create(
        company=company,
        name="PKR Bank",
        bank_name="Bank",
        account_number_encrypted="encrypted",
        currency="PKR",
        ledger_account=ledger,
    )
    explicit_old_currency = api.post(
        "/api/v1/billing/receipts/",
        {
            "company": str(company.id),
            "client": str(graph["client"].id),
            "received_at": timezone.make_aware(datetime(2026, 10, 9, 12, 0)),
            "amount": "50.00",
            "payment_method": PaymentMethod.BANK_TRANSFER,
            "bank_account": str(pkr_bank.id),
            "currency": "PKR",
        },
        format="json",
    )
    assert explicit_old_currency.status_code == 201, explicit_old_currency.data
    receipt = ClientReceipt.objects.get(pk=explicit_old_currency.data["id"])
    receipt.status = ReceiptStatus.CONFIRMED
    receipt.save(update_fields=["status"])
    allocation = allocate_receipt(
        receipt=receipt, invoice=old_invoice, amount=Decimal("50"), actor=actor
    )
    assert allocation.amount == Decimal("50.00")

    usd_ledger = Account.objects.create(
        company=company, code="1042", name="USD settlement", account_type=AccountType.ASSET
    )
    usd_bank = BankAccount.objects.create(
        company=company,
        name="USD Bank",
        bank_name="Bank",
        account_number_encrypted="encrypted-usd",
        currency="USD",
        ledger_account=usd_ledger,
    )
    defaulted_new_currency = api.post(
        "/api/v1/billing/receipts/",
        {
            "company": str(company.id),
            "client": str(graph["client"].id),
            "received_at": timezone.make_aware(datetime(2026, 10, 9, 13, 0)),
            "amount": "10.00",
            "payment_method": PaymentMethod.BANK_TRANSFER,
            "bank_account": str(usd_bank.id),
        },
        format="json",
    )
    assert defaulted_new_currency.status_code == 201, defaulted_new_currency.data
    new_receipt = ClientReceipt.objects.get(pk=defaulted_new_currency.data["id"])
    assert new_receipt.currency == "USD"
    new_receipt.status = ReceiptStatus.CONFIRMED
    new_receipt.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="currencies differ"):
        allocate_receipt(
            receipt=new_receipt, invoice=old_invoice, amount=Decimal("10"), actor=actor
        )


def test_company_rejects_duplicate_document_family_prefixes() -> None:
    company = CompanyFactory.create(invoice_number_prefix="DOC", receipt_number_prefix="RCPT")
    user = UserFactory.create()
    grant_company(
        user,
        company,
        "organization.view_company",
        "organization.change_company",
    )
    api = APIClient()
    api.force_authenticate(user)
    select(api, company)

    response = api.patch(SETTINGS_URL, {"receipt_number_prefix": "doc"}, format="json")

    assert response.status_code == 400
    company.refresh_from_db()
    assert company.invoice_number_prefix == "DOC"
    assert company.receipt_number_prefix == "RCPT"


def test_split_scope_settings_permissions_and_server_selected_company_authority() -> None:
    company_a = CompanyFactory.create(code="A", default_currency="USD")
    company_b = CompanyFactory.create(code="B", default_currency="GBP")
    user = UserFactory.create()
    grant_company(user, company_a, "organization.view_company")
    grant_company(
        user,
        company_b,
        "organization.view_company",
        "organization.change_company",
    )
    api = APIClient()
    api.force_authenticate(user)

    select(api, company_a)
    read_a = api.get(SETTINGS_URL)
    assert read_a.status_code == 200
    assert read_a.data["default_currency"] == "USD"
    assert read_a.data["can_manage"] is False
    denied = api.patch(SETTINGS_URL, {"default_currency": "AED"}, format="json")
    assert denied.status_code == 403

    select(api, company_b)
    read_b = api.get(SETTINGS_URL)
    assert read_b.data["default_currency"] == "GBP"
    assert read_b.data["can_manage"] is True
    allowed = api.patch(
        SETTINGS_URL,
        {
            "default_currency": "aed",
            "timezone": "Asia/Dubai",
            "invoice_number_prefix": "b-inv",
        },
        format="json",
    )
    assert allowed.status_code == 200, allowed.data
    assert allowed.data["default_currency"] == "AED"
    assert allowed.data["invoice_number_prefix"] == "B-INV"
    company_a.refresh_from_db()
    company_b.refresh_from_db()
    assert company_a.default_currency == "USD"
    assert company_b.default_currency == "AED"


@pytest.mark.parametrize(
    "payload",
    [
        {"company_id": "00000000-0000-0000-0000-000000000000"},
        {"default_currency": "US"},
        {"timezone": "Not/A_Real_Zone"},
        {"invoice_number_prefix": "../INV"},
        {"receipt_number_prefix": "<script>"},
    ],
)
def test_business_settings_reject_owner_probes_and_invalid_values(payload: dict[str, str]) -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    grant_company(
        user,
        company,
        "organization.view_company",
        "organization.change_company",
    )
    api = APIClient()
    api.force_authenticate(user)
    response = api.patch(SETTINGS_URL, payload, format="json")
    assert response.status_code == 400


def test_inactive_or_revoked_selected_company_settings_fail_closed() -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    grant_company(user, company, "organization.view_company")
    api = APIClient()
    api.force_authenticate(user)
    assert api.get(SETTINGS_URL).status_code == 200
    company.is_active = False
    company.save(update_fields=["is_active"])
    assert api.get(SETTINGS_URL).status_code == 404
