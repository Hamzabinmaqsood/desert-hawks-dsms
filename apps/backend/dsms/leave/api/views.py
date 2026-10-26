# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg"
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.deployment.tenant_queries import consistent_employees, consistent_leave_requests
from dsms.identity import access
from dsms.leave.models import Holiday, LeaveRequest, LeaveType
from dsms.leave.services import (
    create_leave_request,
    evaluate_employee_availability,
    finalize_leave_approval,
    get_leave_balance,
    reject_leave_request,
    request_leave_cancellation,
    submit_leave_request,
)
from dsms.subscriptions.api.enforcement import TenantModuleViewMixin
from dsms.workforce.models import Employee

from .serializers import (
    AvailabilitySerializer,
    HolidaySerializer,
    LeaveBalanceSerializer,
    LeaveDecisionSerializer,
    LeaveRequestSerializer,
    LeaveTypeSerializer,
    ManagerLeaveRequestSerializer,
    TeamLeaveSerializer,
)


def own_employee(user):
    return get_object_or_404(consistent_employees(Employee.objects.all()), user=user)


def require_employee_permission(user, employee, permission):
    if not access.has_permission(
        user=user,
        permission=permission,
        company=employee.company,
        region=employee.branch.region if employee.branch else None,
        branch=employee.branch,
        department=employee.department,
    ):
        raise PermissionDenied("You do not have permission for this leave operation.")


def scoped_leave_requests(user, permission):
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    department_ids = access.get_accessible_department_ids(user, permission=permission)
    return consistent_leave_requests(LeaveRequest.objects.all()).filter(
        Q(employee__company_id__in=company_ids)
        | Q(employee__branch_id__in=branch_ids)
        | Q(employee__department_id__in=department_ids)
    )


