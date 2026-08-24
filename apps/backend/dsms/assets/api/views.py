from collections.abc import Callable
from typing import Any, TypeVar

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models as django_models
from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import decorators, permissions, response, serializers, status, viewsets

from dsms.identity.permissions import HasRBACPermission

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
    AssetItemSerializer,
    AssetMovementSerializer,
    AssetSerializer,
    AssetStoreSerializer,
    StockAccountSerializer,
)

ModelT = TypeVar("ModelT", bound=django_models.Model)


class NoDeleteModelViewSet(viewsets.ModelViewSet[ModelT]):
    http_method_names = ["get", "post", "put", "patch", "head", "options"]


@extend_schema_view(list=extend_schema(tags=["Assets"]), retrieve=extend_schema(tags=["Assets"]))
class AssetCategoryViewSet(NoDeleteModelViewSet[AssetCategory]):
    serializer_class = AssetCategorySerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "category_type", "tracking_method", "is_active"]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at"]

    def get_queryset(self) -> QuerySet[AssetCategory]:
        return AssetCategory.objects.all().select_related("company")


class AssetItemViewSet(NoDeleteModelViewSet[AssetItem]):
    serializer_class = AssetItemSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "category", "is_active"]
    search_fields = ["item_code", "name", "manufacturer", "model"]

    def get_queryset(self) -> QuerySet[AssetItem]:
        return AssetItem.objects.select_related("company", "category")


class AssetStoreViewSet(NoDeleteModelViewSet[AssetStore]):
    serializer_class = AssetStoreSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "branch", "is_active"]

    def get_queryset(self) -> QuerySet[AssetStore]:
        return AssetStore.objects.select_related("company", "branch", "store_manager")


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

    def get_queryset(self) -> QuerySet[Asset]:
        qs = Asset.objects.select_related(
            "company",
            "item__category",
            "current_warehouse",
            "current_branch",
            "current_site",
            "current_employee",
        )
        if not self.request.user.has_perm("assets.view_controlled_asset"):
            qs = qs.filter(item__category__is_controlled=False)
        return qs

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Asset]]:
        return (
            AssetFinancialSerializer
            if self.request.user.has_perm("assets.view_asset_financial_values")
            else AssetSerializer
        )


class StockAccountViewSet(viewsets.ReadOnlyModelViewSet[StockAccount]):
    serializer_class = StockAccountSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    queryset = StockAccount.objects.select_related("company", "item", "store", "branch", "site")

    @decorators.action(detail=True, methods=["get"])
    def balance(self, request: Any, pk: str | None = None) -> response.Response:
        return response.Response(get_stock_balance(stock_account=self.get_object()))


class AssetIssueViewSet(NoDeleteModelViewSet[AssetIssue]):
    serializer_class = AssetIssueSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "status", "issue_type", "employee", "site", "branch"]
    search_fields = ["issue_number", "purpose"]

    def get_queryset(self) -> QuerySet[AssetIssue]:
        return AssetIssue.objects.select_related(
            "company", "employee", "site", "branch", "requested_by", "approved_by", "issued_by"
        ).prefetch_related("lines__item")

    def perform_create(self, serializer: serializers.BaseSerializer[AssetIssue]) -> None:
        serializer.save(requested_by=self.request.user)

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
    queryset = AssetMovement.objects.select_related(
        "asset", "actor", "from_store", "to_store"
    ).order_by("-moved_at")
    filterset_fields = ["asset", "movement_type"]
