from typing import Any, cast

from django.db.models import Prefetch, QuerySet
from rest_framework import decorators, permissions, response, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission

from dsms.finance import domain_services
from dsms.finance.enums import ApprovalDocumentType
from dsms.finance.exceptions import FinanceError, to_error_dict
from dsms.finance.procurement_models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
)
from dsms.finance.tenant_queries import (
    tenant_consistent_purchase_orders,
    tenant_consistent_purchase_receipts,
    tenant_consistent_purchase_requisitions,
)
from dsms.identity import access
from dsms.identity.models import User
from dsms.subscriptions.api.enforcement import TenantModuleViewMixin

from .procurement_serializers import (
    PurchaseOrderReadSerializer,
    PurchaseOrderWriteSerializer,
    PurchaseReceiptReadSerializer,
    PurchaseReceiptWriteSerializer,
    PurchaseRequisitionReadSerializer,
    PurchaseRequisitionWriteSerializer,
)


class ProcurementPermission(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or view.get_scope_permission() in access.get_effective_permissions(user)
            )
        )


class ProcurementViewSet(TenantModuleViewMixin, viewsets.ModelViewSet[Any]):
    required_module_ids = ("procurement_payables",)
    module_company_lookup = "company_id"
    permission_classes = [permissions.IsAuthenticated, ProcurementPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    model: type[Any]
    read_serializer: type[serializers.BaseSerializer[Any]]
    write_serializer: type[serializers.BaseSerializer[Any]]

    def get_scope_permission(self) -> str:
        model_name = self.model._meta.model_name
        if self.action in {"approve", "reject"}:
            return "finance.approve_finance"
        return {
            "create": f"finance.add_{model_name}",
            "update": f"finance.change_{model_name}",
            "partial_update": f"finance.change_{model_name}",
            "submit": f"finance.change_{model_name}",
            "confirm": f"finance.change_{model_name}",
        }.get(self.action, f"finance.view_{model_name}")

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        return (
            self.write_serializer
            if self.action in {"create", "update", "partial_update"}
            else self.read_serializer
        )

    def perform_create(self, serializer: serializers.BaseSerializer[Any]) -> None:
        company = serializer.validated_data["company"]
        self.require_modules_for(company)
        if not access.has_permission(
            user=cast(User, self.request.user),
            permission=self.get_scope_permission(),
            company=company,
        ):
            raise PermissionDenied("Company-scoped procurement permission required.")
        serializer.save(**self.create_extras())

    def create(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        output = self.read_serializer(serializer.instance, context=self.get_serializer_context())
        return response.Response(output.data, status=status.HTTP_201_CREATED)

    def update(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        output = self.read_serializer(serializer.instance, context=self.get_serializer_context())
        return response.Response(output.data)

    def create_extras(self) -> dict[str, Any]:
        return {"created_by": self.request.user}


class ApprovalWorkflowMixin:
    document_type: str

    def _workflow(self, action: str) -> response.Response:
        view = cast(ProcurementViewSet, self)
        item = view.get_object()
        try:
            if action == "submit":
                item = domain_services.submit_finance_document(
                    obj=item,
                    actor=cast(User, view.request.user),
                    document_type=self.document_type,
                )
            elif action == "approve":
                item = domain_services.approve_finance_document(
                    obj=item,
                    actor=cast(User, view.request.user),
                    document_type=self.document_type,
                )
            elif action == "reject":
                item = domain_services.reject_finance_document(
                    obj=item,
                    actor=cast(User, view.request.user),
                    document_type=self.document_type,
                    reason=str(view.request.data.get("reason", "")),
                )
            else:
                raise serializers.ValidationError({"action": ["Unsupported action."]})
        except FinanceError as exc:
            raise serializers.ValidationError(to_error_dict(exc)) from exc
        return response.Response(
            view.read_serializer(item, context=view.get_serializer_context()).data
        )

    @decorators.action(detail=True, methods=["post"])
    def submit(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow("submit")

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow("approve")

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow("reject")


class PurchaseRequisitionViewSet(ApprovalWorkflowMixin, ProcurementViewSet):
    model = PurchaseRequisition
    read_serializer = PurchaseRequisitionReadSerializer
    write_serializer = PurchaseRequisitionWriteSerializer
    document_type = ApprovalDocumentType.PURCHASE_REQUISITION
    filterset_fields = ["company", "status", "branch", "department", "cost_center"]
    search_fields = ["requisition_number", "purpose"]
    ordering_fields = ["required_date", "created_at", "requisition_number"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[PurchaseRequisition]:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self.get_scope_permission()
        )
        lines = PurchaseRequisitionLine.objects.select_related("expense_account").order_by("pk")
        return cast(
            QuerySet[PurchaseRequisition],
            tenant_consistent_purchase_requisitions(
                PurchaseRequisition.objects.filter(company_id__in=ids)
                .select_related("branch", "department", "cost_center", "created_by", "approved_by")
                .prefetch_related(Prefetch("lines", queryset=lines))
            ),
        )


class PurchaseOrderViewSet(ApprovalWorkflowMixin, ProcurementViewSet):
    model = PurchaseOrder
    read_serializer = PurchaseOrderReadSerializer
    write_serializer = PurchaseOrderWriteSerializer
    document_type = ApprovalDocumentType.PURCHASE_ORDER
    filterset_fields = ["company", "status", "vendor", "requisition"]
    search_fields = [
        "order_number",
        "vendor__code",
        "vendor__name",
        "requisition__requisition_number",
    ]
    ordering_fields = ["order_date", "created_at", "order_number"]
    ordering = ["-created_at"]

    def get_queryset(self) -> QuerySet[PurchaseOrder]:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self.get_scope_permission()
        )
        receipt_lines = PurchaseReceiptLine.objects.select_related("receipt")
        lines = PurchaseOrderLine.objects.select_related("requisition_line").prefetch_related(
            Prefetch("receipt_lines", queryset=receipt_lines)
        )
        return cast(
            QuerySet[PurchaseOrder],
            tenant_consistent_purchase_orders(
                PurchaseOrder.objects.filter(company_id__in=ids)
                .select_related("requisition", "vendor", "created_by", "approved_by")
                .prefetch_related(Prefetch("lines", queryset=lines))
            ),
        )


class PurchaseReceiptViewSet(ProcurementViewSet):
    model = PurchaseReceipt
    read_serializer = PurchaseReceiptReadSerializer
    write_serializer = PurchaseReceiptWriteSerializer
    filterset_fields = ["company", "status", "receipt_type", "purchase_order"]
    search_fields = [
        "receipt_number",
        "purchase_order__order_number",
        "purchase_order__vendor__name",
    ]
    ordering_fields = ["receipt_date", "created_at", "receipt_number"]
    ordering = ["-created_at"]

    def create_extras(self) -> dict[str, Any]:
        return {"received_by": self.request.user}

    def get_queryset(self) -> QuerySet[PurchaseReceipt]:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self.get_scope_permission()
        )
        lines = PurchaseReceiptLine.objects.select_related("purchase_order_line").order_by("pk")
        return cast(
            QuerySet[PurchaseReceipt],
            tenant_consistent_purchase_receipts(
                PurchaseReceipt.objects.filter(company_id__in=ids)
                .select_related("purchase_order__vendor", "received_by")
                .prefetch_related(Prefetch("lines", queryset=lines))
            ),
        )

    @decorators.action(detail=True, methods=["post"])
    def confirm(self, request: Any, pk: Any = None) -> response.Response:
        item = self.get_object()
        try:
            item = domain_services.confirm_receipt(receipt=item)
        except FinanceError as exc:
            raise serializers.ValidationError(to_error_dict(exc)) from exc
        return response.Response(
            self.read_serializer(item, context=self.get_serializer_context()).data
        )
