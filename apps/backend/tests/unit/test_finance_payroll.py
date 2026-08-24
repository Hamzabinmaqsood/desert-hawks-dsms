from datetime import date
from decimal import Decimal

import pytest

from dsms.finance import domain_services
from dsms.finance.enums import CalculationType, ComponentType, WorkflowStatus
from dsms.finance.exceptions import FinanceValidationError, MakerCheckerError
from dsms.finance.payroll_models import (
    EmployeeCompensation,
    PayrollComponent,
    PayrollPeriod,
    PayrollRun,
    PayrollVariableInput,
    SalaryStructure,
    SalaryStructureComponent,
    StatutoryScheme,
    TaxBracket,
    TaxScheme,
)
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def payroll():  # type: ignore[no-untyped-def]
    company = CompanyFactory.create()
    maker, checker = UserFactory.create(), UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    employee = EmployeeFactory.create(company=company)
    earning = PayrollComponent.objects.create(
        company=company,
        code="BASIC",
        name="Basic salary",
        component_type=ComponentType.EARNING,
        calculation_type=CalculationType.FIXED,
        expense_account=accounts["expense"],
        payable_account=accounts["payable"],
    )
    bonus = PayrollComponent.objects.create(
        company=company,
        code="BONUS",
        name="Approved bonus",
        component_type=ComponentType.EARNING,
        calculation_type=CalculationType.VARIABLE,
        expense_account=accounts["expense"],
        payable_account=accounts["payable"],
    )
    deduction = PayrollComponent.objects.create(
        company=company,
        code="TAX",
        name="Tax",
        component_type=ComponentType.DEDUCTION,
        calculation_type=CalculationType.FIXED,
        payable_account=accounts["deduction"],
    )
    structure = SalaryStructure.objects.create(company=company, code="MONTHLY", name="Monthly")
    SalaryStructureComponent.objects.create(
        salary_structure=structure, payroll_component=earning, amount=Decimal("1000.00")
    )
    SalaryStructureComponent.objects.create(
        salary_structure=structure, payroll_component=bonus, amount=Decimal("0.00")
    )
    SalaryStructureComponent.objects.create(
        salary_structure=structure, payroll_component=deduction, amount=Decimal("100.00")
    )
    EmployeeCompensation.objects.create(
        employee=employee,
        salary_structure=structure,
        base_salary=Decimal("1000.00"),
        effective_from=date(2026, 1, 1),
        created_by=maker,
    )
    period = PayrollPeriod.objects.create(
        company=company,
        name="August 2026",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        payment_date=date(2026, 8, 31),
    )
    PayrollVariableInput.objects.create(
        payroll_period=period,
        employee=employee,
        component=bonus,
        amount=Decimal("200.00"),
        status=WorkflowStatus.APPROVED,
        created_by=maker,
        approved_by=checker,
    )
    run = PayrollRun.objects.create(
        company=company,
        payroll_period=period,
        run_number="PR-2026-000001",
        created_by=maker,
    )
    return run, maker, checker


def test_payroll_calculate_uses_only_approved_variable_inputs(payroll) -> None:  # type: ignore[no-untyped-def]
    run, _maker, _checker = payroll
    run = domain_services.calculate_payroll(payroll_run=run)
    slip = run.payslips.get()
    assert (slip.gross_pay, slip.deductions, slip.net_pay) == (
        Decimal("1200.00"),
        Decimal("100.00"),
        Decimal("1100.00"),
    )


def test_payroll_maker_checker_post_and_payment_cycle(payroll) -> None:  # type: ignore[no-untyped-def]
    run, maker, checker = payroll
    run = domain_services.calculate_payroll(payroll_run=run)
    run = domain_services.submit_finance_document(obj=run, actor=maker, document_type="PAYROLL")
    with pytest.raises(MakerCheckerError):
        domain_services.approve_finance_document(obj=run, actor=maker, document_type="PAYROLL")
    run = domain_services.approve_finance_document(obj=run, actor=checker, document_type="PAYROLL")
    run = domain_services.post_payroll(payroll_run=run, actor=checker)
    assert run.journal_entry and run.journal_entry.total_debit == run.journal_entry.total_credit
    batch = domain_services.create_payroll_payment_batch(payroll_run=run, actor=checker)
    item = domain_services.mark_payroll_item_paid(item=batch.items.get(), reference="BANK-1")
    assert item.payslip.payment_status == "PAID" and item.batch.status == "PAID"
    run = domain_services.close_payroll(payroll_run=run)
    assert run.status == WorkflowStatus.CLOSED
    assert run.payroll_period.status == WorkflowStatus.CLOSED


def test_payroll_recalculation_replaces_existing_payslips(payroll) -> None:  # type: ignore[no-untyped-def]
    run, *_ = payroll
    domain_services.calculate_payroll(payroll_run=run)
    first_id = run.payslips.get().id
    domain_services.calculate_payroll(payroll_run=run)
    assert run.payslips.count() == 1 and run.payslips.get().id != first_id


def test_missing_compensation_is_rejected() -> None:
    company = CompanyFactory.create()
    EmployeeFactory.create(company=company)
    period = PayrollPeriod.objects.create(
        company=company,
        name="August",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        payment_date=date(2026, 8, 31),
    )
    run = PayrollRun.objects.create(
        company=company, payroll_period=period, run_number="PR-1", created_by=UserFactory.create()
    )
    with pytest.raises(FinanceValidationError):
        domain_services.calculate_payroll(payroll_run=run)


def test_tax_brackets_and_statutory_schemes_change_payslip(payroll) -> None:  # type: ignore[no-untyped-def]
    run, _maker, _checker = payroll
    compensation = EmployeeCompensation.objects.get()
    expense_account = PayrollComponent.objects.get(code="BASIC").expense_account
    payable_account = PayrollComponent.objects.get(code="TAX").payable_account
    tax_component = PayrollComponent.objects.create(
        company=run.company,
        code="INCOME-TAX",
        name="Income tax",
        component_type=ComponentType.DEDUCTION,
        calculation_type=CalculationType.FIXED,
        payable_account=payable_account,
    )
    employer_component = PayrollComponent.objects.create(
        company=run.company,
        code="EMP-CONTRIB",
        name="Employer contribution",
        component_type=ComponentType.EMPLOYER_CONTRIBUTION,
        calculation_type=CalculationType.PERCENTAGE,
        expense_account=expense_account,
        payable_account=payable_account,
    )
    employee_component = PayrollComponent.objects.create(
        company=run.company,
        code="EMP-DEDUCT",
        name="Employee contribution",
        component_type=ComponentType.DEDUCTION,
        calculation_type=CalculationType.PERCENTAGE,
        payable_account=payable_account,
    )
    scheme = TaxScheme.objects.create(
        company=run.company,
        name="Test tax",
        effective_from=date(2026, 1, 1),
        deduction_component=tax_component,
    )
    TaxBracket.objects.create(
        scheme=scheme,
        lower_bound=Decimal("0"),
        rate=Decimal("10"),
    )
    StatutoryScheme.objects.create(
        company=run.company,
        code="SOCIAL",
        name="Social contribution",
        employee_rate=Decimal("2"),
        employer_rate=Decimal("3"),
        employee_component=employee_component,
        employer_component=employer_component,
    )
    compensation.tax_scheme = scheme
    compensation.save(update_fields=["tax_scheme", "updated_at"])
    run = domain_services.calculate_payroll(payroll_run=run)
    slip = run.payslips.get()
    assert slip.gross_pay == Decimal("1200.00")
    assert slip.deductions == Decimal("240.00")
    assert slip.net_pay == Decimal("960.00")
