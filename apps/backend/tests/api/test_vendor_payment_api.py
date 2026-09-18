from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.finance.enums import AccountType, PaymentStatus, WorkflowStatus
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
