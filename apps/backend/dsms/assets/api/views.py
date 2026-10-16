from collections.abc import Callable
from decimal import Decimal
from typing import Any, TypeVar, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models as django_models
from django.db.models import Q, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, permissions, response, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied

from dsms.finance import domain_selectors as finance_selectors
from dsms.finance.procurement_models import PurchaseReceiptLine
from dsms.identity import access
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission
from dsms.subscriptions.api.enforcement import TenantModuleViewMixin

from .. import selectors
from ..models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetItem,
    AssetMovement,
    AssetStore,
    ProcurementInventoryHandoff,
    ProcurementInventoryRegistration,
    StockAccount,
)
from ..services import (
    ProcurementRegistrationConflict,
    approve_asset_issue,
    get_stock_balance,
    issue_assets,
    register_procurement_inventory,
    submit_asset_issue,
)
from ..tenant_queries import tenant_consistent_procurement_handoffs
from .serializers import (
    AssetCategorySerializer,
    AssetFinancialSerializer,
    AssetIssueSerializer,
    AssetItemFinancialSerializer,
    AssetItemSerializer,
    AssetMovementSerializer,
    AssetStoreSerializer,
    ProcurementAvailabilitySerializer,
    ProcurementRegistrationCreateSerializer,
    ProcurementRegistrationSerializer,
    StockAccountSerializer,
)

ModelT = TypeVar("ModelT", bound=django_models.Model)


class NoDeleteModelViewSet(TenantModuleViewMixin, viewsets.ModelViewSet[ModelT]):
    required_module_ids = ("asset_management",)
    module_company_lookup = "company_id"
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_scope_permission(self) -> str:
        custom_map: dict[str, str] = getattr(self, "custom_action_permissions", {})
        action = getattr(self, "action", "")
        if action in custom_map:
            return custom_map[action]
        verb = {
            "list": "view",
            "retrieve": "view",
            "create": "add",
            "update": "change",
            "partial_update": "change",
        }.get(action, "view")
        serializer_meta: Any = self.get_serializer_class().Meta  # type: ignore[attr-defined]
        model = serializer_meta.model
        return f"{model._meta.app_label}.{verb}_{model._meta.model_name}"

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {"company": validated_data.get("company")}

    def get_update_scope_kwargs(
        self, validated_data: dict[str, Any], instance: ModelT
    ) -> dict[str, Any]:
        return {"company": validated_data.get("company", getattr(instance, "company", None))}

    def _guard_create_scope(self, validated_data: dict[str, Any]) -> None:
        self.require_modules_for(validated_data.get("company"))
        user = cast(User, self.request.user)
        if not access.has_permission(
            user=user,
            permission=self.get_scope_permission(),
            **self.get_create_scope_kwargs(validated_data),
        ):
            raise PermissionDenied(
                "You do not have permission to create this resource in the requested scope."
            )

    def perform_create(self, serializer: serializers.BaseSerializer[ModelT]) -> None:
        self._guard_create_scope(serializer.validated_data)
        serializer.save()

    def perform_update(self, serializer: serializers.BaseSerializer[ModelT]) -> None:
        instance = cast(ModelT, serializer.instance)
        user = cast(User, self.request.user)
        if not access.has_permission(
            user=user,
            permission=self.get_scope_permission(),
            **self.get_update_scope_kwargs(serializer.validated_data, instance),
        ):
            raise PermissionDenied(
                "You do not have permission to update this resource in the resulting scope."
            )
        serializer.save()


@extend_schema_view(list=extend_schema(tags=["Assets"]), retrieve=extend_schema(tags=["Assets"]))
class AssetCategoryViewSet(NoDeleteModelViewSet[AssetCategory]):
    serializer_class = AssetCategorySerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "category_type", "tracking_method", "is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]

    def get_queryset(self) -> QuerySet[AssetCategory]:
        return selectors.accessible_asset_categories(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )


class AssetItemViewSet(NoDeleteModelViewSet[AssetItem]):
    serializer_class = AssetItemSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "category", "is_active"]
    search_fields = ["item_code", "name", "manufacturer", "model"]

    def get_queryset(self) -> QuerySet[AssetItem]:
        return selectors.accessible_asset_items(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )

    def get_serializer_class(self) -> type[serializers.BaseSerializer[AssetItem]]:
        return AssetItemFinancialSerializer


