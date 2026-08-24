# mypy: disable-error-code="type-arg,no-untyped-def"
from django.contrib import admin

from . import models

for model in [
    models.LeaveType,
    models.LeavePolicy,
    models.LeavePolicyRule,
    models.EmployeeLeavePolicyAssignment,
    models.LeaveEntitlementPeriod,
    models.LeaveBalanceAccount,
    models.LeaveApprovalPolicy,
    models.LeaveApprovalStep,
    models.HolidayCalendar,
    models.Holiday,
]:
    admin.site.register(model)


@admin.register(models.LeaveBalanceTransaction, models.LeaveApprovalAction, models.LeaveEvent)
class ReadOnlyHistoryAdmin(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ("request_number", "employee", "leave_type", "starts_at", "ends_at", "status")
    list_filter = ("status", "leave_type")
    search_fields = ("request_number", "employee__employee_number")
    readonly_fields = (
        "request_number",
        "requested_units",
        "approved_units",
        "status",
        "submitted_at",
        "approved_at",
        "rejected_at",
        "cancelled_at",
        "recalled_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False
