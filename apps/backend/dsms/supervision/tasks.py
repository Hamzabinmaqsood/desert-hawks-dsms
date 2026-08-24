# mypy: disable-error-code="untyped-decorator"
from celery import shared_task
from django.utils import timezone

from .models import CorrectiveAction


@shared_task
def detect_overdue_corrective_actions() -> int:
    return (
        CorrectiveAction.objects.filter(due_at__lt=timezone.now())
        .exclude(status__in=["VERIFIED", "CLOSED", "CANCELLED", "OVERDUE"])
        .update(status="OVERDUE")
    )
