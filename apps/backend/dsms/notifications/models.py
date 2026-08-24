# mypy: disable-error-code="no-untyped-def"
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import TimeStampedModel, UUIDModel

from . import enums

P = models.PROTECT


class Base(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class NotificationEvent(Base):
    event_key = models.CharField(max_length=250, unique=True)
    event_type = models.CharField(max_length=80, db_index=True)
    source_app = models.CharField(max_length=50)
    source_model = models.CharField(max_length=80)
    source_object_id = models.UUIDField(null=True, blank=True)
    company = models.ForeignKey("organization.Company", null=True, blank=True, on_delete=P)
    occurred_at = models.DateTimeField(db_index=True)
    payload_version = models.PositiveSmallIntegerField(default=1)
    safe_payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=enums.EventStatus.choices, default="PENDING", db_index=True
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    processing_attempts = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=80, blank=True)

    def delete(self, *args, **kwargs):
        raise ValidationError("Notification events cannot be deleted.")


class NotificationRule(Base):
    company = models.ForeignKey("organization.Company", null=True, blank=True, on_delete=P)
    event_type = models.CharField(max_length=80)
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    priority = models.CharField(max_length=10, choices=enums.Priority.choices, default="NORMAL")
    acknowledgement_requirement = models.CharField(
        max_length=10, choices=enums.Acknowledgement.choices, default="NONE"
    )
    expires_after_minutes = models.PositiveIntegerField(null=True, blank=True)
    quiet_hours_behavior = models.CharField(max_length=30, default="RESPECT")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_notification_rule_code")
        ]
        permissions = [
            ("manage_notification_rules", "Can manage notification rules"),
            ("view_notification_dashboard", "Can view notification dashboard"),
            ("monitor_notification_delivery", "Can monitor notification delivery"),
            ("send_test_notification", "Can send test notifications"),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class NotificationRuleChannel(Base):
    rule = models.ForeignKey(NotificationRule, on_delete=P, related_name="channels")
    channel = models.CharField(max_length=10, choices=enums.Channel.choices)
    is_enabled = models.BooleanField(default=True)
    required = models.BooleanField(default=False)
    delay_minutes = models.PositiveIntegerField(default=0)
    max_delivery_attempts = models.PositiveIntegerField(default=3)
    retry_delay_seconds = models.PositiveIntegerField(default=60)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["rule", "channel"], name="uniq_notification_rule_channel"
            )
        ]


class NotificationRecipientRule(UUIDModel):
    notification_rule = models.ForeignKey(
        NotificationRule, on_delete=P, related_name="recipient_rules"
    )
    audience_type = models.CharField(max_length=30)
    internal_role_code = models.CharField(max_length=80, blank=True)
    client_portal_role_code = models.CharField(max_length=80, blank=True)
    include_event_actor = models.BooleanField(default=False)
    include_object_owner = models.BooleanField(default=False)
    include_branch_scope = models.BooleanField(default=False)
    include_site_supervisors = models.BooleanField(default=False)
    include_command_center = models.BooleanField(default=False)
    explicit_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    priority = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationTemplate(Base):
    company = models.ForeignKey("organization.Company", null=True, blank=True, on_delete=P)
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=150)
    channel = models.CharField(max_length=10, choices=enums.Channel.choices)
    event_type = models.CharField(max_length=80)
    current_version = models.PositiveIntegerField(default=1)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code", "channel"], name="uniq_notification_template"
            )
        ]


class NotificationTemplateVersion(UUIDModel):
    template = models.ForeignKey(NotificationTemplate, on_delete=P, related_name="versions")
    version_number = models.PositiveIntegerField()
    subject_template = models.CharField(max_length=250, blank=True)
    body_template = models.TextField()
    short_body_template = models.CharField(max_length=500, blank=True)
    effective_from = models.DateTimeField()
    effective_to = models.DateTimeField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "version_number"], name="uniq_notification_template_version"
            ),
            models.UniqueConstraint(
                fields=["template"],
                condition=Q(is_current=True),
                name="uniq_current_notification_template",
            ),
        ]


