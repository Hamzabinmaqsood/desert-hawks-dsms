import hashlib
from datetime import date, timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from dsms.documents import selectors, services
from dsms.documents.enums import DocumentCategory, DocumentEventType, DocumentStatus
from dsms.documents.exceptions import (
    DocumentValidationError,
    InvalidDocumentTransitionError,
    ProtectedSystemDocumentTypeError,
)
from dsms.documents.models import EmployeeDocumentEvent
from tests.factories.documents import DocumentTypeFactory, EmployeeDocumentFactory
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db
TODAY = date(2026, 8, 18)
PDF = b"%PDF-1.4\n% safe test document\n%%EOF"
PNG = b"\x89PNG\r\n\x1a\n" + b"safe-test-image"


@pytest.fixture(autouse=True)
def private_storage(settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def upload(name: str = "scan.pdf", content: bytes = PDF) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, content)


def test_document_type_normalization_uniqueness_and_inactive_company() -> None:
    actor = UserFactory.create()
    item = services.create_document_type(
        actor=actor, code=" cnic ", name=" CNIC ", category=DocumentCategory.IDENTITY
    )
    assert item.code == "CNIC" and item.name == "CNIC"
    with pytest.raises(DocumentValidationError):
        services.create_document_type(
            actor=actor, code="CNIC", name="Duplicate", category=DocumentCategory.IDENTITY
        )
    with pytest.raises(DocumentValidationError):
        services.create_document_type(
            actor=actor,
            company=CompanyFactory.create(is_active=False),
            code="LOCAL",
            name="Local",
            category=DocumentCategory.OTHER,
        )


def test_company_document_type_uniqueness_is_per_company() -> None:
    actor = UserFactory.create()
    one = CompanyFactory.create()
    two = CompanyFactory.create()
    services.create_document_type(
        actor=actor, company=one, code="CUSTOM", name="One", category=DocumentCategory.OTHER
    )
    item = services.create_document_type(
        actor=actor, company=two, code="CUSTOM", name="Two", category=DocumentCategory.OTHER
    )
    assert item.company == two


def test_system_document_type_is_protected() -> None:
    item = DocumentTypeFactory.create(is_system=True)
    with pytest.raises(ProtectedSystemDocumentTypeError):
        services.update_document_type(
            document_type=item, actor=UserFactory.create(), name="Changed"
        )


def test_document_required_fields_hierarchy_and_expiry_validation() -> None:
    actor = UserFactory.create()
    employee = EmployeeFactory.create()
    kind = DocumentTypeFactory.create(
        requires_document_number=True,
        requires_issue_date=True,
        requires_expiry_date=True,
        allow_multiple=False,
    )
    with pytest.raises(DocumentValidationError):
        services.create_employee_document(employee=employee, document_type=kind, actor=actor)
    with pytest.raises(DocumentValidationError):
        services.create_employee_document(
            employee=employee,
            document_type=kind,
            actor=actor,
            document_number="ABC",
            issue_date=TODAY,
            expires_on=TODAY - timedelta(days=1),
        )
    other_kind = DocumentTypeFactory.create(company=CompanyFactory.create())
    with pytest.raises(DocumentValidationError):
        services.create_employee_document(employee=employee, document_type=other_kind, actor=actor)


def test_allow_multiple_false_is_enforced() -> None:
    employee = EmployeeFactory.create()
    kind = DocumentTypeFactory.create(allow_multiple=False)
    actor = UserFactory.create()
    services.create_employee_document(employee=employee, document_type=kind, actor=actor)
    with pytest.raises(DocumentValidationError):
        services.create_employee_document(employee=employee, document_type=kind, actor=actor)


def test_sensitive_number_mask_and_expiry_properties() -> None:
    today = timezone.localdate()
    document = EmployeeDocumentFactory.create(
        document_type=DocumentTypeFactory.create(is_sensitive=True),
        document_number="35202-1234567-1",
        expires_on=today,
    )
    assert document.display_document_number == "*****-*******-1"
    assert not document.is_expired
    assert document.days_until_expiry == 0
    assert document.is_expiring_soon(7)
    document.expires_on = today - timedelta(days=1)
    assert document.is_expired


