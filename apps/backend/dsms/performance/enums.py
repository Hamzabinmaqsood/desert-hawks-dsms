from django.db import models


class PerformanceCycleStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PLANNED = "PLANNED", "Planned"
    OPEN = "OPEN", "Open"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    CALIBRATION = "CALIBRATION", "Calibration"
    FINALIZED = "FINALIZED", "Finalized"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"


class PerformancePlanStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    SELF_REVIEW = "SELF_REVIEW", "Self review"
    MANAGER_REVIEW = "MANAGER_REVIEW", "Manager review"
    SECONDARY_REVIEW = "SECONDARY_REVIEW", "Secondary review"
    CALIBRATION = "CALIBRATION", "Calibration"
    FINAL_REVIEW = "FINAL_REVIEW", "Final review"
    COMPLETED = "COMPLETED", "Completed"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    CANCELLED = "CANCELLED", "Cancelled"


class GoalStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    ON_TRACK = "ON_TRACK", "On track"
    AT_RISK = "AT_RISK", "At risk"
    COMPLETED = "COMPLETED", "Completed"
    NOT_COMPLETED = "NOT_COMPLETED", "Not completed"
    CANCELLED = "CANCELLED", "Cancelled"


class GoalMeasurementType(models.TextChoices):
    PERCENTAGE = "PERCENTAGE", "Percentage"
    NUMBER = "NUMBER", "Number"
    DECIMAL = "DECIMAL", "Decimal"
    BOOLEAN = "BOOLEAN", "Boolean"
    MILESTONE = "MILESTONE", "Milestone"
    MANUAL_RATING = "MANUAL_RATING", "Manual rating"


class KPIDirection(models.TextChoices):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER", "Higher is better"
    LOWER_IS_BETTER = "LOWER_IS_BETTER", "Lower is better"
    TARGET_IS_BEST = "TARGET_IS_BEST", "Target is best"
    INFORMATIONAL = "INFORMATIONAL", "Informational"


class KPIDataSource(models.TextChoices):
    MANUAL = "MANUAL", "Manual"
    ATTENDANCE = "ATTENDANCE", "Attendance"
    DEPLOYMENT = "DEPLOYMENT", "Deployment"
    SUPERVISION = "SUPERVISION", "Supervision"
    PATROL = "PATROL", "Patrol"
    INCIDENTS = "INCIDENTS", "Incidents"
    TRAINING = "TRAINING", "Training"
    CLIENT_SERVICE = "CLIENT_SERVICE", "Client service"
    ASSETS = "ASSETS", "Assets"
    FINANCE = "FINANCE", "Finance"
    CUSTOM = "CUSTOM", "Custom"


class AppraisalSectionType(models.TextChoices):
    GOALS = "GOALS", "Goals"
    KPIS = "KPIS", "KPIs"
    COMPETENCIES = "COMPETENCIES", "Competencies"
    VALUES = "VALUES", "Values"
    DEVELOPMENT = "DEVELOPMENT", "Development"
    MANAGER_SUMMARY = "MANAGER_SUMMARY", "Manager summary"
    OTHER = "OTHER", "Other"


class AssessmentSource(models.TextChoices):
    SELF = "SELF", "Self"
    MANAGER = "MANAGER", "Manager"
    SECONDARY_REVIEWER = "SECONDARY_REVIEWER", "Secondary reviewer"
    SUPERVISOR = "SUPERVISOR", "Supervisor"
    HR = "HR", "HR"
    CALIBRATION = "CALIBRATION", "Calibration"


class KPIResultStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CALCULATED = "CALCULATED", "Calculated"
    INCOMPLETE = "INCOMPLETE", "Incomplete"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"
    FINALIZED = "FINALIZED", "Finalized"


class RecognitionStatus(models.TextChoices):
    NOMINATED = "NOMINATED", "Nominated"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    PUBLISHED = "PUBLISHED", "Published"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
