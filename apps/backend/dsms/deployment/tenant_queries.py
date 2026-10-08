# mypy: disable-error-code="no-untyped-def,no-any-return,operator,type-arg"
"""Explicit tenant-consistency predicates for Deployment and Rostering."""

from __future__ import annotations

from django.db.models import F, Q, QuerySet

from dsms.contracts.models import SecurityPost, SecuritySite, StaffingRequirement
from dsms.identity import access
from dsms.leave.models import LeaveRequest
from dsms.workforce.models import Employee

from .models import (
    DeploymentPool,
    DeploymentPoolMembership,
    DutyAssignment,
    DutyShift,
    EmployeeDeployment,
    EmployeeScheduleBlock,
    ReplacementRequest,
    RosterAvailabilityConflict,
    RosterChangeEvent,
    RosterPeriod,
    SchedulingPolicy,
    ShiftTemplate,
)


def consistent_employees(queryset: QuerySet[Employee]) -> QuerySet[Employee]:
    return (
        queryset.filter(company__is_active=True)
        .filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id")))
        .filter(Q(department__isnull=True) | Q(department__company_id=F("company_id")))
        .filter(Q(designation__isnull=True) | Q(designation__company_id=F("company_id")))
    )


def consistent_sites(queryset: QuerySet[SecuritySite]) -> QuerySet[SecuritySite]:
    return (
        queryset.filter(company__is_active=True)
        .filter(client__company_id=F("company_id"))
        .filter(contract__company_id=F("company_id"))
        .filter(contract__client_id=F("client_id"))
        .filter(managing_branch__company_id=F("company_id"))
        .filter(Q(operational_zone__isnull=True) | Q(operational_zone__company_id=F("company_id")))
        .filter(
            Q(operational_zone__isnull=True)
            | Q(operational_zone__branch_id=F("managing_branch_id"))
        )
    )


