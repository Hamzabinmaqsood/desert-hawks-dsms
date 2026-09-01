# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,no-untyped-call,arg-type"
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.identity.access import filter_queryset_by_scope, get_accessible_branch_ids
from dsms.identity.permissions import HasRBACPermission, RequiresPermission
from dsms.workforce.models import Employee

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


class RosterViewSet(NoDeleteViewSet):
    queryset = models.RosterPeriod.objects.select_related("company", "branch")
    serializer_class = SERIALIZERS["RosterPeriod"]
    custom_action_permissions = {
        "generate_demand": "deployment.generate_roster",
        "approve": "deployment.approve_roster",
        "publish": "deployment.publish_roster",
        "lock": "deployment.lock_roster",
    }

    @action(detail=True, methods=["post"], url_path="generate-demand")
    def generate_demand(self, request, pk=None):
        return Response(
            services.generate_roster_demand(roster_period=self.get_object(), actor=request.user)
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.submit_roster(roster=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.approve_roster(roster=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.publish_roster(roster=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.lock_roster(roster=self.get_object(), actor=request.user)
            ).data
        )


class DutyShiftViewSet(NoDeleteViewSet):
    queryset = models.DutyShift.objects.select_related(
        "roster_period", "site", "post", "contract", "client"
    )
    serializer_class = SERIALIZERS["DutyShift"]
    custom_action_permissions = {"assign": "deployment.assign_employee"}

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        item = services.assign_employee_to_shift(
            duty_shift=self.get_object(),
            employee=Employee.objects.get(pk=request.data["employee"]),
            actor=request.user,
        )
        return Response(SERIALIZERS["DutyAssignment"](item).data, status=201)

    @action(detail=True, methods=["get"], url_path="coverage")
    def coverage(self, request, pk=None):
        return Response(services.get_shift_coverage(self.get_object()))


DeploymentViewSet = basic(models.EmployeeDeployment)
PoolViewSet = basic(models.DeploymentPool)
PoolMembershipViewSet = basic(models.DeploymentPoolMembership)
ShiftTemplateViewSet = basic(models.ShiftTemplate)
SchedulingPolicyViewSet = basic(models.SchedulingPolicy)


class DutyAssignmentViewSet(NoDeleteViewSet):
    queryset = models.DutyAssignment.objects.select_related("employee", "duty_shift__roster_period")
    serializer_class = SERIALIZERS["DutyAssignment"]
    custom_action_permissions = {"request_replacement": "deployment.replace_employee"}

    @action(detail=True, methods=["post"], url_path="request-replacement")
    def request_replacement(self, request, pk=None):
        item = services.create_replacement_request(
            original_assignment=self.get_object(),
            actor=request.user,
            reason=request.data.get("reason", "OTHER"),
            description=request.data.get("description", ""),
            priority=request.data.get("priority", "NORMAL"),
        )
        return Response(SERIALIZERS["ReplacementRequest"](item).data, status=201)


ScheduleBlockViewSet = basic(models.EmployeeScheduleBlock)


class ReplacementRequestViewSet(NoDeleteViewSet):
    queryset = models.ReplacementRequest.objects.select_related("duty_shift", "original_assignment")
    serializer_class = SERIALIZERS["ReplacementRequest"]
    custom_action_permissions = {"assign_replacement": "deployment.replace_employee"}

    @action(detail=True, methods=["post"], url_path="assign-replacement")
    def assign_replacement(self, request, pk=None):
        item = services.assign_replacement(
            replacement_request=self.get_object(),
            employee=Employee.objects.get(pk=request.data["employee"]),
            actor=request.user,
        )
        return Response(SERIALIZERS["DutyAssignment"](item).data, status=201)


RosterChangeViewSet = basic(models.RosterChangeEvent)
AvailabilityConflictViewSet = basic(models.RosterAvailabilityConflict)


class DeploymentEligibilityView(APIView):
    permission_classes = [IsAuthenticated, RequiresPermission]
    required_permission = "deployment.view_dutyshift"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, employee_id):
        from dsms.contracts.models import SecurityPost, SecuritySite

        branch_ids = get_accessible_branch_ids(request.user, permission=self.required_permission)
        employee = get_object_or_404(
            Employee.objects.select_related("branch"), pk=employee_id, branch_id__in=branch_ids
        )
        site = get_object_or_404(
            SecuritySite.objects.select_related("client", "contract", "managing_branch"),
            pk=request.query_params.get("site"),
            managing_branch_id__in=branch_ids,
        )
        post = None
        if request.query_params.get("post"):
            post = get_object_or_404(
                SecurityPost.objects.select_related("site"),
                pk=request.query_params["post"],
                site=site,
                site__managing_branch_id__in=branch_ids,
            )
        result = services.evaluate_deployment_eligibility(employee=employee, site=site, post=post)
        return Response(
            {
                "employee_id": str(employee.pk),
                "status": result.status,
                "blocking_reasons": result.blocking_reasons,
                "warnings": result.warnings,
            }
        )


class DeploymentDashboardView(APIView):
    permission_classes = [IsAuthenticated, RequiresPermission]
    required_permission = "deployment.view_dutyshift"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from django.db.models import Sum
        from django.utils import timezone

        today = timezone.localdate()
        branch_ids = get_accessible_branch_ids(request.user, permission=self.required_permission)
        shifts = models.DutyShift.objects.filter(duty_date=today, branch_id__in=branch_ids).exclude(
            status="CANCELLED"
        )
        required = shifts.aggregate(v=Sum("required_headcount"))["v"] or 0
        assigned = models.DutyAssignment.objects.filter(
            duty_shift__in=shifts, status__in=["PLANNED", "CONFIRMED"]
        ).count()
        return Response(
            {
                "active_deployments": models.EmployeeDeployment.objects.filter(
                    status="ACTIVE", managing_branch_id__in=branch_ids
                ).count(),
                "today_planned_duty_shifts": shifts.count(),
                "today_required_positions": required,
                "today_assigned_positions": assigned,
                "unfilled_positions": max(required - assigned, 0),
                "planned_coverage_percentage": str(assigned * 100 / required if required else 0),
                "attendance_records_created": 0,
            }
        )
