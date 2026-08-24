# mypy: disable-error-code="no-untyped-def,no-untyped-call"
import re
import uuid
from collections.abc import Iterable, Mapping
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dsms.identity.models import User

from .models import (
    Notification,
    NotificationAcknowledgementEvent,
    NotificationDeliveryAttempt,
    NotificationEvent,
    NotificationRecipient,
    NotificationRule,
    NotificationTemplate,
    UserNotificationPreference,
)
from .providers import DisabledProvider

MANDATORY_OPERATIONAL_EVENTS = {
    "SOS_TRIGGERED",
    "INCIDENT_ACKNOWLEDGEMENT_REQUIRED",
    "INCIDENT_ESCALATED",
}

FORBIDDEN_PAYLOAD_KEYS = {
    "password",
    "token",
    "jwt",
    "cnic",
    "bank_account",
    "latitude",
    "longitude",
    "qr_secret",
    "biometric",
}
VARIABLE = re.compile(r"{{\s*([a-zA-Z][a-zA-Z0-9_]*)\s*}}")


def validate_safe_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or any(
        str(k).lower() in FORBIDDEN_PAYLOAD_KEYS for k in payload
    ):
        raise ValueError("Payload contains unsupported or sensitive fields.")
    for value in payload.values():
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError("Nested arbitrary payloads are not supported.")
    return dict(payload)


def validate_action_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        raise ValueError("Action URL must be a relative application path.")
    return value


def render_template(text: str, context: Mapping[str, Any], allowed_variables: Iterable[str]) -> str:
    used = set(VARIABLE.findall(text))
    if used - set(allowed_variables) or used - set(context):
        raise ValueError("Template contains an unavailable variable.")
    if "{%" in text or "__" in text or "." in "".join(used):
        raise ValueError("Unsafe template syntax.")
    rendered = VARIABLE.sub(lambda match: str(context[match.group(1)]), text)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("Unsafe or unresolved template expression.")
    return rendered


@transaction.atomic
def publish_notification_event(
    *,
    event_key: str,
    event_type: str,
    source_app: str,
    source_model: str,
    source_object_id: Any = None,
    company: Any = None,
    occurred_at: Any = None,
    safe_payload: Mapping[str, Any] | None = None,
) -> NotificationEvent:
    payload = validate_safe_payload(safe_payload or {})
    event, _ = NotificationEvent.objects.get_or_create(
        event_key=event_key,
        defaults={
            "event_type": event_type,
            "source_app": source_app,
            "source_model": source_model,
            "source_object_id": source_object_id,
            "company": company,
            "occurred_at": occurred_at or timezone.now(),
            "safe_payload": payload,
        },
    )
    return event


def resolve_notification_recipients(*, event, rule):
    user_ids = set()
    for recipient_rule in rule.recipient_rules.filter(is_active=True).select_related(
        "explicit_user"
    ):
        if recipient_rule.explicit_user_id and recipient_rule.explicit_user.is_active:
            user_ids.add(recipient_rule.explicit_user_id)
        if recipient_rule.include_event_actor and event.safe_payload.get("actor_user_id"):
            user_ids.add(event.safe_payload["actor_user_id"])
        if recipient_rule.include_object_owner and event.safe_payload.get("owner_user_id"):
            user_ids.add(event.safe_payload["owner_user_id"])
        if recipient_rule.internal_role_code:
            assignments = Q(
                role_assignments__role__code=recipient_rule.internal_role_code,
                role_assignments__is_active=True,
            )
            if event.company_id:
                assignments &= Q(role_assignments__company=event.company)
            user_ids.update(
                User.objects.filter(assignments, is_active=True).values_list("id", flat=True)
            )
    return User.objects.filter(id__in=user_ids, is_active=True)


