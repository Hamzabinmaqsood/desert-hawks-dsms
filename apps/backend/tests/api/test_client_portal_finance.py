import pytest
from django.contrib.auth.models import Permission
from django.http import StreamingHttpResponse
from rest_framework.test import APIClient

from dsms.billing.services import approve_invoice, issue_invoice, submit_invoice
from dsms.client_portal.models import ClientPortalMembership, ClientPortalRole
from tests.unit.test_billing_core import billing_graph, make_invoice

pytestmark = pytest.mark.django_db


def test_portal_finance_is_strictly_client_scoped_and_pdf_is_private() -> None:
    first = billing_graph()
    second = billing_graph()
    invoice = issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(first)), actor=first["checker"]
        ),
        actor=first["checker"],
    )
    other_invoice = issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(second)), actor=second["checker"]
        ),
        actor=second["checker"],
    )
    role = ClientPortalRole.objects.create(code="PORTAL_FINANCE", name="Portal finance")
    role.permissions.add(
        *Permission.objects.filter(
            content_type__app_label="client_portal",
            codename__in=[
                "view_client_invoices",
                "download_client_invoice",
                "view_client_statement",
            ],
        )
    )
    ClientPortalMembership.objects.create(
        user=first["maker"], client=first["client"], role=role, status="ACTIVE"
    )
    client = APIClient()
    client.force_authenticate(first["maker"])
    base = f"/api/v1/client-portal/{first['client'].id}/finance"

    listing = client.get(f"{base}/invoices/")
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()] == [str(invoice.id)]
    assert client.get(f"{base}/invoices/{other_invoice.id}/").status_code == 404
    assert (
        client.get(f"/api/v1/client-portal/{second['client'].id}/finance/invoices/").status_code
        == 404
    )

    detail = client.get(f"{base}/invoices/{invoice.id}/")
    assert detail.status_code == 200 and detail.json()["invoice_number"] == invoice.invoice_number
    statement = client.get(f"{base}/statement/")
    assert statement.status_code == 200
    assert statement.json()["closing_balance"] == float(invoice.total_amount)
    download = client.get(f"{base}/invoices/{invoice.id}/download/")
    assert download.status_code == 200
    assert isinstance(download, StreamingHttpResponse)
    assert b"".join(download.streaming_content).startswith(b"%PDF-1.4")


def test_portal_finance_permission_denial_is_non_enumerating() -> None:
    graph = billing_graph()
    role = ClientPortalRole.objects.create(code="NO_FINANCE", name="No finance")
    ClientPortalMembership.objects.create(
        user=graph["maker"], client=graph["client"], role=role, status="ACTIVE"
    )
    client = APIClient()
    client.force_authenticate(graph["maker"])
    response = client.get(f"/api/v1/client-portal/{graph['client'].id}/finance/invoices/")
    assert response.status_code == 404
