from typing import Any

from rest_framework import serializers

from ..models import Account
from ..operations_models import FinanceAttachment
from ..procurement_models import PaymentVoucher, VendorBill, VendorBillLine


class VendorBillLineReadSerializer(serializers.ModelSerializer[VendorBillLine]):
    line_total = serializers.DecimalField(max_digits=22, decimal_places=2, read_only=True)
    expense_account_code = serializers.CharField(source="expense_account.code", read_only=True)
    expense_account_name = serializers.CharField(source="expense_account.name", read_only=True)

    class Meta:
        model = VendorBillLine
        fields = (
            "id",
            "purchase_order_line",
            "receipt_line",
            "description",
            "quantity",
            "unit_price",
            "tax_amount",
            "line_total",
            "expense_account",
            "expense_account_code",
            "expense_account_name",
        )


class VendorBillLineWriteSerializer(serializers.ModelSerializer[VendorBillLine]):
    class Meta:
        model = VendorBillLine
        fields = (
            "purchase_order_line",
            "receipt_line",
            "description",
            "quantity",
            "unit_price",
            "tax_amount",
            "expense_account",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        instance = self.instance
        quantity = attrs.get("quantity", getattr(instance, "quantity", None))
        unit_price = attrs.get("unit_price", getattr(instance, "unit_price", None))
        tax_amount = attrs.get("tax_amount", getattr(instance, "tax_amount", 0))
        errors: dict[str, list[str]] = {}
        if quantity is not None and quantity <= 0:
            errors["quantity"] = ["Quantity must be positive."]
        if unit_price is not None and unit_price < 0:
            errors["unit_price"] = ["Unit price cannot be negative."]
        if tax_amount is not None and tax_amount < 0:
            errors["tax_amount"] = ["Tax amount cannot be negative."]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class VendorBillWriteSerializer(serializers.ModelSerializer[VendorBill]):
    class Meta:
        model = VendorBill
        fields = (
            "vendor",
            "purchase_order",
            "vendor_invoice_number",
            "bill_number",
            "bill_date",
            "due_date",
            "match_type",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        bill = self.instance
        bill_date = attrs.get("bill_date", getattr(bill, "bill_date", None))
        due_date = attrs.get("due_date", getattr(bill, "due_date", None))
        if bill_date and due_date and due_date < bill_date:
            raise serializers.ValidationError(
                {"due_date": ["Due date cannot be before the Bill date."]}
            )
        company_id = bill.company_id if bill else attrs["vendor"].company_id
        duplicate = VendorBill.objects.filter(
            company_id=company_id,
            vendor=attrs.get("vendor", getattr(bill, "vendor", None)),
            vendor_invoice_number=attrs.get(
                "vendor_invoice_number", getattr(bill, "vendor_invoice_number", "")
            ),
        )
        if bill:
            duplicate = duplicate.exclude(pk=bill.pk)
        if duplicate.exists():
            raise serializers.ValidationError(
                {"vendor_invoice_number": ["This supplier invoice is already recorded."]}
            )
        return attrs


class VendorBillListSerializer(serializers.ModelSerializer[VendorBill]):
    vendor_code = serializers.CharField(source="vendor.code", read_only=True)
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    outstanding_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = VendorBill
        fields = (
            "id",
            "bill_number",
            "vendor_invoice_number",
            "vendor",
            "vendor_code",
            "vendor_name",
            "bill_date",
            "due_date",
            "status",
            "total_amount",
            "paid_amount",
            "outstanding_amount",
        )


class VendorBillPaymentSerializer(serializers.ModelSerializer[PaymentVoucher]):
    class Meta:
        model = PaymentVoucher
        fields = (
            "id",
            "voucher_number",
            "payment_date",
            "amount",
            "status",
            "payment_status",
            "payment_reference",
        )


class VendorBillDetailSerializer(VendorBillListSerializer):
    lines = VendorBillLineReadSerializer(many=True, read_only=True)
    payments = VendorBillPaymentSerializer(source="payment_vouchers", many=True, read_only=True)

    class Meta:
        model = VendorBill
        fields = VendorBillListSerializer.Meta.fields + (
            "purchase_order",
            "match_type",
            "subtotal",
            "tax_amount",
            "match_exception",
            "created_at",
            "updated_at",
            "lines",
            "payments",
        )


class VendorBillExpenseAccountSerializer(serializers.ModelSerializer[Account]):
    class Meta:
        model = Account
        fields = ("id", "code", "name", "account_type")


class VendorBillAttachmentSerializer(serializers.ModelSerializer[FinanceAttachment]):
    filename = serializers.CharField(source="original_filename", read_only=True)

    class Meta:
        model = FinanceAttachment
        fields = ("id", "filename", "content_type", "size", "created_at")
