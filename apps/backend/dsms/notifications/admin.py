# mypy: disable-error-code="type-arg,no-untyped-def"
from django.contrib import admin

from . import models

for model in [
    models.NotificationRule,
    models.NotificationRuleChannel,
    models.NotificationRecipientRule,
    models.NotificationTemplate,
    models.UserNotificationPreference,
    models.NotificationDeviceEndpoint,
    models.NotificationReminderPolicy,
    models.NotificationChannelFallback,
]:
    admin.site.register(model)


@admin.register(
    models.NotificationEvent,
    models.NotificationTemplateVersion,
    models.NotificationDeliveryAttempt,
    models.NotificationAcknowledgementEvent,
    models.NotificationEscalationRecord,
)
class ReadOnlyHistoryAdmin(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("notification_type", "priority", "status", "scheduled_for", "created_at")
    list_filter = ("priority", "status")

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(models.NotificationRecipient)
admin.site.register(models.NotificationDigest)
