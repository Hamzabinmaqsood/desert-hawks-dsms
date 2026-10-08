from typing import Any

from rest_framework import serializers
from rest_framework.request import Request

from dsms.identity import access
from dsms.organization.models import Company
from dsms.workforce.models import Employee

from ..enums import DocumentCategory
from ..models import DocumentType, EmployeeDocument, EmployeeDocumentEvent, EmployeeDocumentVersion


def _can_view_sensitive(context: dict[str, Any], document: EmployeeDocument) -> bool:
    request: Request | None = context.get("request")
    user = getattr(request, "user", None)
    return bool(
        user
        and user.is_authenticated
        and access.has_permission(
            user=user,
            permission="documents.view_sensitive_document_data",
            company=document.company,
            region=document.employee.branch.region if document.employee.branch else None,
            branch=document.employee.branch,
            department=document.employee.department,
        )
    )


class DocumentTypeReadSerializer(serializers.ModelSerializer[DocumentType]):
    class Meta:
        model = DocumentType
        fields = "__all__"


class DocumentTypeWriteSerializer(serializers.Serializer[Any]):
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), required=False, allow_null=True
    )
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)
    category = serializers.ChoiceField(choices=DocumentCategory.choices)
    description = serializers.CharField(required=False, allow_blank=True)
    is_sensitive = serializers.BooleanField(required=False)
    requires_document_number = serializers.BooleanField(required=False)
    requires_issue_date = serializers.BooleanField(required=False)
    requires_expiry_date = serializers.BooleanField(required=False)
    allow_multiple = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(required=False, min_value=0)


class EmployeeDocumentWriteSerializer(serializers.Serializer[Any]):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.all())
    document_type = serializers.PrimaryKeyRelatedField(queryset=DocumentType.objects.all())
    document_number = serializers.CharField(required=False, allow_blank=True, max_length=100)
    issuing_authority = serializers.CharField(required=False, allow_blank=True, max_length=150)
    issue_date = serializers.DateField(required=False, allow_null=True)
    expires_on = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)


class EmployeeDocumentListSerializer(serializers.ModelSerializer[EmployeeDocument]):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    document_type_code = serializers.CharField(source="document_type.code", read_only=True)
    document_type_name = serializers.CharField(source="document_type.name", read_only=True)
    display_document_number = serializers.CharField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    has_file = serializers.BooleanField(read_only=True)

    class Meta:
        model = EmployeeDocument
        fields = [
            "id",
            "employee",
            "employee_number",
            "employee_name",
            "company",
            "document_type",
            "document_type_code",
            "document_type_name",
            "display_document_number",
            "issue_date",
            "expires_on",
            "status",
            "is_expired",
            "has_file",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class EmployeeDocumentDetailSerializer(EmployeeDocumentListSerializer):
    document_number = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()

    class Meta(EmployeeDocumentListSerializer.Meta):
        fields = EmployeeDocumentListSerializer.Meta.fields + [
            "document_number",
            "issuing_authority",
            "notes",
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
        ]

    def get_document_number(self, obj: EmployeeDocument) -> str | None:
        if not obj.document_type.is_sensitive or _can_view_sensitive(self.context, obj):
            return obj.document_number
        return None

    def get_notes(self, obj: EmployeeDocument) -> str | None:
        return obj.notes if _can_view_sensitive(self.context, obj) else None


class DocumentVersionSerializer(serializers.ModelSerializer[EmployeeDocumentVersion]):
    class Meta:
        model = EmployeeDocumentVersion
        fields = [
            "id",
            "document",
            "version_number",
            "original_filename",
            "file_extension",
            "file_size",
            "mime_type",
            "uploaded_by",
            "uploaded_at",
            "notes",
            "is_current",
        ]
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField()
    notes = serializers.CharField(required=False, allow_blank=True)


class DocumentEventSerializer(serializers.ModelSerializer[EmployeeDocumentEvent]):
    class Meta:
        model = EmployeeDocumentEvent
        fields = ["id", "event_type", "from_status", "to_status", "actor", "reason", "created_at"]
        read_only_fields = fields


class ReasonSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(required=False, allow_blank=True)


class RejectSerializer(serializers.Serializer[Any]):
    rejection_reason = serializers.CharField()


class RevokeSerializer(serializers.Serializer[Any]):
    revocation_reason = serializers.CharField()


class SupersedeSerializer(serializers.Serializer[Any]):
    successor = serializers.PrimaryKeyRelatedField(queryset=EmployeeDocument.objects.all())
    reason = serializers.CharField(required=False, allow_blank=True)


class ComplianceSummarySerializer(serializers.Serializer[Any]):
    employee = serializers.UUIDField()
    total_documents = serializers.IntegerField()
    verified_documents = serializers.IntegerField()
    pending_documents = serializers.IntegerField()
    rejected_documents = serializers.IntegerField()
    expired_documents = serializers.IntegerField()
    expiring_documents = serializers.IntegerField()
    missing_required_documents = serializers.ListField(allow_null=True)
    compliance_determined = serializers.BooleanField()