class AssetStoreViewSet(NoDeleteModelViewSet[AssetStore]):
    serializer_class = AssetStoreSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "branch", "is_active"]

    def get_queryset(self) -> QuerySet[AssetStore]:
        return selectors.accessible_asset_stores(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        branch = validated_data.get("branch")
        operational_zone = validated_data.get("operational_zone")
        branch = branch or getattr(operational_zone, "branch", None)
        return {
            "company": validated_data.get("company"),
            "region": getattr(branch, "region", None),
            "branch": branch,
            "operational_zone": operational_zone,
        }

    def get_update_scope_kwargs(
        self, validated_data: dict[str, Any], instance: AssetStore
    ) -> dict[str, Any]:
        resulting = {
            "company": validated_data.get("company", instance.company),
            "branch": validated_data.get("branch", instance.branch),
            "operational_zone": validated_data.get("operational_zone", instance.operational_zone),
        }
        return self.get_create_scope_kwargs(resulting)


@extend_schema_view(list=extend_schema(tags=["Assets"]), retrieve=extend_schema(tags=["Assets"]))
class AssetViewSet(NoDeleteModelViewSet[Asset]):
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = [
        "company",
        "item",
        "status",
        "condition",
        "current_branch",
        "current_site",
        "current_employee",
    ]
    search_fields = ["asset_number", "serial_number", "barcode_value"]
    ordering_fields = ["asset_number", "acquired_on", "created_at"]
    http_method_names = ["get", "put", "patch", "head", "options"]

    def get_queryset(self) -> QuerySet[Asset]:
        return selectors.accessible_assets(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Asset]]:
        return AssetFinancialSerializer

    def get_update_scope_kwargs(
        self, validated_data: dict[str, Any], instance: Asset
    ) -> dict[str, Any]:
        return selectors.asset_scope_kwargs(instance)


class StockAccountViewSet(TenantModuleViewMixin, viewsets.ReadOnlyModelViewSet[StockAccount]):
    required_module_ids = ("asset_management",)
    module_company_lookup = "company_id"
    serializer_class = StockAccountSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {"balance": "assets.view_stockaccount"}

    def get_scope_permission(self) -> str:
        return "assets.view_stockaccount"

    def get_queryset(self) -> QuerySet[StockAccount]:
        return selectors.accessible_stock_accounts(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )

    @decorators.action(detail=True, methods=["get"])
    def balance(self, request: Any, pk: str | None = None) -> response.Response:
        return response.Response(get_stock_balance(stock_account=self.get_object()))


class AssetIssueViewSet(NoDeleteModelViewSet[AssetIssue]):
    serializer_class = AssetIssueSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "status", "issue_type", "employee", "site", "branch"]
    search_fields = ["issue_number", "purpose"]
    custom_action_permissions = {
        "submit": "assets.change_assetissue",
        "approve": "assets.approve_asset_issue",
        "issue": "assets.issue_asset",
    }

    def get_queryset(self) -> QuerySet[AssetIssue]:
        return selectors.accessible_asset_issues(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )

    def perform_create(self, serializer: serializers.BaseSerializer[AssetIssue]) -> None:
        self._guard_create_scope(serializer.validated_data)
        serializer.save(requested_by=self.request.user)

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        branch = validated_data.get("branch")
        branch = branch or getattr(validated_data.get("site"), "managing_branch", None)
        branch = branch or getattr(validated_data.get("employee"), "branch", None)
        vehicle = validated_data.get("vehicle")
        if vehicle is not None:
            return selectors.asset_scope_kwargs(vehicle)
        return {
            "company": validated_data.get("company"),
            "region": getattr(branch, "region", None),
            "branch": branch,
            "operational_zone": None,
        }

    def get_update_scope_kwargs(
        self, validated_data: dict[str, Any], instance: AssetIssue
    ) -> dict[str, Any]:
        resulting = {
            "company": validated_data.get("company", instance.company),
            "branch": validated_data.get("branch", instance.branch),
            "site": validated_data.get("site", instance.site),
            "employee": validated_data.get("employee", instance.employee),
            "vehicle": validated_data.get("vehicle", instance.vehicle),
        }
        return self.get_create_scope_kwargs(resulting)

    def _workflow(self, function: Callable[..., AssetIssue]) -> response.Response:
        try:
            issue = function(
                issue=self.get_object(),
                **(
                    {"approved_by": self.request.user}
                    if function is approve_asset_issue
                    else {"issued_by": self.request.user}
                    if function is issue_assets
                    else {}
                ),
            )
        except DjangoValidationError as exc:
            return response.Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response(self.get_serializer(issue).data)

    @decorators.action(detail=True, methods=["post"])
    def submit(self, request: Any, pk: str | None = None) -> response.Response:
        return self._workflow(submit_asset_issue)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request: Any, pk: str | None = None) -> response.Response:
        return self._workflow(approve_asset_issue)

    @decorators.action(detail=True, methods=["post"])
    def issue(self, request: Any, pk: str | None = None) -> response.Response:
        return self._workflow(issue_assets)


