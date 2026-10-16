from typing import Any, cast
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import F, Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import decorators, permissions, response, serializers, status, viewsets
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.permissions import BasePermission

from dsms.identity import access
from dsms.identity.models import User
from dsms.subscriptions.api.enforcement import TenantModuleViewMixin

from .. import domain_services
from ..enums import ApprovalDocumentType, WorkflowStatus
from ..exceptions import FinanceError, to_error_dict
from ..models import Account
from ..operations_models import FinanceAttachment
from ..procurement_models import PaymentVoucher, VendorBill, VendorBillLine
from ..vendor_bill_services import (
    ALLOWED_VENDOR_BILL_ACCOUNT_TYPES,
    add_vendor_bill_line,
    delete_vendor_bill_line,
    update_vendor_bill_draft,
    update_vendor_bill_line,
    validate_vendor_bill_header,
)
from .vendor_bill_serializers import (
    VendorBillAttachmentSerializer,
    VendorBillDetailSerializer,
    VendorBillExpenseAccountSerializer,
    VendorBillLineReadSerializer,
    VendorBillLineWriteSerializer,
    VendorBillListSerializer,
    VendorBillWriteSerializer,
)

REFERENCE_PERMISSIONS = (
    "finance.view_vendorbill",
    "finance.add_vendorbill",
    "finance.change_vendorbill",
    "finance.add_vendorbillline",
    "finance.change_vendorbillline",
)


def _errors(exc: DjangoValidationError) -> serializers.ValidationError:
    return serializers.ValidationError(
        exc.message_dict if hasattr(exc, "message_dict") else exc.messages
    )


