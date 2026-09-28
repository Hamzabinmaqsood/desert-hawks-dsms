# mypy: disable-error-code="arg-type"
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from dsms.finance import services
from dsms.finance.enums import AccountType, MatchType, ReceiptType, WorkflowStatus
from dsms.finance.models import JournalEntry
from dsms.finance.operations_models import FinanceApprovalHistory, FinanceAttachment
from dsms.finance.procurement_models import (
    PaymentVoucher,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
    VendorBill,
    VendorBillLine,
)
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from tests.factories.finance import accounting_setup
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def grant(user: User, company: object, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.add(
        *Permission.objects.filter(content_type__app_label="finance", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )


def api(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def graph() -> dict[str, Any]:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    asset = services.create_account(
        company=company, code="1100", name="Equipment", account_type=AccountType.ASSET
    )
    vendor = Vendor.objects.create(
        company=company, code="V-1", name="Supplier", payable_account=accounts["payable"]
    )
    requisition = PurchaseRequisition.objects.create(
        company=company,
        requisition_number="REQ-1",
        required_date=date(2026, 9, 1),
        purpose="Radios",
        status=WorkflowStatus.APPROVED,
        created_by=maker,
    )
    req_line = PurchaseRequisitionLine.objects.create(
        requisition=requisition,
        description="Radios",
        quantity=10,
        estimated_unit_price=100,
        expense_account=accounts["expense"],
    )
    order = PurchaseOrder.objects.create(
        company=company,
        requisition=requisition,
        vendor=vendor,
        order_number="PO-1",
        order_date=date(2026, 9, 1),
        status=WorkflowStatus.APPROVED,
        created_by=maker,
    )
    po_line = PurchaseOrderLine.objects.create(
        purchase_order=order,
        requisition_line=req_line,
        description="Radios",
        quantity=10,
        unit_price=100,
    )
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="GRN-1",
        receipt_date=date(2026, 9, 2),
        receipt_type=ReceiptType.GOODS,
        status=WorkflowStatus.APPROVED,
        received_by=maker,
    )
    receipt_line = PurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=po_line,
        quantity=10,
        accepted_quantity=10,
    )
    return locals()


def bill_payload(g: dict[str, Any], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "vendor": str(g["vendor"].id),
        "purchase_order": str(g["order"].id),
        "vendor_invoice_number": "SUP-1",
        "bill_number": "BILL-1",
        "bill_date": "2026-08-15",
        "due_date": "2026-09-15",
        "match_type": MatchType.TWO_WAY,
        "company": str(CompanyFactory.create().id),
        "status": WorkflowStatus.POSTED,
        "subtotal": "999",
        "tax_amount": "999",
        "total_amount": "999",
        "paid_amount": "999",
        "match_exception": "attacker",
    }
    payload.update(overrides)
    return payload


def line_payload(g: dict[str, Any], **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "description": "Radios",
        "quantity": "2",
        "unit_price": "100.00",
        "tax_amount": "20.00",
        "expense_account": str(g["accounts"]["expense"].id),
        "purchase_order_line": str(g["po_line"].id),
        "receipt_line": None,
    }
    payload.update(overrides)
    return payload


def author(g: dict[str, Any]) -> tuple[User, APIClient]:
    user = UserFactory.create()
    grant(
        user,
        g["company"],
        "view_vendorbill",
        "add_vendorbill",
        "change_vendorbill",
        "add_vendorbillline",
        "change_vendorbillline",
        "delete_vendorbillline",
    )
    return user, api(user)


def test_bill_crud_scope_permissions_and_server_owned_fields() -> None:
    g, other = graph(), graph()
    user, client = author(g)
    hidden = VendorBill.objects.create(
        company=other["company"],
        vendor=other["vendor"],
        vendor_invoice_number="HIDDEN",
        bill_number="HIDDEN",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 9, 2),
        created_by=other["maker"],
    )
    response = client.post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    assert response.status_code == 201, response.data
    bill = VendorBill.objects.get(pk=response.data["id"])
    assert (bill.company, bill.created_by, bill.status) == (
        g["company"],
        user,
        WorkflowStatus.DRAFT,
    )
    assert (bill.subtotal, bill.tax_amount, bill.total_amount, bill.paid_amount) == (
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )
    assert bill.match_exception == ""
    listed = client.get("/api/v1/finance/vendor-bills/")
    assert [row["id"] for row in listed.data["results"]] == [str(bill.id)]
    assert client.get(f"/api/v1/finance/vendor-bills/{hidden.id}/").status_code == 404
    assert client.patch(f"/api/v1/finance/vendor-bills/{hidden.id}/", {}).status_code == 404
    assert not user.has_perm("finance.manage_procurement")


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_bill_payment_history_enforces_parent_company(
    multi_company_access: bool,
) -> None:
    company_a, company_b = graph(), graph()
    bill = VendorBill.objects.create(
        company=company_a["company"],
        vendor=company_a["vendor"],
        vendor_invoice_number="TENANT-HISTORY",
        bill_number="TENANT-HISTORY",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 10, 1),
        status=WorkflowStatus.POSTED,
        subtotal=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        created_by=company_a["maker"],
    )
    valid = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=bill,
        voucher_number="PV-TENANT-A",
        payment_date=date(2026, 9, 2),
        amount=Decimal("25.00"),
        payment_reference="VISIBLE-A",
        created_by=company_a["maker"],
    )
    corrupt = PaymentVoucher.objects.create(
        company=company_b["company"],
        vendor_bill=bill,
        voucher_number="PV-TENANT-B-CORRUPT",
        payment_date=date(2026, 9, 3),
        amount=Decimal("75.00"),
        payment_reference="HIDDEN-B",
        created_by=company_b["maker"],
    )
    user = UserFactory.create()
    grant(user, company_a["company"], "view_vendorbill")
    if multi_company_access:
        grant(user, company_b["company"], "view_vendorbill")

    result = api(user).get(f"/api/v1/finance/vendor-bills/{bill.id}/")

    assert result.status_code == 200
    assert result.data["payments"] == [
        {
            "id": str(valid.id),
            "voucher_number": "PV-TENANT-A",
            "payment_date": "2026-09-02",
            "amount": "25.00",
            "status": WorkflowStatus.DRAFT,
            "payment_status": "PENDING",
            "payment_reference": "VISIBLE-A",
        }
    ]
    serialized = str(result.data)
    assert str(corrupt.id) not in serialized
    assert corrupt.voucher_number not in serialized
    assert corrupt.payment_reference not in serialized


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_bill_lines_enforce_parent_company(multi_company_access: bool) -> None:
    company_a, company_b = graph(), graph()
    company_b["accounts"]["expense"].code = "B-5000"
    company_b["accounts"]["expense"].name = "Foreign Expense"
    company_b["accounts"]["expense"].save(update_fields=["code", "name"])
    bill = VendorBill.objects.create(
        company=company_a["company"],
        vendor=company_a["vendor"],
        vendor_invoice_number="TENANT-LINES",
        bill_number="TENANT-LINES",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 10, 1),
        created_by=company_a["maker"],
    )
    valid = VendorBillLine.objects.create(
        vendor_bill=bill,
        purchase_order_line=company_a["po_line"],
        receipt_line=company_a["receipt_line"],
        description="Visible same-company line",
        quantity=Decimal("1.0000"),
        unit_price=Decimal("100.00"),
        tax_amount=Decimal("10.00"),
        expense_account=company_a["accounts"]["expense"],
    )
    foreign_account = VendorBillLine.objects.create(
        vendor_bill=bill,
        description="Hidden foreign account",
        quantity=1,
        unit_price=1,
        expense_account=company_b["accounts"]["expense"],
    )
    foreign_po = VendorBillLine.objects.create(
        vendor_bill=bill,
        purchase_order_line=company_b["po_line"],
        description="Hidden foreign PO line",
        quantity=1,
        unit_price=1,
        expense_account=company_a["accounts"]["expense"],
    )
    foreign_receipt = VendorBillLine.objects.create(
        vendor_bill=bill,
        receipt_line=company_b["receipt_line"],
        description="Hidden foreign receipt line",
        quantity=1,
        unit_price=1,
        expense_account=company_a["accounts"]["expense"],
    )
    user = UserFactory.create()
    grant(user, company_a["company"], "view_vendorbill")
    if multi_company_access:
        grant(user, company_b["company"], "view_vendorbill")

    result = api(user).get(f"/api/v1/finance/vendor-bills/{bill.id}/")

    assert result.status_code == 200
    assert result.data["lines"] == [
        {
            "id": str(valid.id),
            "purchase_order_line": company_a["po_line"].id,
            "receipt_line": company_a["receipt_line"].id,
            "description": "Visible same-company line",
            "quantity": "1.0000",
            "unit_price": "100.00",
            "tax_amount": "10.00",
            "line_total": "110.00",
            "expense_account": company_a["accounts"]["expense"].id,
            "expense_account_code": "5000",
            "expense_account_name": "Expense",
        }
    ]
    serialized = str(result.data)
    for corrupt in (foreign_account, foreign_po, foreign_receipt):
        assert str(corrupt.id) not in serialized
        assert corrupt.description not in serialized
    assert str(company_b["accounts"]["expense"].id) not in serialized
    assert company_b["accounts"]["expense"].code not in serialized
    assert company_b["accounts"]["expense"].name not in serialized
    assert str(company_b["po_line"].id) not in serialized
    assert str(company_b["receipt_line"].id) not in serialized


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_bill_vendor_enforces_parent_company(multi_company_access: bool) -> None:
    company_a, company_b = graph(), graph()
    company_a["vendor"].code = "V-A"
    company_a["vendor"].name = "Visible Vendor A"
    company_a["vendor"].save(update_fields=["code", "name"])
    company_b["vendor"].code = "V-B-FOREIGN"
    company_b["vendor"].name = "Hidden Vendor B"
    company_b["vendor"].save(update_fields=["code", "name"])
    valid = VendorBill.objects.create(
        company=company_a["company"],
        vendor=company_a["vendor"],
        vendor_invoice_number="TENANT-VENDOR-VALID",
        bill_number="TENANT-VENDOR-VALID",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 10, 1),
        created_by=company_a["maker"],
    )
    corrupt = VendorBill.objects.create(
        company=company_a["company"],
        vendor=company_b["vendor"],
        vendor_invoice_number="TENANT-VENDOR-CORRUPT",
        bill_number="TENANT-VENDOR-CORRUPT",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 10, 1),
        created_by=company_a["maker"],
    )
    user = UserFactory.create()
    grant(user, company_a["company"], "view_vendorbill", "manage_procurement")
    if multi_company_access:
        grant(user, company_b["company"], "view_vendorbill", "manage_procurement")
    client = api(user)

    valid_detail = client.get(f"/api/v1/finance/vendor-bills/{valid.id}/")
    corrupt_detail = client.get(f"/api/v1/finance/vendor-bills/{corrupt.id}/")
    listed = client.get("/api/v1/finance/vendor-bills/")
    legacy_detail = client.get(f"/api/v1/finance/domain/vendor-bills/{corrupt.id}/")
    legacy_list = client.get("/api/v1/finance/domain/vendor-bills/")

    assert valid_detail.status_code == 200
    assert valid_detail.data["vendor"] == company_a["vendor"].id
    assert valid_detail.data["vendor_code"] == "V-A"
    assert valid_detail.data["vendor_name"] == "Visible Vendor A"
    assert corrupt_detail.status_code == 404
    assert [row["id"] for row in listed.data["results"]] == [str(valid.id)]
    assert legacy_detail.status_code == 403
    assert legacy_list.status_code == 403
    serialized = (
        str(listed.data)
        + str(corrupt_detail.data)
        + str(legacy_list.data)
        + str(legacy_detail.data)
    )
    assert str(company_b["vendor"].id) not in serialized
    assert company_b["vendor"].code not in serialized
    assert company_b["vendor"].name not in serialized


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_bill_purchase_order_enforces_parent_company(multi_company_access: bool) -> None:
    company_a, company_b = graph(), graph()
    common = {
        "company": company_a["company"],
        "vendor": company_a["vendor"],
        "bill_date": date(2026, 9, 1),
        "due_date": date(2026, 10, 1),
        "status": WorkflowStatus.POSTED,
        "total_amount": Decimal("100.00"),
        "created_by": company_a["maker"],
    }
    valid = VendorBill.objects.create(
        **common,
        purchase_order=company_a["order"],
        vendor_invoice_number="TENANT-PO-VALID",
        bill_number="TENANT-PO-VALID",
    )
    without_po = VendorBill.objects.create(
        **common,
        purchase_order=None,
        vendor_invoice_number="TENANT-PO-NULL",
        bill_number="TENANT-PO-NULL",
    )
    corrupt = VendorBill.objects.create(
        **common,
        purchase_order=company_b["order"],
        vendor_invoice_number="TENANT-PO-CORRUPT",
        bill_number="TENANT-PO-CORRUPT",
    )
    user = UserFactory.create()
    grant(
        user,
        company_a["company"],
        "view_vendorbill",
        "manage_procurement",
        "view_paymentvoucher",
    )
    if multi_company_access:
        grant(
            user,
            company_b["company"],
            "view_vendorbill",
            "manage_procurement",
            "view_paymentvoucher",
        )
    client = api(user)

    valid_detail = client.get(f"/api/v1/finance/vendor-bills/{valid.id}/")
    corrupt_detail = client.get(f"/api/v1/finance/vendor-bills/{corrupt.id}/")
    listed = client.get("/api/v1/finance/vendor-bills/")
    legacy_detail = client.get(f"/api/v1/finance/domain/vendor-bills/{corrupt.id}/")
    legacy_list = client.get("/api/v1/finance/domain/vendor-bills/")
    payable = client.get("/api/v1/finance/ap-reference/payable-bills/")

    expected_ids = {str(valid.id), str(without_po.id)}
    assert valid_detail.status_code == 200
    assert valid_detail.data["purchase_order"] == company_a["order"].id
    assert client.get(f"/api/v1/finance/vendor-bills/{without_po.id}/").status_code == 200
    assert corrupt_detail.status_code == 404
    assert {row["id"] for row in listed.data["results"]} == expected_ids
    assert legacy_detail.status_code == 403
    assert legacy_list.status_code == 403
    assert {row["id"] for row in payable.data} == expected_ids
    serialized = str(listed.data) + str(legacy_list.data) + str(payable.data)
    assert str(corrupt.id) not in serialized
    assert str(company_b["order"].id) not in serialized


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_legacy_bill_journal_is_platform_only(multi_company_access: bool) -> None:
    company_a, company_b = graph(), graph()
    journal_a = JournalEntry.objects.create(
        company=company_a["company"],
        fiscal_year=company_a["_year"],
        accounting_period=company_a["_period"],
        journal_number="JV-BILL-TENANT-A",
        entry_date=date(2026, 9, 1),
        description="Visible Bill journal",
        created_by=company_a["maker"],
    )
    journal_b = JournalEntry.objects.create(
        company=company_b["company"],
        fiscal_year=company_b["_year"],
        accounting_period=company_b["_period"],
        journal_number="JV-BILL-TENANT-B",
        entry_date=date(2026, 9, 1),
        description="Hidden foreign Bill journal",
        created_by=company_b["maker"],
    )
    common = {
        "company": company_a["company"],
        "vendor": company_a["vendor"],
        "bill_date": date(2026, 9, 1),
        "due_date": date(2026, 10, 1),
        "created_by": company_a["maker"],
    }
    without_journal = VendorBill.objects.create(
        **common,
        vendor_invoice_number="BILL-JOURNAL-NULL",
        bill_number="BILL-JOURNAL-NULL",
    )
    same_company = VendorBill.objects.create(
        **common,
        journal_entry=journal_a,
        vendor_invoice_number="BILL-JOURNAL-VALID",
        bill_number="BILL-JOURNAL-VALID",
    )
    corrupt = VendorBill.objects.create(
        **common,
        journal_entry=journal_b,
        vendor_invoice_number="BILL-JOURNAL-CORRUPT",
        bill_number="BILL-JOURNAL-CORRUPT",
    )
    user = UserFactory.create()
    grant(user, company_a["company"], "view_vendorbill", "manage_procurement")
    if multi_company_access:
        grant(user, company_b["company"], "view_vendorbill", "manage_procurement")
    client = api(user)

    listed = client.get("/api/v1/finance/domain/vendor-bills/")
    null_detail = client.get(f"/api/v1/finance/domain/vendor-bills/{without_journal.id}/")
    valid_detail = client.get(f"/api/v1/finance/domain/vendor-bills/{same_company.id}/")
    corrupt_detail = client.get(f"/api/v1/finance/domain/vendor-bills/{corrupt.id}/")
    corrupt_action = client.post(
        f"/api/v1/finance/domain/vendor-bills/{corrupt.id}/submit/", {}, format="json"
    )
    dedicated_detail = client.get(f"/api/v1/finance/vendor-bills/{corrupt.id}/")

    assert listed.status_code == 403
    assert null_detail.status_code == 403
    assert valid_detail.status_code == 403
    assert corrupt_detail.status_code == 403
    assert corrupt_action.status_code == 403
    assert str(corrupt.id) not in str(listed.data)
    assert str(journal_b.id) not in str(listed.data)
    assert dedicated_detail.status_code == 200
    assert "journal_entry" not in dedicated_detail.data


