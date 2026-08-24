from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .base import CODE_VALIDATOR, OrganizationBaseModel, normalize_code
from .company import Company
from .department import Department


class Designation(OrganizationBaseModel):
    """A job title/level that can be assigned within a company."""

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="designations",
        verbose_name="Company",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="designations",
        verbose_name="Department",
    )
    code = models.CharField(max_length=20, verbose_name="Designation code")
    name = models.CharField(max_length=150, verbose_name="Designation name")
    level = models.PositiveIntegerField(verbose_name="Level")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Sort order")
    is_supervisory = models.BooleanField(default=False, verbose_name="Is supervisory")
    description = models.TextField(blank=True, verbose_name="Description")

    class Meta:
        ordering = ["company__code", "sort_order", "code"]
        verbose_name = "Designation"
        verbose_name_plural = "Designations"
        indexes = [
            models.Index(fields=["company", "department"], name="org_designation_dept_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_designation_code_per_company"
            ),
            models.CheckConstraint(condition=Q(level__gt=0), name="chk_designation_level_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.company.code} / {self.code}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()

        errors: dict[str, str] = {}
        if self.level is not None and self.level <= 0:
            errors["level"] = "Level must be greater than zero."
        if (
            self.department_id
            and self.company_id
            and self.department is not None
            and self.department.company_id != self.company_id
        ):
            errors["department"] = (
                "The selected department does not belong to the selected company."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        super().save(*args, **kwargs)
