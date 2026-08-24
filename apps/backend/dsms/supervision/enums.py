# mypy: disable-error-code="no-untyped-def,call-overload,no-untyped-call"
from django.db import models


def choices(name, values):
    return models.TextChoices(name, {value: value for value in values})


SupervisionAssignmentStatus = choices(
    "SupervisionAssignmentStatus", ["DRAFT", "ACTIVE", "SUSPENDED", "ENDED", "CANCELLED"]
)
SupervisionScopeType = choices("SupervisionScopeType", ["BRANCH", "OPERATIONAL_ZONE", "SITE"])
FrequencyPeriod = choices("FrequencyPeriod", ["DAY", "WEEK", "MONTH"])
VisitPlanStatus = choices(
    "VisitPlanStatus", ["DRAFT", "SCHEDULED", "IN_PROGRESS", "COMPLETED", "MISSED", "CANCELLED"]
)
VisitPriority = choices("VisitPriority", ["LOW", "NORMAL", "HIGH", "URGENT"])
SiteVisitStatus = choices(
    "SiteVisitStatus", ["IN_PROGRESS", "COMPLETED", "INCOMPLETE", "CANCELLED"]
)
VisitVerificationMethod = choices(
    "VisitVerificationMethod", ["GPS", "SUPERVISOR_MANUAL", "CONTROL_ROOM_CONFIRMATION", "OTHER"]
)
VisitVerificationResult = choices(
    "VisitVerificationResult", ["VERIFIED", "WARNING", "FAILED", "NOT_REQUIRED"]
)
InspectionScope = choices("InspectionScope", ["SITE", "POST", "GUARD"])
InspectionStatus = choices(
    "InspectionStatus", ["DRAFT", "IN_PROGRESS", "SUBMITTED", "REVIEWED", "CLOSED", "CANCELLED"]
)
InspectionResult = choices(
    "InspectionResult",
    ["SATISFACTORY", "NEEDS_IMPROVEMENT", "UNSATISFACTORY", "CRITICAL_ATTENTION"],
)
ChecklistResponseType = choices(
    "ChecklistResponseType",
    ["YES_NO", "PASS_FAIL", "SCORE", "TEXT", "NUMBER", "CHOICE", "PHOTO_REQUIRED"],
)
FindingSeverity = choices("FindingSeverity", ["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"])
FindingStatus = choices(
    "FindingStatus",
    ["OPEN", "ACKNOWLEDGED", "ACTION_ASSIGNED", "RESOLVED", "VERIFIED", "CLOSED", "DISMISSED"],
)
CorrectiveActionStatus = choices(
    "CorrectiveActionStatus",
    [
        "OPEN",
        "ASSIGNED",
        "IN_PROGRESS",
        "PENDING_VERIFICATION",
        "VERIFIED",
        "CLOSED",
        "CANCELLED",
        "OVERDUE",
    ],
)
CorrectiveActionPriority = VisitPriority
GuardObservationStatus = choices(
    "GuardObservationStatus",
    [
        "PRESENT_AS_SCHEDULED",
        "PRESENT_DIFFERENT_POST",
        "REPLACEMENT_PRESENT",
        "UNSCHEDULED_EMPLOYEE_PRESENT",
        "NOT_FOUND",
        "OFF_DUTY",
        "UNABLE_TO_VERIFY",
    ],
)
DailyReportStatus = choices(
    "DailyReportStatus", ["DRAFT", "SUBMITTED", "REVIEWED", "APPROVED", "RETURNED"]
)
ObservationCategory = choices(
    "ObservationCategory",
    [
        "SECURITY",
        "HOUSEKEEPING",
        "ACCESS_CONTROL",
        "LIGHTING",
        "PERIMETER",
        "EQUIPMENT",
        "DOCUMENTATION",
        "CLIENT_FEEDBACK",
        "OTHER",
    ],
)
