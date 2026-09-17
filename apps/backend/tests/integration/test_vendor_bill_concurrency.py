from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier

import pytest
from django.db import close_old_connections

from dsms.finance.enums import WorkflowStatus
from dsms.finance.procurement_models import Vendor, VendorBill
from dsms.finance.vendor_bill_services import add_vendor_bill_line
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db(transaction=True)


def test_concurrent_line_creates_preserve_persisted_totals() -> None:
    company = CompanyFactory.create()
    actor = UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    vendor = Vendor.objects.create(
        company=company, code="V-CON", name="Concurrent", payable_account=accounts["payable"]
    )
    bill = VendorBill.objects.create(
        company=company,
        vendor=vendor,
        vendor_invoice_number="CON-1",
        bill_number="B-CON-1",
        bill_date=date(2026, 9, 1),
        due_date=date(2026, 10, 1),
        status=WorkflowStatus.DRAFT,
        created_by=actor,
    )
    gate = Barrier(2)

    def create_line(quantity: str) -> None:
        close_old_connections()
        try:
            local_bill = VendorBill.objects.get(pk=bill.pk)
            account = type(accounts["expense"]).objects.get(pk=accounts["expense"].pk)
            gate.wait()
            add_vendor_bill_line(
                bill=local_bill,
                values={
                    "description": f"Line {quantity}",
                    "quantity": Decimal(quantity),
                    "unit_price": Decimal("100.00"),
                    "tax_amount": Decimal("10.00"),
                    "expense_account": account,
                },
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(create_line, ["1", "2"]))

    bill.refresh_from_db()
    assert bill.lines.count() == 2
    assert bill.subtotal == Decimal("300.00")
    assert bill.tax_amount == Decimal("20.00")
    assert bill.total_amount == Decimal("320.00")
    assert sum((line.line_total for line in bill.lines.all()), Decimal("0")) == bill.total_amount
