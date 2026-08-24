from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel

from .enums import (
    AppraisalSectionType,
    GoalMeasurementType,
    GoalStatus,
    KPIDataSource,
    KPIDirection,
    KPIResultStatus,
    PerformanceCycleStatus,
    PerformancePlanStatus,
    RecognitionStatus,
)


class PerformanceModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class PerformanceCycle(PerformanceModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    period_start = models.DateField()
    period_end = models.DateField()
    planning_opens_at = models.DateTimeField(null=True, blank=True)
    planning_closes_at = models.DateTimeField(null=True, blank=True)
    self_review_opens_at = models.DateTimeField(null=True, blank=True)
    self_review_closes_at = models.DateTimeField(null=True, blank=True)
    manager_review_opens_at = models.DateTimeField(null=True, blank=True)
    manager_review_closes_at = models.DateTimeField(null=True, blank=True)
    calibration_opens_at = models.DateTimeField(null=True, blank=True)
    calibration_closes_at = models.DateTimeField(null=True, blank=True)
    finalization_due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=PerformanceCycleStatus.choices, default=PerformanceCycleStatus.DRAFT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_performance_cycles",
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="opened_performance_cycles",
    )
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="finalized_performance_cycles",
    )
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="performance_cycle_company_code_uniq"
            ),
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")),
                name="performance_cycle_dates_valid",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class PerformanceRatingScale(PerformanceModel, ActiveModel):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    minimum_score = models.DecimalField(max_digits=8, decimal_places=3)
    maximum_score = models.DecimalField(max_digits=8, decimal_places=3)
    is_system = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="performance_scale_company_code_uniq"
            ),
            models.CheckConstraint(
                condition=Q(maximum_score__gte=models.F("minimum_score")),
                name="performance_scale_bounds_valid",
            ),
        ]


class PerformanceRatingBand(UUIDModel):
    scale = models.ForeignKey(
        PerformanceRatingScale, on_delete=models.PROTECT, related_name="bands"
    )
    code = models.CharField(max_length=50)
    label = models.CharField(max_length=100)
    minimum_score = models.DecimalField(max_digits=8, decimal_places=3)
    maximum_score = models.DecimalField(max_digits=8, decimal_places=3)
    numeric_value = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scale", "code"], name="performance_band_scale_code_uniq"
            ),
            models.CheckConstraint(
                condition=Q(maximum_score__gte=models.F("minimum_score")),
                name="performance_band_bounds_valid",
            ),
        ]


class KPIDefinition(PerformanceModel, ActiveModel):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField()
    data_source = models.CharField(max_length=30, choices=KPIDataSource.choices)
    measurement_type = models.CharField(max_length=30, choices=GoalMeasurementType.choices)
    direction = models.CharField(max_length=30, choices=KPIDirection.choices)
    unit = models.CharField(max_length=30)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    default_weight = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="performance_kpi_company_code_uniq"
            ),
            models.CheckConstraint(
                condition=Q(default_weight__isnull=True) | Q(default_weight__gte=0),
                name="performance_kpi_weight_nonnegative",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class PerformanceTemplate(PerformanceModel, ActiveModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    employee_type = models.CharField(max_length=30, blank=True)
    employment_type = models.CharField(max_length=30, blank=True)
    designation = models.ForeignKey(
        "organization.Designation", null=True, blank=True, on_delete=models.PROTECT
    )
    department = models.ForeignKey(
        "organization.Department", null=True, blank=True, on_delete=models.PROTECT
    )
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    is_default = models.BooleanField(default=False)
    version_number = models.PositiveIntegerField(default=1)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code", "version_number"],
                name="performance_template_version_uniq",
            )
        ]


