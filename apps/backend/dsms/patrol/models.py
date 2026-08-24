# mypy: disable-error-code="no-untyped-def,union-attr,operator"
from django.db import models
from django.db.models import Q

from dsms.common.models import TimeStampedModel, UUIDModel
from dsms.contracts.models import Client, SecurityPost, SecuritySite
from dsms.deployment.models import DutyAssignment
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Designation
from dsms.workforce.models import Employee

from . import enums
from .storage import patrol_evidence_upload_to, private_patrol_storage


class PatrolModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class PatrolPolicy(PatrolModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    early_start_tolerance_minutes = models.PositiveIntegerField(default=0)
    late_start_tolerance_minutes = models.PositiveIntegerField(default=0)
    checkpoint_early_tolerance_minutes = models.PositiveIntegerField(default=0)
    checkpoint_late_tolerance_minutes = models.PositiveIntegerField(default=0)
    patrol_completion_tolerance_minutes = models.PositiveIntegerField(default=0)
    require_gps = models.BooleanField(default=False)
    require_checkpoint_token = models.BooleanField(default=True)
    allow_qr = models.BooleanField(default=True)
    allow_nfc = models.BooleanField(default=False)
    allow_supervisor_verification = models.BooleanField(default=True)
    allow_manual_verification = models.BooleanField(default=False)
    allow_offline_submission = models.BooleanField(default=False)
    maximum_gps_accuracy_meters = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    checkpoint_geofence_tolerance_meters = models.PositiveIntegerField(default=0)
    maximum_offline_age_minutes = models.PositiveIntegerField(null=True, blank=True)
    offline_requires_review = models.BooleanField(default=True)
    allow_flexible_checkpoint_order = models.BooleanField(default=False)
    require_all_mandatory_checkpoints = models.BooleanField(default=True)
    require_employee_on_active_duty_assignment = models.BooleanField(default=False)
    require_employee_attendance_checked_in = models.BooleanField(default=False)
    require_evidence_on_failed_checkpoint = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)


class PatrolCheckpoint(PatrolModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    site = models.ForeignKey(
        SecuritySite, on_delete=models.PROTECT, related_name="patrol_checkpoints"
    )
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    checkpoint_code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    checkpoint_type = models.CharField(max_length=30, choices=enums.CheckpointType.choices)
    location_description = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_meters = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.CheckpointStatus.choices, default="ACTIVE"
    )
    supports_qr = models.BooleanField(default=True)
    supports_nfc = models.BooleanField(default=False)
    requires_gps = models.BooleanField(default=False)
    is_sensitive_location = models.BooleanField(default=False)
    instructions = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["site", "checkpoint_code"], name="uniq_patrol_checkpoint_code"
            ),
            models.CheckConstraint(
                condition=Q(latitude__isnull=True) | Q(latitude__gte=-90, latitude__lte=90),
                name="patrol_checkpoint_latitude_range",
            ),
            models.CheckConstraint(
                condition=Q(longitude__isnull=True) | Q(longitude__gte=-180, longitude__lte=180),
                name="patrol_checkpoint_longitude_range",
            ),
        ]
        permissions = [
            ("manage_patrolcheckpoint", "Can manage patrol checkpoints"),
            ("manage_checkpoint_credentials", "Can manage checkpoint credentials"),
            ("view_sensitive_checkpoint_location", "Can view sensitive checkpoint locations"),
        ]

    def save(self, *args, **kwargs):
        self.checkpoint_code = self.checkpoint_code.strip().upper()
        super().save(*args, **kwargs)


class CheckpointQRCredential(UUIDModel):
    checkpoint = models.ForeignKey(
        PatrolCheckpoint, on_delete=models.PROTECT, related_name="qr_credentials"
    )
    credential_id = models.UUIDField(unique=True)
    token_hash = models.CharField(max_length=255)
    token_hint = models.CharField(max_length=12, blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.PROTECT)
    generated_at = models.DateTimeField()
    rotated_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CheckpointNFCCredential(UUIDModel):
    checkpoint = models.ForeignKey(
        PatrolCheckpoint, on_delete=models.PROTECT, related_name="nfc_credentials"
    )
    public_identifier = models.CharField(max_length=150, unique=True)
    credential_hash = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.CheckpointStatus.choices, default="ACTIVE"
    )
    generated_by = models.ForeignKey(User, on_delete=models.PROTECT)
    generated_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)


