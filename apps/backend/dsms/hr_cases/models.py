from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel

from .enums import (
    AllegationStatus,
    AppealStatus,
    CaseConfidentiality,
    CaseEventType,
    CasePriority,
    EvidenceType,
    HRActionType,
    HRCaseStatus,
    HRCaseType,
    InvestigationStatus,
    OutcomeFinding,
)
from .storage import hr_case_evidence_upload_to, private_document_storage


class HRCaseModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class HRCaseCategory(HRCaseModel, ActiveModel):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    case_type = models.CharField(max_length=40, choices=HRCaseType.choices)
    description = models.TextField(blank=True)
    default_priority = models.CharField(
        max_length=20, choices=CasePriority.choices, default=CasePriority.NORMAL
    )
    default_confidentiality = models.CharField(
        max_length=30, choices=CaseConfidentiality.choices, default=CaseConfidentiality.CONFIDENTIAL
    )
    requires_investigation = models.BooleanField(default=True)
    requires_employee_response = models.BooleanField(default=False)
    requires_hearing = models.BooleanField(default=False)
    allows_appeal = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="hr_case_category_company_code_uniq"
            ),
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(company__isnull=True),
                name="hr_case_category_global_code_uniq",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class HRCase(HRCaseModel):
    case_number = models.CharField(max_length=40)
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    employee_subject = models.ForeignKey(
        "workforce.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="hr_cases_as_subject",
    )
    complainant_employee = models.ForeignKey(
        "workforce.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="hr_cases_as_complainant",
    )
    complainant_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="hr_case_complaints",
    )
    external_complainant_name = models.CharField(max_length=200, blank=True)
    external_complainant_contact = models.CharField(max_length=200, blank=True)
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    department = models.ForeignKey(
        "organization.Department", null=True, blank=True, on_delete=models.PROTECT
    )
    designation_snapshot = models.CharField(max_length=150, blank=True)
    site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    case_type = models.CharField(max_length=40, choices=HRCaseType.choices)
    category = models.ForeignKey(HRCaseCategory, on_delete=models.PROTECT)
    priority = models.CharField(max_length=20, choices=CasePriority.choices)
    confidentiality = models.CharField(max_length=30, choices=CaseConfidentiality.choices)
    status = models.CharField(
        max_length=40, choices=HRCaseStatus.choices, default=HRCaseStatus.DRAFT
    )
    title = models.CharField(max_length=255)
    summary = models.TextField()
    reported_at = models.DateTimeField()
    alleged_event_at = models.DateTimeField(null=True, blank=True)
    case_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="managed_hr_cases",
    )
    assigned_hr_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_hr_cases",
    )
    assigned_investigator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="investigated_hr_cases",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    triaged_at = models.DateTimeField(null=True, blank=True)
    investigation_started_at = models.DateTimeField(null=True, blank=True)
    investigation_completed_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_hr_cases"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "case_number"], name="hr_case_company_number_uniq"
            )
        ]
        indexes = [
            models.Index(
                fields=["company", "status", "confidentiality"], name="hr_case_company_status_idx"
            ),
            models.Index(
                fields=["employee_subject", "reported_at"], name="hr_case_subject_reported_idx"
            ),
        ]
        permissions = [
            ("triage_hrcase", "Can triage HR cases"),
            ("investigate_hrcase", "Can investigate HR cases"),
            ("view_confidential_case", "Can view confidential cases"),
            ("view_highly_confidential_case", "Can view highly confidential cases"),
            ("decide_hrcase", "Can decide HR cases"),
            ("execute_workforce_action", "Can explicitly execute approved workforce action"),
        ]

    def clean(self) -> None:
        for field in ("employee_subject", "complainant_employee"):
            employee = getattr(self, field)
            if employee and employee.company_id != self.company_id:
                raise ValidationError({field: "Employee belongs to another company."})
        if self.category.company_id not in (None, self.company_id):
            raise ValidationError({"category": "Category belongs to another company."})


class HRCaseSourceReference(UUIDModel):
    hr_case = models.ForeignKey(HRCase, on_delete=models.PROTECT, related_name="source_references")
    source_type = models.CharField(max_length=40)
    source_object_id = models.UUIDField()
    source_app = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    linked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    linked_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_app", "source_type", "source_object_id"],
                name="hr_case_source_ref_uniq",
            )
        ]


class HRCaseAllegation(HRCaseModel):
    hr_case = models.ForeignKey(HRCase, on_delete=models.PROTECT, related_name="allegations")
    allegation_number = models.PositiveIntegerField()
    category_code = models.CharField(max_length=50)
    description = models.TextField()
    alleged_policy_reference = models.CharField(max_length=200, blank=True)
    alleged_event_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=40, choices=AllegationStatus.choices, default=AllegationStatus.OPEN
    )
    investigator_summary = models.TextField(blank=True)
    decision_reasoning = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hr_case", "allegation_number"], name="hr_case_allegation_number_uniq"
            )
        ]


