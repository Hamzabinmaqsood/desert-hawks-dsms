import csv
import hashlib
import io
from datetime import date
from decimal import Decimal
from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from dsms.documents.exceptions import DocumentValidationError
from dsms.documents.validators import validate_upload
from dsms.identity import access
from dsms.identity.models import User

from .enums import (
    ApprovalDecision,
    ApprovalDocumentType,
    CalculationType,
    ComponentType,
    MatchType,
    PaymentStatus,
    PettyCashTransactionType,
    ReconciliationStatus,
    WorkflowStatus,
)
from .exceptions import FinanceValidationError, InvalidFinanceTransitionError, MakerCheckerError
from .models import Account, AccountingPeriod, JournalEntry
from .operations_models import (
    ApprovalPolicy,
    BankAccount,
    BankStatement,
    BankStatementLine,
    Budget,
    CashAccount,
    CompanyExpense,
    ExpenseClaim,
    FinanceApprovalHistory,
    FinanceAttachment,
    FundTransfer,
    PettyCashFund,
    PettyCashTransaction,
)
from .payroll_models import (
    EmployeeAdvance,
    EmployeeAdvanceRecovery,
    EmployeeCompensation,
    PayrollPaymentBatch,
    PayrollPaymentItem,
    PayrollRun,
    PayrollVariableInput,
    Payslip,
    PayslipLine,
    StatutoryScheme,
)
from .procurement_models import (
    PaymentVoucher,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    VendorBill,
    validate_vendor_payable_account,
)
from .services import create_journal, money, next_document_number, post_journal
from .vendor_bill_services import (
    validate_vendor_bill_header,
    validate_vendor_bill_line,
)

ZERO = Decimal("0.00")


@transaction.atomic
def create_finance_attachment(
    *, company: Any, document_type: str, object_id: Any, upload: Any, actor: User
) -> FinanceAttachment:
    try:
        _extension, content_type, size = validate_upload(upload, upload.name)
    except DocumentValidationError as exc:
        raise FinanceValidationError(exc.detail) from exc
    return FinanceAttachment.objects.create(
        company=company,
        document_type=document_type,
        object_id=object_id,
        file=upload,
        original_filename=upload.name,
        content_type=content_type,
        size=size,
        uploaded_by=actor,
    )


def _maker_checker(created_by_id: Any, actor: User) -> None:
    if not actor.is_superuser and created_by_id == actor.id:
        raise MakerCheckerError("The financial transaction maker cannot give final approval.")


def _period_for(company_id: Any, transaction_date: date) -> AccountingPeriod:
    try:
        return AccountingPeriod.objects.select_related("fiscal_year").get(
            company_id=company_id,
            start_date__lte=transaction_date,
            end_date__gte=transaction_date,
        )
    except AccountingPeriod.DoesNotExist as exc:
        raise FinanceValidationError({"date": ["No accounting period covers this date."]}) from exc


def validate_direct_payment_account(*, company_id: Any, account: Account) -> None:
    errors: dict[str, list[str]] = {}
    if account.company_id != company_id:
        errors["payment_account"] = ["Payment account must belong to the Voucher company."]
    elif account.account_type != "ASSET":
        errors["payment_account"] = ["Payment account must be an asset cash or bank account."]
    elif not account.is_active:
        errors["payment_account"] = ["Payment account must be active."]
    elif not account.allow_posting:
        errors["payment_account"] = ["Payment account must allow posting."]
    elif not (
        CashAccount.objects.filter(
            ledger_account=account, company_id=company_id, is_active=True
        ).exists()
        or BankAccount.objects.filter(
            ledger_account=account, company_id=company_id, is_active=True
        ).exists()
    ):
        errors["payment_account"] = ["Payment account must be an active cash or bank account."]
    if errors:
        raise FinanceValidationError(errors)


def validate_vendor_payment_values(*, bill: VendorBill, amount: Decimal) -> None:
    amount = money(amount)
    if amount <= ZERO:
        raise FinanceValidationError({"amount": ["Payment amount must be positive."]})
    if bill.status not in {WorkflowStatus.POSTED, WorkflowStatus.PARTIALLY_PAID}:
        raise FinanceValidationError({"vendor_bill": ["Vendor Bill is not payable."]})
    if bill.outstanding_amount <= ZERO:
        raise FinanceValidationError({"vendor_bill": ["Vendor Bill is already fully paid."]})
    if amount > bill.outstanding_amount:
        raise FinanceValidationError(
            {"amount": ["Payment exceeds vendor bill outstanding amount."]}
        )


@transaction.atomic
def apply_vendor_bill_payment(*, bill_id: Any, company_id: Any, amount: Decimal) -> VendorBill:
    amount = money(amount)
    bill = (
        VendorBill.objects.select_for_update(of=("self",))
        .select_related("vendor__payable_account")
        .get(pk=bill_id)
    )
    if amount <= ZERO:
        raise FinanceValidationError({"amount": ["Payment amount must be positive."]})
    if bill.company_id != company_id:
        raise FinanceValidationError({"vendor_bill": ["Vendor Bill must belong to the company."]})
    if bill.status not in {WorkflowStatus.POSTED, WorkflowStatus.PARTIALLY_PAID}:
        raise FinanceValidationError({"vendor_bill": ["Vendor Bill is not payable."]})
    if bill.outstanding_amount <= ZERO:
        raise FinanceValidationError({"vendor_bill": ["Vendor Bill is already fully paid."]})
    if amount > bill.outstanding_amount:
        raise FinanceValidationError(
            {"amount": ["Payment exceeds vendor bill outstanding amount."]}
        )
    try:
        validate_vendor_payable_account(company=bill.company, account=bill.vendor.payable_account)
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"vendor_bill": exc.messages}
        raise FinanceValidationError(detail) from exc
    bill.paid_amount = money(bill.paid_amount + amount)
    bill.status = (
        WorkflowStatus.PAID
        if bill.paid_amount == money(bill.total_amount)
        else WorkflowStatus.PARTIALLY_PAID
    )
    bill.save(update_fields=["paid_amount", "status", "updated_at"])
    return bill


