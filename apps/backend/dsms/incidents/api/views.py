# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,arg-type"
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.deployment.tenant_queries import consistent_employees
from dsms.identity import access
from dsms.identity.permissions import HasRBACPermission
from dsms.incidents import services
from dsms.incidents.exceptions import IncidentPermissionError, IncidentValidationError
from dsms.incidents.models import Incident, IncidentEvidence, IncidentEvidenceEvent, SOSAlert
from dsms.incidents.tenant_queries import (
    consistent_events,
    consistent_evidence,
    consistent_sos_alerts,
    scoped_incidents,
    user_belongs_to_company,
)
from dsms.workforce.models import Employee

from .serializers import (
    EscalationSerializer,
    EventSerializer,
    EvidenceSerializer,
    IncidentActionSerializer,
    IncidentDetailSerializer,
    IncidentListSerializer,
    ReasonSerializer,
    ResponderSerializer,
    SOSSerializer,
    TransitionSerializer,
    TriggerSOSSerializer,
)


def _service_call(callable_, **kwargs):
    try:
        return callable_(**kwargs)
    except IncidentPermissionError as exc:
        raise PermissionDenied(str(exc)) from exc
    except IncidentValidationError as exc:
        raise ValidationError(str(exc)) from exc


class NoDeleteViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]


class IncidentViewSet(NoDeleteViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "list": "incidents.view_incident",
        "retrieve": "incidents.view_incident",
        "create": "incidents.report_incident",
        "partial_update": "incidents.manage_incident",
        "update": "incidents.manage_incident",
        "timeline": "incidents.view_incident_audit",
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

    def _permission(self):
        return self.custom_action_permissions.get(self.action, "incidents.view_incident")

    def get_queryset(self):
        return scoped_incidents(
            super().get_queryset(), user=self.request.user, permission=self._permission()
        )

    def get_serializer_class(self):
        return IncidentListSerializer if self.action == "list" else IncidentDetailSerializer

    def perform_create(self, serializer):
        data = serializer.validated_data
        incident = _service_call(
            services.create_incident,
            actor=self.request.user,
            company=data["company"],
            branch=data["branch"],
            incident_type=data["incident_type"],
            title=data["title"],
            description=data["description"],
            source="OTHER",
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
                    "operational_zone",
                }
            },
        )
        serializer.instance = incident

    def perform_update(self, serializer):
        original = serializer.instance
        if not access.has_permission(
            user=self.request.user,
            permission="incidents.manage_incident",
            company=original.company,
            branch=original.branch,
            operational_zone=original.operational_zone,
        ):
            raise PermissionDenied("Incident management permission is required.")
        company = serializer.validated_data.get("company", original.company)
        branch = serializer.validated_data.get("branch", original.branch)
        zone = serializer.validated_data.get("operational_zone", original.operational_zone)
        if not access.has_permission(
            user=self.request.user,
            permission="incidents.manage_incident",
            company=company,
            branch=branch,
            operational_zone=zone,
        ):
            raise PermissionDenied(
                "Incident management permission is required in the target scope."
            )
        serializer.save()

    @action(detail=True, methods=["get"])
    def timeline(self, request, pk=None):
        incident = self.get_object()
        events = consistent_events(incident.events.all())
        return Response(
            EventSerializer(events, many=True, context=self.get_serializer_context()).data
        )

    def _transition(self, request, value):
        payload = TransitionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        obj = _service_call(
            services.transition_incident,
            incident=self.get_object(),
            actor=request.user,
            new_status=value,
            summary=payload.validated_data.get("summary", ""),
        )
        return Response(IncidentDetailSerializer(obj, context=self.get_serializer_context()).data)

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
        incident = self.get_object()
        payload = ResponderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        employee = None
        if payload.validated_data.get("employee"):
            employee = get_object_or_404(
                consistent_employees(Employee.objects.filter(company=incident.company)),
                pk=payload.validated_data["employee"],
            )
        user = None
        if payload.validated_data.get("user"):
            user = get_object_or_404(
                get_user_model().objects.filter(is_active=True),
                pk=payload.validated_data["user"],
            )
            if not user_belongs_to_company(user, incident.company):
                raise Http404
        responder = _service_call(
            services.assign_incident_responder,
            incident=incident,
            actor=request.user,
            user=user,
            employee=employee,
            responder_role=payload.validated_data["responder_role"],
        )
        return Response({"id": str(responder.id), "status": responder.status}, status=201)

    @action(detail=True, methods=["post"], url_path="action")
    def record_action(self, request, pk=None):
        payload = IncidentActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        item = _service_call(
            services.add_incident_action,
            incident=self.get_object(),
            actor=request.user,
            **payload.validated_data,
        )
        return Response({"id": str(item.id), "action_number": item.action_number}, status=201)

    @action(detail=True, methods=["post"])
    def escalate(self, request, pk=None):
        payload = EscalationSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        item = _service_call(
            services.escalate_incident,
            incident=self.get_object(),
            actor=request.user,
            **payload.validated_data,
        )
        return Response({"id": str(item.id), "escalation_type": item.escalation_type}, status=201)


class SOSViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    queryset = SOSAlert.objects.select_related("employee__branch", "site", "linked_incident")
    serializer_class = SOSSerializer

    def _managed_permission(self):
        return {
            "acknowledge": "incidents.acknowledge_incident",
            "resolve": "incidents.resolve_incident",
        }.get(self.action, "incidents.manage_incident")

    def get_queryset(self):
        qs = consistent_sos_alerts(super().get_queryset())
        if self.request.user.is_superuser:
            return qs
        allowed = Q(pk__in=[])
        permissions = access.get_effective_permissions(self.request.user)
        if self.action == "cancel":
            if "incidents.trigger_own_sos" in permissions:
                allowed |= Q(user=self.request.user, employee__user=self.request.user)
        elif self.action in {"acknowledge", "resolve"}:
            branch_ids = access.get_accessible_branch_ids(
                self.request.user, permission=self._managed_permission()
            )
            allowed |= Q(employee__branch_id__in=branch_ids)
        else:
            if "incidents.view_own_sos" in permissions:
                allowed |= Q(user=self.request.user, employee__user=self.request.user)
            branch_ids = access.get_accessible_branch_ids(
                self.request.user, permission="incidents.manage_incident"
            )
            allowed |= Q(employee__branch_id__in=branch_ids)
        return qs.filter(allowed)

    @action(detail=False, methods=["post"])
    def trigger(self, request):
        payload = TriggerSOSSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        permissions = access.get_effective_permissions(request.user)
        allowed = Q(pk__in=[])
        if "incidents.trigger_own_sos" in permissions:
            allowed |= Q(user=request.user)
        managed_branches = access.get_accessible_branch_ids(
            request.user, permission="incidents.manage_incident"
        )
        allowed |= Q(branch_id__in=managed_branches)
        employee = get_object_or_404(
            consistent_employees(Employee.objects.filter(company__is_active=True)).filter(allowed),
            pk=payload.validated_data["employee"],
        )
        location = None
        if "latitude" in payload.validated_data:
            location = {
                key: payload.validated_data[key]
                for key in ("latitude", "longitude", "accuracy_meters")
                if key in payload.validated_data
            }
        sos = _service_call(
            services.trigger_sos,
            actor=request.user,
            employee=employee,
            client_event_id=payload.validated_data["client_event_id"],
            location=location,
            message=payload.validated_data.get("message"),
        )
        return Response(self.get_serializer(sos).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        sos = _service_call(
            services.cancel_own_sos,
            actor=request.user,
            sos=self.get_object(),
            reason=payload.validated_data["reason"],
        )
        return Response(self.get_serializer(sos).data)

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        sos = _service_call(services.acknowledge_sos, sos=self.get_object(), actor=request.user)
        return Response(self.get_serializer(sos).data)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        sos = _service_call(
            services.resolve_sos,
            sos=self.get_object(),
            actor=request.user,
            reason=payload.validated_data["reason"],
        )
        return Response(self.get_serializer(sos).data)


class CommandCenterQueueViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {"list": "incidents.view_incident_dashboard"}
    serializer_class = IncidentListSerializer
    filterset_fields = ["branch", "site", "status", "severity", "priority"]

    def get_queryset(self):
        queryset = scoped_incidents(
            Incident.objects.all(),
            user=self.request.user,
            permission="incidents.view_incident_dashboard",
        )
        return services.command_center_queue(queryset)


class EvidenceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    serializer_class = EvidenceSerializer
    queryset = IncidentEvidence.objects.select_related(
        "company", "incident__company", "incident__branch", "uploaded_by"
    )
    custom_action_permissions = {
        "list": "incidents.download_incident_evidence",
        "retrieve": "incidents.download_incident_evidence",
        "download": "incidents.download_incident_evidence",
    }

    def get_queryset(self):
        queryset = consistent_evidence(super().get_queryset()).order_by("pk")
        if self.request.user.is_superuser:
            return queryset
        return queryset.filter(
            incident__branch_id__in=access.get_accessible_branch_ids(
                self.request.user, permission="incidents.download_incident_evidence"
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
