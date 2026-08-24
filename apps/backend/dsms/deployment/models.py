from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.contracts.models import (
    Client,
    SecurityPost,
    SecuritySite,
    ServiceContract,
    StaffingRequirement,
)
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Designation, OperationalZone
from dsms.workforce.enums import EmployeeType
from dsms.workforce.models import Employee

from .enums import (
    AssignmentType,
    DeploymentStatus,
    DeploymentType,
    DutyAssignmentStatus,
    DutyShiftStatus,
    ReplacementPriority,
    ReplacementRequestStatus,
    RosterChangeType,
    RosterStatus,
    ScheduleBlockType,
)


class DeploymentModel(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class EmployeeDeployment(DeploymentModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="deployments")
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    contract = models.ForeignKey(ServiceContract, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT)
    primary_post = models.ForeignKey(SecurityPost, null=True, blank=True, on_delete=models.PROTECT)
    managing_branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    deployment_type = models.CharField(max_length=20, choices=DeploymentType.choices)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=DeploymentStatus.choices, default=DeploymentStatus.DRAFT
    )
    is_primary = models.BooleanField(default=False)
    reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_deployments"
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_deployments"
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(is_primary=True, status=DeploymentStatus.ACTIVE),
                name="uniq_active_primary_deployment",
            )
        ]
        indexes = [
            models.Index(fields=["employee", "status"]),
            models.Index(fields=["site", "status"]),
        ]
        permissions = [
            ("activate_deployment", "Can activate deployments"),
            ("end_deployment", "Can end deployments"),
        ]


class DeploymentPool(DeploymentModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    operational_zone = models.ForeignKey(
        OperationalZone, null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_deployment_pool_code")
        ]


class DeploymentPoolMembership(DeploymentModel, ActiveModel):
    pool = models.ForeignKey(DeploymentPool, on_delete=models.PROTECT, related_name="memberships")
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="deployment_pool_memberships"
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    priority = models.IntegerField(default=0)


class ShiftTemplate(DeploymentModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, null=True, blank=True, on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    start_time = models.TimeField()
    end_time = models.TimeField()
    crosses_midnight = models.BooleanField(default=False)
    planned_break_minutes = models.PositiveIntegerField(default=0)
    nominal_hours = models.DecimalField(max_digits=5, decimal_places=2)
    description = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_shift_template_code")
        ]


class SchedulingPolicy(DeploymentModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    minimum_rest_hours = models.DecimalField(max_digits=5, decimal_places=2)
    maximum_planned_hours_per_day = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    maximum_planned_hours_per_week = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    maximum_consecutive_duty_days = models.PositiveIntegerField(null=True, blank=True)
    overtime_warning_hours_per_week = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    allow_cross_branch_deployment = models.BooleanField(default=False)
    allow_readiness_warning_assignment = models.BooleanField(default=False)
    allow_overtime_assignment = models.BooleanField(default=False)
    require_published_roster_confirmation = models.BooleanField(default=True)


class RosterPeriod(DeploymentModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    roster_number = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=20, choices=RosterStatus.choices, default=RosterStatus.DRAFT
    )
    version_number = models.PositiveIntegerField(default=1)
    generated_at = models.DateTimeField(null=True, blank=True)
    generated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="generated_rosters"
    )
    submitted_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="submitted_rosters"
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_rosters"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="published_rosters"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="locked_rosters"
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_rosters")

    class Meta:
        indexes = [models.Index(fields=["branch", "period_start", "period_end", "status"])]
        permissions = [
            ("generate_roster", "Can generate roster demand"),
            ("approve_roster", "Can approve rosters"),
            ("publish_roster", "Can publish rosters"),
            ("lock_roster", "Can lock rosters"),
        ]


class DutyShift(DeploymentModel):
    roster_period = models.ForeignKey(
        RosterPeriod, on_delete=models.PROTECT, related_name="duty_shifts"
    )
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    contract = models.ForeignKey(ServiceContract, on_delete=models.PROTECT)
    site = models.ForeignKey(SecuritySite, on_delete=models.PROTECT, related_name="duty_shifts")
    post = models.ForeignKey(SecurityPost, on_delete=models.PROTECT, related_name="duty_shifts")
    staffing_requirement = models.ForeignKey(
        StaffingRequirement, null=True, blank=True, on_delete=models.PROTECT
    )
    shift_template = models.ForeignKey(
        ShiftTemplate, null=True, blank=True, on_delete=models.PROTECT
    )
    duty_date = models.DateField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    required_headcount = models.PositiveIntegerField()
    employee_type = models.CharField(max_length=20, choices=EmployeeType.choices)
    designation = models.ForeignKey(Designation, null=True, blank=True, on_delete=models.PROTECT)
    armed_required = models.BooleanField(default=False)
    supervisor_required = models.BooleanField(default=False)
    is_adhoc = models.BooleanField(default=False)
    adhoc_reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=DutyShiftStatus.choices, default=DutyShiftStatus.PLANNED
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["roster_period", "staffing_requirement", "duty_date", "starts_at"],
                condition=Q(staffing_requirement__isnull=False),
                name="uniq_generated_duty_shift",
            )
        ]
        indexes = [
            models.Index(fields=["duty_date", "status"]),
            models.Index(fields=["site", "post", "duty_date"]),
        ]


