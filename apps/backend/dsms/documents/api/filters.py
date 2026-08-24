import django_filters as filters

from ..enums import DocumentStatus
from ..models import EmployeeDocument


class EmployeeDocumentFilter(filters.FilterSet):  # type: ignore[misc]
    employee = filters.UUIDFilter(field_name="employee_id")
    company = filters.UUIDFilter(field_name="company_id")
    branch = filters.UUIDFilter(field_name="employee__branch_id")
    department = filters.UUIDFilter(field_name="employee__department_id")
    designation = filters.UUIDFilter(field_name="employee__designation_id")
    employee_type = filters.CharFilter(field_name="employee__employee_type")
    document_type = filters.UUIDFilter(field_name="document_type_id")
    category = filters.CharFilter(field_name="document_type__category")
    status = filters.ChoiceFilter(choices=DocumentStatus.choices)
    is_sensitive = filters.BooleanFilter(field_name="document_type__is_sensitive")
    has_expiry = filters.BooleanFilter(method="filter_has_expiry")
    expires_before = filters.DateFilter(field_name="expires_on", lookup_expr="lte")
    expires_after = filters.DateFilter(field_name="expires_on", lookup_expr="gte")
    verified_by = filters.UUIDFilter(field_name="verified_by_id")

    def filter_has_expiry(self, queryset, name: str, value: bool):  # type: ignore[no-untyped-def]
        return queryset.filter(expires_on__isnull=not value)

    class Meta:
        model = EmployeeDocument
        fields: list[str] = []
