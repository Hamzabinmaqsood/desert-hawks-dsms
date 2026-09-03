from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.test import APIClient

from dsms.billing.enums import InvoiceType
from dsms.billing.models import ClientInvoice
from dsms.billing.services import add_invoice_line, create_invoice, update_invoice_line
from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from tests.api.test_billing_invoice_api import authenticated, grant
from tests.factories.identity import UserFactory
from tests.unit.test_billing_core import billing_graph, make_invoice

pytestmark = pytest.mark.django_db


def _maker(graph: dict[str, Any]) -> APIClient:
    maker = UserFactory.create()
    grant(
        maker, graph["company"], "view_clientinvoice", "add_clientinvoice", "change_clientinvoice"
    )
    return authenticated(maker)


def _create_draft(client: APIClient, graph: dict[str, Any]) -> str:
    created = client.post(
        "/api/v1/billing/invoices/",
        {
            "billing_profile": str(graph["profile"].id),
            "invoice_date": "2026-08-01",
            "invoice_type": InvoiceType.STANDARD,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    return str(created.data["id"])


def _line_payload(account_id: object, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "description": "Guarding",
        "quantity": "2",
        "unit": "SERVICE",
        "unit_price": "100",
        "discount_amount": "0",
        "tax_rate": "0",
        "revenue_account": str(account_id),
    }
    payload.update(overrides)
    return payload


def test_line_creation_rejects_same_company_asset_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)
    asset_account = Account.objects.create(
        company=graph["company"],
        code="1200",
        name="Prepaid Expenses",
        account_type=AccountType.ASSET,
    )

    result = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(asset_account.id),
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    invoice = ClientInvoice.objects.get(pk=invoice_id)
    assert not invoice.lines.exists()
    assert invoice.total_amount == Decimal("0.00")


def test_line_creation_rejects_same_company_liability_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)
    liability_account = Account.objects.create(
        company=graph["company"],
        code="2200",
        name="Deferred Revenue",
        account_type=AccountType.LIABILITY,
    )

    result = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(liability_account.id),
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    assert not ClientInvoice.objects.get(pk=invoice_id).lines.exists()


def test_line_creation_rejects_inactive_revenue_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)
    inactive_revenue = Account.objects.create(
        company=graph["company"],
        code="4200",
        name="Discontinued revenue line",
        account_type=AccountType.REVENUE,
        is_active=False,
    )

    result = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(inactive_revenue.id),
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    invoice = ClientInvoice.objects.get(pk=invoice_id)
    assert not invoice.lines.exists()
    assert invoice.total_amount == Decimal("0.00")


def test_line_creation_rejects_non_posting_revenue_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)
    non_posting_revenue = Account.objects.create(
        company=graph["company"],
        code="4000",
        name="Revenue rollup",
        account_type=AccountType.REVENUE,
        allow_posting=False,
    )

    result = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(non_posting_revenue.id),
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    invoice = ClientInvoice.objects.get(pk=invoice_id)
    assert not invoice.lines.exists()
    assert invoice.total_amount == Decimal("0.00")


def test_line_creation_accepts_active_posting_revenue_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)

    result = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(graph["revenue"].id),
        format="json",
    )

    assert result.status_code == 201, result.data
    invoice = ClientInvoice.objects.get(pk=invoice_id)
    assert invoice.lines.count() == 1
    assert invoice.total_amount == Decimal("200.00")


def test_line_creation_rejects_cross_company_revenue_account() -> None:
    graph, other = billing_graph(), billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)

    result = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(other["revenue"].id),
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    assert not ClientInvoice.objects.get(pk=invoice_id).lines.exists()


