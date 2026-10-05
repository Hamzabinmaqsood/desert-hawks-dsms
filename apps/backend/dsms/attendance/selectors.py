# mypy: disable-error-code="no-untyped-def"
from django.db.models import Prefetch, QuerySet

from .models import AttendanceChangeEvent, AttendanceException, AttendancePeriod, AttendanceRecord
from .tenant_queries import (
    consistent_attendance_exceptions,
    consistent_attendance_periods,
    consistent_attendance_records,
    consistent_change_events,
)


def get_expected_attendance(*, start, end, company=None) -> QuerySet[AttendanceRecord]:
    queryset = consistent_attendance_records(
        AttendanceRecord.objects.filter(
            scheduled_start_at__lt=end, scheduled_end_at__gt=start
        ).select_related("employee", "site", "post", "duty_assignment__duty_shift")
    )
    return queryset.filter(company=company) if company else queryset


def get_attendance_period(*, period_id) -> AttendancePeriod:
    return consistent_attendance_periods(
        AttendancePeriod.objects.prefetch_related(
            Prefetch(
                "records",
                queryset=consistent_attendance_records(
                    AttendanceRecord.objects.select_related("employee")
                ),
            ),
            Prefetch(
                "records__exceptions",
                queryset=consistent_attendance_exceptions(AttendanceException.objects.all()),
            ),
            Prefetch(
                "change_events",
                queryset=consistent_change_events(AttendanceChangeEvent.objects.all()),
            ),
        )
    ).get(pk=period_id)


def get_attendance_exceptions(*, company=None, open_only=True) -> QuerySet[AttendanceException]:
    queryset = consistent_attendance_exceptions(
        AttendanceException.objects.select_related(
            "attendance_record__employee", "attendance_record__site", "attendance_event"
        )
    )
    if company:
        queryset = queryset.filter(attendance_record__company=company)
    return queryset.filter(status="OPEN") if open_only else queryset


def get_payroll_ready_attendance(*, period: AttendancePeriod) -> QuerySet[AttendanceRecord]:
    return (
        consistent_attendance_records(period.records.all())
        .filter(status__in=["APPROVED", "LOCKED"])
        .select_related("employee", "duty_assignment__duty_shift")
    )
