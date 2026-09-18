from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.finance.crypto import decrypt_payment_destination
from dsms.finance.models import JournalEntry
from dsms.finance.payment_models import (
    PaymentBatch,
    PaymentBeneficiaryProfile,
    PaymentInstruction,
    PaymentProviderConfiguration,
    PaymentProviderSettlement,
    ProviderType,
)
from dsms.finance.payroll_models import PayrollPeriod, PayrollRun, Payslip
from dsms.finance.procurement_models import PaymentVoucher, Vendor, VendorBill
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from tests.factories.finance import accounting_setup
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def grant(user: User, company: object, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.add(
        *Permission.objects.filter(content_type__app_label="finance", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user, role=role, scope_type=AccessScopeType.COMPANY, company=company
    )


def test_payment_destination_api_masks_and_separates_approval_steps() -> None:
    company = CompanyFactory.create()
    employee = EmployeeFactory.create(company=company)
    requester, verifier, approver, activator = UserFactory.create_batch(4, is_superuser=True)
    client = APIClient()
    client.force_authenticate(requester)
    created = client.post(
        "/api/v1/finance/payment-beneficiaries/",
        {
            "company": str(company.id),
            "employee": str(employee.id),
            "destination": "03123456789",
            "account_title": "Employee",
            "provider_type": "TEST",
            "currency": "PKR",
        },
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert "destination_encrypted" not in body and body["destination_masked"] == "***6789"
    profile = PaymentBeneficiaryProfile.objects.get(pk=body["id"])
    assert decrypt_payment_destination(profile.destination_encrypted) == "03123456789"

    for actor, action, expected in [
        (verifier, "verify", "UNDER_VERIFICATION"),
        (approver, "approve", "APPROVED"),
        (activator, "activate", "ACTIVATED"),
    ]:
        client.force_authenticate(actor)
        result = client.post(
            f"/api/v1/finance/payment-beneficiaries/{profile.id}/{action}/", {}, format="json"
        )
        assert result.status_code == 200 and result.json()["status"] == expected


def test_payment_provider_api_never_returns_secret_reference() -> None:
    company = CompanyFactory.create()
    user = UserFactory.create(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    created = client.post(
        "/api/v1/finance/payment-providers/",
        {
            "company": str(company.id),
            "code": "TEST",
            "provider_type": "TEST",
            "display_name": "Test provider",
            "currency": "PKR",
            "adapter_code": "TEST_SUCCESS",
            "safe_configuration": {},
        },
        format="json",
    )
    assert created.status_code == 201
    assert "secret_reference" not in created.json()


@pytest.mark.parametrize("multi_company_access", [False, True])
def test_provider_reads_enforce_parent_company_relations(multi_company_access: bool) -> None:
    company_a, company_b = CompanyFactory.create(), CompanyFactory.create()
    maker = UserFactory.create()
    year_a, period_a, accounts_a = accounting_setup(company_a)
    year_b, period_b, accounts_b = accounting_setup(company_b)
    provider_a = PaymentProviderConfiguration.objects.create(
        company=company_a,
        code="PROVIDER-A",
        provider_type=ProviderType.TEST,
        display_name="Visible Provider",
        adapter_code="TEST_SUCCESS",
        created_by=maker,
    )
    provider_b = PaymentProviderConfiguration.objects.create(
        company=company_b,
        code="PROVIDER-B",
        provider_type=ProviderType.TEST,
        display_name="Hidden Provider",
        adapter_code="TEST_SUCCESS",
        created_by=maker,
    )
    vendor_a = Vendor.objects.create(
        company=company_a, code="V-A", name="Vendor A", payable_account=accounts_a["payable"]
    )
    vendor_b = Vendor.objects.create(
        company=company_b, code="V-B", name="Vendor B", payable_account=accounts_b["payable"]
    )
    beneficiary_a = PaymentBeneficiaryProfile.objects.create(
        company=company_a,
        vendor=vendor_a,
        provider_type=ProviderType.TEST,
        destination_encrypted="encrypted-a",
        destination_masked="***A",
        account_title="Visible beneficiary",
        requested_by=maker,
    )
    beneficiary_b = PaymentBeneficiaryProfile.objects.create(
        company=company_b,
        vendor=vendor_b,
        provider_type=ProviderType.TEST,
        destination_encrypted="encrypted-b",
        destination_masked="***HIDDEN-B",
        account_title="Hidden beneficiary",
        requested_by=maker,
    )
    employee_a = EmployeeFactory.create(company=company_a)
    employee_b = EmployeeFactory.create(company=company_b)
    valid_employee_beneficiary = PaymentBeneficiaryProfile.objects.create(
        company=company_a,
        employee=employee_a,
        provider_type=ProviderType.TEST,
        destination_encrypted="employee-a",
        destination_masked="***EMPLOYEE-A",
        account_title="Visible employee",
        requested_by=maker,
    )
    corrupt_employee_beneficiary = PaymentBeneficiaryProfile.objects.create(
        company=company_a,
        employee=employee_b,
        provider_type=ProviderType.TEST,
        destination_encrypted="employee-b",
        destination_masked="***HIDDEN-EMPLOYEE-B",
        account_title="Hidden employee",
        requested_by=maker,
    )
    corrupt_vendor_beneficiary = PaymentBeneficiaryProfile.objects.create(
        company=company_a,
        vendor=vendor_b,
        provider_type=ProviderType.TEST,
        destination_encrypted="vendor-b",
        destination_masked="***HIDDEN-VENDOR-B",
        account_title="Hidden vendor",
        requested_by=maker,
    )
    bill_a = VendorBill.objects.create(
        company=company_a,
        vendor=vendor_a,
        vendor_invoice_number="PROVIDER-BILL-A",
        bill_number="PROVIDER-BILL-A",
        bill_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        total_amount=Decimal("100"),
        created_by=maker,
    )
    bill_b = VendorBill.objects.create(
        company=company_b,
        vendor=vendor_b,
        vendor_invoice_number="PROVIDER-BILL-B",
        bill_number="PROVIDER-BILL-B",
        bill_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        total_amount=Decimal("100"),
        created_by=maker,
    )

    def voucher(number: str, bill: VendorBill = bill_a) -> PaymentVoucher:
        return PaymentVoucher.objects.create(
            company=bill.company,
            vendor_bill=bill,
            voucher_number=number,
            payment_date=date(2026, 8, 2),
            amount=Decimal("10"),
            created_by=maker,
        )

    vouchers_a = [voucher(f"PV-INSTRUCTION-{index}") for index in range(4)]
    voucher_b = voucher("PV-INSTRUCTION-B", bill_b)
    journal_b = JournalEntry.objects.create(
        company=company_b,
        fiscal_year=year_b,
        accounting_period=period_b,
        journal_number="JV-INSTRUCTION-B",
        entry_date=date(2026, 8, 2),
        description="Hidden instruction journal",
        created_by=maker,
    )
    batch = PaymentBatch.objects.create(
        company=company_a,
        provider=provider_a,
        batch_number="BATCH-VALID",
        batch_type="VENDOR",
        prepared_by=maker,
    )
    corrupt_batch = PaymentBatch.objects.create(
        company=company_a,
        provider=provider_b,
        batch_number="BATCH-CORRUPT",
        batch_type="VENDOR",
        prepared_by=maker,
    )
    payroll_period_a = PayrollPeriod.objects.create(
        company=company_a,
        name="Provider payroll A",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        payment_date=date(2026, 9, 1),
    )
    payroll_period_b = PayrollPeriod.objects.create(
        company=company_b,
        name="Provider payroll B",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        payment_date=date(2026, 9, 1),
    )
    run_a = PayrollRun.objects.create(
        company=company_a,
        payroll_period=payroll_period_a,
        run_number="PROVIDER-RUN-A",
        created_by=maker,
    )
    run_b = PayrollRun.objects.create(
        company=company_b,
        payroll_period=payroll_period_b,
        run_number="PROVIDER-RUN-B",
        created_by=maker,
    )
    payslip_a = Payslip.objects.create(
        payroll_run=run_a,
        employee=employee_a,
        gross_pay=Decimal("10"),
        net_pay=Decimal("10"),
    )
    payslip_b = Payslip.objects.create(
        payroll_run=run_b,
        employee=employee_b,
        gross_pay=Decimal("10"),
        net_pay=Decimal("10"),
    )
    payroll_batch = PaymentBatch.objects.create(
        company=company_a,
        provider=provider_a,
        payroll_run=run_a,
        batch_number="BATCH-PAYROLL-VALID",
        batch_type="PAYROLL",
        prepared_by=maker,
    )
    corrupt_payroll_batch = PaymentBatch.objects.create(
        company=company_a,
        provider=provider_a,
        payroll_run=run_b,
        batch_number="BATCH-PAYROLL-CORRUPT",
        batch_type="PAYROLL",
        prepared_by=maker,
    )
    valid_instruction = PaymentInstruction.objects.create(
        batch=batch,
        beneficiary=beneficiary_a,
        payment_voucher=vouchers_a[0],
        amount=Decimal("10"),
        currency="PKR",
    )
    corrupt_beneficiary = PaymentInstruction.objects.create(
        batch=batch,
        beneficiary=beneficiary_b,
        payment_voucher=vouchers_a[1],
        amount=Decimal("10"),
        currency="PKR",
    )
    corrupt_voucher = PaymentInstruction.objects.create(
        batch=batch,
        beneficiary=beneficiary_a,
        payment_voucher=voucher_b,
        amount=Decimal("10"),
        currency="PKR",
    )
    corrupt_journal = PaymentInstruction.objects.create(
        batch=batch,
        beneficiary=beneficiary_a,
        payment_voucher=vouchers_a[2],
        accounting_journal=journal_b,
        amount=Decimal("10"),
        currency="PKR",
    )
    valid_payslip_instruction = PaymentInstruction.objects.create(
        batch=batch,
        beneficiary=beneficiary_a,
        payslip=payslip_a,
        amount=Decimal("10"),
        currency="PKR",
    )
    corrupt_payslip_instruction = PaymentInstruction.objects.create(
        batch=batch,
        beneficiary=beneficiary_a,
        payslip=payslip_b,
        amount=Decimal("10"),
        currency="PKR",
    )
    journal_a = JournalEntry.objects.create(
        company=company_a,
        fiscal_year=year_a,
        accounting_period=period_a,
        journal_number="JV-SETTLEMENT-A",
        entry_date=date(2026, 8, 2),
        description="Visible settlement journal",
        created_by=maker,
    )
    valid_settlement = PaymentProviderSettlement.objects.create(
        company=company_a,
        provider=provider_a,
        accounting_journal=journal_a,
        settlement_reference="SETTLEMENT-VALID",
        settlement_date=date(2026, 8, 2),
        currency="PKR",
        gross_amount=Decimal("10"),
        net_amount=Decimal("10"),
        imported_by=maker,
    )
    corrupt_provider_settlement = PaymentProviderSettlement.objects.create(
        company=company_a,
        provider=provider_b,
        settlement_reference="SETTLEMENT-PROVIDER-CORRUPT",
        settlement_date=date(2026, 8, 2),
        currency="PKR",
        gross_amount=Decimal("10"),
        net_amount=Decimal("10"),
        imported_by=maker,
    )
    corrupt_journal_settlement = PaymentProviderSettlement.objects.create(
        company=company_a,
        provider=provider_a,
        accounting_journal=journal_b,
        settlement_reference="SETTLEMENT-JOURNAL-CORRUPT",
        settlement_date=date(2026, 8, 2),
        currency="PKR",
        gross_amount=Decimal("10"),
        net_amount=Decimal("10"),
        imported_by=maker,
    )
    user = UserFactory.create()
    permissions = (
        "prepare_payment_batch",
        "view_paymentinstruction",
        "view_sensitive_payment_destination",
        "import_payment_settlement",
    )
    grant(user, company_a, *permissions)
    if multi_company_access:
        grant(user, company_b, *permissions)
    api = APIClient()
    api.force_authenticate(user)

    batches = api.get("/api/v1/finance/payment-batches/")
    beneficiaries = api.get("/api/v1/finance/payment-beneficiaries/")
    instructions = api.get("/api/v1/finance/payment-instructions/")
    settlements = api.get("/api/v1/finance/payment-settlements/")

    assert {row["id"] for row in batches.data} == {str(batch.id), str(payroll_batch.id)}
    nested = next(row for row in batches.data if row["id"] == str(batch.id))["instructions"]
    assert {row["id"] for row in nested} == {
        str(valid_instruction.id),
        str(valid_payslip_instruction.id),
    }
    assert {row["id"] for row in instructions.data} == {
        str(valid_instruction.id),
        str(valid_payslip_instruction.id),
    }
    assert api.get(f"/api/v1/finance/payment-batches/{corrupt_batch.id}/").status_code == 404
    assert (
        api.get(f"/api/v1/finance/payment-batches/{corrupt_payroll_batch.id}/").status_code == 404
    )
    for corrupt in (
        corrupt_beneficiary,
        corrupt_voucher,
        corrupt_journal,
        corrupt_payslip_instruction,
    ):
        assert api.get(f"/api/v1/finance/payment-instructions/{corrupt.id}/").status_code == 404
    expected_beneficiaries = {str(beneficiary_a.id), str(valid_employee_beneficiary.id)}
    if multi_company_access:
        expected_beneficiaries.add(str(beneficiary_b.id))
    assert {row["id"] for row in beneficiaries.data} == expected_beneficiaries
    for corrupt_destination in (corrupt_employee_beneficiary, corrupt_vendor_beneficiary):
        assert (
            api.get(f"/api/v1/finance/payment-beneficiaries/{corrupt_destination.id}/").status_code
            == 404
        )
    assert [row["id"] for row in settlements.data] == [str(valid_settlement.id)]
    for corrupt_settlement in (corrupt_provider_settlement, corrupt_journal_settlement):
        assert (
            api.get(f"/api/v1/finance/payment-settlements/{corrupt_settlement.id}/").status_code
            == 404
        )
    serialized = (
        str(batches.data) + str(beneficiaries.data) + str(instructions.data) + str(settlements.data)
    )
    for foreign_id in (provider_b.id, voucher_b.id, journal_b.id, run_b.id, payslip_b.id):
        assert str(foreign_id) not in serialized
    assert corrupt_employee_beneficiary.destination_masked not in serialized
    assert corrupt_vendor_beneficiary.destination_masked not in serialized
