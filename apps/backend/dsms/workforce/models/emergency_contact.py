from typing import Any

from django.db import models
from django.db.models import Q

from .base import TimeStampedModel, UUIDModel
from .employee import Employee


class EmergencyContact(UUIDModel, TimeStampedModel):
    """A person to contact in case of an emergency involving the employee."""

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="emergency_contacts",
        verbose_name="Employee",
    )
    name = models.CharField(max_length=150, verbose_name="Name")
    relationship = models.CharField(max_length=100, verbose_name="Relationship")
    mobile_number = models.CharField(max_length=20, verbose_name="Mobile number")
    alternate_mobile_number = models.CharField(
        max_length=20, blank=True, verbose_name="Alternate mobile number"
    )
    address = models.CharField(max_length=255, blank=True, verbose_name="Address")
    is_primary = models.BooleanField(default=False, verbose_name="Is primary")

    class Meta:
        ordering = ["employee", "-is_primary"]
        verbose_name = "Emergency contact"
        verbose_name_plural = "Emergency contacts"
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(is_primary=True),
                name="uniq_primary_emerg_contact",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_number} / {self.name}"

    def clean(self) -> None:
        super().clean()
        self.name = self.name.strip()
        self.relationship = self.relationship.strip()
        self.mobile_number = self.mobile_number.strip()
        self.alternate_mobile_number = self.alternate_mobile_number.strip()
        self.address = self.address.strip()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.name = self.name.strip()
        super().save(*args, **kwargs)
