from typing import Any, cast

from django.db.models import QuerySet
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.deployment.tenant_queries import consistent_employees
from dsms.identity import access
from dsms.identity.models import User
from dsms.workforce.models import Employee

from .. import selectors, services
from ..exceptions import DocumentError, to_error_dict
from ..models import DocumentType, EmployeeDocument, EmployeeDocumentVersion
from ..permissions import HasDocumentPermission
from ..tenant_queries import scoped_document_types
from .filters import EmployeeDocumentFilter
from .serializers import (
    ComplianceSummarySerializer,
    DocumentEventSerializer,
    DocumentTypeReadSerializer,
    DocumentTypeWriteSerializer,
    DocumentUploadSerializer,
    DocumentVersionSerializer,
    EmployeeDocumentDetailSerializer,
    EmployeeDocumentListSerializer,
    EmployeeDocumentWriteSerializer,
    ReasonSerializer,
    RejectSerializer,
    RevokeSerializer,
    SupersedeSerializer,
)


def call_service(function: Any, **kwargs: Any) -> Any:
    try:
        return function(**kwargs)
    except DocumentError as exc:
        raise ValidationError(to_error_dict(exc)) from exc


class DocumentTypeViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [HasDocumentPermission]
    required_permission = "documents.manage_document_types"
    queryset = DocumentType.objects.none()
    serializer_class = DocumentTypeReadSerializer

    def get_queryset(self) -> QuerySet[DocumentType]:
        return scoped_document_types(
            selectors.document_type_list(),
            user=cast(User, self.request.user),
            permission=self.required_permission,
        )

    def _require_target_scope(self, request: Request, company: Any) -> None:
        user = cast(User, request.user)
        if company is None:
            if not user.is_superuser:
                raise PermissionDenied(
                    "Only platform administrators may manage global document types."
                )
            return
        if not access.has_permission(
            user=user, permission=self.required_permission, company=company
        ):
            raise PermissionDenied(
                "Document type management permission is required in this Company."
            )

    def get_serializer_class(self) -> Any:
        return (
            DocumentTypeWriteSerializer
            if self.action in {"create", "partial_update"}
            else DocumentTypeReadSerializer
        )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._require_target_scope(request, serializer.validated_data.get("company"))
        item = call_service(
            services.create_document_type, actor=request.user, **serializer.validated_data
        )
        return Response(DocumentTypeReadSerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        self._require_target_scope(request, item.company)
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        target_company = serializer.validated_data.get("company", item.company)
        if target_company != item.company:
            raise ValidationError({"company": ["Document type ownership cannot be changed."]})
        self._require_target_scope(request, target_company)
        item = call_service(
            services.update_document_type,
            document_type=item,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(DocumentTypeReadSerializer(item).data)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        self._require_target_scope(request, item.company)
        return Response(
            DocumentTypeReadSerializer(
                call_service(
                    services.activate_document_type,
                    document_type=item,
                    actor=request.user,
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        self._require_target_scope(request, item.company)
        return Response(
            DocumentTypeReadSerializer(
                call_service(
                    services.deactivate_document_type,
                    document_type=item,
                    actor=request.user,
                )
            ).data
        )


@extend_schema_view(
    list=extend_schema(tags=["Employee Documents"]),
    retrieve=extend_schema(tags=["Employee Documents"]),
    create=extend_schema(tags=["Employee Documents"]),
    partial_update=extend_schema(tags=["Employee Documents"]),
)
class EmployeeDocumentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [HasDocumentPermission]
    filterset_class = EmployeeDocumentFilter
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = [
        "employee__employee_number",
        "employee__first_name",
        "employee__last_name",
        "document_type__name",
        "document_type__code",
    ]
    ordering_fields = [
        "created_at",
        "updated_at",
        "issue_date",
        "expires_on",
        "verified_at",
        "document_type__name",
    ]
    ordering = ["-created_at"]
    action_permissions = {
        "list": "documents.view_employeedocument",
        "retrieve": "documents.view_employeedocument",
        "create": "documents.add_employeedocument",
        "partial_update": "documents.change_employeedocument",
        "submit": "documents.change_employeedocument",
        "verify": "documents.verify_employee_document",
        "reject": "documents.verify_employee_document",
        "revoke": "documents.revoke_employee_document",
        "supersede": "documents.change_employeedocument",
        "versions": "documents.view_employeedocumentversion",
        "version_detail": "documents.view_employeedocumentversion",
        "download": "documents.download_employee_document",
        "events": "documents.view_document_audit",
        "expired": "documents.view_employeedocument",
        "expiring": "documents.view_employeedocument",
    }

    def get_queryset(self) -> QuerySet[EmployeeDocument]:
        permission = self.action_permissions.get(self.action, "documents.view_employeedocument")
        return selectors.accessible_documents(cast(User, self.request.user), permission)

    def get_serializer_class(self) -> Any:
        if self.action in {"create", "partial_update"}:
            return EmployeeDocumentWriteSerializer
        if self.action == "list":
            return EmployeeDocumentListSerializer
        return EmployeeDocumentDetailSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        employee = serializer.validated_data["employee"]
        self._require_scope(request, employee, "documents.add_employeedocument")
        item = call_service(
            services.create_employee_document, actor=request.user, **serializer.validated_data
        )
        return Response(
            EmployeeDocumentDetailSerializer(item, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("employee", None)
        data.pop("document_type", None)
        item = call_service(
            services.update_employee_document_metadata, document=item, actor=request.user, **data
        )
        return Response(EmployeeDocumentDetailSerializer(item, context={"request": request}).data)

    def _require_scope(self, request: Request, employee: Employee, permission: str) -> None:
        user = cast(User, request.user)
        if not access.has_permission(
            user=user,
            permission=permission,
            company=employee.company,
            region=employee.branch.region if employee.branch else None,
            branch=employee.branch,
            department=employee.department,
        ):
            raise PermissionDenied("You do not have permission in this employee scope.")

    def _workflow(
        self, request: Request, function: Any, serializer_class: Any, **extra: Any
    ) -> Response:
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = call_service(
            function,
            document=self.get_object(),
            actor=request.user,
            **serializer.validated_data,
            **extra,
        )
        return Response(EmployeeDocumentDetailSerializer(item, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def submit(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._workflow(request, services.submit_employee_document, ReasonSerializer)

    @action(detail=True, methods=["post"])
    def verify(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._workflow(request, services.verify_employee_document, ReasonSerializer)

    @action(detail=True, methods=["post"])
    def reject(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._workflow(request, services.reject_employee_document, RejectSerializer)

    @action(detail=True, methods=["post"])
    def revoke(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._workflow(request, services.revoke_employee_document, RevokeSerializer)

    @action(detail=True, methods=["post"])
    def supersede(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self._workflow(request, services.supersede_employee_document, SupersedeSerializer)

    @extend_schema(methods=["GET"], operation_id="documents_employee_document_versions_list")
    @extend_schema(methods=["POST"], operation_id="documents_employee_document_versions_create")
    @action(detail=True, methods=["get", "post"])
    def versions(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        item = self.get_object()
        if request.method == "POST":
            self._require_scope(request, item.employee, "documents.add_employeedocumentversion")
            serializer = DocumentUploadSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            upload = serializer.validated_data["file"]
            version = call_service(
                services.add_employee_document_version,
                document=item,
                upload=upload,
                original_filename=upload.name,
                actor=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
            return Response(DocumentVersionSerializer(version).data, status=status.HTTP_201_CREATED)
        return Response(
            DocumentVersionSerializer(selectors.document_versions(item), many=True).data
        )

    @extend_schema(operation_id="documents_employee_document_version_retrieve")
    @action(detail=True, methods=["get"], url_path=r"versions/(?P<version_id>[0-9a-f-]+)")
    def version_detail(
        self, request: Request, version_id: str | None = None, *args: Any, **kwargs: Any
    ) -> Response:
        version = get_object_or_404(
            EmployeeDocumentVersion, pk=version_id, document=self.get_object()
        )
        return Response(DocumentVersionSerializer(version).data)

    @action(detail=True, methods=["get"], url_path=r"versions/(?P<version_id>[0-9a-f-]+)/download")
    def download(
        self, request: Request, version_id: str | None = None, *args: Any, **kwargs: Any
    ) -> FileResponse:
        version = get_object_or_404(
            EmployeeDocumentVersion, pk=version_id, document=self.get_object()
        )
        record_audit_event(
            action="DOCUMENT_DOWNLOADED",
            category=AuditCategory.DOCUMENTS,
            severity=AuditSeverity.HIGH,
            summary="Sensitive employee document downloaded.",
            actor_user=request.user,
            company=version.document.employee.company,
            branch=version.document.employee.branch,
            source_object=version.document,
            metadata_safe={"version_number": version.version_number},
            request_context=request,
        )
        response = FileResponse(
            version.file.open("rb"),
            content_type=version.mime_type,
            as_attachment=True,
            filename=version.original_filename,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    @action(detail=True, methods=["get"])
    def events(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            DocumentEventSerializer(selectors.document_events(self.get_object()), many=True).data
        )

    @action(detail=False, methods=["get"])
    def expired(self, request: Request) -> Response:
        return self._paginated(request, selectors.expired_documents(self.get_queryset()))

    @extend_schema(parameters=[OpenApiParameter("days", int, required=False)])
    @action(detail=False, methods=["get"])
    def expiring(self, request: Request) -> Response:
        try:
            days = int(request.query_params.get("days", 30))
        except ValueError as exc:
            raise ValidationError({"days": ["Enter a valid integer."]}) from exc
        if not 1 <= days <= 365:
            raise ValidationError({"days": ["Must be between 1 and 365."]})
        return self._paginated(request, selectors.expiring_documents(days, self.get_queryset()))

    def _paginated(self, request: Request, queryset: Any) -> Response:
        page = self.paginate_queryset(queryset)
        serializer = EmployeeDocumentListSerializer(
            page if page is not None else queryset, many=True
        )
        return (
            self.get_paginated_response(serializer.data)
            if page is not None
            else Response(serializer.data)
        )


class EmployeeDocumentsView(APIView):
    permission_classes = [HasDocumentPermission]
    required_permission = "documents.view_employeedocument"

    @extend_schema(
        tags=["Document Compliance"], responses=EmployeeDocumentListSerializer(many=True)
    )
    def get(self, request: Request, employee_id: str) -> Response:
        employee = get_object_or_404(consistent_employees(Employee.objects.all()), pk=employee_id)
        self._require_employee_scope(request, employee)
        queryset = selectors.accessible_documents(cast(User, request.user)).filter(
            employee=employee
        )
        return Response(EmployeeDocumentListSerializer(queryset, many=True).data)

    def _require_employee_scope(self, request: Request, employee: Employee) -> None:
        if not access.has_permission(
            user=cast(User, request.user),
            permission=self.required_permission,
            company=employee.company,
            region=employee.branch.region if employee.branch else None,
            branch=employee.branch,
            department=employee.department,
        ):
            raise Http404


class ComplianceSummaryView(EmployeeDocumentsView):
    @extend_schema(tags=["Document Compliance"], responses=ComplianceSummarySerializer)
    def get(self, request: Request, employee_id: str) -> Response:
        employee = get_object_or_404(consistent_employees(Employee.objects.all()), pk=employee_id)
        self._require_employee_scope(request, employee)
        queryset = selectors.accessible_documents(cast(User, request.user)).filter(
            employee=employee
        )
        today = __import__("django.utils.timezone", fromlist=["localdate"]).localdate()
        return Response(
            {
                "employee": employee.id,
                "total_documents": queryset.count(),
                "verified_documents": queryset.filter(status="VERIFIED").count(),
                "pending_documents": queryset.filter(status="PENDING_REVIEW").count(),
                "rejected_documents": queryset.filter(status="REJECTED").count(),
                "expired_documents": queryset.filter(expires_on__lt=today).count(),
                "expiring_documents": selectors.expiring_documents(30, queryset).count(),
                "missing_required_documents": None,
                "compliance_determined": False,
            }
        )
