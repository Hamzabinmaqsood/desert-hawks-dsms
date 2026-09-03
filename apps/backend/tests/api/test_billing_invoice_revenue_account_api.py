import pytest
from rest_framework.test import APIClient

from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from dsms.identity.models import User
from tests.api.test_billing_invoice_api import authenticated, grant
from tests.factories.identity import UserFactory
from tests.unit.test_billing_core import billing_graph

pytestmark = pytest.mark.django_db

URL = "/api/v1/billing/invoice-reference/revenue-accounts/"


def test_maker_can_list_revenue_accounts_without_finance_permission() -> None:
    graph = billing_graph()
    maker = UserFactory.create()
    grant(maker, graph["company"], "add_clientinvoice", "change_clientinvoice")
    client = authenticated(maker)

    result = client.get(URL)

    assert result.status_code == 200
    ids = {item["id"] for item in result.json()["results"]}
    assert str(graph["revenue"].id) in ids
    item = next(row for row in result.json()["results"] if row["id"] == str(graph["revenue"].id))
    assert set(item.keys()) == {"id", "company", "code", "name", "account_type"}


def test_editor_only_maker_can_also_list() -> None:
    graph = billing_graph()
    editor = UserFactory.create()
    grant(editor, graph["company"], "change_clientinvoice")
    result = authenticated(editor).get(URL)
    assert result.status_code == 200
    ids = {item["id"] for item in result.json()["results"]}
    assert str(graph["revenue"].id) in ids


def test_unauthenticated_and_unrelated_role_denied() -> None:
    graph = billing_graph()
    assert APIClient().get(URL).status_code == 401

    no_role = authenticated(UserFactory.create())
    assert no_role.get(URL).status_code == 403

    approver = UserFactory.create()
    grant(approver, graph["company"], "view_clientinvoice", "approve_invoice", "issue_invoice")
    assert authenticated(approver).get(URL).status_code == 403


def test_cross_company_revenue_accounts_are_excluded() -> None:
    allowed, other = billing_graph(), billing_graph()
    maker = UserFactory.create()
    grant(maker, allowed["company"], "add_clientinvoice")

    result = authenticated(maker).get(URL)

    assert result.status_code == 200
    ids = {item["id"] for item in result.json()["results"]}
    assert str(allowed["revenue"].id) in ids
    assert str(other["revenue"].id) not in ids


def test_ineligible_accounts_are_excluded() -> None:
    graph = billing_graph()
    maker = UserFactory.create()
    grant(maker, graph["company"], "add_clientinvoice")

    non_revenue = Account.objects.create(
        company=graph["company"], code="5100", name="Expense", account_type=AccountType.EXPENSE
    )
    inactive_revenue = Account.objects.create(
        company=graph["company"],
        code="4200",
        name="Discontinued revenue line",
        account_type=AccountType.REVENUE,
        is_active=False,
    )
    non_postable_revenue = Account.objects.create(
        company=graph["company"],
        code="4000",
        name="Revenue rollup",
        account_type=AccountType.REVENUE,
        allow_posting=False,
    )

    result = authenticated(maker).get(URL)

    assert result.status_code == 200
    ids = {item["id"] for item in result.json()["results"]}
    assert str(graph["revenue"].id) in ids
    assert str(non_revenue.id) not in ids
    assert str(inactive_revenue.id) not in ids
    assert str(non_postable_revenue.id) not in ids


def test_maker_still_cannot_manage_chart_of_accounts() -> None:
    graph = billing_graph()
    maker = UserFactory.create()
    grant(maker, graph["company"], "add_clientinvoice", "change_clientinvoice")
    client = authenticated(maker)

    assert client.get("/api/v1/finance/accounts/").status_code == 403
    assert (
        client.post(
            "/api/v1/finance/accounts/",
            {
                "company": str(graph["company"].id),
                "code": "9999",
                "name": "Rogue account",
                "account_type": AccountType.REVENUE,
            },
            format="json",
        ).status_code
        == 403
    )


def test_superuser_sees_all_companies() -> None:
    allowed, other = billing_graph(), billing_graph()
    superuser: User = UserFactory.create(is_superuser=True)

    result = authenticated(superuser).get(URL)

    assert result.status_code == 200
    ids = {item["id"] for item in result.json()["results"]}
    assert str(allowed["revenue"].id) in ids
    assert str(other["revenue"].id) in ids
