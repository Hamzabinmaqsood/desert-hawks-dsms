# mypy: disable-error-code="no-untyped-def,no-untyped-call"
import logging
from decimal import Decimal

from django.db import IntegrityError, models, transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from dsms.attendance.models import AttendanceRecord
from dsms.attendance.tenant_queries import consistent_attendance_records
from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.deployment.models import DutyAssignment
from dsms.deployment.tenant_queries import (
    consistent_duty_assignments,
    consistent_employees,
)
from dsms.identity import access
from dsms.notifications.services import publish_notification_event
from dsms.patrol.models import PatrolException, PatrolObservation, PatrolRun
from dsms.patrol.tenant_queries import (
    consistent_exceptions,
    consistent_observations,
    consistent_runs,
)

from .exceptions import IncidentPermissionError, IncidentValidationError
from .models import (
    Incident,
    IncidentAction,
    IncidentEscalation,
    IncidentEscalationPolicy,
    IncidentEvent,
    IncidentLocationSnapshot,
    IncidentResponder,
    IncidentType,
    SOSAlert,
)
from .tenant_queries import (
    consistent_escalation_policies,
    consistent_incidents,
    consistent_sos_alerts,
    incident_graph_errors,
    user_belongs_to_company,
)

logger = logging.getLogger(__name__)


def _publish_safely(**kwargs):
    """Notification orchestration must never roll back the operational fact."""
    try:
        return publish_notification_event(**kwargs)
    except Exception:
        logger.exception("Incident notification publication failed after business persistence.")
        return None


def _number(prefix):
    # UUID-derived numbering is collision-safe without COUNT(*) and remains human searchable.
    from uuid import uuid4

    return f"{prefix}-{timezone.now():%Y}-{uuid4().hex[:12].upper()}"


def _event(incident, kind, actor, title, *, previous="", new="", description=""):
    event = IncidentEvent.objects.create(
        incident=incident,
        event_type=kind,
        actor_user=actor,
        event_time=timezone.now(),
        title=title,
        description=description,
        previous_status=previous,
        new_status=new,
    )
    record_audit_event(
        action=f"INCIDENT_{kind}",
        category=AuditCategory.INCIDENT,
        severity=AuditSeverity.CRITICAL if incident.severity == "CRITICAL" else AuditSeverity.HIGH,
        summary=title,
        actor_user=actor,
        company=incident.company,
        branch=incident.branch,
        source_object=incident,
        object_reference=incident.incident_number,
        metadata_safe={"previous_status": previous, "new_status": new},
    )
    return event


def _require_permission(*, actor, permission, company, branch, operational_zone=None):
    if not access.has_permission(
        user=actor,
        permission=permission,
        company=company,
        branch=branch,
        operational_zone=operational_zone,
    ):
        raise IncidentPermissionError(f"{permission} permission is required in the target scope.")


def _locked_incident(pk):
    item = (
        consistent_incidents(Incident.objects.select_for_update(of=("self",)))
        .select_related("company", "branch", "operational_zone", "site", "incident_type")
        .filter(pk=pk)
        .first()
    )
    if item is None:
        raise IncidentValidationError("Incident has an invalid tenant graph.")
    return item


def _locked_sos(pk):
    item = (
        consistent_sos_alerts(SOSAlert.objects.select_for_update(of=("self",)))
        .select_related("company", "employee__branch", "linked_incident")
        .filter(pk=pk)
        .first()
    )
    if item is None:
        raise IncidentValidationError("SOS has an invalid tenant graph.")
    return item