def _history(
    *, obj: Any, document_type: str, actor: User, decision: str, comments: str = ""
) -> None:
    FinanceApprovalHistory.objects.create(
        company_id=obj.company_id,
        document_type=document_type,
        object_id=obj.id,
        decision=decision,
        actor=actor,
        comments=comments,
    )


def _document_amount(obj: Any) -> Decimal:
    for field in ("total_amount", "amount", "net_total"):
        value = getattr(obj, field, None)
        if value is not None:
            return money(value)
    if hasattr(obj, "lines"):
        total = ZERO
        for line in obj.lines.all():
            value = getattr(line, "line_total", None)
            if value is None:
                value = getattr(line, "estimated_total", ZERO)
            total += value or ZERO
        return money(total)
    return ZERO


@transaction.atomic
def submit_finance_document(*, obj: Any, actor: User, document_type: str) -> Any:
    locked = type(obj).objects.select_for_update().get(pk=obj.pk)
    if locked.status != WorkflowStatus.DRAFT:
        raise InvalidFinanceTransitionError("Only a draft transaction can be submitted.")
    locked.status = WorkflowStatus.SUBMITTED
    locked.save(update_fields=["status", "updated_at"])
    _history(
        obj=locked, document_type=document_type, actor=actor, decision=ApprovalDecision.SUBMITTED
    )
    return locked


@transaction.atomic
def approve_finance_document(*, obj: Any, actor: User, document_type: str) -> Any:
    locked = type(obj).objects.select_for_update().get(pk=obj.pk)
    if locked.status != WorkflowStatus.SUBMITTED:
        raise InvalidFinanceTransitionError("Only a submitted transaction can be approved.")
    _maker_checker(locked.created_by_id, actor)
    policy = applicable_policy(
        company_id=locked.company_id,
        document_type=document_type,
        amount=_document_amount(locked),
    )
    step = None
    if policy is not None:
        completed = set(
            FinanceApprovalHistory.objects.filter(
                object_id=locked.id,
                document_type=document_type,
                decision=ApprovalDecision.APPROVED,
                step__isnull=False,
            ).values_list("step_id", flat=True)
        )
        step = policy.steps.exclude(id__in=completed).order_by("sequence").first()
        if step is not None and not actor.is_superuser:
            role_codes = {
                assignment.role.code for assignment in access.get_active_role_assignments(actor)
            }
            if step.role_code not in role_codes:
                raise MakerCheckerError(f"Approval step requires role {step.role_code}.")
        if step is not None:
            FinanceApprovalHistory.objects.create(
                company_id=locked.company_id,
                document_type=document_type,
                object_id=locked.id,
                step=step,
                decision=ApprovalDecision.APPROVED,
                actor=actor,
            )
            if policy.steps.exclude(id__in=completed | {step.id}).filter(required=True).exists():
                return locked
    locked.status = WorkflowStatus.APPROVED
    locked.approved_by = actor
    locked.save(update_fields=["status", "approved_by", "updated_at"])
    if step is None:
        _history(
            obj=locked, document_type=document_type, actor=actor, decision=ApprovalDecision.APPROVED
        )
    return locked


@transaction.atomic
def reject_finance_document(*, obj: Any, actor: User, document_type: str, reason: str) -> Any:
    if not reason.strip():
        raise FinanceValidationError({"reason": ["A rejection reason is required."]})
    locked = type(obj).objects.select_for_update().get(pk=obj.pk)
    if locked.status != WorkflowStatus.SUBMITTED:
        raise InvalidFinanceTransitionError("Only a submitted transaction can be rejected.")
    locked.status = WorkflowStatus.REJECTED
    locked.save(update_fields=["status", "updated_at"])
    _history(
        obj=locked,
        document_type=document_type,
        actor=actor,
        decision=ApprovalDecision.REJECTED,
        comments=reason,
    )
    return locked


def applicable_policy(
    *, company_id: Any, document_type: str, amount: Decimal
) -> ApprovalPolicy | None:
    return (
        ApprovalPolicy.objects.filter(
            company_id=company_id,
            document_type=document_type,
            is_active=True,
            minimum_amount__lte=amount,
        )
        .filter(models.Q(maximum_amount__isnull=True) | models.Q(maximum_amount__gte=amount))
        .order_by("-minimum_amount")
        .first()
    )


def _compensation_for(employee_id: Any, on_date: date) -> EmployeeCompensation:
    item = (
        EmployeeCompensation.objects.filter(employee_id=employee_id, effective_from__lte=on_date)
        .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=on_date))
        .select_related("salary_structure", "employee")
        .order_by("-effective_from")
        .first()
    )
    if item is None:
        raise FinanceValidationError({"employee": ["Employee has no effective compensation."]})
    return item


