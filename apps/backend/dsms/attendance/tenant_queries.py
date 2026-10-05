# mypy: disable-error-code="no-untyped-def,operator,type-arg,no-any-return"
"""Explicit tenant-consistency predicates for Attendance operations."""

from __future__ import annotations

from django.db.models import F, Q, QuerySet

from dsms.deployment.models import DutyAssignment
from dsms.identity import access

from .models import (
    AttendanceChangeEvent,
    AttendanceCorrectionRequest,
    AttendanceEvent,
    AttendanceException,
    AttendancePayrollExport,
    AttendancePeriod,
    AttendancePolicy,
    AttendanceQRStation,
    AttendanceRecord,
    AttendanceVerification,
)


def consistent_duty_assignments(
    queryset: QuerySet[DutyAssignment],
) -> QuerySet[DutyAssignment]:
    return (
        queryset.filter(duty_shift__company__is_active=True)
        .filter(duty_shift__branch__company_id=F("duty_shift__company_id"))
        .filter(duty_shift__client__company_id=F("duty_shift__company_id"))
        .filter(duty_shift__contract__company_id=F("duty_shift__company_id"))
        .filter(duty_shift__contract__client_id=F("duty_shift__client_id"))
        .filter(duty_shift__site__company_id=F("duty_shift__company_id"))
        .filter(duty_shift__site__client_id=F("duty_shift__client_id"))
        .filter(duty_shift__site__contract_id=F("duty_shift__contract_id"))
        .filter(duty_shift__site__managing_branch_id=F("duty_shift__branch_id"))
        .filter(duty_shift__post__company_id=F("duty_shift__company_id"))
        .filter(duty_shift__post__client_id=F("duty_shift__client_id"))
        .filter(duty_shift__post__site_id=F("duty_shift__site_id"))
        .filter(duty_shift__roster_period__company_id=F("duty_shift__company_id"))
        .filter(duty_shift__roster_period__branch_id=F("duty_shift__branch_id"))
        .filter(employee__company_id=F("duty_shift__company_id"))
        .filter(
            Q(employee__branch__isnull=True)
            | Q(employee__branch__company_id=F("duty_shift__company_id"))
        )
    )


def consistent_attendance_policies(
    queryset: QuerySet[AttendancePolicy],
) -> QuerySet[AttendancePolicy]:
    return (
        queryset.filter(company__is_active=True)
        .filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__client__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__contract__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__managing_branch__company_id=F("company_id")))
        .filter(
            Q(branch__isnull=True)
            | Q(site__isnull=True)
            | Q(site__managing_branch_id=F("branch_id"))
        )
        .filter(Q(post__isnull=True) | Q(post__company_id=F("company_id")))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
        .filter(Q(post__isnull=True) | Q(post__client__company_id=F("company_id")))
        .filter(Q(post__isnull=True) | Q(post__client_id=F("site__client_id")))
    )


