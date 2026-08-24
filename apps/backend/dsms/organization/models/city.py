from typing import Any

from django.core.exceptions import ValidationError
from django.db import models

from .base import CODE_VALIDATOR, OrganizationBaseModel, normalize_code
from .company import Company
from .region import Region


class City(OrganizationBaseModel):
    """A city that branches can be located in, grouped under a region."""

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="cities",
        verbose_name="Company",
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="cities",
        verbose_name="Region",
    )
    code = models.CharField(max_length=20, verbose_name="City code")
    name = models.CharField(max_length=150, verbose_name="City name")
    province_or_state = models.CharField(max_length=150, verbose_name="Province or state")
    country_code = models.CharField(max_length=2, default="PK", verbose_name="Country code")
    timezone = models.CharField(max_length=64, default="Asia/Karachi", verbose_name="Timezone")

    class Meta:
        ordering = ["company__code", "code"]
        verbose_name = "City"
        verbose_name_plural = "Cities"
        indexes = [
            models.Index(fields=["company", "region"], name="org_city_company_region_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_city_code_per_company"),
            models.UniqueConstraint(
                fields=["company", "name", "province_or_state"],
                name="uniq_city_name_province_per_company",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company.code} / {self.code}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()
        self.province_or_state = self.province_or_state.strip()
        self.country_code = self.country_code.strip().upper()
        if self.region_id and self.company_id and self.region.company_id != self.company_id:
            raise ValidationError(
                {"region": "The selected region does not belong to the selected company."}
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        self.province_or_state = self.province_or_state.strip()
        super().save(*args, **kwargs)