def consistent_posts(queryset: QuerySet[SecurityPost]) -> QuerySet[SecurityPost]:
    return (
        queryset.filter(company__is_active=True)
        .filter(client__company_id=F("company_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__client_id=F("client_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
    )


def consistent_staffing_requirements(
    queryset: QuerySet[StaffingRequirement],
) -> QuerySet[StaffingRequirement]:
    return (
        queryset.filter(company__is_active=True)
        .filter(contract__company_id=F("company_id"))
        .filter(contract__client_id=F("site__client_id"))
        .filter(site__company_id=F("company_id"))
        .filter(site__contract_id=F("contract_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
        .filter(post__company_id=F("company_id"))
        .filter(post__site_id=F("site_id"))
        .filter(post__client_id=F("site__client_id"))
        .filter(post__in=consistent_posts(SecurityPost.objects.all()))
        .filter(Q(designation__isnull=True) | Q(designation__company_id=F("company_id")))
    )


def consistent_employee_deployments(
    queryset: QuerySet[EmployeeDeployment],
) -> QuerySet[EmployeeDeployment]:
    return (
        queryset.filter(company__is_active=True)
        .filter(employee__in=consistent_employees(Employee.objects.all()))
        .filter(employee__company_id=F("company_id"))
        .filter(client__company_id=F("company_id"))
        .filter(contract__company_id=F("company_id"))
        .filter(contract__client_id=F("client_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
        .filter(site__company_id=F("company_id"))
        .filter(site__client_id=F("client_id"))
        .filter(site__contract_id=F("contract_id"))
        .filter(managing_branch__company_id=F("company_id"))
        .filter(site__managing_branch_id=F("managing_branch_id"))
        .filter(
            Q(primary_post__isnull=True)
            | Q(primary_post__in=consistent_posts(SecurityPost.objects.all()))
        )
        .filter(Q(primary_post__isnull=True) | Q(primary_post__company_id=F("company_id")))
        .filter(Q(primary_post__isnull=True) | Q(primary_post__site_id=F("site_id")))
        .filter(Q(primary_post__isnull=True) | Q(primary_post__client_id=F("client_id")))
    )


def consistent_pools(queryset: QuerySet[DeploymentPool]) -> QuerySet[DeploymentPool]:
    return (
        queryset.filter(company__is_active=True)
        .filter(branch__company_id=F("company_id"))
        .filter(Q(operational_zone__isnull=True) | Q(operational_zone__company_id=F("company_id")))
        .filter(Q(operational_zone__isnull=True) | Q(operational_zone__branch_id=F("branch_id")))
    )


def consistent_pool_memberships(
    queryset: QuerySet[DeploymentPoolMembership],
) -> QuerySet[DeploymentPoolMembership]:
    return (
        queryset.filter(pool__in=consistent_pools(DeploymentPool.objects.all()))
        .filter(employee__in=consistent_employees(Employee.objects.all()))
        .filter(employee__company_id=F("pool__company_id"))
    )


def consistent_shift_templates(queryset: QuerySet[ShiftTemplate]) -> QuerySet[ShiftTemplate]:
    return queryset.filter(company__is_active=True).filter(
        Q(branch__isnull=True) | Q(branch__company_id=F("company_id"))
    )


def consistent_scheduling_policies(
    queryset: QuerySet[SchedulingPolicy],
) -> QuerySet[SchedulingPolicy]:
    return queryset.filter(company__is_active=True)


def consistent_rosters(queryset: QuerySet[RosterPeriod]) -> QuerySet[RosterPeriod]:
    return queryset.filter(company__is_active=True, branch__company_id=F("company_id"))


def consistent_duty_shifts(queryset: QuerySet[DutyShift]) -> QuerySet[DutyShift]:
    return (
        queryset.filter(company__is_active=True)
        .filter(roster_period__in=consistent_rosters(RosterPeriod.objects.all()))
        .filter(roster_period__company_id=F("company_id"))
        .filter(roster_period__branch_id=F("branch_id"))
        .filter(branch__company_id=F("company_id"))
        .filter(client__company_id=F("company_id"))
        .filter(contract__company_id=F("company_id"))
        .filter(contract__client_id=F("client_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
        .filter(site__company_id=F("company_id"))
        .filter(site__client_id=F("client_id"))
        .filter(site__contract_id=F("contract_id"))
        .filter(site__managing_branch_id=F("branch_id"))
        .filter(post__in=consistent_posts(SecurityPost.objects.all()))
        .filter(post__company_id=F("company_id"))
        .filter(post__client_id=F("client_id"))
        .filter(post__site_id=F("site_id"))
        .filter(
            Q(staffing_requirement__isnull=True)
            | Q(
                staffing_requirement__in=consistent_staffing_requirements(
                    StaffingRequirement.objects.all()
                )
            )
        )
        .filter(
            Q(staffing_requirement__isnull=True)
            | Q(staffing_requirement__company_id=F("company_id"))
        )
        .filter(
            Q(staffing_requirement__isnull=True)
            | Q(staffing_requirement__contract_id=F("contract_id"))
        )
        .filter(
            Q(staffing_requirement__isnull=True) | Q(staffing_requirement__site_id=F("site_id"))
        )
        .filter(
            Q(staffing_requirement__isnull=True) | Q(staffing_requirement__post_id=F("post_id"))
        )
        .filter(Q(shift_template__isnull=True) | Q(shift_template__company_id=F("company_id")))
        .filter(
            Q(shift_template__isnull=True)
            | Q(shift_template__branch__isnull=True)
            | Q(shift_template__branch_id=F("branch_id"))
        )
        .filter(Q(designation__isnull=True) | Q(designation__company_id=F("company_id")))
    )


def _consistent_assignment_core(
    queryset: QuerySet[DutyAssignment],
) -> QuerySet[DutyAssignment]:
    return (
        queryset.filter(duty_shift__in=consistent_duty_shifts(DutyShift.objects.all()))
        .filter(employee__in=consistent_employees(Employee.objects.all()))
        .filter(employee__company_id=F("duty_shift__company_id"))
        .filter(
            Q(deployment__isnull=True)
            | Q(deployment__in=consistent_employee_deployments(EmployeeDeployment.objects.all()))
        )
        .filter(Q(deployment__isnull=True) | Q(deployment__company_id=F("duty_shift__company_id")))
        .filter(Q(deployment__isnull=True) | Q(deployment__employee_id=F("employee_id")))
        .filter(Q(deployment__isnull=True) | Q(deployment__site_id=F("duty_shift__site_id")))
    )


def consistent_duty_assignments(
    queryset: QuerySet[DutyAssignment],
) -> QuerySet[DutyAssignment]:
    return (
        _consistent_assignment_core(queryset)
        .filter(
            Q(replaces_assignment__isnull=True)
            | Q(replaces_assignment__in=_consistent_assignment_core(DutyAssignment.objects.all()))
        )
        .filter(
            Q(replaces_assignment__isnull=True)
            | Q(replaces_assignment__duty_shift_id=F("duty_shift_id"))
        )
    )


def consistent_schedule_blocks(
    queryset: QuerySet[EmployeeScheduleBlock],
) -> QuerySet[EmployeeScheduleBlock]:
    return (
        queryset.filter(company__is_active=True)
        .filter(employee__in=consistent_employees(Employee.objects.all()))
        .filter(employee__company_id=F("company_id"))
    )


def consistent_replacement_requests(
    queryset: QuerySet[ReplacementRequest],
) -> QuerySet[ReplacementRequest]:
    return (
        queryset.filter(company__is_active=True)
        .filter(duty_shift__in=consistent_duty_shifts(DutyShift.objects.all()))
        .filter(duty_shift__company_id=F("company_id"))
        .filter(
            Q(original_assignment__isnull=True)
            | Q(original_assignment__in=consistent_duty_assignments(DutyAssignment.objects.all()))
        )
        .filter(
            Q(original_assignment__isnull=True)
            | Q(original_assignment__duty_shift_id=F("duty_shift_id"))
        )
        .filter(
            Q(requested_employee__isnull=True)
            | Q(requested_employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(
            Q(requested_employee__isnull=True) | Q(requested_employee__company_id=F("company_id"))
        )
        .filter(
            Q(replacement_employee__isnull=True)
            | Q(replacement_employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(
            Q(replacement_employee__isnull=True)
            | Q(replacement_employee__company_id=F("company_id"))
        )
    )


def consistent_roster_changes(
    queryset: QuerySet[RosterChangeEvent],
) -> QuerySet[RosterChangeEvent]:
    return (
        queryset.filter(roster_period__in=consistent_rosters(RosterPeriod.objects.all()))
        .filter(
            Q(duty_shift__isnull=True)
            | Q(duty_shift__in=consistent_duty_shifts(DutyShift.objects.all()))
        )
        .filter(Q(duty_shift__isnull=True) | Q(duty_shift__roster_period_id=F("roster_period_id")))
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(duty_assignment__in=consistent_duty_assignments(DutyAssignment.objects.all()))
        )
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(duty_assignment__duty_shift__roster_period_id=F("roster_period_id"))
        )
        .filter(
            Q(duty_shift__isnull=True)
            | Q(duty_assignment__isnull=True)
            | Q(duty_assignment__duty_shift_id=F("duty_shift_id"))
        )
        .filter(
            Q(previous_employee__isnull=True)
            | Q(previous_employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(
            Q(previous_employee__isnull=True)
            | Q(previous_employee__company_id=F("roster_period__company_id"))
        )
        .filter(
            Q(new_employee__isnull=True)
            | Q(new_employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(
            Q(new_employee__isnull=True)
            | Q(new_employee__company_id=F("roster_period__company_id"))
        )
    )


def consistent_leave_requests(queryset: QuerySet[LeaveRequest]) -> QuerySet[LeaveRequest]:
    return (
        queryset.filter(company__is_active=True)
        .filter(employee__in=consistent_employees(Employee.objects.all()))
        .filter(employee__company_id=F("company_id"))
        .filter(Q(leave_type__company__isnull=True) | Q(leave_type__company_id=F("company_id")))
        .filter(policy__company_id=F("company_id"))
        .filter(policy_rule__policy_id=F("policy_id"))
        .filter(policy_rule__leave_type_id=F("leave_type_id"))
        .filter(Q(approval_policy__isnull=True) | Q(approval_policy__company_id=F("company_id")))
    )


def consistent_availability_conflicts(
    queryset: QuerySet[RosterAvailabilityConflict],
) -> QuerySet[RosterAvailabilityConflict]:
    return (
        queryset.filter(company__is_active=True)
        .filter(duty_assignment__in=consistent_duty_assignments(DutyAssignment.objects.all()))
        .filter(duty_assignment__duty_shift__company_id=F("company_id"))
        .filter(leave_request__in=consistent_leave_requests(LeaveRequest.objects.all()))
        .filter(leave_request__company_id=F("company_id"))
        .filter(leave_request__employee_id=F("duty_assignment__employee_id"))
        .filter(
            Q(replacement_request__isnull=True)
            | Q(
                replacement_request__in=consistent_replacement_requests(
                    ReplacementRequest.objects.all()
                )
            )
        )
        .filter(
            Q(replacement_request__isnull=True) | Q(replacement_request__company_id=F("company_id"))
        )
        .filter(
            Q(replacement_request__isnull=True)
            | Q(replacement_request__original_assignment_id=F("duty_assignment_id"))
        )
    )


CONSISTENCY_FILTERS = {
    EmployeeDeployment: consistent_employee_deployments,
    DeploymentPool: consistent_pools,
    DeploymentPoolMembership: consistent_pool_memberships,
    ShiftTemplate: consistent_shift_templates,
    SchedulingPolicy: consistent_scheduling_policies,
    RosterPeriod: consistent_rosters,
    DutyShift: consistent_duty_shifts,
    DutyAssignment: consistent_duty_assignments,
    EmployeeScheduleBlock: consistent_schedule_blocks,
    ReplacementRequest: consistent_replacement_requests,
    RosterChangeEvent: consistent_roster_changes,
    RosterAvailabilityConflict: consistent_availability_conflicts,
}


def consistent_queryset(queryset: QuerySet) -> QuerySet:
    return CONSISTENCY_FILTERS[queryset.model](queryset)


def scoped_queryset(queryset: QuerySet, *, user, permission: str) -> QuerySet:
    queryset = consistent_queryset(queryset).order_by("pk")
    if user.is_superuser:
        return queryset
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    model = queryset.model
    if model is EmployeeDeployment:
        return queryset.filter(managing_branch_id__in=branch_ids)
    if model is DeploymentPool:
        return queryset.filter(branch_id__in=branch_ids)
    if model is DeploymentPoolMembership:
        return queryset.filter(pool__branch_id__in=branch_ids)
    if model is ShiftTemplate:
        return queryset.filter(
            Q(branch_id__in=branch_ids) | Q(branch__isnull=True, company_id__in=company_ids)
        )
    if model is SchedulingPolicy:
        return queryset.filter(company_id__in=company_ids)
    if model in {RosterPeriod, DutyShift}:
        return queryset.filter(branch_id__in=branch_ids)
    if model is DutyAssignment:
        return queryset.filter(duty_shift__branch_id__in=branch_ids)
    if model is EmployeeScheduleBlock:
        return queryset.filter(
            Q(employee__branch_id__in=branch_ids)
            | Q(employee__branch__isnull=True, company_id__in=company_ids)
        )
    if model is ReplacementRequest:
        return queryset.filter(duty_shift__branch_id__in=branch_ids)
    if model is RosterChangeEvent:
        return queryset.filter(roster_period__branch_id__in=branch_ids)
    if model is RosterAvailabilityConflict:
        return queryset.filter(duty_assignment__duty_shift__branch_id__in=branch_ids)
    return queryset.none()
