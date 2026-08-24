from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .base import CODE_VALIDATOR, OrganizationBaseModel, normalize_code
from .city import City
from .company import Company
from .region import Region


class Branch(OrganizationBaseModel):
    """A physical operating location of a company within a city."""

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="branches",
        verbose_name="Company",
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        related_name="branches",
        verbose_name="Region",
    )
    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name="branches",
        verbose_name="City",
    )
    code = models.CharField(max_length=20, verbose_name="Branch code")
    name = models.CharField(max_length=150, verbose_name="Branch name")
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=32, blank=True, verbose_name="Phone")
    address_line_1 = models.CharField(max_length=255, verbose_name="Address line 1")
    address_line_2 = models.CharField(max_length=255, blank=True, verbose_name="Address line 2")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="Postal code")
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="Latitude"
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True, verbose_name="Longitude"
    )
    is_head_office = models.BooleanField(default=False, verbose_name="Is head office")

    class Meta:
        ordering = ["company__code", "code"]
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        indexes = [
            models.Index(fields=["company", "region", "city"], name="org_branch_hierarchy_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_branch_code_per_company"
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(is_head_office=True, is_active=True),
                name="uniq_active_head_office_per_company",
            ),
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
                name="chk_branch_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
                name="chk_branch_longitude_range",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company.code} / {self.code}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()
        self.address_line_1 = self.address_line_1.strip()
        self.address_line_2 = self.address_line_2.strip()

        errors: dict[str, str] = {}
        if self.region_id and self.company_id and self.region.company_id != self.company_id:
            errors["region"] = "The selected region does not belong to the selected company."
        if self.city_id and self.company_id and self.city.company_id != self.company_id:
            errors["city"] = "The selected city does not belong to the selected company."
        if self.city_id and self.region_id and self.city.region_id != self.region_id:
            errors["city"] = "The selected city does not belong to the selected region."
        if self.latitude is not None and not (-90 <= self.latitude <= 90):
            errors["latitude"] = "Latitude must be between -90 and 90."
        if self.longitude is not None and not (-180 <= self.longitude <= 180):
            errors["longitude"] = "Longitude must be between -180 and 180."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        super().save(*args, **kwargs)
