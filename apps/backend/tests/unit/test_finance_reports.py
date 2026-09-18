from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import domain_selectors, services
from dsms.finance.models import JournalEntry
from dsms.finance.procurement_models import PaymentVoucher, Vendor, VendorBill
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_profit_loss_balance_sheet_and_dashboard_use_posted_entries() -> None:
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    year, period, accounts = accounting_setup(company)
    journal = services.create_journal(
        company=company,
        fiscal_year=year,
        accounting_period=period,
        entry_date=date(2026, 8, 1),
        description="Expense",
        created_by=maker,
        lines=[
            {"account": accounts["expense"], "debit": Decimal("80")},
            {"account": accounts["cash"], "credit": Decimal("80")},
        ],
    )
    journal = services.submit_journal(journal=journal, actor=maker)
    journal = services.approve_journal(journal=journal, actor=checker)
    services.post_journal(journal=journal, actor=checker)
    pnl = domain_selectors.profit_and_loss(
        company_id=company.id, date_from=date(2026, 8, 1), date_to=date(2026, 8, 31)
    )
    assert pnl["expenses"] == Decimal("80") and pnl["automated_revenue_complete"] is False
    assert domain_selectors.balance_sheet(company_id=company.id, date_to=date(2026, 8, 31))[
        "assets"
    ] == Decimal("-80")
    assert domain_selectors.dashboard_summary(company_id=company.id)[
        "bank_cash_position"
    ] == Decimal("-80")


def test_exception_center_detects_missing_compensation() -> None:
    company = CompanyFactory.create()
    employee = EmployeeFactory.create(company=company)
    rows = domain_selectors.finance_exceptions(company_id=company.id, as_of=date(2026, 8, 18))
    assert {
        "code": "MISSING_COMPENSATION",
        "object_id": employee.id,
        "message": "Employee has no current compensation.",
    } in rows


def test_ap_reports_exclude_tenant_inconsistent_relations() -> None:
    company_a, company_b = CompanyFactory.create(), CompanyFactory.create()
    maker = UserFactory.create()
    year_a, period_a, accounts_a = accounting_setup(company_a)
    year_b, period_b, accounts_b = accounting_setup(company_b)
    vendor_a = Vendor.objects.create(
        company=company_a, code="V-A", name="Visible Vendor", payable_account=accounts_a["payable"]
    )
    vendor_b = Vendor.objects.create(
        company=company_b,
        code="V-B",
        name="Hidden Foreign Vendor",
        payable_account=accounts_b["payable"],
    )
    valid = VendorBill.objects.create(
        company=company_a,
        vendor=vendor_a,
        vendor_invoice_number="REPORT-VALID",
        bill_number="REPORT-VALID",
        bill_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        total_amount=Decimal("100"),
        created_by=maker,
    )
    corrupt_vendor = VendorBill.objects.create(
        company=company_a,
        vendor=vendor_b,
        vendor_invoice_number="REPORT-FOREIGN-VENDOR",
        bill_number="REPORT-FOREIGN-VENDOR",
        bill_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        total_amount=Decimal("900"),
        created_by=maker,
    )
    foreign_journal = JournalEntry.objects.create(
        company=company_b,
        fiscal_year=year_b,
        accounting_period=period_b,
        journal_number="JV-REPORT-B",
        entry_date=date(2026, 8, 1),
        description="Hidden foreign journal",
        created_by=maker,
    )
    corrupt_journal = VendorBill.objects.create(
        company=company_a,
        vendor=vendor_a,
        journal_entry=foreign_journal,
        vendor_invoice_number="REPORT-FOREIGN-JOURNAL",
        bill_number="REPORT-FOREIGN-JOURNAL",
        bill_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        total_amount=Decimal("800"),
        created_by=maker,
    )
    valid_voucher = PaymentVoucher.objects.create(
        company=company_a,
        vendor_bill=valid,
        voucher_number="PV-REPORT-VALID",
        payment_date=date(2026, 8, 2),
        amount=Decimal("25"),
        created_by=maker,
    )
    corrupt_voucher = PaymentVoucher.objects.create(
        company=company_a,
        vendor_bill=corrupt_vendor,
        voucher_number="PV-REPORT-CORRUPT",
        payment_date=date(2026, 8, 2),
        amount=Decimal("25"),
        created_by=maker,
    )
    _ = (year_a, period_a, corrupt_journal)

    aging = domain_selectors.accounts_payable_aging(company_id=company_a.id, as_of=date(2026, 9, 1))
    ledger = list(
        domain_selectors.REPORT_QUERYSETS["vendor-ledger"](company_a.id)  # type: ignore[no-untyped-call]
    )
    outstanding = domain_selectors.REPORT_QUERYSETS["outstanding-bills"](company_a.id)  # type: ignore[no-untyped-call]
    payments = domain_selectors.REPORT_QUERYSETS["payment-register"](company_a.id)  # type: ignore[no-untyped-call]

    assert aging == [
        {
            "bill": valid.id,
            "vendor": "Visible Vendor",
            "due_date": date(2026, 8, 31),
            "outstanding": Decimal("100"),
            "bucket": "1_30",
        }
    ]
    assert ledger == [
        {
            "vendor__code": "V-A",
            "vendor__name": "Visible Vendor",
            "billed": Decimal("100"),
            "paid": Decimal("0"),
        }
    ]
    assert list(outstanding.values_list("id", flat=True)) == [valid.id]
    assert list(payments.values_list("id", flat=True)) == [valid_voucher.id]
    serialized = (
        str(aging) + str(ledger) + str(list(outstanding.values())) + str(list(payments.values()))
    )
    assert str(corrupt_vendor.id) not in serialized
    assert str(corrupt_voucher.id) not in serialized
    assert str(vendor_b.id) not in serialized
    assert vendor_b.name not in serialized
    assert str(foreign_journal.id) not in serialized
