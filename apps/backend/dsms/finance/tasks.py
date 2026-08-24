from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .operations_models import CompanyExpense, RecurringExpenseTemplate

# Import payment tasks so the single Finance Celery module discovers them.
from .payment_tasks import (  # noqa: F401
    process_payment_batch_task,
    process_payment_instruction_task,
)
from .services import next_document_number


@shared_task  # type: ignore[untyped-decorator]
def generate_recurring_expense_drafts() -> int:
    """Create due draft obligations; never approves, posts, or pays them."""
    created = 0
    today = timezone.localdate()
    with transaction.atomic():
        templates = RecurringExpenseTemplate.objects.select_for_update().filter(
            is_active=True, next_due_date__lte=today, created_by__isnull=False
        )
        for template in templates:
            assert template.created_by is not None
            CompanyExpense.objects.create(
                company=template.company,
                category=template.category,
                branch=template.branch,
                department=template.department,
                cost_center=template.cost_center,
                expense_number=next_document_number(
                    company=template.company, prefix="EXP", year=today.year
                ),
                expense_date=template.next_due_date,
                description=template.description,
                amount=template.amount,
                created_by=template.created_by,
            )
            template.next_due_date += timedelta(days=30)
            template.save(update_fields=["next_due_date", "updated_at"])
            created += 1
    return created
