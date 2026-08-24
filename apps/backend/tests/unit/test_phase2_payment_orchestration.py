from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from dsms.finance.crypto import decrypt_payment_destination
from dsms.finance.enums import WorkflowStatus
from dsms.finance.payment_models import (
    PaymentAccountingProfile,
    PaymentInstructionStatus,
    PaymentProviderConfiguration,
    PaymentProviderSettlement,
    PaymentProviderSettlementLine,
    ProviderType,
)
from dsms.finance.payment_providers import (
    DisabledPaymentProvider,
    DuplicateProviderReferenceTestProvider,
    EasypaisaPaymentProvider,
    PendingThenSuccessTestPaymentProvider,
    PermanentFailureTestPaymentProvider,
    SuccessfulTestPaymentProvider,
    TemporaryFailureTestPaymentProvider,
    UnknownAfterSubmitTestPaymentProvider,
    configured_adapter,
)
from dsms.finance.payment_services import (
    activate_payment_destination,
    approve_payment_batch,
    approve_payment_destination_change,
    create_payroll_disbursement_batch,
    create_vendor_payment_batch,
    process_payment_instruction,
    query_payment_instruction_status,
    reconcile_settlement,
    record_manual_payment_success,
    release_payment_batch,
    request_payment_destination_change,
    submit_payment_batch,
    verify_payment_destination_change,
)
from dsms.finance.payroll_models import PayrollPeriod, PayrollRun, Payslip
from dsms.finance.procurement_models import PaymentVoucher, Vendor, VendorBill
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def payment_graph() -> tuple[Any, Any, Any, Any, Any]:
    company = CompanyFactory.create()
    requester, verifier, approver, releaser = UserFactory.create_batch(4)
    employee = EmployeeFactory.create(company=company)
    _year, _period, accounts = accounting_setup(company)
    PaymentAccountingProfile.objects.create(
        company=company,
        payroll_payable_account=accounts["payable"],
        vendor_payable_account=accounts["deduction"],
        gateway_clearing_account=accounts["cash"],
        bank_account=accounts["bank"],
        provider_fee_account=accounts["expense"],
    )
    provider = PaymentProviderConfiguration.objects.create(
        company=company,
        code="TEST",
        provider_type=ProviderType.TEST,
        display_name="Deterministic test provider",
        adapter_code="TEST_SUCCESS",
        created_by=requester,
    )
    profile = request_payment_destination_change(
        company=company,
        actor=requester,
        employee=employee,
        destination="03123456789",
        account_title="Employee",
        provider_type=ProviderType.TEST,
    )
    assert "03123456789" not in profile.destination_encrypted
    assert decrypt_payment_destination(profile.destination_encrypted) == "03123456789"
    profile = verify_payment_destination_change(profile=profile, actor=verifier)
    profile = approve_payment_destination_change(profile=profile, actor=approver)
    profile = activate_payment_destination(profile=profile, actor=releaser)
    period = PayrollPeriod.objects.create(
        company=company,
        name="August payment",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        payment_date=date(2026, 8, 31),
    )
    run = PayrollRun.objects.create(
        company=company,
        payroll_period=period,
        run_number="PAY-PHASE2",
        status=WorkflowStatus.APPROVED,
        created_by=requester,
        approved_by=approver,
    )
    Payslip.objects.create(
        payroll_run=run,
        employee=employee,
        gross_pay=Decimal("1000"),
        deductions=Decimal("100"),
        net_pay=Decimal("900"),
    )
    return run, provider, requester, approver, releaser


def test_payroll_payment_success_posts_once_and_marks_paid() -> None:
    run, provider, maker, approver, releaser = payment_graph()
    batch = create_payroll_disbursement_batch(payroll_run=run, provider=provider, actor=maker)
    batch = submit_payment_batch(batch=batch, actor=maker)
    batch = approve_payment_batch(batch=batch, actor=approver)
    batch = release_payment_batch(batch=batch, actor=releaser)
    instruction = process_payment_instruction(
        instruction=batch.instructions.get(), adapter=SuccessfulTestPaymentProvider()
    )
    assert instruction.status == PaymentInstructionStatus.SUCCEEDED
    journal = instruction.accounting_journal
    payslip = instruction.payslip
    assert journal is not None and payslip is not None
    assert journal.total_debit == Decimal("900.00")
    assert journal.total_credit == Decimal("900.00")
    assert payslip.payment_status == "PAID"
    again = process_payment_instruction(
        instruction=instruction, adapter=SuccessfulTestPaymentProvider()
    )
    assert again.provider_transactions.count() == 1