@transaction.atomic
def calculate_payroll(*, payroll_run: PayrollRun) -> PayrollRun:
    run = (
        PayrollRun.objects.select_for_update()
        .select_related("payroll_period")
        .get(pk=payroll_run.pk)
    )
    if run.status not in [WorkflowStatus.DRAFT, WorkflowStatus.REJECTED]:
        raise InvalidFinanceTransitionError(
            "Payroll can only be calculated or recalculated before approval."
        )
    PayslipLine.objects.filter(payslip__payroll_run=run).delete()
    run.payslips.all().delete()
    employees = run.company.employees.filter(
        joining_date__lte=run.payroll_period.end_date,
    ).exclude(exit_date__lt=run.payroll_period.start_date)
    gross_total = deduction_total = net_total = ZERO
    for employee in employees:
        compensation = _compensation_for(employee.id, run.payroll_period.end_date)
        slip = Payslip.objects.create(payroll_run=run, employee=employee)
        gross = deductions = ZERO
        for structure_line in compensation.salary_structure.components.select_related(
            "payroll_component"
        ):
            component = structure_line.payroll_component
            amount = structure_line.amount
            if component.calculation_type == CalculationType.PERCENTAGE:
                amount = compensation.base_salary * structure_line.percentage / Decimal("100")
            elif component.calculation_type == CalculationType.VARIABLE:
                variable = PayrollVariableInput.objects.filter(
                    payroll_period=run.payroll_period,
                    employee=employee,
                    component=component,
                    status=WorkflowStatus.APPROVED,
                ).first()
                amount = variable.amount if variable else ZERO
            amount = money(amount)
            PayslipLine.objects.create(
                payslip=slip,
                component=component,
                amount=amount,
                component_type=component.component_type,
                source=component.calculation_type,
            )
            if component.component_type == ComponentType.EARNING:
                gross += amount
            elif component.component_type == ComponentType.DEDUCTION:
                deductions += amount
        tax_scheme = compensation.tax_scheme
        if tax_scheme is not None:
            taxable = money(gross)
            tax = ZERO
            for bracket in tax_scheme.brackets.order_by("lower_bound"):
                if taxable <= bracket.lower_bound:
                    continue
                upper = bracket.upper_bound or taxable
                taxable_slice = min(taxable, upper) - bracket.lower_bound
                tax += bracket.fixed_amount + taxable_slice * bracket.rate / Decimal("100")
            tax = money(tax)
            if tax:
                tax_component = tax_scheme.deduction_component
                if tax_component is None:
                    raise FinanceValidationError(
                        {"component": ["Tax scheme has no deduction component mapping."]}
                    )
                PayslipLine.objects.create(
                    payslip=slip,
                    component=tax_component,
                    amount=tax,
                    component_type=ComponentType.DEDUCTION,
                    source="TAX_SCHEME",
                )
                deductions += tax
        for scheme in StatutoryScheme.objects.filter(company=run.company, is_active=True):
            employee_amount = money(
                compensation.base_salary * scheme.employee_rate / Decimal("100")
            )
            employer_amount = money(
                compensation.base_salary * scheme.employer_rate / Decimal("100")
            )
            if employee_amount:
                PayslipLine.objects.create(
                    payslip=slip,
                    component=scheme.employee_component,
                    amount=employee_amount,
                    component_type=ComponentType.DEDUCTION,
                    source="STATUTORY_SCHEME",
                )
                deductions += employee_amount
            if employer_amount:
                PayslipLine.objects.create(
                    payslip=slip,
                    component=scheme.employer_component,
                    amount=employer_amount,
                    component_type=ComponentType.EMPLOYER_CONTRIBUTION,
                    source="STATUTORY_SCHEME",
                )
        for recovery in EmployeeAdvanceRecovery.objects.filter(
            advance__employee=employee, payroll_run=run
        ):
            deductions += recovery.amount
        net = money(gross - deductions)
        if net < ZERO:
            raise FinanceValidationError({"net_pay": [f"Negative net pay for {employee}."]})
        slip.gross_pay, slip.deductions, slip.net_pay = money(gross), money(deductions), net
        slip.save(update_fields=["gross_pay", "deductions", "net_pay", "updated_at"])
        gross_total += gross
        deduction_total += deductions
        net_total += net
    run.gross_total = money(gross_total)
    run.deduction_total = money(deduction_total)
    run.net_total = money(net_total)
    run.status = WorkflowStatus.DRAFT
    run.save(update_fields=["gross_total", "deduction_total", "net_total", "status", "updated_at"])
    return run


@transaction.atomic
def post_payroll(*, payroll_run: PayrollRun, actor: User) -> PayrollRun:
    run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk)
    if run.journal_entry_id:
        return run
    if run.status != WorkflowStatus.APPROVED:
        raise InvalidFinanceTransitionError("Only approved payroll can be posted.")
    lines: list[dict[str, Any]] = []
    earnings = PayslipLine.objects.filter(
        payslip__payroll_run=run,
        component_type__in=[ComponentType.EARNING, ComponentType.EMPLOYER_CONTRIBUTION],
    )
    for row in earnings.values("component__expense_account_id").annotate(total=Sum("amount")):
        if not row["component__expense_account_id"]:
            raise FinanceValidationError({"account": ["Missing payroll expense account mapping."]})
        lines.append(
            {
                "account": Account.objects.get(pk=row["component__expense_account_id"]),
                "debit": row["total"],
            }
        )
    net_payable_id = (
        earnings.exclude(component__payable_account_id__isnull=True)
        .values_list("component__payable_account_id", flat=True)
        .first()
    )
    if not net_payable_id:
        raise FinanceValidationError({"account": ["Missing payroll payable account mapping."]})
    lines.append({"account": Account.objects.get(pk=net_payable_id), "credit": run.net_total})
    employer_payables = (
        PayslipLine.objects.filter(
            payslip__payroll_run=run,
            component_type=ComponentType.EMPLOYER_CONTRIBUTION,
        )
        .values("component__payable_account_id")
        .annotate(total=Sum("amount"))
    )
    for row in employer_payables:
        if not row["component__payable_account_id"]:
            raise FinanceValidationError(
                {"account": ["Missing employer contribution payable account mapping."]}
            )
        lines.append(
            {
                "account": Account.objects.get(pk=row["component__payable_account_id"]),
                "credit": row["total"],
            }
        )
    if run.deduction_total:
        deduction_accounts = (
            PayslipLine.objects.filter(
                payslip__payroll_run=run,
                component_type=ComponentType.DEDUCTION,
            )
            .values("component__payable_account_id")
            .annotate(total=Sum("amount"))
        )
        for row in deduction_accounts:
            if not row["component__payable_account_id"]:
                raise FinanceValidationError(
                    {"account": ["Missing deduction payable account mapping."]}
                )
            lines.append(
                {
                    "account": Account.objects.get(pk=row["component__payable_account_id"]),
                    "credit": row["total"],
                }
            )
    period = _period_for(run.company_id, run.payroll_period.payment_date)
    journal = create_journal(
        company=run.company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=run.payroll_period.payment_date,
        description=f"Payroll {run.run_number}",
        created_by=run.created_by,
        source_type="PAYROLL",
        source_id=run.id,
        lines=lines,
    )
    journal.status = "APPROVED"
    journal.approved_by = actor
    journal.approved_at = timezone.now()
    journal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    journal = post_journal(journal=journal, actor=actor)
    run.journal_entry = journal
    run.status = WorkflowStatus.POSTED
    run.save(update_fields=["journal_entry", "status", "updated_at"])
    return run


