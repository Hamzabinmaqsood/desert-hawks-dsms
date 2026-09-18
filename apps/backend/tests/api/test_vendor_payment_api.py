from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.finance.enums import AccountType, PaymentStatus, WorkflowStatus
from dsms.finance.models import JournalEntry
from dsms.finance.operations_models import CashAccount
from dsms.finance.procurement_models import PaymentVoucher, Vendor, VendorBill
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


def payment_graph(total: Decimal = Decimal("100.00")) -> dict[str, Any]:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    CashAccount.objects.create(
        company=company, name="Payment Cash", ledger_account=accounts["cash"], custodian=maker
    )
    vendor = Vendor.objects.create(
        company=company, code="V-PAY", name="Payment Supplier", payable_account=accounts["payable"]
    )
    bill = VendorBill.objects.create(
        company=company,
        vendor=vendor,
        vendor_invoice_number="SUP-PAY-1",
        bill_number="BILL-PAY-1",
        bill_date=date(2026, 8, 15),
        due_date=date(2026, 9, 15),
        status=WorkflowStatus.POSTED,
        subtotal=total,
        total_amount=total,
        created_by=maker,
        approved_by=checker,
    )
    return locals()


def test_payment_voucher_lifecycle_is_scoped_balanced_and_idempotent() -> None:
    g = payment_graph(Decimal("100.00"))
    grant(
        g["maker"],
        g["company"],
        "view_paymentvoucher",
        "add_paymentvoucher",
        "change_paymentvoucher",
    )
    grant(
        g["checker"],
        g["company"],
        "view_paymentvoucher",
        "approve_finance",
        "post_journal",
    )
    created = api(g["maker"]).post(
        "/api/v1/finance/vendor-payments/",
        {
            "vendor_bill": str(g["bill"].id),
            "voucher_number": "PV-API-1",
            "payment_date": "2026-08-18",
            "amount": "70.00",
            "payment_reference": "DRAFT-REF",
            "company": str(CompanyFactory.create().id),
            "status": WorkflowStatus.PAID,
            "payment_status": PaymentStatus.PAID,
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert (created.data["status"], created.data["payment_status"]) == (
        WorkflowStatus.DRAFT,
        PaymentStatus.PENDING,
    )
    voucher_id = created.data["id"]
    submitted = api(g["maker"]).post(
        f"/api/v1/finance/vendor-payments/{voucher_id}/submit/", {}, format="json"
    )
    assert submitted.data["status"] == WorkflowStatus.SUBMITTED
    grant(g["maker"], g["company"], "approve_finance")
    assert (
        api(g["maker"])
        .post(f"/api/v1/finance/vendor-payments/{voucher_id}/approve/", {}, format="json")
        .status_code
        == 400
    )
    approved = api(g["checker"]).post(
        f"/api/v1/finance/vendor-payments/{voucher_id}/approve/", {}, format="json"
    )
    assert approved.data["status"] == WorkflowStatus.APPROVED
    paid = api(g["checker"]).post(
        f"/api/v1/finance/vendor-payments/{voucher_id}/pay/",
        {
            "payment_account": str(g["accounts"]["cash"].id),
            "payment_reference": "BANK-API-1",
            "journal_entry": str(g["bill"].id),
            "paid_amount": "999.00",
        },
        format="json",
    )
    assert paid.status_code == 200, paid.data
    voucher = PaymentVoucher.objects.get(pk=voucher_id)
    g["bill"].refresh_from_db()
    assert (voucher.status, voucher.payment_status) == (
        WorkflowStatus.PAID,
        PaymentStatus.PAID,
    )
    assert voucher.journal_entry is not None
    assert voucher.journal_entry.total_debit == Decimal("70.00")
    assert voucher.journal_entry.total_credit == Decimal("70.00")
    assert g["bill"].paid_amount == Decimal("70.00")
    assert g["bill"].outstanding_amount == Decimal("30.00")
    assert g["bill"].status == WorkflowStatus.PARTIALLY_PAID
    journal_id = voucher.journal_entry_id
    replay = api(g["checker"]).post(
        f"/api/v1/finance/vendor-payments/{voucher_id}/pay/",
        {"payment_account": str(g["accounts"]["cash"].id)},
        format="json",
    )
    assert replay.status_code == 200
    voucher.refresh_from_db()
    g["bill"].refresh_from_db()
    assert voucher.journal_entry_id == journal_id
    assert g["bill"].paid_amount == Decimal("70.00")


def test_full_payment_closes_bill_exactly() -> None:
    g = payment_graph(Decimal("100.00"))
    voucher = PaymentVoucher.objects.create(
        company=g["company"],
        vendor_bill=g["bill"],
        voucher_number="PV-FULL",
        payment_date=date(2026, 8, 18),
        amount=Decimal("100.00"),
        status=WorkflowStatus.APPROVED,
        created_by=g["maker"],
        approved_by=g["checker"],
    )
    grant(g["checker"], g["company"], "post_journal")
    response = api(g["checker"]).post(
        f"/api/v1/finance/vendor-payments/{voucher.id}/pay/",
        {"payment_account": str(g["accounts"]["cash"].id)},
        format="json",
    )
    assert response.status_code == 200, response.data
    g["bill"].refresh_from_db()
    assert g["bill"].paid_amount == Decimal("100.00")
    assert g["bill"].outstanding_amount == Decimal("0.00")
    assert g["bill"].status == WorkflowStatus.PAID


def test_payment_validation_rejects_ineligible_bill_amount_and_accounts() -> None:
    g = payment_graph()
    grant(g["maker"], g["company"], "add_paymentvoucher", "change_paymentvoucher")
    client = api(g["maker"])
    base = {
        "vendor_bill": str(g["bill"].id),
        "voucher_number": "PV-INVALID",
        "payment_date": "2026-08-18",
        "amount": "101.00",
    }
    assert client.post("/api/v1/finance/vendor-payments/", base, format="json").status_code == 400
    base["amount"] = "0.00"
    assert client.post("/api/v1/finance/vendor-payments/", base, format="json").status_code == 400
    other = payment_graph()
    base.update(vendor_bill=str(other["bill"].id), amount="10.00")
    assert client.post("/api/v1/finance/vendor-payments/", base, format="json").status_code == 404


@pytest.mark.parametrize(
    "mutation", ["type", "unrelated_asset", "inactive", "nonposting", "foreign"]
)
def test_pay_rejects_invalid_payment_account(mutation: str) -> None:
    g = payment_graph()
    voucher = PaymentVoucher.objects.create(
        company=g["company"],
        vendor_bill=g["bill"],
        voucher_number=f"PV-{mutation}",
        payment_date=date(2026, 8, 18),
        amount=Decimal("50.00"),
        status=WorkflowStatus.APPROVED,
        created_by=g["maker"],
        approved_by=g["checker"],
    )
    grant(g["checker"], g["company"], "post_journal")
    account = g["accounts"]["cash"]
    if mutation == "type":
        account = g["accounts"]["expense"]
    elif mutation == "unrelated_asset":
        account = g["accounts"]["bank"]
    elif mutation == "inactive":
        account.is_active = False
        account.save(update_fields=["is_active"])
    elif mutation == "nonposting":
        account.allow_posting = False
        account.save(update_fields=["allow_posting"])
    else:
        other = payment_graph()
        account = other["accounts"]["cash"]
    result = api(g["checker"]).post(
        f"/api/v1/finance/vendor-payments/{voucher.id}/pay/",
        {"payment_account": str(account.id)},
        format="json",
    )
    assert result.status_code in {400, 404}
    voucher.refresh_from_db()
    g["bill"].refresh_from_db()
    assert voucher.journal_entry_id is None
    assert g["bill"].paid_amount == Decimal("0.00")


def test_payment_references_and_bill_history_are_least_privilege() -> None:
    g = payment_graph()
    PaymentVoucher.objects.create(
        company=g["company"],
        vendor_bill=g["bill"],
        voucher_number="PV-HISTORY",
        payment_date=date(2026, 8, 18),
        amount=Decimal("25.00"),
        created_by=g["maker"],
    )
    grant(g["maker"], g["company"], "view_paymentvoucher")
    client = api(g["maker"])
    assert len(client.get("/api/v1/finance/ap-reference/payable-bills/").data) == 1
    accounts = client.get("/api/v1/finance/ap-reference/payment-accounts/").data
    assert all(item["account_type"] == AccountType.ASSET for item in accounts)
    grant(g["maker"], g["company"], "view_vendorbill")
    detail = client.get(f"/api/v1/finance/vendor-bills/{g['bill'].id}/")
    assert detail.data["payments"][0]["voucher_number"] == "PV-HISTORY"
    assert "journal_entry" not in detail.data["payments"][0]


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_payment_projection_enforces_voucher_company(multi_company_access: bool) -> None:
    company_a, company_b = payment_graph(), payment_graph()
    company_b["vendor"].name = "Hidden Foreign Vendor"
    company_b["vendor"].save(update_fields=["name"])
    company_b["bill"].bill_number = "HIDDEN-FOREIGN-BILL"
    company_b["bill"].vendor_invoice_number = "HIDDEN-FOREIGN-INVOICE"
    company_b["bill"].save(update_fields=["bill_number", "vendor_invoice_number"])
    valid = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=company_a["bill"],
        voucher_number="PV-TENANT-VALID",
        payment_date=date(2026, 9, 1),
        amount=Decimal("25.00"),
        payment_reference="VISIBLE-REFERENCE",
        created_by=company_a["maker"],
    )
    foreign_bill = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=company_b["bill"],
        voucher_number="PV-TENANT-FOREIGN-BILL",
        payment_date=date(2026, 9, 1),
        amount=Decimal("25.00"),
        created_by=company_a["maker"],
    )
    corrupt_bill = VendorBill.objects.create(
        company=company_a["company"],
        vendor=company_b["vendor"],
        vendor_invoice_number="CORRUPT-VENDOR-CHAIN",
        bill_number="CORRUPT-VENDOR-CHAIN",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 10, 1),
        status=WorkflowStatus.POSTED,
        total_amount=Decimal("25.00"),
        created_by=company_a["maker"],
    )
    foreign_vendor = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=corrupt_bill,
        voucher_number="PV-TENANT-FOREIGN-VENDOR",
        payment_date=date(2026, 9, 1),
        amount=Decimal("25.00"),
        created_by=company_a["maker"],
    )
    without_bill = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=None,
        voucher_number="PV-TENANT-NULL-BILL",
        payment_date=date(2026, 9, 1),
        amount=Decimal("25.00"),
        created_by=company_a["maker"],
    )
    user = UserFactory.create()
    grant(user, company_a["company"], "view_paymentvoucher", "manage_procurement")
    if multi_company_access:
        grant(user, company_b["company"], "view_paymentvoucher", "manage_procurement")
    client = api(user)

    valid_detail = client.get(f"/api/v1/finance/vendor-payments/{valid.id}/")
    null_detail = client.get(f"/api/v1/finance/vendor-payments/{without_bill.id}/")
    foreign_bill_detail = client.get(f"/api/v1/finance/vendor-payments/{foreign_bill.id}/")
    foreign_vendor_detail = client.get(f"/api/v1/finance/vendor-payments/{foreign_vendor.id}/")
    listed = client.get("/api/v1/finance/vendor-payments/")
    legacy_list = client.get("/api/v1/finance/domain/payment-vouchers/")

    assert valid_detail.status_code == 200
    assert valid_detail.data["vendor_bill"] == company_a["bill"].id
    assert valid_detail.data["bill_number"] == "BILL-PAY-1"
    assert valid_detail.data["vendor_name"] == "Payment Supplier"
    assert valid_detail.data["voucher_number"] == "PV-TENANT-VALID"
    assert valid_detail.data["payment_reference"] == "VISIBLE-REFERENCE"
    assert null_detail.status_code == 200
    assert null_detail.data["vendor_bill"] is None
    assert null_detail.data.get("bill_number") is None
    assert null_detail.data.get("vendor_name") is None
    assert foreign_bill_detail.status_code == 404
    assert foreign_vendor_detail.status_code == 404
    expected_ids = {str(valid.id), str(without_bill.id)}
    assert {row["id"] for row in listed.data["results"]} == expected_ids
    assert {row["id"] for row in legacy_list.data} == expected_ids
    assert (
        client.get(f"/api/v1/finance/domain/payment-vouchers/{foreign_bill.id}/").status_code == 404
    )
    assert (
        client.get(f"/api/v1/finance/domain/payment-vouchers/{foreign_vendor.id}/").status_code
        == 404
    )
    serialized = str(listed.data) + str(legacy_list.data)
    assert str(foreign_bill.id) not in serialized
    assert str(foreign_vendor.id) not in serialized
    assert str(company_b["bill"].id) not in serialized
    assert company_b["bill"].bill_number not in serialized
    assert company_b["vendor"].name not in serialized
    assert corrupt_bill.bill_number not in serialized


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_legacy_payment_journal_enforces_voucher_company(multi_company_access: bool) -> None:
    company_a, company_b = payment_graph(), payment_graph()
    journal_a = JournalEntry.objects.create(
        company=company_a["company"],
        fiscal_year=company_a["_year"],
        accounting_period=company_a["_period"],
        journal_number="JV-TENANT-A",
        entry_date=date(2026, 9, 1),
        description="Visible same-company journal",
        created_by=company_a["maker"],
    )
    journal_b = JournalEntry.objects.create(
        company=company_b["company"],
        fiscal_year=company_b["_year"],
        accounting_period=company_b["_period"],
        journal_number="JV-TENANT-B",
        entry_date=date(2026, 9, 1),
        description="Hidden foreign journal",
        created_by=company_b["maker"],
    )
    without_journal = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=company_a["bill"],
        voucher_number="PV-JOURNAL-NULL",
        payment_date=date(2026, 9, 1),
        amount=Decimal("25.00"),
        created_by=company_a["maker"],
    )
    same_company = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=company_a["bill"],
        journal_entry=journal_a,
        voucher_number="PV-JOURNAL-VALID",
        payment_date=date(2026, 9, 1),
        amount=Decimal("25.00"),
        created_by=company_a["maker"],
    )
    corrupt = PaymentVoucher.objects.create(
        company=company_a["company"],
        vendor_bill=company_a["bill"],
        journal_entry=journal_b,
        voucher_number="PV-JOURNAL-CORRUPT",
        payment_date=date(2026, 9, 1),
        amount=Decimal("25.00"),
        created_by=company_a["maker"],
    )
    user = UserFactory.create()
    grant(
        user,
        company_a["company"],
        "view_paymentvoucher",
        "change_paymentvoucher",
        "manage_procurement",
    )
    if multi_company_access:
        grant(
            user,
            company_b["company"],
            "view_paymentvoucher",
            "change_paymentvoucher",
            "manage_procurement",
        )
    client = api(user)

    listed = client.get("/api/v1/finance/domain/payment-vouchers/")
    null_detail = client.get(f"/api/v1/finance/domain/payment-vouchers/{without_journal.id}/")
    valid_detail = client.get(f"/api/v1/finance/domain/payment-vouchers/{same_company.id}/")
    corrupt_detail = client.get(f"/api/v1/finance/domain/payment-vouchers/{corrupt.id}/")
    corrupt_action = client.post(
        f"/api/v1/finance/domain/payment-vouchers/{corrupt.id}/submit/", {}, format="json"
    )
    dedicated_detail = client.get(f"/api/v1/finance/vendor-payments/{corrupt.id}/")
    dedicated_submit = client.post(
        f"/api/v1/finance/vendor-payments/{corrupt.id}/submit/", {}, format="json"
    )

    expected_ids = {str(without_journal.id), str(same_company.id)}
    assert {row["id"] for row in listed.data} == expected_ids
    assert null_detail.status_code == 200
    assert null_detail.data["journal_entry"] is None
    assert valid_detail.status_code == 200
    assert valid_detail.data["journal_entry"] == journal_a.id
    assert corrupt_detail.status_code == 404
    assert corrupt_action.status_code == 404
    assert str(corrupt.id) not in str(listed.data)
    assert str(journal_b.id) not in str(listed.data)
    assert dedicated_detail.status_code == 200
    assert "journal_entry" not in dedicated_detail.data
    assert dedicated_submit.status_code == 400