@transaction.atomic
def create_incident(
    *,
    actor,
    company,
    branch,
    incident_type,
    title,
    description,
    source="OTHER",
    authorized_source=False,
    **context,
):
    site = context.get("site")
    if site is not None:
        context.setdefault("client", site.client)
        context.setdefault("contract", site.contract)
    errors = incident_graph_errors(
        company=company, branch=branch, incident_type=incident_type, context=context
    )
    if errors:
        raise IncidentValidationError("; ".join(errors.values()))
    if not authorized_source:
        source = "OTHER"
        _require_permission(
            actor=actor,
            permission="incidents.report_incident",
            company=company,
            branch=branch,
            operational_zone=context.get("operational_zone"),
        )
    incident = Incident.objects.create(
        incident_number=_number("INC"),
        company=company,
        branch=branch,
        incident_type=incident_type,
        severity=incident_type.default_severity,
        priority=incident_type.default_priority,
        source=source,
        title=title,
        description=description,
        reported_at=timezone.now(),
        created_by=actor,
        reporter_user=actor,
        client_notification_required=incident_type.requires_client_notification,
        management_notification_required=incident_type.requires_management_notification,
        post_incident_review_required=incident_type.requires_post_incident_review,
        **context,
    )
    _event(incident, "CREATED", actor, "Incident reported")
    _publish_safely(
        event_key=f"incidents.created:{incident.id}",
        event_type="INCIDENT_CREATED",
        source_app="incidents",
        source_model="Incident",
        source_object_id=incident.id,
        company=incident.company,
        safe_payload={
            "incident_number": incident.incident_number,
            "site_name": getattr(incident.site, "name", "Unresolved site"),
            "severity": incident.severity,
            "message": "A new incident has been recorded.",
        },
    )
    if incident.severity == "CRITICAL":
        _publish_safely(
            event_key=f"incidents.critical.created:{incident.id}",
            event_type="CRITICAL_INCIDENT_CREATED",
            source_app="incidents",
            source_model="Incident",
            source_object_id=incident.id,
            company=incident.company,
            safe_payload={
                "incident_number": incident.incident_number,
                "site_name": getattr(incident.site, "name", "Unresolved site"),
                "message": "A critical incident requires command-center attention.",
                "actor_user_id": str(actor.id),
            },
        )
    return incident


@transaction.atomic
def trigger_sos(
    *, actor, employee, client_event_id, location=None, message=None, device_metadata=None
):
    if not actor or not actor.is_authenticated:
        raise IncidentPermissionError("Authentication is required.")
    employee = (
        consistent_employees(
            type(employee)
            .objects.select_related("company", "branch", "user")
            .filter(company__is_active=True)
        )
        .filter(pk=employee.pk)
        .first()
    )
    if employee is None:
        raise IncidentValidationError("Employee has an invalid tenant graph.")
    is_self = employee.user_id == actor.id
    self_allowed = is_self and access.has_permission(
        user=actor,
        permission="incidents.trigger_own_sos",
        company=employee.company,
        branch=employee.branch,
    )
    manager_allowed = access.has_permission(
        user=actor,
        permission="incidents.manage_incident",
        company=employee.company,
        branch=employee.branch,
    )
    if not self_allowed and not manager_allowed:
        raise IncidentPermissionError("SOS trigger permission is required.")
    raw_existing = (
        SOSAlert.objects.select_related("linked_incident")
        .filter(company=employee.company, client_event_id=client_event_id)
        .first()
    )
    existing = (
        consistent_sos_alerts(SOSAlert.objects.select_related("linked_incident"))
        .filter(company=employee.company, client_event_id=client_event_id)
        .first()
    )
    if raw_existing is not None and existing is None:
        raise IncidentValidationError("The existing SOS idempotency record is inconsistent.")
    if existing:
        if existing.employee_id != employee.id or existing.user_id != actor.id:
            raise IncidentPermissionError(
                "The SOS idempotency key belongs to another logical operation."
            ) from None
        return existing
    if location:
        latitude = Decimal(str(location["latitude"]))
        longitude = Decimal(str(location["longitude"]))
        if not Decimal("-90") <= latitude <= Decimal("90"):
            raise IncidentValidationError("Latitude is outside the valid range.")
        if not Decimal("-180") <= longitude <= Decimal("180"):
            raise IncidentValidationError("Longitude is outside the valid range.")
    now = timezone.now()
    duty = (
        consistent_duty_assignments(
            DutyAssignment.objects.filter(
                employee=employee, status__in=["PLANNED", "CONFIRMED"]
            ).select_related(
                "duty_shift__site__client",
                "duty_shift__site__contract",
                "duty_shift__post",
                "duty_shift__branch",
            )
        )
        .order_by("-assigned_at")
        .first()
    )
    attendance = (
        consistent_attendance_records(
            AttendanceRecord.objects.filter(duty_assignment=duty, actual_check_out_at__isnull=True)
        )
        .order_by("-actual_check_in_at")
        .first()
        if duty
        else None
    )
    patrol = (
        consistent_runs(PatrolRun.objects.filter(employee=employee, status="IN_PROGRESS"))
        .order_by("-started_at")
        .first()
    )
    try:
        sos = SOSAlert.objects.create(
            sos_number=_number("SOS"),
            company=employee.company,
            employee=employee,
            user=actor,
            duty_assignment=duty,
            attendance_record=attendance,
            site=duty.duty_shift.site if duty else getattr(patrol, "site", None),
            post=duty.duty_shift.post if duty else None,
            patrol_run=patrol,
            triggered_at=now,
            client_event_id=client_event_id,
            latitude=latitude if location else None,
            longitude=longitude if location else None,
            accuracy_meters=location.get("accuracy_meters") if location else None,
            message=message or "",
        )
    except IntegrityError:
        existing = consistent_sos_alerts(SOSAlert.objects.select_related("linked_incident")).get(
            company=employee.company, client_event_id=client_event_id
        )
        if existing.employee_id != employee.id or existing.user_id != actor.id:
            raise IncidentPermissionError(
                "The SOS idempotency key belongs to another logical operation."
            ) from None
        return existing
    create_incident_from_sos(sos=sos, actor=actor)
    sos.refresh_from_db()
    record_audit_event(
        action="SOS_TRIGGERED",
        category=AuditCategory.INCIDENT,
        severity=AuditSeverity.CRITICAL,
        summary="SOS alert triggered.",
        actor_user=actor,
        actor_employee=employee,
        company=sos.company,
        branch=employee.branch,
        source_object=sos,
        object_reference=sos.sos_number,
    )
    _publish_safely(
        event_key=f"incidents.sos.triggered:{sos.id}",
        event_type="SOS_TRIGGERED",
        source_app="incidents",
        source_model="SOSAlert",
        source_object_id=sos.id,
        company=sos.company,
        safe_payload={
            "sos_number": sos.sos_number,
            "site_name": getattr(sos.site, "name", "Unresolved site"),
            "message": "An SOS alert requires immediate command-center attention.",
            "actor_user_id": str(actor.id),
        },
    )
    return sos


