# mypy: disable-error-code="no-untyped-def"
# ruff: noqa: E501
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import TimeStampedModel, UUIDModel

from . import enums
from .storage import incident_evidence_upload_to, private_incident_storage

PROTECT = models.PROTECT


class IncidentModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class IncidentType(IncidentModel):
    company = models.ForeignKey("organization.Company", null=True, blank=True, on_delete=PROTECT)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    default_severity = models.CharField(
        max_length=10, choices=enums.IncidentSeverity.choices, default="MEDIUM"
    )
    default_priority = models.CharField(
        max_length=10, choices=enums.IncidentPriority.choices, default="NORMAL"
    )
    requires_immediate_acknowledgement = models.BooleanField(default=False)
    requires_client_notification = models.BooleanField(default=False)
    requires_management_notification = models.BooleanField(default=False)
    requires_post_incident_review = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="uniq_incident_type_company_code"
            )
        ]
        permissions = [("manage_incident_types", "Can manage incident types")]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Incident types cannot be deleted; deactivate them instead.")


class Incident(IncidentModel):
    incident_number = models.CharField(max_length=30, unique=True, db_index=True)
    company = models.ForeignKey("organization.Company", on_delete=PROTECT)
    client = models.ForeignKey("contracts.Client", null=True, blank=True, on_delete=PROTECT)
    contract = models.ForeignKey(
        "contracts.ServiceContract", null=True, blank=True, on_delete=PROTECT
    )
    site = models.ForeignKey("contracts.SecuritySite", null=True, blank=True, on_delete=PROTECT)
    post = models.ForeignKey("contracts.SecurityPost", null=True, blank=True, on_delete=PROTECT)
    branch = models.ForeignKey("organization.Branch", on_delete=PROTECT)
    operational_zone = models.ForeignKey(
        "organization.OperationalZone", null=True, blank=True, on_delete=PROTECT
    )
    incident_type = models.ForeignKey(IncidentType, on_delete=PROTECT)
    severity = models.CharField(max_length=10, choices=enums.IncidentSeverity.choices)
    priority = models.CharField(max_length=10, choices=enums.IncidentPriority.choices)
    status = models.CharField(
        max_length=30, choices=enums.IncidentStatus.choices, default="NEW", db_index=True
    )
    verification_status = models.CharField(
        max_length=30, choices=enums.IncidentVerificationStatus.choices, default="UNVERIFIED"
    )
    source = models.CharField(max_length=30, choices=enums.IncidentSource.choices)
    reporter_employee = models.ForeignKey(
        "workforce.Employee",
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="reported_incidents",
    )
    reporter_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="reported_incidents",
    )
    reported_by_name = models.CharField(max_length=150, blank=True)
    reported_at = models.DateTimeField(db_index=True)
    duty_assignment = models.ForeignKey(
        "deployment.DutyAssignment", null=True, blank=True, on_delete=PROTECT
    )
    attendance_record = models.ForeignKey(
        "attendance.AttendanceRecord", null=True, blank=True, on_delete=PROTECT
    )
    employee_deployment = models.ForeignKey(
        "deployment.EmployeeDeployment", null=True, blank=True, on_delete=PROTECT
    )
    site_visit = models.ForeignKey(
        "supervision.SiteVisit", null=True, blank=True, on_delete=PROTECT
    )
    inspection = models.ForeignKey(
        "supervision.SiteInspection", null=True, blank=True, on_delete=PROTECT
    )
    patrol_task = models.ForeignKey("patrol.PatrolTask", null=True, blank=True, on_delete=PROTECT)
    patrol_run = models.ForeignKey("patrol.PatrolRun", null=True, blank=True, on_delete=PROTECT)
    checkpoint_visit = models.ForeignKey(
        "patrol.CheckpointVisit", null=True, blank=True, on_delete=PROTECT
    )
    patrol_observation = models.ForeignKey(
        "patrol.PatrolObservation", null=True, blank=True, on_delete=PROTECT
    )
    supervision_finding = models.ForeignKey(
        "supervision.InspectionFinding",
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="referred_incidents",
    )
    patrol_exception = models.ForeignKey(
        "patrol.PatrolException",
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="referred_incidents",
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    occurred_at = models.DateTimeField(null=True, blank=True)
    discovered_at = models.DateTimeField(null=True, blank=True)
    command_center_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="command_center_incidents",
    )
    operations_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="operations_incidents",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True, db_index=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="acknowledged_incidents",
    )
    triaged_at = models.DateTimeField(null=True, blank=True)
    responding_at = models.DateTimeField(null=True, blank=True)
    contained_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    resolution_summary = models.TextField(blank=True)
    closure_summary = models.TextField(blank=True)
    client_notification_required = models.BooleanField(default=False)
    management_notification_required = models.BooleanField(default=False)
    post_incident_review_required = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="created_incidents"
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "status", "severity"]),
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["site", "reported_at"]),
            models.Index(fields=["incident_type", "source"]),
        ]
        permissions = [
            (p, p.replace("_", " ").title())
            for p in [
                "view_incident_dashboard",
                "report_incident",
                "manage_incident",
                "trigger_own_sos",
                "view_own_sos",
                "acknowledge_incident",
                "triage_incident",
                "assign_incident_owner",
                "manage_incident_response",
                "contain_incident",
                "resolve_incident",
                "close_incident",
                "reopen_incident",
                "manage_responders",
                "manage_incident_actions",
                "escalate_incident",
                "record_external_contact",
                "record_client_notification",
                "record_management_notification",
                "manage_escalation_policies",
                "upload_incident_evidence",
                "download_incident_evidence",
                "view_sensitive_incident_location",
                "view_sensitive_incident_participants",
                "manage_post_incident_review",
                "view_incident_reports",
                "view_incident_audit",
            ]
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["supervision_finding"],
                condition=Q(supervision_finding__isnull=False),
                name="uniq_incident_supervision_finding",
            ),
            models.UniqueConstraint(
                fields=["patrol_exception"],
                condition=Q(patrol_exception__isnull=False),
                name="uniq_incident_patrol_exception",
            ),
            models.UniqueConstraint(
                fields=["patrol_observation"],
                condition=Q(patrol_observation__isnull=False),
                name="uniq_incident_patrol_observation",
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError("Incidents cannot be deleted.")


class SOSAlert(UUIDModel):
    sos_number = models.CharField(max_length=30, unique=True)
    company = models.ForeignKey("organization.Company", on_delete=PROTECT)
    employee = models.ForeignKey("workforce.Employee", on_delete=PROTECT)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT)
    duty_assignment = models.ForeignKey(
        "deployment.DutyAssignment", null=True, blank=True, on_delete=PROTECT
    )
    attendance_record = models.ForeignKey(
        "attendance.AttendanceRecord", null=True, blank=True, on_delete=PROTECT
    )
    site = models.ForeignKey("contracts.SecuritySite", null=True, blank=True, on_delete=PROTECT)
    post = models.ForeignKey("contracts.SecurityPost", null=True, blank=True, on_delete=PROTECT)
    patrol_run = models.ForeignKey("patrol.PatrolRun", null=True, blank=True, on_delete=PROTECT)
    activation_method = models.CharField(
        max_length=20, choices=enums.SOSActivationMethod.choices, default="MOBILE_APP"
    )
    status = models.CharField(
        max_length=30, choices=enums.SOSStatus.choices, default="TRIGGERED", db_index=True
    )
    triggered_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    client_event_id = models.UUIDField(null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    accuracy_meters = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    message = models.TextField(blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="acknowledged_sos",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    linked_incident = models.ForeignKey(
        Incident, null=True, blank=True, on_delete=PROTECT, related_name="sos_alerts"
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    false_alarm_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="confirmed_false_sos",
    )
    false_alarm_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "client_event_id"],
                condition=Q(client_event_id__isnull=False),
                name="uniq_sos_company_client_event",
            )
        ]
        indexes = [models.Index(fields=["company", "status", "triggered_at"])]

    def delete(self, *args, **kwargs):
        raise ValidationError("SOS evidence cannot be deleted.")


