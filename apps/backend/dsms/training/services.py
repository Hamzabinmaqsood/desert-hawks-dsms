from __future__ import annotations

import calendar
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Q, QuerySet
from django.utils import timezone

from dsms.identity.models import User
from dsms.subscriptions.enforcement import requires_company_module
from dsms.workforce.enums import EmploymentStatus
from dsms.workforce.models import Employee

from .enums import (
    AssessmentResult,
    CertificateStatus,
    CompletionStatus,
    CourseStatus,
    EnrollmentStatus,
    QualificationSource,
    QualificationStatus,
    ReadinessIssueSeverity,
    ReadinessStatus,
    RequirementLevel,
    TrainingAttendanceStatus,
    TrainingSessionStatus,
)
from .exceptions import CapacityExceeded, InvalidTrainingTransition, TrainingValidationError
from .models import (
    CourseQualificationOutcome,
    EmployeeQualification,
    EmployeeTrainingAssessmentResult,
    TrainingCertificate,
    TrainingCompletion,
    TrainingCourse,
    TrainingCourseVersion,
    TrainingEnrollment,
    TrainingRequirement,
    TrainingRequirementWaiver,
    TrainingSession,
)


def _add_months(value: date, months: int | None) -> date | None:
    if not months:
        return None
    month = value.month - 1 + months
    year, month = value.year + month // 12, month % 12 + 1
    return value.replace(
        year=year, month=month, day=min(value.day, calendar.monthrange(year, month)[1])
    )


@transaction.atomic
@requires_company_module("learning", argument="course")
def create_course_version(
    *,
    course: TrainingCourse,
    actor: User,
    effective_from: date,
    syllabus_summary: str,
    duration_hours: Decimal | None = None,
    minimum_pass_percentage: Decimal | None = None,
    minimum_attendance_percentage: Decimal | None = None,
) -> TrainingCourseVersion:
    course = TrainingCourse.objects.select_for_update().get(pk=course.pk)
    current = TrainingCourseVersion.objects.filter(course=course, is_current=True).first()
    next_number = (
        TrainingCourseVersion.objects.filter(course=course)
        .order_by("-version_number")
        .values_list("version_number", flat=True)
        .first()
        or 0
    ) + 1
    if current:
        current.is_current = False
        current.effective_to = effective_from
        current.save(update_fields=["is_current", "effective_to"])
    return TrainingCourseVersion.objects.create(
        course=course,
        version_number=next_number,
        effective_from=effective_from,
        syllabus_summary=syllabus_summary,
        duration_hours=duration_hours or course.duration_hours,
        minimum_pass_percentage=minimum_pass_percentage
        if minimum_pass_percentage is not None
        else course.minimum_pass_percentage,
        minimum_attendance_percentage=minimum_attendance_percentage
        if minimum_attendance_percentage is not None
        else course.minimum_attendance_percentage,
        is_current=True,
        created_by=actor,
    )


@requires_company_module("learning", argument="course")
def activate_training_course(*, course: TrainingCourse) -> TrainingCourse:
    if not course.versions.filter(is_current=True).exists():
        raise TrainingValidationError("A current course version is required before activation.")
    course.status = CourseStatus.ACTIVE
    course.save(update_fields=["status", "updated_at"])
    return course


@transaction.atomic
@requires_company_module("learning", argument="session")
def schedule_training_session(*, session: TrainingSession) -> TrainingSession:
    session = (
        TrainingSession.objects.select_for_update()
        .select_related("course", "course_version", "venue")
        .get(pk=session.pk)
    )
    if (
        session.status != TrainingSessionStatus.DRAFT
        or session.course.status != CourseStatus.ACTIVE
    ):
        raise InvalidTrainingTransition("Only draft sessions for active courses can be scheduled.")
    if (
        session.course_version.course_id != session.course_id
        or session.end_datetime <= session.start_datetime
    ):
        raise TrainingValidationError("Session version and date range are invalid.")
    if session.venue and not session.venue.is_active:
        raise TrainingValidationError("Inactive venues cannot receive sessions.")
    session.status = TrainingSessionStatus.SCHEDULED
    session.save(update_fields=["status", "updated_at"])
    return session


@transaction.atomic
@requires_company_module("learning", argument="session")
def enroll_employee(
    *, session: TrainingSession, employee: Employee, actor: User, allow_waitlist: bool = True
) -> TrainingEnrollment:
    session = TrainingSession.objects.select_for_update().get(pk=session.pk)
    if session.status != TrainingSessionStatus.OPEN_FOR_ENROLLMENT:
        raise InvalidTrainingTransition("Session is not open for enrollment.")
    if employee.company_id != session.company_id or employee.employment_status in {
        EmploymentStatus.RESIGNED,
        EmploymentStatus.TERMINATED,
        EmploymentStatus.RETIRED,
        EmploymentStatus.ABSCONDED,
        EmploymentStatus.SUSPENDED,
    }:
        raise TrainingValidationError("Employee is not eligible for this training session.")
    enrolled = session.enrollments.exclude(
        status__in=[
            EnrollmentStatus.WAITLISTED,
            EnrollmentStatus.WITHDRAWN,
            EnrollmentStatus.CANCELLED,
        ]
    ).count()
    status = EnrollmentStatus.ENROLLED
    if session.capacity is not None and enrolled >= session.capacity:
        if not allow_waitlist:
            raise CapacityExceeded("Training session capacity has been reached.")
        status = EnrollmentStatus.WAITLISTED
    return TrainingEnrollment.objects.create(
        session=session,
        employee=employee,
        company=session.company,
        status=status,
        enrolled_by=actor,
    )


