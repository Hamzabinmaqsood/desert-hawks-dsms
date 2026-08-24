# mypy: disable-error-code="no-untyped-def,type-arg"
from django.contrib import admin

from . import models


class ReadOnlyHistoryAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = (
        "incident_number",
        "title",
        "company",
        "branch",
        "severity",
        "priority",
        "status",
        "reported_at",
    )
    list_filter = ("status", "severity", "priority", "source")
    search_fields = ("incident_number", "title", "description")
    readonly_fields = (
        "incident_number",
        "status",
        "acknowledged_at",
        "triaged_at",
        "responding_at",
        "contained_at",
        "resolved_at",
        "closed_at",
        "created_at",
        "updated_at",
    )

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(models.IncidentType)
admin.site.register(models.IncidentEscalationPolicy)
admin.site.register(models.IncidentResponder)
admin.site.register(models.IncidentAction)
admin.site.register(models.PostIncidentReview)
admin.site.register(models.SOSAlert, ReadOnlyHistoryAdmin)
admin.site.register(models.IncidentEvent, ReadOnlyHistoryAdmin)
admin.site.register(models.IncidentLocationSnapshot, ReadOnlyHistoryAdmin)
admin.site.register(models.IncidentEvidenceEvent, ReadOnlyHistoryAdmin)
