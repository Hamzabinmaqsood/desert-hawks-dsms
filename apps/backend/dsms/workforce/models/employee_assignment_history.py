from django.db import models
from django.db.models import Q

from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation

from .base import WorkforceLogModel
from .employee import Employee


class EmployeeAssignmentHistory(WorkforceLogModel):
    """An immutable record of the employee's organizational home assignment over time.

    Not to be confused with future guard-to-client/site deployment history --
    this tracks company/branch/department/designation, the employee's HR home
    assignment. Created exclusively by
    :func:`dsms.workforce.services.change_employee_organization` (and at
    employee creation), which atomically closes the previous open-ended row
    before creating the new one.
    """

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="assignment_history",
        verbose_name="Employee",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="employee_assignment_history",
        verbose_name="Company",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employee_assignment_history",
        verbose_name="Branch",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employee_assignment_history",
        verbose_name="Department",
    )
    designation = models.ForeignKey(
        Designation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employee_assignment_history",
        verbose_name="Designation",
    )
    effective_from = models.DateField(verbose_name="Effective from")
    effective_to = models.DateField(null=True, blank=True, verbose_name="Effective to")
    reason = models.TextField(blank=True, verbose_name="Reason")
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="Changed by",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Employee assignment history"
        verbose_name_plural = "Employee assignment history"
        indexes = [
            models.Index(fields=["employee", "-created_at"], name="wf_assign_hist_emp_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(effective_to__isnull=True),
                name="uniq_emp_open_assignment",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.employee.employee_number}: "
            f"{self.effective_from} -> {self.effective_to or '...'}"
        )
