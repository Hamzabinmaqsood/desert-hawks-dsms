from django.db import models

from dsms.identity.models import User
from dsms.workforce.enums import EmploymentStatus

from .base import WorkforceLogModel
from .employee import Employee


class EmployeeStatusHistory(WorkforceLogModel):
    """An immutable record of a single employment-status change.

    Created exclusively by the status-transition services in
    :mod:`dsms.workforce.services`, atomically with the ``Employee`` row's
    ``employment_status`` update -- never via signals, and never edited or
    deleted afterwards.
    """

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="Employee",
    )
    previous_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        null=True,
        blank=True,
        verbose_name="Previous status",
    )
    new_status = models.CharField(
        max_length=20, choices=EmploymentStatus.choices, verbose_name="New status"
    )
    effective_date = models.DateField(verbose_name="Effective date")
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
        verbose_name = "Employee status history"
        verbose_name_plural = "Employee status history"
        indexes = [
            models.Index(fields=["employee", "-created_at"], name="wf_status_hist_emp_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_number}: {self.previous_status} -> {self.new_status}"