def test_line_update_rejects_change_to_same_company_asset_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)
    added = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(graph["revenue"].id),
        format="json",
    )
    assert added.status_code == 201, added.data
    line_id = added.data["id"]
    asset_account = Account.objects.create(
        company=graph["company"], code="1300", name="Fixed Assets", account_type=AccountType.ASSET
    )

    result = client.patch(
        f"/api/v1/billing/invoices/{invoice_id}/lines/{line_id}/",
        {"revenue_account": str(asset_account.id)},
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    invoice = ClientInvoice.objects.get(pk=invoice_id)
    line = invoice.lines.get(pk=line_id)
    assert line.revenue_account_id == graph["revenue"].id
    assert invoice.total_amount == Decimal("200.00")


def test_line_update_rejects_change_to_inactive_revenue_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    invoice_id = _create_draft(client, graph)
    added = client.post(
        f"/api/v1/billing/invoices/{invoice_id}/lines/",
        _line_payload(graph["revenue"].id),
        format="json",
    )
    line_id = added.data["id"]
    inactive_revenue = Account.objects.create(
        company=graph["company"],
        code="4300",
        name="Legacy revenue",
        account_type=AccountType.REVENUE,
        is_active=False,
    )

    result = client.patch(
        f"/api/v1/billing/invoices/{invoice_id}/lines/{line_id}/",
        {"revenue_account": str(inactive_revenue.id)},
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    line = ClientInvoice.objects.get(pk=invoice_id).lines.get(pk=line_id)
    assert line.revenue_account_id == graph["revenue"].id


def test_initial_invoice_lines_reject_invalid_revenue_account() -> None:
    graph = billing_graph()
    client = _maker(graph)
    asset_account = Account.objects.create(
        company=graph["company"], code="1400", name="Inventory", account_type=AccountType.ASSET
    )
    before = ClientInvoice.objects.count()

    result = client.post(
        "/api/v1/billing/invoices/",
        {
            "billing_profile": str(graph["profile"].id),
            "invoice_date": "2026-08-01",
            "invoice_type": InvoiceType.STANDARD,
            "lines": [_line_payload(asset_account.id)],
        },
        format="json",
    )

    assert result.status_code == 400
    assert "revenue_account" in result.data
    assert ClientInvoice.objects.count() == before


def _service_line(account: Account) -> dict[str, Any]:
    return {
        "description": "Guarding",
        "quantity": Decimal("2"),
        "unit_price": Decimal("100"),
        "discount_amount": Decimal("0"),
        "tax_rate": Decimal("0"),
        "revenue_account": account,
    }


@pytest.mark.parametrize(
    ("code", "name", "attributes"),
    [
        ("1500", "Vehicles", {"account_type": AccountType.ASSET}),
        ("2500", "Accruals", {"account_type": AccountType.LIABILITY}),
        ("5500", "Fuel", {"account_type": AccountType.EXPENSE}),
        ("4500", "Retired revenue", {"account_type": AccountType.REVENUE, "is_active": False}),
        ("4600", "Revenue header", {"account_type": AccountType.REVENUE, "allow_posting": False}),
    ],
)
def test_service_layer_rejects_ineligible_accounts_without_a_serializer(
    code: str, name: str, attributes: dict[str, Any]
) -> None:
    """The service is the authoritative boundary, not serializer queryset filtering."""
    graph = billing_graph()
    account = Account.objects.create(company=graph["company"], code=code, name=name, **attributes)
    invoice = make_invoice(graph)

    with pytest.raises(DjangoValidationError) as created:
        create_invoice(
            profile=graph["profile"],
            actor=graph["maker"],
            invoice_date=date(2026, 8, 1),
            invoice_type=InvoiceType.STANDARD,
            lines=[_service_line(account)],
        )
    assert "revenue_account" in created.value.message_dict

    with pytest.raises(DjangoValidationError) as added:
        add_invoice_line(invoice=invoice, actor=graph["maker"], values=_service_line(account))
    assert "revenue_account" in added.value.message_dict

    with pytest.raises(DjangoValidationError) as updated:
        update_invoice_line(
            invoice=invoice,
            line=invoice.lines.get(),
            actor=graph["maker"],
            values={"revenue_account": account},
        )
    assert "revenue_account" in updated.value.message_dict

    invoice.refresh_from_db()
    assert invoice.lines.count() == 1
    assert invoice.lines.get().revenue_account_id == graph["revenue"].id
    assert invoice.total_amount == Decimal("209.00")
