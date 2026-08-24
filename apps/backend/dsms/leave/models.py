# mypy: disable-error-code="no-untyped-def"
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import TimeStampedModel, UUIDModel

from .enums import LeaveRequestStatus, TransactionType
from .storage import leave_attachment_upload_to, private_leave_storage

P = models.PROTECT


class Base(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class LeaveType(Base):
    company = models.ForeignKey("organization.Company", null=True, blank=True, on_delete=P)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=10, choices=[("DAYS", "Days"), ("HOURS", "Hours")])
    pay_treatment = models.CharField(max_length=30)
    requires_balance = models.BooleanField(default=True)
    requires_attachment = models.BooleanField(default=False)
    attachment_required_after_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    minimum_request_notice_hours = models.PositiveIntegerField(null=True, blank=True)
    maximum_consecutive_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    minimum_request_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    allow_partial_day = models.BooleanField(default=False)
    allow_negative_balance = models.BooleanField(default=False)
    allow_carry_forward = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default="ACTIVE")
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_leave_type_company_code")
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Leave types must be retired, not deleted.")


class LeavePolicy(Base):
    company = models.ForeignKey("organization.Company", on_delete=P)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_leave_policy_code")
        ]


class LeavePolicyRule(Base):
    policy = models.ForeignKey(LeavePolicy, on_delete=P, related_name="rules")
    leave_type = models.ForeignKey(LeaveType, on_delete=P)
    minimum_service_days = models.PositiveIntegerField(null=True, blank=True)
    employee_type = models.CharField(max_length=30, blank=True)
    employment_type = models.CharField(max_length=30, blank=True)
    designation = models.ForeignKey("organization.Designation", null=True, blank=True, on_delete=P)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=P)
    branch = models.ForeignKey("organization.Branch", null=True, blank=True, on_delete=P)
    entitlement_units = models.DecimalField(max_digits=10, decimal_places=2)
    entitlement_period_months = models.PositiveIntegerField(default=12)
    accrual_method = models.CharField(max_length=20, default="NONE")
    accrual_units = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    accrual_interval = models.PositiveIntegerField(null=True, blank=True)
    allow_negative_balance = models.BooleanField(default=False)
    maximum_negative_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    carry_forward_method = models.CharField(max_length=20, default="NONE")
    carry_forward_limit_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    carry_forward_expiry_months = models.PositiveIntegerField(null=True, blank=True)
    maximum_balance_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    minimum_notice_hours = models.PositiveIntegerField(null=True, blank=True)
    maximum_consecutive_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    minimum_request_units = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    allow_partial_day = models.BooleanField(default=False)
    approval_required = models.BooleanField(default=True)
    charge_method = models.CharField(max_length=30, default="CALENDAR_DAYS")
    holidays_are_chargeable = models.BooleanField(default=False)
    rostered_rest_days_are_chargeable = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)


class EmployeeLeavePolicyAssignment(Base):
    employee = models.ForeignKey(
        "workforce.Employee", on_delete=P, related_name="leave_policy_assignments"
    )
    company = models.ForeignKey("organization.Company", on_delete=P)
    leave_policy = models.ForeignKey(LeavePolicy, on_delete=P)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    reason = models.TextField(blank=True)


class LeaveEntitlementPeriod(Base):
    company = models.ForeignKey("organization.Company", on_delete=P)
    employee = models.ForeignKey("workforce.Employee", on_delete=P)
    leave_type = models.ForeignKey(LeaveType, on_delete=P)
    leave_policy = models.ForeignKey(LeavePolicy, on_delete=P)
    policy_rule = models.ForeignKey(LeavePolicyRule, on_delete=P)
    period_start = models.DateField()
    period_end = models.DateField()
    opening_entitlement_units = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, default="OPEN")
    calculated_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "leave_type", "period_start", "period_end"],
                name="uniq_leave_entitlement_period",
            )
        ]


