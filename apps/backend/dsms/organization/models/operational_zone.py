from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from .base import CODE_VALIDATOR, OrganizationBaseModel, normalize_code
from .branch import Branch
from .company import Company


class OperationalZone(OrganizationBaseModel):
    """A patrol/coverage zone within a branch's area of responsibility."""

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="operational_zones",
        verbose_name="Company",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="operational_zones",
        verbose_name="Branch",
    )
    code = models.CharField(max_length=20, verbose_name="Zone code")
    name = models.CharField(max_length=150, verbose_name="Zone name")
    description = models.TextField(blank=True, verbose_name="Description")

    class Meta:
        ordering = ["branch__code", "code"]
        verbose_name = "Operational zone"
        verbose_name_plural = "Operational zones"
        indexes = [
            models.Index(fields=["branch", "is_active"], name="org_zone_branch_active_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["branch", "code"], name="uniq_zone_code_per_branch"),
            models.UniqueConstraint(fields=["branch", "name"], name="uniq_zone_name_per_branch"),
        ]

    def __str__(self) -> str:
        return f"{self.branch.code} / {self.code}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()

        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            raise ValidationError(
                {"branch": "The selected branch does not belong to the selected company."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        super().save(*args, **kwargs)
