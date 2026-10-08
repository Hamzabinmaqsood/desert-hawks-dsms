from __future__ import annotations

from django.db.models import F, Q, QuerySet

from dsms.deployment.tenant_queries import consistent_employees
from dsms.identity import access
from dsms.identity.models import User
from dsms.workforce.models import Employee

from .models import DocumentType, EmployeeDocument


def consistent_document_types(queryset: QuerySet[DocumentType]) -> QuerySet[DocumentType]:
    return queryset.filter(Q(company__isnull=True) | Q(company__is_active=True))


def scoped_document_types(
    queryset: QuerySet[DocumentType], *, user: User, permission: str
) -> QuerySet[DocumentType]:
    queryset = consistent_document_types(queryset)
    if user.is_superuser:
        return queryset
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    return queryset.filter(Q(company__isnull=True) | Q(company_id__in=company_ids))


def consistent_employee_documents(
    queryset: QuerySet[EmployeeDocument],
) -> QuerySet[EmployeeDocument]:
    employee_ids = consistent_employees(Employee.objects.all()).values("pk")
    return (
        queryset.filter(
            company__is_active=True,
            employee_id__in=employee_ids,
            employee__company_id=F("company_id"),
        )
        .filter(
            Q(document_type__company__isnull=True) | Q(document_type__company_id=F("company_id"))
        )
        .distinct()
    )