class LeaveTypeViewSet(
    TenantModuleViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("leave",)
    module_company_lookup = "company_id"
    module_allow_global_rows = True
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveTypeSerializer
    queryset = LeaveType.objects.none()

    def get_queryset(self):
        employee = own_employee(self.request.user)
        return (
            LeaveType.objects.filter(status="ACTIVE")
            .filter(Q(company__isnull=True) | Q(company=employee.company))
            .order_by("sort_order", "code", "pk")
        )


class MyLeaveRequestViewSet(
    TenantModuleViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("leave",)
    module_company_lookup = "employee__company_id"
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveRequestSerializer
    filterset_fields = ["status", "leave_type"]
    ordering_fields = ["starts_at", "ends_at", "created_at"]
    queryset = LeaveRequest.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        employee = own_employee(self.request.user)
        require_employee_permission(self.request.user, employee, "leave.view_own_leave_request")
        return consistent_leave_requests(
            LeaveRequest.objects.filter(employee=employee)
        ).select_related("leave_type", "policy")

    def create(self, request, *args, **kwargs):
        employee = own_employee(request.user)
        require_employee_permission(request.user, employee, "leave.create_own_leave_request")
        self.require_modules_for(employee)
        leave_type = get_object_or_404(
            LeaveType.objects.filter(Q(company__isnull=True) | Q(company=employee.company)),
            pk=request.data.get("leave_type"),
            status="ACTIVE",
        )
        payload = LeaveRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            item = create_leave_request(
                actor=request.user,
                employee=employee,
                leave_type=leave_type,
                starts_at=payload.validated_data["starts_at"],
                ends_at=payload.validated_data["ends_at"],
                reason=payload.validated_data["reason"],
                emergency_request=payload.validated_data.get("emergency_request", False),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(item).data, status=201)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        employee = own_employee(request.user)
        require_employee_permission(request.user, employee, "leave.change_own_draft_leave_request")
        try:
            item = submit_leave_request(request=self.get_object(), actor=request.user)
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"], url_path="request-cancellation")
    def request_cancellation(self, request, pk=None):
        employee = own_employee(request.user)
        require_employee_permission(request.user, employee, "leave.request_leave_cancellation")
        payload = LeaveDecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            item = request_leave_cancellation(
                request=self.get_object(),
                actor=request.user,
                reason=payload.validated_data.get("reason", ""),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(item).data)

    @action(detail=False, methods=["post"])
    def availability(self, request):
        employee = own_employee(request.user)
        require_employee_permission(request.user, employee, "leave.view_own_leave_request")
        payload = AvailabilitySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = evaluate_employee_availability(employee=employee, **payload.validated_data)
        return Response(
            {
                "availability_status": result.availability_status,
                "blocking_reasons": result.blocking_reasons,
                "warnings": result.warnings,
            }
        )


class MyLeaveBalanceViewSet(TenantModuleViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    required_module_ids = ("leave",)
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveBalanceSerializer

    def list(self, request, *args, **kwargs):
        employee = own_employee(request.user)
        require_employee_permission(request.user, employee, "leave.view_own_leave_request")
        leave_types = (
            LeaveType.objects.filter(status="ACTIVE")
            .filter(Q(company__isnull=True) | Q(company=employee.company))
            .order_by("sort_order", "code")
        )
        rows = []
        for leave_type in leave_types:
            balance = get_leave_balance(employee=employee, leave_type=leave_type)
            rows.append(
                {
                    "leave_type": leave_type.pk,
                    "leave_type_name": leave_type.name,
                    "unit": leave_type.unit,
                    **balance,
                }
            )
        return Response(self.get_serializer(rows, many=True).data)


class ManagerLeaveRequestViewSet(
    TenantModuleViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("leave",)
    module_company_lookup = "employee__company_id"
    permission_classes = [IsAuthenticated]
    serializer_class = ManagerLeaveRequestSerializer
    filterset_fields = ["status", "leave_type", "employee", "employee__branch"]
    ordering_fields = ["starts_at", "ends_at", "created_at"]
    queryset = LeaveRequest.objects.none()

    def get_scope_permission(self):
        return {
            "approve": "leave.approve_leave_request",
            "reject": "leave.reject_leave_request",
        }.get(self.action, "leave.view_team_availability")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return (
            scoped_leave_requests(self.request.user, self.get_scope_permission())
            .select_related("employee__branch", "employee__department", "leave_type", "policy")
            .order_by("-created_at")
        )

    def _decision(self, request, function):
        item = self.get_object()
        permission = self.get_scope_permission()
        require_employee_permission(request.user, item.employee, permission)
        payload = LeaveDecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            item = function(
                request=item,
                actor=request.user,
                **(
                    {"comments": payload.validated_data.get("reason", "")}
                    if function is finalize_leave_approval
                    else {"reason": payload.validated_data.get("reason", "")}
                ),
            )
        except ValueError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self._decision(request, finalize_leave_approval)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self._decision(request, reject_leave_request)


class TeamLeaveCalendarViewSet(
    TenantModuleViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    required_module_ids = ("leave",)
    module_company_lookup = "employee__company_id"
    permission_classes = [IsAuthenticated]
    serializer_class = TeamLeaveSerializer
    queryset = LeaveRequest.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return (
            scoped_leave_requests(self.request.user, "leave.view_team_availability")
            .filter(status__in=["APPROVED", "IN_PROGRESS", "COMPLETED"])
            .select_related("employee", "leave_type")
            .order_by("starts_at")
        )


class HolidayViewSet(TenantModuleViewMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    required_module_ids = ("leave",)
    module_company_lookup = "calendar__company_id"
    permission_classes = [IsAuthenticated]
    serializer_class = HolidaySerializer
    queryset = Holiday.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        employee = own_employee(self.request.user)
        require_employee_permission(self.request.user, employee, "leave.view_own_leave_request")
        return (
            Holiday.objects.filter(calendar__company=employee.company, status="ACTIVE")
            .filter(Q(calendar__branch__isnull=True) | Q(calendar__branch=employee.branch))
            .select_related("calendar")
            .order_by("date", "name")
        )
