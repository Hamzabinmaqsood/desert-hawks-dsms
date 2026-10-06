# mypy: disable-error-code="no-untyped-def,no-any-return,no-untyped-call,operator,type-arg"
"""Explicit tenant-consistency and scoped query helpers for Patrol."""

from __future__ import annotations

from django.db.models import F, Q, QuerySet

from dsms.contracts.models import SecurityPost, SecuritySite
from dsms.deployment.models import DutyAssignment
from dsms.deployment.tenant_queries import (
    consistent_duty_assignments,
    consistent_employees,
    consistent_posts,
    consistent_sites,
)
from dsms.identity import access
from dsms.workforce.models import Employee

from . import models


def consistent_policies(queryset: QuerySet[models.PatrolPolicy]) -> QuerySet[models.PatrolPolicy]:
    return (
        queryset.filter(company__is_active=True)
        .filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__in=consistent_sites(SecuritySite.objects.all())))
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
        .filter(
            Q(branch__isnull=True)
            | Q(site__isnull=True)
            | Q(site__managing_branch_id=F("branch_id"))
        )
    )


def consistent_checkpoints(
    queryset: QuerySet[models.PatrolCheckpoint],
) -> QuerySet[models.PatrolCheckpoint]:
    return (
        queryset.filter(company__is_active=True)
        .filter(client__company_id=F("company_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
        .filter(site__company_id=F("company_id"), site__client_id=F("client_id"))
        .filter(Q(post__isnull=True) | Q(post__in=consistent_posts(SecurityPost.objects.all())))
        .filter(Q(post__isnull=True) | Q(post__company_id=F("company_id")))
        .filter(Q(post__isnull=True) | Q(post__client_id=F("client_id")))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
    )


def consistent_qr_credentials(queryset):
    return queryset.filter(
        checkpoint__in=consistent_checkpoints(models.PatrolCheckpoint.objects.all())
    )


def consistent_nfc_credentials(queryset):
    return queryset.filter(
        checkpoint__in=consistent_checkpoints(models.PatrolCheckpoint.objects.all())
    )


def consistent_routes(queryset: QuerySet[models.PatrolRoute]) -> QuerySet[models.PatrolRoute]:
    return (
        queryset.filter(company__is_active=True)
        .filter(client__company_id=F("company_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
        .filter(site__company_id=F("company_id"), site__client_id=F("client_id"))
    )


def consistent_route_versions(queryset):
    return queryset.filter(patrol_route__in=consistent_routes(models.PatrolRoute.objects.all()))


def consistent_route_checkpoints(queryset):
    return (
        queryset.filter(
            route_version__in=consistent_route_versions(models.PatrolRouteVersion.objects.all())
        )
        .filter(checkpoint__in=consistent_checkpoints(models.PatrolCheckpoint.objects.all()))
        .filter(
            checkpoint__company_id=F("route_version__patrol_route__company_id"),
            checkpoint__client_id=F("route_version__patrol_route__client_id"),
            checkpoint__site_id=F("route_version__patrol_route__site_id"),
        )
    )


def consistent_requirements(queryset):
    return (
        queryset.filter(company__is_active=True)
        .filter(branch__company_id=F("company_id"))
        .filter(client__company_id=F("company_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
        .filter(
            site__company_id=F("company_id"),
            site__client_id=F("client_id"),
            site__managing_branch_id=F("branch_id"),
        )
        .filter(patrol_route__in=consistent_routes(models.PatrolRoute.objects.all()))
        .filter(
            patrol_route__company_id=F("company_id"),
            patrol_route__client_id=F("client_id"),
            patrol_route__site_id=F("site_id"),
        )
        .filter(
            Q(assigned_designation__isnull=True)
            | Q(assigned_designation__company_id=F("company_id"))
        )
    )


def consistent_requirement_days(queryset):
    return queryset.filter(
        patrol_requirement__in=consistent_requirements(models.PatrolRequirement.objects.all())
    )


def consistent_requirement_times(queryset):
    return queryset.filter(
        patrol_requirement__in=consistent_requirements(models.PatrolRequirement.objects.all())
    )


def consistent_tasks(queryset: QuerySet[models.PatrolTask]) -> QuerySet[models.PatrolTask]:
    return (
        queryset.filter(company__is_active=True)
        .filter(branch__company_id=F("company_id"))
        .filter(client__company_id=F("company_id"))
        .filter(site__in=consistent_sites(SecuritySite.objects.all()))
        .filter(
            site__company_id=F("company_id"),
            site__client_id=F("client_id"),
            site__managing_branch_id=F("branch_id"),
        )
        .filter(patrol_route__in=consistent_routes(models.PatrolRoute.objects.all()))
        .filter(
            patrol_route__company_id=F("company_id"),
            patrol_route__client_id=F("client_id"),
            patrol_route__site_id=F("site_id"),
        )
        .filter(
            route_version__in=consistent_route_versions(models.PatrolRouteVersion.objects.all())
        )
        .filter(route_version__patrol_route_id=F("patrol_route_id"))
        .filter(
            Q(patrol_requirement__isnull=True)
            | Q(
                patrol_requirement__in=consistent_requirements(
                    models.PatrolRequirement.objects.all()
                )
            )
        )
        .filter(
            Q(patrol_requirement__isnull=True) | Q(patrol_requirement__company_id=F("company_id"))
        )
        .filter(
            Q(patrol_requirement__isnull=True) | Q(patrol_requirement__branch_id=F("branch_id"))
        )
        .filter(
            Q(patrol_requirement__isnull=True) | Q(patrol_requirement__client_id=F("client_id"))
        )
        .filter(Q(patrol_requirement__isnull=True) | Q(patrol_requirement__site_id=F("site_id")))
        .filter(
            Q(patrol_requirement__isnull=True)
            | Q(patrol_requirement__patrol_route_id=F("patrol_route_id"))
        )
        .filter(
            Q(assigned_employee__isnull=True)
            | Q(assigned_employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(
            Q(assigned_employee__isnull=True) | Q(assigned_employee__company_id=F("company_id"))
        )
        .filter(
            Q(supervisor__isnull=True)
            | Q(supervisor__in=consistent_employees(Employee.objects.all()))
        )
        .filter(Q(supervisor__isnull=True) | Q(supervisor__company_id=F("company_id")))
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(duty_assignment__in=consistent_duty_assignments(DutyAssignment.objects.all()))
        )
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(duty_assignment__duty_shift__company_id=F("company_id"))
        )
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(duty_assignment__duty_shift__branch_id=F("branch_id"))
        )
        .filter(
            Q(duty_assignment__isnull=True) | Q(duty_assignment__duty_shift__site_id=F("site_id"))
        )
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(assigned_employee__isnull=True)
            | Q(duty_assignment__employee_id=F("assigned_employee_id"))
        )
    )


def consistent_runs(queryset: QuerySet[models.PatrolRun]) -> QuerySet[models.PatrolRun]:
    return (
        queryset.filter(company__is_active=True)
        .filter(patrol_task__in=consistent_tasks(models.PatrolTask.objects.all()))
        .filter(patrol_task__company_id=F("company_id"))
        .filter(site_id=F("patrol_task__site_id"))
        .filter(employee__in=consistent_employees(Employee.objects.all()))
        .filter(employee__company_id=F("company_id"))
        .filter(employee_id=F("patrol_task__assigned_employee_id"))
        .filter(route_version_id=F("patrol_task__route_version_id"))
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(duty_assignment__in=consistent_duty_assignments(DutyAssignment.objects.all()))
        )
        .filter(Q(duty_assignment__isnull=True) | Q(duty_assignment__employee_id=F("employee_id")))
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(duty_assignment_id=F("patrol_task__duty_assignment_id"))
        )
    )


def consistent_events(queryset):
    return (
        queryset.filter(patrol_run__in=consistent_runs(models.PatrolRun.objects.all()))
        .filter(employee__in=consistent_employees(Employee.objects.all()))
        .filter(employee_id=F("patrol_run__employee_id"))
    )


def consistent_visits(queryset):
    return (
        queryset.filter(patrol_run__in=consistent_runs(models.PatrolRun.objects.all()))
        .filter(patrol_event__in=consistent_events(models.PatrolEvent.objects.all()))
        .filter(patrol_event__patrol_run_id=F("patrol_run_id"))
        .filter(
            route_checkpoint__in=consistent_route_checkpoints(
                models.PatrolRouteCheckpoint.objects.all()
            )
        )
        .filter(route_checkpoint__route_version_id=F("patrol_run__route_version_id"))
        .filter(checkpoint_id=F("route_checkpoint__checkpoint_id"))
        .filter(
            Q(qr_credential__isnull=True)
            | Q(
                qr_credential__in=consistent_qr_credentials(
                    models.CheckpointQRCredential.objects.all()
                )
            )
        )
        .filter(Q(qr_credential__isnull=True) | Q(qr_credential__checkpoint_id=F("checkpoint_id")))
        .filter(
            Q(nfc_credential__isnull=True)
            | Q(
                nfc_credential__in=consistent_nfc_credentials(
                    models.CheckpointNFCCredential.objects.all()
                )
            )
        )
        .filter(
            Q(nfc_credential__isnull=True) | Q(nfc_credential__checkpoint_id=F("checkpoint_id"))
        )
    )


def consistent_observations(queryset):
    return (
        queryset.filter(company__is_active=True)
        .filter(patrol_run__in=consistent_runs(models.PatrolRun.objects.all()))
        .filter(patrol_run__company_id=F("company_id"), site_id=F("patrol_run__site_id"))
        .filter(
            Q(checkpoint_visit__isnull=True)
            | Q(checkpoint_visit__in=consistent_visits(models.CheckpointVisit.objects.all()))
        )
        .filter(
            Q(checkpoint_visit__isnull=True) | Q(checkpoint_visit__patrol_run_id=F("patrol_run_id"))
        )
        .filter(
            Q(checkpoint__isnull=True)
            | Q(checkpoint__in=consistent_checkpoints(models.PatrolCheckpoint.objects.all()))
        )
        .filter(Q(checkpoint__isnull=True) | Q(checkpoint__site_id=F("site_id")))
        .filter(
            Q(checkpoint_visit__isnull=True)
            | Q(checkpoint__isnull=True)
            | Q(checkpoint_visit__checkpoint_id=F("checkpoint_id"))
        )
        .filter(Q(post__isnull=True) | Q(post__in=consistent_posts(SecurityPost.objects.all())))
        .filter(Q(post__isnull=True) | Q(post__site_id=F("site_id")))
    )


def consistent_evidence(queryset):
    return (
        queryset.filter(company__is_active=True)
        .filter(patrol_run__in=consistent_runs(models.PatrolRun.objects.all()))
        .filter(patrol_run__company_id=F("company_id"))
        .filter(
            Q(checkpoint_visit__isnull=True)
            | Q(checkpoint_visit__in=consistent_visits(models.CheckpointVisit.objects.all()))
        )
        .filter(
            Q(checkpoint_visit__isnull=True) | Q(checkpoint_visit__patrol_run_id=F("patrol_run_id"))
        )
        .filter(
            Q(observation__isnull=True)
            | Q(observation__in=consistent_observations(models.PatrolObservation.objects.all()))
        )
        .filter(Q(observation__isnull=True) | Q(observation__patrol_run_id=F("patrol_run_id")))
    )


def consistent_exceptions(queryset):
    return (
        queryset.filter(company__is_active=True)
        .filter(patrol_task__in=consistent_tasks(models.PatrolTask.objects.all()))
        .filter(patrol_task__company_id=F("company_id"))
        .filter(
            Q(patrol_run__isnull=True)
            | Q(patrol_run__in=consistent_runs(models.PatrolRun.objects.all()))
        )
        .filter(Q(patrol_run__isnull=True) | Q(patrol_run__patrol_task_id=F("patrol_task_id")))
        .filter(
            Q(checkpoint_visit__isnull=True)
            | Q(checkpoint_visit__in=consistent_visits(models.CheckpointVisit.objects.all()))
        )
        .filter(Q(checkpoint_visit__isnull=True) | Q(patrol_run__isnull=False))
        .filter(
            Q(checkpoint_visit__isnull=True) | Q(checkpoint_visit__patrol_run_id=F("patrol_run_id"))
        )
    )


def consistent_reviews(queryset):
    return queryset.filter(patrol_run__in=consistent_runs(models.PatrolRun.objects.all()))


CONSISTENCY_FILTERS = {
    models.PatrolPolicy: consistent_policies,
    models.PatrolCheckpoint: consistent_checkpoints,
    models.CheckpointQRCredential: consistent_qr_credentials,
    models.CheckpointNFCCredential: consistent_nfc_credentials,
    models.PatrolRoute: consistent_routes,
    models.PatrolRouteVersion: consistent_route_versions,
    models.PatrolRouteCheckpoint: consistent_route_checkpoints,
    models.PatrolRequirement: consistent_requirements,
    models.PatrolRequirementDay: consistent_requirement_days,
    models.PatrolRequirementTime: consistent_requirement_times,
    models.PatrolTask: consistent_tasks,
    models.PatrolRun: consistent_runs,
    models.PatrolEvent: consistent_events,
    models.CheckpointVisit: consistent_visits,
    models.PatrolObservation: consistent_observations,
    models.PatrolEvidence: consistent_evidence,
    models.PatrolException: consistent_exceptions,
    models.PatrolReview: consistent_reviews,
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
    if model is models.PatrolPolicy:
        return queryset.filter(
            Q(branch_id__in=branch_ids)
            | Q(site__managing_branch_id__in=branch_ids)
            | Q(branch__isnull=True, site__isnull=True, company_id__in=company_ids)
        )
    if model in {models.PatrolCheckpoint, models.PatrolRoute}:
        return queryset.filter(site__managing_branch_id__in=branch_ids)
    if model is models.PatrolRequirement:
        return queryset.filter(branch_id__in=branch_ids)
    if model is models.PatrolTask:
        return queryset.filter(branch_id__in=branch_ids)
    if model in {models.PatrolRun, models.PatrolObservation, models.PatrolEvidence}:
        return (
            queryset.filter(patrol_run__patrol_task__branch_id__in=branch_ids)
            if model is not models.PatrolRun
            else queryset.filter(patrol_task__branch_id__in=branch_ids)
        )
    if model is models.PatrolEvent:
        return queryset.filter(patrol_run__patrol_task__branch_id__in=branch_ids)
    if model is models.CheckpointVisit:
        return queryset.filter(patrol_run__patrol_task__branch_id__in=branch_ids)
    if model is models.PatrolException:
        return queryset.filter(patrol_task__branch_id__in=branch_ids)
    if model is models.PatrolReview:
        return queryset.filter(patrol_run__patrol_task__branch_id__in=branch_ids)
    if model in {models.PatrolRouteVersion, models.PatrolRouteCheckpoint}:
        return (
            queryset.filter(patrol_route__site__managing_branch_id__in=branch_ids)
            if model is models.PatrolRouteVersion
            else queryset.filter(
                route_version__patrol_route__site__managing_branch_id__in=branch_ids
            )
        )
    if model in {models.CheckpointQRCredential, models.CheckpointNFCCredential}:
        return queryset.filter(checkpoint__site__managing_branch_id__in=branch_ids)
    if model in {models.PatrolRequirementDay, models.PatrolRequirementTime}:
        return queryset.filter(patrol_requirement__branch_id__in=branch_ids)
    return queryset.none()
