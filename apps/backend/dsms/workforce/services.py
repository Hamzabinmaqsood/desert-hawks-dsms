"""Business transactions for the workforce/employee-master module.

Services own create/update/lifecycle workflows: they enforce cross-entity
business rules and translate model/database failures into the domain
exceptions defined in :mod:`dsms.workforce.exceptions`. Status and
organizational-assignment changes always write their corresponding history
row atomically with the ``Employee`` update -- never via signals -- so the
history models stay a complete, trustworthy audit trail.
"""

from datetime import date
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction

from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation
from dsms.subscriptions.enforcement import requires_company_module

from .enums import EmploymentStatus, Gender, MaritalStatus
from .exceptions import (
    HierarchyMismatchError,
    InactiveRelatedRecordError,
    InvalidStatusTransitionError,
    UserAlreadyLinkedError,
    WorkforceValidationError,
)
from .models import (
    EmergencyContact,
    Employee,
    EmployeeAddress,
    EmployeeAssignmentHistory,
    EmployeeStatusHistory,
)

_ERROR_TYPE_MARKERS: list[tuple[str, type[Exception]]] = [
    ("does not belong to the selected", HierarchyMismatchError),
    ("requires the employee's branch", HierarchyMismatchError),
    ("belongs to a different branch", HierarchyMismatchError),
    ("belongs to a different department", HierarchyMismatchError),
]


def _save(instance: models.Model) -> None:
    try:
        instance.full_clean()
        instance.save()
    except DjangoValidationError as exc:
        errors = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        flat_messages = " ".join(message for messages in errors.values() for message in messages)
        for marker, exc_class in _ERROR_TYPE_MARKERS:
            if marker in flat_messages:
                raise exc_class(flat_messages) from exc
        raise WorkforceValidationError(errors) from exc
    except IntegrityError as exc:
        raise WorkforceValidationError(str(exc)) from exc


def _apply_fields(instance: models.Model, fields: dict[str, Any]) -> None:
    for name, value in fields.items():
        setattr(instance, name, value)


def _validate_org_consistency(
    *,
    company: Company,
    branch: Branch | None,
    department: Department | None,
    designation: Designation | None,
) -> None:
    if branch is not None:
        if not branch.is_active:
            raise InactiveRelatedRecordError("Cannot assign an inactive branch.")
        if branch.company_id != company.id:
            raise HierarchyMismatchError(
                "The selected branch does not belong to the selected company."
            )
    if department is not None:
        if not department.is_active:
            raise InactiveRelatedRecordError("Cannot assign an inactive department.")
        if department.company_id != company.id:
            raise HierarchyMismatchError(
                "The selected department does not belong to the selected company."
            )
        if department.branch_id is not None:
            if branch is None:
                raise HierarchyMismatchError(
                    "A branch-scoped department requires the employee's branch to be set."
                )
            if department.branch_id != branch.id:
                raise HierarchyMismatchError(
                    "The selected department belongs to a different branch."
                )
    if designation is not None:
        if not designation.is_active:
            raise InactiveRelatedRecordError("Cannot assign an inactive designation.")
        if designation.company_id != company.id:
            raise HierarchyMismatchError(
                "The selected designation does not belong to the selected company."
            )
        if (
            designation.department_id is not None
            and department is not None
            and designation.department_id != department.id
        ):
            raise HierarchyMismatchError(
                "The selected designation belongs to a different department."
            )


# --------------------------------------------------------------------------
# Employee
# --------------------------------------------------------------------------


