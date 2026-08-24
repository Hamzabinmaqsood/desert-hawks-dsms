import hashlib
from datetime import date
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files import File
from django.db import IntegrityError, models, transaction
from django.db.models import Max
from django.utils import timezone

from dsms.audit.models import AuditCategory
from dsms.audit.services import record_audit_event
from dsms.identity.models import User
from dsms.organization.models import Company
from dsms.workforce.models import Employee

from .enums import DocumentEventType, DocumentStatus
from .exceptions import (
    DocumentValidationError,
    InvalidDocumentTransitionError,
    ProtectedSystemDocumentTypeError,
)
from .models import DocumentType, EmployeeDocument, EmployeeDocumentEvent, EmployeeDocumentVersion
from .validators import normalize_document_number, validate_upload


def _save(instance: models.Model) -> None:
    try:
        instance.full_clean()
        instance.save()
    except DjangoValidationError as exc:
        detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
        raise DocumentValidationError(detail) from exc
    except IntegrityError as exc:
        raise DocumentValidationError(
            {"detail": ["The document record conflicts with existing data."]}
        ) from exc


def _event(
    document: EmployeeDocument,
    event_type: str,
    actor: User | None,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str = "",
) -> None:
    EmployeeDocumentEvent.objects.create(
        document=document,
        event_type=event_type,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        reason=reason.strip(),
    )


@transaction.atomic
def create_document_type(
    *,
    actor: User,
    code: str,
    name: str,
    category: str,
    company: Company | None = None,
    description: str = "",
    is_sensitive: bool = False,
    requires_document_number: bool = False,
    requires_issue_date: bool = False,
    requires_expiry_date: bool = False,
    allow_multiple: bool = True,
    sort_order: int = 0,
) -> DocumentType:
    if company is not None and not company.is_active:
        raise DocumentValidationError(
            {"company": ["Inactive companies cannot receive document types."]}
        )
    item = DocumentType(
        company=company,
        code=code,
        name=name,
        category=category,
        description=description,
        is_sensitive=is_sensitive,
        requires_document_number=requires_document_number,
        requires_issue_date=requires_issue_date,
        requires_expiry_date=requires_expiry_date,
        allow_multiple=allow_multiple,
        sort_order=sort_order,
        is_system=False,
    )
    _save(item)
    return item


@transaction.atomic
def update_document_type(
    *, document_type: DocumentType, actor: User, **fields: Any
) -> DocumentType:
    if document_type.is_system and not actor.is_superuser:
        raise ProtectedSystemDocumentTypeError("System document types cannot be modified.")
    for name, value in fields.items():
        setattr(document_type, name, value)
    _save(document_type)
    return document_type


def activate_document_type(*, document_type: DocumentType, actor: User) -> DocumentType:
    return update_document_type(document_type=document_type, actor=actor, is_active=True)


def deactivate_document_type(*, document_type: DocumentType, actor: User) -> DocumentType:
    return update_document_type(document_type=document_type, actor=actor, is_active=False)


def _validate_document(document: EmployeeDocument) -> None:
    if not document.document_type.is_active:
        raise DocumentValidationError(
            {"document_type": ["Inactive document types cannot receive documents."]}
        )
    _save(document)


@transaction.atomic
def create_employee_document(
    *,
    employee: Employee,
    document_type: DocumentType,
    actor: User,
    document_number: str = "",
    issuing_authority: str = "",
    issue_date: date | None = None,
    expires_on: date | None = None,
    notes: str = "",
) -> EmployeeDocument:
    if (
        not document_type.allow_multiple
        and EmployeeDocument.objects.filter(employee=employee, document_type=document_type)
        .exclude(status__in=[DocumentStatus.SUPERSEDED, DocumentStatus.REVOKED])
        .exists()
    ):
        raise DocumentValidationError(
            {"document_type": ["A current document of this type already exists."]}
        )
    document = EmployeeDocument(
        employee=employee,
        company=employee.company,
        document_type=document_type,
        document_number=document_number,
        issuing_authority=issuing_authority.strip(),
        issue_date=issue_date,
        expires_on=expires_on,
        notes=notes.strip(),
        created_by=actor,
    )
    _validate_document(document)
    _event(document, DocumentEventType.CREATED, actor, to_status=DocumentStatus.DRAFT)
    return document


@transaction.atomic
def update_employee_document_metadata(
    *, document: EmployeeDocument, actor: User, **fields: Any
) -> EmployeeDocument:
    if document.status not in {DocumentStatus.DRAFT, DocumentStatus.REJECTED}:
        raise InvalidDocumentTransitionError("Metadata can only be edited while draft or rejected.")
    allowed = {"document_number", "issuing_authority", "issue_date", "expires_on", "notes"}
    for name, value in fields.items():
        if name not in allowed:
            raise DocumentValidationError(
                {name: ["This field cannot be changed through metadata update."]}
            )
        setattr(document, name, value)
    document.document_number = normalize_document_number(document.document_number)
    _validate_document(document)
    _event(document, DocumentEventType.METADATA_UPDATED, actor)
    return document


