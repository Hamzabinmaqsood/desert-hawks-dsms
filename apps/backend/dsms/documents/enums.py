from django.db import models


class DocumentCategory(models.TextChoices):
    IDENTITY = "IDENTITY", "Identity"
    EMPLOYMENT = "EMPLOYMENT", "Employment"
    BACKGROUND_VERIFICATION = "BACKGROUND_VERIFICATION", "Background verification"
    LICENCE = "LICENCE", "Licence"
    MEDICAL_FITNESS = "MEDICAL_FITNESS", "Medical fitness"
    EDUCATION = "EDUCATION", "Education"
    TRAINING = "TRAINING", "Training"
    EXPERIENCE = "EXPERIENCE", "Experience"
    PERSONAL = "PERSONAL", "Personal"
    OTHER = "OTHER", "Other"


class DocumentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"
    REVOKED = "REVOKED", "Revoked"
    SUPERSEDED = "SUPERSEDED", "Superseded"


class DocumentEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    METADATA_UPDATED = "METADATA_UPDATED", "Metadata updated"
    FILE_ADDED = "FILE_ADDED", "File added"
    SUBMITTED = "SUBMITTED", "Submitted"
    VERIFIED = "VERIFIED", "Verified"
    REJECTED = "REJECTED", "Rejected"
    REVOKED = "REVOKED", "Revoked"
    SUPERSEDED = "SUPERSEDED", "Superseded"
