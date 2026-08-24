from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.contracts.models import Client, SecurityPost, SecuritySite
from dsms.deployment.models import DutyAssignment
from dsms.identity.models import User
from dsms.organization.models import Branch, Company
from dsms.workforce.models import Employee

from .enums import (
    AttendanceEventType,
    AttendanceOutcome,
    AttendancePeriodStatus,
    AttendanceRecordStatus,
    CorrectionStatus,
    ExceptionStatus,
    QRStationStatus,
    VerificationMethod,
    VerificationResult,
)


class AttendanceModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class AttendancePolicy(AttendanceModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, null=True, blank=True, on_delete=models.PROTECT)
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    early_check_in_window_minutes = models.PositiveIntegerField(default=0)
    late_grace_minutes = models.PositiveIntegerField(default=0)
    early_departure_grace_minutes = models.PositiveIntegerField(default=0)
    late_check_out_window_minutes = models.PositiveIntegerField(default=0)
    missing_check_in_review_after_minutes = models.PositiveIntegerField(null=True, blank=True)
    require_gps = models.BooleanField(default=False)
    require_qr = models.BooleanField(default=False)
    require_face = models.BooleanField(default=False)
    allow_supervisor_verification = models.BooleanField(default=True)
    allow_manual_correction = models.BooleanField(default=True)
    allow_offline_submission = models.BooleanField(default=False)
    maximum_gps_accuracy_meters = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    additional_geofence_tolerance_meters = models.PositiveIntegerField(default=0)
    maximum_offline_age_minutes = models.PositiveIntegerField(null=True, blank=True)
    offline_requires_review = models.BooleanField(default=True)
    rounding_increment_minutes = models.PositiveIntegerField(null=True, blank=True)
    rounding_mode = models.CharField(max_length=20, blank=True)
    overtime_requires_approval = models.BooleanField(default=True)
    breaks_enabled = models.BooleanField(default=False)


class AttendanceQRStation(AttendanceModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    station_code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    status = models.CharField(
        max_length=20, choices=QRStationStatus.choices, default=QRStationStatus.ACTIVE
    )
    token_hash = models.CharField(max_length=255)
    token_hint = models.CharField(max_length=12, blank=True)
    generated_by = models.ForeignKey(User, on_delete=models.PROTECT)
    generated_at = models.DateTimeField()
    rotated_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)


class AttendancePeriod(AttendanceModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    period_start = models.DateField()
    period_end = models.DateField()
    name = models.CharField(max_length=150)
    status = models.CharField(
        max_length=20, choices=AttendancePeriodStatus.choices, default=AttendancePeriodStatus.OPEN
    )
    submitted_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="submitted_attendance_periods",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_attendance_periods",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="locked_attendance_periods",
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="closed_attendance_periods",
    )
    closed_at = models.DateTimeField(null=True, blank=True)


class AttendanceRecord(AttendanceModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    site = models.ForeignKey(
        SecuritySite, on_delete=models.PROTECT, related_name="attendance_records"
    )
    post = models.ForeignKey(SecurityPost, on_delete=models.PROTECT)
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="attendance_records"
    )
    duty_assignment = models.OneToOneField(
        DutyAssignment, on_delete=models.PROTECT, related_name="attendance_record"
    )
    attendance_period = models.ForeignKey(
        AttendancePeriod, null=True, blank=True, on_delete=models.PROTECT, related_name="records"
    )
    scheduled_start_at = models.DateTimeField()
    scheduled_end_at = models.DateTimeField()
    actual_check_in_at = models.DateTimeField(null=True, blank=True)
    actual_check_out_at = models.DateTimeField(null=True, blank=True)
    approved_check_in_at = models.DateTimeField(null=True, blank=True)
    approved_check_out_at = models.DateTimeField(null=True, blank=True)
    late_minutes = models.PositiveIntegerField(default=0)
    early_departure_minutes = models.PositiveIntegerField(default=0)
    actual_worked_minutes = models.PositiveIntegerField(null=True, blank=True)
    approved_worked_minutes = models.PositiveIntegerField(null=True, blank=True)
    approved_overtime_minutes = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=AttendanceRecordStatus.choices,
        default=AttendanceRecordStatus.PENDING,
    )
    outcome = models.CharField(max_length=30, choices=AttendanceOutcome.choices, blank=True)
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_attendance_records",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_attendance_records",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["site", "scheduled_start_at"]),
        ]
        permissions = [
            ("view_own_attendance", "Can view own attendance"),
            ("perform_own_checkin", "Can perform own check-in"),
            ("perform_own_checkout", "Can perform own check-out"),
            ("view_sensitive_location_data", "Can view exact attendance locations"),
            ("view_biometric_verification_details", "Can view biometric verification metadata"),
        ]