@transaction.atomic
def create_payroll_payment_batch(*, payroll_run: PayrollRun, actor: User) -> PayrollPaymentBatch:
    run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk)
    if run.status != WorkflowStatus.POSTED:
        raise InvalidFinanceTransitionError("Payroll must be posted before payment batching.")
    batch, created = PayrollPaymentBatch.objects.get_or_create(
        payroll_run=run,
        defaults={
            "batch_number": next_document_number(
                company=run.company, prefix="PAY", year=date.today().year
            ),
            "created_by": actor,
        },
    )
    if created:
        PayrollPaymentItem.objects.bulk_create(
            [
                PayrollPaymentItem(batch=batch, payslip=slip, amount=slip.net_pay)
                for slip in run.payslips.all()
            ]
        )
    return batch


@transaction.atomic
def mark_payroll_item_paid(*, item: PayrollPaymentItem, reference: str) -> PayrollPaymentItem:
    locked = (
        PayrollPaymentItem.objects.select_for_update()
        .select_related("payslip", "batch")
        .get(pk=item.pk)
    )
    if locked.status == PaymentStatus.PAID:
        return locked
    if not reference.strip():
        raise FinanceValidationError({"reference": ["Payment reference is required."]})
    locked.status = PaymentStatus.PAID
    locked.payment_reference = reference.strip()
    locked.save(update_fields=["status", "payment_reference", "updated_at"])
    locked.payslip.payment_status = PaymentStatus.PAID
    locked.payslip.save(update_fields=["payment_status", "updated_at"])
    if not locked.batch.items.exclude(status=PaymentStatus.PAID).exists():
        locked.batch.status = PaymentStatus.PAID
        locked.batch.save(update_fields=["status", "updated_at"])
    return locked


@transaction.atomic
def close_payroll(*, payroll_run: PayrollRun) -> PayrollRun:
    run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk)
    if run.status == WorkflowStatus.CLOSED:
        return run
    if run.status != WorkflowStatus.POSTED or not hasattr(run, "payment_batch"):
        raise InvalidFinanceTransitionError("Posted payroll with a payment batch is required.")
    if run.payment_batch.items.exclude(status=PaymentStatus.PAID).exists():
        raise FinanceValidationError({"payments": ["Every payroll payment must be completed."]})
    run.status = WorkflowStatus.CLOSED
    run.payroll_period.status = WorkflowStatus.CLOSED
    run.payroll_period.save(update_fields=["status", "updated_at"])
    run.save(update_fields=["status", "updated_at"])
    return run


@transaction.atomic
def approve_payroll_variable_input(
    *, item: PayrollVariableInput, actor: User
) -> PayrollVariableInput:
    locked = PayrollVariableInput.objects.select_for_update().get(pk=item.pk)
    if locked.status != WorkflowStatus.SUBMITTED:
        raise InvalidFinanceTransitionError("Only a submitted payroll input can be approved.")
    _maker_checker(locked.created_by_id, actor)
    locked.status = WorkflowStatus.APPROVED
    locked.approved_by = actor
    locked.save(update_fields=["status", "approved_by", "updated_at"])
    return locked


@transaction.atomic
def recover_employee_advance(
    *,
    advance: EmployeeAdvance,
    amount: Decimal,
    recovery_date: date,
    payroll_run: PayrollRun | None = None,
) -> EmployeeAdvanceRecovery:
    locked = EmployeeAdvance.objects.select_for_update().get(pk=advance.pk)
    amount = money(amount)
    if amount <= ZERO or amount > locked.outstanding_amount:
        raise FinanceValidationError(
            {"amount": ["Recovery must be positive and not exceed the outstanding advance."]}
        )
    recovery = EmployeeAdvanceRecovery.objects.create(
        advance=locked,
        payroll_run=payroll_run,
        amount=amount,
        recovery_date=recovery_date,
    )
    locked.recovered_amount = money(locked.recovered_amount + amount)
    if locked.outstanding_amount == ZERO:
        locked.status = WorkflowStatus.CLOSED
    locked.save(update_fields=["recovered_amount", "status", "updated_at"])
    return recovery