@transaction.atomic
def process_notification_event(*, event_id: uuid.UUID | str) -> list[Notification]:
    event = NotificationEvent.objects.select_for_update().get(pk=event_id)
    if event.status == "PROCESSED":
        return list(event.notifications.all())
    event.processing_attempts += 1
    rules = (
        NotificationRule.objects.filter(event_type=event.event_type, is_active=True)
        .filter(Q(company=event.company) | Q(company__isnull=True))
        .order_by("-company_id")
    )
    if not rules.exists():
        event.status, event.processed_at = "IGNORED", timezone.now()
        event.save()
        return []
    created = []
    for rule in rules:
        template = (
            NotificationTemplate.objects.filter(
                event_type=event.event_type, channel="IN_APP", is_active=True
            )
            .filter(Q(company=event.company) | Q(company__isnull=True))
            .select_related()
            .order_by("-company_id")
            .first()
        )
        version = template.versions.filter(is_current=True).first() if template else None
        title = (
            render_template(version.subject_template, event.safe_payload, event.safe_payload.keys())
            if version
            else event.event_type.replace("_", " ").title()
        )
        body = (
            render_template(version.body_template, event.safe_payload, event.safe_payload.keys())
            if version
            else str(event.safe_payload.get("message", title))
        )
        notification, _ = Notification.objects.get_or_create(
            event=event,
            rule=rule,
            defaults={
                "company": event.company,
                "notification_type": event.event_type,
                "priority": rule.priority,
                "title": title,
                "body": body,
                "acknowledgement_requirement": rule.acknowledgement_requirement,
                "expires_at": timezone.now() + timedelta(minutes=rule.expires_after_minutes)
                if rule.expires_after_minutes
                else None,
            },
        )
        recipients = resolve_notification_recipients(event=event, rule=rule)
        if event.event_type not in MANDATORY_OPERATIONAL_EVENTS:
            disabled_user_ids = (
                UserNotificationPreference.objects.filter(
                    user__in=recipients,
                    channel="IN_APP",
                    is_enabled=False,
                )
                .filter(Q(event_type="") | Q(event_type=event.event_type))
                .values_list("user_id", flat=True)
            )
            recipients = recipients.exclude(id__in=disabled_user_ids)
        NotificationRecipient.objects.bulk_create(
            [
                NotificationRecipient(
                    notification=notification,
                    user=user,
                    status="DELIVERED",
                    first_delivered_at=timezone.now(),
                    last_delivered_at=timezone.now(),
                )
                for user in recipients
            ],
            ignore_conflicts=True,
        )
        notification.status, notification.processed_at = (
            ("DELIVERED" if notification.recipients.exists() else "FAILED"),
            timezone.now(),
        )
        notification.save()
        created.append(notification)
    event.status, event.processed_at, event.last_error_code = "PROCESSED", timezone.now(), ""
    event.save()
    return created


@transaction.atomic
def deliver_external(*, recipient, channel, destination, provider=None):
    recipient = NotificationRecipient.objects.select_for_update().get(pk=recipient.pk)
    attempt_number = recipient.delivery_attempts.filter(channel=channel).count() + 1
    result = (provider or DisabledProvider()).send(
        destination=destination,
        body=recipient.notification.body,
        subject=recipient.notification.title,
        metadata={"notification_id": str(recipient.notification_id)},
    )
    status = (
        "DELIVERED"
        if result.delivered_if_known
        else "ACCEPTED"
        if result.accepted
        else "TEMPORARY_FAILURE"
        if result.temporary_failure
        else "PERMANENT_FAILURE"
    )
    masked = "***" + destination[-4:] if len(destination) >= 4 else "***"
    return NotificationDeliveryAttempt.objects.create(
        notification_recipient=recipient,
        channel=channel,
        provider=(provider or DisabledProvider()).name,
        attempt_number=attempt_number,
        status=status,
        destination_masked=masked,
        provider_message_id=result.provider_message_id,
        attempted_at=timezone.now(),
        accepted_at=timezone.now() if result.accepted else None,
        failed_at=timezone.now() if not result.accepted else None,
        error_code=result.error_code,
    )


def list_in_app_notifications(user):
    return (
        NotificationRecipient.objects.filter(user=user)
        .select_related("notification")
        .order_by("-notification__created_at")
    )


@transaction.atomic
def mark_notification_read(*, recipient, actor):
    obj = NotificationRecipient.objects.select_for_update().get(pk=recipient.pk, user=actor)
    if obj.read_at is None:
        obj.read_at, obj.status = timezone.now(), "READ"
        obj.save()
    return obj


@transaction.atomic
def acknowledge_notification(*, recipient, actor, comment=""):
    obj = NotificationRecipient.objects.select_for_update().get(pk=recipient.pk, user=actor)
    if obj.acknowledged_at is None:
        obj.acknowledged_at, obj.acknowledgement_comment, obj.status = (
            timezone.now(),
            comment,
            "ACKNOWLEDGED",
        )
        obj.save()
        NotificationAcknowledgementEvent.objects.create(
            recipient=obj,
            acknowledged_by=actor,
            acknowledged_at=obj.acknowledged_at,
            comment=comment,
        )
    return obj
