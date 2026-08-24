from typing import Any

from django.contrib.auth.models import Permission
from django.db import models
from django.db.models import Q

from dsms.organization.models import Company

from .base import CODE_VALIDATOR, IdentityBaseModel, normalize_code


class Role(IdentityBaseModel):
    """A named bundle of Django permissions grantable to users via scoped assignments.

    ``company`` is null for system/platform role templates and populated for
    company-specific custom roles. Roles never carry organizational meaning
    themselves (see :class:`~dsms.organization.models.Designation`) -- they
    exist purely to describe application security access.
    """

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="custom_roles",
        verbose_name="Company",
    )
    code = models.CharField(max_length=50, verbose_name="Role code")
    name = models.CharField(max_length=150, verbose_name="Role name")
    description = models.TextField(blank=True, verbose_name="Description")
    is_system = models.BooleanField(default=False, verbose_name="Is system role")
    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="dsms_roles",
        verbose_name="Permissions",
    )

    class Meta:
        ordering = ["company__code", "code"]
        verbose_name = "Role"
        verbose_name_plural = "Roles"
        indexes = [
            models.Index(fields=["company", "is_active"], name="identity_role_company_act_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_role_code_per_company"),
            models.UniqueConstraint(
                fields=["code"], condition=Q(company__isnull=True), name="uniq_system_role_code"
            ),
        ]
        permissions = [
            ("manage_roles", "Can create, modify, activate, and deactivate roles"),
            ("view_access_matrix", "Can view the role/permission access matrix"),
        ]

    def __str__(self) -> str:
        scope = self.company.code if self.company is not None else "SYSTEM"
        return f"{scope} / {self.code}"

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        super().save(*args, **kwargs)