@requires_company_module("people", argument="company")
def create_employee(
    *,
    actor: User,
    company: Company,
    employee_number: str,
    first_name: str,
    mobile_number: str,
    employee_type: str,
    employment_type: str,
    joining_date: date,
    last_name: str = "",
    middle_name: str = "",
    preferred_name: str = "",
    father_or_spouse_name: str = "",
    gender: str = Gender.UNSPECIFIED,
    date_of_birth: date | None = None,
    marital_status: str = MaritalStatus.UNSPECIFIED,
    nationality: str = "PK",
    national_identity_number: str = "",
    national_identity_expiry: date | None = None,
    personal_email: str = "",
    alternate_mobile_number: str = "",
    confirmation_date: date | None = None,
    probation_end_date: date | None = None,
    branch: Branch | None = None,
    department: Department | None = None,
    designation: Designation | None = None,
    notes: str = "",
) -> Employee:
    if not company.is_active:
        raise InactiveRelatedRecordError("Cannot create an employee under an inactive company.")
    _validate_org_consistency(
        company=company, branch=branch, department=department, designation=designation
    )
    with transaction.atomic():
        employee = Employee(
            company=company,
            employee_number=employee_number,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            preferred_name=preferred_name,
            father_or_spouse_name=father_or_spouse_name,
            gender=gender,
            date_of_birth=date_of_birth,
            marital_status=marital_status,
            nationality=nationality,
            national_identity_number=national_identity_number,
            national_identity_expiry=national_identity_expiry,
            personal_email=personal_email,
            mobile_number=mobile_number,
            alternate_mobile_number=alternate_mobile_number,
            employee_type=employee_type,
            employment_type=employment_type,
            employment_status=EmploymentStatus.DRAFT,
            joining_date=joining_date,
            confirmation_date=confirmation_date,
            probation_end_date=probation_end_date,
            branch=branch,
            department=department,
            designation=designation,
            notes=notes,
        )
        _save(employee)
        EmployeeAssignmentHistory.objects.create(
            employee=employee,
            company=company,
            branch=branch,
            department=department,
            designation=designation,
            effective_from=joining_date,
            reason="Initial assignment",
            changed_by=actor,
        )
    return employee


@requires_company_module("people", argument="employee")
def update_employee_personal_details(*, employee: Employee, **fields: Any) -> Employee:
    with transaction.atomic():
        _apply_fields(employee, fields)
        _save(employee)
    return employee


@requires_company_module("people", argument="employee")
def update_employee_contact_details(*, employee: Employee, **fields: Any) -> Employee:
    with transaction.atomic():
        _apply_fields(employee, fields)
        _save(employee)
    return employee


@requires_company_module("people", argument="employee")
def change_employee_organization(
    *,
    employee: Employee,
    actor: User,
    effective_from: date,
    branch: Branch | None = None,
    department: Department | None = None,
    designation: Designation | None = None,
    reason: str = "",
) -> Employee:
    _validate_org_consistency(
        company=employee.company, branch=branch, department=department, designation=designation
    )
    with transaction.atomic():
        EmployeeAssignmentHistory.objects.filter(
            employee=employee, effective_to__isnull=True
        ).update(effective_to=effective_from)
        EmployeeAssignmentHistory.objects.create(
            employee=employee,
            company=employee.company,
            branch=branch,
            department=department,
            designation=designation,
            effective_from=effective_from,
            reason=reason,
            changed_by=actor,
        )
        employee.branch = branch
        employee.department = department
        employee.designation = designation
        _save(employee)
    return employee


# --------------------------------------------------------------------------
# Employment status lifecycle
# --------------------------------------------------------------------------

_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    EmploymentStatus.DRAFT: frozenset({EmploymentStatus.ACTIVE}),
    EmploymentStatus.ACTIVE: frozenset(
        {
            EmploymentStatus.ON_LEAVE,
            EmploymentStatus.SUSPENDED,
            EmploymentStatus.RESIGNED,
            EmploymentStatus.TERMINATED,
            EmploymentStatus.RETIRED,
            EmploymentStatus.ABSCONDED,
        }
    ),
    EmploymentStatus.ON_LEAVE: frozenset(
        {EmploymentStatus.ACTIVE, EmploymentStatus.RESIGNED, EmploymentStatus.TERMINATED}
    ),
    EmploymentStatus.SUSPENDED: frozenset(
        {EmploymentStatus.ACTIVE, EmploymentStatus.TERMINATED, EmploymentStatus.RESIGNED}
    ),
}
_TERMINAL_STATUSES = frozenset(
    {
        EmploymentStatus.RESIGNED,
        EmploymentStatus.TERMINATED,
        EmploymentStatus.RETIRED,
        EmploymentStatus.ABSCONDED,
    }
)


