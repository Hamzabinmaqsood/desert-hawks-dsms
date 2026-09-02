from decimal import Decimal
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
    ProcurementInventoryRegistration,
    StockAccount,
)
from ..selectors import asset_scope_kwargs, procurement_registration_totals


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


class ProcurementRegistrationCreateSerializer(serializers.Serializer[dict[str, object]]):
    receipt_line = serializers.UUIDField()
    asset_item = serializers.UUIDField()
    destination_store = serializers.UUIDField()
    idempotency_key = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=18, decimal_places=3, required=False)
    assets = serializers.ListField(child=serializers.DictField(), required=False)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if ("quantity" in attrs) == ("assets" in attrs):
            raise serializers.ValidationError("Provide exactly one of quantity or assets.")
        return attrs


class ProcurementAvailabilitySerializer(serializers.Serializer[dict[str, object]]):
    eligible = serializers.BooleanField(read_only=True)
    asset_item = serializers.UUIDField(read_only=True, allow_null=True)
    tracking_method = serializers.CharField(read_only=True, allow_null=True)
    accepted = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    registered = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)
    remaining = serializers.DecimalField(max_digits=18, decimal_places=4, read_only=True)


class ProcurementRegistrationSerializer(
    serializers.ModelSerializer[ProcurementInventoryRegistration]
):
    receipt_line = serializers.UUIDField(source="handoff.receipt_line_id", read_only=True)
    asset_item = serializers.UUIDField(source="handoff.asset_item_id", read_only=True)
    tracking_method = serializers.CharField(source="handoff.tracking_method", read_only=True)
    accepted = serializers.SerializerMethodField()
    registered = serializers.SerializerMethodField()
    remaining = serializers.SerializerMethodField()
    results = serializers.SerializerMethodField()
    unit_cost_snapshot = serializers.SerializerMethodField()

    class Meta:
        model = ProcurementInventoryRegistration
        fields = (
            "id",
            "registration_number",
            "receipt_line",
            "asset_item",
            "destination_store",
            "tracking_method",
            "accepted",
            "registered",
            "remaining",
            "registered_by",
            "registered_at",
            "results",
            "unit_cost_snapshot",
        )
        read_only_fields = fields

    def _totals(self, obj: ProcurementInventoryRegistration) -> dict[str, Decimal]:
        return procurement_registration_totals(handoff=obj.handoff)

    def get_accepted(self, obj: ProcurementInventoryRegistration) -> object:
        return self._totals(obj)["accepted"]

    def get_registered(self, obj: ProcurementInventoryRegistration) -> object:
        return self._totals(obj)["registered"]

    def get_remaining(self, obj: ProcurementInventoryRegistration) -> object:
        return self._totals(obj)["remaining"]

    def get_results(self, obj: ProcurementInventoryRegistration) -> list[dict[str, object]]:
        return [
            {
                "asset": allocation.asset_id,
                "stock_transaction": allocation.stock_transaction_id,
                "quantity": allocation.quantity,
                "receipt_unit_key": allocation.receipt_unit_key,
            }
            for allocation in obj.allocations.all()
        ]

    def get_unit_cost_snapshot(self, obj: ProcurementInventoryRegistration) -> object:
        request = self.context.get("request")
        store = obj.destination_store
        branch = store.branch or getattr(store.operational_zone, "branch", None)
        if access.has_permission(
            user=getattr(request, "user", None),
            permission="assets.view_asset_financial_values",
            company=obj.company,
            region=getattr(branch, "region", None),
            branch=branch,
            operational_zone=store.operational_zone,
        ):
            return obj.handoff.unit_cost_snapshot
        return None