@transaction.atomic
def confirm_receipt(*, receipt: PurchaseReceipt) -> PurchaseReceipt:
    locked = (
        PurchaseReceipt.objects.select_for_update(of=("self",))
        .select_related("purchase_order__vendor", "purchase_order__requisition")
        .get(pk=receipt.pk)
    )
    if locked.status != WorkflowStatus.DRAFT:
        raise InvalidFinanceTransitionError("Only a draft receipt can be confirmed.")

    purchase_order = locked.purchase_order
    if purchase_order.status != WorkflowStatus.APPROVED:
        raise FinanceValidationError(
            {"purchase_order": ["Only an approved purchase order can be received."]}
        )
    if purchase_order.company_id != locked.company_id:
        raise FinanceValidationError(
            {"company": ["Receipt and purchase order must belong to the same company."]}
        )
    if (
        purchase_order.vendor.company_id != locked.company_id
        or purchase_order.requisition.company_id != locked.company_id
    ):
        raise FinanceValidationError(
            {"company": ["Purchase-order vendor and requisition must match the receipt company."]}
        )

    line_ids = list(
        PurchaseReceiptLine.objects.filter(receipt=locked).values_list(
            "purchase_order_line_id", flat=True
        )
    )
    if not line_ids:
        raise FinanceValidationError({"lines": ["A receipt must contain at least one line."]})

    purchase_order_lines = {
        line.pk: line
        for line in PurchaseOrderLine.objects.select_for_update()
        .filter(pk__in=line_ids)
        .order_by("pk")
    }
    receipt_lines = list(
        PurchaseReceiptLine.objects.select_for_update()
        .filter(receipt=locked)
        .select_related("receipt", "purchase_order_line")
        .order_by("pk")
    )
    for line in receipt_lines:
        purchase_order_line = purchase_order_lines[line.purchase_order_line_id]
        if purchase_order_line.purchase_order_id != purchase_order.pk:
            raise FinanceValidationError(
                {"purchase_order_line": ["Receipt line belongs to another purchase order."]}
            )
        try:
            line.full_clean()
        except DjangoValidationError as exc:
            detail = exc.message_dict if hasattr(exc, "message_dict") else {"lines": exc.messages}
            raise FinanceValidationError(detail) from exc
        prior = (
            PurchaseReceiptLine.objects.filter(
                purchase_order_line=purchase_order_line,
                receipt__status=WorkflowStatus.APPROVED,
            )
            .exclude(receipt=locked)
            .aggregate(total=Sum("accepted_quantity"))["total"]
            or ZERO
        )
        if prior + line.accepted_quantity > purchase_order_line.quantity:
            raise FinanceValidationError({"quantity": ["Receipt exceeds ordered quantity."]})
    locked.status = WorkflowStatus.APPROVED
    locked.save(update_fields=["status", "updated_at"])
    return locked


def validate_vendor_bill_match(*, bill: VendorBill) -> None:
    for line in bill.lines.select_related("purchase_order_line", "receipt_line"):
        if bill.purchase_order_id and line.purchase_order_line_id is None:
            raise FinanceValidationError(
                {"match": ["Bill line is not linked to its purchase order."]}
            )
        if line.purchase_order_line and (
            line.quantity > line.purchase_order_line.quantity
            or line.unit_price > line.purchase_order_line.unit_price
        ):
            raise FinanceValidationError(
                {"match": ["Bill exceeds purchase-order quantity or price."]}
            )
        if bill.match_type == MatchType.THREE_WAY:
            receipt_line = line.receipt_line
            if receipt_line is None or line.quantity > receipt_line.accepted_quantity:  # noqa: SIM102
                raise FinanceValidationError({"match": ["Bill exceeds accepted receipt quantity."]})


def _validate_vendor_bill_for_workflow(bill: VendorBill) -> list[Any]:
    try:
        validate_vendor_bill_header(
            company_id=bill.company_id,
            vendor=bill.vendor,
            purchase_order=bill.purchase_order,
        )
        validate_vendor_payable_account(company=bill.company, account=bill.vendor.payable_account)
        lines = list(
            bill.lines.select_related(
                "expense_account",
                "purchase_order_line__purchase_order",
                "receipt_line__receipt",
            )
        )
        if not lines:
            raise DjangoValidationError({"lines": "A Vendor Bill must contain at least one line."})
        for line in lines:
            validate_vendor_bill_line(
                bill=bill,
                account=line.expense_account,
                purchase_order_line=line.purchase_order_line,
                receipt_line=line.receipt_line,
            )
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"bill": exc.messages}
        raise FinanceValidationError(detail) from exc
    validate_vendor_bill_match(bill=bill)
    subtotal = money(sum((line.quantity * line.unit_price for line in lines), ZERO))
    tax = money(sum((line.tax_amount for line in lines), ZERO))
    if (
        subtotal != money(bill.subtotal)
        or tax != money(bill.tax_amount)
        or money(subtotal + tax) != money(bill.total_amount)
    ):
        raise FinanceValidationError({"total": ["Vendor Bill totals do not match its lines."]})
    if bill.match_exception.strip():
        raise FinanceValidationError({"match_exception": ["Resolve the matching exception first."]})
    return lines


@transaction.atomic
def submit_vendor_bill(*, bill: VendorBill, actor: User) -> VendorBill:
    locked = (
        VendorBill.objects.select_for_update(of=("self",))
        .select_related("company", "vendor__payable_account", "purchase_order")
        .get(pk=bill.pk)
    )
    if locked.status != WorkflowStatus.DRAFT:
        raise InvalidFinanceTransitionError("Only a draft Vendor Bill can be submitted.")
    if locked.journal_entry_id:
        raise FinanceValidationError(
            {"journal_entry": ["A draft Vendor Bill cannot have a journal."]}
        )
    _validate_vendor_bill_for_workflow(locked)
    return cast(
        VendorBill,
        submit_finance_document(
            obj=locked, actor=actor, document_type=ApprovalDocumentType.VENDOR_BILL
        ),
    )


