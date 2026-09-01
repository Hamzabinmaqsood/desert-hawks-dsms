from typing import cast

from rest_framework import serializers

from dsms.identity import access
from dsms.organization.models import Company

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
from ..selectors import asset_scope_kwargs


class AssetCategorySerializer(serializers.ModelSerializer[AssetCategory]):
    class Meta:
        model = AssetCategory
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class AssetItemSerializer(serializers.ModelSerializer[AssetItem]):
    class Meta:
        model = AssetItem
        exclude = ("standard_cost",)
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        company = attrs.get("company") or getattr(self.instance, "company", None)
        category = attrs.get("category") or getattr(self.instance, "category", None)
        category_company_id = getattr(category, "company_id", None)
        if category_company_id is not None and category_company_id != getattr(company, "id", None):
            raise serializers.ValidationError(
                {"category": "Must be global or belong to the selected company."}
            )
        return attrs


class AssetItemFinancialSerializer(AssetItemSerializer):
    standard_cost = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)

    class Meta:
        model = AssetItem
        fields = "__all__"
        read_only_fields = AssetItemSerializer.Meta.read_only_fields

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if "standard_cost" in attrs:
            company = cast(
                Company | None, attrs.get("company") or getattr(self.instance, "company", None)
            )
            request = self.context.get("request")
            if not access.has_permission(
                user=getattr(request, "user", None),
                permission="assets.view_asset_financial_values",
                company=company,
            ):
                raise serializers.ValidationError(
                    {"standard_cost": "Financial-value permission is required."}
                )
        return super().validate(attrs)

    def to_representation(self, instance: AssetItem) -> dict[str, object]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not access.has_permission(
            user=user,
            permission="assets.view_asset_financial_values",
            company=instance.company,
        ):
            data.pop("standard_cost", None)
        return data


class AssetStoreSerializer(serializers.ModelSerializer[AssetStore]):
    class Meta:
        model = AssetStore
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        company = attrs.get("company") or getattr(self.instance, "company", None)
        for field in ("branch", "operational_zone", "store_manager"):
            related = attrs.get(field)
            if related is not None and getattr(related, "company_id", None) != getattr(
                company, "id", None
            ):
                raise serializers.ValidationError({field: "Must belong to the selected company."})
        return attrs


class AssetSerializer(serializers.ModelSerializer[Asset]):
    class Meta:
        model = Asset
        exclude = ("acquisition_cost",)
        read_only_fields = (
            "id",
            "company",
            "item",
            "asset_number",
            "serial_number",
            "manufacturer_serial",
            "barcode_value",
            "qr_identifier",
            "acquired_on",
            "procurement_receipt_reference",
            "purchase_order_reference",
            "status",
            "condition",
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

    def to_representation(self, instance: Asset) -> dict[str, object]:
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not access.has_permission(
            user=user,
            permission="assets.view_asset_financial_values",
            **asset_scope_kwargs(instance),
        ):
            data.pop("acquisition_cost", None)
        return data


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

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if self.instance is not None:
            protected = {
                "issue_number",
                "company",
                "issue_type",
                "employee",
                "site",
                "branch",
                "vehicle",
            }
            attempted = protected.intersection(attrs)
            if attempted:
                raise serializers.ValidationError(
                    {field: "This field is fixed after issue creation." for field in attempted}
                )
        else:
            recipients = ("employee", "site", "branch", "vehicle")
            selected = [field for field in recipients if attrs.get(field) is not None]
            if len(selected) != 1:
                raise serializers.ValidationError("Exactly one issue recipient is required.")
            company = attrs.get("company")
            recipient = attrs[selected[0]]
            if getattr(recipient, "company_id", None) != getattr(company, "id", None):
                raise serializers.ValidationError(
                    {selected[0]: "Must belong to the selected company."}
                )
        return attrs


class AssetMovementSerializer(serializers.ModelSerializer[AssetMovement]):
    class Meta:
        model = AssetMovement
        fields = "__all__"
        read_only_fields = tuple(field.name for field in AssetMovement._meta.fields)


class StockAccountSerializer(serializers.ModelSerializer[StockAccount]):
    class Meta:
        model = StockAccount
        fields = "__all__"
        read_only_fields = tuple(field.name for field in StockAccount._meta.fields)
