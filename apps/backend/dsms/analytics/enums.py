from django.db import models


class MetricCategory(models.TextChoices):
    EXECUTIVE = "EXECUTIVE", "Executive"
    FINANCE = "FINANCE", "Finance"
    REVENUE = "REVENUE", "Revenue"
    COLLECTIONS = "COLLECTIONS", "Collections"
    PAYROLL = "PAYROLL", "Payroll"
    PROCUREMENT = "PROCUREMENT", "Procurement"
    VENDOR = "VENDOR", "Vendor"
    WORKFORCE = "WORKFORCE", "Workforce"
    RECRUITMENT = "RECRUITMENT", "Recruitment"
    TRAINING = "TRAINING", "Training"
    DEPLOYMENT = "DEPLOYMENT", "Deployment"
    ATTENDANCE = "ATTENDANCE", "Attendance"
    LEAVE = "LEAVE", "Leave"
    SUPERVISION = "SUPERVISION", "Supervision"
    PATROL = "PATROL", "Patrol"
    INCIDENT = "INCIDENT", "Incident"
    CLIENT_SERVICE = "CLIENT_SERVICE", "Client service"
    ASSETS = "ASSETS", "Assets"
    PERFORMANCE = "PERFORMANCE", "Performance"
    HR = "HR", "HR"
    OTHER = "OTHER", "Other"


class MetricValueType(models.TextChoices):
    INTEGER = "INTEGER", "Integer"
    DECIMAL = "DECIMAL", "Decimal"
    PERCENTAGE = "PERCENTAGE", "Percentage"
    CURRENCY = "CURRENCY", "Currency"
    DURATION = "DURATION", "Duration"
    BOOLEAN = "BOOLEAN", "Boolean"
    TEXT = "TEXT", "Text"


class MetricAggregation(models.TextChoices):
    COUNT = "COUNT", "Count"
    SUM = "SUM", "Sum"
    AVERAGE = "AVERAGE", "Average"
    MINIMUM = "MINIMUM", "Minimum"
    MAXIMUM = "MAXIMUM", "Maximum"
    RATIO = "RATIO", "Ratio"
    PERCENTAGE = "PERCENTAGE", "Percentage"
    BALANCE = "BALANCE", "Balance"
    SNAPSHOT = "SNAPSHOT", "Snapshot"
    CUSTOM_PROVIDER = "CUSTOM_PROVIDER", "Custom provider"


class MetricDirection(models.TextChoices):
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER", "Higher is better"
    LOWER_IS_BETTER = "LOWER_IS_BETTER", "Lower is better"
    TARGET_RANGE = "TARGET_RANGE", "Target range"
    INFORMATIONAL = "INFORMATIONAL", "Informational"


class AnalyticsPeriodType(models.TextChoices):
    DAY = "DAY", "Day"
    WEEK = "WEEK", "Week"
    MONTH = "MONTH", "Month"
    QUARTER = "QUARTER", "Quarter"
    YEAR = "YEAR", "Year"
    CUSTOM = "CUSTOM", "Custom"


class SnapshotStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    CALCULATED = "CALCULATED", "Calculated"
    VALIDATED = "VALIDATED", "Validated"
    PUBLISHED = "PUBLISHED", "Published"
    STALE = "STALE", "Stale"


class ExecutiveHealthStatus(models.TextChoices):
    GOOD = "GOOD", "Good"
    WATCH = "WATCH", "Watch"
    ATTENTION = "ATTENTION", "Attention"
    CRITICAL = "CRITICAL", "Critical"
    NOT_AVAILABLE = "NOT_AVAILABLE", "Not available"


class DataQualityIssueStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
    RESOLVED = "RESOLVED", "Resolved"
    DISMISSED = "DISMISSED", "Dismissed"