class PatrolRoute(PatrolModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT, related_name="patrol_routes")
    route_code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    order_mode = models.CharField(
        max_length=10, choices=enums.PatrolOrderMode.choices, default="STRICT"
    )
    expected_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.PatrolRouteStatus.choices, default="DRAFT"
    )
    current_version_number = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["site", "route_code"], name="uniq_patrol_route_code")
        ]
        permissions = [
            ("manage_patrolroute", "Can manage patrol routes"),
            ("manage_route_versions", "Can manage patrol route versions"),
        ]

    def save(self, *args, **kwargs):
        self.route_code = self.route_code.strip().upper()
        super().save(*args, **kwargs)


class PatrolRouteVersion(UUIDModel):
    patrol_route = models.ForeignKey(PatrolRoute, on_delete=models.PROTECT, related_name="versions")
    version_number = models.PositiveIntegerField()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    order_mode = models.CharField(max_length=10, choices=enums.PatrolOrderMode.choices)
    expected_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    is_current = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patrol_route", "version_number"], name="uniq_patrol_route_version"
            ),
            models.UniqueConstraint(
                fields=["patrol_route"],
                condition=Q(is_current=True),
                name="uniq_current_patrol_route_version",
            ),
        ]


class PatrolRouteCheckpoint(UUIDModel):
    route_version = models.ForeignKey(
        PatrolRouteVersion, on_delete=models.PROTECT, related_name="route_checkpoints"
    )
    checkpoint = models.ForeignKey(PatrolCheckpoint, on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    is_mandatory = models.BooleanField(default=True)
    expected_offset_minutes = models.PositiveIntegerField(null=True, blank=True)
    earliest_offset_minutes = models.PositiveIntegerField(null=True, blank=True)
    latest_offset_minutes = models.PositiveIntegerField(null=True, blank=True)
    minimum_dwell_seconds = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["route_version", "sequence"], name="uniq_patrol_route_checkpoint_sequence"
            ),
            models.CheckConstraint(
                condition=Q(sequence__gt=0), name="patrol_route_checkpoint_sequence_positive"
            ),
        ]


class PatrolRequirement(PatrolModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    patrol_route = models.ForeignKey(PatrolRoute, on_delete=models.PROTECT)
    requirement_code = models.CharField(max_length=50)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.PatrolRequirementStatus.choices, default="DRAFT"
    )
    start_time = models.TimeField()
    expected_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    frequency_per_day = models.PositiveIntegerField(default=1)
    assigned_employee_type = models.CharField(max_length=30, blank=True)
    assigned_designation = models.ForeignKey(
        Designation, null=True, blank=True, on_delete=models.PROTECT
    )
    priority = models.CharField(max_length=10, default="NORMAL")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "requirement_code"], name="uniq_patrol_requirement_code"
            ),
            models.CheckConstraint(
                condition=Q(frequency_per_day__gt=0), name="patrol_frequency_positive"
            ),
        ]
        permissions = [("manage_patrol_requirements", "Can manage patrol requirements")]


class PatrolRequirementDay(UUIDModel):
    patrol_requirement = models.ForeignKey(
        PatrolRequirement, on_delete=models.PROTECT, related_name="days"
    )
    weekday = models.CharField(max_length=10, choices=enums.Weekday.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patrol_requirement", "weekday"], name="uniq_patrol_requirement_weekday"
            )
        ]


class PatrolRequirementTime(UUIDModel):
    patrol_requirement = models.ForeignKey(
        PatrolRequirement, on_delete=models.PROTECT, related_name="times"
    )
    sequence = models.PositiveIntegerField()
    start_time = models.TimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patrol_requirement", "sequence"], name="uniq_patrol_requirement_time"
            )
        ]


