from typing import Any, cast

from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from dsms.identity import access
from dsms.organization.business_defaults import (
    normalize_currency_code,
    normalize_document_prefix,
    validate_currency_code,
    validate_timezone_name,
)
from dsms.organization.models import Company

from .serializers import UserReadSerializer


class LoginSerializer(TokenObtainPairSerializer):
    """Email+password login. Normalizes the email before authenticating.

    Inactive users and unknown emails both fail with SimpleJWT's generic
    "no active account found" message, which avoids account enumeration.
    """

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        value = attrs.get(self.username_field)
        if isinstance(value, str):
            attrs[self.username_field] = value.strip().lower()
        return super().validate(attrs)


class TokenPairResponseSerializer(serializers.Serializer[Any]):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)


class TokenRefreshResponseSerializer(serializers.Serializer[Any]):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)


class TokenVerifyResponseSerializer(serializers.Serializer[Any]):
    pass


class LogoutSerializer(serializers.Serializer[Any]):
    refresh = serializers.CharField(write_only=True)

    def save(self, **kwargs: Any) -> None:
        try:
            token = RefreshToken(self.validated_data["refresh"])
            token.blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({"refresh": ["Invalid or expired token."]}) from exc


class PermissionsResponseSerializer(serializers.Serializer[Any]):
    permissions = serializers.ListField(child=serializers.CharField(), read_only=True)


class PlatformCapabilitiesResponseSerializer(serializers.Serializer[Any]):
    capabilities = serializers.ListField(child=serializers.CharField(), read_only=True)
    can_access_platform_admin = serializers.BooleanField(read_only=True)


class AccessScopeAssignmentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    role_code = serializers.CharField()
    role_name = serializers.CharField()
    scope_type = serializers.CharField()
    company_id = serializers.UUIDField(allow_null=True)
    region_id = serializers.UUIDField(allow_null=True)
    branch_id = serializers.UUIDField(allow_null=True)
    department_id = serializers.UUIDField(allow_null=True)
    operational_zone_id = serializers.UUIDField(allow_null=True)


class AccessScopeSummarySerializer(serializers.Serializer[Any]):
    is_superuser = serializers.BooleanField()
    accessible_company_ids = serializers.ListField(child=serializers.UUIDField())
    accessible_region_ids = serializers.ListField(child=serializers.UUIDField())
    accessible_branch_ids = serializers.ListField(child=serializers.UUIDField())
    accessible_department_ids = serializers.ListField(child=serializers.UUIDField())
    accessible_operational_zone_ids = serializers.ListField(child=serializers.UUIDField())
    assignments = AccessScopeAssignmentSerializer(many=True)


class CompanyContextCompanySerializer(serializers.ModelSerializer[Company]):
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = ("id", "code", "display_name", "legal_name", "is_active")
        read_only_fields = fields

    def get_display_name(self, obj: Company) -> str:
        return obj.trade_name or obj.legal_name


class CompanyBrandingSerializer(serializers.Serializer[Any]):
    display_name = serializers.SerializerMethodField()
    tagline = serializers.SerializerMethodField()
    primary_color = serializers.SerializerMethodField()
    accent_color = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    def get_display_name(self, obj: Company) -> str:
        return obj.trade_name or obj.legal_name

    def get_tagline(self, obj: Company) -> str:
        return obj.brand_tagline or "Digital Transformation System"

    def get_primary_color(self, obj: Company) -> str:
        return obj.brand_primary_color or "#174D34"

    def get_accent_color(self, obj: Company) -> str:
        return obj.brand_accent_color or "#D6A84F"

    def get_can_manage(self, obj: Company) -> bool:
        request = self.context.get("request")
        return bool(
            request
            and access.has_permission(
                user=request.user,
                permission="organization.change_company",
                company=obj,
            )
        )


class CompanyBusinessSettingsSerializer(serializers.ModelSerializer[Company]):
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = (
            "default_currency",
            "timezone",
            "invoice_number_prefix",
            "receipt_number_prefix",
            "credit_note_number_prefix",
            "debit_note_number_prefix",
            "can_manage",
        )
        read_only_fields = fields

    def get_can_manage(self, obj: Company) -> bool:
        request = self.context.get("request")
        return bool(
            request
            and access.has_permission(
                user=request.user,
                permission="organization.change_company",
                company=obj,
            )
        )