class DutyAssignment(DeploymentModel):
    duty_shift = models.ForeignKey(DutyShift, on_delete=models.PROTECT, related_name="assignments")
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="duty_assignments"
    )
    deployment = models.ForeignKey(
        EmployeeDeployment, null=True, blank=True, on_delete=models.PROTECT
    )
    assignment_type = models.CharField(max_length=20, choices=AssignmentType.choices)
    status = models.CharField(
        max_length=20, choices=DutyAssignmentStatus.choices, default=DutyAssignmentStatus.PLANNED
    )
    assigned_by = models.ForeignKey(User, on_delete=models.PROTECT)
    assigned_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    replaces_assignment = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="replacement"
    )
    replacement_reason = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["duty_shift", "employee"],
                condition=Q(
                    status__in=[DutyAssignmentStatus.PLANNED, DutyAssignmentStatus.CONFIRMED]
                ),
                name="uniq_active_employee_shift",
            )
        ]
        indexes = [models.Index(fields=["employee", "status"])]
        permissions = [
            ("assign_employee", "Can assign employees"),
            ("replace_employee", "Can replace employees"),
            ("emergency_assignment", "Can make emergency assignments"),
            ("allow_overstaffing", "Can authorize overstaffing"),
        ]


class EmployeeScheduleBlock(DeploymentModel, ActiveModel):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="schedule_blocks")
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    block_type = models.CharField(max_length=30, choices=ScheduleBlockType.choices)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.TextField()
    source_reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)


class ReplacementRequest(DeploymentModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    duty_shift = models.ForeignKey(
        DutyShift, on_delete=models.PROTECT, related_name="replacement_requests"
    )
    original_assignment = models.ForeignKey(
        DutyAssignment,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replacement_requests",
    )
    requested_employee = models.ForeignKey(
        Employee,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="requested_replacements",
    )
    replacement_employee = models.ForeignKey(
        Employee,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replacement_assignments",
    )
    reason = models.CharField(max_length=30)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=ReplacementPriority.choices)
    status = models.CharField(
        max_length=20,
        choices=ReplacementRequestStatus.choices,
        default=ReplacementRequestStatus.OPEN,
    )
    requested_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="requested_replacement_requests"
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_replacement_requests",
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_replacement_requests",
    )
    completed_at = models.DateTimeField(null=True, blank=True)


class RosterChangeEvent(UUIDModel):
    roster_period = models.ForeignKey(
        RosterPeriod, on_delete=models.PROTECT, related_name="change_events"
    )
    duty_shift = models.ForeignKey(DutyShift, null=True, blank=True, on_delete=models.PROTECT)
    duty_assignment = models.ForeignKey(
        DutyAssignment, null=True, blank=True, on_delete=models.PROTECT
    )
    change_type = models.CharField(max_length=30, choices=RosterChangeType.choices)
    actor = models.ForeignKey(User, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    previous_employee = models.ForeignKey(
        Employee,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="previous_roster_changes",
    )
    new_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.PROTECT, related_name="new_roster_changes"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class RosterAvailabilityConflict(DeploymentModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    duty_assignment = models.ForeignKey(
        DutyAssignment, on_delete=models.PROTECT, related_name="availability_conflicts"
    )
    leave_request = models.ForeignKey(
        "leave.LeaveRequest", on_delete=models.PROTECT, related_name="roster_conflicts"
    )
    conflict_type = models.CharField(max_length=30, default="APPROVED_LEAVE")
    status = models.CharField(max_length=20, default="OPEN")
    detected_at = models.DateTimeField(auto_now_add=True)
    replacement_request = models.ForeignKey(
        ReplacementRequest, null=True, blank=True, on_delete=models.PROTECT
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["duty_assignment", "leave_request"],
                name="uniq_assignment_leave_conflict",
            )
        ]
