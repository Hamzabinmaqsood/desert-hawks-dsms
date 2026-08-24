from django.db import models


class EmployeeType(models.TextChoices):
    """The broad category of work an employee performs."""

    MANAGEMENT = "MANAGEMENT", "Management"
    OFFICE_STAFF = "OFFICE_STAFF", "Office staff"
    CONTROL_ROOM = "CONTROL_ROOM", "Control room"
    SUPERVISOR = "SUPERVISOR", "Supervisor"
    SECURITY_GUARD = "SECURITY_GUARD", "Security guard"
    DRIVER = "DRIVER", "Driver"
    TRAINER = "TRAINER", "Trainer"
    OTHER = "OTHER", "Other"


class EmploymentStatus(models.TextChoices):
    """The employee's current lifecycle stage."""

    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ON_LEAVE = "ON_LEAVE", "On leave"
    SUSPENDED = "SUSPENDED", "Suspended"
    RESIGNED = "RESIGNED", "Resigned"
    TERMINATED = "TERMINATED", "Terminated"
    RETIRED = "RETIRED", "Retired"
    ABSCONDED = "ABSCONDED", "Absconded"


class EmploymentType(models.TextChoices):
    """The contractual basis of the employment."""

    PERMANENT = "PERMANENT", "Permanent"
    CONTRACT = "CONTRACT", "Contract"
    TEMPORARY = "TEMPORARY", "Temporary"
    PROBATION = "PROBATION", "Probation"
    DAILY_WAGE = "DAILY_WAGE", "Daily wage"


class Gender(models.TextChoices):
    MALE = "MALE", "Male"
    FEMALE = "FEMALE", "Female"
    OTHER = "OTHER", "Other"
    UNSPECIFIED = "UNSPECIFIED", "Unspecified"


class MaritalStatus(models.TextChoices):
    SINGLE = "SINGLE", "Single"
    MARRIED = "MARRIED", "Married"
    DIVORCED = "DIVORCED", "Divorced"
    WIDOWED = "WIDOWED", "Widowed"
    UNSPECIFIED = "UNSPECIFIED", "Unspecified"


class AddressType(models.TextChoices):
    CURRENT = "CURRENT", "Current"
    PERMANENT = "PERMANENT", "Permanent"
    OTHER = "OTHER", "Other"
