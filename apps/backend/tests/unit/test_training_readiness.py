# mypy: disable-error-code="misc,arg-type,attr-defined"
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from dsms.training.enums import (
    AssessmentType,
    CourseDeliveryMethod,
    CourseStatus,
    EnrollmentStatus,
    ReadinessStatus,
    RequirementLevel,
    TrainingAttendanceStatus,
    TrainingSessionStatus,
)
from dsms.training.exceptions import InvalidTrainingTransition
from dsms.training.models import (
    CourseQualificationOutcome,
    QualificationType,
    TrainingAssessment,
    TrainingCategory,
    TrainingCourse,
    TrainingEnrollment,
    TrainingRequirement,
    TrainingSession,
    TrainingSessionParticipation,
)
from dsms.training.services import (
    create_course_version,
    evaluate_employee_readiness,
    finalize_training_result,
    record_assessment_result,
)
from dsms.workforce.enums import EmploymentStatus
from tests.factories.identity import UserFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_training_completion_grants_qualification_certificate_and_readiness() -> None:
    today = timezone.localdate()
    actor = UserFactory()
    employee = EmployeeFactory(employment_status=EmploymentStatus.ACTIVE)
    category = TrainingCategory.objects.create(company=employee.company, code="basic", name="Basic")
    course = TrainingCourse.objects.create(
        company=employee.company,
        category=category,
        code="guard-basic",
        title="Basic Guard Training",
        description="Core guard skills",
        delivery_method=CourseDeliveryMethod.BLENDED,
        duration_hours=Decimal("8"),
        minimum_pass_percentage=Decimal("60"),
        minimum_attendance_percentage=Decimal("100"),
        requires_assessment=True,
        produces_certificate=True,
        status=CourseStatus.ACTIVE,
    )
    version = create_course_version(
        course=course, actor=actor, effective_from=today, syllabus_summary="Version one"
    )
    qualification = QualificationType.objects.create(
        company=employee.company, code="general_guarding", name="General Guarding"
    )
    CourseQualificationOutcome.objects.create(
        course=course, qualification_type=qualification, validity_months=12
    )
    TrainingRequirement.objects.create(
        company=employee.company,
        code="GUARD-BASIC",
        name="Basic guard qualification",
        employee_type=employee.employee_type,
        qualification_type=qualification,
        requirement_level=RequirementLevel.MANDATORY,
        effective_from=today,
    )
    assert (
        evaluate_employee_readiness(employee=employee, as_of_date=today).status
        == ReadinessStatus.NOT_READY
    )
    session = TrainingSession.objects.create(
        company=employee.company,
        session_number="TS-0001",
        course=course,
        course_version=version,
        # Keep the session on the same calendar day so the attendance assertion
        # remains deterministic when the suite runs shortly after midnight.
        start_datetime=timezone.now() - timedelta(minutes=30),
        end_datetime=timezone.now(),
        status=TrainingSessionStatus.COMPLETED,
        created_by=actor,
    )
    enrollment = TrainingEnrollment.objects.create(
        session=session,
        employee=employee,
        company=employee.company,
        status=EnrollmentStatus.IN_PROGRESS,
        enrolled_by=actor,
    )
    TrainingSessionParticipation.objects.create(
        enrollment=enrollment,
        attendance_date=today,
        attendance_status=TrainingAttendanceStatus.PRESENT,
        recorded_by=actor,
    )
    assessment = TrainingAssessment.objects.create(
        session=session,
        name="Final",
        assessment_type=AssessmentType.WRITTEN,
        maximum_score=Decimal("100"),
        passing_score=Decimal("60"),
        is_mandatory=True,
    )
    record_assessment_result(
        enrollment=enrollment,
        assessment_id=str(assessment.pk),
        score=Decimal("80"),
        evaluator=actor,
    )
    completion = finalize_training_result(enrollment=enrollment, actor=actor)
    assert completion.passed
    assert employee.qualifications.filter(qualification_type=qualification).exists()
    assert employee.training_certificates.filter(training_completion=completion).exists()
    assert (
        evaluate_employee_readiness(employee=employee, as_of_date=today).status
        == ReadinessStatus.READY
    )
    with pytest.raises(InvalidTrainingTransition):
        finalize_training_result(enrollment=enrollment, actor=actor)
