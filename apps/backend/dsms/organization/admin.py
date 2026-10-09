from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
    Region,
)

READONLY_TIMESTAMPS = ("created_at", "updated_at")


class NoHardDeleteAdmin(admin.ModelAdmin[Any]):
    """Base admin that disables hard delete for organization master data."""

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Company)
class CompanyAdmin(NoHardDeleteAdmin):
    list_display = ("code", "legal_name", "trade_name", "country_code", "is_active")
    list_filter = ("is_active", "country_code")
    search_fields = ("code", "legal_name", "trade_name", "registration_number", "tax_number")
    ordering = ("code",)
    readonly_fields = READONLY_TIMESTAMPS
    fieldsets = (
        (None, {"fields": ("code", "legal_name", "trade_name", "is_active")}),
        (
            "Branding",
            {"fields": ("brand_tagline", "brand_primary_color", "brand_accent_color")},
        ),
        (
            "Registration",
            {"fields": ("registration_number", "tax_number")},
        ),
        (
            "Contact",
            {"fields": ("email", "phone", "website")},
        ),
        (
            "Locale",
            {"fields": ("timezone", "default_currency", "country_code")},
        ),
        (
            "Address",
            {
                "fields": (
                    "address_line_1",
                    "address_line_2",
                    "city_name",
                    "province_name",
                    "postal_code",
                )
            },
        ),
        ("Timestamps", {"fields": READONLY_TIMESTAMPS}),
    )


@admin.register(Region)
class RegionAdmin(NoHardDeleteAdmin):
    list_display = ("code", "name", "company", "is_active")
    list_filter = ("is_active", "company")
    search_fields = ("code", "name")
    ordering = ("company__code", "code")
    autocomplete_fields = ("company",)
    readonly_fields = READONLY_TIMESTAMPS


@admin.register(City)
class CityAdmin(NoHardDeleteAdmin):
    list_display = ("code", "name", "company", "region", "province_or_state", "is_active")
    list_filter = ("is_active", "country_code", "company")
    search_fields = ("code", "name", "province_or_state")
    ordering = ("company__code", "code")
    autocomplete_fields = ("company", "region")
    readonly_fields = READONLY_TIMESTAMPS


@admin.register(Branch)
class BranchAdmin(NoHardDeleteAdmin):
    list_display = (
        "code",
        "name",
        "company",
        "region",
        "city",
        "is_head_office",
        "is_active",
    )
    list_filter = ("is_active", "is_head_office", "company")
    search_fields = ("code", "name")
    ordering = ("company__code", "code")
    autocomplete_fields = ("company", "region", "city")
    readonly_fields = READONLY_TIMESTAMPS


@admin.register(Department)
class DepartmentAdmin(NoHardDeleteAdmin):
    list_display = ("code", "name", "company", "scope", "parent", "branch", "is_active")
    list_filter = ("is_active", "scope", "company")
    search_fields = ("code", "name")
    ordering = ("company__code", "sort_order", "code")
    autocomplete_fields = ("company", "parent", "branch")
    readonly_fields = READONLY_TIMESTAMPS


@admin.register(Designation)
class DesignationAdmin(NoHardDeleteAdmin):
    list_display = (
        "code",
        "name",
        "company",
        "department",
        "level",
        "is_supervisory",
        "is_active",
    )
    list_filter = ("is_active", "is_supervisory", "company")
    search_fields = ("code", "name")
    ordering = ("company__code", "sort_order", "code")
    autocomplete_fields = ("company", "department")
    readonly_fields = READONLY_TIMESTAMPS


@admin.register(OperationalZone)
class OperationalZoneAdmin(NoHardDeleteAdmin):
    list_display = ("code", "name", "company", "branch", "is_active")
    list_filter = ("is_active", "company")
    search_fields = ("code", "name")
    ordering = ("branch__code", "code")
    autocomplete_fields = ("company", "branch")
    readonly_fields = READONLY_TIMESTAMPS