def _sos_type(company):
    incident_type = (
        IncidentType.objects.filter(code="SOS_EMERGENCY", is_active=True)
        .filter(models.Q(company=company) | models.Q(company__isnull=True))
        .order_by("company_id")
        .first()
    )
    if not incident_type:
        incident_type = IncidentType.objects.create(
            company=company,
            code="SOS_EMERGENCY",
            name="SOS / Panic Alert",
            default_severity="CRITICAL",
            default_priority="EMERGENCY",
            requires_immediate_acknowledgement=True,
            requires_management_notification=True,
            requires_post_incident_review=True,
        )
    return incident_type


@transaction.atomic
def create_incident_from_sos(*, sos, actor):
    sos = (
        consistent_sos_alerts(SOSAlert.objects.select_for_update(of=("self",)))
        .select_related(
            "employee__branch",
            "company",
            "site__client",
            "site__contract",
            "duty_assignment__duty_shift__branch",
        )
        .filter(pk=sos.pk)
        .first()
    )
    if sos is None:
        raise IncidentValidationError("SOS has an invalid tenant graph.")
    if sos.employee.user_id != actor.id and not access.has_permission(
        user=actor,
        permission="incidents.manage_incident",
        company=sos.company,
        branch=sos.employee.branch,
    ):
        raise IncidentPermissionError("SOS management permission is required.")
    if sos.linked_incident_id:
        linked = (
            consistent_incidents(Incident.objects.all()).filter(pk=sos.linked_incident_id).first()
        )
        if linked is None:
            raise IncidentValidationError("The linked Incident has an invalid tenant graph.")
        return linked
    branch = (
        sos.duty_assignment.duty_shift.branch if sos.duty_assignment_id else sos.employee.branch
    )
    incident = create_incident(
        actor=actor,
        company=sos.company,
        branch=branch,
        incident_type=_sos_type(sos.company),
        title="SOS / panic alert",
        description=sos.message or "Emergency SOS triggered",
        source="GUARD",
        reporter_employee=sos.employee,
        site=sos.site,
        post=sos.post,
        duty_assignment=sos.duty_assignment,
        attendance_record=sos.attendance_record,
        patrol_run=sos.patrol_run,
        patrol_task=sos.patrol_run.patrol_task if sos.patrol_run_id else None,
        client=sos.site.client if sos.site_id else None,
        contract=sos.site.contract if sos.site_id else None,
        authorized_source=True,
    )
    sos.linked_incident = incident
    sos.status = "LINKED_TO_INCIDENT"
    sos.save(update_fields=["linked_incident", "status"])
    _event(
        incident,
        "SOS_TRIGGERED",
        actor,
        "SOS triggered",
        description="SOS evidence recorded; external dispatch is not implied.",
    )
    if sos.latitude is not None and sos.longitude is not None:
        IncidentLocationSnapshot.objects.create(
            incident=incident,
            source="SOS",
            latitude=sos.latitude,
            longitude=sos.longitude,
            accuracy_meters=sos.accuracy_meters,
            captured_at=sos.triggered_at,
            employee=sos.employee,
            actor_user=actor,
        )
    return incident


