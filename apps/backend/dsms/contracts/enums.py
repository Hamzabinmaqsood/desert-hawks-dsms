from django.db import models


class ClientStatus(models.TextChoices):
    PROSPECT = "PROSPECT", "Prospect"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    INACTIVE = "INACTIVE", "Inactive"
    BLACKLISTED = "BLACKLISTED", "Blacklisted"
    ARCHIVED = "ARCHIVED", "Archived"


class ContractStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
    APPROVED = "APPROVED", "Approved"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    EXPIRED = "EXPIRED", "Expired"
    TERMINATED = "TERMINATED", "Terminated"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class ContractType(models.TextChoices):
    FIXED_TERM = "FIXED_TERM", "Fixed term"
    OPEN_ENDED = "OPEN_ENDED", "Open ended"
    PROJECT = "PROJECT", "Project"
    FRAMEWORK = "FRAMEWORK", "Framework"
    OTHER = "OTHER", "Other"


class ServiceType(models.TextChoices):
    MANNED_GUARDING = "MANNED_GUARDING", "Manned guarding"
    ARMED_GUARDING = "ARMED_GUARDING", "Armed guarding"
    SUPERVISION = "SUPERVISION", "Supervision"
    MOBILE_PATROL = "MOBILE_PATROL", "Mobile patrol"
    VIP_PROTECTION = "VIP_PROTECTION", "VIP protection"
    EVENT_SECURITY = "EVENT_SECURITY", "Event security"
    CONTROL_ROOM = "CONTROL_ROOM", "Control room"
    CCTV_MONITORING = "CCTV_MONITORING", "CCTV monitoring"
    ACCESS_CONTROL = "ACCESS_CONTROL", "Access control"
    CONSULTANCY = "CONSULTANCY", "Consultancy"
    OTHER = "OTHER", "Other"


class SiteStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    ACTIVE = "ACTIVE", "Active"
    TEMPORARILY_INACTIVE = "TEMPORARILY_INACTIVE", "Temporarily inactive"
    CLOSED = "CLOSED", "Closed"


class PostStatus(models.TextChoices):
    PLANNED = "PLANNED", "Planned"
    ACTIVE = "ACTIVE", "Active"
    TEMPORARILY_INACTIVE = "TEMPORARILY_INACTIVE", "Temporarily inactive"
    CLOSED = "CLOSED", "Closed"


class SiteRiskLevel(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"
    CRITICAL = "CRITICAL", "Critical"


class CoverageType(models.TextChoices):
    CONTINUOUS_24_7 = "CONTINUOUS_24_7", "Continuous 24/7"
    DAILY = "DAILY", "Daily"
    WEEKDAYS = "WEEKDAYS", "Weekdays"
    WEEKENDS = "WEEKENDS", "Weekends"
    CUSTOM = "CUSTOM", "Custom"


class StaffingRequirementStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"
    SUPERSEDED = "SUPERSEDED", "Superseded"
    EXPIRED = "EXPIRED", "Expired"


class SLAType(models.TextChoices):
    ATTENDANCE_COVERAGE = "ATTENDANCE_COVERAGE", "Attendance coverage"
    REPLACEMENT_TIME = "REPLACEMENT_TIME", "Replacement time"
    INCIDENT_RESPONSE = "INCIDENT_RESPONSE", "Incident response"
    SUPERVISOR_VISIT = "SUPERVISOR_VISIT", "Supervisor visit"
    REPORTING = "REPORTING", "Reporting"
    OTHER = "OTHER", "Other"


class ContractChangeType(models.TextChoices):
    CREATED = "CREATED", "Created"
    ACTIVATED = "ACTIVATED", "Activated"
    SUSPENDED = "SUSPENDED", "Suspended"
    RENEWED = "RENEWED", "Renewed"
    EXTENDED = "EXTENDED", "Extended"
    AMENDED = "AMENDED", "Amended"
    TERMINATED = "TERMINATED", "Terminated"
    EXPIRED = "EXPIRED", "Expired"
    COMPLETED = "COMPLETED", "Completed"


class RequirementLevel(models.TextChoices):
    MANDATORY = "MANDATORY", "Mandatory"
    RECOMMENDED = "RECOMMENDED", "Recommended"
    OPTIONAL = "OPTIONAL", "Optional"


class Weekday(models.TextChoices):
    MONDAY = "MONDAY", "Monday"
    TUESDAY = "TUESDAY", "Tuesday"
    WEDNESDAY = "WEDNESDAY", "Wednesday"
    THURSDAY = "THURSDAY", "Thursday"
    FRIDAY = "FRIDAY", "Friday"
    SATURDAY = "SATURDAY", "Saturday"
    SUNDAY = "SUNDAY", "Sunday"


class ContactType(models.TextChoices):
    PRIMARY = "PRIMARY", "Primary"
    OPERATIONS = "OPERATIONS", "Operations"
    SECURITY = "SECURITY", "Security"
    FINANCE = "FINANCE", "Finance"
    HR = "HR", "HR"
    EMERGENCY = "EMERGENCY", "Emergency"
    ESCALATION = "ESCALATION", "Escalation"
    OTHER = "OTHER", "Other"
