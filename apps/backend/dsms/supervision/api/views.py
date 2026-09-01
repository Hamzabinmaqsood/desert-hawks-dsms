# mypy: disable-error-code="attr-defined,no-untyped-def,type-arg,no-untyped-call,arg-type"
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.identity.access import filter_queryset_by_scope, get_accessible_branch_ids
from dsms.identity.permissions import HasRBACPermission, RequiresPermission

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


AssignmentViewSet = basic(models.SupervisionAssignment)
FrequencyViewSet = basic(models.VisitFrequencyRequirement)
TemplateViewSet = basic(models.InspectionTemplate)
ResponseViewSet = basic(models.InspectionResponse)
ObservationViewSet = basic(models.SiteObservation)
FeedbackViewSet = basic(models.SiteVisitClientFeedback)
DailyReportViewSet = basic(models.SupervisorDailyReport)


class FindingViewSet(NoDeleteViewSet):
    queryset = models.InspectionFinding.objects.select_related(
        "inspection__site_visit", "site", "post"
    )
    serializer_class = SERIALIZERS["InspectionFinding"]
    custom_action_permissions = {"refer_incident": "supervision.change_inspectionfinding"}

    @action(detail=True, methods=["post"], url_path="refer-incident")
    def refer_incident(self, request, pk=None):
        from dsms.incidents.services import refer_supervision_finding_to_incident

        incident = refer_supervision_finding_to_incident(
            finding=self.get_object(), actor=request.user, reason=request.data.get("reason", "")
        )
        return Response(
            {"incident_id": str(incident.id), "incident_number": incident.incident_number},
            status=201,
        )


class VisitPlanViewSet(NoDeleteViewSet):
    queryset = models.SupervisorVisitPlan.objects.select_related("supervisor", "site", "branch")
    serializer_class = SERIALIZERS["SupervisorVisitPlan"]

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        plan = self.get_object()
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response({"reason": ["This field is required."]}, status=400)
        plan.status, plan.cancellation_reason = "CANCELLED", reason
        plan.save()
        return Response(self.get_serializer(plan).data)


class VisitViewSet(NoDeleteViewSet):
    queryset = models.SiteVisit.objects.select_related("supervisor", "site", "branch", "visit_plan")
    serializer_class = SERIALIZERS["SiteVisit"]

    @action(detail=False, methods=["post"])
    def start(self, request):
        visit = services.start_site_visit(
            actor=request.user,
            supervisor=models.Employee.objects.get(pk=request.data["supervisor"]),
            site=models.SecuritySite.objects.get(pk=request.data["site"]),
            gps=request.data.get("gps"),
        )
        return Response(self.get_serializer(visit).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        visit = services.end_site_visit(
            visit=self.get_object(),
            actor=request.user,
            summary=request.data.get("summary", ""),
            gps=request.data.get("gps"),
        )
        return Response(self.get_serializer(visit).data)

    @action(detail=True, methods=["post"], url_path="verify-guard")
    def verify_guard(self, request, pk=None):
        employee = models.Employee.objects.filter(pk=request.data.get("employee")).first()
        result = services.verify_guard_during_visit(
            site_visit=self.get_object(),
            post=models.SecurityPost.objects.get(pk=request.data["post"]),
            employee=employee,
            observed_at=timezone.now(),
            actor=request.user,
        )
        return Response(result)


class InspectionViewSet(NoDeleteViewSet):
    queryset = models.SiteInspection.objects.select_related("site_visit", "site", "template")
    serializer_class = SERIALIZERS["SiteInspection"]

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        inspection = services.submit_inspection(inspection=self.get_object())
        return Response(self.get_serializer(inspection).data)


class CorrectiveActionViewSet(NoDeleteViewSet):
    queryset = models.CorrectiveAction.objects.select_related("finding", "site")
    serializer_class = SERIALIZERS["CorrectiveAction"]

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        obj = services.transition_corrective_action(
            action=self.get_object(),
            actor=request.user,
            target=request.data["status"],
            notes=request.data.get("notes", ""),
        )
        return Response(self.get_serializer(obj).data)


class GuardObservationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "list": "supervision.view_guard_observation",
        "retrieve": "supervision.view_guard_observation",
    }
    queryset = models.GuardObservation.objects.select_related("site_visit", "employee", "post")
    serializer_class = SERIALIZERS["GuardObservation"]

    def get_queryset(self):
        branches = get_accessible_branch_ids(
            self.request.user, permission="supervision.view_guard_observation"
        )
        return self.queryset.filter(site__managing_branch_id__in=branches).order_by("id")


class EvidenceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "list": "supervision.view_sensitive_field_evidence",
        "retrieve": "supervision.view_sensitive_field_evidence",
    }
    queryset = models.FieldEvidence.objects.select_related(
        "site_visit__branch",
        "inspection__site__managing_branch",
        "finding__site__managing_branch",
        "corrective_action__site__managing_branch",
    )
    serializer_class = SERIALIZERS["FieldEvidence"]

    def get_queryset(self):
        branches = get_accessible_branch_ids(
            self.request.user, permission="supervision.view_sensitive_field_evidence"
        )
        return (
            self.queryset.filter(
                Q(site_visit__branch_id__in=branches)
                | Q(inspection__site__managing_branch_id__in=branches)
                | Q(finding__site__managing_branch_id__in=branches)
                | Q(corrective_action__site__managing_branch_id__in=branches)
            )
            .distinct()
            .order_by("id")
        )


def _supervision_summary(*, branches, exceptions_only=False):
    today = timezone.localdate()
    plans = models.SupervisorVisitPlan.objects.filter(planned_date=today, branch_id__in=branches)
    actions = models.CorrectiveAction.objects.exclude(
        status__in=["VERIFIED", "CLOSED", "CANCELLED"]
    ).filter(site__managing_branch_id__in=branches)
    if exceptions_only:
        return {
            "missed_visits": models.SupervisorVisitPlan.objects.filter(
                status="MISSED", branch_id__in=branches
            ).count(),
            "outside_geofence": models.SiteVisit.objects.filter(
                verification_result__in=["WARNING", "FAILED"], branch_id__in=branches
            ).count(),
            "critical_findings": models.InspectionFinding.objects.filter(
                severity="CRITICAL", site__managing_branch_id__in=branches
            )
            .exclude(status__in=["CLOSED", "DISMISSED"])
            .count(),
            "overdue_corrective_actions": actions.filter(due_at__lt=timezone.now()).count(),
        }
    return {
        "today_planned_visits": plans.count(),
        "today_completed_visits": plans.filter(status="COMPLETED").count(),
        "visits_in_progress": models.SiteVisit.objects.filter(
            status="IN_PROGRESS", branch_id__in=branches
        ).count(),
        "missed_visits": plans.filter(status="MISSED").count(),
        "inspections_completed": models.SiteInspection.objects.filter(
            submitted_at__date=today, site__managing_branch_id__in=branches
        ).count(),
        "open_findings": models.InspectionFinding.objects.filter(
            status__in=["OPEN", "ACKNOWLEDGED", "ACTION_ASSIGNED"],
            site__managing_branch_id__in=branches,
        ).count(),
        "critical_findings": models.InspectionFinding.objects.filter(
            severity="CRITICAL", site__managing_branch_id__in=branches
        )
        .exclude(status__in=["CLOSED", "DISMISSED"])
        .count(),
        "open_corrective_actions": actions.count(),
        "overdue_corrective_actions": actions.filter(due_at__lt=timezone.now()).count(),
        "guard_discrepancies": models.GuardObservation.objects.filter(
            observed_at__date=today, site__managing_branch_id__in=branches
        )
        .exclude(observation_status="PRESENT_AS_SCHEDULED")
        .count(),
    }


class SupervisionSummaryView(APIView):
    permission_classes = [IsAuthenticated, RequiresPermission]
    required_permission = "supervision.view_supervision_dashboard"
    exceptions_only = False

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        branches = get_accessible_branch_ids(request.user, permission=self.required_permission)
        return Response(
            _supervision_summary(branches=branches, exceptions_only=self.exceptions_only)
        )


class SupervisionExceptionsView(SupervisionSummaryView):
    exceptions_only = True
