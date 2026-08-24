# mypy: disable-error-code="no-untyped-def"
# ruff: noqa: E501
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from dsms.common.models import TimeStampedModel, UUIDModel

from . import enums
from .storage import portal_attachment_upload_to, private_portal_storage

P = models.PROTECT


class PortalModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class ClientPortalRole(PortalModel):
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    permissions = models.ManyToManyField(Permission, blank=True)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class ClientPortalMembership(PortalModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="client_portal_memberships"
    )
    client = models.ForeignKey("contracts.Client", on_delete=P, related_name="portal_memberships")
    role = models.ForeignKey(ClientPortalRole, on_delete=P)
    client_contact = models.ForeignKey(
        "contracts.ClientContact", null=True, blank=True, on_delete=P
    )
    status = models.CharField(
        max_length=20, choices=enums.MembershipStatus.choices, default="INVITED"
    )
    access_mode = models.CharField(
        max_length=20,
        choices=[("ALL_CLIENT_SITES", "All client sites"), ("SELECTED_SITES", "Selected sites")],
        default="ALL_CLIENT_SITES",
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="portal_memberships_invited",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)
    last_portal_access_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "client"], name="uniq_portal_user_client")
        ]
        permissions = [
            (code, code.replace("_", " ").title())
            for code in [
                "view_dashboard",
                "view_contracts",
                "view_sites",
                "view_staffing_summary",
                "view_attendance_summary",
                "view_guard_identity",
                "view_patrol_summary",
                "view_supervision_summary",
                "view_incident_summary",
                "view_incident_detail",
                "view_sla_performance",
                "view_service_reports",
                "acknowledge_service_report",
                "create_service_request",
                "view_service_request",
                "comment_service_request",
                "submit_feedback",
                "download_shared_attachment",
                "manage_client_users",
                "view_portal_audit",
                "view_client_invoices",
                "download_client_invoice",
                "view_client_receipts",
                "view_client_statement",
            ]
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError("Portal memberships must be revoked, not deleted.")


class ClientPortalSiteAccess(PortalModel):
    membership = models.ForeignKey(ClientPortalMembership, on_delete=P, related_name="site_access")
    site = models.ForeignKey("contracts.SecuritySite", on_delete=P)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "site"], name="uniq_portal_membership_site"
            )
        ]


class ClientPortalContractAccess(UUIDModel):
    membership = models.ForeignKey(
        ClientPortalMembership, on_delete=P, related_name="contract_access"
    )
    contract = models.ForeignKey("contracts.ServiceContract", on_delete=P)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "contract"], name="uniq_portal_membership_contract"
            )
        ]


class ClientPortalInvitation(UUIDModel):
    client = models.ForeignKey("contracts.Client", on_delete=P)
    email = models.EmailField()
    role = models.ForeignKey(ClientPortalRole, on_delete=P)
    client_contact = models.ForeignKey(
        "contracts.ClientContact", null=True, blank=True, on_delete=P
    )
    invitation_token_hash = models.CharField(max_length=64)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    invited_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=enums.InvitationStatus.choices, default="PENDING"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class ClientDataSharingPolicy(PortalModel):
    client = models.OneToOneField(
        "contracts.Client", on_delete=P, related_name="portal_sharing_policy"
    )
    show_guard_names = models.BooleanField(default=False)
    show_employee_numbers = models.BooleanField(default=False)
    show_guard_designations = models.BooleanField(default=False)
    show_roster_details = models.BooleanField(default=False)
    show_exact_attendance_times = models.BooleanField(default=False)
    show_late_attendance_details = models.BooleanField(default=False)
    show_patrol_checkpoint_details = models.BooleanField(default=False)
    show_supervisor_names = models.BooleanField(default=False)
    show_incident_participants = models.BooleanField(default=False)
    show_incident_evidence = models.BooleanField(default=False)
    show_incident_exact_location = models.BooleanField(default=False)
    show_internal_incident_timeline = models.BooleanField(default=False)
    show_internal_findings = models.BooleanField(default=False)
    show_sla_details = models.BooleanField(default=False)
    allow_service_requests = models.BooleanField(default=False)
    allow_feedback = models.BooleanField(default=False)


class IncidentClientVisibility(PortalModel):
    incident = models.OneToOneField(
        "incidents.Incident", on_delete=P, related_name="client_visibility"
    )
    visibility_status = models.CharField(
        max_length=20, choices=enums.VisibilityStatus.choices, default="INTERNAL_ONLY"
    )
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    approved_at = models.DateTimeField(null=True, blank=True)
    client_summary = models.TextField(blank=True)
    client_resolution_summary = models.TextField(blank=True)
    allow_evidence = models.BooleanField(default=False)


class ClientIncidentAcknowledgement(UUIDModel):
    incident = models.ForeignKey("incidents.Incident", on_delete=P)
    membership = models.ForeignKey(ClientPortalMembership, on_delete=P)
    acknowledged_at = models.DateTimeField()
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["incident", "membership"], name="uniq_client_incident_ack"
            )
        ]


class SLAMeasurementPeriod(PortalModel):
    company = models.ForeignKey("organization.Company", on_delete=P)
    client = models.ForeignKey("contracts.Client", on_delete=P)
    contract = models.ForeignKey("contracts.ServiceContract", on_delete=P)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=enums.PeriodStatus.choices, default="DRAFT")
    calculated_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    approved_at = models.DateTimeField(null=True, blank=True)


