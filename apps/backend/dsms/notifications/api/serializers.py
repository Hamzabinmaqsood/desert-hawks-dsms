# mypy: disable-error-code="type-arg"
from rest_framework import serializers

from dsms.notifications.models import NotificationRecipient, UserNotificationPreference


class InAppNotificationSerializer(serializers.ModelSerializer):
    title = serializers.CharField(source="notification.title")
    body = serializers.CharField(source="notification.body")
    priority = serializers.CharField(source="notification.priority")
    action_url = serializers.CharField(source="notification.action_url")
    acknowledgement_requirement = serializers.CharField(
        source="notification.acknowledgement_requirement"
    )

    class Meta:
        model = NotificationRecipient
        fields = [
            "id",
            "title",
            "body",
            "priority",
            "action_url",
            "acknowledgement_requirement",
            "status",
            "read_at",
            "acknowledged_at",
            "created_at",
        ]


class PreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserNotificationPreference
        fields = [
            "id",
            "event_type",
            "notification_rule",
            "channel",
            "frequency",
            "is_enabled",
            "quiet_hours_start",
            "quiet_hours_end",
            "timezone",
        ]


class AcknowledgeSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000)
