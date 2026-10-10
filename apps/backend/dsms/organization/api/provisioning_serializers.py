from typing import Any

from rest_framework import serializers

from dsms.organization.models import Company, TenantProvisioningRequest


class ProvisioningCompanyInputSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=20)
    legal_name = serializers.CharField(max_length=255)
    trade_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    registration_number = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    tax_number = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    country_code = serializers.CharField(max_length=2)
    timezone = serializers.CharField(max_length=64)
    default_currency = serializers.CharField(max_length=3)
    brand_tagline = serializers.CharField(max_length=160, required=False, allow_blank=True)
    brand_primary_color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$", required=False, allow_blank=True
    )
    brand_accent_color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$", required=False, allow_blank=True
    )
    invoice_number_prefix = serializers.CharField(max_length=10, required=False, default="INV")
    receipt_number_prefix = serializers.CharField(max_length=10, required=False, default="RCPT")
    credit_note_number_prefix = serializers.CharField(max_length=10, required=False, default="CN")
    debit_note_number_prefix = serializers.CharField(max_length=10, required=False, default="DN")


class ProvisioningAdminInputSerializer(serializers.Serializer[Any]):
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)


class TenantProvisioningInputSerializer(serializers.Serializer[Any]):
    idempotency_key = serializers.UUIDField()
    company = ProvisioningCompanyInputSerializer()
    initial_admin = ProvisioningAdminInputSerializer()


class ProvisioningCompanyResultSerializer(serializers.ModelSerializer[Company]):
    class Meta:
        model = Company
        fields = [
            "id",
            "code",
            "legal_name",
            "trade_name",
            "registration_number",
            "tax_number",
            "country_code",
            "timezone",
            "default_currency",
            "brand_tagline",
            "brand_primary_color",
            "brand_accent_color",
            "invoice_number_prefix",
            "receipt_number_prefix",
            "credit_note_number_prefix",
            "debit_note_number_prefix",
            "is_active",
        ]
        read_only_fields = fields


class ProvisioningAdminResultSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    first_name = serializers.CharField(read_only=True)
    last_name = serializers.CharField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    is_staff = serializers.BooleanField(read_only=True)
    is_superuser = serializers.BooleanField(read_only=True)


class TenantProvisioningResultSerializer(serializers.ModelSerializer[TenantProvisioningRequest]):
    company = ProvisioningCompanyResultSerializer(read_only=True)
    initial_admin = ProvisioningAdminResultSerializer(read_only=True)

    class Meta:
        model = TenantProvisioningRequest
        fields = [
            "id",
            "idempotency_key",
            "status",
            "company",
            "initial_admin",
            "attempt_count",
            "failure_code",
            "failure_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PlatformTenantDirectorySerializer(serializers.ModelSerializer[Company]):
    """Allowlisted platform metadata; never nests tenant business resources."""

    class Meta:
        model = Company
        fields = [
            "id",
            "code",
            "legal_name",
            "trade_name",
            "is_active",
            "country_code",
            "timezone",
            "default_currency",
            "created_at",
        ]
        read_only_fields = fields
