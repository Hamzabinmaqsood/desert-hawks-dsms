from typing import Any

from django.db import models
from django.db.models import Q

from dsms.workforce.enums import AddressType

from .base import TimeStampedModel, UUIDModel
from .employee import Employee


class EmployeeAddress(UUIDModel, TimeStampedModel):
    """A postal address associated with an employee (current, permanent, or other)."""

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name="Employee",
    )
    address_type = models.CharField(
        max_length=10, choices=AddressType.choices, verbose_name="Address type"
    )
    address_line_1 = models.CharField(max_length=255, verbose_name="Address line 1")
    address_line_2 = models.CharField(max_length=255, blank=True, verbose_name="Address line 2")
    city = models.CharField(max_length=100, verbose_name="City")
    province_or_state = models.CharField(max_length=100, blank=True, verbose_name="Province/state")
    postal_code = models.CharField(max_length=20, blank=True, verbose_name="Postal code")
    country_code = models.CharField(max_length=2, default="PK", verbose_name="Country code")
    is_primary = models.BooleanField(default=False, verbose_name="Is primary")

    class Meta:
        ordering = ["employee", "address_type"]
        verbose_name = "Employee address"
        verbose_name_plural = "Employee addresses"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "address_type"],
                condition=Q(is_primary=True),
                name="uniq_primary_address_per_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_number} / {self.address_type}"

    def clean(self) -> None:
        super().clean()
        self.address_line_1 = self.address_line_1.strip()
        self.address_line_2 = self.address_line_2.strip()
        self.city = self.city.strip()
        self.province_or_state = self.province_or_state.strip()
        self.postal_code = self.postal_code.strip()
        self.country_code = self.country_code.strip().upper()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.country_code = self.country_code.strip().upper()
        super().save(*args, **kwargs)
