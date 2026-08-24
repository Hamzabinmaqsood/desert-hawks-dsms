# mypy: disable-error-code="no-untyped-def,no-untyped-call,call-overload"
# ruff: noqa: E501
from django.db import models


def choices(name, values):
    return models.TextChoices(name, {value: value for value in values})


IncidentStatus = choices(
    "IncidentStatus",
    [
        "NEW",
        "ACKNOWLEDGED",
        "TRIAGED",
        "RESPONDING",
        "CONTAINED",
        "UNDER_INVESTIGATION",
        "RESOLVED",
        "CLOSED",
        "REOPENED",
        "CANCELLED",
    ],
)
IncidentSeverity = choices("IncidentSeverity", ["LOW", "MEDIUM", "HIGH", "CRITICAL"])
IncidentPriority = choices("IncidentPriority", ["LOW", "NORMAL", "HIGH", "URGENT", "EMERGENCY"])
IncidentSource = choices(
    "IncidentSource",
    [
        "GUARD",
        "SUPERVISOR",
        "CONTROL_ROOM",
        "PATROL",
        "INSPECTION",
        "ATTENDANCE",
        "CLIENT",
        "MANAGEMENT",
        "SYSTEM_EXCEPTION",
        "OTHER",
    ],
)
IncidentVerificationStatus = choices(
    "IncidentVerificationStatus", ["UNVERIFIED", "PARTIALLY_VERIFIED", "VERIFIED", "DISPUTED"]
)
SOSStatus = choices(
    "SOSStatus",
    [
        "TRIGGERED",
        "ACKNOWLEDGED",
        "LINKED_TO_INCIDENT",
        "CANCELLED_BY_REPORTER",
        "FALSE_ALARM_CONFIRMED",
        "CLOSED",
    ],
)
SOSActivationMethod = choices(
    "SOSActivationMethod", ["MOBILE_APP", "SUPERVISOR", "CONTROL_ROOM", "MANUAL", "OTHER"]
)
IncidentEventType = choices(
    "IncidentEventType",
    [
        "CREATED",
        "SOS_TRIGGERED",
        "ACKNOWLEDGED",
        "TRIAGED",
        "SEVERITY_CHANGED",
        "PRIORITY_CHANGED",
        "OWNER_ASSIGNED",
        "RESPONDER_ASSIGNED",
        "RESPONDER_UPDATED",
        "ACTION_CREATED",
        "ACTION_COMPLETED",
        "ESCALATED",
        "CONTACT_ATTEMPTED",
        "CLIENT_NOTIFIED",
        "MANAGEMENT_NOTIFIED",
        "EVIDENCE_ADDED",
        "LOCATION_UPDATED",
        "STATUS_CHANGED",
        "CONTAINED",
        "RESOLVED",
        "CLOSED",
        "REOPENED",
        "COMMENT_ADDED",
        "REVIEW_COMPLETED",
        "OTHER",
    ],
)
ResponderStatus = choices(
    "ResponderStatus",
    ["ASSIGNED", "ACKNOWLEDGED", "EN_ROUTE", "ON_SCENE", "COMPLETED", "CANCELLED", "UNAVAILABLE"],
)
ResponderRole = choices(
    "ResponderRole",
    [
        "SUPERVISOR",
        "OPERATIONS_MANAGER",
        "CONTROL_ROOM",
        "RELIEF_TEAM",
        "MANAGEMENT",
        "MEDICAL_SUPPORT",
        "OTHER",
    ],
)
IncidentActionStatus = choices(
    "IncidentActionStatus", ["OPEN", "ASSIGNED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "BLOCKED"]
)
IncidentActionPriority = choices("IncidentActionPriority", ["LOW", "NORMAL", "HIGH", "URGENT"])
ContactAttemptMethod = choices(
    "ContactAttemptMethod", ["PHONE", "SMS", "EMAIL", "RADIO", "IN_PERSON", "WHATSAPP", "OTHER"]
)
ContactAttemptResult = choices(
    "ContactAttemptResult",
    ["ANSWERED", "NO_ANSWER", "BUSY", "FAILED", "MESSAGE_LEFT", "ACKNOWLEDGED", "OTHER"],
)
PersonInvolvementType = choices(
    "PersonInvolvementType",
    [
        "REPORTER",
        "GUARD",
        "SUPERVISOR",
        "CLIENT_CONTACT",
        "VICTIM",
        "WITNESS",
        "SUSPECTED_OFFENDER",
        "RESPONDER",
        "OTHER",
    ],
)
DamageType = choices("DamageType", ["NONE", "PROPERTY", "VEHICLE", "EQUIPMENT", "OTHER"])
InjurySeverity = choices(
    "InjurySeverity", ["NONE", "MINOR", "MODERATE", "SERIOUS", "CRITICAL", "FATAL_REPORTED"]
)
LocationSource = choices(
    "LocationSource",
    ["SOS", "REPORTER", "RESPONDER", "PATROL", "ATTENDANCE", "SUPERVISION", "MANUAL"],
)
EvidenceType = choices(
    "EvidenceType",
    ["PHOTO", "VIDEO_REFERENCE", "DOCUMENT", "AUDIO_REFERENCE", "CCTV_REFERENCE", "OTHER"],
)
