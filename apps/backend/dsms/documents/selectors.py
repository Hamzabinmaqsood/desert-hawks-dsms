from datetime import timedelta
from uuid import UUID

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone

from dsms.identity import access
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User

from .enums import DocumentStatus
from .models import DocumentType, EmployeeDocument, EmployeeDocumentEvent, EmployeeDocumentVersion


def document_type_list() -> QuerySet[DocumentType]:
    return DocumentType.objects.select_related("company")


def active_document_types() -> QuerySet[DocumentType]:
    return document_type_list().filter(is_active=True)


def employee_document_list() -> QuerySet[EmployeeDocument]:
    current = EmployeeDocumentVersion.objects.filter(is_current=True)
    return EmployeeDocument.objects.select_related(
        "employee",
        "company",
        "employee__branch",
        "employee__branch__region",
        "employee__department",
        "employee__designation",
        "document_type",
        "verified_by",
    ).prefetch_related(Prefetch("versions", queryset=current, to_attr="current_versions"))


def accessible_documents(
    user: User | None, permission: str = "documents.view_employeedocument"
) -> QuerySet[EmployeeDocument]:
    queryset = employee_document_list()
    if user is None or not user.is_authenticated or not user.is_active:
        return queryset.none()
    if user.is_superuser:
        return queryset
    query = Q(pk__in=[])
    for assignment in access.get_active_role_assignments(user):
        codes = {
            f"{item.content_type.app_label}.{item.codename}"
            for item in assignment.role.permissions.all()
        }
        if permission not in codes:
            continue
        if assignment.scope_type == AccessScopeType.GLOBAL:
            return queryset
        if assignment.scope_type == AccessScopeType.COMPANY:
            query |= Q(company_id=assignment.company_id)
        elif assignment.scope_type == AccessScopeType.REGION:
            query |= Q(employee__branch__region_id=assignment.region_id)
        elif assignment.scope_type == AccessScopeType.BRANCH:
            query |= Q(employee__branch_id=assignment.branch_id)
        elif assignment.scope_type == AccessScopeType.DEPARTMENT:
            query |= Q(employee__department_id=assignment.department_id)
    return queryset.filter(query).distinct()


def documents_for_employee(employee_id: UUID) -> QuerySet[EmployeeDocument]:
    return employee_document_list().filter(employee_id=employee_id)


def document_detail(document_id: UUID) -> EmployeeDocument:
    return employee_document_list().get(pk=document_id)


def document_versions(document: EmployeeDocument) -> QuerySet[EmployeeDocumentVersion]:
    return document.versions.select_related("uploaded_by")


def document_events(document: EmployeeDocument) -> QuerySet[EmployeeDocumentEvent]:
    return document.events.select_related("actor")


def verified_documents() -> QuerySet[EmployeeDocument]:
    return employee_document_list().filter(status=DocumentStatus.VERIFIED)


def pending_documents() -> QuerySet[EmployeeDocument]:
    return employee_document_list().filter(status=DocumentStatus.PENDING_REVIEW)


def rejected_documents() -> QuerySet[EmployeeDocument]:
    return employee_document_list().filter(status=DocumentStatus.REJECTED)


def expired_documents(
    queryset: QuerySet[EmployeeDocument] | None = None,
) -> QuerySet[EmployeeDocument]:
    return (queryset or employee_document_list()).filter(expires_on__lt=timezone.localdate())


def expiring_documents(
    days: int = 30, queryset: QuerySet[EmployeeDocument] | None = None
) -> QuerySet[EmployeeDocument]:
    today = timezone.localdate()
    return (queryset or employee_document_list()).filter(
        expires_on__gte=today, expires_on__lte=today + timedelta(days=days)
    )
