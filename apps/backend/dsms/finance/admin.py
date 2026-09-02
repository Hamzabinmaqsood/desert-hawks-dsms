from typing import Any

from django.apps import apps
from django.contrib import admin
from django.http import HttpRequest

from .enums import JournalStatus
from .models import (
    Account,
    AccountingPeriod,
    CostCenter,
    FinanceEvent,
    FiscalYear,
    JournalEntry,
    JournalLine,
)
from .procurement_models import PurchaseReceiptLine


class NoDeleteAdmin(admin.ModelAdmin[Any]):
    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Account)
class AccountAdmin(NoDeleteAdmin):
    list_display = ("code", "name", "company", "account_type", "allow_posting", "is_active")
    list_filter = ("company", "account_type", "is_active")
    search_fields = ("code", "name")
    autocomplete_fields = ("company", "parent")


@admin.register(FiscalYear)
class FiscalYearAdmin(NoDeleteAdmin):
    list_display = ("name", "company", "start_date", "end_date", "is_closed")
    list_filter = ("company", "is_closed")


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(NoDeleteAdmin):
    list_display = ("name", "company", "start_date", "end_date", "status")
    list_filter = ("company", "status")
    readonly_fields = ("status", "created_at", "updated_at")


@admin.register(CostCenter)
class CostCenterAdmin(NoDeleteAdmin):
    list_display = ("code", "name", "company", "branch", "department", "is_active")
    list_filter = ("company", "branch", "department", "is_active")


class JournalLineInline(admin.TabularInline[JournalLine, JournalEntry]):
    model = JournalLine
    extra = 0
    readonly_fields = ("account", "cost_center", "description", "debit", "credit", "created_at")

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return bool(obj and obj.status == JournalStatus.DRAFT)

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(JournalEntry)
class JournalEntryAdmin(NoDeleteAdmin):
    list_display = ("journal_number", "company", "entry_date", "status", "created_by", "posted_at")
    list_filter = ("company", "status", "accounting_period")
    search_fields = ("journal_number", "reference", "description")
    readonly_fields = (
        "journal_number",
        "status",
        "submitted_by",
        "submitted_at",
        "approved_by",
        "approved_at",
        "posted_by",
        "posted_at",
        "reversed_by_entry",
        "created_at",
        "updated_at",
    )
    inlines = (JournalLineInline,)

    def has_change_permission(self, request: HttpRequest, obj: JournalEntry | None = None) -> bool:
        return bool(
            super().has_change_permission(request, obj)
            and (obj is None or obj.status == JournalStatus.DRAFT)
        )


@admin.register(FinanceEvent)
class FinanceEventAdmin(NoDeleteAdmin):
    list_display = (
        "event_type",
        "company",
        "journal_entry",
        "accounting_period",
        "actor",
        "created_at",
    )
    readonly_fields = (
        "company",
        "journal_entry",
        "accounting_period",
        "event_type",
        "actor",
        "reason",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


class ProtectedFinanceAdmin(NoDeleteAdmin):
    """Fallback registration that keeps lifecycle records service-controlled."""

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        always_sensitive = {
            "account_number_encrypted",
            "iban_encrypted",
            "bank_details_encrypted",
            "journal_entry",
            "approved_by",
            "paid_amount",
            "recovered_amount",
        }
        protected_statuses = {
            "APPROVED",
            "POSTED",
            "PARTIALLY_PAID",
            "PAID",
            "CLOSED",
            "MATCHED",
        }
        names = {field.name for field in self.model._meta.fields}
        readonly = names & always_sensitive
        if isinstance(obj, PurchaseReceiptLine) and obj.receipt.status == "APPROVED":
            return tuple(sorted(names))
        if obj is not None and getattr(obj, "status", None) in protected_statuses:
            readonly = names
        return tuple(sorted(readonly))


for finance_model in apps.get_app_config("finance").get_models():
    if finance_model not in admin.site._registry:
        admin.site.register(finance_model, ProtectedFinanceAdmin)
