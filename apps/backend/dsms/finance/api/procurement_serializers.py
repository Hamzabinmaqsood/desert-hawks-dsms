from decimal import Decimal
from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from dsms.finance.enums import AccountType, WorkflowStatus
from dsms.finance.models import Account
from dsms.finance.procurement_models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
)
from dsms.organization.models import Company

ALLOWED_EXPENSE_TYPES = (AccountType.EXPENSE, AccountType.ASSET)


def _positive(value: Decimal, field: str) -> Decimal:
    if value <= 0:
        raise serializers.ValidationError({field: ["Must be greater than zero."]})
    return value


def _same_company(value: Any, company: Company, field: str) -> None:
    if value is not None and value.company_id != company.id:
        raise serializers.ValidationError({field: ["Must belong to the same company."]})


class RequisitionLineWriteSerializer(serializers.Serializer[dict[str, Any]]):
    description = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
    estimated_unit_price = serializers.DecimalField(max_digits=18, decimal_places=2)
    expense_account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())

    def validate_quantity(self, value: Decimal) -> Decimal:
        return _positive(value, "quantity")

    def validate_estimated_unit_price(self, value: Decimal) -> Decimal:
        if value < 0:
            raise serializers.ValidationError("Cannot be negative.")
        return value


class RequisitionLineReadSerializer(serializers.ModelSerializer[PurchaseRequisitionLine]):
    expense_account_code = serializers.CharField(source="expense_account.code", read_only=True)
    expense_account_name = serializers.CharField(source="expense_account.name", read_only=True)
    estimated_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseRequisitionLine
        fields = (
            "id",
            "description",
            "quantity",
            "estimated_unit_price",
            "estimated_total",
            "expense_account",
            "expense_account_code",
            "expense_account_name",
        )
        read_only_fields = fields