def test_generated_bill_and_line_permissions_are_enforced() -> None:
    g = graph()
    viewer, creator = UserFactory.create(), UserFactory.create()
    grant(viewer, g["company"], "view_vendorbill")
    grant(creator, g["company"], "add_vendorbill")
    assert (
        api(viewer)
        .post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
        .status_code
        == 403
    )
    created = api(creator).post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    assert created.status_code == 201
    assert (
        api(creator).get(f"/api/v1/finance/vendor-bills/{created.data['id']}/").status_code == 403
    )
    line_url = f"/api/v1/finance/vendor-bills/{created.data['id']}/lines/"
    line_adder = UserFactory.create()
    grant(line_adder, g["company"], "add_vendorbillline")
    line = api(line_adder).post(line_url, line_payload(g), format="json")
    assert line.status_code == 201
    assert (
        api(line_adder)
        .patch(f"{line_url}{line.data['id']}/", {"quantity": "3"}, format="json")
        .status_code
        == 403
    )
    line_editor = UserFactory.create()
    grant(line_editor, g["company"], "change_vendorbillline")
    assert (
        api(line_editor)
        .patch(f"{line_url}{line.data['id']}/", {"quantity": "3"}, format="json")
        .status_code
        == 200
    )
    assert api(line_editor).delete(f"{line_url}{line.data['id']}/").status_code == 403
    line_deleter = UserFactory.create()
    grant(line_deleter, g["company"], "delete_vendorbillline")
    assert api(line_deleter).delete(f"{line_url}{line.data['id']}/").status_code == 204