@transaction.atomic
def approve_vendor_bill(*, bill: VendorBill, actor: User) -> VendorBill:
    locked = (
        VendorBill.objects.select_for_update(of=("self",))
        .select_related("company", "vendor__payable_account", "purchase_order")
        .get(pk=bill.pk)
    )
    if locked.status != WorkflowStatus.SUBMITTED:
        raise InvalidFinanceTransitionError("Only a submitted Vendor Bill can be approved.")
    _validate_vendor_bill_for_workflow(locked)
    return cast(
        VendorBill,
        approve_finance_document(
            obj=locked, actor=actor, document_type=ApprovalDocumentType.VENDOR_BILL
        ),
    )


@transaction.atomic
def reject_vendor_bill(*, bill: VendorBill, actor: User, reason: str) -> VendorBill:
    locked = VendorBill.objects.select_for_update().get(pk=bill.pk)
    _maker_checker(locked.created_by_id, actor)
    return cast(
        VendorBill,
        reject_finance_document(
            obj=locked,
            actor=actor,
            document_type=ApprovalDocumentType.VENDOR_BILL,
            reason=reason,
        ),
    )


@transaction.atomic
def post_vendor_bill(*, bill: VendorBill, actor: User) -> VendorBill:
    locked = (
        VendorBill.objects.select_for_update(of=("self",))
        .select_related("company", "vendor__payable_account", "purchase_order", "journal_entry")
        .get(pk=bill.pk)
    )
    if locked.status == WorkflowStatus.POSTED and locked.journal_entry_id:
        return locked
    if locked.status != WorkflowStatus.APPROVED:
        raise InvalidFinanceTransitionError("Only an approved Vendor Bill can be posted.")
    if locked.journal_entry_id:
        raise FinanceValidationError({"journal_entry": ["Vendor Bill already has a journal."]})
    lines = _validate_vendor_bill_for_workflow(locked)
    period = _period_for(locked.company_id, locked.bill_date)
    journal = create_journal(
        company=locked.company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=locked.bill_date,
        description=f"Vendor Bill {locked.bill_number}",
        created_by=locked.created_by,
        source_type="VENDOR_BILL",
        source_id=locked.id,
        lines=[
            *[{"account": line.expense_account, "debit": line.line_total} for line in lines],
            {"account": locked.vendor.payable_account, "credit": locked.total_amount},
        ],
    )
    journal.status, journal.approved_by, journal.approved_at = "APPROVED", actor, timezone.now()
    journal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    journal = post_journal(journal=journal, actor=actor)
    locked.status = WorkflowStatus.POSTED
    locked.journal_entry = journal
    locked.save(update_fields=["status", "journal_entry", "updated_at"])
    return locked


@transaction.atomic
def approve_and_post_vendor_bill(*, bill: VendorBill, actor: User) -> VendorBill:
    current = VendorBill.objects.get(pk=bill.pk)
    if current.status == WorkflowStatus.POSTED and current.journal_entry_id:
        return current
    approved = approve_vendor_bill(bill=bill, actor=actor)
    if approved.status != WorkflowStatus.APPROVED:
        return approved
    return post_vendor_bill(bill=approved, actor=actor)


@transaction.atomic
def approve_and_post_expense(
    *, expense: CompanyExpense, actor: User, payable_account: Account
) -> CompanyExpense:
    locked = (
        CompanyExpense.objects.select_for_update().select_related("category").get(pk=expense.pk)
    )
    if locked.journal_entry_id:
        return locked
    if locked.status != WorkflowStatus.SUBMITTED:
        raise InvalidFinanceTransitionError("Only a submitted expense can be approved.")
    _maker_checker(locked.created_by_id, actor)
    if (
        locked.category.receipt_required
        and locked.amount >= locked.category.receipt_threshold
        and not locked.company.finance_attachments.filter(object_id=locked.id).exists()
    ):
        raise FinanceValidationError({"attachment": ["A receipt is required for this expense."]})
    period = _period_for(locked.company_id, locked.expense_date)
    journal = create_journal(
        company=locked.company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=locked.expense_date,
        description=locked.description,
        created_by=locked.created_by,
        source_type="EXPENSE",
        source_id=locked.id,
        lines=[
            {
                "account": locked.category.expense_account,
                "cost_center": locked.cost_center,
                "debit": locked.amount,
            },
            {"account": payable_account, "credit": locked.amount},
        ],
    )
    journal.status, journal.approved_by, journal.approved_at = "APPROVED", actor, timezone.now()
    journal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    journal = post_journal(journal=journal, actor=actor)
    locked.status, locked.approved_by, locked.journal_entry = (
        WorkflowStatus.APPROVED,
        actor,
        journal,
    )
    locked.save(update_fields=["status", "approved_by", "journal_entry", "updated_at"])
    return locked


@transaction.atomic
def approve_and_post_expense_claim(
    *, claim: ExpenseClaim, actor: User, reimbursement_payable: Account
) -> ExpenseClaim:
    locked = ExpenseClaim.objects.select_for_update().get(pk=claim.pk)
    if locked.journal_entry_id:
        return locked
    if locked.status != WorkflowStatus.SUBMITTED:
        raise InvalidFinanceTransitionError("Only a submitted expense claim can be approved.")
    _maker_checker(locked.created_by_id, actor)
    lines = list(locked.lines.select_related("category__expense_account", "cost_center"))
    total = money(sum((line.amount for line in lines), ZERO))
    if not lines or total != money(locked.total_amount):
        raise FinanceValidationError({"lines": ["Claim lines must equal the claim total."]})
    for line in lines:
        if (
            line.category.receipt_required
            and line.amount >= line.category.receipt_threshold
            and not FinanceAttachment.objects.filter(object_id=locked.id).exists()
        ):
            raise FinanceValidationError({"attachment": ["Claim receipt is required."]})
    period = _period_for(locked.company_id, locked.claim_date)
    journal = create_journal(
        company=locked.company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=locked.claim_date,
        description=f"Employee expense claim {locked.claim_number}",
        created_by=locked.created_by,
        source_type="EXPENSE_CLAIM",
        source_id=locked.id,
        lines=[
            *[
                {
                    "account": line.category.expense_account,
                    "cost_center": line.cost_center,
                    "debit": line.amount,
                }
                for line in lines
            ],
            {"account": reimbursement_payable, "credit": total},
        ],
    )
    journal.status, journal.approved_by, journal.approved_at = "APPROVED", actor, timezone.now()
    journal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    journal = post_journal(journal=journal, actor=actor)
    locked.status, locked.approved_by, locked.journal_entry = (
        WorkflowStatus.APPROVED,
        actor,
        journal,
    )
    locked.save(update_fields=["status", "approved_by", "journal_entry", "updated_at"])
    return locked


