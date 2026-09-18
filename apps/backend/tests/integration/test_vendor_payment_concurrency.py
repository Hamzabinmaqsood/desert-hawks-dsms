from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import close_old_connections

from dsms.finance import domain_services
from dsms.finance.enums import PaymentStatus, WorkflowStatus
from dsms.finance.exceptions import FinanceError
from dsms.finance.operations_models import CashAccount
from dsms.finance.procurement_models import PaymentVoucher, Vendor, VendorBill
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_direct_payments_cannot_overpay_vendor_bill() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    CashAccount.objects.create(
        company=company, name="Race Cash", ledger_account=accounts["cash"], custodian=maker
    )
    vendor = Vendor.objects.create(
        company=company, code="V-RACE", name="Race Supplier", payable_account=accounts["payable"]
    )
    bill = VendorBill.objects.create(
        company=company,
        vendor=vendor,
        vendor_invoice_number="RACE-1",
        bill_number="RACE-1",
        bill_date=date(2026, 8, 15),
        due_date=date(2026, 9, 15),
        status=WorkflowStatus.POSTED,
        subtotal=Decimal("100.00"),
        total_amount=Decimal("100.00"),
        created_by=maker,
        approved_by=checker,
    )
    vouchers = [
        PaymentVoucher.objects.create(
            company=company,
            vendor_bill=bill,
            voucher_number=f"PV-RACE-{index}",
            payment_date=date(2026, 8, 18),
            amount=Decimal("70.00"),
            status=WorkflowStatus.APPROVED,
            payment_status=PaymentStatus.PENDING,
            created_by=maker,
            approved_by=checker,
        )
        for index in range(2)
    ]
    barrier = Barrier(2)

    def pay(voucher_id) -> bool:  # type: ignore[no-untyped-def]
        close_old_connections()
        barrier.wait()
        try:
            domain_services.pay_vendor_voucher(
                voucher=PaymentVoucher.objects.get(pk=voucher_id),
                actor=checker,
                cash_account=accounts["cash"],
                reference=str(voucher_id),
            )
            return True
        except FinanceError:
            return False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(pay, [voucher.id for voucher in vouchers]))
    bill.refresh_from_db()
    assert sorted(results) == [False, True]
    assert bill.paid_amount == Decimal("70.00")
    assert bill.outstanding_amount == Decimal("30.00")
    assert Decimal("0.00") <= bill.paid_amount <= bill.total_amount
