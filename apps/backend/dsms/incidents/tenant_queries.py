# mypy: disable-error-code="no-untyped-def,no-any-return,no-untyped-call,type-arg"
"""Explicit tenant-consistency and scoped query helpers for Incidents."""

from __future__ import annotations

from django.db.models import F, Q, QuerySet

from dsms.attendance.tenant_queries import consistent_attendance_records
from dsms.contracts.models import ClientContact, SecuritySite
from dsms.deployment.tenant_queries import (
    consistent_duty_assignments,
    consistent_employee_deployments,
    consistent_employees,
    consistent_posts,
    consistent_sites,
)
from dsms.identity import access
from dsms.patrol.tenant_queries import (
    consistent_exceptions as consistent_patrol_exceptions,
)
from dsms.patrol.tenant_queries import consistent_observations as consistent_patrol_observations
from dsms.patrol.tenant_queries import consistent_runs as consistent_patrol_runs
from dsms.patrol.tenant_queries import consistent_tasks as consistent_patrol_tasks
from dsms.patrol.tenant_queries import consistent_visits as consistent_checkpoint_visits
from dsms.supervision.tenant_queries import (
    consistent_findings,
    consistent_inspections,
    consistent_site_visits,
)
from dsms.workforce.models import Employee

from . import models


def consistent_incident_types(queryset):
    return queryset.filter(Q(company__isnull=True) | Q(company__is_active=True))