class PatrolTask(PatrolModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT, related_name="patrol_tasks")
    patrol_requirement = models.ForeignKey(
        PatrolRequirement, null=True, blank=True, on_delete=models.PROTECT
    )
    patrol_route = models.ForeignKey(PatrolRoute, on_delete=models.PROTECT)
    route_version = models.ForeignKey(PatrolRouteVersion, on_delete=models.PROTECT)
    task_number = models.CharField(max_length=50, unique=True)
    scheduled_start_at = models.DateTimeField()
    scheduled_end_at = models.DateTimeField(null=True, blank=True)
    assigned_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT, related_name="patrol_tasks"
    )
    duty_assignment = models.ForeignKey(
        DutyAssignment, null=True, blank=True, on_delete=models.PROTECT
    )
    supervisor = models.ForeignKey(
        Employee,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="supervised_patrol_tasks",
    )
    priority = models.CharField(max_length=10, default="NORMAL")
    status = models.CharField(
        max_length=20, choices=enums.PatrolTaskStatus.choices, default="SCHEDULED"
    )
    is_adhoc = models.BooleanField(default=False)
    adhoc_reason = models.TextField(blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    generated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patrol_requirement", "scheduled_start_at"],
                condition=Q(patrol_requirement__isnull=False),
                name="uniq_generated_patrol_task",
            )
        ]
        permissions = [
            ("assign_patroltask", "Can assign patrol tasks"),
            ("cancel_patroltask", "Can cancel patrol tasks"),
            ("perform_own_patrol", "Can perform own assigned patrol"),
        ]


class PatrolRun(PatrolModel):
    patrol_task = models.OneToOneField(
        PatrolTask, on_delete=models.PROTECT, related_name="patrol_run"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="patrol_runs")
    duty_assignment = models.ForeignKey(
        DutyAssignment, null=True, blank=True, on_delete=models.PROTECT
    )
    route_version = models.ForeignKey(PatrolRouteVersion, on_delete=models.PROTECT)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.PatrolRunStatus.choices, default="IN_PROGRESS"
    )
    start_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    start_accuracy_meters = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    start_distance_from_site_meters = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    end_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    end_accuracy_meters = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    mandatory_checkpoint_count = models.PositiveIntegerField(default=0)
    verified_mandatory_count = models.PositiveIntegerField(default=0)
    total_checkpoint_count = models.PositiveIntegerField(default=0)
    visited_checkpoint_count = models.PositiveIntegerField(default=0)
    completion_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    started_offline = models.BooleanField(default=False)
    completed_offline = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        permissions = [
            ("view_sensitive_patrol_location", "Can view exact patrol event coordinates"),
            ("review_patrolrun", "Can review patrol runs"),
            ("view_patrol_dashboard", "Can view patrol dashboard"),
            ("view_patrol_reports", "Can view patrol reports"),
            ("view_patrol_audit", "Can view patrol audit"),
        ]


class PatrolEvent(UUIDModel):
    patrol_run = models.ForeignKey(PatrolRun, on_delete=models.PROTECT, related_name="events")
    event_type = models.CharField(max_length=30, choices=enums.PatrolEventType.choices)
    actor_user = models.ForeignKey(User, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT)
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    client_event_id = models.UUIDField(null=True, blank=True)
    is_offline_submission = models.BooleanField(default=False)
    device_platform = models.CharField(max_length=50, blank=True)
    app_version = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["client_event_id"],
                condition=Q(client_event_id__isnull=False),
                name="uniq_patrol_client_event",
            )
        ]