class PerformanceTemplateSection(UUIDModel):
    template = models.ForeignKey(
        PerformanceTemplate, on_delete=models.PROTECT, related_name="sections"
    )
    section_type = models.CharField(max_length=30, choices=AppraisalSectionType.choices)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=3)
    rating_scale = models.ForeignKey(
        PerformanceRatingScale, null=True, blank=True, on_delete=models.PROTECT
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["template", "code"], name="performance_section_template_code_uniq"
            ),
            models.CheckConstraint(
                condition=Q(weight__gte=0), name="performance_section_weight_nonnegative"
            ),
        ]


class PerformanceTemplateKPI(UUIDModel):
    section = models.ForeignKey(
        PerformanceTemplateSection, on_delete=models.PROTECT, related_name="kpis"
    )
    kpi_definition = models.ForeignKey(KPIDefinition, on_delete=models.PROTECT)
    weight = models.DecimalField(max_digits=8, decimal_places=3)
    target_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    minimum_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    stretch_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    is_required = models.BooleanField(default=True)
    allow_manager_override = models.BooleanField(default=False)
    override_requires_comment = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(weight__gte=0), name="performance_template_kpi_weight_nonnegative"
            )
        ]


class EmployeePerformancePlan(PerformanceModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    employee = models.ForeignKey(
        "workforce.Employee", on_delete=models.PROTECT, related_name="performance_plans"
    )
    cycle = models.ForeignKey(PerformanceCycle, on_delete=models.PROTECT, related_name="plans")
    template = models.ForeignKey(PerformanceTemplate, on_delete=models.PROTECT)
    template_version = models.PositiveIntegerField()
    manager_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="managed_performance_plans",
    )
    secondary_reviewer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="secondary_performance_plans",
    )
    status = models.CharField(
        max_length=30, choices=PerformancePlanStatus.choices, default=PerformancePlanStatus.DRAFT
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    self_review_submitted_at = models.DateTimeField(null=True, blank=True)
    manager_review_submitted_at = models.DateTimeField(null=True, blank=True)
    secondary_review_submitted_at = models.DateTimeField(null=True, blank=True)
    calibrated_at = models.DateTimeField(null=True, blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    final_score = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    final_rating_band = models.ForeignKey(
        PerformanceRatingBand, null=True, blank=True, on_delete=models.PROTECT
    )
    final_summary = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_performance_plans"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "cycle"], name="performance_employee_cycle_plan_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="perf_plan_company_status_idx"),
            models.Index(fields=["manager_user", "status"], name="perf_plan_manager_status_idx"),
        ]
        permissions = [
            ("finalize_performance_review", "Can human-finalize performance reviews"),
            ("view_performance_score", "Can view sensitive performance scores"),
            ("view_calibration_details", "Can view calibration details"),
        ]

    def clean(self) -> None:
        if (
            self.employee.company_id != self.company_id
            or self.cycle.company_id != self.company_id
            or self.template.company_id != self.company_id
        ):
            raise ValidationError("Plan employee, cycle, template, and company must agree.")


class PerformanceGoal(PerformanceModel):
    plan = models.ForeignKey(
        EmployeePerformancePlan, on_delete=models.PROTECT, related_name="goals"
    )
    goal_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField()
    measurement_type = models.CharField(max_length=30, choices=GoalMeasurementType.choices)
    target_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    target_text = models.TextField(blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=3)
    start_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=30, choices=GoalStatus.choices, default=GoalStatus.DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_performance_goals"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_performance_goals",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "goal_number"], name="performance_goal_plan_number_uniq"
            ),
            models.CheckConstraint(
                condition=Q(weight__gte=0), name="performance_goal_weight_nonnegative"
            ),
            models.CheckConstraint(
                condition=Q(due_date__gte=models.F("start_date")),
                name="performance_goal_dates_valid",
            ),
        ]