def test_upload_versioning_hash_and_private_uuid_path() -> None:
    actor = UserFactory.create()
    document = EmployeeDocumentFactory.create()
    first = services.add_employee_document_version(
        document=document,
        upload=upload("../../cnic.pdf"),
        original_filename="../../cnic.pdf",
        actor=actor,
    )
    second = services.add_employee_document_version(
        document=document, upload=upload("clear.pdf"), original_filename="clear.pdf", actor=actor
    )
    first.refresh_from_db()
    assert first.version_number == 1 and second.version_number == 2
    assert not first.is_current and second.is_current
    assert first.sha256_hash == hashlib.sha256(PDF).hexdigest()
    assert first.original_filename == "cnic.pdf"
    assert "cnic" not in first.stored_filename
    with pytest.raises(ValueError):
        first.file.storage.url(first.file.name)


@pytest.mark.parametrize(
    ("name", "content"),
    [("attack.exe", b"MZ executable"), ("fake.pdf", b"not a pdf"), ("page.html", b"<html>")],
)
def test_unsafe_uploads_rejected(name: str, content: bytes) -> None:
    with pytest.raises(DocumentValidationError):
        services.add_employee_document_version(
            document=EmployeeDocumentFactory.create(),
            upload=upload(name, content),
            original_filename=name,
            actor=UserFactory.create(),
        )


def test_file_too_large_rejected(settings) -> None:  # type: ignore[no-untyped-def]
    settings.DOCUMENT_MAX_UPLOAD_SIZE = 5
    with pytest.raises(DocumentValidationError):
        services.add_employee_document_version(
            document=EmployeeDocumentFactory.create(),
            upload=upload(),
            original_filename="scan.pdf",
            actor=UserFactory.create(),
        )


def test_submit_verify_reject_resubmit_and_revoke_workflows() -> None:
    actor = UserFactory.create()
    document = EmployeeDocumentFactory.create()
    with pytest.raises(DocumentValidationError):
        services.submit_employee_document(document=document, actor=actor)
    services.add_employee_document_version(
        document=document, upload=upload(), original_filename="scan.pdf", actor=actor
    )
    services.submit_employee_document(document=document, actor=actor)
    assert document.status == DocumentStatus.PENDING_REVIEW
    with pytest.raises(DocumentValidationError):
        services.reject_employee_document(document=document, actor=actor, rejection_reason="")
    services.reject_employee_document(document=document, actor=actor, rejection_reason="Blurred")
    services.add_employee_document_version(
        document=document, upload=upload("fixed.pdf"), original_filename="fixed.pdf", actor=actor
    )
    services.submit_employee_document(document=document, actor=actor)
    services.verify_employee_document(document=document, actor=actor)
    assert document.verified_by == actor
    services.revoke_employee_document(document=document, actor=actor, revocation_reason="Invalid")
    assert document.status == DocumentStatus.REVOKED
    assert EmployeeDocumentEvent.objects.filter(document=document).count() == 7


def test_invalid_workflow_transition_is_rejected() -> None:
    document = EmployeeDocumentFactory.create()
    services.add_employee_document_version(
        document=document,
        upload=upload(),
        original_filename="scan.pdf",
        actor=UserFactory.create(),
    )
    with pytest.raises(InvalidDocumentTransitionError):
        services.verify_employee_document(document=document, actor=UserFactory.create())


def test_expiry_and_status_selectors() -> None:
    today = timezone.localdate()
    expired = EmployeeDocumentFactory.create(expires_on=today - timedelta(days=1))
    soon = EmployeeDocumentFactory.create(expires_on=today + timedelta(days=7))
    verified = EmployeeDocumentFactory.create(status=DocumentStatus.VERIFIED)
    assert selectors.expired_documents().filter(pk=expired.pk).exists()
    assert selectors.expiring_documents(7).filter(pk=soon.pk).exists()
    assert selectors.verified_documents().filter(pk=verified.pk).exists()
    assert selectors.document_events(soon).count() == 0
    assert selectors.document_versions(soon).count() == 0


def test_created_and_file_events_capture_actor() -> None:
    actor = UserFactory.create()
    document = services.create_employee_document(
        employee=EmployeeFactory.create(), document_type=DocumentTypeFactory.create(), actor=actor
    )
    services.add_employee_document_version(
        document=document, upload=upload(), original_filename="scan.pdf", actor=actor
    )
    events = list(document.events.order_by("created_at"))
    assert [item.event_type for item in events] == [
        DocumentEventType.CREATED,
        DocumentEventType.FILE_ADDED,
    ]
    assert all(item.actor == actor for item in events)
