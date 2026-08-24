from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import DocumentType, EmployeeDocument, EmployeeDocumentEvent, EmployeeDocumentVersion


class NoDeleteAdmin(admin.ModelAdmin[Any]):
    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(DocumentType)
class DocumentTypeAdmin(NoDeleteAdmin):
    list_display = ("code", "name", "company", "category", "is_sensitive", "is_active")
    list_filter = ("company", "category", "is_sensitive", "is_active")
    search_fields = ("code", "name")
    readonly_fields = ("is_system", "created_at", "updated_at")


@admin.register(EmployeeDocument)
class EmployeeDocumentAdmin(NoDeleteAdmin):
    list_display = ("employee", "document_type", "company", "status", "expires_on")
    list_filter = ("company", "document_type__category", "status")
    search_fields = ("employee__employee_number", "document_type__code", "document_type__name")
    autocomplete_fields = ("employee", "document_type")
    readonly_fields = (
        "company",
        "status",
        "submitted_at",
        "verified_at",
        "verified_by",
        "rejected_at",
        "rejected_by",
        "rejection_reason",
        "revoked_at",
        "revoked_by",
        "revocation_reason",
        "superseded_by",
        "created_by",
        "created_at",
        "updated_at",
    )


@admin.register(EmployeeDocumentVersion)
class EmployeeDocumentVersionAdmin(NoDeleteAdmin):
    list_display = (
        "document",
        "version_number",
        "file_extension",
        "file_size",
        "is_current",
        "uploaded_at",
    )
    search_fields = ("document__employee__employee_number", "document__document_type__code")
    readonly_fields = (
        "document",
        "version_number",
        "file",
        "original_filename",
        "stored_filename",
        "file_extension",
        "file_size",
        "mime_type",
        "sha256_hash",
        "uploaded_by",
        "uploaded_at",
        "notes",
        "is_current",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(EmployeeDocumentEvent)
class EmployeeDocumentEventAdmin(NoDeleteAdmin):
    list_display = ("document", "event_type", "from_status", "to_status", "actor", "created_at")
    list_filter = ("event_type", "to_status")
    search_fields = ("document__employee__employee_number", "document__document_type__code")
    readonly_fields = (
        "document",
        "event_type",
        "from_status",
        "to_status",
        "actor",
        "reason",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False
