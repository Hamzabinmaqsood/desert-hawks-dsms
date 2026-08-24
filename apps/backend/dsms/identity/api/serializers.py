"""Transport-layer validation for the identity/RBAC module.

Write serializers validate and normalize incoming payloads; views pass
``validated_data`` into the corresponding service function rather than
calling ``serializer.save()`` directly, so business rules stay in
:mod:`dsms.identity.services`.
"""

from typing import Any

from django.contrib.auth.models import Permission
from rest_framework import serializers

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User, UserRoleAssignment
from dsms.organization.models import Branch, Company, Department, OperationalZone, Region

# --------------------------------------------------------------------------
# User
# --------------------------------------------------------------------------


class UserReadSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "last_login",
            "date_joined",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class UserWriteSerializer(serializers.Serializer[Any]):
    """Used for both create and partial-update.

    ``password`` is only honored on create -- the view rejects it on update
    and points callers to the dedicated set-password action. ``is_staff``
    and ``is_superuser`` are deliberately not exposed here: staff status
    grants Django admin-site access, a separate concern from RBAC, and
    superuser status must never be settable through a normal API.
    """

    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    password = serializers.CharField(required=False, write_only=True, allow_null=True)


class SetPasswordSerializer(serializers.Serializer[Any]):
    password = serializers.CharField(write_only=True)


# --------------------------------------------------------------------------
# Role
# --------------------------------------------------------------------------


class RolePermissionSerializer(serializers.ModelSerializer[Permission]):
    permission_code = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "permission_code"]
        read_only_fields = fields

    def get_permission_code(self, obj: Permission) -> str:
        return f"{obj.content_type.app_label}.{obj.codename}"


class RoleReadSerializer(serializers.ModelSerializer[Role]):
    company_code = serializers.CharField(source="company.code", read_only=True, default=None)
    permissions = RolePermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = [
            "id",
            "company",
            "company_code",
            "code",
            "name",
            "description",
            "is_system",
            "is_active",
            "permissions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class RoleWriteSerializer(serializers.Serializer[Any]):
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), required=False, allow_null=True
    )
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True)
    permissions = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(), many=True, required=False
    )

    def validate_code(self, value: str) -> str:
        return value.strip().upper()


# --------------------------------------------------------------------------
# User role assignment
# --------------------------------------------------------------------------


class UserRoleAssignmentReadSerializer(serializers.ModelSerializer[UserRoleAssignment]):
    user_email = serializers.CharField(source="user.email", read_only=True)
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)
    company_name = serializers.CharField(source="company.legal_name", read_only=True, default=None)
    region_name = serializers.CharField(source="region.name", read_only=True, default=None)
    branch_name = serializers.CharField(source="branch.name", read_only=True, default=None)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    operational_zone_name = serializers.CharField(
        source="operational_zone.name", read_only=True, default=None
    )
    created_by_email = serializers.CharField(
        source="created_by.email", read_only=True, default=None
    )

    class Meta:
        model = UserRoleAssignment
        fields = [
            "id",
            "user",
            "user_email",
            "role",
            "role_code",
            "role_name",
            "scope_type",
            "company",
            "company_name",
            "region",
            "region_name",
            "branch",
            "branch_name",
            "department",
            "department_name",
            "operational_zone",
            "operational_zone_name",
            "starts_at",
            "ends_at",
            "is_active",
            "created_by",
            "created_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class UserRoleAssignmentWriteSerializer(serializers.Serializer[Any]):
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    scope_type = serializers.ChoiceField(choices=AccessScopeType.choices)
    company = serializers.PrimaryKeyRelatedField(
        queryset=Company.objects.all(), required=False, allow_null=True
    )
    region = serializers.PrimaryKeyRelatedField(
        queryset=Region.objects.all(), required=False, allow_null=True
    )
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True
    )
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(), required=False, allow_null=True
    )
    operational_zone = serializers.PrimaryKeyRelatedField(
        queryset=OperationalZone.objects.all(), required=False, allow_null=True
    )
    starts_at = serializers.DateTimeField(required=False, allow_null=True)
    ends_at = serializers.DateTimeField(required=False, allow_null=True)


# --------------------------------------------------------------------------
# Permissions / access matrix (read-only)
# --------------------------------------------------------------------------


class PermissionSerializer(serializers.ModelSerializer[Permission]):
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)
    model = serializers.CharField(source="content_type.model", read_only=True)
    permission_code = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "app_label", "model", "permission_code"]
        read_only_fields = fields

    def get_permission_code(self, obj: Permission) -> str:
        return f"{obj.content_type.app_label}.{obj.codename}"


class AccessMatrixEntrySerializer(serializers.Serializer[Any]):
    role_id = serializers.UUIDField()
    role_code = serializers.CharField()
    role_name = serializers.CharField()
    company_id = serializers.UUIDField(allow_null=True)
    company_code = serializers.CharField(allow_null=True)
    is_system = serializers.BooleanField()
    permissions = serializers.ListField(child=serializers.CharField())
