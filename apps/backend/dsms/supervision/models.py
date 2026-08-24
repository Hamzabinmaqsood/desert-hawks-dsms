# mypy: disable-error-code="no-untyped-def,union-attr,operator"
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.attendance.models import AttendanceRecord
from dsms.common.models import TimeStampedModel, UUIDModel
from dsms.contracts.models import SecurityPost, SecuritySite, SiteType
from dsms.deployment.models import DutyAssignment
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Designation, OperationalZone
from dsms.workforce.models import Employee

from . import enums
from .storage import field_evidence_upload_to, private_evidence_storage


class SupervisionModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class SupervisionAssignment(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    supervisor = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="supervision_assignments"
    )
    scope_type = models.CharField(max_length=20, choices=enums.SupervisionScopeType.choices)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    operational_zone = models.ForeignKey(
        OperationalZone, null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(SecuritySite, null=True, blank=True, on_delete=models.PROTECT)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.SupervisionAssignmentStatus.choices, default="DRAFT"
    )
    is_primary = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_supervision_assignments"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_supervision_assignments",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("manage_supervisionassignment", "Can manage supervision assignments"),
            ("create_visitplan", "Can create supervisor visit plans"),
            ("approve_visitplan", "Can approve supervisor visit plans"),
            ("start_site_visit", "Can start supervisor site visits"),
            ("end_site_visit", "Can end supervisor site visits"),
            ("manage_inspection_templates", "Can manage inspection templates"),
            ("perform_site_inspection", "Can perform site inspections"),
            ("perform_post_inspection", "Can perform post inspections"),
            ("perform_guard_inspection", "Can perform guard inspections"),
            ("review_inspection", "Can review inspections"),
            ("create_finding", "Can create inspection findings"),
            ("manage_finding", "Can manage inspection findings"),
            ("create_corrective_action", "Can create corrective actions"),
            ("assign_corrective_action", "Can assign corrective actions"),
            ("complete_corrective_action", "Can complete corrective actions"),
            ("verify_corrective_action", "Can verify corrective actions"),
            ("view_guard_observation", "Can view guard observations"),
            ("verify_guard", "Can verify guards during visits"),
            ("submit_daily_report", "Can submit supervisor daily reports"),
            ("review_daily_report", "Can review supervisor daily reports"),
            ("approve_daily_report", "Can approve supervisor daily reports"),
        ]

    def clean(self):
        errors = {}
        if self.supervisor_id and self.company_id and self.supervisor.company_id != self.company_id:
            errors["supervisor"] = "Supervisor must belong to the company."
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            errors["branch"] = "Branch must belong to the company."
        if self.operational_zone_id and self.operational_zone.branch_id != self.branch_id:
            errors["operational_zone"] = "Operational zone must belong to the branch."
        if self.site_id and (
            self.site.company_id != self.company_id
            or self.site.managing_branch_id != self.branch_id
        ):
            errors["site"] = "Site must belong to the company and branch."
        if self.scope_type == "SITE" and not self.site_id:
            errors["site"] = "Site scope requires a site."
        if self.scope_type == "OPERATIONAL_ZONE" and not self.operational_zone_id:
            errors["operational_zone"] = "Zone scope requires an operational zone."
        if self.scope_type == "BRANCH" and (self.operational_zone_id or self.site_id):
            errors["scope_type"] = "Branch scope cannot specify a zone or site."
        if self.effective_to and self.effective_to < self.effective_from:
            errors["effective_to"] = "End date cannot precede start date."
        if errors:
            raise ValidationError(errors)


