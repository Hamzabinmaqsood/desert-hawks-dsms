# mypy: disable-error-code="arg-type"
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from rest_framework.test import APIClient

from dsms.billing.enums import InvoiceStatus, InvoiceType, PaymentMethod
from dsms.billing.models import ClientInvoice, ClientReceipt
from dsms.billing.services import allocate_receipt, approve_invoice, issue_invoice, submit_invoice
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.unit.test_billing_core import billing_graph, make_invoice

pytestmark = pytest.mark.django_db


def grant(user: User, company: object, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.add(
        *Permission.objects.filter(content_type__app_label="billing", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def authenticated(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def concurrent_allocate(
    receipt_id: UUID, invoice_id: UUID, amount: str, actor_id: UUID, barrier: Barrier
) -> bool:
    close_old_connections()
    try:
        barrier.wait()
        allocate_receipt(
            receipt=ClientReceipt.objects.get(pk=receipt_id),
            invoice=ClientInvoice.objects.get(pk=invoice_id),
            amount=Decimal(amount),
            actor=User.objects.get(pk=actor_id),
        )
        return True
    except ValidationError:
        return False
    finally:
        close_old_connections()


def test_invoice_list_detail_authentication_and_company_scope() -> None:
    allowed, hidden = billing_graph(), billing_graph()
    visible_invoice, hidden_invoice = make_invoice(allowed), make_invoice(hidden)
    url = "/api/v1/billing/invoices/"
    assert APIClient().get(url).status_code == 401
    no_role = authenticated(UserFactory.create())
    assert no_role.get(url).status_code == 403
    viewer = UserFactory.create()
    grant(viewer, allowed["company"], "view_clientinvoice")
    client = authenticated(viewer)
    result = client.get(url)
    assert result.status_code == 200
    ids = {item["id"] for item in result.json()["results"]}
    assert str(visible_invoice.id) in ids
    assert str(hidden_invoice.id) not in ids
    assert client.get(f"{url}{hidden_invoice.id}/").status_code == 404


def test_invoice_draft_create_edit_lines_totals_and_submit_permissions() -> None:
    graph, other = billing_graph(), billing_graph()
    maker = UserFactory.create()
    grant(
        maker,
        graph["company"],
        "view_clientinvoice",
        "add_clientinvoice",
        "change_clientinvoice",
    )
    client = authenticated(maker)
    url = "/api/v1/billing/invoices/"
    created = client.post(
        url,
        {
            "billing_profile": str(graph["profile"].id),
            "invoice_date": "2026-08-01",
            "invoice_type": InvoiceType.STANDARD,
            "status": InvoiceStatus.PAID,
            "total_amount": "999999.00",
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    invoice = ClientInvoice.objects.get(pk=created.data["id"])
    assert invoice.status == InvoiceStatus.DRAFT and invoice.total_amount == 0
    assert (
        client.post(
            url,
            {
                "billing_profile": str(other["profile"].id),
                "invoice_date": "2026-08-01",
                "invoice_type": InvoiceType.STANDARD,
            },
            format="json",
        ).status_code
        == 403
    )
    lines = f"{url}{invoice.id}/lines/"
    added = client.post(
        lines,
        {
            "description": "Guarding",
            "quantity": "2",
            "unit": "SERVICE",
            "unit_price": "100",
            "discount_amount": "10",
            "tax_rate": "10",
            "revenue_account": str(graph["revenue"].id),
            "line_total": "1",
        },
        format="json",
    )
    assert added.status_code == 201, added.data
    invoice.refresh_from_db()
    assert invoice.total_amount == Decimal("209.00")
    cross_account = dict(added.data)
    cross_account.update({"revenue_account": str(other["revenue"].id)})
    assert client.post(lines, cross_account, format="json").status_code == 400
    assert client.post(f"{url}{invoice.id}/submit/", {}, format="json").status_code == 200
    assert client.patch(f"{url}{invoice.id}/", {"client_reference": "late"}).status_code == 400
    assert client.post(f"{url}{invoice.id}/approve/", {}, format="json").status_code == 403


def test_invoice_approve_issue_and_private_download_use_dedicated_permissions() -> None:
    graph = billing_graph()
    invoice = submit_invoice(invoice=make_invoice(graph))
    approver = UserFactory.create()
    grant(
        approver,
        graph["company"],
        "view_clientinvoice",
        "approve_invoice",
        "issue_invoice",
        "download_invoice",
    )
    client = authenticated(approver)
    base = f"/api/v1/billing/invoices/{invoice.id}/"
    assert client.post(f"{base}approve/", {}, format="json").status_code == 200
    assert client.post(f"{base}issue/", {}, format="json").status_code == 200
    downloaded = client.get(f"{base}download/")
    assert downloaded.status_code == 200
    assert downloaded["Content-Type"] == "application/pdf"
    assert "attachment" in downloaded["Content-Disposition"]
    viewer = UserFactory.create()
    grant(viewer, graph["company"], "view_clientinvoice")
    assert authenticated(viewer).get(f"{base}download/").status_code == 403


def test_invoice_wrong_scope_workflow_is_non_enumerating() -> None:
    allowed, hidden = billing_graph(), billing_graph()
    hidden_invoice = submit_invoice(invoice=make_invoice(hidden))
    approver = UserFactory.create()
    grant(approver, allowed["company"], "approve_invoice")
    result = authenticated(approver).post(
        f"/api/v1/billing/invoices/{hidden_invoice.id}/approve/", {}, format="json"
    )
    assert result.status_code == 404


def test_receipt_create_scope_and_action_specific_permissions() -> None:
    graph, other = billing_graph(), billing_graph()
    maker = UserFactory.create()
    grant(maker, graph["company"], "add_clientreceipt", "view_clientreceipt")
    client = authenticated(maker)
    url = "/api/v1/billing/receipts/"
    payload = {
        "company": str(graph["company"].id),
        "client": str(graph["client"].id),
        "received_at": "2026-08-02T10:00:00Z",
        "currency": "PKR",
        "amount": "100.00",
        "payment_method": PaymentMethod.BANK_TRANSFER,
        "bank_account": str(graph["bank"].id),
    }
    created = client.post(url, payload, format="json")
    assert created.status_code == 201, created.data
    receipt = ClientReceipt.objects.get(pk=created.data["id"])
    payload.update(
        {
            "company": str(other["company"].id),
            "client": str(other["client"].id),
            "bank_account": str(other["bank"].id),
        }
    )
    assert client.post(url, payload, format="json").status_code == 403
    assert client.post(f"{url}{receipt.id}/confirm/", {}, format="json").status_code == 403
    checker = UserFactory.create()
    grant(checker, graph["company"], "confirm_receipt")
    assert (
        authenticated(checker).post(f"{url}{receipt.id}/confirm/", {}, format="json").status_code
        == 200
    )
    assert (
        authenticated(checker)
        .post(f"{url}{receipt.id}/reverse/", {"reason": "Correction required"}, format="json")
        .status_code
        == 403
    )
    reverser = UserFactory.create()
    grant(reverser, graph["company"], "reverse_receipt")
    assert (
        authenticated(reverser)
        .post(f"{url}{receipt.id}/reverse/", {"reason": "Correction required"}, format="json")
        .status_code
        == 200
    )


def test_allocation_locks_preserve_receipt_and_invoice_budgets() -> None:
    graph = billing_graph()
    invoice = issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(graph, "50")), actor=graph["checker"]
        ),
        actor=graph["checker"],
    )
    receipt = ClientReceipt.objects.create(
        receipt_number="RCPT-LOCK",
        company=graph["company"],
        client=graph["client"],
        received_at="2026-08-02T10:00:00Z",
        currency="PKR",
        amount=Decimal("100"),
        payment_method=PaymentMethod.BANK_TRANSFER,
        received_by=graph["maker"],
        bank_account=graph["bank"],
        status="CONFIRMED",
    )
    allocator = UserFactory.create()
    grant(allocator, graph["company"], "allocate_receipt")
    client = authenticated(allocator)
    endpoint = f"/api/v1/billing/receipts/{receipt.id}/allocate/"
    assert client.post(endpoint, {"invoice": invoice.id, "amount": "70"}).status_code == 201
    assert client.post(endpoint, {"invoice": invoice.id, "amount": "60"}).status_code == 400
    invoice.refresh_from_db()
    assert invoice.amount_paid == Decimal("70.00")
    assert sum(receipt.allocations.values_list("amount", flat=True), Decimal("0")) == Decimal("70")


def test_receipt_reference_and_payment_visibility_contract() -> None:
    graph = billing_graph()
    invoice = issue_invoice(
        invoice=approve_invoice(
            invoice=submit_invoice(invoice=make_invoice(graph, "100")), actor=graph["checker"]
        ),
        actor=graph["checker"],
    )
    receipt = ClientReceipt.objects.create(
        receipt_number="RCPT-VISIBILITY",
        company=graph["company"],
        client=graph["client"],
        received_at="2026-08-02T10:00:00Z",
        currency="PKR",
        amount=Decimal("70"),
        payment_method=PaymentMethod.BANK_TRANSFER,
        external_reference="BANK-9",
        received_by=graph["maker"],
        bank_account=graph["bank"],
        status="CONFIRMED",
    )
    clerk = UserFactory.create()
    grant(
        clerk,
        graph["company"],
        "add_clientreceipt",
        "view_clientreceipt",
        "allocate_receipt",
        "view_clientinvoice",
    )
    client = authenticated(clerk)
    clients = client.get("/api/v1/billing/receipt-reference/clients/")
    assert clients.status_code == 200
    assert set(clients.data["results"][0]) == {"client", "company", "billing_name", "currency"}
    banks = client.get("/api/v1/billing/receipt-reference/bank-accounts/")
    assert banks.status_code == 200
    assert set(banks.data["results"][0]) == {"id", "company", "name", "bank_name", "currency"}
    eligible = client.get(f"/api/v1/billing/receipts/{receipt.id}/eligible-invoices/")
    assert eligible.status_code == 200
    assert eligible.data[0]["id"] == invoice.id
    allocated = client.post(
        f"/api/v1/billing/receipts/{receipt.id}/allocate/",
        {"invoice": invoice.id, "amount": "60.00"},
        format="json",
    )
    assert allocated.status_code == 201
    receipt_detail = client.get(f"/api/v1/billing/receipts/{receipt.id}/")
    assert receipt_detail.data["allocated_amount"] == Decimal("60.00")
    assert receipt_detail.data["unallocated_amount"] == Decimal("10.00")
    assert receipt_detail.data["allocations"][0]["invoice_number"] == invoice.invoice_number
    invoice_detail = client.get(f"/api/v1/billing/invoices/{invoice.id}/")
    assert invoice_detail.data["amount_paid"] == "60.00"
    assert invoice_detail.data["balance_due"] == "149.00"
    assert invoice_detail.data["receipt_allocations"][0]["receipt_number"] == receipt.receipt_number


@pytest.mark.django_db(transaction=True)
def test_postgresql_concurrent_allocations_preserve_both_budgets() -> None:
    graph = billing_graph()
    invoices = [
        issue_invoice(
            invoice=approve_invoice(
                invoice=submit_invoice(invoice=make_invoice(graph)), actor=graph["checker"]
            ),
            actor=graph["checker"],
        )
        for _ in range(2)
    ]
    receipts = [
        ClientReceipt.objects.create(
            receipt_number=f"RCPT-RACE-{index}",
            company=graph["company"],
            client=graph["client"],
            received_at="2026-08-02T10:00:00Z",
            currency="PKR",
            amount=Decimal("100"),
            payment_method=PaymentMethod.BANK_TRANSFER,
            received_by=graph["maker"],
            bank_account=graph["bank"],
            status="CONFIRMED",
        )
        for index in range(2)
    ]
    actor = UserFactory.create()
    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipt_results = list(
            pool.map(
                lambda args: concurrent_allocate(*args),
                [
                    (receipts[0].id, invoices[0].id, "70", actor.id, barrier),
                    (receipts[0].id, invoices[1].id, "60", actor.id, barrier),
                ],
            )
        )
    assert sum(receipt_results) == 1
    assert sum(receipts[0].allocations.values_list("amount", flat=True), Decimal("0")) <= Decimal(
        "100"
    )

    barrier = Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        invoice_results = list(
            pool.map(
                lambda args: concurrent_allocate(*args),
                [
                    (receipts[0].id, invoices[1].id, "70", actor.id, barrier),
                    (receipts[1].id, invoices[1].id, "60", actor.id, barrier),
                ],
            )
        )
    invoices[1].refresh_from_db()
    assert sum(invoice_results) <= 1
    assert invoices[1].amount_paid <= invoices[1].total_amount