@transaction.atomic
@requires_company_module("learning", argument="enrollment")
def record_assessment_result(
    *,
    enrollment: TrainingEnrollment,
    assessment_id: str,
    score: Decimal,
    evaluator: User,
    remarks: str = "",
) -> EmployeeTrainingAssessmentResult:
    assessment = enrollment.session.assessments.get(pk=assessment_id)
    if score < 0 or score > assessment.maximum_score:
        raise TrainingValidationError("Score must be between zero and the assessment maximum.")
    percentage = (score / assessment.maximum_score * Decimal("100")).quantize(Decimal("0.01"))
    result = AssessmentResult.PASS if score >= assessment.passing_score else AssessmentResult.FAIL
    return EmployeeTrainingAssessmentResult.objects.create(
        assessment=assessment,
        enrollment=enrollment,
        employee=enrollment.employee,
        score=score,
        percentage=percentage,
        result=result,
        evaluator=evaluator,
        remarks=remarks,
    )


@transaction.atomic
@requires_company_module("learning", argument="enrollment")
def finalize_training_result(*, enrollment: TrainingEnrollment, actor: User) -> TrainingCompletion:
    enrollment = (
        TrainingEnrollment.objects.select_for_update()
        .select_related("session__course", "session__course_version", "employee")
        .get(pk=enrollment.pk)
    )
    if hasattr(enrollment, "completion"):
        raise InvalidTrainingTransition("Training result is already finalized.")
    session, course, version = (
        enrollment.session,
        enrollment.session.course,
        enrollment.session.course_version,
    )
    if session.status not in {
        TrainingSessionStatus.IN_PROGRESS,
        TrainingSessionStatus.COMPLETED,
    } or enrollment.status in {
        EnrollmentStatus.WITHDRAWN,
        EnrollmentStatus.CANCELLED,
        EnrollmentStatus.WAITLISTED,
    }:
        raise InvalidTrainingTransition("Enrollment is not eligible for finalization.")
    mandatory = session.assessments.filter(is_mandatory=True)
    results = enrollment.assessment_results.filter(assessment__in=mandatory)
    if mandatory.count() != results.exclude(result=AssessmentResult.PENDING).count():
        raise TrainingValidationError("Every mandatory assessment requires a finalized result.")
    attendance_days = max((session.end_datetime.date() - session.start_datetime.date()).days + 1, 1)
    attended = enrollment.participation.filter(
        attendance_status__in=[TrainingAttendanceStatus.PRESENT, TrainingAttendanceStatus.LATE]
    ).count()
    attendance_percentage = Decimal(attended * 100) / Decimal(attendance_days)
    required_attendance = version.minimum_attendance_percentage or Decimal("0")
    assessment_passed = not results.filter(result=AssessmentResult.FAIL).exists()
    final_percentage = results.aggregate(value=Avg("percentage"))["value"]
    threshold = version.minimum_pass_percentage or Decimal("0")
    passed = (
        assessment_passed
        and attendance_percentage >= required_attendance
        and (final_percentage is None or final_percentage >= threshold)
    )
    completion = TrainingCompletion.objects.create(
        enrollment=enrollment,
        employee=enrollment.employee,
        course=course,
        course_version=version,
        session=session,
        completed_on=timezone.localdate(),
        final_percentage=final_percentage,
        passed=passed,
        completion_status=CompletionStatus.PASSED if passed else CompletionStatus.FAILED,
        approved_by=actor,
    )
    enrollment.status = EnrollmentStatus.COMPLETED if passed else EnrollmentStatus.FAILED
    enrollment.save(update_fields=["status", "updated_at"])
    if passed:
        for outcome in CourseQualificationOutcome.objects.filter(course=course).select_related(
            "qualification_type"
        ):
            expiry = _add_months(
                completion.completed_on, outcome.validity_months or course.validity_months
            )
            EmployeeQualification.objects.create(
                employee=enrollment.employee,
                company=enrollment.company,
                qualification_type=outcome.qualification_type,
                source=QualificationSource.TRAINING,
                source_training_completion=completion,
                obtained_on=completion.completed_on,
                valid_from=completion.completed_on,
                expires_on=expiry,
                status=QualificationStatus.VALID,
                verified_by=actor,
            )
        if course.produces_certificate:
            certificate_outcome = CourseQualificationOutcome.objects.filter(course=course).first()
            TrainingCertificate.objects.create(
                employee=enrollment.employee,
                training_completion=completion,
                company=enrollment.company,
                certificate_number=f"TC-{uuid.uuid4().hex[:12].upper()}",
                qualification_type=(
                    certificate_outcome.qualification_type if certificate_outcome else None
                ),
                issued_on=completion.completed_on,
                valid_from=completion.completed_on,
                expires_on=_add_months(
                    completion.completed_on,
                    (certificate_outcome.validity_months if certificate_outcome else None)
                    or course.validity_months,
                ),
                status=CertificateStatus.VALID,
                issued_by=actor,
            )
    return completion


