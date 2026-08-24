from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.organization.enums import DepartmentScope

from .base import CODE_VALIDATOR, OrganizationBaseModel, normalize_code
from .branch import Branch
from .company import Company


class Department(OrganizationBaseModel):
    """An organizational unit within a company, optionally scoped to a branch."""

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="departments",
        verbose_name="Company",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="Parent department",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="departments",
        verbose_name="Branch",
    )
    code = models.CharField(max_length=20, verbose_name="Department code")
    name = models.CharField(max_length=150, verbose_name="Department name")
    scope = models.CharField(max_length=10, choices=DepartmentScope.choices, verbose_name="Scope")
    description = models.TextField(blank=True, verbose_name="Description")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Sort order")

    class Meta:
        ordering = ["company__code", "sort_order", "code"]
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        indexes = [
            models.Index(fields=["company", "parent"], name="org_department_parent_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_department_code_per_company"
            ),
            models.CheckConstraint(
                condition=(
                    Q(scope=DepartmentScope.COMPANY, branch__isnull=True)
                    | Q(scope=DepartmentScope.BRANCH, branch__isnull=False)
                ),
                name="chk_department_scope_branch_consistency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company.code} / {self.code}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()

        errors: dict[str, str] = {}
        if self.scope == DepartmentScope.COMPANY and self.branch_id is not None:
            errors["branch"] = "Company-scoped departments must not have a branch."
        if self.scope == DepartmentScope.BRANCH and self.branch_id is None:
            errors["branch"] = "Branch-scoped departments must have a branch."
        if (
            self.branch_id
            and self.company_id
            and self.branch is not None
            and self.branch.company_id != self.company_id
        ):
            errors["branch"] = "The selected branch does not belong to the selected company."

        if self.parent_id and self.parent is not None:
            if self.pk is not None and self.parent_id == self.pk:
                errors["parent"] = "A department cannot be its own parent."
            elif self.parent.company_id != self.company_id:
                errors["parent"] = "The parent department must belong to the same company."
            elif (
                self.scope == DepartmentScope.COMPANY
                and self.parent.scope == DepartmentScope.BRANCH
            ):
                errors["scope"] = "A child department cannot have a broader scope than its parent."
            elif self.pk is not None:
                node: Department | None = self.parent
                while node is not None:
                    if node.pk == self.pk:
                        errors["parent"] = "This assignment would create a department cycle."
                        break
                    node = node.parent

        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        super().save(*args, **kwargs)
