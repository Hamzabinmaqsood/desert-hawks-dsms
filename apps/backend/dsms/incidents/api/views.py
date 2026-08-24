# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,arg-type"
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.identity import access
from dsms.identity.permissions import HasRBACPermission
from dsms.incidents import services
from dsms.incidents.models import Incident, IncidentEvidence, IncidentEvidenceEvent, SOSAlert
from dsms.workforce.models import Employee

from .serializers import (
    EventSerializer,
    EvidenceSerializer,
    IncidentDetailSerializer,
    IncidentListSerializer,
    SensitiveSOSSerializer,
    SOSSerializer,
    TransitionSerializer,
    TriggerSOSSerializer,
)


class NoDeleteViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]


class IncidentViewSet(NoDeleteViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "acknowledge": "incidents.acknowledge_incident",
        "respond": "incidents.manage_incident_response",
        "contain": "incidents.contain_incident",
        "resolve": "incidents.resolve_incident",
        "close": "incidents.close_incident",
        "reopen": "incidents.reopen_incident",
        "assign_responder": "incidents.manage_responders",
        "record_action": "incidents.manage_incident_actions",
        "escalate": "incidents.escalate_incident",
    }
    queryset = Incident.objects.select_related("company", "branch", "site", "incident_type")
    filterset_fields = [
        "company",
        "branch",
        "site",
        "client",
        "status",
        "severity",
        "priority",
        "source",
        "incident_type",
    ]
    search_fields = ["incident_number", "title", "description"]
    ordering_fields = ["reported_at", "severity", "priority", "acknowledged_at", "resolved_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        permission = "incidents.view_incident"
        return queryset.filter(
            branch_id__in=access.get_accessible_branch_ids(self.request.user, permission=permission)
        )

    def get_serializer_class(self):
        return IncidentListSerializer if self.action == "list" else IncidentDetailSerializer

    def perform_create(self, serializer):
        data = serializer.validated_data
        incident = services.create_incident(
            actor=self.request.user,
            company=data["company"],
            branch=data["branch"],
            incident_type=data["incident_type"],
            title=data["title"],
            description=data["description"],
            source=data.get("source", "OTHER"),
            **{
                key: value
                for key, value in data.items()
                if key
                in {
                    "client",
                    "contract",
                    "site",
                    "post",
                    "reporter_employee",
                    "reported_by_name",
                    "occurred_at",
                    "discovered_at",
                    "duty_assignment",
                    "attendance_record",
                    "employee_deployment",
                    "site_visit",
                    "inspection",
                    "patrol_task",
                    "patrol_run",
                    "checkpoint_visit",
                    "patrol_observation",
                    "operational_zone",
                }
            },
        )
        serializer.instance = incident

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        return Response(EventSerializer(self.get_object().events.all(), many=True).data)

    def _transition(self, request, value):
        payload = TransitionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        obj = services.transition_incident(
            incident=self.get_object(),
            actor=request.user,
            new_status=value,
            summary=payload.validated_data.get("summary", ""),
        )
        return Response(IncidentDetailSerializer(obj).data)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        return self._transition(request, "ACKNOWLEDGED")

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        return self._transition(request, "RESPONDING")

    @action(detail=True, methods=["post"])
    def contain(self, request, pk=None):
        return self._transition(request, "CONTAINED")

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        return self._transition(request, "RESOLVED")

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self._transition(request, "CLOSED")

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        return self._transition(request, "REOPENED")

    @action(detail=True, methods=["post"], url_path="assign-responder")
    def assign_responder(self, request, pk=None):
        responder = services.assign_incident_responder(
            incident=self.get_object(),
            actor=request.user,
            user=request.user.__class__.objects.filter(pk=request.data.get("user")).first(),
            employee=Employee.objects.filter(pk=request.data.get("employee")).first(),
            responder_role=request.data.get("responder_role", "OTHER"),
        )
        return Response({"id": str(responder.id), "status": responder.status}, status=201)

    @action(detail=True, methods=["post"], url_path="action")
    def record_action(self, request, pk=None):
        item = services.add_incident_action(
            incident=self.get_object(),
            actor=request.user,
            title=request.data.get("title", ""),
            description=request.data.get("description", ""),
            priority=request.data.get("priority", "NORMAL"),
        )
        return Response({"id": str(item.id), "action_number": item.action_number}, status=201)

    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        item = services.escalate_incident(
            incident=self.get_object(),
            actor=request.user,
            escalation_type=request.data.get("escalation_type", "MANUAL"),
            reason=request.data.get("reason", ""),
        )
        return Response({"id": str(item.id), "escalation_type": item.escalation_type}, status=201)


class SOSViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "trigger": "incidents.trigger_own_sos",
        "acknowledge": "incidents.acknowledge_incident",
        "resolve": "incidents.resolve_incident",
        "cancel": "incidents.trigger_own_sos",
    }
    queryset = SOSAlert.objects.select_related("employee", "site", "linked_incident")

    def get_queryset(self):
        qs = super().get_queryset()
        if (
            self.request.user.is_superuser
            or "incidents.manage_incident" in access.get_effective_permissions(self.request.user)
        ):
            if self.request.user.is_superuser:
                return qs
            return qs.filter(
                employee__branch_id__in=access.get_accessible_branch_ids(
                    self.request.user, permission="incidents.manage_incident"
                )
            )
        return qs.filter(user=self.request.user)

    def get_serializer_class(self):
        return (
            SensitiveSOSSerializer
            if "incidents.view_sensitive_incident_location"
            in access.get_effective_permissions(self.request.user)
            else SOSSerializer
        )

    @action(detail=False, methods=["post"])
    def trigger(self, request):
        payload = TriggerSOSSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        employee = get_object_or_404(Employee, pk=payload.validated_data["employee"])
        location = None
        if "latitude" in payload.validated_data and "longitude" in payload.validated_data:
            location = {
                k: payload.validated_data[k]
                for k in ("latitude", "longitude", "accuracy_meters")
                if k in payload.validated_data
            }
        sos = services.trigger_sos(
            actor=request.user,
            employee=employee,
            client_event_id=payload.validated_data["client_event_id"],
            location=location,
            message=payload.validated_data.get("message"),
        )
        return Response(self.get_serializer(sos).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        sos = services.cancel_own_sos(
            actor=request.user, sos=self.get_object(), reason=request.data.get("reason", "")
        )
        return Response(self.get_serializer(sos).data)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        sos = services.acknowledge_sos(sos=self.get_object(), actor=request.user)
        return Response(self.get_serializer(sos).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        sos = services.resolve_sos(
            sos=self.get_object(), actor=request.user, reason=request.data.get("reason", "")
        )
        return Response(self.get_serializer(sos).data)


class CommandCenterQueueViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {"list": "incidents.view_incident_dashboard"}
    serializer_class = IncidentListSerializer
    filterset_fields = ["branch", "site", "status", "severity", "priority"]

    def get_queryset(self):
        queryset = Incident.objects.all()
        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                branch_id__in=access.get_accessible_branch_ids(
                    self.request.user, permission="incidents.view_incident_dashboard"
                )
            )
        return services.command_center_queue(queryset)


class EvidenceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    serializer_class = EvidenceSerializer
    queryset = IncidentEvidence.objects.select_related("incident__branch", "uploaded_by")
    custom_action_permissions = {"download": "incidents.download_incident_evidence"}

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(
            incident__branch_id__in=access.get_accessible_branch_ids(
                self.request.user, permission="incidents.view_incidentevidence"
            )
        )

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        evidence = self.get_object()
        if not evidence.file:
            return Response({"detail": "No retained file exists."}, status=404)
        IncidentEvidenceEvent.objects.create(
            evidence=evidence, event_type="DOWNLOADED", actor=request.user
        )
        record_audit_event(
            action="INCIDENT_EVIDENCE_DOWNLOADED",
            category=AuditCategory.INCIDENT,
            severity=AuditSeverity.HIGH,
            summary="Incident evidence downloaded.",
            actor_user=request.user,
            company=evidence.company,
            branch=evidence.incident.branch,
            source_object=evidence,
            object_reference=evidence.original_filename,
        )
        return FileResponse(
            evidence.file.open("rb"),
            as_attachment=True,
            filename=evidence.original_filename or f"evidence-{evidence.id}",
            content_type=evidence.mime_type or "application/octet-stream",
        )