def test_line_crud_recalculates_authoritative_totals_and_is_draft_only() -> None:
    g = graph()
    _user, client = author(g)
    created = client.post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    url = f"/api/v1/finance/vendor-bills/{created.data['id']}/lines/"
    line = client.post(url, line_payload(g), format="json")
    assert line.status_code == 201, line.data
    bill = VendorBill.objects.get(pk=created.data["id"])
    assert (bill.subtotal, bill.tax_amount, bill.total_amount) == (
        Decimal("200.00"),
        Decimal("20.00"),
        Decimal("220.00"),
    )
    assert (
        client.patch(
            f"/api/v1/finance/vendor-bills/{bill.id}/",
            {"match_type": MatchType.THREE_WAY},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/v1/finance/vendor-bills/{bill.id}/",
            {"purchase_order": None},
            format="json",
        ).status_code
        == 400
    )
    line_url = f"{url}{line.data['id']}/"
    assert (
        client.patch(line_url, {"quantity": "3", "tax_amount": "30"}, format="json").status_code
        == 200
    )
    bill.refresh_from_db()
    assert (bill.subtotal, bill.tax_amount, bill.total_amount) == (
        Decimal("300.00"),
        Decimal("30.00"),
        Decimal("330.00"),
    )
    assert client.delete(line_url).status_code == 204
    bill.refresh_from_db()
    assert (bill.subtotal, bill.tax_amount, bill.total_amount) == (
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )
    bill.status = WorkflowStatus.SUBMITTED
    bill.save(update_fields=["status"])
    assert (
        client.patch(
            f"/api/v1/finance/vendor-bills/{bill.id}/", {"due_date": "2026-11-01"}
        ).status_code
        == 400
    )
    assert client.post(url, line_payload(g), format="json").status_code == 400


