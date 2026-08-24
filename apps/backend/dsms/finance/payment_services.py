from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event

from .crypto import encrypt_payment_destination
from .enums import PaymentStatus, WorkflowStatus
from .models import AccountingPeriod
from .payment_models import (
    BeneficiaryStatus,
    PaymentAccountingProfile,
    PaymentBatch,
    PaymentBatchStatus,
    PaymentBeneficiaryProfile,
    PaymentDestinationChange,
    PaymentInstruction,
    PaymentInstructionAllocation,
    PaymentInstructionStatus,
    PaymentProviderConfiguration,
    PaymentProviderSettlement,
    PaymentProviderTransaction,
    ProviderTransactionStatus,
    SettlementStatus,
)
from .payment_providers import PaymentProviderAdapter, configured_adapter
from .payroll_models import PayrollRun
from .procurement_models import PaymentVoucher, VendorBill
from .services import (
    approve_journal,
    create_journal,
    money,
    next_document_number,
    post_journal,
    submit_journal,
)


def _audit(action: str, actor: Any, obj: Any, summary: str) -> None:
    record_audit_event(
        action=action,
        category=AuditCategory.FINANCE,
        severity=AuditSeverity.HIGH,
        summary=summary,
        actor_user=actor,
        company=obj.company,
        source_object=obj,
        object_reference=getattr(obj, "batch_number", "") or str(obj.pk),
    )


def _publish_payment_event(item: PaymentInstruction) -> None:
    from dsms.notifications.services import publish_notification_event

    publish_notification_event(
        event_key=f"payment:{item.id}:{item.attempt_count}:{item.status}",
        event_type=f"PAYMENT_{item.status}",
        source_app="finance",
        source_model="PaymentInstruction",
        source_object_id=item.id,
        company=item.batch.company,
        safe_payload={
            "batch_number": item.batch.batch_number,
            "instruction_id": str(item.id),
            "status": item.status,
            "failure_code": item.failure_code,
        },
    )


def _post_payment_journal(
    *,
    company: Any,
    entry_date: Any,
    maker: Any,
    actor: Any,
    description: str,
    source_type: str,
    source_id: Any,
    lines: list[dict[str, Any]],
) -> Any:
    period = (
        AccountingPeriod.objects.select_related("fiscal_year")
        .filter(
            company=company, start_date__lte=entry_date, end_date__gte=entry_date, status="OPEN"
        )
        .first()
    )
    if not period:
        raise ValidationError("No open accounting period covers this payment transaction.")
    journal = create_journal(
        company=company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=entry_date,
        description=description,
        created_by=maker,
        source_type=source_type,
        source_id=source_id,
        lines=lines,
    )
    journal = submit_journal(journal=journal, actor=maker)
    journal = approve_journal(journal=journal, actor=actor)
    return post_journal(journal=journal, actor=actor)


def _post_instruction_accounting(item: PaymentInstruction) -> None:
    if item.accounting_journal_id:
        return
    profile = PaymentAccountingProfile.objects.select_related(
        "payroll_payable_account", "vendor_payable_account", "gateway_clearing_account"
    ).get(company=item.batch.company, is_active=True)
    payable = profile.payroll_payable_account if item.payslip_id else profile.vendor_payable_account
    journal = _post_payment_journal(
        company=item.batch.company,
        entry_date=timezone.localdate(),
        maker=item.batch.prepared_by,
        actor=item.batch.released_by,
        description=f"Payment release {item.batch.batch_number}",
        source_type="PAYMENT_INSTRUCTION",
        source_id=item.id,
        lines=[
            {"account": payable, "debit": item.amount},
            {"account": profile.gateway_clearing_account, "credit": item.amount},
        ],
    )
    item.accounting_journal = journal


@transaction.atomic
def request_payment_destination_change(
    *,
    company: Any,
    actor: Any,
    destination: str,
    account_title: str,
    provider_type: str,
    employee: Any = None,
    vendor: Any = None,
    currency: str = "PKR",
) -> PaymentBeneficiaryProfile:
    raw = destination.strip()
    if len(raw) < 4 or (employee is None) == (vendor is None):
        raise ValidationError("A valid destination and exactly one beneficiary are required.")
    profile = PaymentBeneficiaryProfile.objects.create(
        company=company,
        employee=employee,
        vendor=vendor,
        provider_type=provider_type,
        currency=currency,
        destination_encrypted=encrypt_payment_destination(raw),
        destination_masked="***" + raw[-4:],
        account_title=account_title.strip(),
        requested_by=actor,
    )
    PaymentDestinationChange.objects.create(profile=profile, status=profile.status, actor=actor)
    _audit("PAYMENT_DESTINATION_REQUESTED", actor, profile, "Payment destination change requested.")
    return profile


