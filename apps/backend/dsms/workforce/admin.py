from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import (
    EmergencyContact,
    Employee,
    EmployeeAddress,
    EmployeeAssignmentHistory,
    EmployeeStatusHistory,
)

READONLY_TIMESTAMPS: tuple[str, ...] = ("created_at", "updated_at")
# Lifecycle fields are only ever mutated by the status/assignment services
# (which also write the corresponding history row atomically) -- exposing
# them as editable admin fields would let an admin silently desync the
# Employee row from its own audit trail.
_LIFECYCLE_READONLY = ("employment_status", "exit_date", "is_active")


class NoHardDeleteAdmin(admin.ModelAdmin[Any]):
    """Base admin that disables hard delete for workforce master data."""

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class ReadOnlyLogAdmin(admin.ModelAdmin[Any]):
    """Base admin for immutable history/log rows: viewable only, never editable."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Employee)
class EmployeeAdmin(NoHardDeleteAdmin):
    list_display = (
        "employee_number",
        "display_full_name",
        "company",
        "branch",
        "department",
        "designation",
        "employee_type",
        "employment_status",
        "is_active",
    )
    list_filter = ("company", "branch", "department", "employee_type", "employment_status")
    search_fields = (
        "employee_number",
        "first_name",
        "middle_name",
        "last_name",
        "personal_email",
        "mobile_number",
    )
    ordering = ("company__code", "employee_number")
    autocomplete_fields = ("company", "branch", "department", "designation", "user")
    readonly_fields = (*READONLY_TIMESTAMPS, *_LIFECYCLE_READONLY)

    @admin.display(description="Full name")
    def display_full_name(self, obj: Employee) -> str:
        return obj.full_name

    def get_readonly_fields(
        self, request: HttpRequest, obj: Any = None
    ) -> list[str] | tuple[str, ...]:
        fields: list[str] | tuple[str, ...] = self.readonly_fields
        if obj is not None:
            # The employee number is immutable once assigned; only settable
            # through the create service/form, never edited afterwards.
            fields = (*fields, "employee_number")
        return fields


@admin.register(EmployeeAddress)
class EmployeeAddressAdmin(admin.ModelAdmin[EmployeeAddress]):
    list_display = ("employee", "address_type", "city", "country_code", "is_primary")
    list_filter = ("address_type", "is_primary", "country_code")
    search_fields = (
        "employee__employee_number",
        "employee__first_name",
        "employee__last_name",
        "city",
    )
    autocomplete_fields = ("employee",)
    readonly_fields = READONLY_TIMESTAMPS


@admin.register(EmergencyContact)
class EmergencyContactAdmin(admin.ModelAdmin[EmergencyContact]):
    list_display = ("employee", "name", "relationship", "mobile_number", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("employee__employee_number", "name", "mobile_number")
    autocomplete_fields = ("employee",)
    readonly_fields = READONLY_TIMESTAMPS


@admin.register(EmployeeStatusHistory)
class EmployeeStatusHistoryAdmin(ReadOnlyLogAdmin):
    list_display = ("employee", "previous_status", "new_status", "effective_date", "changed_by")
    list_filter = ("new_status",)
    search_fields = ("employee__employee_number",)
    autocomplete_fields = ("employee", "changed_by")


@admin.register(EmployeeAssignmentHistory)
class EmployeeAssignmentHistoryAdmin(ReadOnlyLogAdmin):
    list_display = (
        "employee",
        "company",
        "branch",
        "department",
        "designation",
        "effective_from",
        "effective_to",
    )
    list_filter = ("company", "branch")
    search_fields = ("employee__employee_number",)
    autocomplete_fields = (
        "employee",
        "company",
        "branch",
        "department",
        "designation",
        "changed_by",
    )
