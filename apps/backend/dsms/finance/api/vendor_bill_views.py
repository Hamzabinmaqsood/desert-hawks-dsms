from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import decorators, permissions, response, serializers, status, viewsets
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.permissions import BasePermission

from dsms.identity import access
from dsms.identity.models import User

from ..enums import WorkflowStatus
from ..models import Account
from ..procurement_models import VendorBill, VendorBillLine
from ..vendor_bill_services import (
    ALLOWED_VENDOR_BILL_ACCOUNT_TYPES,
    add_vendor_bill_line,
    delete_vendor_bill_line,
    update_vendor_bill_draft,
    update_vendor_bill_line,
    validate_vendor_bill_header,
)
from .vendor_bill_serializers import (
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
        else:
            code = {
                "create": "finance.add_vendorbill",
                "partial_update": "finance.change_vendorbill",
                "update": "finance.change_vendorbill",
            }.get(view.action, "finance.view_vendorbill")
        return code in access.get_effective_permissions(user)


class VendorBillViewSet(viewsets.ModelViewSet[VendorBill]):
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
        return {
            "create": "finance.add_vendorbill",
            "partial_update": "finance.change_vendorbill",
            "update": "finance.change_vendorbill",
        }.get(self.action, "finance.view_vendorbill")

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self._permission()
        )
        queryset = VendorBill.objects.filter(company_id__in=ids).select_related("vendor")
        if self.action == "retrieve":
            queryset = queryset.prefetch_related("lines__expense_account")
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


class VendorBillExpenseAccountViewSet(viewsets.ReadOnlyModelViewSet[Account]):
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