def test_unknown_provider_outcome_requires_review_without_marking_paid() -> None:
    run, provider, maker, approver, releaser = payment_graph()
    batch = release_payment_batch(
        batch=approve_payment_batch(
            batch=submit_payment_batch(
                batch=create_payroll_disbursement_batch(
                    payroll_run=run, provider=provider, actor=maker
                ),
                actor=maker,
            ),
            actor=approver,
        ),
        actor=releaser,
    )
    instruction = process_payment_instruction(
        instruction=batch.instructions.get(), adapter=UnknownAfterSubmitTestPaymentProvider()
    )
    assert instruction.status == PaymentInstructionStatus.REQUIRES_REVIEW
    assert instruction.accounting_journal_id is None
    assert instruction.payslip is not None
    assert instruction.payslip.payment_status != "PAID"


def _released_batch() -> tuple[Any, Any]:
    run, provider, maker, approver, releaser = payment_graph()
    batch = create_payroll_disbursement_batch(payroll_run=run, provider=provider, actor=maker)
    batch = submit_payment_batch(batch=batch, actor=maker)
    batch = approve_payment_batch(batch=batch, actor=approver)
    return release_payment_batch(batch=batch, actor=releaser), approver


def test_pending_payment_is_paid_only_after_provider_status_query() -> None:
    batch, _reviewer = _released_batch()
    adapter = PendingThenSuccessTestPaymentProvider()
    instruction = process_payment_instruction(instruction=batch.instructions.get(), adapter=adapter)
    assert instruction.status == PaymentInstructionStatus.ACCEPTED
    assert instruction.accounting_journal_id is None
    instruction = query_payment_instruction_status(instruction=instruction, adapter=adapter)
    assert instruction.status == PaymentInstructionStatus.SUCCEEDED
    assert instruction.accounting_journal_id is not None
    assert instruction.provider_transactions.count() == 2


def test_unknown_payment_requires_independent_evidence_for_manual_success() -> None:
    batch, reviewer = _released_batch()
    instruction = process_payment_instruction(
        instruction=batch.instructions.get(), adapter=UnknownAfterSubmitTestPaymentProvider()
    )
    with pytest.raises(ValidationError, match="evidence"):
        record_manual_payment_success(
            instruction=instruction, actor=reviewer, evidence_reference="bad"
        )
    instruction = record_manual_payment_success(
        instruction=instruction, actor=reviewer, evidence_reference="BANK-EVIDENCE-001"
    )
    assert instruction.status == PaymentInstructionStatus.SUCCEEDED
    assert instruction.accounting_journal_id is not None


@pytest.mark.parametrize(
    ("adapter", "expected"),
    [
        (SuccessfulTestPaymentProvider(), "SUCCEEDED"),
        (TemporaryFailureTestPaymentProvider(), "FAILED"),
        (PermanentFailureTestPaymentProvider(), "FAILED"),
        (UnknownAfterSubmitTestPaymentProvider(), "UNKNOWN"),
        (DisabledPaymentProvider(), "FAILED"),
        (EasypaisaPaymentProvider(), "FAILED"),
        (DuplicateProviderReferenceTestProvider(), "SUCCEEDED"),
    ],
)
def test_deterministic_provider_boundaries(adapter: Any, expected: str) -> None:
    result = adapter.submit_payment(instruction=object(), idempotency_key="fixed")
    assert result.status == expected
    queried = adapter.query_payment_status(provider_reference=result.provider_reference)
    assert queried.status in {"SUCCEEDED", "FAILED", "UNKNOWN"}


