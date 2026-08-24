from decimal import Decimal

from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.identity.models import User
from dsms.organization.models import Company
from dsms.workforce.models import Employee

from .enums import CalculationType, ComponentType, PaymentStatus, WorkflowStatus
from .models import Account, CostCenter, JournalEntry


class EmployeePaymentProfile(UUIDModel, TimeStampedModel):
    employee = models.OneToOneField(
        Employee, on_delete=models.PROTECT, related_name="payment_profile"
    )
    bank_name = models.CharField(max_length=120)
    account_title = models.CharField(max_length=120)
    account_number_encrypted = models.TextField()
    iban_encrypted = models.TextField(blank=True)
    payment_method = models.CharField(max_length=20, default="BANK")
    is_verified = models.BooleanField(default=False)


class PayrollComponent(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="payroll_components"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    component_type = models.CharField(max_length=30, choices=ComponentType.choices)
    calculation_type = models.CharField(max_length=20, choices=CalculationType.choices)
    taxable = models.BooleanField(default=False)
    expense_account = models.ForeignKey(
        Account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_expense_components",
    )
    payable_account = models.ForeignKey(
        Account,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payroll_payable_components",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_pay_component")
        ]


class SalaryStructure(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="salary_structures")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_salary_structure")
        ]


class SalaryStructureComponent(UUIDModel):
    salary_structure = models.ForeignKey(
        SalaryStructure, on_delete=models.PROTECT, related_name="components"
    )
    payroll_component = models.ForeignKey(
        PayrollComponent, on_delete=models.PROTECT, related_name="structure_components"
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    percentage = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    sequence = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["salary_structure", "payroll_component"], name="uniq_structure_component"
            )
        ]


class EmployeeCompensation(UUIDModel, TimeStampedModel):
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="compensation_history"
    )
    salary_structure = models.ForeignKey(
        SalaryStructure, on_delete=models.PROTECT, related_name="employee_compensations"
    )
    cost_center = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employee_compensations",
    )
    base_salary = models.DecimalField(max_digits=18, decimal_places=2)
    tax_scheme = models.ForeignKey(
        "finance.TaxScheme",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="employee_compensations",
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_compensations"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True)
                | Q(effective_to__gte=models.F("effective_from")),
                name="comp_dates_valid",
            )
        ]


class TaxScheme(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="tax_schemes")
    name = models.CharField(max_length=120)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    deduction_component = models.ForeignKey(
        PayrollComponent,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tax_schemes",
    )


class TaxBracket(UUIDModel):
    scheme = models.ForeignKey(TaxScheme, on_delete=models.PROTECT, related_name="brackets")
    lower_bound = models.DecimalField(max_digits=18, decimal_places=2)
    upper_bound = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    rate = models.DecimalField(max_digits=8, decimal_places=4)
    fixed_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))


class StatutoryScheme(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="statutory_schemes")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    employee_rate = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    employer_rate = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))
    employee_component = models.ForeignKey(
        PayrollComponent, on_delete=models.PROTECT, related_name="employee_statutory_schemes"
    )
    employer_component = models.ForeignKey(
        PayrollComponent, on_delete=models.PROTECT, related_name="employer_statutory_schemes"
    )


class PayrollPeriod(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="payroll_periods")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    payment_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "start_date", "end_date"], name="uniq_payroll_period"
            )
        ]


class PayrollVariableInput(UUIDModel, TimeStampedModel):
    payroll_period = models.ForeignKey(
        PayrollPeriod, on_delete=models.PROTECT, related_name="variable_inputs"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="payroll_variable_inputs"
    )
    component = models.ForeignKey(
        PayrollComponent, on_delete=models.PROTECT, related_name="variable_inputs"
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_payroll_inputs"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_payroll_inputs",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_period", "employee", "component"], name="uniq_payroll_input"
            )
        ]


class PayrollRun(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="payroll_runs")
    payroll_period = models.ForeignKey(PayrollPeriod, on_delete=models.PROTECT, related_name="runs")
    run_number = models.CharField(max_length=30)
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    gross_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    deduction_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_payroll_runs"
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_payroll_runs"
    )
    journal_entry = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="payroll_run"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "run_number"], name="uniq_payroll_run_number"
            )
        ]


class Payslip(UUIDModel, TimeStampedModel):
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.PROTECT, related_name="payslips")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payslips")
    gross_pay = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    deductions = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    net_pay = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "employee"], name="uniq_run_employee_payslip"
            )
        ]


class PayslipLine(UUIDModel):
    payslip = models.ForeignKey(Payslip, on_delete=models.PROTECT, related_name="lines")
    component = models.ForeignKey(
        PayrollComponent, on_delete=models.PROTECT, related_name="payslip_lines"
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    component_type = models.CharField(max_length=30, choices=ComponentType.choices)
    source = models.CharField(max_length=30)


class PayrollPaymentBatch(UUIDModel, TimeStampedModel):
    payroll_run = models.OneToOneField(
        PayrollRun, on_delete=models.PROTECT, related_name="payment_batch"
    )
    batch_number = models.CharField(max_length=30, unique=True)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_payroll_batches"
    )


class PayrollPaymentItem(UUIDModel, TimeStampedModel):
    batch = models.ForeignKey(PayrollPaymentBatch, on_delete=models.PROTECT, related_name="items")
    payslip = models.OneToOneField(Payslip, on_delete=models.PROTECT, related_name="payment_item")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    payment_reference = models.CharField(max_length=100, blank=True)


class EmployeeAdvance(UUIDModel, TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="advances")
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    recovered_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    purpose = models.TextField()
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_employee_advances"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_employee_advances",
    )

    @property
    def outstanding_amount(self) -> Decimal:
        return self.amount - self.recovered_amount


class EmployeeAdvanceRecovery(UUIDModel, TimeStampedModel):
    advance = models.ForeignKey(
        EmployeeAdvance, on_delete=models.PROTECT, related_name="recoveries"
    )
    payroll_run = models.ForeignKey(
        PayrollRun,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="advance_recoveries",
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    recovery_date = models.DateField()
    journal_entry = models.ForeignKey(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="advance_recoveries",
    )