@transaction.atomic
def post_fund_transfer(*, transfer: FundTransfer, actor: User) -> FundTransfer:
    locked = FundTransfer.objects.select_for_update().get(pk=transfer.pk)
    if locked.journal_entry_id:
        return locked
    if locked.status != WorkflowStatus.APPROVED:
        raise InvalidFinanceTransitionError("Only an approved fund transfer can be posted.")
    if locked.source_account_id == locked.destination_account_id:
        raise FinanceValidationError(
            {"destination_account": ["Source and destination must differ."]}
        )
    period = _period_for(locked.company_id, locked.transfer_date)
    journal = create_journal(
        company=locked.company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=locked.transfer_date,
        description=f"Fund transfer {locked.transfer_number}",
        created_by=locked.created_by,
        source_type="FUND_TRANSFER",
        source_id=locked.id,
        lines=[
            {"account": locked.destination_account, "debit": locked.amount},
            {"account": locked.source_account, "credit": locked.amount},
        ],
    )
    journal.status, journal.approved_by, journal.approved_at = "APPROVED", actor, timezone.now()
    journal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    journal = post_journal(journal=journal, actor=actor)
    locked.status, locked.journal_entry = WorkflowStatus.POSTED, journal
    locked.save(update_fields=["status", "journal_entry", "updated_at"])
    return locked


def _validate_vendor_payment_voucher(voucher: PaymentVoucher) -> None:
    if not voucher.vendor_bill_id:
        raise FinanceValidationError({"vendor_bill": ["Vendor Bill is required."]})
    bill = VendorBill.objects.select_related("vendor__payable_account").get(
        pk=voucher.vendor_bill_id
    )
    if bill.company_id != voucher.company_id:
        raise FinanceValidationError({"vendor_bill": ["Vendor Bill must belong to the company."]})
    validate_vendor_payment_values(bill=bill, amount=voucher.amount)
    if voucher.payment_status != PaymentStatus.PENDING:
        raise FinanceValidationError({"payment_status": ["Voucher is not pending payment."]})
    if voucher.journal_entry_id:
        raise FinanceValidationError({"journal_entry": ["Voucher already has a journal."]})


@transaction.atomic
def submit_vendor_payment(*, voucher: PaymentVoucher, actor: User) -> PaymentVoucher:
    locked = PaymentVoucher.objects.select_for_update(of=("self",)).get(pk=voucher.pk)
    _validate_vendor_payment_voucher(locked)
    return cast(
        PaymentVoucher,
        submit_finance_document(
            obj=locked, actor=actor, document_type=ApprovalDocumentType.PAYMENT_VOUCHER
        ),
    )


@transaction.atomic
def approve_vendor_payment(*, voucher: PaymentVoucher, actor: User) -> PaymentVoucher:
    locked = PaymentVoucher.objects.select_for_update(of=("self",)).get(pk=voucher.pk)
    _validate_vendor_payment_voucher(locked)
    return cast(
        PaymentVoucher,
        approve_finance_document(
            obj=locked, actor=actor, document_type=ApprovalDocumentType.PAYMENT_VOUCHER
        ),
    )


@transaction.atomic
def reject_vendor_payment(*, voucher: PaymentVoucher, actor: User, reason: str) -> PaymentVoucher:
    locked = PaymentVoucher.objects.select_for_update(of=("self",)).get(pk=voucher.pk)
    _maker_checker(locked.created_by_id, actor)
    return cast(
        PaymentVoucher,
        reject_finance_document(
            obj=locked,
            actor=actor,
            document_type=ApprovalDocumentType.PAYMENT_VOUCHER,
            reason=reason,
        ),
    )


@transaction.atomic
def pay_vendor_voucher(
    *, voucher: PaymentVoucher, actor: User, cash_account: Account, reference: str
) -> PaymentVoucher:
    locked = (
        PaymentVoucher.objects.select_for_update(of=("self",))
        .select_related("vendor_bill__vendor")
        .get(pk=voucher.pk)
    )
    if locked.payment_status == PaymentStatus.PAID:
        return locked
    if locked.status != WorkflowStatus.APPROVED or not locked.vendor_bill_id:
        raise InvalidFinanceTransitionError("An approved bill payment voucher is required.")
    if locked.journal_entry_id:
        raise FinanceValidationError({"journal_entry": ["Payment Voucher already has a journal."]})
    validate_direct_payment_account(company_id=locked.company_id, account=cash_account)
    bill = apply_vendor_bill_payment(
        bill_id=locked.vendor_bill_id, company_id=locked.company_id, amount=locked.amount
    )
    period = _period_for(locked.company_id, locked.payment_date)
    journal = create_journal(
        company=locked.company,
        fiscal_year=period.fiscal_year,
        accounting_period=period,
        entry_date=locked.payment_date,
        description=f"Vendor payment {locked.voucher_number}",
        created_by=locked.created_by,
        source_type="PAYMENT_VOUCHER",
        source_id=locked.id,
        lines=[
            {"account": bill.vendor.payable_account, "debit": locked.amount},
            {"account": cash_account, "credit": locked.amount},
        ],
    )
    journal.status, journal.approved_by, journal.approved_at = "APPROVED", actor, timezone.now()
    journal.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    journal = post_journal(journal=journal, actor=actor)
    locked.payment_status = PaymentStatus.PAID
    locked.status = WorkflowStatus.PAID
    locked.payment_reference = reference.strip()
    locked.journal_entry = journal
    locked.save(
        update_fields=[
            "payment_status",
            "status",
            "payment_reference",
            "journal_entry",
            "updated_at",
        ]
    )
    return locked


