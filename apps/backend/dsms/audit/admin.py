from django.contrib import admin
from django.http import HttpRequest

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin[AuditEvent]):
    list_display = ("occurred_at", "category", "action", "actor_user", "company", "success")
    list_filter = ("category", "severity", "success", "source_app", "company", "branch")
    search_fields = ("action", "summary", "object_reference", "request_id")
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: AuditEvent | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: AuditEvent | None = None) -> bool:
        return False
