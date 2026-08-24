from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from django.db import models
from django.db.models import QuerySet
from django.utils import timezone

from dsms.workforce.enums import EmployeeType
from dsms.workforce.models import Employee

from .enums import CertificateStatus, EnrollmentStatus, TrainingSessionStatus
from .models import (
    EmployeeQualification,
    TrainingCertificate,
    TrainingCompletion,
    TrainingCourse,
    TrainingEnrollment,
    TrainingSession,
)
from .services import evaluate_employee_readiness


def training_course_list() -> QuerySet[TrainingCourse]:
    return TrainingCourse.objects.select_related("company", "category").prefetch_related("versions")


def training_session_list() -> QuerySet[TrainingSession]:
    return TrainingSession.objects.select_related(
        "company", "course", "course_version", "branch", "venue", "lead_instructor"
    )


def employee_training_history(employee: Employee) -> QuerySet[TrainingCompletion]:
    return TrainingCompletion.objects.filter(employee=employee).select_related(
        "course", "course_version", "session"
    )


def employee_certificates(employee: Employee) -> QuerySet[TrainingCertificate]:
    return TrainingCertificate.objects.filter(employee=employee).select_related(
        "qualification_type", "training_completion"
    )


def valid_employee_qualifications(
    employee: Employee, *, as_of: date | None = None
) -> QuerySet[EmployeeQualification]:
    day = as_of or timezone.localdate()
    return (
        EmployeeQualification.objects.filter(
            employee=employee, status="VALID", obtained_on__lte=day
        )
        .filter(models.Q(expires_on__isnull=True) | models.Q(expires_on__gte=day))
        .select_related("qualification_type")
    )


def training_dashboard_summary(*, company_id: str | None = None) -> dict[str, Any]:
    today, now = timezone.localdate(), timezone.now()
    courses = TrainingCourse.objects.all()
    sessions = TrainingSession.objects.all()
    enrollments = TrainingEnrollment.objects.all()
    completions = TrainingCompletion.objects.all()
    certificates = TrainingCertificate.objects.all()
    employees = Employee.objects.filter(employment_status="ACTIVE", is_active=True)
    if company_id:
        courses, sessions = (
            courses.filter(company_id=company_id),
            sessions.filter(company_id=company_id),
        )
        enrollments, completions = (
            enrollments.filter(company_id=company_id),
            completions.filter(employee__company_id=company_id),
        )
        certificates, employees = (
            certificates.filter(company_id=company_id),
            employees.filter(company_id=company_id),
        )
    month_completions = completions.filter(
        completed_on__year=today.year, completed_on__month=today.month
    )
    total, passed = month_completions.count(), month_completions.filter(passed=True).count()
    readiness = [
        evaluate_employee_readiness(employee=e).status
        for e in employees.select_related("company", "branch", "department", "designation")
    ]
    return {
        "active_courses": courses.filter(status="ACTIVE").count(),
        "upcoming_sessions": sessions.filter(start_datetime__gt=now)
        .exclude(status="CANCELLED")
        .count(),
        "sessions_in_progress": sessions.filter(status=TrainingSessionStatus.IN_PROGRESS).count(),
        "employees_enrolled": enrollments.filter(
            status__in=[
                EnrollmentStatus.ENROLLED,
                EnrollmentStatus.CONFIRMED,
                EnrollmentStatus.IN_PROGRESS,
            ]
        ).count(),
        "training_completions_this_month": total,
        "pass_rate": str((passed * 100 / total) if total else 0),
        "failed_training_count": month_completions.filter(passed=False).count(),
        "valid_certifications": certificates.filter(status=CertificateStatus.VALID)
        .filter(models.Q(expires_on__isnull=True) | models.Q(expires_on__gte=today))
        .count(),
        "certifications_expiring_within_30_days": certificates.filter(
            status=CertificateStatus.VALID, expires_on__range=(today, today + timedelta(days=30))
        ).count(),
        "expired_certifications": certificates.filter(expires_on__lt=today).count(),
        "readiness": dict(Counter(readiness)),
        "pending_assessment_results": enrollments.filter(assessment_results__result="PENDING")
        .distinct()
        .count(),
    }


def guard_readiness_list(*, company_id: str | None = None) -> list[dict[str, Any]]:
    employees = Employee.objects.filter(
        employee_type__in=[EmployeeType.SECURITY_GUARD, EmployeeType.SUPERVISOR],
        employment_status="ACTIVE",
    ).select_related("company", "branch", "designation")
    if company_id:
        employees = employees.filter(company_id=company_id)
    return [
        {
            "employee_id": str(employee.pk),
            "employee_number": employee.employee_number,
            "full_name": employee.full_name,
            "company": employee.company.code,
            "branch": employee.branch.name if employee.branch else None,
            "designation": employee.designation.name if employee.designation else None,
            "readiness_status": (result := evaluate_employee_readiness(employee=employee)).status,
            "blocking_issue_count": len(result.blocking_issues),
            "warning_count": len(result.warnings),
        }
        for employee in employees
    ]


def training_exceptions(*, company_id: str | None = None) -> list[dict[str, str]]:
    sessions = TrainingSession.objects.filter(
        status=TrainingSessionStatus.SCHEDULED, lead_instructor__isnull=True
    )
    external = __import__(
        "dsms.training.models", fromlist=["ExternalCertification"]
    ).ExternalCertification.objects.filter(verification_status="PENDING")
    if company_id:
        sessions, external = (
            sessions.filter(company_id=company_id),
            external.filter(company_id=company_id),
        )
    return [
        {"code": "SESSION_WITHOUT_INSTRUCTOR", "severity": "HIGH", "object_id": str(item.pk)}
        for item in sessions
    ] + [
        {"code": "EXTERNAL_CERTIFICATION_PENDING", "severity": "WARNING", "object_id": str(item.pk)}
        for item in external
    ]
