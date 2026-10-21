from decimal import Decimal
from typing import Any, cast

from django.db import models as django_models
from django.db.models import Q
from rest_framework import serializers

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Company

from ..models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetIssueLine,
    AssetItem,
    AssetMovement,
    AssetReturn,
    AssetReturnLine,
    AssetStore,
    ProcurementInventoryRegistration,
    StockAccount,
)
from ..selectors import asset_scope_kwargs, procurement_registration_totals
from ..tenant_queries import COMPANY_PATHS, GLOBAL_REFERENCES, company_id_for


class TenantSafeAssetSerializer(serializers.ModelSerializer[Any]):
    """Scope writable relations and validate the complete resulting tenant state."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if not isinstance(actor, User) or actor.is_superuser:
            return
        view = self.context.get("view")
        permission = view.get_scope_permission() if view is not None else None
        company_ids = access.get_fully_accessible_company_ids(actor, permission=permission)
        for field in self.fields.values():
            if not isinstance(field, serializers.PrimaryKeyRelatedField) or field.queryset is None:
                continue
            remote = field.queryset.model
            if remote is Company:
                field.queryset = field.queryset.filter(pk__in=company_ids, is_active=True)
                continue
            path = COMPANY_PATHS.get(remote)
            if path is None:
                continue
            condition = Q(**{f"{path}__in": company_ids})
            if remote in GLOBAL_REFERENCES:
                condition |= Q(company__isnull=True)
            field.queryset = field.queryset.filter(condition)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        model = cast(type[django_models.Model], self.Meta.model)
        instance = self.instance
        company = attrs.get("company", getattr(instance, "company", None))
        if instance is not None and "company" in attrs and attrs["company"] != instance.company:
            raise serializers.ValidationError({"company": "Company ownership cannot be changed."})
        company_id = company_id_for(company)
        errors: dict[str, str] = {}
        for model_field in model._meta.fields:
            remote = getattr(getattr(model_field, "remote_field", None), "model", None)
            if model_field.name == "company" or remote not in COMPANY_PATHS:
                continue
            related = attrs.get(model_field.name, getattr(instance, model_field.name, None))
            related_company_id = company_id_for(related)
            if (
                related is not None
                and related_company_id != company_id
                and not (remote in GLOBAL_REFERENCES and related_company_id is None)
            ):
                errors[model_field.name] = "Must belong to the same company."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


ASSET_CATEGORY_FIELDS = (
    "id",
    "company",
    "code",
    "name",
    "category_type",
    "description",
    "tracking_method",
    "is_returnable",
    "is_consumable",
    "requires_approval_for_issue",
    "requires_employee_authorization",
    "requires_serial_number",
    "requires_periodic_inspection",
    "default_inspection_interval_days",
    "requires_maintenance",
    "is_controlled",
    "is_system",
    "is_active",
    "created_at",
    "updated_at",
)

ASSET_ITEM_FIELDS = (
    "id",
    "company",
    "category",
    "item_code",
    "name",
    "description",
    "manufacturer",
    "model",
    "unit_of_measure",
    "reorder_level",
    "reorder_quantity",
    "expected_useful_life_months",
    "is_active",
    "created_at",
    "updated_at",
)


class AssetCategorySerializer(TenantSafeAssetSerializer):
    class Meta:
        model = AssetCategory
        fields = ASSET_CATEGORY_FIELDS
        read_only_fields = ("id", "is_system", "created_at", "updated_at")


class AssetItemSerializer(TenantSafeAssetSerializer):
    class Meta:
        model = AssetItem
        fields = ASSET_ITEM_FIELDS
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)
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
        fields = ASSET_ITEM_FIELDS + ("standard_cost",)
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


class AssetStoreSerializer(TenantSafeAssetSerializer):
    class Meta:
        model = AssetStore
        fields = (
            "id",
            "company",
            "branch",
            "operational_zone",
            "code",
            "name",
            "address",
            "store_manager",
            "is_central_store",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        attrs = super().validate(attrs)
        company = attrs.get("company") or getattr(self.instance, "company", None)
        for field in ("branch", "operational_zone", "store_manager"):
            related = attrs.get(field)
            if related is not None and getattr(related, "company_id", None) != getattr(
                company, "id", None
            ):
                raise serializers.ValidationError({field: "Must belong to the selected company."})
        return attrs


class AssetSerializer(TenantSafeAssetSerializer):
    item_code = serializers.CharField(source="item.item_code", read_only=True)
    item_name = serializers.CharField(source="item.name", read_only=True)
    category_name = serializers.CharField(source="item.category.name", read_only=True)
    current_warehouse_name = serializers.CharField(
        source="current_warehouse.name", read_only=True, allow_null=True
    )
    current_branch_name = serializers.CharField(
        source="current_branch.name", read_only=True, allow_null=True
    )
    current_employee_name = serializers.CharField(
        source="current_employee.full_name", read_only=True, allow_null=True
    )

    class Meta:
        model = Asset
        fields = (
            "id",
            "company",
            "item",
            "item_code",
            "item_name",
            "category_name",
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
            "current_warehouse_name",
            "current_branch",
            "current_branch_name",
            "current_site",
            "current_employee",
            "current_employee_name",
            "current_vehicle",
            "warranty_expires_on",
            "expected_retirement_on",
            "retired_on",
            "disposal_date",
            "notes",
            "created_at",
            "updated_at",
        )
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
        fields = AssetSerializer.Meta.fields + ("acquisition_cost",)
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
        fields = (
            "id",
            "asset_issue",
            "item",
            "serialized_asset",
            "stock_account",
            "requested_quantity",
            "approved_quantity",
            "issued_quantity",
            "returned_quantity",
            "condition_at_issue",
            "notes",
            "created_at",
        )
        read_only_fields = fields


class AssetIssueSerializer(TenantSafeAssetSerializer):
    lines = AssetIssueLineSerializer(many=True, read_only=True)
    employee_name = serializers.CharField(
        source="employee.full_name", read_only=True, allow_null=True
    )
    branch_name = serializers.CharField(source="branch.name", read_only=True, allow_null=True)

    class Meta:
        model = AssetIssue
        fields = (
            "id",
            "issue_number",
            "company",
            "issue_type",
            "employee",
            "employee_name",
            "site",
            "branch",
            "branch_name",
            "vehicle",
            "requested_by",
            "approved_by",
            "approved_at",
            "issued_by",
            "issued_at",
            "expected_return_at",
            "status",
            "purpose",
            "notes",
            "lines",
            "created_at",
            "updated_at",
        )
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
        attrs = super().validate(attrs)
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


class AssetIssueRequestSerializer(serializers.Serializer[dict[str, object]]):
    asset = serializers.UUIDField()
    issue_number = serializers.CharField(max_length=50)
    issue_type = serializers.ChoiceField(
        choices=(
            "TEMPORARY",
            "LONG_TERM",
            "EMPLOYEE_ASSIGNMENT",
        )
    )
    employee = serializers.UUIDField(required=False, allow_null=True)
    branch = serializers.UUIDField(required=False, allow_null=True)
    expected_return_at = serializers.DateTimeField(required=False, allow_null=True)
    purpose = serializers.CharField()
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs: dict[str, object]) -> dict[str, object]:
        if sum(attrs.get(field) is not None for field in ("employee", "branch")) != 1:
            raise serializers.ValidationError("Select exactly one Employee or Branch recipient.")
        return attrs


class AssetReturnRequestSerializer(serializers.Serializer[dict[str, object]]):
    return_number = serializers.CharField(max_length=50)
    return_condition = serializers.ChoiceField(choices=("GOOD", "FAIR", "DAMAGED", "UNSERVICEABLE"))
    returned_at = serializers.DateTimeField()
    damage_notes = serializers.CharField(required=False, allow_blank=True)
    requires_maintenance = serializers.BooleanField(default=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class AssetReturnLineSerializer(serializers.ModelSerializer[AssetReturnLine]):
    asset_number = serializers.CharField(source="serialized_asset.asset_number", read_only=True)

    class Meta:
        model = AssetReturnLine
        fields = (
            "id",
            "serialized_asset",
            "asset_number",
            "quantity",
            "return_condition",
            "damage_notes",
            "requires_maintenance",
            "received_at",
        )
        read_only_fields = fields


class AssetReturnSerializer(serializers.ModelSerializer[AssetReturn]):
    lines = AssetReturnLineSerializer(many=True, read_only=True)

    class Meta:
        model = AssetReturn
        fields = (
            "id",
            "return_number",
            "original_issue",
            "returned_by_employee",
            "received_by",
            "returned_at",
            "status",
            "notes",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class AssetMovementSerializer(serializers.ModelSerializer[AssetMovement]):
    class Meta:
        model = AssetMovement
        fields = (
            "id",
            "asset",
            "movement_type",
            "from_custody_type",
            "from_store",
            "from_branch",
            "from_site",
            "from_employee",
            "to_custody_type",
            "to_store",
            "to_branch",
            "to_site",
            "to_employee",
            "moved_at",
            "issue",
            "return_record",
            "actor",
            "reason",
            "created_at",
        )
        read_only_fields = fields


class StockAccountSerializer(serializers.ModelSerializer[StockAccount]):
    class Meta:
        model = StockAccount
        fields = ("id", "company", "item", "store", "branch", "site", "created_at")
        read_only_fields = fields


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
