# mypy: disable-error-code="no-untyped-def,no-untyped-call"
from celery import shared_task
from django.utils import timezone

from .models import Notification, NotificationEvent, NotificationRecipient
from .services import process_notification_event


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def process_notification_event_task(self, event_id):
    return process_notification_event(event_id=event_id)


@shared_task
def process_pending_notification_events():
    count = 0
    for event_id in NotificationEvent.objects.filter(status="PENDING").values_list("id", flat=True)[
        :500
    ]:
        process_notification_event_task.delay(str(event_id))
        count += 1
    return count


@shared_task
def mark_expired_notifications():
    now = timezone.now()
    notifications = Notification.objects.filter(expires_at__lte=now).exclude(
        status__in=["CANCELLED", "EXPIRED"]
    )
    ids = list(notifications.values_list("id", flat=True))
    notifications.update(status="EXPIRED")
    return (
        NotificationRecipient.objects.filter(notification_id__in=ids)
        .exclude(status="ACKNOWLEDGED")
        .update(status="EXPIRED")
    )