class VisitFrequencyRequirement(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    operational_zone = models.ForeignKey(
        OperationalZone, null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(SecuritySite, null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    visits_required = models.PositiveIntegerField()
    frequency_period = models.CharField(max_length=10, choices=enums.FrequencyPeriod.choices)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    priority = models.CharField(
        max_length=10, choices=enums.VisitPriority.choices, default="NORMAL"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(visits_required__gt=0), name="supervision_visit_frequency_positive"
            )
        ]


class SupervisorVisitPlan(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    supervisor = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="visit_plans")
    supervision_assignment = models.ForeignKey(
        SupervisionAssignment, null=True, blank=True, on_delete=models.PROTECT
    )
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    planned_date = models.DateField()
    planned_start_at = models.DateTimeField(null=True, blank=True)
    planned_end_at = models.DateTimeField(null=True, blank=True)
    priority = models.CharField(
        max_length=10, choices=enums.VisitPriority.choices, default="NORMAL"
    )
    purpose = models.TextField()
    status = models.CharField(max_length=20, choices=enums.VisitPlanStatus.choices, default="DRAFT")
    generated_from_requirement = models.ForeignKey(
        VisitFrequencyRequirement, null=True, blank=True, on_delete=models.PROTECT
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_visit_plans"
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_visit_plans"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["supervisor", "site", "planned_date"],
                condition=~Q(status="CANCELLED"),
                name="uniq_active_supervisor_site_plan_day",
            )
        ]


class SiteVisit(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    supervisor = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="site_visits")
    visit_plan = models.ForeignKey(
        SupervisorVisitPlan, null=True, blank=True, on_delete=models.PROTECT, related_name="visits"
    )
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    site = models.ForeignKey(
        SecuritySite, on_delete=models.PROTECT, related_name="supervisor_visits"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.SiteVisitStatus.choices, default="IN_PROGRESS"
    )
    verification_method = models.CharField(
        max_length=30, choices=enums.VisitVerificationMethod.choices
    )
    verification_result = models.CharField(
        max_length=20, choices=enums.VisitVerificationResult.choices
    )
    arrival_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    arrival_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    arrival_accuracy_meters = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    arrival_distance_from_site_meters = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    departure_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    departure_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    departure_accuracy_meters = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    visit_summary = models.TextField(blank=True)
    client_contact_met = models.BooleanField(null=True, blank=True)
    client_contact_name = models.CharField(max_length=150, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["supervisor"],
                condition=Q(status="IN_PROGRESS"),
                name="uniq_open_site_visit_per_supervisor",
            )
        ]
        permissions = [
            ("view_sensitive_visit_location", "Can view exact supervisor visit coordinates")
        ]

    @property
    def duration_minutes(self):
        return (
            int((self.ended_at - self.started_at).total_seconds() // 60) if self.ended_at else None
        )


class InspectionTemplate(SupervisionModel):
    company = models.ForeignKey(Company, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    scope = models.CharField(max_length=10, choices=enums.InspectionScope.choices)
    description = models.TextField(blank=True)
    site_type = models.ForeignKey(SiteType, null=True, blank=True, on_delete=models.PROTECT)
    designation = models.ForeignKey(Designation, null=True, blank=True, on_delete=models.PROTECT)
    employee_type = models.CharField(max_length=30, blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    version_number = models.PositiveIntegerField(default=1)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code", "version_number"],
                name="uniq_inspection_template_version",
            )
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class InspectionTemplateSection(UUIDModel):
    template = models.ForeignKey(
        InspectionTemplate, on_delete=models.PROTECT, related_name="sections"
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class InspectionTemplateItem(UUIDModel):
    section = models.ForeignKey(
        InspectionTemplateSection, on_delete=models.PROTECT, related_name="items"
    )
    code = models.CharField(max_length=50)
    question = models.TextField()
    help_text = models.TextField(blank=True)
    response_type = models.CharField(max_length=20, choices=enums.ChecklistResponseType.choices)
    is_required = models.BooleanField(default=True)
    weight = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    minimum_score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    requires_comment_on_failure = models.BooleanField(default=False)
    requires_photo_on_failure = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class InspectionTemplateItemOption(UUIDModel):
    item = models.ForeignKey(
        InspectionTemplateItem, on_delete=models.PROTECT, related_name="options"
    )
    value = models.CharField(max_length=100)
    label = models.CharField(max_length=150)
    score = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)


class SiteInspection(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    site_visit = models.ForeignKey(SiteVisit, on_delete=models.PROTECT, related_name="inspections")
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    inspected_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT
    )
    template = models.ForeignKey(InspectionTemplate, on_delete=models.PROTECT)
    template_version = models.PositiveIntegerField()
    scope = models.CharField(max_length=10, choices=enums.InspectionScope.choices)
    status = models.CharField(
        max_length=20, choices=enums.InspectionStatus.choices, default="DRAFT"
    )
    started_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_site_inspections",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    result = models.CharField(max_length=30, choices=enums.InspectionResult.choices, blank=True)
    total_score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    maximum_score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    summary = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_site_inspections"
    )


class InspectionResponse(SupervisionModel):
    inspection = models.ForeignKey(
        SiteInspection, on_delete=models.PROTECT, related_name="responses"
    )
    template_item = models.ForeignKey(InspectionTemplateItem, on_delete=models.PROTECT)
    boolean_value = models.BooleanField(null=True, blank=True)
    text_value = models.TextField(blank=True)
    numeric_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    selected_option = models.ForeignKey(
        InspectionTemplateItemOption, null=True, blank=True, on_delete=models.PROTECT
    )
    score = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_noncompliant = models.BooleanField(default=False)
    comment = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["inspection", "template_item"], name="uniq_inspection_item_response"
            )
        ]


class GuardObservation(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    site_visit = models.ForeignKey(
        SiteVisit, on_delete=models.PROTECT, related_name="guard_observations"
    )
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    post = models.ForeignKey(SecurityPost, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.PROTECT)
    expected_duty_assignment = models.ForeignKey(
        DutyAssignment, null=True, blank=True, on_delete=models.PROTECT
    )
    attendance_record = models.ForeignKey(
        AttendanceRecord, null=True, blank=True, on_delete=models.PROTECT
    )
    observation_status = models.CharField(
        max_length=40, choices=enums.GuardObservationStatus.choices
    )
    observed_at = models.DateTimeField()
    uniform_compliant = models.BooleanField(null=True, blank=True)
    grooming_compliant = models.BooleanField(null=True, blank=True)
    identity_badge_available = models.BooleanField(null=True, blank=True)
    alert_and_attentive = models.BooleanField(null=True, blank=True)
    understands_post_instructions = models.BooleanField(null=True, blank=True)
    required_equipment_available = models.BooleanField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)


