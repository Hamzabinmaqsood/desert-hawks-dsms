from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from .services import create_overdue_collection_reminders, generate_due_draft_invoices


@shared_task  # type: ignore[untyped-decorator]
def generate_recurring_billing_drafts() -> int:
    """Generate drafts only; absence of an explicit system actor is a safe no-op."""
    actor_id = getattr(settings, "BILLING_SYSTEM_USER_ID", "")
    if not actor_id:
        return 0
    actor = get_user_model().objects.filter(pk=actor_id, is_active=True).first()
    if not actor:
        return 0
    return generate_due_draft_invoices(as_of=timezone.localdate(), actor=actor)


@shared_task  # type: ignore[untyped-decorator]
def queue_overdue_collection_reminders() -> int:
    actor_id = getattr(settings, "BILLING_SYSTEM_USER_ID", "")
    actor = (
        get_user_model().objects.filter(pk=actor_id, is_active=True).first() if actor_id else None
    )
    if not actor:
        return 0
    return create_overdue_collection_reminders(as_of=timezone.localdate(), actor=actor)
