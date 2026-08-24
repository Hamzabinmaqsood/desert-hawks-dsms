from typing import Any

from django.db import models
from django.db.models.functions import Lower

from .base import CODE_VALIDATOR, OrganizationBaseModel, normalize_code
from .company import Company


class Region(OrganizationBaseModel):
    """A geographic grouping of cities and branches within a company."""

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="regions",
        verbose_name="Company",
    )
    code = models.CharField(max_length=20, verbose_name="Region code")
    name = models.CharField(max_length=150, verbose_name="Region name")
    description = models.TextField(blank=True, verbose_name="Description")

    class Meta:
        ordering = ["company__code", "code"]
        verbose_name = "Region"
        verbose_name_plural = "Regions"
        indexes = [models.Index(fields=["company", "is_active"], name="org_region_company_act_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_region_code_per_company"
            ),
            models.UniqueConstraint(
                Lower("name"), "company", name="uniq_region_name_per_company_ci"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company.code} / {self.code}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        super().save(*args, **kwargs)