class CheckpointVisit(UUIDModel):
    patrol_run = models.ForeignKey(
        PatrolRun, on_delete=models.PROTECT, related_name="checkpoint_visits"
    )
    patrol_event = models.OneToOneField(PatrolEvent, on_delete=models.PROTECT)
    route_checkpoint = models.ForeignKey(PatrolRouteCheckpoint, on_delete=models.PROTECT)
    checkpoint = models.ForeignKey(PatrolCheckpoint, on_delete=models.PROTECT)
    sequence_observed = models.PositiveIntegerField()
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=enums.CheckpointVisitStatus.choices)
    gps_result = models.CharField(max_length=20, choices=enums.CheckpointVerificationResult.choices)
    token_result = models.CharField(
        max_length=20, choices=enums.CheckpointVerificationResult.choices
    )
    overall_verification_result = models.CharField(
        max_length=20, choices=enums.CheckpointVerificationResult.choices
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_meters = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    distance_meters = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    allowed_radius_meters = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    verification_method = models.CharField(
        max_length=20, choices=enums.CheckpointVerificationMethod.choices
    )
    qr_credential = models.ForeignKey(
        CheckpointQRCredential, null=True, blank=True, on_delete=models.PROTECT
    )
    nfc_credential = models.ForeignKey(
        CheckpointNFCCredential, null=True, blank=True, on_delete=models.PROTECT
    )
    expected_at = models.DateTimeField(null=True, blank=True)
    early_minutes = models.PositiveIntegerField(default=0)
    late_minutes = models.PositiveIntegerField(default=0)
    is_offline_submission = models.BooleanField(default=False)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PatrolObservation(PatrolModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    patrol_run = models.ForeignKey(PatrolRun, on_delete=models.PROTECT, related_name="observations")
    checkpoint_visit = models.ForeignKey(
        CheckpointVisit, null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    checkpoint = models.ForeignKey(
        PatrolCheckpoint, null=True, blank=True, on_delete=models.PROTECT
    )
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    category = models.CharField(max_length=30, choices=enums.PatrolObservationCategory.choices)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=enums.PatrolObservationSeverity.choices)
    requires_follow_up = models.BooleanField(default=False)
    requires_incident_escalation = models.BooleanField(default=False)
    observed_at = models.DateTimeField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)


class PatrolEvidence(UUIDModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    patrol_run = models.ForeignKey(PatrolRun, on_delete=models.PROTECT, related_name="evidence")
    checkpoint_visit = models.ForeignKey(
        CheckpointVisit, null=True, blank=True, on_delete=models.PROTECT
    )
    observation = models.ForeignKey(
        PatrolObservation, null=True, blank=True, on_delete=models.PROTECT
    )
    file = models.FileField(storage=private_patrol_storage, upload_to=patrol_evidence_upload_to)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField()
    mime_type = models.CharField(max_length=100)
    sha256_hash = models.CharField(max_length=64)
    caption = models.TextField(blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        permissions = [("download_patrol_evidence", "Can securely download patrol evidence")]


class PatrolException(PatrolModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    patrol_task = models.ForeignKey(PatrolTask, on_delete=models.PROTECT, related_name="exceptions")
    patrol_run = models.ForeignKey(
        PatrolRun, null=True, blank=True, on_delete=models.PROTECT, related_name="exceptions"
    )
    checkpoint_visit = models.ForeignKey(
        CheckpointVisit, null=True, blank=True, on_delete=models.PROTECT
    )
    exception_type = models.CharField(max_length=40, choices=enums.PatrolExceptionType.choices)
    severity = models.CharField(max_length=10, choices=enums.PatrolObservationSeverity.choices)
    status = models.CharField(
        max_length=20, choices=enums.PatrolExceptionStatus.choices, default="OPEN"
    )
    detected_at = models.DateTimeField()
    message = models.TextField()
    acknowledged_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acknowledged_patrol_exceptions",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resolved_patrol_exceptions",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["patrol_task", "exception_type", "checkpoint_visit"],
                condition=Q(status__in=["OPEN", "ACKNOWLEDGED"]),
                name="uniq_open_patrol_exception",
            )
        ]
        permissions = [
            ("view_patrol_exceptions", "Can view patrol exceptions"),
            ("resolve_patrol_exception", "Can resolve patrol exceptions"),
        ]


class PatrolReview(UUIDModel):
    patrol_run = models.OneToOneField(PatrolRun, on_delete=models.PROTECT, related_name="review")
    reviewed_by = models.ForeignKey(User, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField()
    review_result = models.CharField(max_length=40, choices=enums.PatrolReviewResult.choices)
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