class AssetMovementViewSet(TenantModuleViewMixin, viewsets.ReadOnlyModelViewSet[AssetMovement]):
    required_module_ids = ("asset_management",)
    module_company_lookup = "stock_account__company_id"
    serializer_class = AssetMovementSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["asset", "movement_type"]

    def get_scope_permission(self) -> str:
        return "assets.view_assetmovement"

    def get_queryset(self) -> QuerySet[AssetMovement]:
        return selectors.accessible_asset_movements(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )


class ProcurementRegistrationViewSet(
    TenantModuleViewMixin, viewsets.ReadOnlyModelViewSet[ProcurementInventoryRegistration]
):
    required_module_ids = ("asset_management",)
    module_company_lookup = "handoff__company_id"
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self) -> list[permissions.BasePermission]:
        classes: list[type[permissions.BasePermission]] = (
            [permissions.IsAuthenticated]
            if self.action == "create"
            or (self.request.method or "").lower() not in self.http_method_names
            else [permissions.IsAuthenticated, HasRBACPermission]
        )
        return [permission() for permission in classes]

    def get_queryset(self) -> QuerySet[ProcurementInventoryRegistration]:
        return selectors.accessible_procurement_registrations(user=cast(User, self.request.user))

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        return (
            ProcurementRegistrationCreateSerializer
            if self.action == "create"
            else ProcurementRegistrationSerializer
        )

    def create(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        incoming = ProcurementRegistrationCreateSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        user = cast(User, request.user)
        source_companies = access.get_accessible_company_ids(
            user, permission="finance.view_purchasereceipt"
        )
        line = get_object_or_404(
            PurchaseReceiptLine.objects.select_related("receipt"),
            pk=data["receipt_line"],
            receipt__company_id__in=source_companies,
        )
        item = get_object_or_404(
            AssetItem.objects.select_related("category").filter(
                Q(company__isnull=True) | Q(company=line.receipt.company)
            ),
            pk=data["asset_item"],
        )
        operation = (
            "assets.register_asset"
            if item.category.tracking_method == "SERIALIZED"
            else "assets.receive_asset_stock"
        )
        if item.category.is_controlled and not access.has_permission(
            user=user, permission="assets.view_controlled_asset", company=line.receipt.company
        ):
            raise Http404
        store = get_object_or_404(
            selectors.accessible_asset_stores(user=user, permission=operation),
            pk=data["destination_store"],
        )
        try:
            registration, replayed = register_procurement_inventory(
                receipt_line=line,
                asset_item=item,
                destination_store=store,
                idempotency_key=data["idempotency_key"],
                actor=user,
                quantity=data.get("quantity"),
                assets=data.get("assets"),
            )
        except PermissionError as exc:
            raise PermissionDenied(str(exc)) from exc
        except ProcurementRegistrationConflict as exc:
            return response.Response({"detail": exc.messages}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return response.Response(
                {"detail": exc.message_dict if hasattr(exc, "message_dict") else exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        output = ProcurementRegistrationSerializer(registration, context={"request": request}).data
        output["replayed"] = replayed
        return response.Response(
            output, status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED
        )


class ProcurementReceiptLineViewSet(
    TenantModuleViewMixin, viewsets.GenericViewSet[PurchaseReceiptLine]
):
    required_module_ids = ("asset_management",)
    module_company_lookup = "purchase_receipt__company_id"
    serializer_class: Any = ProcurementAvailabilitySerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "head", "options"]

    @decorators.action(detail=True, methods=["get"])
    def availability(self, request: Any, pk: str | None = None) -> response.Response:
        user = cast(User, request.user)
        companies = access.get_accessible_company_ids(
            user, permission="finance.view_purchasereceipt"
        )
        line = get_object_or_404(
            PurchaseReceiptLine.objects.select_related("receipt"),
            pk=pk,
            receipt__company_id__in=companies,
        )
        handoff = tenant_consistent_procurement_handoffs(
            ProcurementInventoryHandoff.objects.select_related("asset_item__category").filter(
                receipt_line=line
            )
        ).first()
        if (
            handoff
            and handoff.asset_item.category.is_controlled
            and not access.has_permission(
                user=user, permission="assets.view_controlled_asset", company=handoff.company
            )
        ):
            raise Http404
        totals: dict[str, Any] = (
            selectors.procurement_registration_totals(handoff=handoff)
            if handoff
            else {
                "accepted": line.accepted_quantity,
                "registered": Decimal("0"),
                "remaining": line.accepted_quantity,
            }
        )
        return response.Response(
            {
                "eligible": finance_selectors.is_inventory_registration_eligible(receipt_line=line),
                "asset_item": handoff.asset_item_id if handoff else None,
                "tracking_method": handoff.tracking_method if handoff else None,
                **totals,
            }
        )
