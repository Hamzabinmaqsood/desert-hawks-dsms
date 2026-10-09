from typing import Any

from django.core.validators import RegexValidator
from django.db import models

from .base import CODE_VALIDATOR, OrganizationBaseModel, normalize_code

BRAND_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Enter a color in #RRGGBB format.",
)


class Company(OrganizationBaseModel):
    """A legal business entity that owns an organization hierarchy."""

    code = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Company code",
        help_text="Short uppercase code used to identify the company.",
    )
    legal_name = models.CharField(max_length=255, verbose_name="Legal name")
    trade_name = models.CharField(max_length=255, blank=True, verbose_name="Trade name")
    brand_tagline = models.CharField(max_length=160, blank=True, verbose_name="Brand tagline")
    brand_primary_color = models.CharField(
        max_length=7,
        blank=True,
        validators=[BRAND_COLOR_VALIDATOR],
        verbose_name="Primary brand color",
        help_text="Optional hexadecimal color in #RRGGBB format.",
    )
    brand_accent_color = models.CharField(
        max_length=7,
        blank=True,
        validators=[BRAND_COLOR_VALIDATOR],
        verbose_name="Accent brand color",
        help_text="Optional hexadecimal color in #RRGGBB format.",
    )
    registration_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Registration number",
    )
    tax_number = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True,
        verbose_name="Tax number",
    )
    email = models.EmailField(blank=True, verbose_name="Email")
    phone = models.CharField(max_length=32, blank=True, verbose_name="Phone")
    website = models.URLField(blank=True, verbose_name="Website")
    timezone = models.CharField(max_length=64, default="Asia/Karachi", verbose_name="Timezone")
    default_currency = models.CharField(
        max_length=3, default="PKR", verbose_name="Default currency"
    )
    address_line_1 = models.CharField(max_length=255, blank=True, verbose_name="Address line 1")
    address_line_2 = models.CharField(max_length=255, blank=True, verbose_name="Address line 2")
    city_name = models.CharField(max_length=100, blank=True, verbose_name="City")
    province_name = models.CharField(max_length=100, blank=True, verbose_name="Province")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="Postal code")
    country_code = models.CharField(max_length=2, default="PK", verbose_name="Country code")

    class Meta:
        ordering = ["code"]
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        indexes = [models.Index(fields=["code"], name="org_company_code_idx")]

    def __str__(self) -> str:
        return f"{self.code} - {self.legal_name}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.legal_name = self.legal_name.strip()
        self.trade_name = self.trade_name.strip()
        self.brand_tagline = self.brand_tagline.strip()
        self.brand_primary_color = self.brand_primary_color.strip().upper()
        self.brand_accent_color = self.brand_accent_color.strip().upper()
        self.country_code = self.country_code.strip().upper()
        self.default_currency = self.default_currency.strip().upper()
        if self.registration_number is not None:
            self.registration_number = self.registration_number.strip() or None
        if self.tax_number is not None:
            self.tax_number = self.tax_number.strip() or None

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        super().save(*args, **kwargs)