@transaction.atomic
def verify_payment_destination_change(
    *, profile: PaymentBeneficiaryProfile, actor: Any
) -> PaymentBeneficiaryProfile:
    item = PaymentBeneficiaryProfile.objects.select_for_update(of=("self",)).get(pk=profile.pk)
    if item.status != BeneficiaryStatus.REQUESTED:
        raise ValidationError("Only requested destinations can be verified.")
    item.status, item.verified_by = BeneficiaryStatus.UNDER_VERIFICATION, actor
    item.save(update_fields=["status", "verified_by", "updated_at"])
    PaymentDestinationChange.objects.create(profile=item, status=item.status, actor=actor)
    return item


@transaction.atomic
def approve_payment_destination_change(
    *, profile: PaymentBeneficiaryProfile, actor: Any
) -> PaymentBeneficiaryProfile:
    item = PaymentBeneficiaryProfile.objects.select_for_update(of=("self",)).get(pk=profile.pk)
    if (
        item.status != BeneficiaryStatus.UNDER_VERIFICATION
        or item.requested_by_id == actor.id
        or item.verified_by_id == actor.id
    ):
        raise ValidationError("Destination requires independent verification and approval.")
    item.status, item.approved_by = BeneficiaryStatus.APPROVED, actor
    item.save(update_fields=["status", "approved_by", "updated_at"])
    PaymentDestinationChange.objects.create(profile=item, status=item.status, actor=actor)
    _audit("PAYMENT_DESTINATION_APPROVED", actor, item, "Payment destination approved.")
    return item


@transaction.atomic
def activate_payment_destination(
    *, profile: PaymentBeneficiaryProfile, actor: Any
) -> PaymentBeneficiaryProfile:
    item = PaymentBeneficiaryProfile.objects.select_for_update(of=("self",)).get(pk=profile.pk)
    if item.status != BeneficiaryStatus.APPROVED or item.approved_by_id == actor.id:
        raise ValidationError("An independently approved destination is required for activation.")
    owner_filter: dict[str, Any] = (
        {"employee_id": item.employee_id} if item.employee_id else {"vendor_id": item.vendor_id}
    )
    previous = (
        PaymentBeneficiaryProfile.objects.select_for_update()
        .filter(is_active=True, **owner_filter)
        .first()
    )
    if previous:
        previous.status, previous.is_active = BeneficiaryStatus.SUPERSEDED, False
        previous.save(update_fields=["status", "is_active", "updated_at"])
    item.status, item.is_active, item.activated_at = (
        BeneficiaryStatus.ACTIVATED,
        True,
        timezone.now(),
    )
    item.save(update_fields=["status", "is_active", "activated_at", "updated_at"])
    PaymentDestinationChange.objects.create(
        profile=item, previous_profile=previous, status=item.status, actor=actor
    )
    _audit("PAYMENT_DESTINATION_ACTIVATED", actor, item, "Payment destination activated.")
    return item


