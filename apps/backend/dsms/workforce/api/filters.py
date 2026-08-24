import django_filters as filters
from rest_framework.filters import SearchFilter
from rest_framework.request import Request
from rest_framework.views import APIView

from dsms.identity import access
from dsms.workforce.enums import EmployeeType, EmploymentStatus, EmploymentType, Gender
from dsms.workforce.models import Employee


class EmployeeFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    region = filters.UUIDFilter(field_name="branch__region_id")
    branch = filters.UUIDFilter(field_name="branch_id")
    department = filters.UUIDFilter(field_name="department_id")
    designation = filters.UUIDFilter(field_name="designation_id")
    employee_type = filters.ChoiceFilter(field_name="employee_type", choices=EmployeeType.choices)
    employment_type = filters.ChoiceFilter(
        field_name="employment_type", choices=EmploymentType.choices
    )
    employment_status = filters.ChoiceFilter(
        field_name="employment_status", choices=EmploymentStatus.choices
    )
    is_active = filters.BooleanFilter(field_name="is_active")
    gender = filters.ChoiceFilter(field_name="gender", choices=Gender.choices)
    joining_date_from = filters.DateFilter(field_name="joining_date", lookup_expr="gte")
    joining_date_to = filters.DateFilter(field_name="joining_date", lookup_expr="lte")

    class Meta:
        model = Employee
        fields = [
            "company",
            "region",
            "branch",
            "department",
            "designation",
            "employee_type",
            "employment_type",
            "employment_status",
            "is_active",
            "gender",
            "joining_date_from",
            "joining_date_to",
        ]


class EmployeeSearchFilter(SearchFilter):
    """Search filter that only offers ``national_identity_number`` to privileged callers.

    Plain :class:`~rest_framework.filters.SearchFilter` reads ``search_fields``
    as a static list; this subclass extends it per-request so that
    unprivileged users cannot discover/match employees by identity number.
    """

    def get_search_fields(self, view: APIView, request: Request) -> list[str] | None:
        fields = list(getattr(view, "search_fields", None) or [])
        user = request.user
        if (
            user is not None
            and user.is_authenticated
            and (
                user.is_superuser
                or "workforce.view_sensitive_employee_data"
                in access.get_effective_permissions(user)
            )
        ):
            fields.append("national_identity_number")
        return fields
