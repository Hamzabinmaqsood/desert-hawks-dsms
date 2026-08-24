import django_filters as filters
from django.contrib.auth.models import Permission

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User, UserRoleAssignment


class UserFilterSet(filters.FilterSet):  # type: ignore[misc]
    is_active = filters.BooleanFilter(field_name="is_active")
    is_staff = filters.BooleanFilter(field_name="is_staff")

    class Meta:
        model = User
        fields = ["is_active", "is_staff"]


class RoleFilterSet(filters.FilterSet):  # type: ignore[misc]
    company = filters.UUIDFilter(field_name="company_id")
    is_system = filters.BooleanFilter(field_name="is_system")
    is_active = filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = Role
        fields = ["company", "is_system", "is_active"]


class UserRoleAssignmentFilterSet(filters.FilterSet):  # type: ignore[misc]
    user = filters.UUIDFilter(field_name="user_id")
    role = filters.UUIDFilter(field_name="role_id")
    company = filters.UUIDFilter(field_name="company_id")
    scope_type = filters.ChoiceFilter(field_name="scope_type", choices=AccessScopeType.choices)
    is_active = filters.BooleanFilter(field_name="is_active")

    class Meta:
        model = UserRoleAssignment
        fields = ["user", "role", "company", "scope_type", "is_active"]


class PermissionFilterSet(filters.FilterSet):  # type: ignore[misc]
    app_label = filters.CharFilter(field_name="content_type__app_label")
    model = filters.CharFilter(field_name="content_type__model")

    class Meta:
        model = Permission
        fields = ["app_label", "model"]