class LeaveBalanceAccount(Base):
    company = models.ForeignKey("organization.Company", on_delete=P)
    employee = models.ForeignKey("workforce.Employee", on_delete=P)
    leave_type = models.ForeignKey(LeaveType, on_delete=P)
    entitlement_period = models.OneToOneField(
        LeaveEntitlementPeriod, on_delete=P, related_name="balance_account"
    )


class LeaveApprovalPolicy(Base):
    company = models.ForeignKey("organization.Company", on_delete=P)
    leave_type = models.ForeignKey(LeaveType, null=True, blank=True, on_delete=P)
    employee_type = models.CharField(max_length=30, blank=True)
    branch = models.ForeignKey("organization.Branch", null=True, blank=True, on_delete=P)
    department = models.ForeignKey("organization.Department", null=True, blank=True, on_delete=P)
    minimum_units = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    maximum_units = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_active = models.BooleanField(default=True)


class LeaveApprovalStep(UUIDModel):
    policy = models.ForeignKey(LeaveApprovalPolicy, on_delete=P, related_name="steps")
    sequence = models.PositiveIntegerField()
    approver_type = models.CharField(max_length=30)
    role_code = models.CharField(max_length=80, blank=True)
    specific_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    required = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["policy", "sequence"], name="uniq_leave_approval_step")
        ]


class LeaveRequest(Base):
    request_number = models.CharField(max_length=40, unique=True)
    company = models.ForeignKey("organization.Company", on_delete=P)
    employee = models.ForeignKey("workforce.Employee", on_delete=P, related_name="leave_requests")
    leave_type = models.ForeignKey(LeaveType, on_delete=P)
    policy = models.ForeignKey(LeavePolicy, on_delete=P)
    policy_rule = models.ForeignKey(LeavePolicyRule, on_delete=P)
    approval_policy = models.ForeignKey(LeaveApprovalPolicy, null=True, blank=True, on_delete=P)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    requested_units = models.DecimalField(max_digits=10, decimal_places=2)
    approved_units = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    reason = models.TextField()
    status = models.CharField(
        max_length=30, choices=LeaveRequestStatus.choices, default="DRAFT", db_index=True
    )
    emergency_request = models.BooleanField(default=False)
    contact_during_leave = models.CharField(max_length=150, blank=True)
    handover_notes = models.TextField(blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    current_approval_step = models.ForeignKey(LeaveApprovalStep, null=True, blank=True, on_delete=P)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="approved_leave_requests",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="rejected_leave_requests",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    cancellation_requested_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="cancelled_leave_requests",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    recalled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="recalled_leave_requests",
    )
    recalled_at = models.DateTimeField(null=True, blank=True)
    recall_reason = models.TextField(blank=True)
    actual_return_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="created_leave_requests"
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["employee", "starts_at", "ends_at"]),
        ]
        permissions = [
            (code, code.replace("_", " ").title())
            for code in [
                "view_leave_dashboard",
                "manage_leavetype",
                "manage_leavepolicy",
                "manage_policy_assignments",
                "view_leave_balance",
                "adjust_leave_balance",
                "manage_leave_entitlements",
                "create_own_leave_request",
                "view_own_leave_request",
                "change_own_draft_leave_request",
                "approve_leave_request",
                "reject_leave_request",
                "request_leave_cancellation",
                "approve_leave_cancellation",
                "extend_leave",
                "recall_employee_from_leave",
                "view_sensitive_leave_details",
                "download_leave_attachment",
                "manage_holiday_calendar",
                "view_team_availability",
                "view_operations_availability",
                "export_leave_to_payroll",
                "view_leave_reports",
                "view_leave_audit",
            ]
        ]

    def delete(self, *args, **kwargs):
        if self.status != "DRAFT":
            raise ValidationError("Submitted leave history cannot be deleted.")
        super().delete(*args, **kwargs)


