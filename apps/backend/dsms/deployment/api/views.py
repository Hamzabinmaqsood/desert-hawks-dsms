# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,no-untyped-call,arg-type,no-any-return,union-attr"
# ruff: noqa: E501
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.contracts.models import SecurityPost, SecuritySite
from dsms.identity import access
from dsms.identity.permissions import HasRBACPermission, RequiresPermission
from dsms.subscriptions.api.enforcement import TenantModuleViewMixin
from dsms.workforce.models import Employee

from .. import models, services
from ..exceptions import DeploymentError
from ..tenant_queries import (
    consistent_duty_assignments,
    consistent_employees,
    consistent_posts,
    consistent_sites,
    scoped_queryset,
)
from .serializers import SERIALIZERS, EmployeeActionSerializer, ReplacementRequestActionSerializer


def _service_call(function, **kwargs):
    try:
        return function(**kwargs)
    except DeploymentError as exc:
        raise ValidationError(str(exc)) from exc


class NoDeleteViewSet(
    TenantModuleViewMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("workforce_scheduling",)
    module_company_lookup = "company_id"
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _permission(self, verb: str) -> str:
        model = self.queryset.model
        return getattr(self, "custom_action_permissions", {}).get(
            self.action, f"deployment.{verb}_{model._meta.model_name}"
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
        branch = value("branch") or value("managing_branch")
        for name in ("pool", "roster_period", "duty_shift", "employee"):
            parent = value(name)
            if parent is None:
                continue
            company = company or getattr(parent, "company", None)
            branch = branch or getattr(parent, "branch", None)
            if name == "duty_shift":
                company = company or parent.company
                branch = branch or parent.branch
            if name == "employee":
                company = company or parent.company
                branch = branch or parent.branch
        site = value("site")
        company = company or getattr(site, "company", None) or getattr(branch, "company", None)
        branch = branch or getattr(site, "managing_branch", None)
        return {"company": company, "branch": branch}

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        self.require_modules_for(self._scope(serializer.validated_data).get("company"))
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
    TenantModuleViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("workforce_scheduling",)
    module_company_lookup = "company_id"
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "head", "options"]

    def _permission(self) -> str:
        model = self.queryset.model
        return getattr(self, "custom_action_permissions", {}).get(
            self.action, f"deployment.view_{model._meta.model_name}"
        )

    def get_queryset(self):
        return scoped_queryset(
            super().get_queryset(), user=self.request.user, permission=self._permission()
        )


def basic(model):
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    if model is models.EmployeeDeployment:
        ViewSet.required_module_ids = ("security_operations",)
    if model is models.DeploymentPoolMembership:
        ViewSet.module_company_lookup = "pool__company_id"

    return ViewSet


DeploymentViewSet = basic(models.EmployeeDeployment)
PoolViewSet = basic(models.DeploymentPool)
PoolMembershipViewSet = basic(models.DeploymentPoolMembership)
ShiftTemplateViewSet = basic(models.ShiftTemplate)
SchedulingPolicyViewSet = basic(models.SchedulingPolicy)
ScheduleBlockViewSet = basic(models.EmployeeScheduleBlock)


class RosterViewSet(NoDeleteViewSet):
    queryset = models.RosterPeriod.objects.select_related("company", "branch")
    serializer_class = SERIALIZERS["RosterPeriod"]
    custom_action_permissions = {
        "generate_demand": "deployment.generate_roster",
        "submit": "deployment.change_rosterperiod",
        "approve": "deployment.approve_roster",
        "publish": "deployment.publish_roster",
        "lock": "deployment.lock_roster",
    }

    @action(detail=True, methods=["post"], url_path="generate-demand")
    def generate_demand(self, request, pk=None):
        return Response(
            _service_call(
                services.generate_roster_demand,
                roster_period=self.get_object(),
                actor=request.user,
            )
        )

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(
            self.get_serializer(
                _service_call(services.submit_roster, roster=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(
            self.get_serializer(
                _service_call(services.approve_roster, roster=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        return Response(
            self.get_serializer(
                _service_call(services.publish_roster, roster=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        return Response(
            self.get_serializer(
                _service_call(services.lock_roster, roster=self.get_object(), actor=request.user)
            ).data
        )


class DutyShiftViewSet(NoDeleteViewSet):
    queryset = models.DutyShift.objects.select_related(
        "roster_period", "site", "post", "contract", "client"
    )
    serializer_class = SERIALIZERS["DutyShift"]
    custom_action_permissions = {
        "assign": "deployment.assign_employee",
        "coverage": "deployment.view_dutyshift",
    }

    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        shift = self.get_object()
        payload = EmployeeActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        employee = get_object_or_404(
            consistent_employees(
                Employee.objects.filter(company=shift.company, company__is_active=True)
            ),
            pk=payload.validated_data["employee"],
        )
        item = _service_call(
            services.assign_employee_to_shift,
            duty_shift=shift,
            employee=employee,
            actor=request.user,
        )
        return Response(
            SERIALIZERS["DutyAssignment"](item, context=self.get_serializer_context()).data,
            status=201,
        )

    @action(detail=True, methods=["get"], url_path="coverage")
    def coverage(self, request, pk=None):
        return Response(_service_call(services.get_shift_coverage, duty_shift=self.get_object()))


class DutyAssignmentViewSet(ReadOnlyWorkflowViewSet):
    module_company_lookup = "duty_shift__company_id"
    queryset = models.DutyAssignment.objects.select_related("employee", "duty_shift__roster_period")
    serializer_class = SERIALIZERS["DutyAssignment"]
    custom_action_permissions = {"request_replacement": "deployment.replace_employee"}

    @action(detail=True, methods=["post"], url_path="request-replacement")
    def request_replacement(self, request, pk=None):
        payload = ReplacementRequestActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        item = _service_call(
            services.create_replacement_request,
            original_assignment=self.get_object(),
            actor=request.user,
            reason=payload.validated_data["reason"],
            description=payload.validated_data["description"],
            priority=payload.validated_data["priority"],
        )
        return Response(
            SERIALIZERS["ReplacementRequest"](item, context=self.get_serializer_context()).data,
            status=201,
        )


class ReplacementRequestViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.ReplacementRequest.objects.select_related("duty_shift", "original_assignment")
    serializer_class = SERIALIZERS["ReplacementRequest"]
    custom_action_permissions = {"assign_replacement": "deployment.replace_employee"}

    @action(detail=True, methods=["post"], url_path="assign-replacement")
    def assign_replacement(self, request, pk=None):
        replacement_request = self.get_object()
        payload = EmployeeActionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        employee = get_object_or_404(
            consistent_employees(
                Employee.objects.filter(
                    company=replacement_request.company, company__is_active=True
                )
            ),
            pk=payload.validated_data["employee"],
        )
        item = _service_call(
            services.assign_replacement,
            replacement_request=replacement_request,
            employee=employee,
            actor=request.user,
        )
        return Response(
            SERIALIZERS["DutyAssignment"](item, context=self.get_serializer_context()).data,
            status=201,
        )


class RosterChangeViewSet(ReadOnlyWorkflowViewSet):
    module_company_lookup = "roster_period__company_id"
    queryset = models.RosterChangeEvent.objects.select_related(
        "roster_period", "duty_shift", "duty_assignment"
    )
    serializer_class = SERIALIZERS["RosterChangeEvent"]


class AvailabilityConflictViewSet(ReadOnlyWorkflowViewSet):
    queryset = models.RosterAvailabilityConflict.objects.select_related(
        "duty_assignment__duty_shift", "leave_request", "replacement_request"
    )
    serializer_class = SERIALIZERS["RosterAvailabilityConflict"]


class DeploymentEligibilityView(TenantModuleViewMixin, APIView):
    required_module_ids = ("workforce_scheduling",)
    permission_classes = [IsAuthenticated, RequiresPermission]
    required_permission = "deployment.view_dutyshift"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, employee_id):
        branch_ids = access.get_accessible_branch_ids(
            request.user, permission=self.required_permission
        )
        employee = get_object_or_404(
            consistent_employees(Employee.objects.select_related("branch")),
            pk=employee_id,
            branch_id__in=branch_ids,
        )
        site = get_object_or_404(
            consistent_sites(
                SecuritySite.objects.select_related("client", "contract", "managing_branch")
            ),
            pk=request.query_params.get("site"),
            company=employee.company,
            managing_branch_id__in=branch_ids,
        )
        post = None
        if request.query_params.get("post"):
            post = get_object_or_404(
                consistent_posts(SecurityPost.objects.select_related("site")),
                pk=request.query_params["post"],
                company=employee.company,
                site=site,
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


class DeploymentDashboardView(TenantModuleViewMixin, APIView):
    required_module_ids = ("workforce_scheduling",)
    permission_classes = [IsAuthenticated, RequiresPermission]
    required_permission = "deployment.view_dutyshift"

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        branch_ids = access.get_accessible_branch_ids(
            request.user, permission=self.required_permission
        )
        today = timezone.localdate()
        shifts = scoped_queryset(
            models.DutyShift.objects.filter(duty_date=today).exclude(status="CANCELLED"),
            user=request.user,
            permission=self.required_permission,
        )
        required = shifts.aggregate(v=Sum("required_headcount"))["v"] or 0
        assignments = consistent_duty_assignments(
            models.DutyAssignment.objects.filter(
                duty_shift__in=shifts, status__in=["PLANNED", "CONFIRMED"]
            )
        )
        assigned = assignments.count()
        deployments = scoped_queryset(
            models.EmployeeDeployment.objects.filter(status="ACTIVE"),
            user=request.user,
            permission=self.required_permission,
        )
        return Response(
            {
                "active_deployments": deployments.filter(managing_branch_id__in=branch_ids).count(),
                "today_planned_duty_shifts": shifts.count(),
                "today_required_positions": required,
                "today_assigned_positions": assigned,
                "unfilled_positions": max(required - assigned, 0),
                "planned_coverage_percentage": str(assigned * 100 / required if required else 0),
                "attendance_records_created": 0,
            }
        )
