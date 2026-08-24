from django.db import models


class DeploymentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    ENDED = "ENDED", "Ended"
    CANCELLED = "CANCELLED", "Cancelled"


class DeploymentType(models.TextChoices):
    REGULAR = "REGULAR", "Regular"
    TEMPORARY = "TEMPORARY", "Temporary"
    RELIEF = "RELIEF", "Relief"
    EMERGENCY = "EMERGENCY", "Emergency"
    SUPERVISORY = "SUPERVISORY", "Supervisory"


class RosterStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    GENERATED = "GENERATED", "Generated"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    PUBLISHED = "PUBLISHED", "Published"
    LOCKED = "LOCKED", "Locked"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"


class DutyShiftStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    PUBLISHED = "PUBLISHED", "Published"
    CANCELLED = "CANCELLED", "Cancelled"


class DutyAssignmentStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    CONFIRMED = "CONFIRMED", "Confirmed"
    REPLACED = "REPLACED", "Replaced"
    CANCELLED = "CANCELLED", "Cancelled"


class AssignmentType(models.TextChoices):
    REGULAR = "REGULAR", "Regular"
    RELIEF = "RELIEF", "Relief"
    REPLACEMENT = "REPLACEMENT", "Replacement"
    EMERGENCY = "EMERGENCY", "Emergency"
    OVERTIME = "OVERTIME", "Overtime"


class ScheduleBlockType(models.TextChoices):
    MANUAL_UNAVAILABLE = "MANUAL_UNAVAILABLE", "Manual unavailable"
    TRAINING = "TRAINING", "Training"
    MANAGEMENT_BLOCK = "MANAGEMENT_BLOCK", "Management block"
    MEDICAL_RESTRICTION = "MEDICAL_RESTRICTION", "Medical restriction"
    FUTURE_LEAVE = "FUTURE_LEAVE", "Future leave"
    OTHER = "OTHER", "Other"


class EligibilityStatus(models.TextChoices):
    ELIGIBLE = "ELIGIBLE", "Eligible"
    ELIGIBLE_WITH_WARNING = "ELIGIBLE_WITH_WARNING", "Eligible with warning"
    INELIGIBLE = "INELIGIBLE", "Ineligible"


class RosterChangeType(models.TextChoices):
    ASSIGNED = "ASSIGNED", "Assigned"
    UNASSIGNED = "UNASSIGNED", "Unassigned"
    REASSIGNED = "REASSIGNED", "Reassigned"
    REPLACED = "REPLACED", "Replaced"
    SHIFT_ADDED = "SHIFT_ADDED", "Shift added"
    SHIFT_CANCELLED = "SHIFT_CANCELLED", "Shift cancelled"
    TIME_CHANGED = "TIME_CHANGED", "Time changed"
    PUBLISHED = "PUBLISHED", "Published"
    LOCKED = "LOCKED", "Locked"


class ReplacementRequestStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    ASSIGNED = "ASSIGNED", "Assigned"
    APPROVED = "APPROVED", "Approved"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class ReplacementPriority(models.TextChoices):
    NORMAL = "NORMAL", "Normal"
    URGENT = "URGENT", "Urgent"
    EMERGENCY = "EMERGENCY", "Emergency"
