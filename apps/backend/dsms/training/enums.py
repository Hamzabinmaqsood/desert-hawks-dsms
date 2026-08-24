from django.db import models


class CourseStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    RETIRED = "RETIRED", "Retired"


class CourseDeliveryMethod(models.TextChoices):
    CLASSROOM = "CLASSROOM", "Classroom"
    PRACTICAL = "PRACTICAL", "Practical"
    FIELD = "FIELD", "Field"
    ONLINE = "ONLINE", "Online"
    BLENDED = "BLENDED", "Blended"
    OTHER = "OTHER", "Other"


class TrainingSessionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SCHEDULED = "SCHEDULED", "Scheduled"
    OPEN_FOR_ENROLLMENT = "OPEN_FOR_ENROLLMENT", "Open for enrollment"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class EnrollmentStatus(models.TextChoices):
    ENROLLED = "ENROLLED", "Enrolled"
    WAITLISTED = "WAITLISTED", "Waitlisted"
    CONFIRMED = "CONFIRMED", "Confirmed"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No show"


class TrainingAttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    LATE = "LATE", "Late"
    EXCUSED = "EXCUSED", "Excused"


class AssessmentType(models.TextChoices):
    WRITTEN = "WRITTEN", "Written"
    PRACTICAL = "PRACTICAL", "Practical"
    PHYSICAL = "PHYSICAL", "Physical"
    ORAL = "ORAL", "Oral"
    SCENARIO = "SCENARIO", "Scenario"
    OTHER = "OTHER", "Other"


class AssessmentResult(models.TextChoices):
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    PENDING = "PENDING", "Pending"


class CertificateStatus(models.TextChoices):
    VALID = "VALID", "Valid"
    SUSPENDED = "SUSPENDED", "Suspended"
    REVOKED = "REVOKED", "Revoked"
    SUPERSEDED = "SUPERSEDED", "Superseded"


class QualificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    VALID = "VALID", "Valid"
    SUSPENDED = "SUSPENDED", "Suspended"
    REVOKED = "REVOKED", "Revoked"
    SUPERSEDED = "SUPERSEDED", "Superseded"


class RequirementLevel(models.TextChoices):
    MANDATORY = "MANDATORY", "Mandatory"
    RECOMMENDED = "RECOMMENDED", "Recommended"
    OPTIONAL = "OPTIONAL", "Optional"


class ReadinessStatus(models.TextChoices):
    READY = "READY", "Ready"
    CONDITIONALLY_READY = "CONDITIONALLY_READY", "Conditionally ready"
    NOT_READY = "NOT_READY", "Not ready"
    NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"


class ReadinessIssueSeverity(models.TextChoices):
    INFO = "INFO", "Info"
    WARNING = "WARNING", "Warning"
    BLOCKING = "BLOCKING", "Blocking"


class QualificationSource(models.TextChoices):
    TRAINING = "TRAINING", "Training"
    EXTERNAL_CERTIFICATION = "EXTERNAL_CERTIFICATION", "External certification"
    EXPERIENCE = "EXPERIENCE", "Experience"
    MANUAL_VERIFICATION = "MANUAL_VERIFICATION", "Manual verification"
    OTHER = "OTHER", "Other"


class CompletionStatus(models.TextChoices):
    PASSED = "PASSED", "Passed"
    FAILED = "FAILED", "Failed"
    INCOMPLETE = "INCOMPLETE", "Incomplete"