class InspectionFinding(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    inspection = models.ForeignKey(
        SiteInspection, on_delete=models.PROTECT, related_name="findings"
    )
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, null=True, blank=True, on_delete=models.PROTECT)
    template_item = models.ForeignKey(
        InspectionTemplateItem, null=True, blank=True, on_delete=models.PROTECT
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=enums.FindingSeverity.choices)
    status = models.CharField(max_length=20, choices=enums.FindingStatus.choices, default="OPEN")
    requires_corrective_action = models.BooleanField(default=False)
    requires_incident_escalation = models.BooleanField(default=False)
    target_resolution_date = models.DateField(null=True, blank=True)
    identified_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="identified_findings"
    )
    identified_at = models.DateTimeField()
    acknowledged_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="acknowledged_findings"
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_summary = models.TextField(blank=True)


class CorrectiveAction(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    finding = models.ForeignKey(
        InspectionFinding, on_delete=models.PROTECT, related_name="corrective_actions"
    )
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(
        max_length=10, choices=enums.CorrectiveActionPriority.choices, default="NORMAL"
    )
    assigned_to_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_corrective_actions",
    )
    assigned_to_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT
    )
    assigned_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="delegated_corrective_actions"
    )
    assigned_at = models.DateTimeField()
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=enums.CorrectiveActionStatus.choices, default="OPEN"
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)
    verification_required = models.BooleanField(default=True)
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="verified_corrective_actions",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)

    @property
    def is_overdue(self):
        from django.utils import timezone

        return bool(
            self.due_at
            and self.due_at < timezone.now()
            and self.status not in {"VERIFIED", "CLOSED", "CANCELLED"}
        )

    @property
    def days_overdue(self):
        from django.utils import timezone

        return max(0, (timezone.now() - self.due_at).days) if self.is_overdue else 0


class FieldEvidence(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    site_visit = models.ForeignKey(SiteVisit, null=True, blank=True, on_delete=models.PROTECT)
    inspection = models.ForeignKey(
        SiteInspection, null=True, blank=True, on_delete=models.PROTECT, related_name="evidence"
    )
    finding = models.ForeignKey(InspectionFinding, null=True, blank=True, on_delete=models.PROTECT)
    corrective_action = models.ForeignKey(
        CorrectiveAction, null=True, blank=True, on_delete=models.PROTECT, related_name="evidence"
    )
    file = models.FileField(storage=private_evidence_storage, upload_to=field_evidence_upload_to)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField()
    mime_type = models.CharField(max_length=100)
    sha256_hash = models.CharField(max_length=64)
    caption = models.TextField(blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [
            ("download_field_evidence", "Can securely download field evidence"),
            ("view_sensitive_field_evidence", "Can view sensitive field evidence"),
        ]


class SiteObservation(UUIDModel):
    site_visit = models.ForeignKey(
        SiteVisit, on_delete=models.PROTECT, related_name="site_observations"
    )
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    category = models.CharField(max_length=30, choices=enums.ObservationCategory.choices)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=enums.FindingSeverity.choices)
    requires_follow_up = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class SiteVisitClientFeedback(UUIDModel):
    site_visit = models.ForeignKey(
        SiteVisit, on_delete=models.PROTECT, related_name="client_feedback"
    )
    contact_name = models.CharField(max_length=150)
    designation = models.CharField(max_length=150, blank=True)
    feedback = models.TextField()
    satisfaction_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    requires_follow_up = models.BooleanField(default=False)
    captured_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(satisfaction_rating__isnull=True)
                | Q(satisfaction_rating__gte=1, satisfaction_rating__lte=5),
                name="supervision_feedback_rating_range",
            )
        ]


class SupervisorDailyReport(SupervisionModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    supervisor = models.ForeignKey(Employee, on_delete=models.PROTECT)
    report_date = models.DateField()
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20, choices=enums.DailyReportStatus.choices, default="DRAFT"
    )
    summary = models.TextField()
    key_issues = models.TextField(blank=True)
    unresolved_items = models.TextField(blank=True)
    support_required = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_supervisor_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_comments = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_supervisor_reports",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["supervisor", "report_date", "branch"], name="uniq_supervisor_daily_report"
            )
        ]
        permissions = [
            ("view_supervision_dashboard", "Can view supervision dashboard"),
            ("view_supervision_reports", "Can view supervision reports"),
            ("view_supervision_audit", "Can view supervision audit"),
        ]
