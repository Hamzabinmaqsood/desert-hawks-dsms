from rest_framework import serializers

from ..models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetIssueLine,
    AssetItem,
    AssetMovement,
    AssetStore,
    StockAccount,
)


class AssetCategorySerializer(serializers.ModelSerializer[AssetCategory]):
    class Meta:
        model = AssetCategory
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class AssetItemSerializer(serializers.ModelSerializer[AssetItem]):
    class Meta:
        model = AssetItem
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class AssetStoreSerializer(serializers.ModelSerializer[AssetStore]):
    class Meta:
        model = AssetStore
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class AssetSerializer(serializers.ModelSerializer[Asset]):
    class Meta:
        model = Asset
        exclude = ("acquisition_cost",)
        read_only_fields = (
            "id",
            "status",
            "current_custody_type",
            "current_warehouse",
            "current_branch",
            "current_site",
            "current_employee",
            "current_vehicle",
            "retired_on",
            "disposal_date",
            "created_at",
            "updated_at",
        )


class AssetFinancialSerializer(AssetSerializer):
    acquisition_cost = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Asset
        fields = "__all__"
        read_only_fields = AssetSerializer.Meta.read_only_fields


class AssetIssueLineSerializer(serializers.ModelSerializer[AssetIssueLine]):
    class Meta:
        model = AssetIssueLine
        fields = "__all__"
        read_only_fields = ("returned_quantity", "issued_quantity")


class AssetIssueSerializer(serializers.ModelSerializer[AssetIssue]):
    lines = AssetIssueLineSerializer(many=True, read_only=True)

    class Meta:
        model = AssetIssue
        fields = "__all__"
        read_only_fields = (
            "id",
            "requested_by",
            "approved_by",
            "approved_at",
            "issued_by",
            "issued_at",
            "status",
            "created_at",
            "updated_at",
        )


class AssetMovementSerializer(serializers.ModelSerializer[AssetMovement]):
    class Meta:
        model = AssetMovement
        fields = "__all__"


class StockAccountSerializer(serializers.ModelSerializer[StockAccount]):
    class Meta:
        model = StockAccount
        fields = "__all__"
