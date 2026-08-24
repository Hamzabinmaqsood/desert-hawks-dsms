from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.identity.models import User
from dsms.organization.models import Company
from dsms.workforce.models import Employee

from .enums import DocumentCategory, DocumentEventType, DocumentStatus
from .storage import private_document_storage, private_document_upload_to
from .validators import mask_document_number, normalize_document_number


class DocumentType(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(
        Company, null=True, blank=True, on_delete=models.PROTECT, related_name="document_types"
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=30, choices=DocumentCategory.choices)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    is_sensitive = models.BooleanField(default=False)
    requires_document_number = models.BooleanField(default=False)
    requires_issue_date = models.BooleanField(default=False)
    requires_expiry_date = models.BooleanField(default=False)
    allow_multiple = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(company__isnull=True),
                name="uniq_global_document_type_code",
            ),
            models.UniqueConstraint(
                fields=["company", "code"],
                condition=Q(company__isnull=False),
                name="uniq_company_document_type_code",
            ),
        ]
        permissions = [("manage_document_types", "Can manage document types")]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        super().save(*args, **kwargs)


class EmployeeDocument(UUIDModel, TimeStampedModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="documents")
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="employee_documents"
    )
    document_type = models.ForeignKey(
        DocumentType, on_delete=models.PROTECT, related_name="employee_documents"
    )
    document_number = models.CharField(max_length=100, blank=True)
    issuing_authority = models.CharField(max_length=150, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT
    )
    notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_employee_documents",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rejected_employee_documents",
    )
    rejection_reason = models.TextField(blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="revoked_employee_documents",
    )
    revocation_reason = models.TextField(blank=True)
    superseded_by = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="supersedes"
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_employee_documents",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "status"], name="doc_company_status_idx"),
            models.Index(fields=["expires_on"], name="doc_expiry_idx"),
        ]
        permissions = [
            ("view_sensitive_document_data", "Can view sensitive document data"),
            ("download_employee_document", "Can download employee document files"),
            ("verify_employee_document", "Can verify or reject employee documents"),
            ("revoke_employee_document", "Can revoke employee documents"),
            ("view_document_audit", "Can view document audit history"),
        ]

    def __str__(self) -> str:
        return f"{self.employee.employee_number} / {self.document_type.code}"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.employee_id and self.company_id != self.employee.company_id:
            errors["company"] = "Document company must match employee company."
        if self.document_type_id and self.document_type.company_id not in {None, self.company_id}:
            errors["document_type"] = "Document type is not available to this company."
        if self.document_type_id:
            if self.document_type.requires_document_number and not self.document_number:
                errors["document_number"] = "Document number is required for this document type."
            if self.document_type.requires_issue_date and self.issue_date is None:
                errors["issue_date"] = "Issue date is required for this document type."
            if self.document_type.requires_expiry_date and self.expires_on is None:
                errors["expires_on"] = "Expiry date is required for this document type."
        if self.issue_date and self.expires_on and self.expires_on < self.issue_date:
            errors["expires_on"] = "Expiry date cannot be earlier than issue date."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.document_number = normalize_document_number(self.document_number)
        super().save(*args, **kwargs)

    @property
    def is_expired(self) -> bool:
        return self.expires_on is not None and self.expires_on < timezone.localdate()

    @property
    def days_until_expiry(self) -> int | None:
        return None if self.expires_on is None else (self.expires_on - timezone.localdate()).days

    def is_expiring_soon(self, days: int = 30) -> bool:
        remaining = self.days_until_expiry
        return remaining is not None and 0 <= remaining <= days

    @property
    def current_version(self) -> "EmployeeDocumentVersion | None":
        prefetched = getattr(self, "current_versions", None)
        if prefetched is not None:
            return prefetched[0] if prefetched else None
        return next((version for version in self.versions.all() if version.is_current), None)

    @property
    def has_file(self) -> bool:
        return self.current_version is not None

    @property
    def display_document_number(self) -> str:
        return (
            mask_document_number(self.document_number)
            if self.document_type.is_sensitive
            else self.document_number
        )


class EmployeeDocumentVersion(UUIDModel):
    document = models.ForeignKey(
        EmployeeDocument, on_delete=models.PROTECT, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    file = models.FileField(
        storage=private_document_storage, upload_to=private_document_upload_to, max_length=255
    )
    original_filename = models.CharField(max_length=255)
    stored_filename = models.CharField(max_length=255)
    file_extension = models.CharField(max_length=10)
    file_size = models.PositiveBigIntegerField()
    mime_type = models.CharField(max_length=100)
    sha256_hash = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uploaded_document_versions",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "version_number"], name="uniq_document_version"
            ),
            models.UniqueConstraint(
                fields=["document"],
                condition=Q(is_current=True),
                name="uniq_current_document_version",
            ),
            models.CheckConstraint(
                condition=Q(version_number__gt=0), name="positive_document_version"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} v{self.version_number}"


class EmployeeDocumentEvent(UUIDModel):
    document = models.ForeignKey(EmployeeDocument, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=30, choices=DocumentEventType.choices)
    from_status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, null=True, blank=True
    )
    to_status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, null=True, blank=True
    )
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee_document_events",
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.document_id} / {self.event_type}"