def _change_employee_status(
    *,
    employee: Employee,
    new_status: str,
    effective_date: date,
    changed_by: User,
    reason: str = "",
    exit_date: date | None = None,
    allowed_from: frozenset[str],
) -> Employee:
    current_status = employee.employment_status
    if current_status not in allowed_from or new_status not in _STATUS_TRANSITIONS.get(
        current_status, frozenset()
    ):
        raise InvalidStatusTransitionError(
            f"Cannot transition an employee from {current_status} to {new_status}."
        )
    if new_status == EmploymentStatus.ACTIVE:
        if employee.joining_date is None:
            raise WorkforceValidationError(
                {"joining_date": ["joining_date is required to activate an employee."]}
            )
        employee.is_active = True
    if new_status in _TERMINAL_STATUSES:
        if exit_date is None:
            raise WorkforceValidationError(
                {"exit_date": ["exit_date is required for this status change."]}
            )
        if exit_date < employee.joining_date or exit_date < effective_date:
            raise WorkforceValidationError(
                {
                    "exit_date": [
                        "exit_date cannot be before joining_date or the status effective_date."
                    ]
                }
            )
        employee.exit_date = exit_date
        employee.is_active = False
    employee.employment_status = new_status
    with transaction.atomic():
        _save(employee)
        EmployeeStatusHistory.objects.create(
            employee=employee,
            previous_status=current_status,
            new_status=new_status,
            effective_date=effective_date,
            reason=reason,
            changed_by=changed_by,
        )
    return employee


@requires_company_module("people", argument="employee")
def activate_employee(
    *, employee: Employee, effective_date: date, changed_by: User, reason: str = ""
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.ACTIVE,
        effective_date=effective_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=frozenset({EmploymentStatus.DRAFT}),
    )


@requires_company_module("people", argument="employee")
def place_employee_on_leave(
    *, employee: Employee, effective_date: date, changed_by: User, reason: str = ""
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.ON_LEAVE,
        effective_date=effective_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=frozenset({EmploymentStatus.ACTIVE}),
    )


@requires_company_module("people", argument="employee")
def return_employee_from_leave(
    *, employee: Employee, effective_date: date, changed_by: User, reason: str = ""
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.ACTIVE,
        effective_date=effective_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=frozenset({EmploymentStatus.ON_LEAVE}),
    )


@requires_company_module("people", argument="employee")
def suspend_employee(
    *, employee: Employee, effective_date: date, changed_by: User, reason: str = ""
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.SUSPENDED,
        effective_date=effective_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=frozenset({EmploymentStatus.ACTIVE}),
    )


@requires_company_module("people", argument="employee")
def reinstate_employee(
    *, employee: Employee, effective_date: date, changed_by: User, reason: str = ""
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.ACTIVE,
        effective_date=effective_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=frozenset({EmploymentStatus.SUSPENDED}),
    )


_TERMINAL_SOURCE_STATUSES = frozenset(
    {EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE, EmploymentStatus.SUSPENDED}
)


@requires_company_module("people", argument="employee")
def resign_employee(
    *,
    employee: Employee,
    effective_date: date,
    exit_date: date,
    changed_by: User,
    reason: str = "",
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.RESIGNED,
        effective_date=effective_date,
        exit_date=exit_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=_TERMINAL_SOURCE_STATUSES,
    )


@requires_company_module("people", argument="employee")
def terminate_employee(
    *,
    employee: Employee,
    effective_date: date,
    exit_date: date,
    changed_by: User,
    reason: str = "",
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.TERMINATED,
        effective_date=effective_date,
        exit_date=exit_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=_TERMINAL_SOURCE_STATUSES,
    )


@requires_company_module("people", argument="employee")
def retire_employee(
    *,
    employee: Employee,
    effective_date: date,
    exit_date: date,
    changed_by: User,
    reason: str = "",
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.RETIRED,
        effective_date=effective_date,
        exit_date=exit_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=frozenset({EmploymentStatus.ACTIVE}),
    )


@requires_company_module("people", argument="employee")
def mark_employee_absconded(
    *,
    employee: Employee,
    effective_date: date,
    exit_date: date,
    changed_by: User,
    reason: str = "",
) -> Employee:
    return _change_employee_status(
        employee=employee,
        new_status=EmploymentStatus.ABSCONDED,
        effective_date=effective_date,
        exit_date=exit_date,
        changed_by=changed_by,
        reason=reason,
        allowed_from=frozenset({EmploymentStatus.ACTIVE}),
    )


