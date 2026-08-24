from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.documents.models import EmployeeDocument
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation
from dsms.workforce.enums import EmployeeType
from dsms.workforce.models import Employee

from .enums import (
    AssessmentResult,
    AssessmentType,
    CertificateStatus,
    CompletionStatus,
    CourseDeliveryMethod,
    CourseStatus,
    EnrollmentStatus,
    QualificationSource,
    QualificationStatus,
    ReadinessStatus,
    RequirementLevel,
    TrainingAttendanceStatus,
    TrainingSessionStatus,
)


class TrainingModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class TrainingCategory(TrainingModel, ActiveModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(company__isnull=True),
                name="uniq_global_training_category",
            ),
            models.UniqueConstraint(
                fields=["company", "code"],
                condition=Q(company__isnull=False),
                name="uniq_company_training_category",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class TrainingCourse(TrainingModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    category = models.ForeignKey(TrainingCategory, on_delete=models.PROTECT, related_name="courses")
    code = models.CharField(max_length=50)
    title = models.CharField(max_length=200)
    description = models.TextField()
    objective = models.TextField(blank=True)
    delivery_method = models.CharField(max_length=20, choices=CourseDeliveryMethod.choices)
    duration_hours = models.DecimalField(max_digits=7, decimal_places=2)
    validity_months = models.PositiveIntegerField(null=True, blank=True)
    minimum_pass_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    minimum_attendance_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    requires_assessment = models.BooleanField(default=False)
    produces_certificate = models.BooleanField(default=False)
    is_mandatory_by_default = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20, choices=CourseStatus.choices, default=CourseStatus.DRAFT
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(company__isnull=True),
                name="uniq_global_training_course",
            ),
            models.UniqueConstraint(
                fields=["company", "code"],
                condition=Q(company__isnull=False),
                name="uniq_company_training_course",
            ),
            models.CheckConstraint(
                condition=Q(duration_hours__gt=0), name="training_course_duration_positive"
            ),
            models.CheckConstraint(
                condition=Q(minimum_pass_percentage__isnull=True)
                | Q(minimum_pass_percentage__gte=0, minimum_pass_percentage__lte=100),
                name="training_course_pass_range",
            ),
        ]
        permissions = [("manage_course_versions", "Can manage course versions")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class TrainingCourseVersion(UUIDModel):
    course = models.ForeignKey(TrainingCourse, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    syllabus_summary = models.TextField()
    duration_hours = models.DecimalField(max_digits=7, decimal_places=2)
    minimum_pass_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    minimum_attendance_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    is_current = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "version_number"], name="uniq_training_course_version"
            ),
            models.UniqueConstraint(
                fields=["course"],
                condition=Q(is_current=True),
                name="uniq_current_training_version",
            ),
        ]


class QualificationType(TrainingModel, ActiveModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.ForeignKey(TrainingCategory, null=True, blank=True, on_delete=models.PROTECT)
    requires_expiry = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(company__isnull=True),
                name="uniq_global_qualification_type",
            ),
            models.UniqueConstraint(
                fields=["company", "code"],
                condition=Q(company__isnull=False),
                name="uniq_company_qualification_type",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class CourseQualificationOutcome(TrainingModel):
    course = models.ForeignKey(
        TrainingCourse, on_delete=models.PROTECT, related_name="qualification_outcomes"
    )
    qualification_type = models.ForeignKey(QualificationType, on_delete=models.PROTECT)
    qualification_level = models.CharField(max_length=100, blank=True)
    validity_months = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["course", "qualification_type"], name="uniq_course_qualification_outcome"
            )
        ]


class TrainingRequirement(TrainingModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices, blank=True)
    designation = models.ForeignKey(Designation, null=True, blank=True, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    course = models.ForeignKey(TrainingCourse, null=True, blank=True, on_delete=models.PROTECT)
    qualification_type = models.ForeignKey(
        QualificationType, null=True, blank=True, on_delete=models.PROTECT
    )
    requirement_level = models.CharField(max_length=20, choices=RequirementLevel.choices)
    renewal_required = models.BooleanField(default=False)
    grace_period_days = models.PositiveIntegerField(default=0)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_training_requirement_code"
            ),
            models.CheckConstraint(
                condition=Q(course__isnull=False) | Q(qualification_type__isnull=False),
                name="training_requirement_has_target",
            ),
        ]
        permissions = [("manage_requirement_waivers", "Can manage training requirement waivers")]


class TrainingVenue(TrainingModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    address = models.TextField()
    city = models.CharField(max_length=100)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_training_venue_code")
        ]


