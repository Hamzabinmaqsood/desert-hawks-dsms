from typing import Any, cast

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.billing.models import ClientInvoice
from dsms.billing.services import approve_invoice, issue_invoice, submit_invoice
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User, UserRoleAssignment
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.unit.test_billing_core import billing_graph, make_invoice

pytestmark = pytest.mark.django_db

CONTEXT_URL = "/api/v1/auth/company-context/"
INVOICES_URL = "/api/v1/billing/invoices/"


def grant(user: User, graph: dict[str, Any], *codenames: str) -> UserRoleAssignment:
    company = graph["company"]
    role = RoleFactory.create(company=company)
    role.permissions.set(
        Permission.objects.filter(
            content_type__app_label__in={"billing", "organization"},
            codename__in={*codenames, "view_company"},
        )
    )
    return UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def issued_invoice(graph: dict[str, Any]) -> ClientInvoice:
    return issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(graph)), actor=graph["checker"]
        ),
        actor=graph["checker"],
    )


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def select(client: APIClient, graph: dict[str, Any]) -> None:
    response = client.put(CONTEXT_URL, {"company_id": str(graph["company"].id)}, format="json")
    assert response.status_code == 200


def pdf(client: APIClient, invoice: ClientInvoice) -> tuple[int, bytes]:
    response = client.get(f"{INVOICES_URL}{invoice.id}/download/")
    return response.status_code, b"".join(
        cast(Any, response).streaming_content
    ) if response.status_code == 200 else b""


def identify(graph: dict[str, Any], prefix: str) -> None:
    company = graph["company"]
    company.trade_name = f"{prefix} Response"
    company.legal_name = f"{prefix} Response Holdings"
    company.brand_tagline = f"{prefix} tenant operations"
    company.registration_number = f"REG-{prefix}"
    company.tax_number = f"TAX-{prefix}"
    company.email = f"accounts@{prefix.lower()}.example"
    company.phone = f"+1000-{prefix}"
    company.website = f"https://{prefix.lower()}.example"
    company.address_line_1 = f"{prefix} House"
    company.city_name = f"{prefix} City"
    company.country_code = "AE"
    company.save()


def test_a_only_document_uses_a_identity_and_rejects_b_probe() -> None:
    graph_a, graph_b = billing_graph(), billing_graph()
    identify(graph_a, "ALPHA")
    identify(graph_b, "BRAVO")
    invoice_a, invoice_b = issued_invoice(graph_a), issued_invoice(graph_b)
    user = UserFactory.create()
    grant(user, graph_a, "download_invoice")
    client = client_for(user)

    status, payload = pdf(client, invoice_a)
    assert status == 200
    assert b"ALPHA Response" in payload
    assert b"BRAVO Response" not in payload
    assert pdf(client, invoice_b)[0] == 404


def test_b_only_document_identity_is_symmetric() -> None:
    graph_a, graph_b = billing_graph(), billing_graph()
    identify(graph_a, "ALPHA")
    identify(graph_b, "BRAVO")
    invoice_a, invoice_b = issued_invoice(graph_a), issued_invoice(graph_b)
    user = UserFactory.create()
    grant(user, graph_b, "download_invoice")
    client = client_for(user)

    status, payload = pdf(client, invoice_b)
    assert status == 200
    assert b"BRAVO Response" in payload
    assert b"ALPHA Response" not in payload
    assert pdf(client, invoice_a)[0] == 404


def test_selected_a_cannot_misbrand_authorized_b_invoice() -> None:
    graph_a, graph_b = billing_graph(), billing_graph()
    identify(graph_a, "ALPHA")
    identify(graph_b, "BRAVO")
    invoice_a, invoice_b = issued_invoice(graph_a), issued_invoice(graph_b)
    user = UserFactory.create()
    grant(user, graph_a, "download_invoice")
    grant(user, graph_b, "download_invoice")
    client = client_for(user)

    select(client, graph_a)
    status, b_while_a_selected = pdf(client, invoice_b)
    assert status == 200
    assert b"BRAVO Response" in b_while_a_selected
    assert b"BRAVO Response Holdings" in b_while_a_selected
    assert b"BRAVO tenant operations" in b_while_a_selected
    assert b"Registration: REG-BRAVO" in b_while_a_selected
    assert b"Tax number: TAX-BRAVO" in b_while_a_selected
    assert b"accounts@bravo.example" in b_while_a_selected
    assert b"ALPHA Response" not in b_while_a_selected

    a_status, a_payload = pdf(client, invoice_a)
    assert a_status == 200
    assert b"ALPHA Response" in a_payload
    assert b"BRAVO Response" not in a_payload

    select(client, graph_b)
    assert pdf(client, invoice_b) == (200, b_while_a_selected)


def test_company_and_resource_currency_fallbacks_are_stable() -> None:
    graph = billing_graph()
    company = graph["company"]
    company.legal_name = "Fallback Legal Company"
    company.trade_name = ""
    company.brand_tagline = ""
    company.brand_primary_color = ""
    company.brand_accent_color = ""
    company.save()
    graph["profile"].currency = "USD"
    graph["profile"].save(update_fields=["currency"])
    invoice = issued_invoice(graph)
    user = UserFactory.create()
    grant(user, graph, "download_invoice")

    status, payload = pdf(client_for(user), invoice)
    assert status == 200
    assert b"Fallback Legal Company" in payload
    assert b"Currency: USD" in payload
    assert b"DESERT HAWKS" not in payload


def test_inactive_revoked_and_corrupt_document_graphs_fail_closed() -> None:
    graph, other = billing_graph(), billing_graph()
    invoice = issued_invoice(graph)
    user = UserFactory.create()
    assignment = grant(user, graph, "download_invoice")
    client = client_for(user)
    assert pdf(client, invoice)[0] == 200

    assignment.is_active = False
    assignment.save(update_fields=["is_active"])
    assert pdf(client, invoice)[0] == 403

    assignment.is_active = True
    assignment.save(update_fields=["is_active"])
    graph["company"].is_active = False
    graph["company"].save(update_fields=["is_active"])
    assert pdf(client, invoice)[0] == 403

    graph["company"].is_active = True
    graph["company"].save(update_fields=["is_active"])
    invoice.documents.update(company=other["company"])
    assert pdf(client, invoice)[0] == 404
