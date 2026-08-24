from django.db import models


class HRCaseType(models.TextChoices):
    DISCIPLINARY = "DISCIPLINARY", "Disciplinary"
    GRIEVANCE = "GRIEVANCE", "Grievance"
    EMPLOYEE_COMPLAINT = "EMPLOYEE_COMPLAINT", "Employee complaint"
    CLIENT_COMPLAINT = "CLIENT_COMPLAINT", "Client complaint"
    WORKPLACE_CONDUCT = "WORKPLACE_CONDUCT", "Workplace conduct"
    POLICY_VIOLATION = "POLICY_VIOLATION", "Policy violation"
    ATTENDANCE_REFERRAL = "ATTENDANCE_REFERRAL", "Attendance referral"
    OPERATIONAL_REFERRAL = "OPERATIONAL_REFERRAL", "Operational referral"
    ASSET_REFERRAL = "ASSET_REFERRAL", "Asset referral"
    INCIDENT_REFERRAL = "INCIDENT_REFERRAL", "Incident referral"
    OTHER = "OTHER", "Other"


class HRCaseStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    TRIAGE = "TRIAGE", "Triage"
    UNDER_PRELIMINARY_REVIEW = "UNDER_PRELIMINARY_REVIEW", "Under preliminary review"
    INVESTIGATION = "INVESTIGATION", "Investigation"
    AWAITING_RESPONSE = "AWAITING_RESPONSE", "Awaiting response"
    HEARING_SCHEDULED = "HEARING_SCHEDULED", "Hearing scheduled"
    UNDER_DECISION = "UNDER_DECISION", "Under decision"
    DECIDED = "DECIDED", "Decided"
    APPEAL_OPEN = "APPEAL_OPEN", "Appeal open"
    APPEAL_REVIEW = "APPEAL_REVIEW", "Appeal review"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"
    REOPENED = "REOPENED", "Reopened"


class CasePriority(models.TextChoices):
    LOW = "LOW", "Low"
    NORMAL = "NORMAL", "Normal"
    HIGH = "HIGH", "High"
    URGENT = "URGENT", "Urgent"


class CaseConfidentiality(models.TextChoices):
    STANDARD = "STANDARD", "Standard"
    CONFIDENTIAL = "CONFIDENTIAL", "Confidential"
    HIGHLY_CONFIDENTIAL = "HIGHLY_CONFIDENTIAL", "Highly confidential"


class AllegationStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    SUBSTANTIATED = "SUBSTANTIATED", "Substantiated"
    PARTIALLY_SUBSTANTIATED = "PARTIALLY_SUBSTANTIATED", "Partially substantiated"
    NOT_SUBSTANTIATED = "NOT_SUBSTANTIATED", "Not substantiated"
    INCONCLUSIVE = "INCONCLUSIVE", "Inconclusive"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class InvestigationStatus(models.TextChoices):
    NOT_STARTED = "NOT_STARTED", "Not started"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    AWAITING_INFORMATION = "AWAITING_INFORMATION", "Awaiting information"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class EvidenceType(models.TextChoices):
    DOCUMENT = "DOCUMENT", "Document"
    PHOTO = "PHOTO", "Photo"
    VIDEO_REFERENCE = "VIDEO_REFERENCE", "Video reference"
    AUDIO_REFERENCE = "AUDIO_REFERENCE", "Audio reference"
    EMAIL_REFERENCE = "EMAIL_REFERENCE", "Email reference"
    ATTENDANCE_REFERENCE = "ATTENDANCE_REFERENCE", "Attendance reference"
    INCIDENT_REFERENCE = "INCIDENT_REFERENCE", "Incident reference"
    PATROL_REFERENCE = "PATROL_REFERENCE", "Patrol reference"
    SUPERVISION_REFERENCE = "SUPERVISION_REFERENCE", "Supervision reference"
    ASSET_REFERENCE = "ASSET_REFERENCE", "Asset reference"
    CLIENT_COMPLAINT_REFERENCE = "CLIENT_COMPLAINT_REFERENCE", "Client complaint reference"
    WITNESS_STATEMENT = "WITNESS_STATEMENT", "Witness statement"
    OTHER = "OTHER", "Other"


class OutcomeFinding(models.TextChoices):
    NO_FINDING = "NO_FINDING", "No finding"
    NOT_SUBSTANTIATED = "NOT_SUBSTANTIATED", "Not substantiated"
    PARTIALLY_SUBSTANTIATED = "PARTIALLY_SUBSTANTIATED", "Partially substantiated"
    SUBSTANTIATED = "SUBSTANTIATED", "Substantiated"
    INCONCLUSIVE = "INCONCLUSIVE", "Inconclusive"
    RESOLVED_INFORMALLY = "RESOLVED_INFORMALLY", "Resolved informally"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class HRActionType(models.TextChoices):
    NO_ACTION = "NO_ACTION", "No action"
    COUNSELLING_RECORDED = "COUNSELLING_RECORDED", "Counselling recorded"
    COACHING = "COACHING", "Coaching"
    TRAINING_REFERRAL = "TRAINING_REFERRAL", "Training referral"
    VERBAL_WARNING_RECORDED = "VERBAL_WARNING_RECORDED", "Verbal warning recorded"
    WRITTEN_WARNING = "WRITTEN_WARNING", "Written warning"
    FINAL_WARNING = "FINAL_WARNING", "Final warning"
    TRANSFER_RECOMMENDATION = "TRANSFER_RECOMMENDATION", "Transfer recommendation"
    SUSPENSION_RECOMMENDATION = "SUSPENSION_RECOMMENDATION", "Suspension recommendation"
    TERMINATION_RECOMMENDATION = "TERMINATION_RECOMMENDATION", "Termination recommendation"
    OTHER = "OTHER", "Other"


class AppealStatus(models.TextChoices):
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    UPHELD = "UPHELD", "Upheld"
    PARTIALLY_UPHELD = "PARTIALLY_UPHELD", "Partially upheld"
    OVERTURNED = "OVERTURNED", "Overturned"
    RETURNED_FOR_REVIEW = "RETURNED_FOR_REVIEW", "Returned for review"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    CLOSED = "CLOSED", "Closed"


class CaseEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    SUBMITTED = "SUBMITTED", "Submitted"
    TRIAGED = "TRIAGED", "Triaged"
    ASSIGNED = "ASSIGNED", "Assigned"
    INVESTIGATION_STARTED = "INVESTIGATION_STARTED", "Investigation started"
    ALLEGATION_ADDED = "ALLEGATION_ADDED", "Allegation added"
    EVIDENCE_ADDED = "EVIDENCE_ADDED", "Evidence added"
    RESPONSE_REQUESTED = "RESPONSE_REQUESTED", "Response requested"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED", "Response received"
    INVESTIGATION_COMPLETED = "INVESTIGATION_COMPLETED", "Investigation completed"
    DECISION_RECORDED = "DECISION_RECORDED", "Decision recorded"
    APPEAL_SUBMITTED = "APPEAL_SUBMITTED", "Appeal submitted"
    APPEAL_DECIDED = "APPEAL_DECIDED", "Appeal decided"
    CASE_CLOSED = "CASE_CLOSED", "Case closed"
    CASE_REOPENED = "CASE_REOPENED", "Case reopened"
    OTHER = "OTHER", "Other"
