from django.db import models


class AssetCategoryType(models.TextChoices):
    UNIFORM = "UNIFORM", "Uniform"
    SECURITY_EQUIPMENT = "SECURITY_EQUIPMENT", "Security equipment"
    COMMUNICATION_DEVICE = "COMMUNICATION_DEVICE", "Communication device"
    ELECTRONIC_DEVICE = "ELECTRONIC_DEVICE", "Electronic device"
    OFFICE_EQUIPMENT = "OFFICE_EQUIPMENT", "Office equipment"
    SITE_EQUIPMENT = "SITE_EQUIPMENT", "Site equipment"
    VEHICLE = "VEHICLE", "Vehicle"
    CONTROLLED_ITEM = "CONTROLLED_ITEM", "Controlled item"
    CONSUMABLE = "CONSUMABLE", "Consumable"
    TOOL = "TOOL", "Tool"
    OTHER = "OTHER", "Other"


class TrackingMethod(models.TextChoices):
    SERIALIZED = "SERIALIZED", "Serialized"
    QUANTITY = "QUANTITY", "Quantity"


class AssetStatus(models.TextChoices):
    PENDING_REGISTRATION = "PENDING_REGISTRATION", "Pending registration"
    AVAILABLE = "AVAILABLE", "Available"
    RESERVED = "RESERVED", "Reserved"
    ISSUED = "ISSUED", "Issued"
    IN_TRANSIT = "IN_TRANSIT", "In transit"
    UNDER_INSPECTION = "UNDER_INSPECTION", "Under inspection"
    UNDER_MAINTENANCE = "UNDER_MAINTENANCE", "Under maintenance"
    DAMAGED = "DAMAGED", "Damaged"
    LOST = "LOST", "Lost"
    STOLEN_REPORTED = "STOLEN_REPORTED", "Stolen reported"
    RETIRED = "RETIRED", "Retired"
    DISPOSED = "DISPOSED", "Disposed"


class AssetCondition(models.TextChoices):
    NEW = "NEW", "New"
    EXCELLENT = "EXCELLENT", "Excellent"
    GOOD = "GOOD", "Good"
    FAIR = "FAIR", "Fair"
    POOR = "POOR", "Poor"
    DAMAGED = "DAMAGED", "Damaged"
    UNSERVICEABLE = "UNSERVICEABLE", "Unserviceable"


class CustodyType(models.TextChoices):
    WAREHOUSE = "WAREHOUSE", "Warehouse"
    BRANCH = "BRANCH", "Branch"
    SITE = "SITE", "Site"
    EMPLOYEE = "EMPLOYEE", "Employee"
    VEHICLE = "VEHICLE", "Vehicle"
    EXTERNAL_SERVICE_PROVIDER = "EXTERNAL_SERVICE_PROVIDER", "External service provider"
    OTHER = "OTHER", "Other"


class MovementType(models.TextChoices):
    RECEIPT = "RECEIPT", "Receipt"
    ISSUE = "ISSUE", "Issue"
    RETURN = "RETURN", "Return"
    TRANSFER = "TRANSFER", "Transfer"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"
    MAINTENANCE_OUT = "MAINTENANCE_OUT", "Maintenance out"
    MAINTENANCE_RETURN = "MAINTENANCE_RETURN", "Maintenance return"
    LOSS = "LOSS", "Loss"
    RECOVERY = "RECOVERY", "Recovery"
    RETIREMENT = "RETIREMENT", "Retirement"
    DISPOSAL = "DISPOSAL", "Disposal"
    COUNT_CORRECTION = "COUNT_CORRECTION", "Count correction"


class IssueType(models.TextChoices):
    TEMPORARY = "TEMPORARY", "Temporary"
    LONG_TERM = "LONG_TERM", "Long term"
    SHIFT_SPECIFIC = "SHIFT_SPECIFIC", "Shift specific"
    SITE_ASSIGNMENT = "SITE_ASSIGNMENT", "Site assignment"
    EMPLOYEE_ASSIGNMENT = "EMPLOYEE_ASSIGNMENT", "Employee assignment"


class IssueStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending approval"
    APPROVED = "APPROVED", "Approved"
    ISSUED = "ISSUED", "Issued"
    PARTIALLY_RETURNED = "PARTIALLY_RETURNED", "Partially returned"
    RETURNED = "RETURNED", "Returned"
    CANCELLED = "CANCELLED", "Cancelled"
    REJECTED = "REJECTED", "Rejected"


class ReturnStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    RECEIVED = "RECEIVED", "Received"
    INSPECTED = "INSPECTED", "Inspected"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class ReturnCondition(models.TextChoices):
    GOOD = "GOOD", "Good"
    FAIR = "FAIR", "Fair"
    DAMAGED = "DAMAGED", "Damaged"
    UNSERVICEABLE = "UNSERVICEABLE", "Unserviceable"


class UnitOfMeasure(models.TextChoices):
    PIECE = "PIECE", "Piece"
    PAIR = "PAIR", "Pair"
    SET = "SET", "Set"
    BOX = "BOX", "Box"
    LITRE = "LITRE", "Litre"
    OTHER = "OTHER", "Other"


class RequirementType(models.TextChoices):
    MANDATORY = "MANDATORY", "Mandatory"
    RECOMMENDED = "RECOMMENDED", "Recommended"
    OPTIONAL = "OPTIONAL", "Optional"