@transaction.atomic
def create_payroll_disbursement_batch(
    *, payroll_run: PayrollRun, provider: PaymentProviderConfiguration, actor: Any
) -> PaymentBatch:
    run = PayrollRun.objects.select_for_update(of=("self",)).get(pk=payroll_run.pk)
    if run.status not in {WorkflowStatus.APPROVED, WorkflowStatus.POSTED}:
        raise ValidationError("Payroll run must be approved or posted.")
    if run.company_id != provider.company_id or not provider.is_active:
        raise ValidationError("An active provider from the payroll company is required.")
    batch = PaymentBatch.objects.create(
        batch_number=next_document_number(
            company=run.company, prefix="PAY", year=timezone.localdate().year
        ),
        company=run.company,
        batch_type="PAYROLL",
        payroll_run=run,
        provider=provider,
        currency=provider.currency,
        prepared_by=actor,
    )
    total = Decimal("0.00")
    for payslip in run.payslips.select_related("employee"):
        if payslip.net_pay <= 0:
            continue
        beneficiary = PaymentBeneficiaryProfile.objects.filter(
            employee=payslip.employee,
            is_active=True,
            status=BeneficiaryStatus.ACTIVATED,
            currency=provider.currency,
        ).first()
        if not beneficiary:
            raise ValidationError(
                f"Employee {payslip.employee_id} has no active verified destination."
            )
        PaymentInstruction.objects.create(
            batch=batch,
            beneficiary=beneficiary,
            payslip=payslip,
            amount=payslip.net_pay,
            currency=provider.currency,
        )
        total += payslip.net_pay
    if not batch.instructions.exists():
        raise ValidationError("Payroll has no payable payslips.")
    batch.total_amount, batch.instruction_count = money(total), batch.instructions.count()
    batch.save(update_fields=["total_amount", "instruction_count", "updated_at"])
    _audit("PAYROLL_PAYMENT_BATCH_PREPARED", actor, batch, "Payroll disbursement batch prepared.")
    return batch


@transaction.atomic
def create_vendor_payment_batch(
    *, vouchers: list[PaymentVoucher], provider: PaymentProviderConfiguration, actor: Any
) -> PaymentBatch:
    if not vouchers:
        raise ValidationError("At least one approved payment voucher is required.")
    company = vouchers[0].company
    if provider.company_id != company.id or not provider.is_active:
        raise ValidationError("An active provider from the voucher company is required.")
    batch = PaymentBatch.objects.create(
        batch_number=next_document_number(
            company=company, prefix="VPAY", year=timezone.localdate().year
        ),
        company=company,
        batch_type="VENDOR",
        provider=provider,
        currency=provider.currency,
        prepared_by=actor,
    )
    total = Decimal("0.00")
    for voucher in vouchers:
        locked = (
            PaymentVoucher.objects.select_for_update(of=("self",))
            .select_related("vendor_bill__vendor")
            .get(pk=voucher.pk)
        )
        if locked.status != WorkflowStatus.APPROVED or not locked.vendor_bill_id:
            raise ValidationError("Every voucher must be approved and linked to a vendor bill.")
        bill = locked.vendor_bill
        assert bill is not None
        beneficiary = PaymentBeneficiaryProfile.objects.filter(
            vendor=bill.vendor,
            is_active=True,
            status=BeneficiaryStatus.ACTIVATED,
            currency=provider.currency,
        ).first()
        if not beneficiary or locked.amount > bill.outstanding_amount:
            raise ValidationError(
                "Verified destination and sufficient vendor payable are required."
            )
        instruction = PaymentInstruction.objects.create(
            batch=batch,
            beneficiary=beneficiary,
            payment_voucher=locked,
            amount=locked.amount,
            currency=provider.currency,
        )
        PaymentInstructionAllocation.objects.create(
            instruction=instruction, vendor_bill=bill, amount=locked.amount
        )
        total += locked.amount
    batch.total_amount, batch.instruction_count = money(total), batch.instructions.count()
    batch.save(update_fields=["total_amount", "instruction_count", "updated_at"])
    _audit("VENDOR_PAYMENT_BATCH_PREPARED", actor, batch, "Vendor payment batch prepared.")
    return batch


@transaction.atomic
def submit_payment_batch(*, batch: PaymentBatch, actor: Any) -> PaymentBatch:
    item = PaymentBatch.objects.select_for_update(of=("self",)).get(pk=batch.pk)
    if item.status != PaymentBatchStatus.DRAFT:
        raise ValidationError("Only draft payment batches can be submitted.")
    item.status = PaymentBatchStatus.PENDING_APPROVAL
    item.save(update_fields=["status", "updated_at"])
    return item


@transaction.atomic
def approve_payment_batch(*, batch: PaymentBatch, actor: Any) -> PaymentBatch:
    item = PaymentBatch.objects.select_for_update(of=("self",)).get(pk=batch.pk)
    if item.status != PaymentBatchStatus.PENDING_APPROVAL or item.prepared_by_id == actor.id:
        raise ValidationError("Independent approval is required.")
    item.status, item.approved_by, item.approved_at = (
        PaymentBatchStatus.APPROVED,
        actor,
        timezone.now(),
    )
    item.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    _audit("PAYMENT_BATCH_APPROVED", actor, item, "Payment batch approved.")
    return item


