from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.http import HttpRequest

from .models import Role, User, UserRoleAssignment


@admin.register(User)
class DSMSUserAdmin(UserAdmin[User]):
    ordering = ("email",)
    list_display = ("email", "is_staff", "is_active", "is_superuser", "last_login")
    list_filter = ("is_staff", "is_active", "is_superuser")
    search_fields = ("email", "first_name", "last_name")
    readonly_fields = ("created_at", "updated_at", "last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal information",
            {"fields": ("first_name", "last_name")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_active",
                ),
            },
        ),
    )


class NoHardDeleteAdmin(admin.ModelAdmin[Any]):
    """Base admin that disables hard delete for RBAC master data."""

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Role)
class RoleAdmin(NoHardDeleteAdmin):
    list_display = ("code", "name", "company", "is_system", "is_active")
    list_filter = ("is_active", "is_system", "company")
    search_fields = ("code", "name")
    ordering = ("company__code", "code")
    autocomplete_fields = ("company",)
    filter_horizontal = ("permissions",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserRoleAssignment)
class UserRoleAssignmentAdmin(NoHardDeleteAdmin):
    list_display = (
        "user",
        "role",
        "scope_type",
        "company",
        "region",
        "branch",
        "department",
        "operational_zone",
        "is_active",
    )
    list_filter = ("scope_type", "is_active", "company")
    search_fields = ("user__email", "role__code")
    ordering = ("-created_at",)
    autocomplete_fields = (
        "user",
        "role",
        "company",
        "region",
        "branch",
        "department",
        "operational_zone",
        "created_by",
    )
    readonly_fields = ("created_at", "updated_at")
