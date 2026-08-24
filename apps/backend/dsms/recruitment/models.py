from __future__ import annotations

import uuid
from typing import Any

from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.documents.enums import DocumentStatus
from dsms.documents.models import DocumentType
from dsms.documents.storage import private_document_storage
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department, Designation
from dsms.workforce.enums import EmployeeType, EmploymentType, Gender, MaritalStatus
from dsms.workforce.models import Employee
from dsms.workforce.validators import mask_identity_number, normalize_identity_number

from .enums import (
    ApplicationStatus,
    AssessmentResult,
    AssessmentType,
    CandidateStatus,
    ChecklistStatus,
    CheckType,
    InterviewRecommendation,
    InterviewStatus,
    InterviewType,
    NoteVisibility,
    OfferStatus,
    OnboardingStatus,
    RequirementType,
    RequisitionStatus,
    ScreeningDecision,
    SourceType,
    VacancyStatus,
    VerificationStatus,
)


def candidate_upload_to(instance: CandidateDocumentVersion, filename: str) -> str:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"recruitment/{instance.document.candidate_id}/{uuid.uuid4()}.{extension}"


class RecruitmentModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class ManpowerRequisition(RecruitmentModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="requisitions")
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT)
    designation = models.ForeignKey(Designation, on_delete=models.PROTECT)
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices)
    requested_headcount = models.PositiveIntegerField()
    required_by_date = models.DateField(null=True, blank=True)
    reason = models.TextField()
    replacement_for_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT
    )
    budget_reference = models.CharField(max_length=100, blank=True)
    requested_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="requested_requisitions"
    )
    status = models.CharField(
        max_length=20, choices=RequisitionStatus.choices, default=RequisitionStatus.DRAFT
    )  # noqa: F405
    approved_headcount = models.PositiveIntegerField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_manpower_requisitions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    class Meta:
        permissions = [("approve_requisition", "Can approve manpower requisition")]
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_headcount__gt=0), name="recruit_req_headcount_positive"
            )
        ]


class Vacancy(RecruitmentModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="vacancies")
    manpower_requisition = models.ForeignKey(
        ManpowerRequisition,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="vacancies",
    )
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT)
    designation = models.ForeignKey(Designation, on_delete=models.PROTECT)
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices)
    vacancy_code = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    description = models.TextField()
    number_of_positions = models.PositiveIntegerField()
    positions_filled = models.PositiveIntegerField(default=0)
    opening_date = models.DateField()
    closing_date = models.DateField(null=True, blank=True)
    minimum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    maximum_age = models.PositiveSmallIntegerField(null=True, blank=True)
    minimum_experience_months = models.PositiveIntegerField(null=True, blank=True)
    minimum_education = models.CharField(max_length=200, blank=True)
    location_text = models.CharField(max_length=200, blank=True)
    is_public = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20, choices=VacancyStatus.choices, default=VacancyStatus.DRAFT
    )  # noqa: F405
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "vacancy_code"], name="uniq_vacancy_code_company"
            ),
            models.CheckConstraint(
                condition=Q(number_of_positions__gt=0), name="recruit_vacancy_positions_positive"
            ),
            models.CheckConstraint(
                condition=Q(positions_filled__lte=models.F("number_of_positions")),
                name="recruit_vacancy_not_overfilled",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.vacancy_code = self.vacancy_code.strip().upper()
        super().save(*args, **kwargs)


class Candidate(RecruitmentModel):
    candidate_number = models.CharField(max_length=40, unique=True)
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    first_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    father_or_spouse_name = models.CharField(max_length=150, blank=True)
    gender = models.CharField(max_length=20, choices=Gender.choices, default=Gender.UNSPECIFIED)
    date_of_birth = models.DateField(null=True, blank=True)
    national_identity_number = models.CharField(max_length=32, null=True, blank=True)
    national_identity_expiry = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=2, default="PK")
    marital_status = models.CharField(
        max_length=20, choices=MaritalStatus.choices, default=MaritalStatus.UNSPECIFIED
    )
    mobile_number = models.CharField(max_length=20)
    alternate_mobile_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    current_address = models.TextField(blank=True)
    permanent_address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    province_or_state = models.CharField(max_length=100, blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)  # noqa: F405
    referred_by_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT
    )
    status = models.CharField(
        max_length=20, choices=CandidateStatus.choices, default=CandidateStatus.ACTIVE
    )  # noqa: F405
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["national_identity_number"],
                condition=Q(national_identity_number__isnull=False)
                & ~Q(national_identity_number=""),
                name="uniq_candidate_identity",
            )
        ]
        permissions = [
            ("view_candidate_sensitive_data", "Can view candidate sensitive data"),
            ("hire_candidate", "Can hire candidate"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.national_identity_number:
            self.national_identity_number = normalize_identity_number(self.national_identity_number)
        self.email = self.email.strip().lower()
        self.mobile_number = self.mobile_number.strip()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return " ".join(x for x in (self.first_name, self.middle_name, self.last_name) if x)

    @property
    def masked_identity_number(self) -> str:
        return mask_identity_number(self.national_identity_number or "")


class CandidateApplication(RecruitmentModel):
    application_number = models.CharField(max_length=40, unique=True)
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="applications")
    vacancy = models.ForeignKey(Vacancy, on_delete=models.PROTECT, related_name="applications")
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=30, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT
    )  # noqa: F405
    applied_at = models.DateTimeField(null=True, blank=True)
    source_type = models.CharField(max_length=20, choices=SourceType.choices)  # noqa: F405
    expected_salary = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    availability_date = models.DateField(null=True, blank=True)
    current_employer = models.CharField(max_length=200, blank=True)
    current_job_title = models.CharField(max_length=200, blank=True)
    total_experience_months = models.PositiveIntegerField(null=True, blank=True)
    recruiter = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    rejection_reason = models.TextField(blank=True)
    withdrawal_reason = models.TextField(blank=True)
    hired_employee = models.OneToOneField(
        Employee, null=True, blank=True, on_delete=models.PROTECT, related_name="source_application"
    )

    class Meta:
        indexes = [models.Index(fields=["company", "status"], name="recruit_app_company_status")]


