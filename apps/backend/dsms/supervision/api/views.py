# mypy: disable-error-code="attr-defined,no-untyped-def,type-arg,no-untyped-call,arg-type,no-any-return,union-attr"
# ruff: noqa: E501
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.identity import access
from dsms.identity.permissions import HasRBACPermission, RequiresPermission

from .. import models, services
from ..exceptions import SupervisionPermissionError, SupervisionValidationError
from ..tenant_queries import scoped_queryset
from .serializers import SERIALIZERS


def _service_call(function, **kwargs):
    try:
        return function(**kwargs)
    except SupervisionPermissionError as exc:
        raise PermissionDenied(str(exc)) from exc
    except SupervisionValidationError as exc:
        raise ValidationError(str(exc)) from exc


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
        return scoped_queryset(
            super().get_queryset(),
            user=self.request.user,
            permission=self._permission("view"),
        )

    def _permission(self, verb: str) -> str:
        model = self.queryset.model
        return getattr(self, "custom_action_permissions", {}).get(
            self.action, f"supervision.{verb}_{model._meta.model_name}"
        )

    @staticmethod
    def _scope(data, instance=None):
        def value(name):
            return data.get(name, getattr(instance, name, None))

        company = value("company")
        branch = value("branch")
        site = value("site")
        for parent_name in ("inspection", "site_visit", "finding"):
            parent = value(parent_name)
            if parent is not None:
                company = company or getattr(parent, "company", None)
                site = site or getattr(parent, "site", None)
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
        if not access.has_permission(
            user=self.request.user,
            permission=self._permission("change"),
            **self._scope(serializer.validated_data, serializer.instance),
        ):
            raise PermissionDenied("You cannot update this resource in the resulting scope.")
        serializer.save()


class ReadOnlyWorkflowViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "head", "options"]

    def _permission(self, verb: str) -> str:
        model = self.queryset.model
        return getattr(self, "custom_action_permissions", {}).get(
            self.action, f"supervision.{verb}_{model._meta.model_name}"
        )

    def get_queryset(self):
        return scoped_queryset(
            super().get_queryset(),
            user=self.request.user,
            permission=self._permission("view"),
        )


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
        from dsms.incidents.exceptions import IncidentValidationError
        from dsms.incidents.services import refer_supervision_finding_to_incident

        try:
            incident = refer_supervision_finding_to_incident(
                finding=self.get_object(), actor=request.user, reason=request.data.get("reason", "")
            )
        except IncidentValidationError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(
            {"incident_id": str(incident.id), "incident_number": incident.incident_number},
            status=201,
        )


class VisitPlanViewSet(NoDeleteViewSet):
    queryset = models.SupervisorVisitPlan.objects.select_related("supervisor", "site", "branch")
    serializer_class = SERIALIZERS["SupervisorVisitPlan"]
    custom_action_permissions = {"cancel": "supervision.change_supervisorvisitplan"}

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        plan = self.get_object()
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response({"reason": ["This field is required."]}, status=400)
        plan.status, plan.cancellation_reason = "CANCELLED", reason
        plan.save()
        return Response(self.get_serializer(plan).data)


class VisitViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.SiteVisit.objects.select_related("supervisor", "site", "branch", "visit_plan")
    serializer_class = SERIALIZERS["SiteVisit"]
    custom_action_permissions = {
        "start": "supervision.start_site_visit",
        "end": "supervision.end_site_visit",
        "verify_guard": "supervision.verify_guard",
    }

    @action(detail=False, methods=["post"])
    def start(self, request):
        permission = "supervision.start_site_visit"
        branch_ids = access.get_accessible_branch_ids(request.user, permission=permission)
        company_ids = access.get_accessible_company_ids(request.user, permission=permission)
        supervisor = get_object_or_404(
            models.Employee.objects.filter(company_id__in=company_ids, company__is_active=True),
            pk=request.data["supervisor"],
        )
        site = get_object_or_404(
            models.SecuritySite.objects.filter(
                company_id__in=company_ids,
                company__is_active=True,
                managing_branch_id__in=branch_ids,
            ).filter(
                client__company_id=F("company_id"),
                contract__company_id=F("company_id"),
                managing_branch__company_id=F("company_id"),
            ),
            pk=request.data["site"],
        )
        visit = _service_call(
            services.start_site_visit,
            actor=request.user,
            supervisor=supervisor,
            site=site,
            gps=request.data.get("gps"),
        )
        return Response(self.get_serializer(visit).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        visit = _service_call(
            services.end_site_visit,
            visit=self.get_object(),
            actor=request.user,
            summary=request.data.get("summary", ""),
            gps=request.data.get("gps"),
        )
        return Response(self.get_serializer(visit).data)

    @action(detail=True, methods=["post"], url_path="verify-guard")
    def verify_guard(self, request, pk=None):
        visit = self.get_object()
        employee = (
            models.Employee.objects.filter(
                pk=request.data.get("employee"),
                company=visit.company,
                company__is_active=True,
            )
            .filter(Q(branch__isnull=True) | Q(branch__company=visit.company))
            .first()
        )
        if request.data.get("employee") and employee is None:
            raise PermissionDenied("Employee is unavailable in this visit scope.")
        result = _service_call(
            services.verify_guard_during_visit,
            site_visit=visit,
            post=get_object_or_404(
                models.SecurityPost.objects.filter(
                    company=visit.company,
                    site=visit.site,
                    client=visit.site.client,
                    company__is_active=True,
                ),
                pk=request.data["post"],
            ),
            employee=employee,
            observed_at=timezone.now(),
            actor=request.user,
        )
        return Response(result)


class InspectionViewSet(NoDeleteViewSet):
    queryset = models.SiteInspection.objects.select_related("site_visit", "site", "template")
    serializer_class = SERIALIZERS["SiteInspection"]
    custom_action_permissions = {"submit": "supervision.change_siteinspection"}

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        inspection = _service_call(services.submit_inspection, inspection=self.get_object())
        return Response(self.get_serializer(inspection).data)


class CorrectiveActionViewSet(NoDeleteViewSet):
    queryset = models.CorrectiveAction.objects.select_related("finding", "site")
    serializer_class = SERIALIZERS["CorrectiveAction"]
    custom_action_permissions = {"transition": "supervision.change_correctiveaction"}

    @action(detail=True, methods=["post"])
    def transition(self, request, pk=None):
        obj = _service_call(
            services.transition_corrective_action,
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
        return scoped_queryset(
            self.queryset,
            user=self.request.user,
            permission="supervision.view_guard_observation",
        ).order_by("id")


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
        return scoped_queryset(
            self.queryset,
            user=self.request.user,
            permission="supervision.view_sensitive_field_evidence",
        ).order_by("id")


def _supervision_summary(*, user, permission, exceptions_only=False):
    today = timezone.localdate()
    plans = scoped_queryset(
        models.SupervisorVisitPlan.objects.filter(planned_date=today),
        user=user,
        permission=permission,
    )
    visits = scoped_queryset(models.SiteVisit.objects.all(), user=user, permission=permission)
    inspections = scoped_queryset(
        models.SiteInspection.objects.all(), user=user, permission=permission
    )
    findings = scoped_queryset(
        models.InspectionFinding.objects.all(), user=user, permission=permission
    )
    actions = scoped_queryset(
        models.CorrectiveAction.objects.all(), user=user, permission=permission
    ).exclude(status__in=["VERIFIED", "CLOSED", "CANCELLED"])
    observations = scoped_queryset(
        models.GuardObservation.objects.all(), user=user, permission=permission
    )
    if exceptions_only:
        return {
            "missed_visits": plans.filter(status="MISSED").count(),
            "outside_geofence": visits.filter(
                verification_result__in=["WARNING", "FAILED"]
            ).count(),
            "critical_findings": findings.filter(severity="CRITICAL")
            .exclude(status__in=["CLOSED", "DISMISSED"])
            .count(),
            "overdue_corrective_actions": actions.filter(due_at__lt=timezone.now()).count(),
        }
    return {
        "today_planned_visits": plans.count(),
        "today_completed_visits": plans.filter(status="COMPLETED").count(),
        "visits_in_progress": visits.filter(status="IN_PROGRESS").count(),
        "missed_visits": plans.filter(status="MISSED").count(),
        "inspections_completed": inspections.filter(submitted_at__date=today).count(),
        "open_findings": findings.filter(
            status__in=["OPEN", "ACKNOWLEDGED", "ACTION_ASSIGNED"]
        ).count(),
        "critical_findings": findings.filter(severity="CRITICAL")
        .exclude(status__in=["CLOSED", "DISMISSED"])
        .count(),
        "open_corrective_actions": actions.count(),
        "overdue_corrective_actions": actions.filter(due_at__lt=timezone.now()).count(),
        "guard_discrepancies": observations.filter(observed_at__date=today)
        .exclude(observation_status="PRESENT_AS_SCHEDULED")
        .count(),
    }


class SupervisionSummaryView(APIView):
    permission_classes = [IsAuthenticated, RequiresPermission]
    required_permission = "supervision.view_supervision_dashboard"
    exceptions_only = False

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            _supervision_summary(
                user=request.user,
                permission=self.required_permission,
                exceptions_only=self.exceptions_only,
            )
        )


class SupervisionExceptionsView(SupervisionSummaryView):
    exceptions_only = True
