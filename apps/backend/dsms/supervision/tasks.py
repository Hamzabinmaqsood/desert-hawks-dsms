# mypy: disable-error-code="untyped-decorator"
from celery import shared_task
from django.utils import timezone

from dsms.subscriptions.enforcement import company_ids_with_module

from .models import CorrectiveAction
from .tenant_queries import consistent_corrective_actions


@shared_task
def detect_overdue_corrective_actions() -> int:
    return (
        consistent_corrective_actions(
            CorrectiveAction.objects.filter(
                company_id__in=company_ids_with_module("security_supervision"),
                due_at__lt=timezone.now(),
            )
        )
        .exclude(status__in=["VERIFIED", "CLOSED", "CANCELLED", "OVERDUE"])
        .update(status="OVERDUE")
    )
