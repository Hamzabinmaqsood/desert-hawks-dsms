from rest_framework import serializers

from ..models import Account
from ..procurement_models import PaymentVoucher, VendorBill


class VendorPaymentWriteSerializer(serializers.Serializer[dict[str, object]]):
    vendor_bill = serializers.UUIDField()
    voucher_number = serializers.CharField(max_length=30)
    payment_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    payment_reference = serializers.CharField(max_length=100, allow_blank=True, required=False)

    def validate_amount(self, value):  # type: ignore[no-untyped-def]
        if value <= 0:
            raise serializers.ValidationError("Payment amount must be positive.")
        return value


class VendorPaymentListSerializer(serializers.ModelSerializer[PaymentVoucher]):
    bill_number = serializers.CharField(source="vendor_bill.bill_number", read_only=True)
    vendor_name = serializers.CharField(source="vendor_bill.vendor.name", read_only=True)

    class Meta:
        model = PaymentVoucher
        fields = (
            "id",
            "vendor_bill",
            "bill_number",
            "vendor_name",
            "voucher_number",
            "payment_date",
            "amount",
            "status",
            "payment_status",
            "payment_reference",
        )


class VendorPaymentDetailSerializer(VendorPaymentListSerializer):
    class Meta:
        model = PaymentVoucher
        fields = VendorPaymentListSerializer.Meta.fields + ("created_at", "updated_at")


class PayVendorPaymentSerializer(serializers.Serializer[dict[str, object]]):
    payment_account = serializers.UUIDField()
    payment_reference = serializers.CharField(max_length=100, allow_blank=True, required=False)


class PayableVendorBillSerializer(serializers.ModelSerializer[VendorBill]):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)
    outstanding_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = VendorBill
        fields = (
            "id",
            "bill_number",
            "vendor_invoice_number",
            "vendor_name",
            "total_amount",
            "paid_amount",
            "outstanding_amount",
            "status",
        )


class PaymentAccountSerializer(serializers.ModelSerializer[Account]):
    class Meta:
        model = Account
        fields = ("id", "code", "name", "account_type")