@transaction.atomic
def acknowledge_sos(*, sos: SOSAlert, actor):
    item = _locked_sos(sos.pk)
    _require_permission(
        actor=actor,
        permission="incidents.acknowledge_incident",
        company=item.company,
        branch=item.employee.branch,
    )
    if item.status not in {"TRIGGERED", "LINKED_TO_INCIDENT", "ACKNOWLEDGED"}:
        raise IncidentValidationError("SOS is not active.")
    if item.acknowledged_at is None:
        item.acknowledged_by, item.acknowledged_at = actor, timezone.now()
    item.status = "ACKNOWLEDGED"
    item.save(update_fields=["acknowledged_by", "acknowledged_at", "status"])
    if item.linked_incident_id:
        incident = _locked_incident(item.linked_incident_id)
        if incident.status == "NEW":
            transition_incident(incident=incident, actor=actor, new_status="ACKNOWLEDGED")
    record_audit_event(
        action="SOS_ACKNOWLEDGED",
        category=AuditCategory.INCIDENT,
        severity=AuditSeverity.CRITICAL,
        summary="SOS acknowledged.",
        actor_user=actor,
        company=item.company,
        branch=item.employee.branch,
        source_object=item,
        object_reference=item.sos_number,
    )
    _publish_safely(
        event_key=f"incidents.sos.acknowledged:{item.id}",
        event_type="SOS_ACKNOWLEDGED",
        source_app="incidents",
        source_model="SOSAlert",
        source_object_id=item.id,
        company=item.company,
        safe_payload={
            "sos_number": item.sos_number,
            "site_name": getattr(item.site, "name", "Unresolved site"),
            "message": "The SOS alert has been acknowledged.",
        },
    )
    return item


@transaction.atomic
def resolve_sos(*, sos: SOSAlert, actor, reason: str):
    item = _locked_sos(sos.pk)
    _require_permission(
        actor=actor,
        permission="incidents.resolve_incident",
        company=item.company,
        branch=item.employee.branch,
    )
    if item.status in {"CLOSED", "CANCELLED_BY_REPORTER", "FALSE_ALARM_CONFIRMED"}:
        raise IncidentValidationError("SOS is already terminal.")
    if item.linked_incident_id:
        incident = (
            consistent_incidents(Incident.objects.all()).filter(pk=item.linked_incident_id).first()
        )
        if incident is None:
            raise IncidentValidationError("The linked Incident has an invalid tenant graph.")
        if incident.status not in {"RESOLVED", "CLOSED"}:
            raise IncidentValidationError("Resolve the linked incident before closing the SOS.")
    item.status = "CLOSED"
    item.save(update_fields=["status"])
    record_audit_event(
        action="SOS_RESOLVED",
        category=AuditCategory.INCIDENT,
        severity=AuditSeverity.HIGH,
        summary="SOS closed after human resolution.",
        actor_user=actor,
        company=item.company,
        branch=item.employee.branch,
        source_object=item,
        object_reference=item.sos_number,
        metadata_safe={"reason": reason},
    )
    return item