@pytest.mark.parametrize(
    "kind", ["cross", "inactive", "nonposting", "LIABILITY", "REVENUE", "EQUITY"]
)
def test_expense_account_policy(kind: str) -> None:
    g = graph()
    _user, client = author(g)
    bill = client.post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    if kind == "cross":
        other = graph()
        account = other["accounts"]["expense"]
    else:
        account_type = AccountType.EXPENSE if kind in {"inactive", "nonposting"} else kind
        account = services.create_account(
            company=g["company"],
            code=f"X-{kind}",
            name=kind,
            account_type=account_type,
            allow_posting=kind != "nonposting",
        )
        if kind == "inactive":
            account.is_active = False
            account.save(update_fields=["is_active"])
    response = client.post(
        f"/api/v1/finance/vendor-bills/{bill.data['id']}/lines/",
        line_payload(g, expense_account=str(account.id)),
        format="json",
    )
    assert response.status_code == 400
    assert "expense_account" in response.data


def test_asset_account_three_way_relationships_and_nested_line_scope() -> None:
    g, other = graph(), graph()
    _user, client = author(g)
    bill = client.post(
        "/api/v1/finance/vendor-bills/",
        bill_payload(g, match_type=MatchType.THREE_WAY),
        format="json",
    )
    valid = client.post(
        f"/api/v1/finance/vendor-bills/{bill.data['id']}/lines/",
        line_payload(g, expense_account=str(g["asset"].id), receipt_line=str(g["receipt_line"].id)),
        format="json",
    )
    assert valid.status_code == 201, valid.data
    unrelated = client.post(
        f"/api/v1/finance/vendor-bills/{bill.data['id']}/lines/",
        line_payload(g, receipt_line=str(other["receipt_line"].id)),
        format="json",
    )
    assert unrelated.status_code == 400
    other_bill = VendorBill.objects.create(
        company=g["company"],
        vendor=g["vendor"],
        vendor_invoice_number="OTHER",
        bill_number="B2",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 9, 2),
        created_by=g["maker"],
    )
    assert (
        client.delete(
            f"/api/v1/finance/vendor-bills/{other_bill.id}/lines/{valid.data['id']}/"
        ).status_code
        == 404
    )


