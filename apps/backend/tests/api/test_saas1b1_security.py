# mypy: disable-error-code="arg-type,no-untyped-def,no-any-return"
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.billing.models import (
    BillingRule,
    BillingSchedule,
    ClientBillingProfile,
    ClientCollectionActivity,
    TaxCode,
)
from dsms.contracts.models import Client, ClientIndustry, SecuritySite, ServiceContract
from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from dsms.identity.enums import AccessScopeType
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory

pytestmark = pytest.mark.django_db


def grant(actor, company, app_label: str, *codenames: str) -> None:
    role = RoleFactory.create(company=company)
    role.permissions.set(
        Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=actor,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def rows(response) -> list[dict[str, object]]:
    body = response.json()
    return body["results"] if isinstance(body, dict) and "results" in body else body


def contract_graph(company, suffix: str, actor):
    industry = ClientIndustry.objects.create(
        company=company, code=f"IND-{suffix}", name=f"Industry {suffix}"
    )
    client = Client.objects.create(
        company=company,
        client_code=f"CLI-{suffix}",
        legal_name=f"Client {suffix}",
        industry=industry,
    )
    contract = ServiceContract.objects.create(
        company=company,
        client=client,
        contract_number=f"CTR-{suffix}",
        contract_type="FIXED_TERM",
        title=f"Contract {suffix}",
        start_date=date(2026, 1, 1),
        created_by=actor,
    )
    return industry, client, contract


def account(company, suffix: str, account_type: str = AccountType.ASSET):
    return Account.objects.create(
        company=company,
        code=f"ACC-{suffix}",
        name=f"Account {suffix}",
        account_type=account_type,
    )


def test_contract_clients_hide_corruption_and_reject_cross_company_for_multi_company_actor() -> (
    None
):
    company_a, company_b = CompanyFactory.create_batch(2)
    actor = UserFactory.create()
    for company in (company_a, company_b):
        grant(
            actor,
            company,
            "contracts",
            "view_client",
            "add_client",
            "change_client",
            "view_securitysite",
            "change_securitysite",
            "view_servicecontract",
        )
    industry_a, valid_a, contract_a = contract_graph(company_a, "A", actor)
    industry_b, valid_b, contract_b = contract_graph(company_b, "B", actor)
    corrupt = Client.objects.create(
        company=company_a,
        client_code="CLI-CORRUPT",
        legal_name="Foreign metadata must not leak",
        industry=industry_b,
    )
    client = APIClient()
    client.force_authenticate(actor)

    response = client.get("/api/v1/contracts/clients/")
    assert response.status_code == 200
    ids = {item["id"] for item in rows(response)}
    assert {str(valid_a.pk), str(valid_b.pk)} <= ids
    assert str(corrupt.pk) not in ids
    assert client.get(f"/api/v1/contracts/clients/{corrupt.pk}/").status_code == 404
    create = client.post(
        "/api/v1/contracts/clients/",
        {
            "company": str(company_a.pk),
            "client_code": "CLI-CROSS",
            "legal_name": "Cross tenant",
            "industry": str(industry_b.pk),
        },
        format="json",
    )
    assert create.status_code == 400
    patch = client.patch(
        f"/api/v1/contracts/clients/{valid_a.pk}/",
        {"company": str(company_b.pk), "industry": str(industry_b.pk)},
        format="json",
    )
    assert patch.status_code == 400
    valid_a.refresh_from_db()
    assert valid_a.company_id == company_a.pk and valid_a.industry_id == industry_a.pk
    branch_a = BranchFactory.create(company=company_a)
    branch_b = BranchFactory.create(company=company_b)
    valid_site = SecuritySite.objects.create(
        company=company_a,
        client=valid_a,
        contract=contract_a,
        site_code="SITE-A",
        name="Valid site",
        managing_branch=branch_a,
        address_line_1="A",
        city_name="A",
        risk_level="LOW",
    )
    corrupt_site = SecuritySite.objects.create(
        company=company_a,
        client=valid_a,
        contract=contract_b,
        site_code="SITE-CORRUPT",
        name="Foreign contract and branch",
        managing_branch=branch_b,
        address_line_1="A",
        city_name="A",
        risk_level="LOW",
    )
    response = client.get("/api/v1/contracts/sites/")
    site_ids = {item["id"] for item in rows(response)}
    assert str(valid_site.pk) in site_ids and str(corrupt_site.pk) not in site_ids
    assert client.get(f"/api/v1/contracts/sites/{corrupt_site.pk}/").status_code == 404
    assert (
        client.patch(
            f"/api/v1/contracts/sites/{valid_site.pk}/",
            {"managing_branch": str(branch_b.pk)},
            format="json",
        ).status_code
        == 400
    )


def test_generic_client_contract_queries_are_bounded_and_presentable() -> None:
    company_a, company_b = CompanyFactory.create_batch(2)
    actor = UserFactory.create()
    for company in (company_a, company_b):
        grant(
            actor,
            company,
            "contracts",
            "view_client",
            "view_servicecontract",
        )
    industry_a, client_a, contract_a = contract_graph(company_a, "GENERAL-A", actor)
    contract_graph(company_a, "UNRELATED-A", actor)
    contract_graph(company_b, "GENERAL-B", actor)
    client_a.trade_name = "Acme Advisory"
    client_a.save(update_fields=["trade_name"])
    api = APIClient()
    api.force_authenticate(actor)

    clients = api.get(
        "/api/v1/contracts/clients/",
        {"company": company_a.pk, "search": "Advisory", "ordering": "legal_name"},
    )
    assert clients.status_code == 200
    client_rows = rows(clients)
    assert [item["id"] for item in client_rows] == [str(client_a.pk)]
    assert client_rows[0]["industry_name"] == industry_a.name

    contracts = api.get(
        "/api/v1/contracts/contracts/",
        {
            "company": company_a.pk,
            "client": client_a.pk,
            "search": "GENERAL-A",
            "ordering": "contract_number",
        },
    )
    assert contracts.status_code == 200
    contract_rows = rows(contracts)
    assert [item["id"] for item in contract_rows] == [str(contract_a.pk)]
    assert contract_rows[0]["client_name"] == client_a.legal_name


def test_contract_dashboard_company_scope_and_inactive_company() -> None:
    company_a, company_b = CompanyFactory.create_batch(2)
    actor = UserFactory.create()
    grant(actor, company_a, "contracts", "view_servicecontract")
    contract_graph(company_a, "A-DASH", actor)
    contract_graph(company_b, "B-DASH", actor)
    client = APIClient()
    client.force_authenticate(actor)

    assert (
        client.get("/api/v1/contracts/dashboard/summary/", {"company": company_a.pk}).status_code
        == 200
    )
    assert (
        client.get("/api/v1/contracts/dashboard/summary/", {"company": company_b.pk}).status_code
        == 404
    )
    company_a.is_active = False
    company_a.save(update_fields=["is_active"])
    assert client.get(
        "/api/v1/contracts/dashboard/summary/", {"company": company_a.pk}
    ).status_code in {403, 404}


def test_billing_profiles_hide_corruption_and_reject_cross_company_relations() -> None:
    company_a, company_b = CompanyFactory.create_batch(2)
    actor = UserFactory.create()
    for company in (company_a, company_b):
        grant(
            actor,
            company,
            "billing",
            "view_clientbillingprofile",
            "add_clientbillingprofile",
            "change_clientbillingprofile",
        )
    _, client_a, _ = contract_graph(company_a, "BA", actor)
    _, client_b, _ = contract_graph(company_b, "BB", actor)
    receivable_a = account(company_a, "AR-A")
    receivable_b = account(company_b, "AR-B")
    valid = ClientBillingProfile.objects.create(
        company=company_a,
        client=client_a,
        billing_name="Valid A",
        billing_address="A",
        default_receivable_account=receivable_a,
    )
    corrupt = ClientBillingProfile.objects.create(
        company=company_b,
        client=client_b,
        billing_name="Corrupt foreign account",
        billing_address="B",
        default_receivable_account=receivable_a,
    )
    api = APIClient()
    api.force_authenticate(actor)
    response = api.get("/api/v1/billing/billing-profiles/")
    ids = {item["id"] for item in rows(response)}
    assert str(valid.pk) in ids and str(corrupt.pk) not in ids
    assert api.get(f"/api/v1/billing/billing-profiles/{corrupt.pk}/").status_code == 404
    create = api.post(
        "/api/v1/billing/billing-profiles/",
        {
            "company": str(company_a.pk),
            "client": str(client_a.pk),
            "billing_name": "Cross account",
            "billing_address": "A",
            "default_receivable_account": str(receivable_b.pk),
        },
        format="json",
    )
    assert create.status_code == 400


def test_billing_schedule_rule_tax_and_collection_consistency() -> None:
    company_a, company_b = CompanyFactory.create_batch(2)
    actor = UserFactory.create()
    billing_codes = (
        "view_billingschedule",
        "add_billingschedule",
        "change_billingschedule",
        "view_billingrule",
        "add_billingrule",
        "change_billingrule",
        "view_taxcode",
        "add_taxcode",
        "change_taxcode",
        "view_clientcollectionactivity",
        "add_clientcollectionactivity",
        "change_clientcollectionactivity",
    )
    for company in (company_a, company_b):
        grant(actor, company, "billing", *billing_codes)
    _, client_a, contract_a = contract_graph(company_a, "RULE-A", actor)
    _, client_b, contract_b = contract_graph(company_b, "RULE-B", actor)
    revenue_b = account(company_b, "REV-B", AccountType.REVENUE)
    tax_a = account(company_a, "TAX-A", AccountType.LIABILITY)
    schedule_a = BillingSchedule.objects.create(
        company=company_a,
        client=client_a,
        contract=contract_a,
        frequency="MONTHLY",
        period_alignment="ADVANCE",
        first_billing_date=date(2026, 1, 1),
        created_by=actor,
    )
    corrupt_schedule = BillingSchedule.objects.create(
        company=company_a,
        client=client_a,
        contract=contract_b,
        frequency="MONTHLY",
        period_alignment="ADVANCE",
        first_billing_date=date(2026, 1, 1),
        created_by=actor,
    )
    corrupt_rule = BillingRule.objects.create(
        billing_schedule=schedule_a,
        description="Foreign account",
        calculation_method="FIXED_AMOUNT",
        quantity_source="FIXED",
        unit_price=Decimal("100"),
        revenue_account=revenue_b,
        effective_from=date(2026, 1, 1),
    )
    corrupt_tax = TaxCode.objects.create(
        company=company_a,
        code="TX-CORRUPT",
        name="Foreign tax account",
        rate=Decimal("5"),
        tax_account=revenue_b,
        effective_from=date(2026, 1, 1),
    )
    valid_collection = ClientCollectionActivity.objects.create(
        company=company_a,
        client=client_a,
        invoice=None,
        activity_type="CALL",
        activity_at="2026-01-01T00:00:00Z",
        actor=actor,
    )
    corrupt_collection = ClientCollectionActivity.objects.create(
        company=company_a,
        client=client_b,
        invoice=None,
        activity_type="CALL",
        activity_at="2026-01-01T00:00:00Z",
        actor=actor,
    )
    api = APIClient()
    api.force_authenticate(actor)
    cases = (
        ("billing-schedules", corrupt_schedule.pk),
        ("billing-rules", corrupt_rule.pk),
        ("tax-codes", corrupt_tax.pk),
    )
    for route, corrupt_id in cases:
        response = api.get(f"/api/v1/billing/{route}/")
        assert response.status_code == 200
        assert str(corrupt_id) not in {item["id"] for item in rows(response)}
        assert api.get(f"/api/v1/billing/{route}/{corrupt_id}/").status_code == 404
    assert api.get(f"/api/v1/billing/collections/{valid_collection.pk}/").status_code == 200
    collection_response = api.get("/api/v1/billing/collections/")
    assert str(corrupt_collection.pk) not in {item["id"] for item in rows(collection_response)}
    assert api.get(f"/api/v1/billing/collections/{corrupt_collection.pk}/").status_code == 404
    create_schedule = api.post(
        "/api/v1/billing/billing-schedules/",
        {
            "company": str(company_a.pk),
            "client": str(client_a.pk),
            "contract": str(contract_b.pk),
            "frequency": "MONTHLY",
            "period_alignment": "ADVANCE",
            "first_billing_date": "2026-01-01",
        },
        format="json",
    )
    assert create_schedule.status_code == 400
    create_tax = api.post(
        "/api/v1/billing/tax-codes/",
        {
            "company": str(company_a.pk),
            "code": "TX-CROSS",
            "name": "Cross",
            "rate": "5.0000",
            "tax_account": str(revenue_b.pk),
            "effective_from": "2026-01-01",
        },
        format="json",
    )
    assert create_tax.status_code == 400
    assert tax_a.company_id == company_a.pk and client_b.company_id == company_b.pk