def consistent_incidents(queryset: QuerySet[models.Incident]) -> QuerySet[models.Incident]:
    """Exclude inactive and mixed-tenant Incident graphs with flat relational checks."""
    return (
        queryset.filter(company__is_active=True, branch__company_id=F("company_id"))
        .filter(
            Q(operational_zone__isnull=True)
            | Q(
                operational_zone__company_id=F("company_id"),
                operational_zone__branch_id=F("branch_id"),
            )
        )
        .filter(
            Q(incident_type__company__isnull=True) | Q(incident_type__company_id=F("company_id"))
        )
        .filter(Q(client__isnull=True) | Q(client__company_id=F("company_id")))
        .filter(Q(contract__isnull=True) | Q(contract__company_id=F("company_id")))
        .filter(
            Q(contract__isnull=True) | Q(client__isnull=False, contract__client_id=F("client_id"))
        )
        .filter(
            Q(site__isnull=True)
            | Q(
                site__company_id=F("company_id"),
                client_id=F("site__client_id"),
                contract_id=F("site__contract_id"),
                branch_id=F("site__managing_branch_id"),
                site__client__company_id=F("company_id"),
                site__contract__company_id=F("company_id"),
                site__contract__client_id=F("client_id"),
            )
        )
        .filter(
            Q(post__isnull=True)
            | Q(
                site__isnull=False,
                post__company_id=F("company_id"),
                post__client_id=F("client_id"),
                post__site_id=F("site_id"),
                post__site__company_id=F("company_id"),
            )
        )
        .filter(
            Q(reporter_employee__isnull=True) | Q(reporter_employee__company_id=F("company_id"))
        )
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(
                duty_assignment__duty_shift__company_id=F("company_id"),
                duty_assignment__duty_shift__branch_id=F("branch_id"),
                duty_assignment__duty_shift__client_id=F("client_id"),
                duty_assignment__duty_shift__contract_id=F("contract_id"),
                duty_assignment__duty_shift__site_id=F("site_id"),
                duty_assignment__duty_shift__post_id=F("post_id"),
                duty_assignment__employee__company_id=F("company_id"),
            )
        )
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(reporter_employee__isnull=True)
            | Q(duty_assignment__employee_id=F("reporter_employee_id"))
        )
        .filter(
            Q(attendance_record__isnull=True)
            | Q(
                duty_assignment__isnull=False,
                attendance_record__duty_assignment_id=F("duty_assignment_id"),
                attendance_record__company_id=F("company_id"),
                attendance_record__branch_id=F("branch_id"),
                attendance_record__client_id=F("client_id"),
                attendance_record__site_id=F("site_id"),
                attendance_record__post_id=F("post_id"),
                attendance_record__employee__company_id=F("company_id"),
                attendance_record__employee_id=F("duty_assignment__employee_id"),
            )
        )
        .filter(
            Q(attendance_record__isnull=True)
            | Q(reporter_employee__isnull=True)
            | Q(attendance_record__employee_id=F("reporter_employee_id"))
        )
        .filter(
            Q(employee_deployment__isnull=True)
            | Q(
                employee_deployment__company_id=F("company_id"),
                employee_deployment__client_id=F("client_id"),
                employee_deployment__contract_id=F("contract_id"),
                employee_deployment__site_id=F("site_id"),
                employee_deployment__managing_branch_id=F("branch_id"),
                employee_deployment__employee__company_id=F("company_id"),
            )
        )
        .filter(
            Q(employee_deployment__isnull=True)
            | Q(reporter_employee__isnull=True)
            | Q(employee_deployment__employee_id=F("reporter_employee_id"))
        )
        .filter(
            Q(site_visit__isnull=True)
            | Q(
                site_visit__company_id=F("company_id"),
                site_visit__branch_id=F("branch_id"),
                site_visit__site_id=F("site_id"),
                site_visit__site__company_id=F("company_id"),
                site_visit__site__client_id=F("client_id"),
                site_visit__site__contract_id=F("contract_id"),
                site_visit__supervisor__company_id=F("company_id"),
            )
        )
        .filter(
            Q(site_visit__isnull=True)
            | Q(site_visit__visit_plan__isnull=True)
            | Q(
                site_visit__visit_plan__company_id=F("company_id"),
                site_visit__visit_plan__branch_id=F("branch_id"),
                site_visit__visit_plan__site_id=F("site_id"),
                site_visit__visit_plan__supervisor_id=F("site_visit__supervisor_id"),
            )
        )
        .filter(
            Q(inspection__isnull=True)
            | Q(
                site_visit__isnull=False,
                inspection__company_id=F("company_id"),
                inspection__site_id=F("site_id"),
                inspection__site_visit_id=F("site_visit_id"),
                inspection__site__company_id=F("company_id"),
                inspection__site__client_id=F("client_id"),
                inspection__site__contract_id=F("contract_id"),
            )
        )
        .filter(
            Q(inspection__isnull=True)
            | Q(inspection__post__isnull=True)
            | Q(
                inspection__post__company_id=F("company_id"),
                inspection__post__client_id=F("client_id"),
                inspection__post__site_id=F("site_id"),
            )
        )
        .filter(
            Q(inspection__isnull=True)
            | Q(inspection__inspected_employee__isnull=True)
            | Q(inspection__inspected_employee__company_id=F("company_id"))
        )
        .filter(
            Q(inspection__isnull=True)
            | Q(inspection__template__company__isnull=True)
            | Q(inspection__template__company_id=F("company_id"))
        )
        .filter(
            Q(patrol_task__isnull=True)
            | Q(
                patrol_task__company_id=F("company_id"),
                patrol_task__branch_id=F("branch_id"),
                patrol_task__site_id=F("site_id"),
                patrol_task__client_id=F("client_id"),
                patrol_task__patrol_route__company_id=F("company_id"),
                patrol_task__patrol_route__client_id=F("client_id"),
                patrol_task__patrol_route__site_id=F("site_id"),
                patrol_task__route_version__patrol_route_id=F("patrol_task__patrol_route_id"),
            )
        )
        .filter(
            Q(patrol_task__isnull=True)
            | Q(patrol_task__patrol_requirement__isnull=True)
            | Q(
                patrol_task__patrol_requirement__company_id=F("company_id"),
                patrol_task__patrol_requirement__branch_id=F("branch_id"),
                patrol_task__patrol_requirement__client_id=F("client_id"),
                patrol_task__patrol_requirement__site_id=F("site_id"),
                patrol_task__patrol_requirement__patrol_route_id=F("patrol_task__patrol_route_id"),
            )
        )
        .filter(
            Q(patrol_task__isnull=True)
            | Q(patrol_task__assigned_employee__isnull=True)
            | Q(patrol_task__assigned_employee__company_id=F("company_id"))
        )
        .filter(
            Q(patrol_task__isnull=True)
            | Q(patrol_task__supervisor__isnull=True)
            | Q(patrol_task__supervisor__company_id=F("company_id"))
        )
        .filter(
            Q(patrol_task__isnull=True)
            | Q(patrol_task__duty_assignment__isnull=True)
            | Q(
                patrol_task__duty_assignment__duty_shift__company_id=F("company_id"),
                patrol_task__duty_assignment__duty_shift__branch_id=F("branch_id"),
                patrol_task__duty_assignment__duty_shift__site_id=F("site_id"),
            )
        )
        .filter(
            Q(patrol_task__isnull=True)
            | Q(patrol_task__duty_assignment__isnull=True)
            | Q(patrol_task__assigned_employee__isnull=True)
            | Q(patrol_task__duty_assignment__employee_id=F("patrol_task__assigned_employee_id"))
        )
        .filter(
            Q(patrol_run__isnull=True)
            | Q(
                patrol_task__isnull=False,
                patrol_run__company_id=F("company_id"),
                patrol_run__site_id=F("site_id"),
                patrol_run__patrol_task_id=F("patrol_task_id"),
                patrol_run__employee__company_id=F("company_id"),
                patrol_run__employee_id=F("patrol_task__assigned_employee_id"),
                patrol_run__route_version_id=F("patrol_task__route_version_id"),
            )
        )
        .filter(
            Q(patrol_run__isnull=True)
            | Q(patrol_run__duty_assignment__isnull=True)
            | Q(
                patrol_run__duty_assignment__employee_id=F("patrol_run__employee_id"),
                patrol_run__duty_assignment_id=F("patrol_task__duty_assignment_id"),
            )
        )
        .filter(
            Q(checkpoint_visit__isnull=True)
            | Q(
                patrol_run__isnull=False,
                checkpoint_visit__patrol_run_id=F("patrol_run_id"),
                checkpoint_visit__patrol_run__company_id=F("company_id"),
                checkpoint_visit__patrol_event__patrol_run_id=F("patrol_run_id"),
                checkpoint_visit__route_checkpoint__route_version_id=F(
                    "patrol_run__route_version_id"
                ),
                checkpoint_visit__checkpoint_id=F(
                    "checkpoint_visit__route_checkpoint__checkpoint_id"
                ),
                checkpoint_visit__checkpoint__company_id=F("company_id"),
                checkpoint_visit__checkpoint__client_id=F("client_id"),
                checkpoint_visit__checkpoint__site_id=F("site_id"),
            )
        )
        .filter(
            Q(patrol_observation__isnull=True)
            | Q(
                patrol_run__isnull=False,
                patrol_observation__company_id=F("company_id"),
                patrol_observation__patrol_run_id=F("patrol_run_id"),
                patrol_observation__site_id=F("site_id"),
            )
        )
        .filter(
            Q(patrol_observation__isnull=True)
            | Q(patrol_observation__checkpoint_visit__isnull=True)
            | Q(patrol_observation__checkpoint_visit__patrol_run_id=F("patrol_run_id"))
        )
        .filter(
            Q(patrol_observation__isnull=True)
            | Q(patrol_observation__checkpoint__isnull=True)
            | Q(
                patrol_observation__checkpoint__company_id=F("company_id"),
                patrol_observation__checkpoint__client_id=F("client_id"),
                patrol_observation__checkpoint__site_id=F("site_id"),
            )
        )
        .filter(
            Q(patrol_observation__isnull=True)
            | Q(patrol_observation__post__isnull=True)
            | Q(
                patrol_observation__post__company_id=F("company_id"),
                patrol_observation__post__client_id=F("client_id"),
                patrol_observation__post__site_id=F("site_id"),
            )
        )
        .filter(
            Q(patrol_exception__isnull=True)
            | Q(
                patrol_task__isnull=False,
                patrol_exception__company_id=F("company_id"),
                patrol_exception__patrol_task_id=F("patrol_task_id"),
            )
        )
        .filter(
            Q(patrol_exception__isnull=True)
            | Q(patrol_exception__patrol_run__isnull=True)
            | Q(
                patrol_run__isnull=False,
                patrol_exception__patrol_run_id=F("patrol_run_id"),
                patrol_exception__patrol_run__patrol_task_id=F("patrol_task_id"),
            )
        )
        .filter(
            Q(patrol_exception__isnull=True)
            | Q(patrol_exception__checkpoint_visit__isnull=True)
            | Q(
                checkpoint_visit__isnull=False,
                patrol_exception__checkpoint_visit_id=F("checkpoint_visit_id"),
                patrol_exception__checkpoint_visit__patrol_run_id=F("patrol_run_id"),
            )
        )
        .filter(
            Q(supervision_finding__isnull=True)
            | Q(
                inspection__isnull=False,
                supervision_finding__company_id=F("company_id"),
                supervision_finding__inspection_id=F("inspection_id"),
                supervision_finding__site_id=F("site_id"),
            )
        )
        .filter(
            Q(supervision_finding__isnull=True)
            | Q(supervision_finding__post__isnull=True)
            | Q(
                supervision_finding__post__company_id=F("company_id"),
                supervision_finding__post__client_id=F("client_id"),
                supervision_finding__post__site_id=F("site_id"),
            )
        )
        .filter(
            Q(supervision_finding__isnull=True)
            | Q(supervision_finding__employee__isnull=True)
            | Q(supervision_finding__employee__company_id=F("company_id"))
        )
    )