@transaction.atomic
def release_payment_batch(*, batch: PaymentBatch, actor: Any) -> PaymentBatch:
    item = PaymentBatch.objects.select_for_update(of=("self",)).get(pk=batch.pk)
    if item.status != PaymentBatchStatus.APPROVED or item.approved_by_id == actor.id:
        raise ValidationError("Independent release of an approved batch is required.")
    item.status, item.released_by, item.released_at = (
        PaymentBatchStatus.QUEUED,
        actor,
        timezone.now(),
    )
    item.save(update_fields=["status", "released_by", "released_at", "updated_at"])
    _audit("PAYMENT_BATCH_RELEASED", actor, item, "Payment batch released to the payment queue.")
    transaction.on_commit(lambda: _queue_batch(item.pk))
    return item


def _queue_batch(batch_id: Any) -> None:
    from .payment_tasks import process_payment_batch_task

    process_payment_batch_task.delay(str(batch_id))


@transaction.atomic
def process_payment_instruction(
    *, instruction: PaymentInstruction, adapter: PaymentProviderAdapter | None = None
) -> PaymentInstruction:
    item = (
        PaymentInstruction.objects.select_for_update(of=("self",))
        .select_related("batch__provider")
        .get(pk=instruction.pk)
    )
    if item.status in {
        PaymentInstructionStatus.SUCCEEDED,
        PaymentInstructionStatus.REQUIRES_REVIEW,
    }:
        return item
    if item.status not in {PaymentInstructionStatus.QUEUED, PaymentInstructionStatus.FAILED}:
        return item
    item.status, item.attempt_count = PaymentInstructionStatus.PROCESSING, item.attempt_count + 1
    item.save(update_fields=["status", "attempt_count", "updated_at"])
    provider = adapter or configured_adapter(item.batch.provider)
    result = provider.submit_payment(instruction=item, idempotency_key=str(item.idempotency_key))
    PaymentProviderTransaction.objects.create(
        instruction=item,
        attempt_number=item.attempt_count,
        provider_reference=result.provider_reference,
        status=result.status,
        submitted_at=timezone.now(),
        completed_at=timezone.now()
        if result.status in {ProviderTransactionStatus.SUCCEEDED, ProviderTransactionStatus.FAILED}
        else None,
        failure_code=result.failure_code,
        safe_failure_message=result.safe_failure_message,
    )
    item.provider_reference = result.provider_reference
    item.provider_status = result.status
    item.submitted_at = item.submitted_at or timezone.now()
    item.failure_code, item.safe_failure_message = result.failure_code, result.safe_failure_message
    if result.status == ProviderTransactionStatus.SUCCEEDED:
        item.status, item.completed_at = PaymentInstructionStatus.SUCCEEDED, timezone.now()
        _post_instruction_accounting(item)
        if item.payslip_id:
            payslip = item.payslip
            assert payslip is not None
            payslip.payment_status = PaymentStatus.PAID
            payslip.save(update_fields=["payment_status", "updated_at"])
        if item.payment_voucher_id:
            _apply_vendor_payment(item)
    elif result.status in {ProviderTransactionStatus.UNKNOWN, ProviderTransactionStatus.PENDING}:
        item.status = (
            PaymentInstructionStatus.REQUIRES_REVIEW
            if result.status == ProviderTransactionStatus.UNKNOWN
            else PaymentInstructionStatus.ACCEPTED
        )
    else:
        item.status = PaymentInstructionStatus.FAILED
    item.save()
    _publish_payment_event(item)
    _refresh_batch(item.batch_id)
    return item