def test_provider_settlement_matches_payment_and_posts_clearing_journal() -> None:
    batch, reviewer = _released_batch()
    instruction = process_payment_instruction(
        instruction=batch.instructions.get(), adapter=SuccessfulTestPaymentProvider()
    )
    settlement = PaymentProviderSettlement.objects.create(
        company=batch.company,
        provider=batch.provider,
        settlement_reference="SETTLEMENT-001",
        settlement_date=date(2026, 8, 21),
        currency="PKR",
        gross_amount=Decimal("900"),
        fee_amount=Decimal("10"),
        net_amount=Decimal("910"),
        imported_by=batch.prepared_by,
    )
    PaymentProviderSettlementLine.objects.create(
        settlement=settlement,
        provider_reference=instruction.provider_reference,
        amount=instruction.amount,
        currency=instruction.currency,
    )
    settlement = reconcile_settlement(settlement=settlement, actor=reviewer)
    assert settlement.status == "RECONCILED"
    assert settlement.lines.get().instruction == instruction
    assert settlement.accounting_journal is not None
    assert (
        settlement.accounting_journal.total_debit
        == settlement.accounting_journal.total_credit
        == Decimal("910.00")
    )


def test_provider_configuration_never_enables_unverified_easypaisa() -> None:
    for code in [
        "TEST_SUCCESS",
        "TEST_TEMPORARY_FAILURE",
        "TEST_PERMANENT_FAILURE",
        "TEST_PENDING_SUCCESS",
        "TEST_UNKNOWN",
        "TEST_DUPLICATE_REFERENCE",
    ]:
        adapter = configured_adapter(
            SimpleNamespace(adapter_code=code, provider_type=ProviderType.TEST, is_active=True)
        )
        assert adapter is not None
    disabled = configured_adapter(
        SimpleNamespace(
            adapter_code="UNVERIFIED",
            provider_type=ProviderType.EASYPAISA,
            is_active=True,
        )
    )
    assert isinstance(disabled, EasypaisaPaymentProvider)
    assert disabled.submit_payment(instruction=object(), idempotency_key="x").status == "FAILED"


def test_vendor_partial_payment_updates_only_allocated_payable() -> None:
    run, provider, maker, approver, releaser = payment_graph()
    accounting = PaymentAccountingProfile.objects.get(company=run.company)
    vendor = Vendor.objects.create(
        company=run.company,
        code="VENDOR-1",
        name="Test Vendor",
        payable_account=accounting.vendor_payable_account,
    )
    profile = request_payment_destination_change(
        company=run.company,
        actor=maker,
        vendor=vendor,
        destination="PK00TEST0001",
        account_title="Test Vendor",
        provider_type=ProviderType.TEST,
    )
    profile = verify_payment_destination_change(profile=profile, actor=UserFactory.create())
    profile = approve_payment_destination_change(profile=profile, actor=approver)
    activate_payment_destination(profile=profile, actor=releaser)
    bill = VendorBill.objects.create(
        company=run.company,
        vendor=vendor,
        vendor_invoice_number="SUP-1",
        bill_number="VB-1",
        bill_date=date(2026, 8, 1),
        due_date=date(2026, 8, 31),
        status=WorkflowStatus.APPROVED,
        subtotal=Decimal("1000"),
        total_amount=Decimal("1000"),
        created_by=maker,
        approved_by=approver,
    )
    voucher = PaymentVoucher.objects.create(
        company=run.company,
        vendor_bill=bill,
        voucher_number="PV-1",
        payment_date=date(2026, 8, 21),
        amount=Decimal("400"),
        status=WorkflowStatus.APPROVED,
        created_by=maker,
        approved_by=approver,
    )
    batch = create_vendor_payment_batch(vouchers=[voucher], provider=provider, actor=maker)
    batch = release_payment_batch(
        batch=approve_payment_batch(
            batch=submit_payment_batch(batch=batch, actor=maker), actor=approver
        ),
        actor=releaser,
    )
    instruction = process_payment_instruction(
        instruction=batch.instructions.get(), adapter=SuccessfulTestPaymentProvider()
    )
    bill.refresh_from_db()
    voucher.refresh_from_db()
    assert bill.paid_amount == Decimal("400.00")
    assert bill.outstanding_amount == Decimal("600.00")
    assert bill.status == WorkflowStatus.PARTIALLY_PAID
    assert voucher.payment_status == "PAID"
    assert instruction.accounting_journal_id is not None