@transaction.atomic
def assign_incident_responder(
    *, incident: Incident, actor, employee=None, user=None, responder_role="OTHER"
) -> IncidentResponder:
    obj = _locked_incident(incident.pk)
    _require_permission(
        actor=actor,
        permission="incidents.manage_responders",
        company=obj.company,
        branch=obj.branch,
        operational_zone=obj.operational_zone,
    )
    if obj.status in {"CLOSED", "CANCELLED"}:
        raise IncidentValidationError("A terminal incident cannot receive responders.")
    if employee is None and user is None:
        raise IncidentValidationError("A User or Employee responder is required.")
    if (
        employee is not None
        and not consistent_employees(type(employee).objects.filter(company=obj.company))
        .filter(pk=employee.pk)
        .exists()
    ):
        raise IncidentValidationError("Responder Employee belongs to another Company.")
    if user is not None and not user_belongs_to_company(user, obj.company):
        raise IncidentValidationError("Responder User does not belong to the Incident Company.")
    responder = IncidentResponder.objects.create(
        incident=obj,
        employee=employee,
        user=user,
        responder_role=responder_role,
        assigned_by=actor,
        assigned_at=timezone.now(),
    )
    _event(obj, "RESPONDER_ASSIGNED", actor, "Incident responder assigned")
    return responder


@transaction.atomic
def add_incident_action(
    *,
    incident: Incident,
    actor,
    title: str,
    description="",
    assigned_to_user=None,
    assigned_to_employee=None,
    priority="NORMAL",
):
    obj = _locked_incident(incident.pk)
    _require_permission(
        actor=actor,
        permission="incidents.manage_incident_actions",
        company=obj.company,
        branch=obj.branch,
        operational_zone=obj.operational_zone,
    )
    if (
        assigned_to_employee is not None
        and not consistent_employees(type(assigned_to_employee).objects.filter(company=obj.company))
        .filter(pk=assigned_to_employee.pk)
        .exists()
    ):
        raise IncidentValidationError("Assigned Employee belongs to another Company.")
    if assigned_to_user is not None and not user_belongs_to_company(assigned_to_user, obj.company):
        raise IncidentValidationError("Assigned User does not belong to the Incident Company.")
    number = (
        obj.actions.order_by("-action_number").values_list("action_number", flat=True).first() or 0
    ) + 1
    action = IncidentAction.objects.create(
        incident=obj,
        action_number=number,
        title=title,
        description=description,
        priority=priority,
        assigned_to_user=assigned_to_user,
        assigned_to_employee=assigned_to_employee,
        created_by=actor,
        assigned_at=timezone.now() if assigned_to_user or assigned_to_employee else None,
        status="ASSIGNED" if assigned_to_user or assigned_to_employee else "OPEN",
    )
    _event(obj, "ACTION_CREATED", actor, "Incident response action recorded")
    return action


@transaction.atomic
def escalate_incident(*, incident: Incident, actor, escalation_type="MANUAL", reason=""):
    obj = _locked_incident(incident.pk)
    _require_permission(
        actor=actor,
        permission="incidents.escalate_incident",
        company=obj.company,
        branch=obj.branch,
        operational_zone=obj.operational_zone,
    )
    escalation, _ = IncidentEscalation.objects.get_or_create(
        incident=obj,
        escalation_type=escalation_type,
        defaults={"triggered_at": timezone.now(), "actor": actor, "details": reason},
    )
    _event(obj, "ESCALATED", actor, "Incident escalated")
    _publish_safely(
        event_key=f"incidents.escalated:{obj.id}:{escalation_type}",
        event_type="INCIDENT_ESCALATED",
        source_app="incidents",
        source_model="Incident",
        source_object_id=obj.id,
        company=obj.company,
        safe_payload={
            "incident_number": obj.incident_number,
            "site_name": getattr(obj.site, "name", "Unresolved site"),
            "severity": obj.severity,
            "message": "An incident requires escalated command-center attention.",
        },
    )
    return escalation


def _referral_type(company):
    item, _ = IncidentType.objects.get_or_create(
        company=company,
        code="OPERATIONAL_REFERRAL",
        defaults={
            "name": "Operational referral",
            "default_severity": "MEDIUM",
            "default_priority": "NORMAL",
            "is_system": True,
        },
    )
    return item