class LeaveBalanceTransaction(UUIDModel):
    balance_account = models.ForeignKey(
        LeaveBalanceAccount, on_delete=P, related_name="transactions"
    )
    transaction_type = models.CharField(max_length=30, choices=TransactionType.choices)
    units = models.DecimalField(max_digits=10, decimal_places=2)
    effective_at = models.DateTimeField(db_index=True)
    leave_request = models.ForeignKey(
        LeaveRequest, null=True, blank=True, on_delete=P, related_name="balance_transactions"
    )
    source_reference = models.CharField(max_length=150, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    reason = models.TextField(blank=True)
    reverses_transaction = models.OneToOneField(
        "self", null=True, blank=True, on_delete=P, related_name="reversal"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["balance_account", "source_reference"],
                condition=~Q(source_reference=""),
                name="uniq_leave_ledger_source",
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Leave ledger is immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Leave ledger is immutable.")


class LeaveApprovalAction(UUIDModel):
    leave_request = models.ForeignKey(LeaveRequest, on_delete=P, related_name="approval_actions")
    approval_step = models.ForeignKey(LeaveApprovalStep, on_delete=P)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    decision = models.CharField(max_length=20)
    comments = models.TextField(blank=True)
    acted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        raise ValidationError("Approval history is immutable.")


class LeaveAttachment(UUIDModel):
    leave_request = models.ForeignKey(LeaveRequest, on_delete=P, related_name="attachments")
    file = models.FileField(storage=private_leave_storage, upload_to=leave_attachment_upload_to)
    original_filename = models.CharField(max_length=255)
    file_size = models.PositiveBigIntegerField()
    mime_type = models.CharField(max_length=100)
    sha256_hash = models.CharField(max_length=64)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    created_at = models.DateTimeField(auto_now_add=True)


class LeaveExtensionRequest(Base):
    original_leave_request = models.ForeignKey(LeaveRequest, on_delete=P, related_name="extensions")
    requested_new_end_at = models.DateTimeField()
    reason = models.TextField()
    status = models.CharField(max_length=20, default="PENDING")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="leave_extensions_requested"
    )
    requested_at = models.DateTimeField()
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="leave_extensions_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)


class HolidayCalendar(Base):
    company = models.ForeignKey("organization.Company", on_delete=P)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=150)
    country_code = models.CharField(max_length=2, blank=True)
    province_or_state = models.CharField(max_length=100, blank=True)
    branch = models.ForeignKey("organization.Branch", null=True, blank=True, on_delete=P)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_holiday_calendar_code")
        ]


class Holiday(Base):
    calendar = models.ForeignKey(HolidayCalendar, on_delete=P, related_name="holidays")
    date = models.DateField(db_index=True)
    name = models.CharField(max_length=150)
    holiday_type = models.CharField(max_length=20)
    is_full_day = models.BooleanField(default=True)
    starts_at = models.TimeField(null=True, blank=True)
    ends_at = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default="ACTIVE")
    affects_leave_charging = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["calendar", "date", "name"], name="uniq_calendar_holiday"
            )
        ]


class EmployeeAvailabilityOverride(UUIDModel):
    employee = models.ForeignKey("workforce.Employee", on_delete=P)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    availability_status = models.CharField(max_length=30)
    reason = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=P, related_name="availability_overrides_created"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=P,
        related_name="availability_overrides_approved",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class LeavePayrollExport(UUIDModel):
    company = models.ForeignKey("organization.Company", on_delete=P)
    period_start = models.DateField()
    period_end = models.DateField()
    payroll_period = models.ForeignKey("finance.PayrollPeriod", null=True, blank=True, on_delete=P)
    exported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=P)
    exported_at = models.DateTimeField()
    status = models.CharField(max_length=20)
    employee_count = models.PositiveIntegerField(default=0)
    source_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "period_start", "period_end", "source_hash"],
                name="uniq_leave_payroll_export",
            )
        ]


class LeaveEvent(UUIDModel):
    leave_request = models.ForeignKey(LeaveRequest, on_delete=P, related_name="events")
    event_type = models.CharField(max_length=50)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=P)
    occurred_at = models.DateTimeField()
    description = models.CharField(max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        raise ValidationError("Leave events are immutable.")
