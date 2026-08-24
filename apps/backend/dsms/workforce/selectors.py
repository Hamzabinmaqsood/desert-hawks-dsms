"""Read-side queries for the workforce module.

Selectors return querysets and are responsible for avoiding N+1 queries via
``select_related``/``prefetch_related``. RBAC-aware querysets
(``get_accessible_employees``) additionally filter to the caller's
organizational access scope -- callers must use these (not the plain
``get_employees``) for anything reachable by a non-superuser.
"""

from typing import TYPE_CHECKING
from uuid import UUID

from django.db.models import Q, QuerySet

from dsms.identity import access as identity_access
from dsms.identity.enums import AccessScopeType
from dsms.workforce.enums import EmployeeType

from .models import (
    EmergencyContact,
    Employee,
    EmployeeAddress,
    EmployeeAssignmentHistory,
    EmployeeStatusHistory,
)

if TYPE_CHECKING:
    from dsms.identity.models import User

_SELECT_RELATED = ("company", "branch", "department", "designation", "user")


def get_employees() -> QuerySet[Employee]:
    return Employee.objects.select_related(*_SELECT_RELATED)


def get_employee(*, employee_id: UUID) -> Employee:
    return get_employees().get(pk=employee_id)


def employees_by_company(*, company_id: UUID) -> QuerySet[Employee]:
    return get_employees().filter(company_id=company_id)


def employees_by_branch(*, branch_id: UUID) -> QuerySet[Employee]:
    return get_employees().filter(branch_id=branch_id)


def employees_by_department(*, department_id: UUID) -> QuerySet[Employee]:
    return get_employees().filter(department_id=department_id)


def employees_by_designation(*, designation_id: UUID) -> QuerySet[Employee]:
    return get_employees().filter(designation_id=designation_id)


def employees_by_type(*, employee_type: str) -> QuerySet[Employee]:
    return get_employees().filter(employee_type=employee_type)


def employees_by_status(*, employment_status: str) -> QuerySet[Employee]:
    return get_employees().filter(employment_status=employment_status)


def active_employees() -> QuerySet[Employee]:
    return get_employees().filter(is_active=True)


def guards() -> QuerySet[Employee]:
    return get_employees().filter(employee_type=EmployeeType.SECURITY_GUARD)


def supervisors() -> QuerySet[Employee]:
    return get_employees().filter(employee_type=EmployeeType.SUPERVISOR)


def employee_status_history(*, employee: Employee) -> QuerySet[EmployeeStatusHistory]:
    return employee.status_history.select_related("changed_by").order_by("-created_at")


def employee_assignment_history(*, employee: Employee) -> QuerySet[EmployeeAssignmentHistory]:
    return employee.assignment_history.select_related(
        "company", "branch", "department", "designation", "changed_by"
    ).order_by("-created_at")


def employee_addresses(*, employee: Employee) -> QuerySet[EmployeeAddress]:
    return employee.addresses.order_by("address_type", "-is_primary")


def employee_emergency_contacts(*, employee: Employee) -> QuerySet[EmergencyContact]:
    return employee.emergency_contacts.order_by("-is_primary", "name")


def get_accessible_employees(
    user: "User | None", *, permission: str | None = None
) -> QuerySet[Employee]:
    """Employees visible to ``user`` at their granted RBAC scope.

    Employee master data is organizational (company/region/branch/
    department), not deployment-based, so OPERATIONAL_ZONE-scoped
    assignments never grant employee visibility.
    """
    if user is not None and getattr(user, "is_superuser", False):
        return get_employees()
    if not (user is not None and user.is_authenticated and user.is_active):
        return Employee.objects.none()

    company_ids: set[UUID] = set()
    region_ids: set[UUID] = set()
    branch_ids: set[UUID] = set()
    department_ids: set[UUID] = set()
    for assignment in identity_access.get_active_role_assignments(user):
        if permission is not None:
            codes = {
                f"{perm.content_type.app_label}.{perm.codename}"
                for perm in assignment.role.permissions.all()
            }
            if permission not in codes:
                continue
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return get_employees()
        if assignment.scope_type == AccessScopeType.COMPANY and assignment.company_id:
            company_ids.add(assignment.company_id)
        elif assignment.scope_type == AccessScopeType.REGION and assignment.region_id:
            region_ids.add(assignment.region_id)
        elif assignment.scope_type == AccessScopeType.BRANCH and assignment.branch_id:
            branch_ids.add(assignment.branch_id)
        elif assignment.scope_type == AccessScopeType.DEPARTMENT and assignment.department_id:
            department_ids.add(assignment.department_id)

    condition = Q(pk__in=[])
    if company_ids:
        condition |= Q(company_id__in=company_ids)
    if region_ids:
        condition |= Q(branch__region_id__in=region_ids)
    if branch_ids:
        condition |= Q(branch_id__in=branch_ids)
    if department_ids:
        condition |= Q(department_id__in=department_ids)
    return get_employees().filter(condition)