class TrainingInstructor(TrainingModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.PROTECT)
    external_name = models.CharField(max_length=200, blank=True)
    external_organization = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    mobile_number = models.CharField(max_length=30, blank=True)
    qualifications_summary = models.TextField(blank=True)
    is_internal = models.BooleanField(default=False)

    def clean(self) -> None:
        if self.is_internal and not self.employee_id:
            raise ValidationError({"employee": "Internal instructors require an employee."})
        if not self.is_internal and not self.external_name:
            raise ValidationError({"external_name": "External instructors require a name."})


class TrainingProgram(TrainingModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField()
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices, blank=True)
    designation = models.ForeignKey(Designation, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_training_program_code")
        ]


class TrainingProgramCourse(UUIDModel):
    program = models.ForeignKey(
        TrainingProgram, on_delete=models.PROTECT, related_name="program_courses"
    )
    course = models.ForeignKey(TrainingCourse, on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    is_mandatory = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["program", "course"], name="uniq_program_course")
        ]


class TrainingSession(TrainingModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    session_number = models.CharField(max_length=50, unique=True)
    course = models.ForeignKey(TrainingCourse, on_delete=models.PROTECT, related_name="sessions")
    course_version = models.ForeignKey(TrainingCourseVersion, on_delete=models.PROTECT)
    program = models.ForeignKey(TrainingProgram, null=True, blank=True, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    venue = models.ForeignKey(TrainingVenue, null=True, blank=True, on_delete=models.PROTECT)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()
    enrollment_deadline = models.DateTimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=TrainingSessionStatus.choices, default=TrainingSessionStatus.DRAFT
    )
    lead_instructor = models.ForeignKey(
        TrainingInstructor, null=True, blank=True, on_delete=models.PROTECT
    )
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)


class TrainingSessionInstructor(UUIDModel):
    session = models.ForeignKey(
        TrainingSession, on_delete=models.PROTECT, related_name="session_instructors"
    )
    instructor = models.ForeignKey(TrainingInstructor, on_delete=models.PROTECT)
    role = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "instructor"], name="uniq_session_instructor"
            )
        ]


class TrainingEnrollment(TrainingModel):
    session = models.ForeignKey(
        TrainingSession, on_delete=models.PROTECT, related_name="enrollments"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="training_enrollments"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ENROLLED
    )
    enrolled_by = models.ForeignKey(User, on_delete=models.PROTECT)
    enrolled_at = models.DateTimeField(default=timezone.now)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["session", "employee"], name="uniq_training_enrollment")
        ]


class TrainingSessionParticipation(TrainingModel):
    enrollment = models.ForeignKey(
        TrainingEnrollment, on_delete=models.PROTECT, related_name="participation"
    )
    attendance_date = models.DateField()
    attendance_status = models.CharField(max_length=20, choices=TrainingAttendanceStatus.choices)
    check_in_time = models.TimeField(null=True, blank=True)
    check_out_time = models.TimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    remarks = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["enrollment", "attendance_date"], name="uniq_training_attendance_date"
            )
        ]


class TrainingAssessment(TrainingModel):
    session = models.ForeignKey(
        TrainingSession, on_delete=models.PROTECT, related_name="assessments"
    )
    name = models.CharField(max_length=150)
    assessment_type = models.CharField(max_length=20, choices=AssessmentType.choices)
    maximum_score = models.DecimalField(max_digits=8, decimal_places=2)
    passing_score = models.DecimalField(max_digits=8, decimal_places=2)
    weight_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    assessment_date = models.DateField(null=True, blank=True)
    is_mandatory = models.BooleanField(default=True)


class EmployeeTrainingAssessmentResult(TrainingModel):
    assessment = models.ForeignKey(
        TrainingAssessment, on_delete=models.PROTECT, related_name="results"
    )
    enrollment = models.ForeignKey(
        TrainingEnrollment, on_delete=models.PROTECT, related_name="assessment_results"
    )
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    result = models.CharField(
        max_length=10, choices=AssessmentResult.choices, default=AssessmentResult.PENDING
    )
    evaluator = models.ForeignKey(User, on_delete=models.PROTECT)
    evaluated_at = models.DateTimeField(default=timezone.now)
    remarks = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "enrollment"], name="uniq_training_assessment_result"
            )
        ]


class TrainingCompletion(UUIDModel):
    enrollment = models.OneToOneField(
        TrainingEnrollment, on_delete=models.PROTECT, related_name="completion"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="training_completions"
    )
    course = models.ForeignKey(TrainingCourse, on_delete=models.PROTECT)
    course_version = models.ForeignKey(TrainingCourseVersion, on_delete=models.PROTECT)
    session = models.ForeignKey(
        TrainingSession, on_delete=models.PROTECT, related_name="completions"
    )
    completed_on = models.DateField()
    final_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    passed = models.BooleanField()
    completion_status = models.CharField(max_length=20, choices=CompletionStatus.choices)
    approved_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("finalize_training_result", "Can finalize training results")]


