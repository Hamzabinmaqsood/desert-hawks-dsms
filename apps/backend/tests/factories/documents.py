from datetime import date

import factory
from factory.django import DjangoModelFactory

from dsms.documents.enums import DocumentCategory, DocumentStatus
from dsms.documents.models import DocumentType, EmployeeDocument
from dsms.identity.models import User
from dsms.organization.models import Company
from dsms.workforce.models import Employee
from tests.factories.identity import UserFactory
from tests.factories.workforce import EmployeeFactory


class DocumentTypeFactory(DjangoModelFactory[DocumentType]):
    class Meta:
        model = DocumentType

    code = factory.Sequence(lambda n: f"DOC{n:04d}")
    name = factory.Sequence(lambda n: f"Document Type {n}")
    category = DocumentCategory.OTHER


class EmployeeDocumentFactory(DjangoModelFactory[EmployeeDocument]):
    class Meta:
        model = EmployeeDocument

    employee: Employee = factory.SubFactory(EmployeeFactory)  # type: ignore[assignment]
    company: Company = factory.LazyAttribute(  # type: ignore[assignment]
        lambda item: item.employee.company
    )
    document_type: DocumentType = factory.SubFactory(  # type: ignore[assignment]
        DocumentTypeFactory
    )
    status = DocumentStatus.DRAFT
    created_by: User = factory.SubFactory(UserFactory)  # type: ignore[assignment]
    issue_date = date(2026, 1, 1)