class Notification(Base):
    event = models.ForeignKey(
        NotificationEvent, null=True, blank=True, on_delete=P, related_name="notifications"
    )
    rule = models.ForeignKey(NotificationRule, null=True, blank=True, on_delete=P)
    template_version = models.ForeignKey(
        NotificationTemplateVersion, null=True, blank=True, on_delete=P
    )
    company = models.ForeignKey("organization.Company", null=True, blank=True, on_delete=P)
    notification_type = models.CharField(max_length=80)
    priority = models.CharField(max_length=10, choices=enums.Priority.choices)
    title = models.CharField(max_length=250)
    body = models.TextField()
    action_url = models.CharField(max_length=500, blank=True)
    acknowledgement_requirement = models.CharField(
        max_length=10, choices=enums.Acknowledgement.choices, default="NONE"
    )
    scheduled_for = models.DateTimeField(null=True, blank=True, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=enums.NotificationStatus.choices, default="PENDING", db_index=True
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    processed_at = models.DateTimeField(null=True, blank=True)


class NotificationRecipient(Base):
    notification = models.ForeignKey(Notification, on_delete=P, related_name="recipients")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="notification_recipients"
    )
    client_portal_membership = models.ForeignKey(
        "client_portal.ClientPortalMembership", null=True, blank=True, on_delete=P
    )
    employee = models.ForeignKey("workforce.Employee", null=True, blank=True, on_delete=P)
    status = models.CharField(
        max_length=20, choices=enums.RecipientStatus.choices, default="PENDING", db_index=True
    )
    first_delivered_at = models.DateTimeField(null=True, blank=True)
    last_delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True, db_index=True)
    acknowledgement_comment = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["notification", "user"], name="uniq_notification_recipient"
            )
        ]
        indexes = [models.Index(fields=["user", "status"])]


class NotificationDeliveryAttempt(UUIDModel):
    notification_recipient = models.ForeignKey(
        NotificationRecipient, on_delete=P, related_name="delivery_attempts"
    )
    channel = models.CharField(max_length=10, choices=enums.Channel.choices, db_index=True)
    provider = models.CharField(max_length=50)
    attempt_number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=30, choices=enums.DeliveryStatus.choices, default="PENDING", db_index=True
    )
    destination_masked = models.CharField(max_length=150, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    attempted_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message_safe = models.CharField(max_length=250, blank=True)
    response_reference = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["notification_recipient", "channel", "attempt_number"],
                name="uniq_delivery_attempt_number",
            )
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError("Delivery attempts are immutable.")


class UserNotificationPreference(Base):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="notification_preferences"
    )
    event_type = models.CharField(max_length=80, blank=True)
    notification_rule = models.ForeignKey(NotificationRule, null=True, blank=True, on_delete=P)
    channel = models.CharField(max_length=10, choices=enums.Channel.choices)
    frequency = models.CharField(
        max_length=20, choices=enums.Frequency.choices, default="IMMEDIATE"
    )
    is_enabled = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=50, default="Asia/Karachi")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "event_type", "notification_rule", "channel"],
                name="uniq_user_notification_preference",
            )
        ]


class NotificationDeviceEndpoint(Base):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="notification_devices"
    )
    device_id = models.CharField(max_length=150)
    platform = models.CharField(max_length=20)
    token_hash = models.CharField(max_length=64)
    token_encrypted = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    last_registered_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    app_version = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "device_id"], name="uniq_user_device")
        ]


class NotificationAcknowledgementEvent(UUIDModel):
    recipient = models.ForeignKey(
        NotificationRecipient, on_delete=P, related_name="acknowledgement_events"
    )
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    acknowledged_at = models.DateTimeField()
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class NotificationDigest(Base):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    frequency = models.CharField(max_length=20, choices=enums.Frequency.choices)
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    status = models.CharField(max_length=20, default="PENDING")
    generated_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "frequency", "period_start", "period_end"],
                name="uniq_notification_digest",
            )
        ]


class NotificationDigestItem(UUIDModel):
    digest = models.ForeignKey(NotificationDigest, on_delete=P, related_name="items")
    notification_recipient = models.OneToOneField(NotificationRecipient, on_delete=P)
    sort_order = models.PositiveIntegerField(default=0)


class NotificationReminderPolicy(Base):
    notification_rule = models.OneToOneField(
        NotificationRule, on_delete=P, related_name="reminder_policy"
    )
    reminder_after_minutes = models.PositiveIntegerField()
    repeat_every_minutes = models.PositiveIntegerField(null=True, blank=True)
    maximum_reminders = models.PositiveIntegerField(null=True, blank=True)
    stop_on_read = models.BooleanField(default=False)
    stop_on_acknowledgement = models.BooleanField(default=True)
    escalate_after_reminders = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)


class NotificationEscalationRecord(UUIDModel):
    notification_recipient = models.ForeignKey(
        NotificationRecipient, on_delete=P, related_name="escalations"
    )
    reminder_number = models.PositiveIntegerField()
    escalated_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P
    )
    escalation_reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["notification_recipient", "reminder_number"],
                name="uniq_notification_reminder",
            )
        ]


class NotificationChannelFallback(UUIDModel):
    rule = models.ForeignKey(NotificationRule, on_delete=P, related_name="fallbacks")
    from_channel = models.CharField(max_length=10, choices=enums.Channel.choices)
    to_channel = models.CharField(max_length=10, choices=enums.Channel.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