class IncidentEvent(UUIDModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="events")
    event_type = models.CharField(max_length=30, choices=enums.IncidentEventType.choices)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT
    )
    actor_employee = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=PROTECT
    )
    event_time = models.DateTimeField()
    server_recorded_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    previous_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)
    metadata_reference = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["event_time", "server_recorded_at"]
        indexes = [models.Index(fields=["incident", "event_time"])]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Incident events are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Incident events are immutable.")


class IncidentLocationSnapshot(UUIDModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="location_snapshots")
    source = models.CharField(max_length=20, choices=enums.LocationSource.choices)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    accuracy_meters = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    employee = models.ForeignKey("workforce.Employee", null=True, blank=True, on_delete=PROTECT)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(latitude__gte=-90, latitude__lte=90), name="incident_location_lat_range"
            ),
            models.CheckConstraint(
                condition=Q(longitude__gte=-180, longitude__lte=180),
                name="incident_location_lon_range",
            ),
        ]


class IncidentParticipant(IncidentModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="participants")
    involvement_type = models.CharField(max_length=30, choices=enums.PersonInvolvementType.choices)
    employee = models.ForeignKey("workforce.Employee", null=True, blank=True, on_delete=PROTECT)
    client_contact = models.ForeignKey(
        "contracts.ClientContact", null=True, blank=True, on_delete=PROTECT
    )
    external_name = models.CharField(max_length=150, blank=True)
    external_contact = models.CharField(max_length=150, blank=True)
    role_description = models.TextField(blank=True)
    statement_summary = models.TextField(blank=True)
    injury_severity = models.CharField(
        max_length=30, choices=enums.InjurySeverity.choices, blank=True
    )