class AttendanceEvent(UUIDModel):
    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(max_length=30, choices=AttendanceEventType.choices)
    subject_employee = models.ForeignKey(Employee, on_delete=models.PROTECT)
    actor_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
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
                name="uniq_attendance_client_event",
            )
        ]
        indexes = [
            models.Index(fields=["event_type", "observed_at"]),
            models.Index(fields=["received_at"]),
        ]


class AttendanceVerification(UUIDModel):
    attendance_event = models.ForeignKey(
        AttendanceEvent, on_delete=models.PROTECT, related_name="verifications"
    )
    method = models.CharField(max_length=20, choices=VerificationMethod.choices)
    result = models.CharField(max_length=20, choices=VerificationResult.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_meters = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    distance_from_site_meters = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    geofence_radius_meters = models.PositiveIntegerField(null=True, blank=True)
    qr_station = models.ForeignKey(
        AttendanceQRStation, null=True, blank=True, on_delete=models.PROTECT
    )
    provider_reference = models.CharField(max_length=150, blank=True)
    face_match_result = models.CharField(max_length=20, blank=True)
    liveness_result = models.CharField(max_length=20, blank=True)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    verified_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    failure_code = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AttendanceException(AttendanceModel):
    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="exceptions"
    )
    attendance_event = models.ForeignKey(
        AttendanceEvent, null=True, blank=True, on_delete=models.PROTECT
    )
    exception_type = models.CharField(max_length=50)
    severity = models.CharField(max_length=10)
    status = models.CharField(
        max_length=20, choices=ExceptionStatus.choices, default=ExceptionStatus.OPEN
    )
    detected_at = models.DateTimeField()
    message = models.TextField()
    acknowledged_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="acknowledged_attendance_exceptions",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="resolved_attendance_exceptions",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attendance_record", "exception_type"],
                condition=Q(status=ExceptionStatus.OPEN),
                name="uniq_open_attendance_exception",
            )
        ]


class AttendanceCorrectionRequest(AttendanceModel):
    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="corrections"
    )
    requested_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="requested_attendance_corrections"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()
    proposed_check_in_at = models.DateTimeField(null=True, blank=True)
    proposed_check_out_at = models.DateTimeField(null=True, blank=True)
    proposed_outcome = models.CharField(
        max_length=30, choices=AttendanceOutcome.choices, blank=True
    )
    proposed_approved_worked_minutes = models.PositiveIntegerField(null=True, blank=True)
    proposed_overtime_minutes = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=CorrectionStatus.choices, default=CorrectionStatus.DRAFT
    )
    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_attendance_corrections",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(blank=True)


class AttendanceChangeEvent(UUIDModel):
    attendance_record = models.ForeignKey(
        AttendanceRecord,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="change_events",
    )
    attendance_period = models.ForeignKey(
        AttendancePeriod,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="change_events",
    )
    event_type = models.CharField(max_length=40)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class AttendancePayrollExport(UUIDModel):
    attendance_period = models.ForeignKey(
        AttendancePeriod, on_delete=models.PROTECT, related_name="payroll_exports"
    )
    payroll_period = models.ForeignKey(
        "finance.PayrollPeriod", on_delete=models.PROTECT, related_name="attendance_exports"
    )
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="attendance_payroll_exports"
    )
    source_version = models.PositiveIntegerField(default=1)
    quantities = models.JSONField(default=dict)
    exported_by = models.ForeignKey(User, on_delete=models.PROTECT)
    exported_at = models.DateTimeField(auto_now_add=True)
    adjustment_required = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attendance_period", "payroll_period", "employee", "source_version"],
                name="uniq_attendance_payroll_export_version",
            )
        ]