@dataclass(frozen=True)
class ReadinessIssue:
    code: str
    severity: str
    requirement_id: str | None
    message: str
    expires_on: date | None = None
    days_remaining: int | None = None


@dataclass(frozen=True)
class ReadinessResult:
    employee: Employee
    status: str
    blocking_issues: tuple[ReadinessIssue, ...]
    warnings: tuple[ReadinessIssue, ...]
    requirements_checked: int
    requirements_satisfied: int
    requirements_missing: int


def applicable_requirements(*, employee: Employee, as_of_date: date) -> list[TrainingRequirement]:
    queryset = (
        TrainingRequirement.objects.filter(
            company=employee.company, is_active=True, effective_from__lte=as_of_date
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .filter(Q(employee_type="") | Q(employee_type=employee.employee_type))
        .filter(Q(designation__isnull=True) | Q(designation=employee.designation))
        .filter(Q(branch__isnull=True) | Q(branch=employee.branch))
        .filter(Q(department__isnull=True) | Q(department=employee.department))
        .select_related("course", "qualification_type")
    )
    return list(queryset)


def evaluate_employee_readiness(
    *, employee: Employee, as_of_date: date | None = None
) -> ReadinessResult:
    as_of = as_of_date or timezone.localdate()
    blocking: list[ReadinessIssue] = []
    warnings: list[ReadinessIssue] = []
    if (
        not employee.company.is_active
        or employee.employment_status != EmploymentStatus.ACTIVE
        or not employee.is_active
    ):
        blocking.append(
            ReadinessIssue(
                "EMPLOYEE_INACTIVE",
                ReadinessIssueSeverity.BLOCKING,
                None,
                "Employee is not in an active workforce state.",
            )
        )
    requirements = applicable_requirements(employee=employee, as_of_date=as_of)
    if not requirements and not blocking:
        return ReadinessResult(employee, ReadinessStatus.NOT_APPLICABLE, (), (), 0, 0, 0)
    satisfied = 0
    for requirement in requirements:
        waiver = TrainingRequirementWaiver.objects.filter(
            employee=employee,
            training_requirement=requirement,
            revoked_at__isnull=True,
            valid_from__lte=as_of,
            valid_until__gte=as_of,
        ).exists()
        qualification = (
            requirement.qualification_type
            and EmployeeQualification.objects.filter(
                employee=employee,
                qualification_type=requirement.qualification_type,
                status=QualificationStatus.VALID,
                obtained_on__lte=as_of,
            )
            .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=as_of))
            .exists()
        )
        completion = (
            requirement.course
            and TrainingCompletion.objects.filter(
                employee=employee, course=requirement.course, passed=True, completed_on__lte=as_of
            ).exists()
        )
        if waiver or qualification or completion:
            satisfied += 1
            continue
        expired_qualification = bool(
            requirement.qualification_type_id
            and EmployeeQualification.objects.filter(
                employee=employee,
                qualification_type=requirement.qualification_type,
                expires_on__lt=as_of,
            ).exists()
        )
        issue = ReadinessIssue(
            "EXPIRED_CERTIFICATION"
            if expired_qualification
            else "MISSING_REQUIRED_QUALIFICATION"
            if requirement.qualification_type_id
            else "MANDATORY_TRAINING_INCOMPLETE",
            ReadinessIssueSeverity.BLOCKING
            if requirement.requirement_level == RequirementLevel.MANDATORY
            else ReadinessIssueSeverity.WARNING,
            str(requirement.pk),
            f"Requirement '{requirement.name}' is not currently satisfied.",
        )
        (blocking if issue.severity == ReadinessIssueSeverity.BLOCKING else warnings).append(issue)
    status = (
        ReadinessStatus.NOT_READY
        if blocking
        else ReadinessStatus.CONDITIONALLY_READY
        if warnings
        else ReadinessStatus.READY
    )
    return ReadinessResult(
        employee,
        status,
        tuple(blocking),
        tuple(warnings),
        len(requirements),
        satisfied,
        len(requirements) - satisfied,
    )


def is_employee_ready_for_duty(
    employee: Employee, *, as_of_date: date | None = None
) -> ReadinessResult:
    return evaluate_employee_readiness(employee=employee, as_of_date=as_of_date)


def get_employee_qualifications(employee: Employee) -> QuerySet[EmployeeQualification]:
    return EmployeeQualification.objects.filter(employee=employee, status=QualificationStatus.VALID)