def consistent_sos_alerts(queryset: QuerySet[models.SOSAlert]) -> QuerySet[models.SOSAlert]:
    return (
        queryset.filter(company__is_active=True)
        .filter(employee__company_id=F("company_id"))
        .filter(Q(employee__branch__isnull=True) | Q(employee__branch__company_id=F("company_id")))
        .filter(
            Q(duty_assignment__isnull=True)
            | Q(
                duty_assignment__employee_id=F("employee_id"),
                duty_assignment__duty_shift__company_id=F("company_id"),
                duty_assignment__employee__company_id=F("company_id"),
            )
        )
        .filter(
            Q(attendance_record__isnull=True)
            | Q(
                duty_assignment__isnull=False,
                attendance_record__duty_assignment_id=F("duty_assignment_id"),
                attendance_record__employee_id=F("employee_id"),
                attendance_record__company_id=F("company_id"),
            )
        )
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
        .filter(
            Q(duty_assignment__isnull=True) | Q(site_id=F("duty_assignment__duty_shift__site_id"))
        )
        .filter(
            Q(post__isnull=True)
            | Q(site__isnull=False, post__company_id=F("company_id"), post__site_id=F("site_id"))
        )
        .filter(
            Q(duty_assignment__isnull=True) | Q(post_id=F("duty_assignment__duty_shift__post_id"))
        )
        .filter(
            Q(patrol_run__isnull=True)
            | Q(
                patrol_run__company_id=F("company_id"),
                patrol_run__employee_id=F("employee_id"),
                patrol_run__site_id=F("site_id"),
                patrol_run__patrol_task__company_id=F("company_id"),
            )
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(linked_incident__in=consistent_incidents(models.Incident.objects.all()))
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(
                linked_incident__company_id=F("company_id"),
                linked_incident__reporter_employee_id=F("employee_id"),
            )
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(duty_assignment__isnull=True, linked_incident__duty_assignment__isnull=True)
            | Q(linked_incident__duty_assignment_id=F("duty_assignment_id"))
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(attendance_record__isnull=True, linked_incident__attendance_record__isnull=True)
            | Q(linked_incident__attendance_record_id=F("attendance_record_id"))
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(site__isnull=True, linked_incident__site__isnull=True)
            | Q(linked_incident__site_id=F("site_id"))
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(post__isnull=True, linked_incident__post__isnull=True)
            | Q(linked_incident__post_id=F("post_id"))
        )
        .filter(
            Q(linked_incident__isnull=True)
            | Q(patrol_run__isnull=True, linked_incident__patrol_run__isnull=True)
            | Q(linked_incident__patrol_run_id=F("patrol_run_id"))
        )
    )


