# mypy: disable-error-code="attr-defined,no-untyped-def,type-arg,no-untyped-call,arg-type,union-attr,no-any-return"
# ruff: noqa: E501
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.deployment.tenant_queries import consistent_employees
from dsms.identity import access
from dsms.identity.permissions import HasRBACPermission
from dsms.incidents.exceptions import IncidentPermissionError, IncidentValidationError
from dsms.workforce.models import Employee

from .. import models, services
from ..exceptions import PatrolPermissionError, PatrolValidationError
from ..tenant_queries import consistent_checkpoints, scoped_queryset
from .serializers import (
    SERIALIZERS,
    CompletePatrolSerializer,
    EmployeeActionSerializer,
    StartPatrolSerializer,
    VerifyCheckpointSerializer,
)


def _service_call(function, **kwargs):
    try:
        return function(**kwargs)
    except (PatrolPermissionError, IncidentPermissionError) as exc:
        raise PermissionDenied(str(exc)) from exc
    except (PatrolValidationError, IncidentValidationError) as exc:
        raise ValidationError(str(exc)) from exc


class TenantConfigViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _permission(self, verb: str) -> str:
        model = self.queryset.model
        return getattr(self, "custom_action_permissions", {}).get(
            self.action, f"patrol.{verb}_{model._meta.model_name}"
        )

    def get_queryset(self):
        verb = "change" if self.action in {"update", "partial_update"} else "view"
        return scoped_queryset(
            super().get_queryset(),
            user=self.request.user,
            permission=self._permission(verb),
        )

    @staticmethod
    def _scope(data, instance=None):
        def value(name):
            return data.get(name, getattr(instance, name, None))

        company = value("company")
        branch = value("branch")
        site = value("site")
        run = value("patrol_run")
        if run is not None:
            company = company or run.company
            branch = branch or run.patrol_task.branch
            site = site or run.site
        company = company or getattr(site, "company", None) or getattr(branch, "company", None)
        branch = branch or getattr(site, "managing_branch", None)
        return {"company": company, "branch": branch}

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        if not access.has_permission(
            user=self.request.user,
            permission=self._permission("add"),
            **self._scope(serializer.validated_data),
        ):
            raise PermissionDenied("You cannot create this resource in the requested scope.")
        serializer.save()

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        permission = self._permission("change")
        if not access.has_permission(
            user=self.request.user,
            permission=permission,
            **self._scope({}, serializer.instance),
        ):
            raise PermissionDenied("You cannot update this resource in its current scope.")
        if not access.has_permission(
            user=self.request.user,
            permission=permission,
            **self._scope(serializer.validated_data, serializer.instance),
        ):
            raise PermissionDenied("You cannot update this resource in the resulting scope.")
        serializer.save()


class ReadOnlyWorkflowViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "head", "options"]

    def _permission(self) -> str:
        model = self.queryset.model
        return getattr(self, "custom_action_permissions", {}).get(
            self.action, f"patrol.view_{model._meta.model_name}"
        )

    def get_queryset(self):
        return scoped_queryset(
            super().get_queryset(), user=self.request.user, permission=self._permission()
        )