@transaction.atomic
def record_petty_cash(
    *,
    fund: PettyCashFund,
    transaction_type: str,
    amount: Decimal,
    transaction_date: date,
    description: str,
    actor: User,
) -> PettyCashTransaction:
    locked = PettyCashFund.objects.select_for_update().get(pk=fund.pk)
    amount = money(amount)
    credits = [
        PettyCashTransactionType.OPENING,
        PettyCashTransactionType.REIMBURSEMENT,
        PettyCashTransactionType.RETURN,
    ]
    totals = locked.transactions.values("transaction_type").annotate(total=Sum("amount"))
    balance = sum(
        (row["total"] if row["transaction_type"] in credits else -row["total"] for row in totals),
        ZERO,
    )
    if transaction_type == PettyCashTransactionType.DISBURSEMENT and amount > balance:
        raise FinanceValidationError({"amount": ["Petty cash balance is insufficient."]})
    return PettyCashTransaction.objects.create(
        fund=locked,
        transaction_type=transaction_type,
        transaction_date=transaction_date,
        amount=amount,
        description=description,
        created_by=actor,
    )


def petty_cash_balance(*, fund: PettyCashFund) -> Decimal:
    credits = [
        PettyCashTransactionType.OPENING,
        PettyCashTransactionType.REIMBURSEMENT,
        PettyCashTransactionType.RETURN,
    ]
    total = ZERO
    for row in fund.transactions.values("transaction_type").annotate(total=Sum("amount")):
        total += row["total"] if row["transaction_type"] in credits else -row["total"]
    return money(total)


@transaction.atomic
def import_bank_csv(*, bank_account: BankAccount, content: bytes, actor: User) -> BankStatement:
    digest = hashlib.sha256(content).hexdigest()
    if BankStatement.objects.filter(import_hash=digest).exists():
        raise FinanceValidationError({"file": ["This bank statement was already imported."]})
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    rows = list(reader)
    required = {"date", "description", "amount"}
    if not rows or not required.issubset(reader.fieldnames or []):
        raise FinanceValidationError(
            {"file": ["CSV requires date, description, and amount columns."]}
        )
    statement = BankStatement.objects.create(
        bank_account=bank_account,
        statement_date=max(date.fromisoformat(row["date"]) for row in rows),
        opening_balance=money(rows[0].get("opening_balance") or ZERO),
        closing_balance=money(rows[-1].get("closing_balance") or ZERO),
        import_hash=digest,
        imported_by=actor,
    )
    for row in rows:
        line = BankStatementLine.objects.create(
            statement=statement,
            transaction_date=date.fromisoformat(row["date"]),
            reference=row.get("reference", ""),
            description=row["description"],
            amount=money(row["amount"]),
        )
        amount = abs(line.amount)
        candidates = (
            JournalEntry.objects.filter(
                company=bank_account.company,
                status="POSTED",
                entry_date=line.transaction_date,
                lines__account=bank_account.ledger_account,
            )
            .filter(models.Q(lines__debit=amount) | models.Q(lines__credit=amount))
            .distinct()
        )
        if candidates.count() == 1:
            line.suggested_journal = candidates.first()
            line.status = ReconciliationStatus.SUGGESTED
            line.save(update_fields=["suggested_journal", "status", "updated_at"])
    return statement


@transaction.atomic
def reconcile_bank_line(
    *, line: BankStatementLine, journal: JournalEntry, actor: User
) -> BankStatementLine:
    locked = BankStatementLine.objects.select_for_update().get(pk=line.pk)
    if locked.status == ReconciliationStatus.MATCHED:
        return locked
    if journal.status != "POSTED" or journal.company_id != locked.statement.bank_account.company_id:
        raise FinanceValidationError(
            {"journal": ["A posted journal from the same company is required."]}
        )
    locked.status = ReconciliationStatus.MATCHED
    locked.matched_journal = journal
    locked.reconciled_by = actor
    locked.reconciled_at = timezone.now()
    locked.save(
        update_fields=["status", "matched_journal", "reconciled_by", "reconciled_at", "updated_at"]
    )
    return locked


@transaction.atomic
def classify_bank_line(*, line: BankStatementLine, status: str, actor: User) -> BankStatementLine:
    if status not in [ReconciliationStatus.IGNORED, ReconciliationStatus.EXCEPTION]:
        raise FinanceValidationError({"status": ["Only ignored or exception is allowed here."]})
    locked = BankStatementLine.objects.select_for_update().get(pk=line.pk)
    if locked.status == ReconciliationStatus.MATCHED:
        raise InvalidFinanceTransitionError("A matched bank line cannot be reclassified.")
    locked.status = status
    locked.reconciled_by = actor
    locked.reconciled_at = timezone.now()
    locked.save(update_fields=["status", "reconciled_by", "reconciled_at", "updated_at"])
    return locked


@transaction.atomic
def approve_budget(*, budget: Budget, actor: User) -> Budget:
    result: Budget = approve_finance_document(
        obj=budget, actor=actor, document_type=ApprovalDocumentType.BUDGET
    )
    return result
