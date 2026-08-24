# mypy: disable-error-code="untyped-decorator"
from celery import shared_task
from django.utils import timezone

from .models import AttendanceException, AttendanceRecord


@shared_task
def detect_attendance_missing_checkout() -> int:
    now = timezone.now()
    created = 0
    records = AttendanceRecord.objects.filter(
        actual_check_in_at__isnull=False,
        actual_check_out_at__isnull=True,
        scheduled_end_at__lt=now,
    ).exclude(status="LOCKED")
    for record in records:
        _, made = AttendanceException.objects.get_or_create(
            attendance_record=record,
            exception_type="MISSING_CHECKOUT",
            status="OPEN",
            defaults={
                "severity": "MEDIUM",
                "detected_at": now,
                "message": "No check-out was received after the scheduled duty end.",
            },
        )
        created += int(made)
    return created