def test_duplicate_vendor_reference_and_legacy_total_hardening() -> None:
    g = graph()
    _user, client = author(g)
    first = client.post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    assert first.status_code == 201
    duplicate = client.post(
        "/api/v1/finance/vendor-bills/", bill_payload(g, bill_number="BILL-2"), format="json"
    )
    assert duplicate.status_code == 400
    assert "vendor_invoice_number" in duplicate.data
    reference = client.get("/api/v1/finance/ap-reference/expense-accounts/")
    assert reference.status_code == 200
    assert {row["account_type"] for row in reference.data} == {"ASSET", "EXPENSE"}
    assert all(set(row) == {"id", "code", "name", "account_type"} for row in reference.data)
    assert not _user.has_perm("finance.manage_chart_of_accounts")
    superuser = UserFactory.create(is_superuser=True)
    legacy = api(superuser).post(
        "/api/v1/finance/domain/vendor-bills/",
        bill_payload(
            g,
            vendor_invoice_number="LEGACY",
            company=str(g["company"].id),
            created_by=str(UserFactory.create().id),
        ),
        format="json",
    )
    assert legacy.status_code == 201, legacy.data
    stored = VendorBill.objects.get(pk=legacy.data["id"])
    assert (stored.subtotal, stored.tax_amount, stored.total_amount, stored.paid_amount) == (
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
    )


