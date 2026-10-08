from typing import Any

from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

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


class CompanyContextResponseSerializer(serializers.Serializer[Any]):
    user = UserReadSerializer(read_only=True)
    companies = CompanyContextCompanySerializer(many=True, read_only=True)
    selected_company = CompanyContextCompanySerializer(read_only=True, allow_null=True)
    selection_required = serializers.BooleanField(read_only=True)


class SelectCompanySerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
