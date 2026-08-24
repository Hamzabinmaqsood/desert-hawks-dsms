from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.organization.models import Branch, Company, Department, OperationalZone, Region

from ..enums import AccessScopeType
from .base import IdentityBaseModel
from .role import Role

_SCOPE_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    AccessScopeType.GLOBAL: frozenset(),
    AccessScopeType.COMPANY: frozenset({"company"}),
    AccessScopeType.REGION: frozenset({"company", "region"}),
    AccessScopeType.BRANCH: frozenset({"company", "branch"}),
    AccessScopeType.DEPARTMENT: frozenset({"company", "department"}),
    AccessScopeType.OPERATIONAL_ZONE: frozenset({"company", "operational_zone"}),
}
_SCOPE_FIELDS = ("company", "region", "branch", "department", "operational_zone")


def _scope_consistency_condition() -> Q:
    condition = Q()
    for scope_type, required in _SCOPE_REQUIRED_FIELDS.items():
        clause = Q(scope_type=scope_type)
        for field in _SCOPE_FIELDS:
            clause &= Q(**{f"{field}__isnull": field not in required})
        condition |= clause
    return condition


class UserRoleAssignment(IdentityBaseModel):
    """Grants a user a role's permissions within a specific organizational scope."""

    user = models.ForeignKey(
        "identity.User",
        on_delete=models.CASCADE,
        related_name="role_assignments",
        verbose_name="User",
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name="Role",
    )
    scope_type = models.CharField(
        max_length=20, choices=AccessScopeType.choices, verbose_name="Scope type"
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_assignments",
        verbose_name="Company",
    )
    region = models.ForeignKey(
        Region,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_assignments",
        verbose_name="Region",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_assignments",
        verbose_name="Branch",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_assignments",
        verbose_name="Department",
    )
    operational_zone = models.ForeignKey(
        OperationalZone,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_assignments",
        verbose_name="Operational zone",
    )
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="Starts at")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="Ends at")
    created_by = models.ForeignKey(
        "identity.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_role_assignments",
        verbose_name="Created by",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User role assignment"
        verbose_name_plural = "User role assignments"
        indexes = [
            models.Index(fields=["user", "is_active"], name="ura_user_active_idx"),
            models.Index(fields=["company", "scope_type"], name="ura_company_scope_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=_scope_consistency_condition(),
                name="chk_role_assignment_scope_consistency",
            ),
            models.CheckConstraint(
                condition=(
                    Q(starts_at__isnull=True)
                    | Q(ends_at__isnull=True)
                    | Q(starts_at__lt=models.F("ends_at"))
                ),
                name="chk_role_assignment_starts_before_ends",
            ),
        ]
        permissions = [
            ("assign_roles", "Can create, modify, activate, and deactivate role assignments"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} / {self.role_id} / {self.scope_type}"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        required = _SCOPE_REQUIRED_FIELDS.get(self.scope_type, frozenset())
        for field in _SCOPE_FIELDS:
            value = getattr(self, f"{field}_id")
            if field in required and value is None:
                errors[field] = f"{field} is required for {self.scope_type} scope."
            elif field not in required and value is not None:
                errors[field] = f"{field} must be empty for {self.scope_type} scope."

        if not errors:
            if (
                self.region_id
                and self.region is not None
                and self.region.company_id != self.company_id
            ):
                errors["region"] = "The selected region does not belong to the selected company."
            if (
                self.branch_id
                and self.branch is not None
                and self.branch.company_id != self.company_id
            ):
                errors["branch"] = "The selected branch does not belong to the selected company."
            if (
                self.department_id
                and self.department is not None
                and self.department.company_id != self.company_id
            ):
                errors["department"] = (
                    "The selected department does not belong to the selected company."
                )
            if (
                self.operational_zone_id
                and self.operational_zone is not None
                and self.operational_zone.company_id != self.company_id
            ):
                errors["operational_zone"] = (
                    "The selected operational zone does not belong to the selected company."
                )

        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            errors["ends_at"] = "ends_at must be after starts_at."

        if (
            self.role_id
            and self.role.company_id is not None
            and self.role.company_id != self.company_id
        ):
            errors["role"] = "The role's company must match the assignment's company."

        if errors:
            raise ValidationError(errors)
