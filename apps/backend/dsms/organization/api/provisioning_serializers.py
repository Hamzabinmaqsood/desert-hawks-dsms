from typing import Any, cast
from uuid import UUID

from rest_framework import serializers

from dsms.organization.models import Company, TenantProvisioningRequest
from dsms.organization.readiness import (
    CompanyOperationalReadiness,
    get_company_operational_readiness,
)


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
    operational_readiness = serializers.SerializerMethodField()

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
            "operational_readiness",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_operational_readiness(self, obj: TenantProvisioningRequest) -> dict[str, Any] | None:
        if obj.company is None:
            return None
        readiness = get_company_operational_readiness(obj.company)
        return {
            "status": readiness.status,
            "blocker_count": readiness.blocker_count,
            "blocker_codes": [b.code for b in readiness.blockers],
        }


class PlatformTenantDirectorySerializer(serializers.ModelSerializer[Company]):
    """Allowlisted platform metadata; never nests tenant business resources."""

    operational_status = serializers.SerializerMethodField()
    blocker_count = serializers.SerializerMethodField()
    blocker_codes = serializers.SerializerMethodField()

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
            "operational_status",
            "blocker_count",
            "blocker_codes",
            "created_at",
        ]
        read_only_fields = fields

    def _operational_readiness(self, obj: Company) -> CompanyOperationalReadiness:
        cache = cast(
            dict[UUID, CompanyOperationalReadiness] | None,
            getattr(self, "_operational_readiness_cache", None),
        )
        if cache is None:
            cache = {}
            self._operational_readiness_cache = cache
        if obj.pk not in cache:
            cache[obj.pk] = get_company_operational_readiness(obj)
        return cache[obj.pk]

    def get_operational_status(self, obj: Company) -> str:
        return self._operational_readiness(obj).status

    def get_blocker_count(self, obj: Company) -> int:
        return self._operational_readiness(obj).blocker_count

    def get_blocker_codes(self, obj: Company) -> list[str]:
        return [b.code for b in self._operational_readiness(obj).blockers]