@transaction.atomic
def refer_supervision_finding_to_incident(*, finding, actor, reason):
    from dsms.supervision.models import InspectionFinding
    from dsms.supervision.tenant_queries import consistent_findings

    finding = (
        consistent_findings(
            InspectionFinding.objects.select_related(
                "company",
                "site__managing_branch",
                "site__client",
                "site__contract",
                "post",
                "inspection__site_visit",
            )
        )
        .filter(pk=finding.pk)
        .first()
    )
    if finding is None:
        raise IncidentValidationError("Supervision finding is not tenant-consistent.")
    if not access.has_permission(
        user=actor,
        permission="supervision.change_inspectionfinding",
        company=finding.company,
        branch=finding.site.managing_branch,
    ):
        raise IncidentPermissionError("Supervision finding referral permission is required.")
    raw_existing = Incident.objects.filter(supervision_finding=finding).first()
    existing = (
        consistent_incidents(Incident.objects.all()).filter(supervision_finding=finding).first()
    )
    if raw_existing is not None and existing is None:
        raise IncidentValidationError("The existing referral Incident is tenant-inconsistent.")
    if existing is not None:
        return existing
    incident = create_incident(
        actor=actor,
        company=finding.company,
        branch=finding.site.managing_branch,
        incident_type=_referral_type(finding.company),
        title=f"Supervision referral: {finding.title}",
        description=reason,
        source="INSPECTION",
        client=finding.site.client,
        contract=finding.site.contract,
        site=finding.site,
        post=finding.post,
        inspection=finding.inspection,
        site_visit=finding.inspection.site_visit,
        supervision_finding=finding,
        authorized_source=True,
    )
    record_audit_event(
        action="SUPERVISION_FINDING_ESCALATED",
        category=AuditCategory.SUPERVISION,
        severity=AuditSeverity.HIGH,
        summary="Finding explicitly referred to Incident.",
        actor_user=actor,
        company=finding.company,
        branch=finding.site.managing_branch,
        source_object=finding,
        metadata_safe={"incident_number": incident.incident_number},
    )
    return incident


@transaction.atomic
def refer_patrol_exception_to_incident(*, exception, actor, reason):
    exception = (
        consistent_exceptions(
            PatrolException.objects.select_for_update(of=("self",)).select_related(
                "company",
                "patrol_task__branch",
                "patrol_task__site",
                "patrol_run",
                "checkpoint_visit",
            )
        )
        .filter(pk=exception.pk)
        .first()
    )
    if exception is None:
        raise IncidentValidationError("Patrol exception has an invalid tenant graph.")
    if not access.has_permission(
        user=actor,
        permission="patrol.resolve_patrol_exception",
        company=exception.company,
        branch=exception.patrol_task.branch,
    ):
        raise IncidentPermissionError("Patrol exception referral permission is required.")
    raw_existing = Incident.objects.filter(patrol_exception=exception).first()
    existing = (
        consistent_incidents(Incident.objects.all()).filter(patrol_exception=exception).first()
    )
    if raw_existing is not None and existing is None:
        raise IncidentValidationError("The existing referral Incident is tenant-inconsistent.")
    if existing is not None:
        return existing
    task = exception.patrol_task
    incident = create_incident(
        actor=actor,
        company=exception.company,
        branch=task.site.managing_branch,
        incident_type=_referral_type(exception.company),
        title="Patrol exception referral",
        description=reason,
        source="PATROL",
        client=task.site.client,
        contract=task.site.contract,
        site=task.site,
        patrol_task=task,
        patrol_run=exception.patrol_run,
        checkpoint_visit=exception.checkpoint_visit,
        patrol_exception=exception,
        authorized_source=True,
    )
    record_audit_event(
        action="PATROL_EXCEPTION_ESCALATED",
        category=AuditCategory.PATROL,
        severity=AuditSeverity.HIGH,
        summary="Patrol exception explicitly referred to Incident.",
        actor_user=actor,
        company=exception.company,
        branch=task.site.managing_branch,
        source_object=exception,
        metadata_safe={"incident_number": incident.incident_number},
    )
    return incident


