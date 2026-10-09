from typing import Any

from rest_framework import serializers

from dsms.organization.business_defaults import (
    normalize_currency_code,
    validate_currency_code,
)

from ..payment_models import (
    PaymentBatch,
    PaymentBeneficiaryProfile,
    PaymentInstruction,
    PaymentProviderConfiguration,
    PaymentProviderSettlement,
    PaymentProviderSettlementLine,
)


class PaymentProviderSerializer(serializers.ModelSerializer[PaymentProviderConfiguration]):
    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if self.instance is None and "currency" not in attrs:
            attrs["currency"] = attrs["company"].default_currency
        if "currency" in attrs:
            attrs["currency"] = normalize_currency_code(attrs["currency"])
            validate_currency_code(attrs["currency"])
        return attrs

    class Meta:
        model = PaymentProviderConfiguration
        exclude = ("secret_reference",)
        read_only_fields = ("id", "created_by", "created_at", "updated_at")


class PaymentBeneficiarySerializer(serializers.ModelSerializer[PaymentBeneficiaryProfile]):
    class Meta:
        model = PaymentBeneficiaryProfile
        exclude = ("destination_encrypted",)
        read_only_fields = (
            "id",
            "destination_masked",
            "status",
            "requested_by",
            "verified_by",
            "approved_by",
            "activated_at",
            "is_active",
            "created_at",
            "updated_at",
        )


class PaymentInstructionSerializer(serializers.ModelSerializer[PaymentInstruction]):
    destination = serializers.CharField(source="beneficiary.destination_masked", read_only=True)

    class Meta:
        model = PaymentInstruction
        fields = "__all__"
        read_only_fields = tuple(field.name for field in PaymentInstruction._meta.fields)


class PaymentBatchSerializer(serializers.ModelSerializer[PaymentBatch]):
    instructions = PaymentInstructionSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentBatch
        fields = "__all__"
        read_only_fields = tuple(field.name for field in PaymentBatch._meta.fields)


class SettlementLineSerializer(serializers.ModelSerializer[PaymentProviderSettlementLine]):
    class Meta:
        model = PaymentProviderSettlementLine
        exclude = ("settlement", "instruction", "status", "exception_code")


class PaymentSettlementSerializer(serializers.ModelSerializer[PaymentProviderSettlement]):
    lines = SettlementLineSerializer(many=True)

    class Meta:
        model = PaymentProviderSettlement
        fields = "__all__"
        read_only_fields = (
            "id",
            "status",
            "imported_by",
            "reconciled_by",
            "accounting_journal",
            "created_at",
            "updated_at",
        )


class PaymentBatchCreateSerializer(serializers.Serializer[Any]):
    provider = serializers.PrimaryKeyRelatedField(
        queryset=PaymentProviderConfiguration.objects.all()
    )
    payroll_run = serializers.UUIDField(required=False)
    vouchers = serializers.ListField(child=serializers.UUIDField(), required=False)


class DestinationRequestSerializer(serializers.Serializer[Any]):
    company = serializers.UUIDField()
    employee = serializers.UUIDField(required=False)
    vendor = serializers.UUIDField(required=False)
    destination = serializers.CharField(write_only=True, trim_whitespace=True)
    account_title = serializers.CharField()
    provider_type = serializers.CharField()
    currency = serializers.CharField(required=False, max_length=3)

    def validate_currency(self, value: str) -> str:
        normalized = normalize_currency_code(value)
        validate_currency_code(normalized)
        return normalized


class ManualPaymentSuccessSerializer(serializers.Serializer[Any]):
    evidence_reference = serializers.CharField(min_length=6, max_length=150)