def test_sequential_workflow_is_least_privilege_balanced_and_idempotent() -> None:
    g = graph()
    maker, maker_client = author(g)
    created = maker_client.post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    bill_id = created.data["id"]
    assert (
        maker_client.post(
            f"/api/v1/finance/vendor-bills/{bill_id}/submit/", {}, format="json"
        ).status_code
        == 400
    )
    line = maker_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/lines/", line_payload(g), format="json"
    )
    assert line.status_code == 201
    submitted = maker_client.post(
        f"/api/v1/finance/vendor-bills/{bill_id}/submit/",
        {"status": "POSTED", "journal_entry": str(g["company"].id)},
        format="json",
    )
    assert submitted.status_code == 200
    assert submitted.data["status"] == WorkflowStatus.SUBMITTED
    assert not maker.has_perm("finance.manage_procurement")

    grant(maker, g["company"], "approve_finance")
    assert (
        api(maker)
        .post(f"/api/v1/finance/vendor-bills/{bill_id}/approve/", {}, format="json")
        .status_code
        == 400
    )
    checker = UserFactory.create()
    grant(checker, g["company"], "approve_finance", "post_journal")
    approved = api(checker).post(
        f"/api/v1/finance/vendor-bills/{bill_id}/approve/", {}, format="json"
    )
    assert approved.status_code == 200
    assert approved.data["status"] == WorkflowStatus.APPROVED
    g["vendor"].payable_account.is_active = False
    g["vendor"].payable_account.save(update_fields=["is_active"])
    assert (
        api(checker)
        .post(f"/api/v1/finance/vendor-bills/{bill_id}/post/", {}, format="json")
        .status_code
        == 400
    )
    assert VendorBill.objects.get(pk=bill_id).journal_entry_id is None
    g["vendor"].payable_account.is_active = True
    g["vendor"].payable_account.save(update_fields=["is_active"])
    g["accounts"]["expense"].allow_posting = False
    g["accounts"]["expense"].save(update_fields=["allow_posting"])
    assert (
        api(checker)
        .post(f"/api/v1/finance/vendor-bills/{bill_id}/post/", {}, format="json")
        .status_code
        == 400
    )
    assert VendorBill.objects.get(pk=bill_id).journal_entry_id is None
    g["accounts"]["expense"].allow_posting = True
    g["accounts"]["expense"].save(update_fields=["allow_posting"])
    posted = api(checker).post(
        f"/api/v1/finance/vendor-bills/{bill_id}/post/",
        {"total_amount": "1.00", "company": str(CompanyFactory.create().id)},
        format="json",
    )
    assert posted.status_code == 200, posted.data
    assert posted.data["status"] == WorkflowStatus.POSTED
    bill = VendorBill.objects.get(pk=bill_id)
    journal_id = bill.journal_entry_id
    assert journal_id is not None
    journal = bill.journal_entry
    assert journal is not None
    assert journal.total_debit == Decimal("220.00")
    assert journal.total_credit == Decimal("220.00")
    assert (
        api(checker)
        .post(f"/api/v1/finance/vendor-bills/{bill_id}/post/", {}, format="json")
        .status_code
        == 200
    )
    bill.refresh_from_db()
    assert bill.journal_entry_id == journal_id
    assert FinanceApprovalHistory.objects.filter(object_id=bill.id).count() == 2


