# mypy: disable-error-code="no-untyped-def,call-overload,no-untyped-call"
from django.db import models


def choices(name, values):
    return models.TextChoices(name, {value: value for value in values})


CheckpointStatus = choices("CheckpointStatus", ["ACTIVE", "INACTIVE", "REVOKED", "RETIRED"])
CheckpointType = choices(
    "CheckpointType",
    [
        "GENERAL",
        "GATE",
        "PERIMETER",
        "BUILDING",
        "ROOM",
        "EQUIPMENT_AREA",
        "PARKING",
        "CONTROL_ROOM",
        "WAREHOUSE",
        "ATM",
        "OTHER",
    ],
)
CheckpointVerificationMethod = choices(
    "CheckpointVerificationMethod", ["QR", "NFC", "GPS", "SUPERVISOR", "MANUAL"]
)
CheckpointVerificationResult = choices(
    "CheckpointVerificationResult", ["VERIFIED", "WARNING", "FAILED", "NOT_REQUIRED"]
)
PatrolRouteStatus = choices("PatrolRouteStatus", ["DRAFT", "ACTIVE", "INACTIVE", "RETIRED"])
PatrolOrderMode = choices("PatrolOrderMode", ["STRICT", "FLEXIBLE"])
PatrolRequirementStatus = choices(
    "PatrolRequirementStatus", ["DRAFT", "ACTIVE", "SUSPENDED", "SUPERSEDED", "EXPIRED"]
)
PatrolTaskStatus = choices(
    "PatrolTaskStatus",
    ["SCHEDULED", "READY", "IN_PROGRESS", "COMPLETED", "INCOMPLETE", "MISSED", "CANCELLED"],
)
PatrolRunStatus = choices("PatrolRunStatus", ["IN_PROGRESS", "COMPLETED", "INCOMPLETE", "ABORTED"])
CheckpointVisitStatus = choices("CheckpointVisitStatus", ["VERIFIED", "WARNING", "FAILED"])
PatrolExceptionStatus = choices(
    "PatrolExceptionStatus", ["OPEN", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"]
)
PatrolObservationSeverity = choices(
    "PatrolObservationSeverity", ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
)
PatrolEventType = choices(
    "PatrolEventType",
    [
        "START",
        "CHECKPOINT",
        "OBSERVATION",
        "PAUSE",
        "RESUME",
        "END",
        "ABORT",
        "SUPERVISOR_VERIFICATION",
        "MANUAL_EVENT",
    ],
)
PatrolReviewResult = choices(
    "PatrolReviewResult",
    ["ACCEPTED", "ACCEPTED_WITH_EXCEPTIONS", "REQUIRES_FOLLOW_UP", "REJECTED_AS_COMPLIANT_RECORD"],
)
Weekday = choices(
    "Weekday", ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
)
PatrolObservationCategory = choices(
    "PatrolObservationCategory",
    [
        "SECURITY",
        "ACCESS_CONTROL",
        "PERIMETER",
        "LIGHTING",
        "DOOR_OR_GATE",
        "EQUIPMENT",
        "FIRE_SAFETY",
        "HOUSEKEEPING",
        "UNUSUAL_ACTIVITY",
        "CLIENT_CONCERN",
        "OTHER",
    ],
)
PatrolExceptionType = choices(
    "PatrolExceptionType",
    [
        "MISSED_PATROL",
        "LATE_PATROL_START",
        "EARLY_PATROL_START",
        "MISSED_CHECKPOINT",
        "LATE_CHECKPOINT",
        "CHECKPOINT_OUT_OF_ORDER",
        "CHECKPOINT_TOO_FAST",
        "CHECKPOINT_TOO_SLOW",
        "OUTSIDE_CHECKPOINT_GEOFENCE",
        "GPS_LOW_ACCURACY",
        "GPS_UNAVAILABLE",
        "QR_INVALID",
        "QR_REVOKED",
        "QR_EXPIRED",
        "NFC_INVALID",
        "OFFLINE_SUBMISSION",
        "DUPLICATE_EVENT",
        "ROUTE_INCOMPLETE",
        "ASSIGNMENT_MISMATCH",
        "EMPLOYEE_NOT_ON_DUTY",
        "PATROL_OVERRUN",
        "PATROL_INTERRUPTED",
        "UNVERIFIED_CHECKPOINT",
        "OTHER",
    ],
)