class ApplicationStatusHistory(UUIDModel):
    application = models.ForeignKey(
        CandidateApplication, on_delete=models.PROTECT, related_name="status_history"
    )
    previous_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, choices=ApplicationStatus.choices)  # noqa: F405
    reason = models.TextField(blank=True)
    changed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    changed_at = models.DateTimeField(auto_now_add=True)


class CandidateScreening(RecruitmentModel):
    application = models.OneToOneField(
        CandidateApplication, on_delete=models.PROTECT, related_name="screening"
    )
    screened_by = models.ForeignKey(User, on_delete=models.PROTECT)
    screened_at = models.DateTimeField()
    age_eligible = models.BooleanField(null=True)
    education_eligible = models.BooleanField(null=True)
    experience_eligible = models.BooleanField(null=True)
    identity_available = models.BooleanField(null=True)
    physically_eligible = models.BooleanField(null=True)
    communication_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    decision = models.CharField(max_length=10, choices=ScreeningDecision.choices)  # noqa: F405


class Interview(RecruitmentModel):
    application = models.ForeignKey(
        CandidateApplication, on_delete=models.PROTECT, related_name="interviews"
    )
    interview_number = models.CharField(max_length=40, unique=True)
    interview_type = models.CharField(max_length=20, choices=InterviewType.choices)  # noqa: F405
    scheduled_at = models.DateTimeField()
    location = models.CharField(max_length=200)
    status = models.CharField(
        max_length=20, choices=InterviewStatus.choices, default=InterviewStatus.SCHEDULED
    )  # noqa: F405
    conducted_at = models.DateTimeField(null=True, blank=True)
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    recommendation = models.CharField(
        max_length=20, choices=InterviewRecommendation.choices, blank=True
    )  # noqa: F405
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)


class InterviewPanelMember(UUIDModel):
    interview = models.ForeignKey(Interview, on_delete=models.PROTECT, related_name="panel_members")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    role_label = models.CharField(max_length=100, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["interview", "user"], name="uniq_interview_panel_user")
        ]


class InterviewEvaluation(UUIDModel):
    interview = models.ForeignKey(Interview, on_delete=models.PROTECT, related_name="evaluations")
    evaluator = models.ForeignKey(User, on_delete=models.PROTECT)
    discipline_score = models.PositiveSmallIntegerField(null=True, blank=True)
    communication_score = models.PositiveSmallIntegerField(null=True, blank=True)
    experience_score = models.PositiveSmallIntegerField(null=True, blank=True)
    role_suitability_score = models.PositiveSmallIntegerField(null=True, blank=True)
    appearance_or_bearing_score = models.PositiveSmallIntegerField(null=True, blank=True)
    overall_comments = models.TextField(blank=True)
    recommendation = models.CharField(max_length=20, choices=InterviewRecommendation.choices)  # noqa: F405
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["interview", "evaluator"], name="uniq_interview_evaluator"
            )
        ]


class CandidateAssessment(RecruitmentModel):
    application = models.ForeignKey(
        CandidateApplication, on_delete=models.PROTECT, related_name="assessments"
    )
    assessment_type = models.CharField(max_length=20, choices=AssessmentType.choices)  # noqa: F405
    assessment_date = models.DateField()
    maximum_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    obtained_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    result = models.CharField(
        max_length=10, choices=AssessmentResult.choices, default=AssessmentResult.PENDING
    )  # noqa: F405
    assessed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)


class CandidateReference(RecruitmentModel):
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="references")
    name = models.CharField(max_length=200)
    relationship = models.CharField(max_length=100)
    organization = models.CharField(max_length=200, blank=True)
    designation = models.CharField(max_length=200, blank=True)
    mobile_number = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    years_known = models.PositiveSmallIntegerField(null=True, blank=True)


class ReferenceVerification(RecruitmentModel):
    reference = models.OneToOneField(
        CandidateReference, on_delete=models.PROTECT, related_name="verification"
    )
    application = models.ForeignKey(CandidateApplication, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )  # noqa: F405
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    verified_at = models.DateTimeField(null=True, blank=True)
    remarks = models.TextField(blank=True)


