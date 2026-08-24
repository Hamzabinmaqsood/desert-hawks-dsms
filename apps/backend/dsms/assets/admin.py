from django.contrib import admin
from django.http import HttpRequest

from .models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetItem,
    AssetMovement,
    AssetStore,
    StockAccount,
    StockTransaction,
)


@admin.register(AssetCategory, AssetItem, AssetStore)
class ReferenceAdmin(admin.ModelAdmin[AssetCategory]):
    list_display = ("id", "name", "is_active")
    search_fields = ("name",)


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin[Asset]):
    list_display = ("asset_number", "item", "status", "condition", "current_custody_type")
    list_filter = ("status", "condition", "current_custody_type")
    search_fields = ("asset_number", "serial_number")
    readonly_fields = (
        "status",
        "current_custody_type",
        "current_warehouse",
        "current_branch",
        "current_site",
        "current_employee",
        "current_vehicle",
    )


@admin.register(AssetMovement, StockTransaction)
class ImmutableLedgerAdmin(admin.ModelAdmin[AssetMovement]):
    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False


admin.site.register([AssetIssue, StockAccount])
