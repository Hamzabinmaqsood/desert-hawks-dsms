from collections.abc import Callable
from typing import Any, TypeVar, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models as django_models
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, permissions, response, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied

from dsms.identity import access
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission

from .. import selectors
from ..models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetItem,
    AssetMovement,
    AssetStore,
    StockAccount,
)
from ..services import approve_asset_issue, get_stock_balance, issue_assets, submit_asset_issue
from .serializers import (
    AssetCategorySerializer,
    AssetFinancialSerializer,
    AssetIssueSerializer,
    AssetItemFinancialSerializer,
    AssetItemSerializer,
    AssetMovementSerializer,
    AssetStoreSerializer,
    StockAccountSerializer,
)

ModelT = TypeVar("ModelT", bound=django_models.Model)


class NoDeleteModelViewSet(viewsets.ModelViewSet[ModelT]):
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

    def _guard_create_scope(self, validated_data: dict[str, Any]) -> None:
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


class StockAccountViewSet(viewsets.ReadOnlyModelViewSet[StockAccount]):
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


class AssetMovementViewSet(viewsets.ReadOnlyModelViewSet[AssetMovement]):
    serializer_class = AssetMovementSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["asset", "movement_type"]

    def get_scope_permission(self) -> str:
        return "assets.view_assetmovement"

    def get_queryset(self) -> QuerySet[AssetMovement]:
        return selectors.accessible_asset_movements(
            user=cast(User, self.request.user), permission=self.get_scope_permission()
        )