class IncidentEvidence(UUIDModel):
    company = models.ForeignKey("organization.Company", on_delete=PROTECT)
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="evidence")
    evidence_type = models.CharField(max_length=30, choices=enums.EvidenceType.choices)
    file = models.FileField(
        storage=private_incident_storage,
        upload_to=incident_evidence_upload_to,
        null=True,
        blank=True,
    )
    external_reference = models.CharField(max_length=500, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, blank=True)
    sha256_hash = models.CharField(max_length=64, blank=True)
    captured_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        raise ValidationError("Incident evidence cannot be deleted.")


class IncidentEvidenceEvent(UUIDModel):
    evidence = models.ForeignKey(
        IncidentEvidence, on_delete=PROTECT, related_name="handling_events"
    )
    event_type = models.CharField(max_length=20)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
    timestamp = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        raise ValidationError("Evidence handling history is immutable.")


class IncidentResponder(IncidentModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="responders")
    employee = models.ForeignKey("workforce.Employee", null=True, blank=True, on_delete=PROTECT)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="incident_responses",
    )
    responder_role = models.CharField(max_length=30, choices=enums.ResponderRole.choices)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="assigned_incident_responders"
    )
    assigned_at = models.DateTimeField()
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.ResponderStatus.choices, default="ASSIGNED"
    )
    en_route_at = models.DateTimeField(null=True, blank=True)
    on_scene_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)


class IncidentAction(IncidentModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="actions")
    action_number = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(
        max_length=10, choices=enums.IncidentActionPriority.choices, default="NORMAL"
    )
    status = models.CharField(
        max_length=20, choices=enums.IncidentActionStatus.choices, default="OPEN", db_index=True
    )
    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="incident_actions",
    )
    assigned_to_employee = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=PROTECT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="created_incident_actions"
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "action_number"], name="uniq_incident_action_number"
            )
        ]


class IncidentEscalationPolicy(IncidentModel):
    company = models.ForeignKey("organization.Company", on_delete=PROTECT)
    incident_type = models.ForeignKey(IncidentType, null=True, blank=True, on_delete=PROTECT)
    severity = models.CharField(max_length=10, choices=enums.IncidentSeverity.choices, blank=True)
    site = models.ForeignKey("contracts.SecuritySite", null=True, blank=True, on_delete=PROTECT)
    name = models.CharField(max_length=150)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    acknowledgement_target_minutes = models.PositiveIntegerField(null=True, blank=True)
    response_start_target_minutes = models.PositiveIntegerField(null=True, blank=True)
    management_escalation_after_minutes = models.PositiveIntegerField(null=True, blank=True)
    unresolved_escalation_after_minutes = models.PositiveIntegerField(null=True, blank=True)
    notify_client = models.BooleanField(default=False)
    notify_branch_operations = models.BooleanField(default=False)
    notify_company_operations = models.BooleanField(default=False)
    notify_management = models.BooleanField(default=False)
    require_post_incident_review = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)


