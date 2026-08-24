from django.db import models


class MembershipStatus(models.TextChoices):
    INVITED = "INVITED", "Invited"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    REVOKED = "REVOKED", "Revoked"
    EXPIRED = "EXPIRED", "Expired"


class InvitationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    ACCEPTED = "ACCEPTED", "Accepted"
    EXPIRED = "EXPIRED", "Expired"
    REVOKED = "REVOKED", "Revoked"


class VisibilityStatus(models.TextChoices):
    INTERNAL_ONLY = "INTERNAL_ONLY", "Internal only"
    CLIENT_SUMMARY = "CLIENT_SUMMARY", "Client summary"
    CLIENT_DETAILED = "CLIENT_DETAILED", "Client detailed"


class PeriodStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CALCULATED = "CALCULATED", "Calculated"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    LOCKED = "LOCKED", "Locked"
    STALE = "STALE", "Stale"


class SLAResult(models.TextChoices):
    MET = "MET", "Met"
    NOT_MET = "NOT_MET", "Not met"
    WARNING = "WARNING", "Warning"
    NOT_MEASURABLE = "NOT_MEASURABLE", "Not measurable"
    NOT_APPLICABLE = "NOT_APPLICABLE", "Not applicable"


class ReportStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    GENERATED = "GENERATED", "Generated"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    PUBLISHED = "PUBLISHED", "Published"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    ARCHIVED = "ARCHIVED", "Archived"


class RequestStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    WAITING_FOR_CLIENT = "WAITING_FOR_CLIENT", "Waiting for client"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"