@transaction.atomic
def refer_patrol_observation_to_incident(*, observation, actor, reason):
    observation = (
        consistent_observations(
            PatrolObservation.objects.select_for_update(of=("self",)).select_related(
                "company",
                "patrol_run__patrol_task__branch",
                "site",
                "post",
                "checkpoint_visit",
            )
        )
        .filter(pk=observation.pk)
        .first()
    )
    if observation is None:
        raise IncidentValidationError("Patrol observation has an invalid tenant graph.")
    if not access.has_permission(
        user=actor,
        permission="patrol.change_patrolobservation",
        company=observation.company,
        branch=observation.patrol_run.patrol_task.branch,
    ):
        raise IncidentPermissionError("Patrol observation referral permission is required.")
    raw_existing = Incident.objects.filter(patrol_observation=observation).first()
    existing = (
        consistent_incidents(Incident.objects.all()).filter(patrol_observation=observation).first()
    )
    if raw_existing is not None and existing is None:
        raise IncidentValidationError("The existing referral Incident is tenant-inconsistent.")
    if existing is not None:
        return existing
    run = observation.patrol_run
    incident = create_incident(
        actor=actor,
        company=observation.company,
        branch=observation.site.managing_branch,
        incident_type=_referral_type(observation.company),
        title=f"Patrol referral: {observation.title}",
        description=reason,
        source="PATROL",
        client=observation.site.client,
        contract=observation.site.contract,
        site=observation.site,
        post=observation.post,
        patrol_task=run.patrol_task,
        patrol_run=run,
        checkpoint_visit=observation.checkpoint_visit,
        patrol_observation=observation,
        authorized_source=True,
    )
    return incident


@transaction.atomic
def cancel_own_sos(*, actor, sos, reason):
    locked = _locked_sos(sos.pk)
    if locked.employee.user_id != actor.id:
        raise IncidentPermissionError("Only the reporter may request cancellation.")
    _require_permission(
        actor=actor,
        permission="incidents.trigger_own_sos",
        company=locked.company,
        branch=locked.employee.branch,
    )
    if not reason.strip() or locked.status not in {"TRIGGERED", "LINKED_TO_INCIDENT"}:
        raise IncidentValidationError("A reason and an active SOS are required.")
    locked.status, locked.cancelled_at, locked.cancellation_reason = (
        "CANCELLED_BY_REPORTER",
        timezone.now(),
        reason.strip(),
    )
    locked.save(update_fields=["status", "cancelled_at", "cancellation_reason"])
    if locked.linked_incident_id:
        _event(
            locked.linked_incident,
            "OTHER",
            actor,
            "SOS cancellation requested",
            description=reason.strip(),
        )
    return locked


TRANSITIONS = {
    "NEW": {"ACKNOWLEDGED", "CANCELLED"},
    "ACKNOWLEDGED": {"TRIAGED", "RESPONDING", "CANCELLED"},
    "TRIAGED": {"RESPONDING", "UNDER_INVESTIGATION", "CANCELLED"},
    "RESPONDING": {"CONTAINED", "UNDER_INVESTIGATION"},
    "CONTAINED": {"UNDER_INVESTIGATION", "RESOLVED"},
    "UNDER_INVESTIGATION": {"RESOLVED"},
    "RESOLVED": {"CLOSED", "REOPENED"},
    "CLOSED": {"REOPENED"},
    "REOPENED": {"RESPONDING", "UNDER_INVESTIGATION", "RESOLVED"},
}


