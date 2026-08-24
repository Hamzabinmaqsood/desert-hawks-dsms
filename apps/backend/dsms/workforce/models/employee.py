from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation
from dsms.workforce.enums import (
    EmployeeType,
    EmploymentStatus,
    EmploymentType,
    Gender,
    MaritalStatus,
)
from dsms.workforce.validators import mask_identity_number, normalize_identity_number

from .base import CODE_VALIDATOR, WorkforceBaseModel, normalize_code


class Employee(WorkforceBaseModel):
    """The authoritative HR/workforce record for a person employed by a company.

    ``Employee`` and :class:`~dsms.identity.models.User` are deliberately
    separate: this is the organizational employment record (who they are,
    where they sit in the company), not an authentication identity. ``user``
    is therefore optional and is only ever linked/unlinked through the
    dedicated ``link_employee_user``/``unlink_employee_user`` services, never
    implicitly. Likewise, ``branch``/``department``/``designation`` here are
    the employee's *home organizational assignment*, not an operational duty
    location -- guard-to-site deployment is a separate future module.
    """

    # -- Identity ----------------------------------------------------------
    employee_number = models.CharField(
        max_length=32,
        verbose_name="Employee number",
        help_text="The official Desert Hawks employee identifier, e.g. DH-000001.",
    )
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee",
        verbose_name="Linked user account",
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="employees",
        verbose_name="Company",
    )
    first_name = models.CharField(max_length=150, verbose_name="First name")
    middle_name = models.CharField(max_length=150, blank=True, verbose_name="Middle name")
    # Optional: many Pakistani CNIC/legal records carry only a single given
    # name plus a father's/husband's name rather than a distinct family
    # surname, so a last name cannot be assumed to always exist.
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Last name")
    preferred_name = models.CharField(max_length=150, blank=True, verbose_name="Preferred name")
    father_or_spouse_name = models.CharField(
        max_length=150, blank=True, verbose_name="Father's/spouse's name"
    )
    gender = models.CharField(
        max_length=20, choices=Gender.choices, default=Gender.UNSPECIFIED, verbose_name="Gender"
    )
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="Date of birth")
    marital_status = models.CharField(
        max_length=20,
        choices=MaritalStatus.choices,
        default=MaritalStatus.UNSPECIFIED,
        verbose_name="Marital status",
    )
    nationality = models.CharField(max_length=2, default="PK", verbose_name="Nationality")
    national_identity_number = models.CharField(
        max_length=32,
        blank=True,
        verbose_name="National identity number",
        help_text="CNIC/passport/national identity reference. Never store document scans here.",
    )
    national_identity_expiry = models.DateField(
        null=True, blank=True, verbose_name="National identity expiry"
    )

    # -- Contact -------------------------------------------------------------
    personal_email = models.EmailField(blank=True, verbose_name="Personal email")
    mobile_number = models.CharField(max_length=20, verbose_name="Mobile number")
    alternate_mobile_number = models.CharField(
        max_length=20, blank=True, verbose_name="Alternate mobile number"
    )

    # -- Employment ------------------------------------------------------------
    employee_type = models.CharField(
        max_length=20, choices=EmployeeType.choices, verbose_name="Employee type"
    )
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, verbose_name="Employment type"
    )
    employment_status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.DRAFT,
        verbose_name="Employment status",
    )
    joining_date = models.DateField(verbose_name="Joining date")
    confirmation_date = models.DateField(null=True, blank=True, verbose_name="Confirmation date")
    probation_end_date = models.DateField(null=True, blank=True, verbose_name="Probation end date")
    exit_date = models.DateField(null=True, blank=True, verbose_name="Exit date")

    # -- Organization (home assignment, not duty deployment) ------------------
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employees",
        verbose_name="Branch",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employees",
        verbose_name="Department",
    )
    designation = models.ForeignKey(
        Designation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employees",
        verbose_name="Designation",
    )

    # -- Other -----------------------------------------------------------------
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        ordering = ["company__code", "employee_number"]
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        indexes = [
            models.Index(fields=["company", "employment_status"], name="wf_emp_company_status_idx"),
            models.Index(fields=["company", "employee_type"], name="wf_emp_company_type_idx"),
            models.Index(fields=["branch"], name="wf_emp_branch_idx"),
            models.Index(fields=["department"], name="wf_emp_department_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "employee_number"], name="uniq_employee_number_per_company"
            ),
            models.UniqueConstraint(
                fields=["company", "national_identity_number"],
                condition=Q(national_identity_number__isnull=False)
                & ~Q(national_identity_number=""),
                name="uniq_identity_num_per_company",
            ),
        ]
        permissions = [
            ("view_sensitive_employee_data", "Can view unmasked national identity numbers"),
            ("manage_employee_status", "Can change an employee's employment status"),
            ("manage_employee_assignment", "Can change an employee's organizational assignment"),
            ("link_employee_user", "Can link or unlink an employee's system access"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_number} - {self.full_name}"

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(part for part in parts if part)

    @property
    def masked_national_identity_number(self) -> str:
        return mask_identity_number(self.national_identity_number)

    def clean(self) -> None:
        super().clean()
        self.employee_number = normalize_code(self.employee_number)
        CODE_VALIDATOR(self.employee_number)
        self.first_name = self.first_name.strip()
        self.middle_name = self.middle_name.strip()
        self.last_name = self.last_name.strip()
        self.preferred_name = self.preferred_name.strip()
        self.father_or_spouse_name = self.father_or_spouse_name.strip()
        self.nationality = self.nationality.strip().upper()
        self.mobile_number = self.mobile_number.strip()
        self.alternate_mobile_number = self.alternate_mobile_number.strip()
        if self.national_identity_number:
            self.national_identity_number = normalize_identity_number(self.national_identity_number)

        errors: dict[str, str] = {}
        if (
            self.branch_id
            and self.company_id
            and self.branch is not None
            and self.branch.company_id != self.company_id
        ):
            errors["branch"] = "The selected branch does not belong to the selected company."
        if self.department_id and self.company_id and self.department is not None:
            if self.department.company_id != self.company_id:
                errors["department"] = (
                    "The selected department does not belong to the selected company."
                )
            elif self.department.branch_id is not None:
                if self.branch_id is None:
                    errors["branch"] = (
                        "A branch-scoped department requires the employee's branch to be set."
                    )
                elif self.department.branch_id != self.branch_id:
                    errors["department"] = "The selected department belongs to a different branch."
        if self.designation_id and self.company_id and self.designation is not None:
            if self.designation.company_id != self.company_id:
                errors["designation"] = (
                    "The selected designation does not belong to the selected company."
                )
            elif (
                self.designation.department_id is not None
                and self.department_id is not None
                and self.designation.department_id != self.department_id
            ):
                errors["designation"] = (
                    "The selected designation belongs to a different department."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.employee_number = normalize_code(self.employee_number)
        self.first_name = self.first_name.strip()
        self.last_name = self.last_name.strip()
        super().save(*args, **kwargs)