def consistent_qr_stations(
    queryset: QuerySet[AttendanceQRStation],
) -> QuerySet[AttendanceQRStation]:
    return (
        queryset.filter(company__is_active=True)
        .filter(site__company_id=F("company_id"))
        .filter(site__client__company_id=F("company_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(site__managing_branch__company_id=F("company_id"))
        .filter(Q(post__isnull=True) | Q(post__company_id=F("company_id")))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
        .filter(Q(post__isnull=True) | Q(post__client_id=F("site__client_id")))
    )


def consistent_attendance_periods(
    queryset: QuerySet[AttendancePeriod],
) -> QuerySet[AttendancePeriod]:
    return queryset.filter(company__is_active=True).filter(
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id"))
    )


def consistent_attendance_records(
    queryset: QuerySet[AttendanceRecord],
) -> QuerySet[AttendanceRecord]:
    return (
        queryset.filter(company__is_active=True)
        .filter(branch__company_id=F("company_id"))
        .filter(client__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client_id=F("client_id"))
        .filter(site__managing_branch_id=F("branch_id"))
        .filter(site__contract__company_id=F("company_id"))
        .filter(post__company_id=F("company_id"))
        .filter(post__client_id=F("client_id"))
        .filter(post__site_id=F("site_id"))
        .filter(employee__company_id=F("company_id"))
        .filter(Q(employee__branch__isnull=True) | Q(employee__branch__company_id=F("company_id")))
        .filter(duty_assignment__in=consistent_duty_assignments(DutyAssignment.objects.all()))
        .filter(duty_assignment__duty_shift__company_id=F("company_id"))
        .filter(duty_assignment__duty_shift__branch_id=F("branch_id"))
        .filter(duty_assignment__duty_shift__client_id=F("client_id"))
        .filter(duty_assignment__duty_shift__site_id=F("site_id"))
        .filter(duty_assignment__duty_shift__post_id=F("post_id"))
        .filter(duty_assignment__employee_id=F("employee_id"))
        .filter(
            Q(attendance_period__isnull=True) | Q(attendance_period__company_id=F("company_id"))
        )
        .filter(
            Q(attendance_period__isnull=True)
            | Q(attendance_period__branch__isnull=True)
            | Q(attendance_period__branch_id=F("branch_id"))
        )
    )


def consistent_attendance_events(
    queryset: QuerySet[AttendanceEvent],
) -> QuerySet[AttendanceEvent]:
    return queryset.filter(
        attendance_record__in=consistent_attendance_records(AttendanceRecord.objects.all()),
        subject_employee__company_id=F("attendance_record__company_id"),
    )


def consistent_attendance_verifications(
    queryset: QuerySet[AttendanceVerification],
) -> QuerySet[AttendanceVerification]:
    return (
        queryset.filter(
            attendance_event__in=consistent_attendance_events(AttendanceEvent.objects.all())
        )
        .filter(
            Q(qr_station__isnull=True)
            | Q(qr_station__company_id=F("attendance_event__attendance_record__company_id"))
        )
        .filter(
            Q(qr_station__isnull=True)
            | Q(qr_station__site_id=F("attendance_event__attendance_record__site_id"))
        )
        .filter(
            Q(qr_station__isnull=True)
            | Q(qr_station__in=consistent_qr_stations(AttendanceQRStation.objects.all()))
        )
    )


def consistent_attendance_exceptions(
    queryset: QuerySet[AttendanceException],
) -> QuerySet[AttendanceException]:
    return (
        queryset.filter(
            attendance_record__in=consistent_attendance_records(AttendanceRecord.objects.all())
        )
        .filter(
            Q(attendance_event__isnull=True)
            | Q(attendance_event__attendance_record_id=F("attendance_record_id"))
        )
        .filter(
            Q(attendance_event__isnull=True)
            | Q(attendance_event__in=consistent_attendance_events(AttendanceEvent.objects.all()))
        )
    )


def consistent_corrections(
    queryset: QuerySet[AttendanceCorrectionRequest],
) -> QuerySet[AttendanceCorrectionRequest]:
    return queryset.filter(
        attendance_record__in=consistent_attendance_records(AttendanceRecord.objects.all())
    )


def consistent_change_events(
    queryset: QuerySet[AttendanceChangeEvent],
) -> QuerySet[AttendanceChangeEvent]:
    return (
        queryset.filter(Q(attendance_record__isnull=False) | Q(attendance_period__isnull=False))
        .filter(
            Q(attendance_record__isnull=True)
            | Q(attendance_record__in=consistent_attendance_records(AttendanceRecord.objects.all()))
        )
        .filter(
            Q(attendance_period__isnull=True)
            | Q(attendance_period__in=consistent_attendance_periods(AttendancePeriod.objects.all()))
        )
        .filter(
            Q(attendance_record__isnull=True)
            | Q(attendance_period__isnull=True)
            | Q(attendance_record__company_id=F("attendance_period__company_id"))
        )
    )


def consistent_payroll_exports(
    queryset: QuerySet[AttendancePayrollExport],
) -> QuerySet[AttendancePayrollExport]:
    return (
        queryset.filter(
            attendance_period__in=consistent_attendance_periods(AttendancePeriod.objects.all())
        )
        .filter(payroll_period__company_id=F("attendance_period__company_id"))
        .filter(employee__company_id=F("attendance_period__company_id"))
        .filter(
            Q(employee__branch__isnull=True)
            | Q(employee__branch__company_id=F("attendance_period__company_id"))
        )
    )


CONSISTENCY_FILTERS = {
    AttendancePolicy: consistent_attendance_policies,
    AttendanceQRStation: consistent_qr_stations,
    AttendancePeriod: consistent_attendance_periods,
    AttendanceRecord: consistent_attendance_records,
    AttendanceEvent: consistent_attendance_events,
    AttendanceVerification: consistent_attendance_verifications,
    AttendanceException: consistent_attendance_exceptions,
    AttendanceCorrectionRequest: consistent_corrections,
    AttendanceChangeEvent: consistent_change_events,
    AttendancePayrollExport: consistent_payroll_exports,
}


def consistent_queryset(queryset: QuerySet) -> QuerySet:
    return CONSISTENCY_FILTERS[queryset.model](queryset)


def scoped_queryset(queryset: QuerySet, *, user, permission: str) -> QuerySet:
    queryset = consistent_queryset(queryset)
    if user.is_superuser:
        return queryset.order_by("pk")
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    model = queryset.model
    if model is AttendancePolicy:
        return queryset.filter(
            Q(branch_id__in=branch_ids)
            | Q(branch__isnull=True, site__managing_branch_id__in=branch_ids)
            | Q(branch__isnull=True, site__isnull=True, company_id__in=company_ids)
        ).order_by("pk")
    if model is AttendanceQRStation:
        return queryset.filter(site__managing_branch_id__in=branch_ids).order_by("pk")
    if model is AttendancePeriod:
        return queryset.filter(
            Q(branch_id__in=branch_ids) | Q(branch__isnull=True, company_id__in=company_ids)
        ).order_by("pk")
    if model is AttendanceRecord:
        return queryset.filter(branch_id__in=branch_ids).order_by("pk")
    if model is AttendanceEvent:
        return queryset.filter(attendance_record__branch_id__in=branch_ids).order_by("pk")
    if model is AttendanceVerification:
        return queryset.filter(
            attendance_event__attendance_record__branch_id__in=branch_ids
        ).order_by("pk")
    if model in {AttendanceException, AttendanceCorrectionRequest}:
        return queryset.filter(attendance_record__branch_id__in=branch_ids).order_by("pk")
    if model is AttendanceChangeEvent:
        return (
            queryset.filter(
                Q(attendance_record__branch_id__in=branch_ids)
                | Q(attendance_period__branch_id__in=branch_ids)
                | Q(
                    attendance_period__branch__isnull=True,
                    attendance_period__company_id__in=company_ids,
                )
            )
            .distinct()
            .order_by("pk")
        )
    if model is AttendancePayrollExport:
        return queryset.filter(attendance_period__company_id__in=company_ids).order_by("pk")
    return queryset.none()
