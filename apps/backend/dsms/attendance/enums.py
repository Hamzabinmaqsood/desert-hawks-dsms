from django.db import models


class AttendanceRecordStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    EXCEPTION = "EXCEPTION", "Exception"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    LOCKED = "LOCKED", "Locked"


class AttendanceOutcome(models.TextChoices):
    ON_TIME = "ON_TIME", "On time"
    LATE = "LATE", "Late"
    EARLY_DEPARTURE = "EARLY_DEPARTURE", "Early departure"
    LATE_AND_EARLY = "LATE_AND_EARLY", "Late and early"
    ABSENT = "ABSENT", "Absent"
    PARTIAL = "PARTIAL", "Partial"
    UNVERIFIED = "UNVERIFIED", "Unverified"
    EXCUSED = "EXCUSED", "Excused"


class AttendanceEventType(models.TextChoices):
    CHECK_IN = "CHECK_IN", "Check in"
    CHECK_OUT = "CHECK_OUT", "Check out"
    BREAK_START = "BREAK_START", "Break start"
    BREAK_END = "BREAK_END", "Break end"
    SUPERVISOR_CONFIRMATION = "SUPERVISOR_CONFIRMATION", "Supervisor confirmation"
    MANUAL_EVENT = "MANUAL_EVENT", "Manual event"


class VerificationMethod(models.TextChoices):
    GPS = "GPS", "GPS"
    QR = "QR", "QR"
    FACE = "FACE", "Face"
    SUPERVISOR = "SUPERVISOR", "Supervisor"
    MANUAL = "MANUAL", "Manual"


class VerificationResult(models.TextChoices):
    PASSED = "PASSED", "Passed"
    FAILED = "FAILED", "Failed"
    WARNING = "WARNING", "Warning"
    NOT_REQUIRED = "NOT_REQUIRED", "Not required"


class ExceptionStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    RESOLVED = "RESOLVED", "Resolved"
    DISMISSED = "DISMISSED", "Dismissed"


class CorrectionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    CANCELLED = "CANCELLED", "Cancelled"


class AttendancePeriodStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    LOCKED = "LOCKED", "Locked"
    CLOSED = "CLOSED", "Closed"


class QRStationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    REVOKED = "REVOKED", "Revoked"
    INACTIVE = "INACTIVE", "Inactive"