class HRInvestigation(HRCaseModel):
    hr_case = models.OneToOneField(HRCase, on_delete=models.PROTECT, related_name="investigation")
    status = models.CharField(
        max_length=30, choices=InvestigationStatus.choices, default=InvestigationStatus.NOT_STARTED
    )
    lead_investigator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="led_hr_investigations"
    )
    secondary_investigators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="secondary_hr_investigations"
    )
    terms_of_reference = models.TextField()
    started_at = models.DateTimeField(null=True, blank=True)
    target_completion_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    investigation_summary = models.TextField(blank=True)

    def clean(self) -> None:
        subject = self.hr_case.employee_subject if self.hr_case.employee_subject_id else None
        subject_user_id = subject.user_id if subject is not None else None
        if subject_user_id == self.lead_investigator_id:
            raise ValidationError(
                {"lead_investigator": "The case subject cannot investigate their own case."}
            )
        if self.hr_case.complainant_user_id == self.lead_investigator_id:
            raise ValidationError(
                {"lead_investigator": "The complainant cannot be sole lead investigator."}
            )


class HRCaseEvidence(UUIDModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    hr_case = models.ForeignKey(HRCase, on_delete=models.PROTECT, related_name="evidence")
    allegation = models.ForeignKey(
        HRCaseAllegation, null=True, blank=True, on_delete=models.PROTECT
    )
    evidence_type = models.CharField(max_length=40, choices=EvidenceType.choices)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_reference = models.ForeignKey(
        HRCaseSourceReference, null=True, blank=True, on_delete=models.PROTECT
    )
    file = models.FileField(
        storage=private_document_storage,
        upload_to=hr_case_evidence_upload_to,
        null=True,
        blank=True,
    )
    external_reference = models.CharField(max_length=255, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    sha256_hash = models.CharField(max_length=64, blank=True)
    provided_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="provided_hr_evidence",
    )
    provided_by_employee = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    collected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="collected_hr_evidence"
    )
    collected_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class HRCaseEvent(UUIDModel):
    hr_case = models.ForeignKey(HRCase, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=40, choices=CaseEventType.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    event_time = models.DateTimeField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Case timeline events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Case timeline events cannot be deleted.")


class HRResponseRequest(UUIDModel):
    hr_case = models.ForeignKey(HRCase, on_delete=models.PROTECT, related_name="response_requests")
    allegation = models.ForeignKey(
        HRCaseAllegation, null=True, blank=True, on_delete=models.PROTECT
    )
    requested_from_employee = models.ForeignKey("workforce.Employee", on_delete=models.PROTECT)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issued_at = models.DateTimeField()
    due_at = models.DateTimeField()
    title = models.CharField(max_length=255)
    notice_text = models.TextField()
    status = models.CharField(max_length=30, default="ISSUED")
    created_at = models.DateTimeField(auto_now_add=True)


class HRCaseResponse(UUIDModel):
    response_request = models.ForeignKey(
        HRResponseRequest, on_delete=models.PROTECT, related_name="responses"
    )
    employee = models.ForeignKey("workforce.Employee", on_delete=models.PROTECT)
    submitted_at = models.DateTimeField()
    response_text = models.TextField()
    is_supplementary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError(
                "Submitted responses are immutable; add a supplementary response."
            )
        if self.employee_id != self.response_request.requested_from_employee_id:
            raise ValidationError("Only the requested employee may submit this response.")
        super().save(*args, **kwargs)


class HRInvestigationFinding(UUIDModel):
    investigation = models.ForeignKey(
        HRInvestigation, on_delete=models.PROTECT, related_name="findings"
    )
    allegation = models.OneToOneField(HRCaseAllegation, on_delete=models.PROTECT)
    finding = models.CharField(max_length=40, choices=OutcomeFinding.choices)
    summary = models.TextField()
    supporting_evidence_summary = models.TextField()
    conflicting_evidence_summary = models.TextField(blank=True)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class HRCaseDecision(UUIDModel):
    hr_case = models.OneToOneField(HRCase, on_delete=models.PROTECT, related_name="decision")
    overall_finding = models.CharField(max_length=40, choices=OutcomeFinding.choices)
    decision_summary = models.TextField()
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    decided_at = models.DateTimeField()
    action_type = models.CharField(max_length=40, choices=HRActionType.choices)
    action_reason = models.TextField()
    effective_from = models.DateField(null=True, blank=True)
    effective_until = models.DateField(null=True, blank=True)
    requires_workforce_action = models.BooleanField(default=False)
    requires_training_referral = models.BooleanField(default=False)
    requires_finance_follow_up = models.BooleanField(default=False)
    requires_asset_follow_up = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class HRCaseAppeal(HRCaseModel):
    hr_case = models.ForeignKey(HRCase, on_delete=models.PROTECT, related_name="appeals")
    appellant_employee = models.ForeignKey("workforce.Employee", on_delete=models.PROTECT)
    grounds = models.TextField()
    submitted_at = models.DateTimeField()
    status = models.CharField(
        max_length=30, choices=AppealStatus.choices, default=AppealStatus.SUBMITTED
    )
    assigned_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="hr_appeals_to_review",
    )
    decision_summary = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decided_hr_appeals",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hr_case", "appellant_employee"],
                condition=Q(status__in=[AppealStatus.SUBMITTED, AppealStatus.UNDER_REVIEW]),
                name="hr_case_one_open_appeal_uniq",
            )
        ]


class HRCaseAccessGrant(UUIDModel):
    hr_case = models.ForeignKey(HRCase, on_delete=models.PROTECT, related_name="access_grants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="granted_hr_case_access"
    )
    reason = models.TextField()
    granted_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["hr_case", "user"],
                condition=Q(revoked_at__isnull=True),
                name="hr_case_active_access_grant_uniq",
            )
        ]
