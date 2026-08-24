"""Business transactions for the organization module.

Services own create/update/activate/deactivate workflows: they enforce
cross-entity business rules and translate model/database failures into the
domain exceptions defined in :mod:`dsms.organization.exceptions`.
"""

from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction

from .enums import DepartmentScope
from .exceptions import (
    ActiveChildrenExistError,
    DuplicateHeadOfficeError,
    HierarchyCycleError,
    HierarchyMismatchError,
    InactiveRelatedRecordError,
    OrganizationError,
    OrganizationValidationError,
    ScopeViolationError,
)
from .models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
    Region,
)

_ERROR_TYPE_MARKERS: list[tuple[str, type[OrganizationError]]] = [
    ("cycle", HierarchyCycleError),
    ("broader scope", ScopeViolationError),
    ("does not belong to the selected", HierarchyMismatchError),
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
        raise OrganizationValidationError(errors) from exc
    except IntegrityError as exc:
        raise OrganizationValidationError(str(exc)) from exc


def _apply_fields(instance: models.Model, fields: dict[str, Any]) -> None:
    for name, value in fields.items():
        setattr(instance, name, value)


def _guard_single_head_office(*, company: Company, exclude_pk: Any = None) -> None:
    queryset = Branch.objects.filter(company=company, is_head_office=True, is_active=True)
    if exclude_pk is not None:
        queryset = queryset.exclude(pk=exclude_pk)
    if queryset.exists():
        raise DuplicateHeadOfficeError("An active head office already exists for this company.")


# --------------------------------------------------------------------------
# Company
# --------------------------------------------------------------------------


def create_company(
    *,
    code: str,
    legal_name: str,
    trade_name: str = "",
    registration_number: str | None = None,
    tax_number: str | None = None,
    email: str = "",
    phone: str = "",
    website: str = "",
    timezone: str = "Asia/Karachi",
    default_currency: str = "PKR",
    address_line_1: str = "",
    address_line_2: str = "",
    city_name: str = "",
    province_name: str = "",
    postal_code: str = "",
    country_code: str = "PK",
    is_active: bool = True,
) -> Company:
    with transaction.atomic():
        company = Company(
            code=code,
            legal_name=legal_name,
            trade_name=trade_name,
            registration_number=registration_number,
            tax_number=tax_number,
            email=email,
            phone=phone,
            website=website,
            timezone=timezone,
            default_currency=default_currency,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            city_name=city_name,
            province_name=province_name,
            postal_code=postal_code,
            country_code=country_code,
            is_active=is_active,
        )
        _save(company)
    return company


def update_company(*, company: Company, **fields: Any) -> Company:
    with transaction.atomic():
        _apply_fields(company, fields)
        _save(company)
    return company


def deactivate_company(*, company: Company) -> Company:
    with transaction.atomic():
        company.is_active = False
        _save(company)
    return company


def activate_company(*, company: Company) -> Company:
    with transaction.atomic():
        company.is_active = True
        _save(company)
    return company


# --------------------------------------------------------------------------
# Region
# --------------------------------------------------------------------------


def create_region(
    *,
    company: Company,
    code: str,
    name: str,
    description: str = "",
    is_active: bool = True,
) -> Region:
    if not company.is_active:
        raise InactiveRelatedRecordError("Cannot create a region under an inactive company.")
    with transaction.atomic():
        region = Region(
            company=company, code=code, name=name, description=description, is_active=is_active
        )
        _save(region)
    return region


def update_region(*, region: Region, **fields: Any) -> Region:
    with transaction.atomic():
        _apply_fields(region, fields)
        _save(region)
    return region


def deactivate_region(*, region: Region) -> Region:
    with transaction.atomic():
        if region.branches.filter(is_active=True).exists():
            raise ActiveChildrenExistError("Cannot deactivate a region with active branches.")
        region.is_active = False
        _save(region)
    return region


def activate_region(*, region: Region) -> Region:
    with transaction.atomic():
        region.is_active = True
        _save(region)
    return region


# --------------------------------------------------------------------------
# City
# --------------------------------------------------------------------------


def create_city(
    *,
    company: Company,
    region: Region,
    code: str,
    name: str,
    province_or_state: str,
    country_code: str = "PK",
    timezone: str = "Asia/Karachi",
    is_active: bool = True,
) -> City:
    if not company.is_active:
        raise InactiveRelatedRecordError("Cannot create a city under an inactive company.")
    if not region.is_active:
        raise InactiveRelatedRecordError("Cannot create a city under an inactive region.")
    if region.company_id != company.id:
        raise HierarchyMismatchError("The selected region does not belong to the selected company.")
    with transaction.atomic():
        city = City(
            company=company,
            region=region,
            code=code,
            name=name,
            province_or_state=province_or_state,
            country_code=country_code,
            timezone=timezone,
            is_active=is_active,
        )
        _save(city)
    return city


def update_city(*, city: City, **fields: Any) -> City:
    with transaction.atomic():
        _apply_fields(city, fields)
        _save(city)
    return city


def deactivate_city(*, city: City) -> City:
    with transaction.atomic():
        if city.branches.filter(is_active=True).exists():
            raise ActiveChildrenExistError("Cannot deactivate a city with active branches.")
        city.is_active = False
        _save(city)
    return city


def activate_city(*, city: City) -> City:
    with transaction.atomic():
        city.is_active = True
        _save(city)
    return city


# --------------------------------------------------------------------------
# Branch
# --------------------------------------------------------------------------


def create_branch(
    *,
    company: Company,
    region: Region,
    city: City,
    code: str,
    name: str,
    address_line_1: str,
    email: str = "",
    phone: str = "",
    address_line_2: str = "",
    postal_code: str = "",
    latitude: Any = None,
    longitude: Any = None,
    is_head_office: bool = False,
    is_active: bool = True,
) -> Branch:
    if not company.is_active:
        raise InactiveRelatedRecordError("Cannot create a branch under an inactive company.")
    if not region.is_active:
        raise InactiveRelatedRecordError("Cannot create a branch under an inactive region.")
    if not city.is_active:
        raise InactiveRelatedRecordError("Cannot create a branch under an inactive city.")
    if region.company_id != company.id:
        raise HierarchyMismatchError("The selected region does not belong to the selected company.")
    if city.company_id != company.id:
        raise HierarchyMismatchError("The selected city does not belong to the selected company.")
    if city.region_id != region.id:
        raise HierarchyMismatchError("The selected city does not belong to the selected region.")
    if is_head_office and is_active:
        _guard_single_head_office(company=company)
    with transaction.atomic():
        branch = Branch(
            company=company,
            region=region,
            city=city,
            code=code,
            name=name,
            email=email,
            phone=phone,
            address_line_1=address_line_1,
            address_line_2=address_line_2,
            postal_code=postal_code,
            latitude=latitude,
            longitude=longitude,
            is_head_office=is_head_office,
            is_active=is_active,
        )
        _save(branch)
    return branch


def update_branch(*, branch: Branch, **fields: Any) -> Branch:
    with transaction.atomic():
        _apply_fields(branch, fields)
        if branch.is_head_office and branch.is_active:
            _guard_single_head_office(company=branch.company, exclude_pk=branch.pk)
        _save(branch)
    return branch


def deactivate_branch(*, branch: Branch) -> Branch:
    with transaction.atomic():
        if branch.operational_zones.filter(is_active=True).exists():
            raise ActiveChildrenExistError(
                "Cannot deactivate a branch with active operational zones."
            )
        branch.is_active = False
        _save(branch)
    return branch


def activate_branch(*, branch: Branch) -> Branch:
    with transaction.atomic():
        if branch.is_head_office:
            _guard_single_head_office(company=branch.company, exclude_pk=branch.pk)
        branch.is_active = True
        _save(branch)
    return branch


# --------------------------------------------------------------------------
# Department
# --------------------------------------------------------------------------


def create_department(
    *,
    company: Company,
    code: str,
    name: str,
    scope: str,
    parent: Department | None = None,
    branch: Branch | None = None,
    description: str = "",
    sort_order: int = 0,
    is_active: bool = True,
) -> Department:
    if not company.is_active:
        raise InactiveRelatedRecordError("Cannot create a department under an inactive company.")
    if parent is not None:
        if not parent.is_active:
            raise InactiveRelatedRecordError(
                "Cannot create a child department under an inactive parent."
            )
        if parent.company_id != company.id:
            raise HierarchyMismatchError("The parent department must belong to the same company.")
        if scope == DepartmentScope.COMPANY and parent.scope == DepartmentScope.BRANCH:
            raise ScopeViolationError(
                "A child department cannot have a broader scope than its parent."
            )
    if branch is not None and branch.company_id != company.id:
        raise HierarchyMismatchError("The selected branch does not belong to the selected company.")
    with transaction.atomic():
        department = Department(
            company=company,
            parent=parent,
            branch=branch,
            code=code,
            name=name,
            scope=scope,
            description=description,
            sort_order=sort_order,
            is_active=is_active,
        )
        _save(department)
    return department


def update_department(*, department: Department, **fields: Any) -> Department:
    with transaction.atomic():
        _apply_fields(department, fields)
        _save(department)
    return department


def deactivate_department(*, department: Department) -> Department:
    with transaction.atomic():
        if department.children.filter(is_active=True).exists():
            raise ActiveChildrenExistError(
                "Cannot deactivate a department with active child departments."
            )
        department.is_active = False
        _save(department)
    return department


def activate_department(*, department: Department) -> Department:
    with transaction.atomic():
        department.is_active = True
        _save(department)
    return department


# --------------------------------------------------------------------------
# Designation
# --------------------------------------------------------------------------


def create_designation(
    *,
    company: Company,
    code: str,
    name: str,
    level: int,
    department: Department | None = None,
    sort_order: int = 0,
    is_supervisory: bool = False,
    description: str = "",
    is_active: bool = True,
) -> Designation:
    if not company.is_active:
        raise InactiveRelatedRecordError("Cannot create a designation under an inactive company.")
    if department is not None:
        if not department.is_active:
            raise InactiveRelatedRecordError(
                "Cannot create a designation under an inactive department."
            )
        if department.company_id != company.id:
            raise HierarchyMismatchError(
                "The selected department does not belong to the selected company."
            )
    with transaction.atomic():
        designation = Designation(
            company=company,
            department=department,
            code=code,
            name=name,
            level=level,
            sort_order=sort_order,
            is_supervisory=is_supervisory,
            description=description,
            is_active=is_active,
        )
        _save(designation)
    return designation


def update_designation(*, designation: Designation, **fields: Any) -> Designation:
    with transaction.atomic():
        _apply_fields(designation, fields)
        _save(designation)
    return designation


def deactivate_designation(*, designation: Designation) -> Designation:
    with transaction.atomic():
        designation.is_active = False
        _save(designation)
    return designation


def activate_designation(*, designation: Designation) -> Designation:
    with transaction.atomic():
        designation.is_active = True
        _save(designation)
    return designation


# --------------------------------------------------------------------------
# Operational Zone
# --------------------------------------------------------------------------


def create_operational_zone(
    *,
    company: Company,
    branch: Branch,
    code: str,
    name: str,
    description: str = "",
    is_active: bool = True,
) -> OperationalZone:
    if not company.is_active:
        raise InactiveRelatedRecordError(
            "Cannot create an operational zone under an inactive company."
        )
    if not branch.is_active:
        raise InactiveRelatedRecordError(
            "Cannot create an operational zone under an inactive branch."
        )
    if branch.company_id != company.id:
        raise HierarchyMismatchError("The selected branch does not belong to the selected company.")
    with transaction.atomic():
        zone = OperationalZone(
            company=company,
            branch=branch,
            code=code,
            name=name,
            description=description,
            is_active=is_active,
        )
        _save(zone)
    return zone


def update_operational_zone(*, operational_zone: OperationalZone, **fields: Any) -> OperationalZone:
    with transaction.atomic():
        _apply_fields(operational_zone, fields)
        _save(operational_zone)
    return operational_zone


def deactivate_operational_zone(*, operational_zone: OperationalZone) -> OperationalZone:
    with transaction.atomic():
        operational_zone.is_active = False
        _save(operational_zone)
    return operational_zone


def activate_operational_zone(*, operational_zone: OperationalZone) -> OperationalZone:
    with transaction.atomic():
        operational_zone.is_active = True
        _save(operational_zone)
    return operational_zone