class SLAMeasurement(UUIDModel):
    measurement_period = models.ForeignKey(
        SLAMeasurementPeriod, on_delete=P, related_name="measurements"
    )
    sla = models.ForeignKey("contracts.ServiceLevelAgreement", on_delete=P)
    site = models.ForeignKey("contracts.SecuritySite", null=True, blank=True, on_delete=P)
    measured_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_value = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    target_unit = models.CharField(max_length=30)
    result = models.CharField(max_length=30, choices=enums.SLAResult.choices)
    numerator = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    denominator = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)
    measurement_source = models.CharField(max_length=100)
    calculated_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["measurement_period", "sla", "site"], name="uniq_sla_period_sla_site"
            )
        ]


class ClientServiceReport(PortalModel):
    company = models.ForeignKey("organization.Company", on_delete=P)
    client = models.ForeignKey("contracts.Client", on_delete=P)
    contract = models.ForeignKey("contracts.ServiceContract", null=True, blank=True, on_delete=P)
    report_number = models.CharField(max_length=40, unique=True)
    report_type = models.CharField(max_length=20)
    period_start = models.DateField()
    period_end = models.DateField()
    title = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=enums.ReportStatus.choices, default="DRAFT")
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="generated_client_reports"
    )
    generated_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="reviewed_client_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="approved_client_reports",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="published_client_reports",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    withdrawn_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="withdrawn_client_reports",
    )
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    withdrawal_reason = models.TextField(blank=True)
    executive_summary = models.TextField(blank=True)
    revision_number = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey(
        "self", null=True, blank=True, on_delete=P, related_name="revisions"
    )

    def delete(self, *args, **kwargs):
        raise ValidationError("Client reports cannot be deleted.")


class ClientServiceReportSection(UUIDModel):
    report = models.ForeignKey(ClientServiceReport, on_delete=P, related_name="sections")
    section_type = models.CharField(max_length=30)
    title = models.CharField(max_length=200)
    narrative = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)


class ClientServiceReportMetric(UUIDModel):
    report = models.ForeignKey(ClientServiceReport, on_delete=P, related_name="metrics")
    section = models.ForeignKey(ClientServiceReportSection, on_delete=P, related_name="metrics")
    metric_code = models.CharField(max_length=60)
    label = models.CharField(max_length=150)
    value_decimal = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)
    value_integer = models.BigIntegerField(null=True, blank=True)
    value_text = models.CharField(max_length=250, blank=True)
    unit = models.CharField(max_length=30, blank=True)
    sort_order = models.PositiveIntegerField(default=0)


class ClientServiceReportAcknowledgement(UUIDModel):
    report = models.ForeignKey(ClientServiceReport, on_delete=P, related_name="acknowledgements")
    membership = models.ForeignKey(ClientPortalMembership, on_delete=P)
    acknowledged_at = models.DateTimeField()
    comments = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["report", "membership"], name="uniq_client_report_ack")
        ]


class ClientServiceRequest(PortalModel):
    request_number = models.CharField(max_length=40, unique=True)
    client = models.ForeignKey("contracts.Client", on_delete=P)
    contract = models.ForeignKey("contracts.ServiceContract", null=True, blank=True, on_delete=P)
    site = models.ForeignKey("contracts.SecuritySite", null=True, blank=True, on_delete=P)
    created_by_membership = models.ForeignKey(ClientPortalMembership, on_delete=P)
    request_type = models.CharField(max_length=30)
    priority = models.CharField(max_length=10, default="NORMAL")
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=30, choices=enums.RequestStatus.choices, default="OPEN")
    assigned_to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_summary = models.TextField(blank=True)
    linked_incident = models.OneToOneField("incidents.Incident", null=True, blank=True, on_delete=P)


class ClientServiceRequestComment(UUIDModel):
    request = models.ForeignKey(ClientServiceRequest, on_delete=P, related_name="comments")
    author_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    author_membership = models.ForeignKey(
        ClientPortalMembership, null=True, blank=True, on_delete=P
    )
    is_internal = models.BooleanField(default=False)
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)


class ClientFeedback(UUIDModel):
    client = models.ForeignKey("contracts.Client", on_delete=P)
    contract = models.ForeignKey("contracts.ServiceContract", null=True, blank=True, on_delete=P)
    site = models.ForeignKey("contracts.SecuritySite", null=True, blank=True, on_delete=P)
    membership = models.ForeignKey(ClientPortalMembership, on_delete=P)
    feedback_type = models.CharField(max_length=30)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=200)
    comments = models.TextField()
    submitted_at = models.DateTimeField()
    internal_status = models.CharField(max_length=20, default="NEW")
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ClientSharedAttachment(UUIDModel):
    company = models.ForeignKey("organization.Company", on_delete=P)
    client = models.ForeignKey("contracts.Client", on_delete=P)
    report = models.ForeignKey(ClientServiceReport, null=True, blank=True, on_delete=P)
    incident_visibility = models.ForeignKey(
        IncidentClientVisibility, null=True, blank=True, on_delete=P
    )
    service_request = models.ForeignKey(ClientServiceRequest, null=True, blank=True, on_delete=P)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(storage=private_portal_storage, upload_to=portal_attachment_upload_to)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField()
    mime_type = models.CharField(max_length=100)
    sha256_hash = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    published_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ClientPortalAuditEvent(UUIDModel):
    client = models.ForeignKey("contracts.Client", on_delete=P)
    membership = models.ForeignKey(ClientPortalMembership, null=True, blank=True, on_delete=P)
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    event_type = models.CharField(max_length=50)
    resource_type = models.CharField(max_length=50, blank=True)
    resource_id = models.UUIDField(null=True, blank=True)
    occurred_at = models.DateTimeField()
    description = models.CharField(max_length=250, blank=True)

    def delete(self, *args, **kwargs):
        raise ValidationError("Portal audit events are immutable.")