class BackgroundCheck(RecruitmentModel):
    application = models.ForeignKey(
        CandidateApplication, on_delete=models.PROTECT, related_name="background_checks"
    )
    check_type = models.CharField(max_length=40, choices=CheckType.choices)  # noqa: F405
    status = models.CharField(
        max_length=20, choices=VerificationStatus.choices, default=VerificationStatus.PENDING
    )  # noqa: F405
    initiated_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    result_summary = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    waiver_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["application", "check_type"], name="uniq_application_check_type"
            )
        ]
        permissions = [("waive_background_check", "Can waive background checks")]


class CandidateDocument(RecruitmentModel):
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT, related_name="documents")
    application = models.ForeignKey(
        CandidateApplication,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="documents",
    )
    document_type = models.ForeignKey(DocumentType, on_delete=models.PROTECT)
    document_number = models.CharField(max_length=100, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT
    )
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        permissions = [("download_candidate_document", "Can download candidate documents")]


class CandidateDocumentVersion(UUIDModel):
    document = models.ForeignKey(
        CandidateDocument, on_delete=models.PROTECT, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    file = models.FileField(
        storage=private_document_storage, upload_to=candidate_upload_to, max_length=255
    )
    original_filename = models.CharField(max_length=255)
    stored_filename = models.CharField(max_length=255)
    file_extension = models.CharField(max_length=10)
    file_size = models.PositiveBigIntegerField()
    mime_type = models.CharField(max_length=100)
    sha256_hash = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["document", "version_number"], name="uniq_candidate_doc_version"
            ),
            models.UniqueConstraint(
                fields=["document"],
                condition=Q(is_current=True),
                name="uniq_current_candidate_doc_version",
            ),
        ]


class CandidateNote(UUIDModel):
    candidate = models.ForeignKey(
        Candidate, on_delete=models.PROTECT, related_name="candidate_notes"
    )
    application = models.ForeignKey(
        CandidateApplication, null=True, blank=True, on_delete=models.PROTECT
    )
    note = models.TextField()
    visibility = models.CharField(max_length=20, choices=NoteVisibility.choices)  # noqa: F405
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class EmploymentOffer(RecruitmentModel):
    application = models.OneToOneField(
        CandidateApplication, on_delete=models.PROTECT, related_name="offer"
    )
    offer_number = models.CharField(max_length=40, unique=True)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    designation = models.ForeignKey(Designation, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT)
    employment_type = models.CharField(max_length=20, choices=EmploymentType.choices)
    proposed_joining_date = models.DateField()
    offered_base_salary = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    probation_months = models.PositiveSmallIntegerField(null=True, blank=True)
    offer_expiry_date = models.DateField(null=True, blank=True)
    terms_summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=OfferStatus.choices, default=OfferStatus.DRAFT)  # noqa: F405
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_offers")
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_offers"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("approve_offer", "Can approve employment offers"),
            ("view_offer_salary", "Can view offered salary"),
        ]


class EmploymentOfferRevision(UUIDModel):
    offer = models.ForeignKey(EmploymentOffer, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    snapshot = models.JSONField()
    reason = models.TextField()
    revised_by = models.ForeignKey(User, on_delete=models.PROTECT)
    revised_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["offer", "revision_number"], name="uniq_offer_revision")
        ]


class OnboardingChecklistTemplate(RecruitmentModel, ActiveModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices, blank=True)
    designation = models.ForeignKey(Designation, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_onboarding_template_code"
            )
        ]


class OnboardingChecklistTemplateItem(RecruitmentModel):
    template = models.ForeignKey(
        OnboardingChecklistTemplate, on_delete=models.PROTECT, related_name="items"
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_mandatory = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    requirement_type = models.CharField(max_length=20, choices=RequirementType.choices)  # noqa: F405


class OnboardingCase(RecruitmentModel):
    application = models.OneToOneField(
        CandidateApplication, on_delete=models.PROTECT, related_name="onboarding"
    )
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT)
    accepted_offer = models.OneToOneField(EmploymentOffer, on_delete=models.PROTECT)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.PROTECT)
    designation = models.ForeignKey(Designation, on_delete=models.PROTECT)
    proposed_employee_number = models.CharField(max_length=32, blank=True)
    proposed_joining_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=OnboardingStatus.choices, default=OnboardingStatus.IN_PROGRESS
    )  # noqa: F405
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    ready_to_hire_at = models.DateTimeField(null=True, blank=True)
    hired_at = models.DateTimeField(null=True, blank=True)


class OnboardingChecklistItem(RecruitmentModel):
    onboarding_case = models.ForeignKey(
        OnboardingCase, on_delete=models.PROTECT, related_name="checklist_items"
    )
    template_item = models.ForeignKey(
        OnboardingChecklistTemplateItem, null=True, blank=True, on_delete=models.PROTECT
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_mandatory = models.BooleanField(default=True)
    status = models.CharField(
        max_length=20, choices=ChecklistStatus.choices, default=ChecklistStatus.PENDING
    )  # noqa: F405
    completed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="completed_onboarding_items",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    waived_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="waived_onboarding_items",
    )
    waiver_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
