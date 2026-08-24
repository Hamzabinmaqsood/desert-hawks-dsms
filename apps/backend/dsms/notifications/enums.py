from django.db import models


class Channel(models.TextChoices):
    IN_APP = "IN_APP", "In app"
    EMAIL = "EMAIL", "Email"
    SMS = "SMS", "SMS"
    PUSH = "PUSH", "Push"


class Priority(models.TextChoices):
    LOW = "LOW", "Low"
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"
    EMERGENCY = "EMERGENCY", "Emergency"


class NotificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    SCHEDULED = "SCHEDULED", "Scheduled"
    PROCESSING = "PROCESSING", "Processing"
    PARTIALLY_DELIVERED = "PARTIALLY_DELIVERED", "Partially delivered"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"
    EXPIRED = "EXPIRED", "Expired"


class RecipientStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    READ = "READ", "Read"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    EXPIRED = "EXPIRED", "Expired"


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    ACCEPTED = "ACCEPTED", "Accepted"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    TEMPORARY_FAILURE = "TEMPORARY_FAILURE", "Temporary failure"
    PERMANENT_FAILURE = "PERMANENT_FAILURE", "Permanent failure"
    SKIPPED = "SKIPPED", "Skipped"
    CANCELLED = "CANCELLED", "Cancelled"


class EventStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSED = "PROCESSED", "Processed"
    FAILED = "FAILED", "Failed"
    IGNORED = "IGNORED", "Ignored"


class Acknowledgement(models.TextChoices):
    NONE = "NONE", "None"
    OPTIONAL = "OPTIONAL", "Optional"
    REQUIRED = "REQUIRED", "Required"


class Frequency(models.TextChoices):
    IMMEDIATE = "IMMEDIATE", "Immediate"
    DAILY_DIGEST = "DAILY_DIGEST", "Daily digest"
    WEEKLY_DIGEST = "WEEKLY_DIGEST", "Weekly digest"
    DISABLED = "DISABLED", "Disabled"