class VendorBillPermission(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        if view.action == "lines":
            code = "finance.add_vendorbillline"
        elif view.action == "line_detail":
            code = (
                "finance.delete_vendorbillline"
                if request.method == "DELETE"
                else "finance.change_vendorbillline"
            )
        elif view.action in {"attachments", "attachment_download"}:
            code = "finance.manage_finance_attachments"
        elif view.action == "submit":
            code = "finance.change_vendorbill"
        elif view.action in {"approve", "reject"}:
            code = "finance.approve_finance"
        elif view.action == "post":
            code = "finance.post_journal"
        else:
            code = {
                "create": "finance.add_vendorbill",
                "partial_update": "finance.change_vendorbill",
                "update": "finance.change_vendorbill",
            }.get(view.action, "finance.view_vendorbill")
        return code in access.get_effective_permissions(user)


class VendorBillViewSet(TenantModuleViewMixin, viewsets.ModelViewSet[VendorBill]):
    required_module_ids = ("procurement_payables",)
    module_company_lookup = "company_id"
    permission_classes = [permissions.IsAuthenticated, VendorBillPermission]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filterset_fields = ["status", "vendor"]
    search_fields = ["bill_number", "vendor_invoice_number", "vendor__code", "vendor__name"]
    ordering_fields = ["bill_date", "due_date", "total_amount", "created_at"]
    ordering = ["-created_at"]

    def _permission(self) -> str:
        if self.action == "lines":
            return "finance.add_vendorbillline"
        if self.action == "line_detail":
            return (
                "finance.delete_vendorbillline"
                if self.request.method == "DELETE"
                else "finance.change_vendorbillline"
            )
        if self.action in {"attachments", "attachment_download"}:
            return "finance.manage_finance_attachments"
        if self.action == "submit":
            return "finance.change_vendorbill"
        if self.action in {"approve", "reject"}:
            return "finance.approve_finance"
        if self.action == "post":
            return "finance.post_journal"
        return {
            "create": "finance.add_vendorbill",
            "partial_update": "finance.change_vendorbill",
            "update": "finance.change_vendorbill",
        }.get(self.action, "finance.view_vendorbill")

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self._permission()
        )
        queryset = (
            VendorBill.objects.filter(company_id__in=ids, vendor__company_id=F("company_id"))
            .filter(Q(purchase_order__isnull=True) | Q(purchase_order__company_id=F("company_id")))
            .select_related("vendor")
        )
        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                Prefetch(
                    "lines",
                    queryset=(
                        VendorBillLine.objects.filter(
                            expense_account__company_id=F("vendor_bill__company_id")
                        )
                        .filter(
                            Q(purchase_order_line__isnull=True)
                            | Q(
                                purchase_order_line__purchase_order__company_id=F(
                                    "vendor_bill__company_id"
                                )
                            )
                        )
                        .filter(
                            Q(receipt_line__isnull=True)
                            | Q(receipt_line__receipt__company_id=F("vendor_bill__company_id"))
                        )
                        .select_related("expense_account")
                    ),
                ),
                Prefetch(
                    "payment_vouchers",
                    queryset=PaymentVoucher.objects.filter(
                        company_id=F("vendor_bill__company_id")
                    ).order_by("payment_date", "created_at"),
                ),
            )
        return queryset

    def get_serializer_class(self) -> Any:
        if self.action in {"create", "partial_update", "update"}:
            return VendorBillWriteSerializer
        if self.action in {"lines", "line_detail"}:
            return VendorBillLineWriteSerializer
        return VendorBillDetailSerializer if self.action == "retrieve" else VendorBillListSerializer

    def create(self, request: Any) -> response.Response:
        writer = self.get_serializer(data=request.data)
        writer.is_valid(raise_exception=True)
        data = dict(writer.validated_data)
        vendor = data["vendor"]
        if not access.has_permission(
            user=cast(User, request.user),
            permission="finance.add_vendorbill",
            company=vendor.company,
        ):
            raise PermissionDenied
        try:
            validate_vendor_bill_header(
                company_id=vendor.company_id,
                vendor=vendor,
                purchase_order=data.get("purchase_order"),
            )
            with transaction.atomic():
                item = VendorBill.objects.create(
                    company=vendor.company,
                    created_by=request.user,
                    status=WorkflowStatus.DRAFT,
                    subtotal=0,
                    tax_amount=0,
                    total_amount=0,
                    paid_amount=0,
                    **data,
                )
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"vendor_invoice_number": ["This supplier invoice is already recorded."]}
            ) from exc
        except DjangoValidationError as exc:
            raise _errors(exc) from exc
        return response.Response(
            VendorBillDetailSerializer(item).data, status=status.HTTP_201_CREATED
        )

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        raise MethodNotAllowed("DELETE")

    def partial_update(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        item = self.get_object()
        writer = self.get_serializer(item, data=request.data, partial=True)
        writer.is_valid(raise_exception=True)
        try:
            item = update_vendor_bill_draft(bill=item, values=dict(writer.validated_data))
        except (DjangoValidationError, IntegrityError) as exc:
            if isinstance(exc, IntegrityError):
                raise serializers.ValidationError(
                    {"vendor_invoice_number": ["This supplier invoice is already recorded."]}
                ) from exc
            raise _errors(exc) from exc
        return response.Response(VendorBillDetailSerializer(item).data)

    @decorators.action(detail=True, methods=["post"])
    def lines(self, request: Any, pk: Any = None) -> response.Response:
        bill = self.get_object()
        writer = self.get_serializer(data=request.data)
        writer.is_valid(raise_exception=True)
        try:
            line = add_vendor_bill_line(bill=bill, values=dict(writer.validated_data))
        except DjangoValidationError as exc:
            raise _errors(exc) from exc
        return response.Response(VendorBillLineReadSerializer(line).data, status=201)

    @decorators.action(
        detail=True, methods=["patch", "delete"], url_path=r"lines/(?P<line_id>[^/.]+)"
    )
    def line_detail(self, request: Any, pk: Any = None, line_id: Any = None) -> response.Response:
        bill = self.get_object()
        line = get_object_or_404(VendorBillLine.objects.filter(vendor_bill=bill), pk=line_id)
        try:
            if request.method == "DELETE":
                delete_vendor_bill_line(bill=bill, line=line)
                return response.Response(status=204)
            writer = self.get_serializer(data=request.data, partial=True)
            writer.is_valid(raise_exception=True)
            line = update_vendor_bill_line(bill=bill, line=line, values=dict(writer.validated_data))
        except DjangoValidationError as exc:
            raise _errors(exc) from exc
        return response.Response(VendorBillLineReadSerializer(line).data)

    def _workflow_response(self, operation: Any, **kwargs: Any) -> response.Response:
        try:
            item = operation(bill=self.get_object(), actor=cast(User, self.request.user), **kwargs)
        except FinanceError as exc:
            raise serializers.ValidationError(to_error_dict(exc)) from exc
        return response.Response(VendorBillDetailSerializer(item).data)

    @decorators.action(detail=True, methods=["post"])
    def submit(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow_response(domain_services.submit_vendor_bill)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow_response(domain_services.approve_vendor_bill)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow_response(
            domain_services.reject_vendor_bill, reason=str(request.data.get("reason", ""))
        )

    @decorators.action(detail=True, methods=["post"])
    def post(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow_response(domain_services.post_vendor_bill)

    @decorators.action(detail=True, methods=["get", "post"])
    def attachments(self, request: Any, pk: Any = None) -> response.Response:
        bill = self.get_object()
        items = FinanceAttachment.objects.filter(
            company=bill.company,
            document_type=ApprovalDocumentType.VENDOR_BILL,
            object_id=bill.id,
        ).order_by("created_at")
        if request.method == "GET":
            return response.Response(VendorBillAttachmentSerializer(items, many=True).data)
        upload = request.FILES.get("file")
        if upload is None:
            raise serializers.ValidationError({"file": ["Attachment is required."]})
        try:
            item = domain_services.create_finance_attachment(
                company=bill.company,
                document_type=ApprovalDocumentType.VENDOR_BILL,
                object_id=bill.id,
                upload=upload,
                actor=cast(User, request.user),
            )
        except FinanceError as exc:
            raise serializers.ValidationError(to_error_dict(exc)) from exc
        return response.Response(VendorBillAttachmentSerializer(item).data, status=201)

    @extend_schema(parameters=[OpenApiParameter("attachment_id", UUID, OpenApiParameter.PATH)])
    @decorators.action(
        detail=True,
        methods=["get"],
        url_path=r"attachments/(?P<attachment_id>[^/.]+)/download",
    )
    def attachment_download(
        self, request: Any, pk: Any = None, attachment_id: Any = None
    ) -> FileResponse:
        bill = self.get_object()
        item = get_object_or_404(
            FinanceAttachment.objects.filter(
                company=bill.company,
                document_type=ApprovalDocumentType.VENDOR_BILL,
                object_id=bill.id,
            ),
            pk=attachment_id,
        )
        try:
            private_file = item.file.open("rb")
        except OSError as exc:
            raise Http404 from exc
        result = FileResponse(
            private_file,
            as_attachment=True,
            filename=item.original_filename,
            content_type=item.content_type,
        )
        result["Cache-Control"] = "private, no-store"
        result["X-Content-Type-Options"] = "nosniff"
        return result


class VendorBillReferencePermission(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or access.get_effective_permissions(user).intersection(REFERENCE_PERMISSIONS)
            )
        )


class VendorBillExpenseAccountViewSet(
    TenantModuleViewMixin, viewsets.ReadOnlyModelViewSet[Account]
):
    required_module_ids = ("procurement_payables",)
    module_company_lookup = "company_id"
    serializer_class = VendorBillExpenseAccountSerializer
    permission_classes = [permissions.IsAuthenticated, VendorBillReferencePermission]
    pagination_class = None

    def get_queryset(self) -> Any:
        ids: set[Any] = set()
        for permission in REFERENCE_PERMISSIONS:
            ids.update(
                access.get_fully_accessible_company_ids(
                    cast(User, self.request.user), permission=permission
                )
            )
        return Account.objects.filter(
            company_id__in=ids,
            account_type__in=ALLOWED_VENDOR_BILL_ACCOUNT_TYPES,
            is_active=True,
            allow_posting=True,
        ).order_by("company_id", "code")
