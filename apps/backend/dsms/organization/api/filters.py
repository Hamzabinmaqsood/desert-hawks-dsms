import django_filters as filters

from dsms.organization.enums import DepartmentScope
from dsms.organization.models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
    Region,
)


class CompanyFilterSet(filters.FilterSet):  # type: ignore[misc]
    is_active = filters.BooleanFilter(field_name="is_active")
    country_code = filters.CharFilter(field_name="country_code", lookup_expr="iexact")

    class Meta:
        model = Company
        fields = ["is_active", "country_code"]


class RegionFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    is_active = filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = Region
        fields = ["company", "is_active"]


class CityFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    region = filters.UUIDFilter(field_name="region_id")
    is_active = filters.BooleanFilter(field_name="is_active")
    country_code = filters.CharFilter(field_name="country_code", lookup_expr="iexact")

    class Meta:
        model = City
        fields = ["company", "region", "is_active", "country_code"]


class BranchFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    region = filters.UUIDFilter(field_name="region_id")
    city = filters.UUIDFilter(field_name="city_id")
    is_active = filters.BooleanFilter(field_name="is_active")
    is_head_office = filters.BooleanFilter(field_name="is_head_office")

    class Meta:
        model = Branch
        fields = ["company", "region", "city", "is_active", "is_head_office"]


class DepartmentFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    branch = filters.UUIDFilter(field_name="branch_id")
    parent = filters.UUIDFilter(field_name="parent_id")
    scope = filters.ChoiceFilter(field_name="scope", choices=DepartmentScope.choices)
    is_active = filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = Department
        fields = ["company", "branch", "parent", "scope", "is_active"]


class DesignationFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    department = filters.UUIDFilter(field_name="department_id")
    is_active = filters.BooleanFilter(field_name="is_active")
    is_supervisory = filters.BooleanFilter(field_name="is_supervisory")

    class Meta:
        model = Designation
        fields = ["company", "department", "is_active", "is_supervisory"]


class OperationalZoneFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    branch = filters.UUIDFilter(field_name="branch_id")
    is_active = filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = OperationalZone
        fields = ["company", "branch", "is_active"]