class IncidentEscalation(UUIDModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="escalations")
    policy = models.ForeignKey(IncidentEscalationPolicy, null=True, blank=True, on_delete=PROTECT)
    escalation_type = models.CharField(max_length=50)
    triggered_at = models.DateTimeField()
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT)
    details = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "escalation_type"], name="uniq_incident_escalation_type"
            )
        ]


class ExternalContactAttempt(UUIDModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="contact_attempts")
    contact_name = models.CharField(max_length=150)
    organization = models.CharField(max_length=150, blank=True)
    method = models.CharField(max_length=20, choices=enums.ContactAttemptMethod.choices)
    result = models.CharField(max_length=20, choices=enums.ContactAttemptResult.choices)
    attempted_at = models.DateTimeField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ClientNotificationRecord(UUIDModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="client_notifications")
    client_contact = models.ForeignKey(
        "contracts.ClientContact", null=True, blank=True, on_delete=PROTECT
    )
    notified_name = models.CharField(max_length=150, blank=True)
    method = models.CharField(max_length=20, choices=enums.ContactAttemptMethod.choices)
    result = models.CharField(max_length=20, choices=enums.ContactAttemptResult.choices)
    notified_at = models.DateTimeField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=PROTECT)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ManagementNotificationRecord(UUIDModel):
    incident = models.ForeignKey(
        Incident, on_delete=PROTECT, related_name="management_notifications"
    )
    notified_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT
    )
    notified_name = models.CharField(max_length=150, blank=True)
    method = models.CharField(max_length=20, choices=enums.ContactAttemptMethod.choices)
    result = models.CharField(max_length=20, choices=enums.ContactAttemptResult.choices)
    notified_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=PROTECT,
        related_name="recorded_management_notifications",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class IncidentImpact(IncidentModel):
    incident = models.OneToOneField(Incident, on_delete=PROTECT, related_name="impact")
    injury_count = models.PositiveIntegerField(default=0)
    highest_injury_severity = models.CharField(
        max_length=30, choices=enums.InjurySeverity.choices, default="NONE"
    )
    damage_type = models.CharField(max_length=20, choices=enums.DamageType.choices, default="NONE")
    estimated_damage_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )
    operational_disruption = models.BooleanField(default=False)
    notes = models.TextField(blank=True)


class PostIncidentReview(IncidentModel):
    incident = models.OneToOneField(Incident, on_delete=PROTECT, related_name="review")
    status = models.CharField(max_length=20, default="DRAFT")
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name="started_incident_reviews"
    )
    started_at = models.DateTimeField()
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=PROTECT,
        related_name="completed_incident_reviews",
    )
    completed_at = models.DateTimeField(null=True, blank=True)
    summary = models.TextField(blank=True)
    root_cause_classification = models.CharField(max_length=100, blank=True)
    lessons_learned = models.TextField(blank=True)


class ReviewRecommendation(IncidentModel):
    review = models.ForeignKey(
        PostIncidentReview, on_delete=PROTECT, related_name="recommendations"
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(
        max_length=10, choices=enums.IncidentActionPriority.choices, default="NORMAL"
    )
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=PROTECT)
    due_at = models.DateTimeField(null=True, blank=True)


class IncidentException(UUIDModel):
    incident = models.ForeignKey(Incident, on_delete=PROTECT, related_name="exceptions")
    exception_type = models.CharField(max_length=50)
    detected_at = models.DateTimeField()
    resolved_at = models.DateTimeField(null=True, blank=True)
    details = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "exception_type"],
                condition=Q(resolved_at__isnull=True),
                name="uniq_open_incident_exception",
            )
        ]
