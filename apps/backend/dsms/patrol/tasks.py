# mypy: disable-error-code="untyped-decorator,no-any-return,no-untyped-call"
from celery import shared_task

from .services import mark_missed_patrols


@shared_task
def detect_missed_patrol_tasks() -> int:
    return mark_missed_patrols()