# --------------------------------------------------------------------------
# User access linking
# --------------------------------------------------------------------------


@requires_company_module("people", argument="employee")
def link_employee_user(*, employee: Employee, user: User) -> Employee:
    if not user.is_active:
        raise InactiveRelatedRecordError("Cannot link an inactive user account.")
    if Employee.objects.filter(user=user).exclude(pk=employee.pk).exists():
        raise UserAlreadyLinkedError("This user is already linked to another employee.")
    if employee.user_id is not None:
        raise UserAlreadyLinkedError(
            "This employee already has a linked user account; unlink it first."
        )
    with transaction.atomic():
        employee.user = user
        _save(employee)
    return employee


@requires_company_module("people", argument="employee")
def unlink_employee_user(*, employee: Employee) -> Employee:
    with transaction.atomic():
        employee.user = None
        _save(employee)
    return employee


# --------------------------------------------------------------------------
# Addresses
# --------------------------------------------------------------------------


@requires_company_module("people", argument="employee")
def add_employee_address(
    *,
    employee: Employee,
    address_type: str,
    address_line_1: str,
    city: str,
    address_line_2: str = "",
    province_or_state: str = "",
    postal_code: str = "",
    country_code: str = "PK",
    is_primary: bool = False,
) -> EmployeeAddress:
    with transaction.atomic():
        if is_primary:
            EmployeeAddress.objects.filter(
                employee=employee, address_type=address_type, is_primary=True
            ).update(is_primary=False)
        address = EmployeeAddress(
            employee=employee,
            address_type=address_type,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city=city,
            province_or_state=province_or_state,
            postal_code=postal_code,
            country_code=country_code,
            is_primary=is_primary,
        )
        _save(address)
    return address


@requires_company_module("people", argument="address")
def update_employee_address(*, address: EmployeeAddress, **fields: Any) -> EmployeeAddress:
    with transaction.atomic():
        if fields.get("is_primary") is True:
            address_type = fields.get("address_type", address.address_type)
            EmployeeAddress.objects.filter(
                employee=address.employee, address_type=address_type, is_primary=True
            ).exclude(pk=address.pk).update(is_primary=False)
        _apply_fields(address, fields)
        _save(address)
    return address


@requires_company_module("people", argument="address")
def set_primary_employee_address(*, address: EmployeeAddress) -> EmployeeAddress:
    return update_employee_address(address=address, is_primary=True)


@requires_company_module("people", argument="address")
def remove_employee_address(*, address: EmployeeAddress) -> None:
    address.delete()


# --------------------------------------------------------------------------
# Emergency contacts
# --------------------------------------------------------------------------


@requires_company_module("people", argument="employee")
def add_emergency_contact(
    *,
    employee: Employee,
    name: str,
    relationship: str,
    mobile_number: str,
    alternate_mobile_number: str = "",
    address: str = "",
    is_primary: bool = False,
) -> EmergencyContact:
    with transaction.atomic():
        if is_primary:
            EmergencyContact.objects.filter(employee=employee, is_primary=True).update(
                is_primary=False
            )
        contact = EmergencyContact(
            employee=employee,
            name=name,
            relationship=relationship,
            mobile_number=mobile_number,
            alternate_mobile_number=alternate_mobile_number,
            address=address,
            is_primary=is_primary,
        )
        _save(contact)
    return contact


@requires_company_module("people", argument="contact")
def update_emergency_contact(*, contact: EmergencyContact, **fields: Any) -> EmergencyContact:
    with transaction.atomic():
        if fields.get("is_primary") is True:
            EmergencyContact.objects.filter(employee=contact.employee, is_primary=True).exclude(
                pk=contact.pk
            ).update(is_primary=False)
        _apply_fields(contact, fields)
        _save(contact)
    return contact


@requires_company_module("people", argument="contact")
def set_primary_emergency_contact(*, contact: EmergencyContact) -> EmergencyContact:
    return update_emergency_contact(contact=contact, is_primary=True)


@requires_company_module("people", argument="contact")
def remove_emergency_contact(*, contact: EmergencyContact) -> None:
    contact.delete()