def _apply_vendor_payment(item: PaymentInstruction) -> None:
    assert item.payment_voucher_id is not None
    voucher = PaymentVoucher.objects.select_for_update(of=("self",)).get(pk=item.payment_voucher_id)
    for allocation in item.bill_allocations.select_related("vendor_bill"):
        bill = VendorBill.objects.select_for_update(of=("self",)).get(pk=allocation.vendor_bill_id)
        if allocation.amount > bill.outstanding_amount:
            raise ValidationError("Payment allocation exceeds remaining vendor payable.")
        bill.paid_amount = money(bill.paid_amount + allocation.amount)
        bill.status = (
            WorkflowStatus.PAID if bill.outstanding_amount == 0 else WorkflowStatus.PARTIALLY_PAID
        )
        bill.save(update_fields=["paid_amount", "status", "updated_at"])
    voucher.payment_status, voucher.status = PaymentStatus.PAID, WorkflowStatus.PAID
    voucher.payment_reference = item.provider_reference
    voucher.save(update_fields=["payment_status", "status", "payment_reference", "updated_at"])


def _refresh_batch(batch_id: Any) -> None:
    batch = PaymentBatch.objects.select_for_update(of=("self",)).get(pk=batch_id)
    statuses = set(batch.instructions.values_list("status", flat=True))
    if statuses == {PaymentInstructionStatus.SUCCEEDED}:
        batch.status = PaymentBatchStatus.SUCCEEDED
    elif PaymentInstructionStatus.REQUIRES_REVIEW in statuses or statuses <= {
        PaymentInstructionStatus.FAILED
    }:
        batch.status = PaymentBatchStatus.EXCEPTION
    elif statuses & {PaymentInstructionStatus.SUCCEEDED, PaymentInstructionStatus.FAILED}:
        batch.status = PaymentBatchStatus.PARTIAL
    else:
        batch.status = PaymentBatchStatus.PROCESSING
    batch.save(update_fields=["status", "updated_at"])


@transaction.atomic
def retry_failed_payment(*, instruction: PaymentInstruction, actor: Any) -> PaymentInstruction:
    item = PaymentInstruction.objects.select_for_update(of=("self",)).get(pk=instruction.pk)
    if item.status != PaymentInstructionStatus.FAILED or item.failure_code != "TEMPORARY_FAILURE":
        raise ValidationError("Only known temporary failures may be retried.")
    item.status = PaymentInstructionStatus.QUEUED
    item.save(update_fields=["status", "updated_at"])
    _audit("PAYMENT_RETRY_QUEUED", actor, item.batch, "Failed payment safely queued for retry.")
    return item


@transaction.atomic
def query_payment_instruction_status(
    *, instruction: PaymentInstruction, adapter: PaymentProviderAdapter | None = None
) -> PaymentInstruction:
    item = (
        PaymentInstruction.objects.select_for_update(of=("self",))
        .select_related("batch__provider")
        .get(pk=instruction.pk)
    )
    if (
        item.status
        not in {
            PaymentInstructionStatus.ACCEPTED,
            PaymentInstructionStatus.REQUIRES_REVIEW,
        }
        or not item.provider_reference
    ):
        raise ValidationError("Only submitted unresolved payments can be queried.")
    provider = adapter or configured_adapter(item.batch.provider)
    result = provider.query_payment_status(provider_reference=item.provider_reference)
    PaymentProviderTransaction.objects.create(
        instruction=item,
        attempt_number=item.attempt_count + 1,
        provider_reference="",
        status=result.status,
        submitted_at=timezone.now(),
        completed_at=timezone.now()
        if result.status in {ProviderTransactionStatus.SUCCEEDED, ProviderTransactionStatus.FAILED}
        else None,
        failure_code=result.failure_code,
        safe_failure_message=result.safe_failure_message,
        safe_response={"query_for": item.provider_reference},
    )
    item.attempt_count += 1
    item.provider_status = result.status
    if result.status == ProviderTransactionStatus.SUCCEEDED:
        item.status, item.completed_at = PaymentInstructionStatus.SUCCEEDED, timezone.now()
        _post_instruction_accounting(item)
        if item.payslip_id:
            payslip = item.payslip
            assert payslip is not None
            payslip.payment_status = PaymentStatus.PAID
            payslip.save(update_fields=["payment_status", "updated_at"])
        elif item.payment_voucher_id:
            _apply_vendor_payment(item)
    elif result.status == ProviderTransactionStatus.FAILED:
        item.status = PaymentInstructionStatus.FAILED
    else:
        item.status = PaymentInstructionStatus.REQUIRES_REVIEW
    item.failure_code = result.failure_code
    item.safe_failure_message = result.safe_failure_message
    item.save()
    _publish_payment_event(item)
    _refresh_batch(item.batch_id)
    return item