class EmployeeQualification(TrainingModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="qualifications")
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    qualification_type = models.ForeignKey(QualificationType, on_delete=models.PROTECT)
    source = models.CharField(max_length=30, choices=QualificationSource.choices)
    source_training_completion = models.ForeignKey(
        TrainingCompletion, null=True, blank=True, on_delete=models.PROTECT
    )
    obtained_on = models.DateField()
    valid_from = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=QualificationStatus.choices, default=QualificationStatus.PENDING
    )
    notes = models.TextField(blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)

    @property
    def is_expired(self) -> bool:
        return self.expires_on is not None and self.expires_on < timezone.localdate()

    @property
    def is_valid(self) -> bool:
        today = timezone.localdate()
        return (
            self.status == QualificationStatus.VALID
            and not self.is_expired
            and (self.valid_from is None or self.valid_from <= today)
        )

    @property
    def days_until_expiry(self) -> int | None:
        return None if self.expires_on is None else (self.expires_on - timezone.localdate()).days


class TrainingCertificate(TrainingModel):
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="training_certificates"
    )
    training_completion = models.ForeignKey(
        TrainingCompletion, on_delete=models.PROTECT, related_name="certificates"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    certificate_number = models.CharField(max_length=50, unique=True)
    qualification_type = models.ForeignKey(
        QualificationType, null=True, blank=True, on_delete=models.PROTECT
    )
    employee_document = models.ForeignKey(
        EmployeeDocument, null=True, blank=True, on_delete=models.PROTECT
    )
    issued_on = models.DateField()
    valid_from = models.DateField()
    expires_on = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=CertificateStatus.choices, default=CertificateStatus.VALID
    )
    issued_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="issued_training_certificates",
    )
    revoked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="revoked_training_certificates",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)
    superseded_by = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="supersedes"
    )

    class Meta:
        permissions = [
            ("issue_certificate", "Can issue training certificates"),
            ("revoke_certificate", "Can revoke training certificates"),
        ]

    @property
    def is_expired(self) -> bool:
        return self.expires_on is not None and self.expires_on < timezone.localdate()

    @property
    def is_valid(self) -> bool:
        today = timezone.localdate()
        return (
            self.status == CertificateStatus.VALID
            and self.valid_from <= today
            and not self.is_expired
        )

    @property
    def days_until_expiry(self) -> int | None:
        return None if self.expires_on is None else (self.expires_on - timezone.localdate()).days

    def is_expiring_soon(self, days: int = 30) -> bool:
        remaining = self.days_until_expiry
        return remaining is not None and 0 <= remaining <= days


class ExternalCertification(TrainingModel):
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="external_certifications"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    qualification_type = models.ForeignKey(QualificationType, on_delete=models.PROTECT)
    certificate_name = models.CharField(max_length=200)
    certificate_number = models.CharField(max_length=100, blank=True)
    issuing_authority = models.CharField(max_length=200)
    issued_on = models.DateField(null=True, blank=True)
    expires_on = models.DateField(null=True, blank=True)
    verification_status = models.CharField(
        max_length=20, choices=QualificationStatus.choices, default=QualificationStatus.PENDING
    )
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    verified_at = models.DateTimeField(null=True, blank=True)
    employee_document = models.ForeignKey(
        EmployeeDocument, null=True, blank=True, on_delete=models.PROTECT
    )


class TrainingRequirementWaiver(TrainingModel):
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="training_waivers"
    )
    training_requirement = models.ForeignKey(
        TrainingRequirement, on_delete=models.PROTECT, related_name="waivers"
    )
    valid_from = models.DateField()
    valid_until = models.DateField()
    reason = models.TextField()
    approved_by = models.ForeignKey(User, on_delete=models.PROTECT)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="revoked_training_waivers",
    )


class EmployeeReadinessSnapshot(UUIDModel):
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="readiness_snapshots"
    )
    calculated_at = models.DateTimeField(auto_now_add=True)
    readiness_status = models.CharField(max_length=30, choices=ReadinessStatus.choices)
    blocking_issue_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [
            ("view_training_dashboard", "Can view training dashboard"),
            ("view_readiness", "Can view workforce readiness"),
            ("view_training_reports", "Can view training reports"),
            ("view_training_audit", "Can view training audit"),
        ]