@transaction.atomic
def add_employee_document_version(
    *,
    document: EmployeeDocument,
    upload: Any,
    original_filename: str,
    actor: User,
    notes: str = "",
) -> EmployeeDocumentVersion:
    extension, mime_type, size = validate_upload(upload, original_filename)
    upload.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: upload.read(1024 * 1024), b""):
        digest.update(chunk)
    upload.seek(0)
    current_max = document.versions.aggregate(value=Max("version_number"))["value"] or 0
    document.versions.filter(is_current=True).update(is_current=False)
    safe_original = Path(original_filename).name[:255]
    version = EmployeeDocumentVersion(
        document=document,
        version_number=current_max + 1,
        original_filename=safe_original,
        stored_filename="pending",
        file_extension=extension,
        file_size=size,
        mime_type=mime_type,
        sha256_hash=digest.hexdigest(),
        uploaded_by=actor,
        notes=notes.strip(),
        is_current=True,
    )
    version.file.save(safe_original, File(upload), save=False)
    version.stored_filename = version.file.name
    _save(version)
    _event(
        document,
        DocumentEventType.FILE_ADDED,
        actor,
        reason=f"File version {version.version_number} added.",
    )
    return version


def _transition(
    document: EmployeeDocument,
    *,
    expected: set[str],
    target: str,
    event_type: str,
    actor: User,
    reason: str = "",
) -> EmployeeDocument:
    if document.status not in expected:
        raise InvalidDocumentTransitionError(
            f"Cannot transition document from {document.status} to {target}."
        )
    previous = document.status
    document.status = target
    _save(document)
    _event(document, event_type, actor, from_status=previous, to_status=target, reason=reason)
    if target in {DocumentStatus.VERIFIED, DocumentStatus.REJECTED, DocumentStatus.REVOKED}:
        record_audit_event(
            action=f"DOCUMENT_{target}",
            category=AuditCategory.DOCUMENTS,
            summary=f"Employee document moved to {target}.",
            actor_user=actor,
            company=document.employee.company,
            branch=document.employee.branch,
            source_object=document,
            metadata_safe={"document_type": document.document_type.code},
        )
    return document


@transaction.atomic
def submit_employee_document(*, document: EmployeeDocument, actor: User) -> EmployeeDocument:
    _validate_document(document)
    if not document.versions.filter(is_current=True).exists():
        raise DocumentValidationError(
            {"file": ["A current file version is required before submission."]}
        )
    document.submitted_at = timezone.now()
    document.rejection_reason = ""
    return _transition(
        document,
        expected={DocumentStatus.DRAFT, DocumentStatus.REJECTED},
        target=DocumentStatus.PENDING_REVIEW,
        event_type=DocumentEventType.SUBMITTED,
        actor=actor,
    )


@transaction.atomic
def verify_employee_document(
    *, document: EmployeeDocument, actor: User, reason: str = ""
) -> EmployeeDocument:
    if not document.versions.filter(is_current=True).exists():
        raise DocumentValidationError({"file": ["A current file version is required."]})
    document.verified_at = timezone.now()
    document.verified_by = actor
    return _transition(
        document,
        expected={DocumentStatus.PENDING_REVIEW},
        target=DocumentStatus.VERIFIED,
        event_type=DocumentEventType.VERIFIED,
        actor=actor,
        reason=reason,
    )


@transaction.atomic
def reject_employee_document(
    *, document: EmployeeDocument, actor: User, rejection_reason: str
) -> EmployeeDocument:
    if not rejection_reason.strip():
        raise DocumentValidationError({"rejection_reason": ["A rejection reason is required."]})
    document.rejected_at = timezone.now()
    document.rejected_by = actor
    document.rejection_reason = rejection_reason.strip()
    return _transition(
        document,
        expected={DocumentStatus.PENDING_REVIEW},
        target=DocumentStatus.REJECTED,
        event_type=DocumentEventType.REJECTED,
        actor=actor,
        reason=rejection_reason,
    )


@transaction.atomic
def revoke_employee_document(
    *, document: EmployeeDocument, actor: User, revocation_reason: str
) -> EmployeeDocument:
    if not revocation_reason.strip():
        raise DocumentValidationError({"revocation_reason": ["A revocation reason is required."]})
    document.revoked_at = timezone.now()
    document.revoked_by = actor
    document.revocation_reason = revocation_reason.strip()
    return _transition(
        document,
        expected={DocumentStatus.VERIFIED},
        target=DocumentStatus.REVOKED,
        event_type=DocumentEventType.REVOKED,
        actor=actor,
        reason=revocation_reason,
    )


@transaction.atomic
def supersede_employee_document(
    *, document: EmployeeDocument, successor: EmployeeDocument, actor: User, reason: str = ""
) -> EmployeeDocument:
    if (
        successor.pk == document.pk
        or successor.employee_id != document.employee_id
        or successor.document_type_id != document.document_type_id
    ):
        raise DocumentValidationError(
            {"successor": ["Successor must be another document of the same employee and type."]}
        )
    document.superseded_by = successor
    return _transition(
        document,
        expected={DocumentStatus.VERIFIED},
        target=DocumentStatus.SUPERSEDED,
        event_type=DocumentEventType.SUPERSEDED,
        actor=actor,
        reason=reason,
    )