@transaction.atomic
def record_manual_payment_success(
    *, instruction: PaymentInstruction, actor: Any, evidence_reference: str
) -> PaymentInstruction:
    item = (
        PaymentInstruction.objects.select_for_update(of=("self",))
        .select_related("batch")
        .get(pk=instruction.pk)
    )
    if item.status != PaymentInstructionStatus.REQUIRES_REVIEW:
        raise ValidationError("Manual confirmation is restricted to review-required payments.")
    if item.batch.released_by_id == actor.id or len(evidence_reference.strip()) < 6:
        raise ValidationError("Independent reviewer and evidence reference are required.")
    item.status = PaymentInstructionStatus.SUCCEEDED
    item.provider_status = ProviderTransactionStatus.SUCCEEDED
    item.completed_at = timezone.now()
    _post_instruction_accounting(item)
    if item.payslip_id:
        payslip = item.payslip
        assert payslip is not None
        payslip.payment_status = PaymentStatus.PAID
        payslip.save(update_fields=["payment_status", "updated_at"])
    else:
        _apply_vendor_payment(item)
    item.save()
    _publish_payment_event(item)
    _audit(
        "PAYMENT_MANUALLY_CONFIRMED",
        actor,
        item.batch,
        f"Payment manually confirmed with evidence {evidence_reference.strip()}.",
    )
    _refresh_batch(item.batch_id)
    return item


@transaction.atomic
def reconcile_settlement(
    *, settlement: PaymentProviderSettlement, actor: Any
) -> PaymentProviderSettlement:
    item = PaymentProviderSettlement.objects.select_for_update(of=("self",)).get(pk=settlement.pk)
    item.status = SettlementStatus.PROCESSING
    exceptions = 0
    for line in item.lines.select_for_update(of=("self",)):
        instruction = PaymentInstruction.objects.filter(
            batch__provider=item.provider, provider_reference=line.provider_reference
        ).first()
        if not instruction:
            line.status, line.exception_code = "EXCEPTION", "SETTLEMENT_WITHOUT_PAYMENT"
            exceptions += 1
        elif instruction.currency != line.currency or instruction.amount != line.amount:
            line.status, line.exception_code = "EXCEPTION", "AMOUNT_MISMATCH"
            exceptions += 1
        elif instruction.status != PaymentInstructionStatus.SUCCEEDED:
            line.status, line.exception_code = "EXCEPTION", "SUCCESS_NOT_IN_SETTLEMENT"
            exceptions += 1
        else:
            line.instruction, line.status, line.exception_code = instruction, "MATCHED", ""
        line.save(update_fields=["instruction", "status", "exception_code"])
    item.status = SettlementStatus.EXCEPTION if exceptions else SettlementStatus.RECONCILED
    item.reconciled_by = actor
    if not exceptions and not item.accounting_journal_id:
        profile = PaymentAccountingProfile.objects.select_related(
            "gateway_clearing_account", "bank_account", "provider_fee_account"
        ).get(company=item.company, is_active=True)
        lines = [
            {"account": profile.gateway_clearing_account, "debit": item.gross_amount},
            {
                "account": profile.bank_account,
                "credit": item.net_amount,
            },
        ]
        if item.fee_amount:
            lines.append({"account": profile.provider_fee_account, "debit": item.fee_amount})
        item.accounting_journal = _post_payment_journal(
            company=item.company,
            entry_date=item.settlement_date,
            maker=item.imported_by,
            actor=actor,
            description=f"Provider settlement {item.settlement_reference}",
            source_type="PAYMENT_SETTLEMENT",
            source_id=item.id,
            lines=lines,
        )
    item.save(update_fields=["status", "reconciled_by", "accounting_journal", "updated_at"])
    _audit("PAYMENT_SETTLEMENT_RECONCILED", actor, item, "Provider settlement reconciled.")
    return item


def vendor_statement(*, vendor: Any) -> list[dict[str, Any]]:
    bills = vendor.bills.order_by("bill_date", "id")
    return [
        {
            "bill_number": bill.bill_number,
            "total": bill.total_amount,
            "paid": bill.paid_amount,
            "outstanding": bill.outstanding_amount,
        }
        for bill in bills
    ]
