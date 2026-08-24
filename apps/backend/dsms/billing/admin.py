from typing import Any

from django.apps import apps
from django.contrib import admin
from django.http import HttpRequest


class ProtectedBillingAdmin(admin.ModelAdmin[Any]):
    """Billing records are corrected through services, never destructive admin edits."""

    list_per_page = 50

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        protected = {
            "APPROVED",
            "ISSUED",
            "CONFIRMED",
            "PARTIALLY_ALLOCATED",
            "ALLOCATED",
            "REVERSED",
            "PAID",
        }
        if obj is not None and getattr(obj, "status", None) in protected:
            return tuple(field.name for field in self.model._meta.fields)
        return tuple(
            name
            for name in ("accounting_journal", "posted_at", "sha256", "generated_at")
            if any(field.name == name for field in self.model._meta.fields)
        )


for billing_model in apps.get_app_config("billing").get_models():
    if billing_model not in admin.site._registry:
        admin.site.register(billing_model, ProtectedBillingAdmin)