def config_viewset(model):
    class ViewSet(TenantConfigViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    return ViewSet


PolicyViewSet = config_viewset(models.PatrolPolicy)
CheckpointViewSet = config_viewset(models.PatrolCheckpoint)
RouteViewSet = config_viewset(models.PatrolRoute)
RequirementViewSet = config_viewset(models.PatrolRequirement)


class ObservationViewSet(TenantConfigViewSet):
    queryset = models.PatrolObservation.objects.select_related(
        "patrol_run__patrol_task", "site", "post", "checkpoint", "checkpoint_visit"
    )
    serializer_class = SERIALIZERS["PatrolObservation"]
    custom_action_permissions = {"refer_incident": "patrol.change_patrolobservation"}

    @action(detail=True, methods=["post"], url_path="refer-incident")
    def refer_incident(self, request, pk=None):
        from dsms.incidents.services import refer_patrol_observation_to_incident

        incident = _service_call(
            refer_patrol_observation_to_incident,
            observation=self.get_object(),
            actor=request.user,
            reason=request.data.get("reason", ""),
        )
        return Response(
            {"incident_id": str(incident.id), "incident_number": incident.incident_number},
            status=201,
        )


class ExceptionViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.PatrolException.objects.select_related(
        "patrol_task", "patrol_run", "checkpoint_visit"
    )
    serializer_class = SERIALIZERS["PatrolException"]
    custom_action_permissions = {"refer_incident": "patrol.resolve_patrol_exception"}

    @action(detail=True, methods=["post"], url_path="refer-incident")
    def refer_incident(self, request, pk=None):
        from dsms.incidents.services import refer_patrol_exception_to_incident

        incident = _service_call(
            refer_patrol_exception_to_incident,
            exception=self.get_object(),
            actor=request.user,
            reason=request.data.get("reason", ""),
        )
        return Response(
            {"incident_id": str(incident.id), "incident_number": incident.incident_number},
            status=201,
        )


class ReviewViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.PatrolReview.objects.select_related("patrol_run__patrol_task", "reviewed_by")
    serializer_class = SERIALIZERS["PatrolReview"]


class TaskViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.PatrolTask.objects.select_related(
        "assigned_employee", "site", "route_version", "patrol_route", "branch"
    )
    serializer_class = SERIALIZERS["PatrolTask"]
    custom_action_permissions = {"assign": "patrol.assign_patroltask"}

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        task = self.get_object()
        payload = EmployeeActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        employee = get_object_or_404(
            consistent_employees(Employee.objects.filter(company=task.company)),
            pk=payload.validated_data["employee"],
        )
        task = _service_call(
            services.assign_employee_to_patrol,
            patrol_task=task,
            employee=employee,
            actor=request.user,
        )
        return Response(self.get_serializer(task).data)


class RunViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.PatrolRun.objects.select_related(
        "employee", "patrol_task__branch", "site", "route_version"
    )
    serializer_class = SERIALIZERS["PatrolRun"]
    custom_action_permissions = {
        "start": "patrol.perform_own_patrol",
        "complete": "patrol.perform_own_patrol",
        "verify_checkpoint": "patrol.perform_own_patrol",
    }

    @action(detail=False, methods=["post"])
    def start(self, request):
        payload = StartPatrolSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        task = get_object_or_404(
            scoped_queryset(
                models.PatrolTask.objects.select_related("assigned_employee", "branch", "site"),
                user=request.user,
                permission="patrol.perform_own_patrol",
            ),
            pk=payload.validated_data["patrol_task"],
        )
        run = _service_call(
            services.start_patrol,
            actor=request.user,
            patrol_task=task,
            gps=payload.validated_data.get("gps"),
            client_event_id=payload.validated_data.get("client_event_id"),
            device_metadata=payload.validated_data.get("device_metadata"),
        )
        return Response(self.get_serializer(run).data, status=201)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        payload = CompletePatrolSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        run = _service_call(
            services.complete_patrol,
            actor=request.user,
            patrol_run=self.get_object(),
            gps=payload.validated_data.get("gps"),
            client_event_id=payload.validated_data.get("client_event_id"),
        )
        return Response(self.get_serializer(run).data)

    @action(detail=True, methods=["post"], url_path="verify-checkpoint")
    def verify_checkpoint(self, request, pk=None):
        run = self.get_object()
        payload = VerifyCheckpointSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        checkpoint = get_object_or_404(
            consistent_checkpoints(
                models.PatrolCheckpoint.objects.filter(
                    company=run.company,
                    site=run.site,
                    patrolroutecheckpoint__route_version=run.route_version,
                )
            ),
            pk=payload.validated_data["checkpoint"],
        )
        visit = _service_call(
            services.verify_patrol_checkpoint,
            actor=request.user,
            patrol_run=run,
            checkpoint=checkpoint,
            event_time=timezone.now(),
            gps=payload.validated_data.get("gps"),
            qr_token=payload.validated_data.get("qr_token"),
            nfc_payload=payload.validated_data.get("nfc_payload"),
            client_event_id=payload.validated_data.get("client_event_id"),
        )
        return Response(
            SERIALIZERS["CheckpointVisit"](visit, context=self.get_serializer_context()).data,
            status=201,
        )


class EvidenceViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.PatrolEvidence.objects.select_related(
        "patrol_run__patrol_task", "checkpoint_visit", "observation", "uploaded_by"
    )
    serializer_class = SERIALIZERS["PatrolEvidence"]


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    permission = "patrol.view_patrol_dashboard"
    if not request.user.is_superuser and permission not in access.get_effective_permissions(
        request.user
    ):
        raise PermissionDenied("Patrol dashboard permission is required.")
    today = timezone.localdate()
    tasks = scoped_queryset(
        models.PatrolTask.objects.filter(scheduled_start_at__date=today),
        user=request.user,
        permission=permission,
    )
    visits = scoped_queryset(
        models.CheckpointVisit.objects.filter(
            created_at__date=today, overall_verification_result="FAILED"
        ),
        user=request.user,
        permission=permission,
    )
    exceptions = scoped_queryset(
        models.PatrolException.objects.filter(status__in=["OPEN", "ACKNOWLEDGED"]),
        user=request.user,
        permission=permission,
    )
    observations = scoped_queryset(
        models.PatrolObservation.objects.filter(severity="CRITICAL", observed_at__date=today),
        user=request.user,
        permission=permission,
    )
    return Response(
        {
            "scheduled": tasks.count(),
            "in_progress": tasks.filter(status="IN_PROGRESS").count(),
            "completed": tasks.filter(status="COMPLETED").count(),
            "incomplete": tasks.filter(status="INCOMPLETE").count(),
            "missed": tasks.filter(status="MISSED").count(),
            "checkpoint_failures": visits.count(),
            "open_exceptions": exceptions.count(),
            "critical_observations": observations.count(),
        }
    )
