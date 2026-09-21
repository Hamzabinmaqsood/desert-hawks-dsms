"""Transport-layer validation for the identity/RBAC module.

Write serializers validate and normalize incoming payloads; views pass
``validated_data`` into the corresponding service function rather than
calling ``serializer.save()`` directly, so business rules stay in
:mod:`dsms.identity.services`.
"""

from typing import Any

from django.contrib.auth.models import Permission
from django.db.models import Q
from rest_framework import serializers

from dsms.identity import access, selectors
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not isinstance(user, User) or user.is_superuser:
            return
        company_field: Any = self.fields["company"]
        company_field.queryset = Company.objects.filter(
            id__in=access.get_fully_accessible_company_ids(
                user, permission="identity.manage_roles"
            ),
            is_active=True,
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if (
            self.instance is not None
            and "company" in attrs
            and attrs["company"] != self.instance.company
        ):
            raise serializers.ValidationError(
                {"company": "Role company cannot be changed after creation."}
            )
        return attrs

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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if not isinstance(actor, User) or actor.is_superuser:
            return
        permission = "identity.assign_roles"
        company_ids = access.get_accessible_company_ids(actor, permission=permission)
        company_field: Any = self.fields["company"]
        company_field.queryset = Company.objects.filter(id__in=company_ids, is_active=True)
        region_field: Any = self.fields["region"]
        region_field.queryset = Region.objects.filter(
            id__in=access.get_accessible_region_ids(actor, permission=permission),
            company__is_active=True,
        )
        branch_field: Any = self.fields["branch"]
        branch_field.queryset = Branch.objects.filter(
            id__in=access.get_accessible_branch_ids(actor, permission=permission),
            company__is_active=True,
        )
        department_field: Any = self.fields["department"]
        department_field.queryset = Department.objects.filter(
            id__in=access.get_accessible_department_ids(actor, permission=permission),
            company__is_active=True,
        )
        zone_field: Any = self.fields["operational_zone"]
        zone_field.queryset = OperationalZone.objects.filter(
            id__in=access.get_accessible_operational_zone_ids(actor, permission=permission),
            company__is_active=True,
        )
        role_field: Any = self.fields["role"]
        role_field.queryset = Role.objects.filter(
            Q(company__isnull=True) | Q(company_id__in=company_ids), is_active=True
        )
        visible_users = selectors.get_accessible_users(actor=actor, permission=permission)
        user_field: Any = self.fields["user"]
        user_field.queryset = User.objects.filter(
            Q(pk__in=visible_users.values("pk")) | Q(role_assignments__isnull=True), is_active=True
        ).distinct()


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