class SelectedCompanyContextSerializer(CompanyContextCompanySerializer):
    branding = CompanyBrandingSerializer(source="*", read_only=True)

    class Meta:
        model = Company
        fields = ("id", "code", "display_name", "legal_name", "is_active", "branding")
        read_only_fields = fields


class CompanyContextResponseSerializer(serializers.Serializer[Any]):
    user = UserReadSerializer(read_only=True)
    companies = CompanyContextCompanySerializer(many=True, read_only=True)
    selected_company = SelectedCompanyContextSerializer(read_only=True, allow_null=True)
    selection_required = serializers.BooleanField(read_only=True)


class SelectCompanySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()


class CompanyBrandingUpdateSerializer(serializers.Serializer[Any]):
    display_name = serializers.CharField(
        max_length=255, required=False, allow_blank=True, trim_whitespace=True
    )
    tagline = serializers.CharField(
        max_length=160, required=False, allow_blank=True, trim_whitespace=True
    )
    primary_color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$",
        required=False,
        allow_blank=True,
        error_messages={"invalid": "Enter a color in #RRGGBB format."},
    )
    accent_color = serializers.RegexField(
        regex=r"^#[0-9A-Fa-f]{6}$",
        required=False,
        allow_blank=True,
        error_messages={"invalid": "Enter a color in #RRGGBB format."},
    )

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            unsupported = sorted(set(data) - set(self.fields))
            if unsupported:
                raise serializers.ValidationError(
                    {name: ["This field is not supported."] for name in unsupported}
                )
        return cast(dict[str, Any], super().to_internal_value(data))

    def validate_primary_color(self, value: str) -> str:
        return value.upper()

    def validate_accent_color(self, value: str) -> str:
        return value.upper()


class CompanyBusinessSettingsUpdateSerializer(serializers.Serializer[Any]):
    default_currency = serializers.CharField(max_length=3, required=False)
    timezone = serializers.CharField(max_length=64, required=False, trim_whitespace=True)
    invoice_number_prefix = serializers.RegexField(
        regex=r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,8}[A-Za-z0-9])?$", required=False
    )
    receipt_number_prefix = serializers.RegexField(
        regex=r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,8}[A-Za-z0-9])?$", required=False
    )
    credit_note_number_prefix = serializers.RegexField(
        regex=r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,8}[A-Za-z0-9])?$", required=False
    )
    debit_note_number_prefix = serializers.RegexField(
        regex=r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,8}[A-Za-z0-9])?$", required=False
    )

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        if isinstance(data, dict):
            unsupported = sorted(set(data) - set(self.fields))
            if unsupported:
                raise serializers.ValidationError(
                    {name: ["This field is not supported."] for name in unsupported}
                )
        return cast(dict[str, Any], super().to_internal_value(data))

    def validate_default_currency(self, value: str) -> str:
        normalized = normalize_currency_code(value)
        validate_currency_code(normalized)
        return normalized

    def validate_timezone(self, value: str) -> str:
        validate_timezone_name(value)
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        prefix_fields = (
            "invoice_number_prefix",
            "receipt_number_prefix",
            "credit_note_number_prefix",
            "debit_note_number_prefix",
        )
        for name in prefix_fields:
            if name in attrs:
                attrs[name] = normalize_document_prefix(attrs[name])
        company = cast(Company | None, self.context.get("company"))
        if company:
            prefixes = {name: attrs.get(name, getattr(company, name)) for name in prefix_fields}
            duplicate_errors = {
                name: ["Document numbering prefixes must be unique per Company."]
                for name, value in prefixes.items()
                if sum(candidate == value for candidate in prefixes.values()) > 1
            }
            if duplicate_errors:
                raise serializers.ValidationError(duplicate_errors)
        return attrs


class ReadinessItemSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    severity = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    details = serializers.DictField(read_only=True)


class CategoryCheckSerializer(serializers.Serializer[Any]):
    status = serializers.CharField(read_only=True)
    summary = serializers.CharField(read_only=True)
    items = ReadinessItemSerializer(many=True, read_only=True)


class CompanyOperationalReadinessSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField(read_only=True)
    company_code = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    blocker_count = serializers.IntegerField(read_only=True)
    warning_count = serializers.IntegerField(read_only=True)
    blockers = ReadinessItemSerializer(many=True, read_only=True)
    warnings = ReadinessItemSerializer(many=True, read_only=True)
    checks = serializers.DictField(child=CategoryCheckSerializer(), read_only=True)