class PurchaseRequisitionReadSerializer(serializers.ModelSerializer[PurchaseRequisition]):
    branch_name = serializers.CharField(source="branch.name", read_only=True, allow_null=True)
    department_name = serializers.CharField(
        source="department.name", read_only=True, allow_null=True
    )
    cost_center_name = serializers.CharField(
        source="cost_center.name", read_only=True, allow_null=True
    )
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    estimated_total = serializers.SerializerMethodField()
    lines = RequisitionLineReadSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseRequisition
        fields = (
            "id",
            "company",
            "branch",
            "branch_name",
            "department",
            "department_name",
            "cost_center",
            "cost_center_name",
            "requisition_number",
            "required_date",
            "purpose",
            "status",
            "created_by",
            "created_by_name",
            "approved_by",
            "approved_by_name",
            "estimated_total",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_created_by_name(self, obj: PurchaseRequisition) -> str:
        return obj.created_by.get_full_name() or obj.created_by.email

    def get_approved_by_name(self, obj: PurchaseRequisition) -> str | None:
        if obj.approved_by is None:
            return None
        return obj.approved_by.get_full_name() or obj.approved_by.email

    def get_estimated_total(self, obj: PurchaseRequisition) -> Decimal:
        return sum((line.estimated_total for line in obj.lines.all()), Decimal("0.00"))


class PurchaseRequisitionWriteSerializer(serializers.ModelSerializer[PurchaseRequisition]):
    lines = RequisitionLineWriteSerializer(many=True)

    class Meta:
        model = PurchaseRequisition
        fields = (
            "company",
            "branch",
            "department",
            "cost_center",
            "requisition_number",
            "required_date",
            "purpose",
            "lines",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        if instance is not None and instance.status != WorkflowStatus.DRAFT:
            raise serializers.ValidationError("Only draft requisitions can be edited.")
        company = cast(Company | None, attrs.get("company", getattr(instance, "company", None)))
        if company is None:
            raise serializers.ValidationError({"company": ["This field is required."]})
        if instance is not None and "company" in attrs and attrs["company"] != instance.company:
            raise serializers.ValidationError({"company": ["Tenant ownership cannot be changed."]})
        for field in ("branch", "department", "cost_center"):
            _same_company(attrs.get(field, getattr(instance, field, None)), company, field)
        lines = attrs.get("lines")
        if lines is None and instance is not None:
            lines = [
                {
                    "expense_account": line.expense_account,
                    "quantity": line.quantity,
                }
                for line in instance.lines.all()
            ]
        for index, line in enumerate(lines or []):
            account = line["expense_account"]
            if (
                account.company_id != company.id
                or not account.is_active
                or not account.allow_posting
                or account.account_type not in ALLOWED_EXPENSE_TYPES
            ):
                raise serializers.ValidationError(
                    {
                        "lines": {
                            str(index): {
                                "expense_account": [
                                    "Select an eligible same-company expense account."
                                ]
                            }
                        }
                    }
                )
        return attrs

    def validate_lines(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> PurchaseRequisition:
        lines = validated_data.pop("lines")
        item = PurchaseRequisition.objects.create(**validated_data)
        PurchaseRequisitionLine.objects.bulk_create(
            [PurchaseRequisitionLine(requisition=item, **line) for line in lines]
        )
        return item

    @transaction.atomic
    def update(
        self, instance: PurchaseRequisition, validated_data: dict[str, Any]
    ) -> PurchaseRequisition:
        lines = validated_data.pop("lines", None)
        if lines is not None:
            if instance.purchase_orders.exists():
                raise serializers.ValidationError(
                    {"lines": ["Lines cannot change after an order is linked."]}
                )
            instance.lines.all().delete()
            PurchaseRequisitionLine.objects.bulk_create(
                [PurchaseRequisitionLine(requisition=instance, **line) for line in lines]
            )
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class OrderLineWriteSerializer(serializers.Serializer[dict[str, Any]]):
    requisition_line = serializers.PrimaryKeyRelatedField(
        queryset=PurchaseRequisitionLine.objects.all()
    )
    description = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = serializers.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    def validate_quantity(self, value: Decimal) -> Decimal:
        return _positive(value, "quantity")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs["unit_price"] < 0 or attrs["tax_amount"] < 0:
            raise serializers.ValidationError("Price and tax cannot be negative.")
        return attrs


class OrderLineReadSerializer(serializers.ModelSerializer[PurchaseOrderLine]):
    requisition_line_description = serializers.CharField(
        source="requisition_line.description", read_only=True
    )
    line_total = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    received_quantity = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderLine
        fields = (
            "id",
            "requisition_line",
            "requisition_line_description",
            "description",
            "quantity",
            "unit_price",
            "tax_amount",
            "line_total",
            "received_quantity",
        )
        read_only_fields = fields

    def get_received_quantity(self, obj: PurchaseOrderLine) -> Decimal:
        return sum(
            (
                line.accepted_quantity
                for line in obj.receipt_lines.all()
                if line.receipt.status == WorkflowStatus.APPROVED
            ),
            Decimal("0.00"),
        )


class PurchaseOrderReadSerializer(serializers.ModelSerializer[PurchaseOrder]):
    requisition_number = serializers.CharField(
        source="requisition.requisition_number", read_only=True
    )
    vendor_code = serializers.CharField(source="vendor.code", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    approved_by_name = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    lines = OrderLineReadSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "company",
            "requisition",
            "requisition_number",
            "vendor",
            "vendor_code",
            "vendor_name",
            "order_number",
            "order_date",
            "status",
            "created_by",
            "created_by_name",
            "approved_by",
            "approved_by_name",
            "total_amount",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_created_by_name(self, obj: PurchaseOrder) -> str:
        return obj.created_by.get_full_name() or obj.created_by.email

    def get_approved_by_name(self, obj: PurchaseOrder) -> str | None:
        if obj.approved_by is None:
            return None
        return obj.approved_by.get_full_name() or obj.approved_by.email

    def get_total_amount(self, obj: PurchaseOrder) -> Decimal:
        return sum((line.line_total for line in obj.lines.all()), Decimal("0.00"))


class PurchaseOrderWriteSerializer(serializers.ModelSerializer[PurchaseOrder]):
    lines = OrderLineWriteSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = ("company", "requisition", "vendor", "order_number", "order_date", "lines")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        if instance is not None and instance.status != WorkflowStatus.DRAFT:
            raise serializers.ValidationError("Only draft purchase orders can be edited.")
        company = cast(Company | None, attrs.get("company", getattr(instance, "company", None)))
        if company is None:
            raise serializers.ValidationError({"company": ["This field is required."]})
        if instance is not None and "company" in attrs and attrs["company"] != instance.company:
            raise serializers.ValidationError({"company": ["Tenant ownership cannot be changed."]})
        requisition = cast(
            PurchaseRequisition | None,
            attrs.get("requisition", getattr(instance, "requisition", None)),
        )
        vendor = attrs.get("vendor", getattr(instance, "vendor", None))
        if requisition is None:
            raise serializers.ValidationError({"requisition": ["This field is required."]})
        if vendor is None:
            raise serializers.ValidationError({"vendor": ["This field is required."]})
        _same_company(requisition, company, "requisition")
        _same_company(vendor, company, "vendor")
        if requisition.status != WorkflowStatus.APPROVED:
            raise serializers.ValidationError(
                {"requisition": ["Only an approved requisition can be ordered."]}
            )
        if not vendor.is_active:
            raise serializers.ValidationError({"vendor": ["Select an active Vendor."]})
        lines = attrs.get("lines")
        if lines is None and instance is not None:
            lines = [
                {"requisition_line": line.requisition_line, "quantity": line.quantity}
                for line in instance.lines.all()
            ]
        seen: set[Any] = set()
        for index, line in enumerate(lines or []):
            source = line["requisition_line"]
            if source.requisition_id != requisition.id:
                raise serializers.ValidationError(
                    {
                        "lines": {
                            str(index): {
                                "requisition_line": ["Must belong to the selected requisition."]
                            }
                        }
                    }
                )
            if source.id in seen:
                raise serializers.ValidationError(
                    {"lines": {str(index): ["Duplicate requisition line."]}}
                )
            seen.add(source.id)
            if line["quantity"] > source.quantity:
                raise serializers.ValidationError(
                    {"lines": {str(index): {"quantity": ["Cannot exceed requested quantity."]}}}
                )
            existing = source.purchase_order_lines.all()
            if instance is not None:
                existing = existing.exclude(purchase_order=instance)
            already_ordered = existing.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if already_ordered + line["quantity"] > source.quantity:
                raise serializers.ValidationError(
                    {
                        "lines": {
                            str(index): {
                                "quantity": ["Cannot exceed the remaining requested quantity."]
                            }
                        }
                    }
                )
        return attrs

    def validate_lines(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> PurchaseOrder:
        lines = validated_data.pop("lines")
        item = PurchaseOrder.objects.create(**validated_data)
        PurchaseOrderLine.objects.bulk_create(
            [PurchaseOrderLine(purchase_order=item, **line) for line in lines]
        )
        return item

    @transaction.atomic
    def update(self, instance: PurchaseOrder, validated_data: dict[str, Any]) -> PurchaseOrder:
        lines = validated_data.pop("lines", None)
        if lines is not None:
            if instance.receipts.exists() or instance.vendor_bills.exists():
                raise serializers.ValidationError(
                    {"lines": ["Lines cannot change after downstream documents exist."]}
                )
            instance.lines.all().delete()
            PurchaseOrderLine.objects.bulk_create(
                [PurchaseOrderLine(purchase_order=instance, **line) for line in lines]
            )
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class ReceiptLineWriteSerializer(serializers.Serializer[dict[str, Any]]):
    purchase_order_line = serializers.PrimaryKeyRelatedField(
        queryset=PurchaseOrderLine.objects.all()
    )
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
    accepted_quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        _positive(attrs["quantity"], "quantity")
        if attrs["accepted_quantity"] < 0 or attrs["accepted_quantity"] > attrs["quantity"]:
            raise serializers.ValidationError(
                {"accepted_quantity": ["Must be between zero and received quantity."]}
            )
        return attrs


class ReceiptLineReadSerializer(serializers.ModelSerializer[PurchaseReceiptLine]):
    description = serializers.CharField(source="purchase_order_line.description", read_only=True)
    ordered_quantity = serializers.DecimalField(
        source="purchase_order_line.quantity", max_digits=18, decimal_places=4, read_only=True
    )

    class Meta:
        model = PurchaseReceiptLine
        fields = (
            "id",
            "purchase_order_line",
            "description",
            "ordered_quantity",
            "quantity",
            "accepted_quantity",
            "notes",
        )
        read_only_fields = fields


class PurchaseReceiptReadSerializer(serializers.ModelSerializer[PurchaseReceipt]):
    purchase_order_number = serializers.CharField(
        source="purchase_order.order_number", read_only=True
    )
    vendor = serializers.UUIDField(source="purchase_order.vendor_id", read_only=True)
    vendor_name = serializers.CharField(source="purchase_order.vendor.name", read_only=True)
    received_by_name = serializers.SerializerMethodField()
    lines = ReceiptLineReadSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseReceipt
        fields = (
            "id",
            "company",
            "purchase_order",
            "purchase_order_number",
            "vendor",
            "vendor_name",
            "receipt_number",
            "receipt_date",
            "receipt_type",
            "status",
            "received_by",
            "received_by_name",
            "lines",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_received_by_name(self, obj: PurchaseReceipt) -> str:
        return obj.received_by.get_full_name() or obj.received_by.email


class PurchaseReceiptWriteSerializer(serializers.ModelSerializer[PurchaseReceipt]):
    lines = ReceiptLineWriteSerializer(many=True)

    class Meta:
        model = PurchaseReceipt
        fields = (
            "company",
            "purchase_order",
            "receipt_number",
            "receipt_date",
            "receipt_type",
            "lines",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        if instance is not None and instance.status != WorkflowStatus.DRAFT:
            raise serializers.ValidationError("Only draft purchase receipts can be edited.")
        company = cast(Company | None, attrs.get("company", getattr(instance, "company", None)))
        if company is None:
            raise serializers.ValidationError({"company": ["This field is required."]})
        if instance is not None and "company" in attrs and attrs["company"] != instance.company:
            raise serializers.ValidationError({"company": ["Tenant ownership cannot be changed."]})
        order = cast(
            PurchaseOrder | None,
            attrs.get("purchase_order", getattr(instance, "purchase_order", None)),
        )
        if order is None:
            raise serializers.ValidationError({"purchase_order": ["This field is required."]})
        _same_company(order, company, "purchase_order")
        if order.status != WorkflowStatus.APPROVED:
            raise serializers.ValidationError(
                {"purchase_order": ["Only an approved purchase order can be received."]}
            )
        lines = attrs.get("lines")
        if lines is None and instance is not None:
            lines = [
                {"purchase_order_line": line.purchase_order_line} for line in instance.lines.all()
            ]
        seen: set[Any] = set()
        for index, line in enumerate(lines or []):
            source = line["purchase_order_line"]
            if source.purchase_order_id != order.id:
                raise serializers.ValidationError(
                    {
                        "lines": {
                            str(index): {
                                "purchase_order_line": [
                                    "Must belong to the selected purchase order."
                                ]
                            }
                        }
                    }
                )
            if source.id in seen:
                raise serializers.ValidationError(
                    {"lines": {str(index): ["Duplicate purchase-order line."]}}
                )
            seen.add(source.id)
            existing = source.receipt_lines.all()
            if instance is not None:
                existing = existing.exclude(receipt=instance)
            already_received = existing.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
            if already_received + line["quantity"] > source.quantity:
                raise serializers.ValidationError(
                    {
                        "lines": {
                            str(index): {
                                "quantity": ["Cannot exceed the remaining order quantity."]
                            }
                        }
                    }
                )
        return attrs

    def validate_lines(self, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not value:
            raise serializers.ValidationError("At least one line is required.")
        return value

    @transaction.atomic
    def create(self, validated_data: dict[str, Any]) -> PurchaseReceipt:
        lines = validated_data.pop("lines")
        item = PurchaseReceipt.objects.create(**validated_data)
        records = [PurchaseReceiptLine(receipt=item, **line) for line in lines]
        for record in records:
            try:
                record.full_clean()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(exc.message_dict) from exc
        PurchaseReceiptLine.objects.bulk_create(records)
        return item

    @transaction.atomic
    def update(self, instance: PurchaseReceipt, validated_data: dict[str, Any]) -> PurchaseReceipt:
        lines = validated_data.pop("lines", None)
        if lines is not None:
            instance.lines.all().delete()
            records = [PurchaseReceiptLine(receipt=instance, **line) for line in lines]
            for record in records:
                try:
                    record.full_clean()
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(exc.message_dict) from exc
            PurchaseReceiptLine.objects.bulk_create(records)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