def consistent_events(queryset):
    return (
        queryset.filter(incident__in=consistent_incidents(models.Incident.objects.all()))
        .filter(
            Q(actor_employee__isnull=True)
            | Q(actor_employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(
            Q(actor_employee__isnull=True) | Q(actor_employee__company_id=F("incident__company_id"))
        )
    )


def consistent_location_snapshots(queryset):
    return (
        queryset.filter(incident__in=consistent_incidents(models.Incident.objects.all()))
        .filter(
            Q(employee__isnull=True) | Q(employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(Q(employee__isnull=True) | Q(employee__company_id=F("incident__company_id")))
    )


def consistent_participants(queryset):
    return (
        queryset.filter(incident__in=consistent_incidents(models.Incident.objects.all()))
        .filter(
            Q(employee__isnull=True) | Q(employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(Q(employee__isnull=True) | Q(employee__company_id=F("incident__company_id")))
        .filter(
            Q(client_contact__isnull=True)
            | Q(client_contact__in=ClientContact.objects.filter(is_active=True))
        )
        .filter(
            Q(client_contact__isnull=True) | Q(client_contact__client_id=F("incident__client_id"))
        )
    )


def consistent_evidence(queryset):
    return queryset.filter(
        incident__in=consistent_incidents(models.Incident.objects.all()),
        company_id=F("incident__company_id"),
    )


def consistent_evidence_events(queryset):
    return queryset.filter(evidence__in=consistent_evidence(models.IncidentEvidence.objects.all()))


def _incident_child(queryset):
    return queryset.filter(incident__in=consistent_incidents(models.Incident.objects.all()))


def consistent_responders(queryset):
    return (
        _incident_child(queryset)
        .filter(
            Q(employee__isnull=True) | Q(employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(Q(employee__isnull=True) | Q(employee__company_id=F("incident__company_id")))
    )


def consistent_actions(queryset):
    return (
        _incident_child(queryset)
        .filter(
            Q(assigned_to_employee__isnull=True)
            | Q(assigned_to_employee__in=consistent_employees(Employee.objects.all()))
        )
        .filter(
            Q(assigned_to_employee__isnull=True)
            | Q(assigned_to_employee__company_id=F("incident__company_id"))
        )
    )


def consistent_escalation_policies(queryset):
    return (
        queryset.filter(company__is_active=True)
        .filter(
            Q(incident_type__isnull=True)
            | Q(incident_type__company__isnull=True)
            | Q(incident_type__company_id=F("company_id"))
        )
        .filter(Q(site__isnull=True) | Q(site__in=consistent_sites(SecuritySite.objects.all())))
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
    )


def consistent_escalations(
    queryset: QuerySet[models.IncidentEscalation],
) -> QuerySet[models.IncidentEscalation]:
    return (
        _incident_child(queryset)
        .filter(
            Q(policy__isnull=True)
            | Q(
                policy__in=consistent_escalation_policies(
                    models.IncidentEscalationPolicy.objects.all()
                )
            )
        )
        .filter(Q(policy__isnull=True) | Q(policy__company_id=F("incident__company_id")))
    )


def consistent_client_notifications(queryset):
    return _incident_child(queryset).filter(
        Q(client_contact__isnull=True) | Q(client_contact__client_id=F("incident__client_id"))
    )


def consistent_reviews(queryset):
    return _incident_child(queryset)


def consistent_recommendations(queryset):
    return queryset.filter(review__incident__in=consistent_incidents(models.Incident.objects.all()))


CONSISTENCY_FILTERS = {
    models.IncidentType: consistent_incident_types,
    models.Incident: consistent_incidents,
    models.SOSAlert: consistent_sos_alerts,
    models.IncidentEvent: consistent_events,
    models.IncidentLocationSnapshot: consistent_location_snapshots,
    models.IncidentParticipant: consistent_participants,
    models.IncidentEvidence: consistent_evidence,
    models.IncidentEvidenceEvent: consistent_evidence_events,
    models.IncidentResponder: consistent_responders,
    models.IncidentAction: consistent_actions,
    models.IncidentEscalationPolicy: consistent_escalation_policies,
    models.IncidentEscalation: consistent_escalations,
    models.ExternalContactAttempt: _incident_child,
    models.ClientNotificationRecord: consistent_client_notifications,
    models.ManagementNotificationRecord: _incident_child,
    models.IncidentImpact: _incident_child,
    models.PostIncidentReview: consistent_reviews,
    models.ReviewRecommendation: consistent_recommendations,
    models.IncidentException: _incident_child,
}


def consistent_queryset(queryset: QuerySet) -> QuerySet:
    return CONSISTENCY_FILTERS[queryset.model](queryset)


def scoped_incidents(queryset: QuerySet[models.Incident], *, user, permission: str):
    queryset = consistent_incidents(queryset).order_by("pk")
    if user.is_superuser:
        return queryset
    return queryset.filter(
        branch_id__in=access.get_accessible_branch_ids(user, permission=permission)
    )


def user_belongs_to_company(user, company) -> bool:
    return bool(
        user
        and user.is_active
        and (user.is_superuser or company.id in access.get_accessible_company_ids(user))
    )


def _is_consistent(instance, filterer) -> bool:
    return (
        instance is None or filterer(type(instance).objects.all()).filter(pk=instance.pk).exists()
    )


def incident_graph_errors(*, company, branch, incident_type, context) -> dict[str, str]:
    """Validate a complete prospective Incident graph without persisting it."""
    errors: dict[str, str] = {}
    if not company.is_active:
        errors["company"] = "An active Company is required."
    if branch.company_id != company.id:
        errors["branch"] = "Branch belongs to another Company."
    if not incident_type.is_active:
        errors["incident_type"] = "Inactive Incident Types cannot be used."
    elif incident_type.company_id not in {None, company.id}:
        errors["incident_type"] = "Incident Type belongs to another Company."

    zone = context.get("operational_zone")
    if zone is not None and (zone.company_id != company.id or zone.branch_id != branch.id):
        errors["operational_zone"] = "Operational Zone does not match Company and Branch."

    client = context.get("client")
    contract = context.get("contract")
    site = context.get("site")
    post = context.get("post")
    employee = context.get("reporter_employee")
    duty = context.get("duty_assignment")
    attendance = context.get("attendance_record")
    deployment = context.get("employee_deployment")
    visit = context.get("site_visit")
    inspection = context.get("inspection")
    patrol_task = context.get("patrol_task")
    patrol_run = context.get("patrol_run")
    checkpoint_visit = context.get("checkpoint_visit")
    observation = context.get("patrol_observation")
    patrol_exception = context.get("patrol_exception")
    finding = context.get("supervision_finding")

    if client is not None and client.company_id != company.id:
        errors["client"] = "Client belongs to another Company."
    if contract is not None and (
        contract.company_id != company.id or client is None or contract.client_id != client.id
    ):
        errors["contract"] = "Contract does not match Company and Client."
    if site is not None and (
        not _is_consistent(site, consistent_sites)
        or site.company_id != company.id
        or client is None
        or site.client_id != client.id
        or contract is None
        or site.contract_id != contract.id
        or site.managing_branch_id != branch.id
    ):
        errors["site"] = "Site does not match Company, Client, Contract and Branch."
    if post is not None and (
        not _is_consistent(post, consistent_posts)
        or site is None
        or post.company_id != company.id
        or post.client_id != getattr(client, "id", None)
        or post.site_id != site.id
    ):
        errors["post"] = "Post does not match the Incident Site."
    if employee is not None and (
        not _is_consistent(employee, consistent_employees) or employee.company_id != company.id
    ):
        errors["reporter_employee"] = "Reporter Employee belongs to another Company."

    if duty is not None and (
        not _is_consistent(duty, consistent_duty_assignments)
        or duty.duty_shift.company_id != company.id
        or duty.duty_shift.branch_id != branch.id
        or duty.duty_shift.site_id != getattr(site, "id", None)
        or duty.duty_shift.post_id != getattr(post, "id", None)
        or (employee is not None and duty.employee_id != employee.id)
    ):
        errors["duty_assignment"] = "Duty Assignment does not match the Incident context."
    if attendance is not None and (
        not _is_consistent(attendance, consistent_attendance_records)
        or duty is None
        or attendance.duty_assignment_id != duty.id
        or attendance.company_id != company.id
        or attendance.branch_id != branch.id
        or attendance.client_id != getattr(client, "id", None)
        or attendance.site_id != getattr(site, "id", None)
        or attendance.post_id != getattr(post, "id", None)
    ):
        errors["attendance_record"] = "Attendance Record does not match the Incident context."
    if deployment is not None and (
        not _is_consistent(deployment, consistent_employee_deployments)
        or deployment.company_id != company.id
        or deployment.client_id != getattr(client, "id", None)
        or deployment.contract_id != getattr(contract, "id", None)
        or deployment.site_id != getattr(site, "id", None)
        or deployment.managing_branch_id != branch.id
        or (employee is not None and deployment.employee_id != employee.id)
    ):
        errors["employee_deployment"] = "Employee Deployment does not match the Incident context."
    if visit is not None and (
        not _is_consistent(visit, consistent_site_visits)
        or visit.company_id != company.id
        or visit.branch_id != branch.id
        or visit.site_id != getattr(site, "id", None)
    ):
        errors["site_visit"] = "Site Visit does not match the Incident context."
    if inspection is not None and (
        not _is_consistent(inspection, consistent_inspections)
        or visit is None
        or inspection.company_id != company.id
        or inspection.site_id != getattr(site, "id", None)
        or inspection.site_visit_id != visit.id
    ):
        errors["inspection"] = "Inspection does not match the Incident context."
    if patrol_task is not None and (
        not _is_consistent(patrol_task, consistent_patrol_tasks)
        or patrol_task.company_id != company.id
        or patrol_task.branch_id != branch.id
        or patrol_task.site_id != getattr(site, "id", None)
    ):
        errors["patrol_task"] = "Patrol Task does not match the Incident context."
    if patrol_run is not None and (
        not _is_consistent(patrol_run, consistent_patrol_runs)
        or patrol_task is None
        or patrol_run.company_id != company.id
        or patrol_run.site_id != getattr(site, "id", None)
        or patrol_run.patrol_task_id != patrol_task.id
    ):
        errors["patrol_run"] = "Patrol Run does not match the Incident context."
    if checkpoint_visit is not None and (
        not _is_consistent(checkpoint_visit, consistent_checkpoint_visits)
        or patrol_run is None
        or checkpoint_visit.patrol_run_id != patrol_run.id
    ):
        errors["checkpoint_visit"] = "Checkpoint Visit does not match the Patrol Run."
    if observation is not None and (
        not _is_consistent(observation, consistent_patrol_observations)
        or patrol_run is None
        or observation.company_id != company.id
        or observation.patrol_run_id != patrol_run.id
        or observation.site_id != getattr(site, "id", None)
    ):
        errors["patrol_observation"] = "Patrol Observation does not match the Incident context."
    if patrol_exception is not None and (
        not _is_consistent(patrol_exception, consistent_patrol_exceptions)
        or patrol_task is None
        or patrol_exception.company_id != company.id
        or patrol_exception.patrol_task_id != patrol_task.id
    ):
        errors["patrol_exception"] = "Patrol Exception does not match the Incident context."
    if finding is not None and (
        not _is_consistent(finding, consistent_findings)
        or inspection is None
        or finding.company_id != company.id
        or finding.inspection_id != inspection.id
        or finding.site_id != getattr(site, "id", None)
    ):
        errors["supervision_finding"] = "Supervision Finding does not match the Incident context."
    return errors