class PerformanceGoalProgress(UUIDModel):
    goal = models.ForeignKey(
        PerformanceGoal, on_delete=models.PROTECT, related_name="progress_entries"
    )
    progress_date = models.DateField()
    progress_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    progress_percentage = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    comment = models.TextField()
    entered_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    evidence_reference = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class EmployeeKPIAssignment(UUIDModel):
    plan = models.ForeignKey(
        EmployeePerformancePlan, on_delete=models.PROTECT, related_name="kpi_assignments"
    )
    template_kpi = models.ForeignKey(PerformanceTemplateKPI, on_delete=models.PROTECT)
    kpi_definition = models.ForeignKey(KPIDefinition, on_delete=models.PROTECT)
    weight = models.DecimalField(max_digits=8, decimal_places=3)
    target_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    baseline_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    stretch_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "template_kpi"], name="performance_plan_template_kpi_uniq"
            )
        ]


class PerformanceKPIResult(PerformanceModel):
    plan = models.ForeignKey(
        EmployeePerformancePlan, on_delete=models.PROTECT, related_name="kpi_results"
    )
    employee_kpi_assignment = models.ForeignKey(
        EmployeeKPIAssignment, on_delete=models.PROTECT, related_name="results"
    )
    measurement_period_start = models.DateField()
    measurement_period_end = models.DateField()
    calculated_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    source = models.CharField(max_length=30, choices=KPIDataSource.choices)
    source_reference = models.JSONField(default=dict)
    calculated_at = models.DateTimeField(null=True, blank=True)
    calculation_version = models.CharField(max_length=30)
    status = models.CharField(
        max_length=30, choices=KPIResultStatus.choices, default=KPIResultStatus.PENDING
    )
    finalized_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    override_reason = models.TextField(blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT
    )
    finalized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["plan", "status"], name="perf_kpi_result_status_idx")]


class SelfAssessmentSummary(UUIDModel):
    plan = models.OneToOneField(
        EmployeePerformancePlan, on_delete=models.PROTECT, related_name="self_assessment"
    )
    employee = models.ForeignKey("workforce.Employee", on_delete=models.PROTECT)
    achievements = models.TextField()
    challenges = models.TextField()
    development_needs = models.TextField()
    additional_comments = models.TextField(blank=True)
    submitted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Submitted self-assessments are immutable.")
        if self.employee_id != self.plan.employee_id:
            raise ValidationError("Self-assessment employee does not match the plan.")
        super().save(*args, **kwargs)


class ManagerAssessmentSummary(UUIDModel):
    plan = models.OneToOneField(
        EmployeePerformancePlan, on_delete=models.PROTECT, related_name="manager_assessment"
    )
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    strengths = models.TextField()
    improvement_areas = models.TextField()
    overall_comments = models.TextField()
    recommended_development = models.TextField(blank=True)
    submitted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class PerformanceCalibrationAdjustment(UUIDModel):
    plan = models.ForeignKey(
        EmployeePerformancePlan, on_delete=models.PROTECT, related_name="calibration_adjustments"
    )
    before_score = models.DecimalField(max_digits=8, decimal_places=3)
    after_score = models.DecimalField(max_digits=8, decimal_places=3)
    before_rating = models.ForeignKey(
        PerformanceRatingBand,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="calibration_before",
    )
    after_rating = models.ForeignKey(
        PerformanceRatingBand,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="calibration_after",
    )
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class PerformanceAcknowledgement(UUIDModel):
    plan = models.OneToOneField(
        EmployeePerformancePlan, on_delete=models.PROTECT, related_name="acknowledgement"
    )
    employee = models.ForeignKey("workforce.Employee", on_delete=models.PROTECT)
    acknowledged_at = models.DateTimeField()
    agrees_with_review = models.BooleanField(null=True, blank=True)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RecognitionNomination(PerformanceModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    employee = models.ForeignKey(
        "workforce.Employee", on_delete=models.PROTECT, related_name="recognition_nominations"
    )
    recognition_type = models.CharField(max_length=40)
    reason = models.TextField()
    status = models.CharField(
        max_length=30, choices=RecognitionStatus.choices, default=RecognitionStatus.NOMINATED
    )
    nominated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="performance_nominations"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_performance_nominations",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        permissions = [
            ("approve_recognition", "Can approve recognition without creating compensation")
        ]
