# mypy: disable-error-code="no-untyped-def"
from django.db.models import QuerySet

from .models import AttendanceException, AttendancePeriod, AttendanceRecord


def get_expected_attendance(*, start, end, company=None) -> QuerySet[AttendanceRecord]:
    queryset = AttendanceRecord.objects.filter(
        scheduled_start_at__lt=end, scheduled_end_at__gt=start
    ).select_related("employee", "site", "post", "duty_assignment__duty_shift")
    return queryset.filter(company=company) if company else queryset


def get_attendance_period(*, period_id) -> AttendancePeriod:
    return AttendancePeriod.objects.prefetch_related(
        "records__employee", "records__exceptions", "change_events"
    ).get(pk=period_id)


def get_attendance_exceptions(*, company=None, open_only=True) -> QuerySet[AttendanceException]:
    queryset = AttendanceException.objects.select_related(
        "attendance_record__employee", "attendance_record__site", "attendance_event"
    )
    if company:
        queryset = queryset.filter(attendance_record__company=company)
    return queryset.filter(status="OPEN") if open_only else queryset


def get_payroll_ready_attendance(*, period: AttendancePeriod) -> QuerySet[AttendanceRecord]:
    return period.records.filter(status__in=["APPROVED", "LOCKED"]).select_related(
        "employee", "duty_assignment__duty_shift"
    )
