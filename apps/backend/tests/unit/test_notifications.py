from datetime import timedelta

import pytest
from celery.exceptions import Retry
from django.utils import timezone

from dsms.identity.models import User
from dsms.notifications.models import (
    Notification,
    NotificationRecipient,
    NotificationRecipientRule,
    NotificationRule,
)
from dsms.notifications.providers import DisabledProvider
from dsms.notifications.providers import TestProvider as DeliveryTestProvider
from dsms.notifications.services import (
    process_notification_event,
    publish_notification_event,
    render_template,
    validate_action_url,
)
from dsms.notifications.tasks import (
    mark_expired_notifications,
    process_notification_event_task,
    process_pending_notification_events,
)
from tests.factories.identity import UserFactory


def test_restricted_template_renderer_rejects_traversal() -> None:
    assert (
        render_template(
            "Incident {{ incident_number }}", {"incident_number": "INC-1"}, {"incident_number"}
        )
        == "Incident INC-1"
    )
    with pytest.raises(ValueError):
        render_template("{{ user.password }}", {"user": "x"}, {"user"})


def test_action_url_rejects_external_hosts() -> None:
    assert validate_action_url("/incidents/1") == "/incidents/1"
    with pytest.raises(ValueError):
        validate_action_url("https://attacker.example/path")


def test_default_providers_do_not_perform_network_delivery() -> None:
    assert DisabledProvider().send(destination="hidden").permanent_failure
    assert DeliveryTestProvider().send(destination="hidden").accepted


@pytest.mark.django_db
def test_event_processing_is_idempotent_and_creates_in_app_recipient() -> None:
    user: User = UserFactory.create()
    rule = NotificationRule.objects.create(event_type="TEST_EVENT", code="TEST_EVENT", name="Test")
    NotificationRecipientRule.objects.create(
        notification_rule=rule, audience_type="USER", explicit_user=user
    )
    event = publish_notification_event(
        event_key="test:event:1",
        event_type="TEST_EVENT",
        source_app="tests",
        source_model="Example",
        safe_payload={"message": "Safe message"},
    )
    first = process_notification_event(event_id=event.id)
    second = process_notification_event(event_id=event.id)
    assert first[0].id == second[0].id
    assert first[0].recipients.get().user == user


@pytest.mark.django_db
def test_event_key_deduplicates_retries() -> None:
    first = publish_notification_event(
        event_key="test:event:dedupe", event_type="TEST", source_app="tests", source_model="Example"
    )
    second = publish_notification_event(
        event_key="test:event:dedupe", event_type="TEST", source_app="tests", source_model="Example"
    )
    assert first.id == second.id


@pytest.mark.django_db
def test_pending_event_task_dispatch_is_bounded_and_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        publish_notification_event(
            event_key=f"pending:{index}",
            event_type="TEST",
            source_app="tests",
            source_model="Example",
        )
        for index in range(2)
    ]
    dispatched: list[str] = []
    monkeypatch.setattr(
        process_notification_event_task,
        "delay",
        lambda event_id: dispatched.append(event_id),
    )
    assert process_pending_notification_events.run() == 2
    assert set(dispatched) == {str(event.id) for event in events}


@pytest.mark.django_db
def test_expiry_task_expires_notification_and_unacknowledged_recipient() -> None:
    user = UserFactory.create()
    notification = Notification.objects.create(
        notification_type="TEST",
        priority="NORMAL",
        title="Expired",
        body="Safe body",
        expires_at=timezone.now() - timedelta(seconds=1),
        status="DELIVERED",
    )
    recipient = NotificationRecipient.objects.create(
        notification=notification, user=user, status="DELIVERED"
    )
    assert mark_expired_notifications.run() == 1
    notification.refresh_from_db()
    recipient.refresh_from_db()
    assert notification.status == "EXPIRED"
    assert recipient.status == "EXPIRED"


def test_retry_capable_task_requests_retry_on_temporary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def temporary_failure(*, event_id: str) -> None:
        raise ConnectionError("temporary broker-independent provider failure")

    monkeypatch.setattr("dsms.notifications.tasks.process_notification_event", temporary_failure)
    with pytest.raises(Retry):
        process_notification_event_task.apply(args=["missing"], throw=True)
    assert process_notification_event_task.max_retries == 5
