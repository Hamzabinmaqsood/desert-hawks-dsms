# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg"
from django.shortcuts import get_object_or_404
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.leave.models import LeaveRequest, LeaveType
from dsms.leave.services import (
    create_leave_request,
    evaluate_employee_availability,
    submit_leave_request,
)
from dsms.workforce.models import Employee

from .serializers import AvailabilitySerializer, LeaveRequestSerializer, LeaveTypeSerializer


def own_employee(user):
    return get_object_or_404(Employee, user=user)


class LeaveTypeViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveTypeSerializer
    queryset = LeaveType.objects.filter(status="ACTIVE")


class MyLeaveRequestViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveRequestSerializer
    filterset_fields = ["status", "leave_type"]
    ordering_fields = ["starts_at", "ends_at", "created_at"]
    queryset = LeaveRequest.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return LeaveRequest.objects.filter(employee=own_employee(self.request.user)).select_related(
            "leave_type", "policy"
        )

    def create(self, request, *args, **kwargs):
        employee = own_employee(request.user)
        leave_type = get_object_or_404(
            LeaveType, pk=request.data.get("leave_type"), status="ACTIVE"
        )
        payload = LeaveRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        item = create_leave_request(
            actor=request.user,
            employee=employee,
            leave_type=leave_type,
            starts_at=payload.validated_data["starts_at"],
            ends_at=payload.validated_data["ends_at"],
            reason=payload.validated_data["reason"],
            emergency_request=payload.validated_data.get("emergency_request", False),
        )
        return Response(self.get_serializer(item).data, status=201)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(
            self.get_serializer(
                submit_leave_request(request=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=False, methods=["post"])
    def availability(self, request):
        payload = AvailabilitySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = evaluate_employee_availability(
            employee=own_employee(request.user), **payload.validated_data
        )
        return Response(
            {
                "availability_status": result.availability_status,
                "blocking_reasons": result.blocking_reasons,
                "warnings": result.warnings,
            }
        )
