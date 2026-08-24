from typing import Any

from rest_framework import serializers
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken


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