@transaction.atomic
def transition_incident(*, incident, actor, new_status, summary=""):
    obj = _locked_incident(incident.pk)
    permission = {
        "ACKNOWLEDGED": "incidents.acknowledge_incident",
        "RESPONDING": "incidents.manage_incident_response",
        "CONTAINED": "incidents.contain_incident",
        "RESOLVED": "incidents.resolve_incident",
        "CLOSED": "incidents.close_incident",
        "REOPENED": "incidents.reopen_incident",
        "TRIAGED": "incidents.triage_incident",
        "CANCELLED": "incidents.manage_incident",
        "UNDER_INVESTIGATION": "incidents.manage_incident",
    }.get(new_status, "incidents.manage_incident")
    _require_permission(
        actor=actor,
        permission=permission,
        company=obj.company,
        branch=obj.branch,
        operational_zone=obj.operational_zone,
    )
    if new_status not in TRANSITIONS.get(obj.status, set()):
        raise IncidentValidationError(f"Invalid transition from {obj.status} to {new_status}.")
    if new_status == "CLOSED":
        if obj.actions.filter(status__in=["OPEN", "ASSIGNED", "IN_PROGRESS", "BLOCKED"]).exists():
            raise IncidentValidationError("Open actions prevent closure.")
        if obj.client_notification_required and not obj.client_notifications.exists():
            raise IncidentValidationError("Required client notification is missing.")
        if (
            obj.post_incident_review_required
            and not hasattr(obj, "review")
            or (obj.post_incident_review_required and obj.review.status != "COMPLETED")
        ):
            raise IncidentValidationError("Required post-incident review is incomplete.")
    old, now = obj.status, timezone.now()
    obj.status = new_status
    field = {
        "ACKNOWLEDGED": "acknowledged_at",
        "TRIAGED": "triaged_at",
        "RESPONDING": "responding_at",
        "CONTAINED": "contained_at",
        "RESOLVED": "resolved_at",
        "CLOSED": "closed_at",
    }.get(new_status)
    if field and getattr(obj, field) is None:
        setattr(obj, field, now)
    if new_status == "ACKNOWLEDGED" and obj.acknowledged_by_id is None:
        obj.acknowledged_by = actor
    if new_status == "RESOLVED":
        obj.resolution_summary = summary
    if new_status == "CLOSED":
        obj.closure_summary = summary
    obj.save()
    _event(
        obj,
        new_status
        if new_status in {"ACKNOWLEDGED", "CONTAINED", "RESOLVED", "CLOSED", "REOPENED"}
        else "STATUS_CHANGED",
        actor,
        f"Incident {new_status.lower()}",
        previous=old,
        new=new_status,
        description=summary,
    )
    event_type = {
        "ACKNOWLEDGED": "INCIDENT_ACKNOWLEDGED",
        "RESPONDING": "INCIDENT_RESPONSE_STARTED",
        "RESOLVED": "INCIDENT_RESOLVED",
        "CLOSED": "INCIDENT_CLOSED",
        "REOPENED": "INCIDENT_REOPENED",
    }.get(new_status)
    if event_type:
        _publish_safely(
            event_key=f"incidents.transition:{obj.id}:{new_status}:{obj.updated_at.isoformat()}",
            event_type=event_type,
            source_app="incidents",
            source_model="Incident",
            source_object_id=obj.id,
            company=obj.company,
            safe_payload={
                "incident_number": obj.incident_number,
                "site_name": getattr(obj.site, "name", "Unresolved site"),
                "severity": obj.severity,
                "message": f"Incident status changed to {new_status.lower()}.",
            },
        )
    return obj


def resolve_incident_escalation_policy(incident):
    incident = consistent_incidents(Incident.objects.all()).filter(pk=incident.pk).first()
    if incident is None:
        return None
    today = timezone.localdate()
    return (
        consistent_escalation_policies(
            IncidentEscalationPolicy.objects.filter(
                company=incident.company, is_active=True, effective_from__lte=today
            )
        )
        .filter(models.Q(effective_to__isnull=True) | models.Q(effective_to__gte=today))
        .filter(models.Q(site=incident.site) | models.Q(site__isnull=True))
        .filter(
            models.Q(incident_type=incident.incident_type) | models.Q(incident_type__isnull=True)
        )
        .filter(models.Q(severity=incident.severity) | models.Q(severity=""))
        .annotate(
            rank=Case(
                When(site=incident.site, then=Value(4)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .order_by("-rank", "-effective_from")
        .first()
    )


def command_center_queue(queryset=None):
    qs = queryset if queryset is not None else Incident.objects.all()
    return (
        consistent_incidents(qs)
        .exclude(status__in=["CLOSED", "CANCELLED"])
        .select_related("company", "branch", "site", "incident_type", "command_center_owner")
        .annotate(
            queue_rank=Case(
                When(priority="EMERGENCY", acknowledged_at__isnull=True, then=Value(0)),
                When(severity="CRITICAL", then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("queue_rank", "reported_at")
    )
