from django.db import models


class RequisitionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"
    OPEN = "OPEN", "Open"
    FILLED = "FILLED", "Filled"
    CANCELLED = "CANCELLED", "Cancelled"
    CLOSED = "CLOSED", "Closed"


class VacancyStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"
    CANCELLED = "CANCELLED", "Cancelled"
    FILLED = "FILLED", "Filled"


class CandidateStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    BLACKLISTED = "BLACKLISTED", "Blacklisted"
    HIRED = "HIRED", "Hired"
    ARCHIVED = "ARCHIVED", "Archived"


class ApplicationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    APPLIED = "APPLIED", "Applied"
    SCREENING = "SCREENING", "Screening"
    SHORTLISTED = "SHORTLISTED", "Shortlisted"
    INTERVIEW = "INTERVIEW", "Interview"
    ASSESSMENT = "ASSESSMENT", "Assessment"
    BACKGROUND_CHECK = "BACKGROUND_CHECK", "Background check"
    SELECTED = "SELECTED", "Selected"
    OFFERED = "OFFERED", "Offered"
    OFFER_ACCEPTED = "OFFER_ACCEPTED", "Offer accepted"
    OFFER_DECLINED = "OFFER_DECLINED", "Offer declined"
    ONBOARDING = "ONBOARDING", "Onboarding"
    HIRED = "HIRED", "Hired"
    REJECTED = "REJECTED", "Rejected"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    CANCELLED = "CANCELLED", "Cancelled"


class ScreeningDecision(models.TextChoices):
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    HOLD = "HOLD", "Hold"


class InterviewRecommendation(models.TextChoices):
    RECOMMEND = "RECOMMEND", "Recommend"
    NOT_RECOMMEND = "NOT_RECOMMEND", "Do not recommend"
    HOLD = "HOLD", "Hold"


class VerificationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    VERIFIED = "VERIFIED", "Verified"
    FAILED = "FAILED", "Failed"
    WAIVED = "WAIVED", "Waived"


class OfferStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    APPROVED = "APPROVED", "Approved"
    ISSUED = "ISSUED", "Issued"
    ACCEPTED = "ACCEPTED", "Accepted"
    DECLINED = "DECLINED", "Declined"
    EXPIRED = "EXPIRED", "Expired"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class OnboardingStatus(models.TextChoices):
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    BLOCKED = "BLOCKED", "Blocked"
    READY_TO_HIRE = "READY_TO_HIRE", "Ready to hire"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class SourceType(models.TextChoices):
    WEBSITE = "WEBSITE", "Website"
    REFERRAL = "REFERRAL", "Referral"
    AGENCY = "AGENCY", "Agency"
    WALK_IN = "WALK_IN", "Walk-in"
    JOB_PORTAL = "JOB_PORTAL", "Job portal"
    INTERNAL = "INTERNAL", "Internal"
    OTHER = "OTHER", "Other"


class InterviewType(models.TextChoices):
    HR = "HR", "HR"
    OPERATIONS = "OPERATIONS", "Operations"
    TECHNICAL = "TECHNICAL", "Technical"
    FINAL = "FINAL", "Final"
    OTHER = "OTHER", "Other"


class InterviewStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"
    NO_SHOW = "NO_SHOW", "No show"
    RESCHEDULED = "RESCHEDULED", "Rescheduled"


class AssessmentResult(models.TextChoices):
    PASS = "PASS", "Pass"
    FAIL = "FAIL", "Fail"
    PENDING = "PENDING", "Pending"


class AssessmentType(models.TextChoices):
    WRITTEN = "WRITTEN", "Written"
    PHYSICAL = "PHYSICAL", "Physical"
    DRIVING = "DRIVING", "Driving"
    TECHNICAL = "TECHNICAL", "Technical"
    APTITUDE = "APTITUDE", "Aptitude"
    OTHER = "OTHER", "Other"


class CheckType(models.TextChoices):
    IDENTITY = "IDENTITY", "Identity"
    POLICE = "POLICE", "Police"
    PREVIOUS_EMPLOYMENT = "PREVIOUS_EMPLOYMENT", "Previous employment"
    ADDRESS = "ADDRESS", "Address"
    REFERENCE = "REFERENCE", "Reference"
    CRIMINAL_RECORD_DECLARATION = "CRIMINAL_RECORD_DECLARATION", "Declaration"
    OTHER = "OTHER", "Other"


class NoteVisibility(models.TextChoices):
    RECRUITMENT = "RECRUITMENT", "Recruitment"
    HR_RESTRICTED = "HR_RESTRICTED", "HR restricted"


class RequirementType(models.TextChoices):
    ACTION = "ACTION", "Action"
    DOCUMENT = "DOCUMENT", "Document"
    VERIFICATION = "VERIFICATION", "Verification"
    APPROVAL = "APPROVAL", "Approval"
    INFORMATION = "INFORMATION", "Information"


class ChecklistStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    COMPLETED = "COMPLETED", "Completed"
    WAIVED = "WAIVED", "Waived"
    FAILED = "FAILED", "Failed"
