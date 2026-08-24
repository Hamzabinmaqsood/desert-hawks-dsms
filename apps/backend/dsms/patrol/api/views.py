# mypy: disable-error-code="attr-defined,no-untyped-def,type-arg,no-untyped-call,arg-type"
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.identity.access import filter_queryset_by_scope
from dsms.identity.permissions import HasRBACPermission

from .. import models, services
from .serializers import SERIALIZERS


class NoDeleteViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return filter_queryset_by_scope(super().get_queryset(), self.request.user)


def basic(model):
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    return ViewSet


PolicyViewSet = basic(models.PatrolPolicy)
CheckpointViewSet = basic(models.PatrolCheckpoint)
RouteViewSet = basic(models.PatrolRoute)
RequirementViewSet = basic(models.PatrolRequirement)


class ObservationViewSet(NoDeleteViewSet):
    queryset = models.PatrolObservation.objects.select_related("patrol_run", "site", "post")
    serializer_class = SERIALIZERS["PatrolObservation"]
    custom_action_permissions = {"refer_incident": "patrol.change_patrolobservation"}

    @action(detail=True, methods=["post"], url_path="refer-incident")
    def refer_incident(self, request, pk=None):
        from dsms.incidents.services import refer_patrol_observation_to_incident

        incident = refer_patrol_observation_to_incident(
            observation=self.get_object(), actor=request.user, reason=request.data.get("reason", "")
        )
        return Response(
            {"incident_id": str(incident.id), "incident_number": incident.incident_number},
            status=201,
        )


class ExceptionViewSet(NoDeleteViewSet):
    queryset = models.PatrolException.objects.select_related(
        "patrol_task", "patrol_run", "checkpoint_visit"
    )
    serializer_class = SERIALIZERS["PatrolException"]
    custom_action_permissions = {"refer_incident": "patrol.resolve_patrol_exception"}

    @action(detail=True, methods=["post"], url_path="refer-incident")
    def refer_incident(self, request, pk=None):
        from dsms.incidents.services import refer_patrol_exception_to_incident

        incident = refer_patrol_exception_to_incident(
            exception=self.get_object(), actor=request.user, reason=request.data.get("reason", "")
        )
        return Response(
            {"incident_id": str(incident.id), "incident_number": incident.incident_number},
            status=201,
        )


ReviewViewSet = basic(models.PatrolReview)


class TaskViewSet(NoDeleteViewSet):
    queryset = models.PatrolTask.objects.select_related(
        "assigned_employee", "site", "route_version"
    )
    serializer_class = SERIALIZERS["PatrolTask"]

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        task = services.assign_employee_to_patrol(
            patrol_task=self.get_object(),
            employee=models.Employee.objects.get(pk=request.data["employee"]),
            actor=request.user,
        )
        return Response(self.get_serializer(task).data)


class RunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    queryset = models.PatrolRun.objects.select_related("employee", "patrol_task", "site")
    serializer_class = SERIALIZERS["PatrolRun"]

    def get_queryset(self):
        return filter_queryset_by_scope(super().get_queryset(), self.request.user)

    @action(detail=False, methods=["post"])
    def start(self, request):
        run = services.start_patrol(
            actor=request.user,
            patrol_task=models.PatrolTask.objects.get(pk=request.data["patrol_task"]),
            gps=request.data.get("gps"),
            client_event_id=request.data.get("client_event_id"),
            device_metadata=request.data.get("device_metadata"),
        )
        return Response(self.get_serializer(run).data, status=201)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        run = services.complete_patrol(
            actor=request.user,
            patrol_run=self.get_object(),
            gps=request.data.get("gps"),
            client_event_id=request.data.get("client_event_id"),
        )
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"], url_path="verify-checkpoint")
    def verify_checkpoint(self, request, pk=None):
        visit = services.verify_patrol_checkpoint(
            actor=request.user,
            patrol_run=self.get_object(),
            checkpoint=models.PatrolCheckpoint.objects.get(pk=request.data["checkpoint"]),
            event_time=timezone.now(),
            gps=request.data.get("gps"),
            qr_token=request.data.get("qr_token"),
            nfc_payload=request.data.get("nfc_payload"),
            client_event_id=request.data.get("client_event_id"),
        )
        return Response(
            SERIALIZERS["CheckpointVisit"](visit, context={"request": request}).data, status=201
        )


class EvidenceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    queryset = models.PatrolEvidence.objects.all()
    serializer_class = SERIALIZERS["PatrolEvidence"]

    def get_queryset(self):
        return filter_queryset_by_scope(super().get_queryset(), self.request.user)


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    from dsms.identity.access import get_accessible_branch_ids

    today = timezone.localdate()
    branches = get_accessible_branch_ids(request.user)
    tasks = models.PatrolTask.objects.filter(scheduled_start_at__date=today, branch_id__in=branches)
    return Response(
        {
            "scheduled": tasks.count(),
            "in_progress": tasks.filter(status="IN_PROGRESS").count(),
            "completed": tasks.filter(status="COMPLETED").count(),
            "incomplete": tasks.filter(status="INCOMPLETE").count(),
            "missed": tasks.filter(status="MISSED").count(),
            "checkpoint_failures": models.CheckpointVisit.objects.filter(
                created_at__date=today,
                overall_verification_result="FAILED",
                patrol_run__patrol_task__branch_id__in=branches,
            ).count(),
            "open_exceptions": models.PatrolException.objects.filter(
                status__in=["OPEN", "ACKNOWLEDGED"], patrol_task__branch_id__in=branches
            ).count(),
            "critical_observations": models.PatrolObservation.objects.filter(
                severity="CRITICAL",
                observed_at__date=today,
                site__managing_branch_id__in=branches,
            ).count(),
        }
    )