def test_reject_requires_independent_checker_and_reason() -> None:
    g = graph()
    maker, client = author(g)
    created = client.post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    client.post(
        f"/api/v1/finance/vendor-bills/{created.data['id']}/lines/",
        line_payload(g),
        format="json",
    )
    client.post(f"/api/v1/finance/vendor-bills/{created.data['id']}/submit/", {}, format="json")
    grant(maker, g["company"], "approve_finance")
    url = f"/api/v1/finance/vendor-bills/{created.data['id']}/reject/"
    assert api(maker).post(url, {"reason": "Incorrect"}, format="json").status_code == 400
    checker = UserFactory.create()
    grant(checker, g["company"], "approve_finance")
    assert api(checker).post(url, {}, format="json").status_code == 400
    result = api(checker).post(url, {"reason": "Incorrect price"}, format="json")
    assert result.status_code == 200
    assert result.data["status"] == WorkflowStatus.REJECTED


def test_vendor_bill_private_attachments_are_nested_and_company_scoped(settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private-finance"
    g, other = graph(), graph()
    _maker, client = author(g)
    bill = client.post("/api/v1/finance/vendor-bills/", bill_payload(g), format="json")
    attachment_user = UserFactory.create()
    grant(attachment_user, g["company"], "manage_finance_attachments")
    attachment_client = api(attachment_user)
    url = f"/api/v1/finance/vendor-bills/{bill.data['id']}/attachments/"
    uploaded = attachment_client.post(
        url,
        {
            "company": str(other["company"].id),
            "object_id": str(other["company"].id),
            "file": SimpleUploadedFile("invoice.pdf", b"%PDF-1.4\n%%EOF"),
        },
        format="multipart",
    )
    assert uploaded.status_code == 201, uploaded.data
    assert set(uploaded.data) == {"id", "filename", "content_type", "size", "created_at"}
    item = FinanceAttachment.objects.get(pk=uploaded.data["id"])
    assert (item.company_id, item.object_id, item.uploaded_by_id) == (
        g["company"].id,
        VendorBill.objects.get(pk=bill.data["id"]).id,
        attachment_user.id,
    )
    assert attachment_client.get(url).data == [uploaded.data]
    download = attachment_client.get(f"{url}{item.id}/download/")
    assert download.status_code == 200
    assert download["Cache-Control"] == "private, no-store"
    assert "url" not in uploaded.data and "file" not in uploaded.data
    no_permission = UserFactory.create()
    assert api(no_permission).get(url).status_code == 403
    wrong_bill = VendorBill.objects.create(
        company=g["company"],
        vendor=g["vendor"],
        vendor_invoice_number="OTHER-ATTACHMENT",
        bill_number="OTHER-ATTACHMENT",
        bill_date=date(2026, 9, 3),
        due_date=date(2026, 10, 3),
        created_by=g["maker"],
    )
    assert (
        attachment_client.get(
            f"/api/v1/finance/vendor-bills/{wrong_bill.id}/attachments/{item.id}/download/"
        ).status_code
        == 404
    )
    grant(attachment_user, other["company"], "manage_finance_attachments")
    foreign_bill = VendorBill.objects.create(
        company=other["company"],
        vendor=other["vendor"],
        vendor_invoice_number="FOREIGN-ATTACHMENT",
        bill_number="FOREIGN-ATTACHMENT",
        bill_date=date(2026, 9, 3),
        due_date=date(2026, 10, 3),
        created_by=other["maker"],
    )
    assert (
        attachment_client.get(
            f"/api/v1/finance/vendor-bills/{foreign_bill.id}/attachments/{item.id}/download/"
        ).status_code
        == 404
    )
