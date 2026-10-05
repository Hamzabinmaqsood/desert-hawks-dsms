# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,no-untyped-call,arg-type,no-any-return,union-attr,assignment"
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

from dsms.identity import access
from dsms.identity.permissions import HasRBACPermission

from .. import models, services
from ..exceptions import AttendancePermissionError, AttendanceValidationError
from ..tenant_queries import (
    consistent_attendance_exceptions,
    consistent_duty_assignments,
    consistent_queryset,
    scoped_queryset,
)
from .serializers import SERIALIZERS, AttendanceQRStationSerializer, AttendanceRecordSerializer


def _service_call(function, **kwargs):
    try:
        return function(**kwargs)
    except AttendancePermissionError as exc:
        raise PermissionDenied(str(exc)) from exc
    except AttendanceValidationError as exc:
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
        model = super().get_queryset().model
        permission = getattr(self, "custom_action_permissions", {}).get(
            self.action, f"attendance.view_{model._meta.model_name}"
        )
        return scoped_queryset(
            super().get_queryset(),
            user=self.request.user,
            permission=permission,
        )

    def _permission(self, verb: str) -> str:
        model = self.get_queryset().model
        return getattr(self, "custom_action_permissions", {}).get(
            self.action, f"attendance.{verb}_{model._meta.model_name}"
        )

    def _scope(self, data):
        company = data.get("company")
        branch = data.get("branch")
        site = data.get("site")
        return {
            "company": company,
            "branch": branch or getattr(site, "managing_branch", None),
        }

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        if not access.has_permission(
            user=self.request.user,
            permission=self._permission("add"),
            **self._scope(serializer.validated_data),
        ):
            raise PermissionDenied("You cannot create this resource in the requested scope.")
        serializer.save()

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        instance = serializer.instance
        resulting = {
            "company": serializer.validated_data.get("company", instance.company),
            "branch": serializer.validated_data.get("branch", getattr(instance, "branch", None)),
            "site": serializer.validated_data.get("site", getattr(instance, "site", None)),
        }
        if not access.has_permission(
            user=self.request.user,
            permission=self._permission("change"),
            **self._scope(resulting),
        ):
            raise PermissionDenied("You cannot update this resource in the resulting scope.")
        serializer.save()


class ReadOnlyEvidenceViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        model = super().get_queryset().model
        permission = getattr(self, "custom_action_permissions", {}).get(
            self.action, f"attendance.view_{model._meta.model_name}"
        )
        return scoped_queryset(
            super().get_queryset(),
            user=self.request.user,
            permission=permission,
        )


def basic(model):
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    return ViewSet


class QRStationViewSet(NoDeleteViewSet):
    queryset = models.AttendanceQRStation.objects.select_related("company", "site", "post")
    serializer_class = AttendanceQRStationSerializer
    custom_action_permissions = {"rotate": "attendance.change_attendanceqrstation"}

    @action(detail=True, methods=["post"])
    def rotate(self, request, pk=None):
        station = self.get_object()
        token = _service_call(services.generate_qr_station_token, station=station)
        return Response({"station_id": str(station.pk), "token": token})


class AttendanceRecordViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "check_in": "attendance.perform_own_checkin",
        "check_out": "attendance.perform_own_checkout",
        "verify": "attendance.change_attendancerecord",
        "correction_request": "attendance.add_attendancecorrectionrequest",
        "post_lock_adjustment": "attendance.change_attendancerecord",
    }
    queryset = models.AttendanceRecord.objects.select_related(
        "employee", "site", "post", "duty_assignment"
    )
    serializer_class = AttendanceRecordSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        permission = self.custom_action_permissions.get(
            self.action,
            f"attendance.view_{self.queryset.model._meta.model_name}",
        )
        return scoped_queryset(queryset, user=self.request.user, permission=permission)

    @action(detail=False, methods=["post"], url_path="check-in")
    def check_in(self, request):
        from django.utils.dateparse import parse_datetime

        from dsms.deployment.models import DutyAssignment

        assignments = consistent_duty_assignments(
            DutyAssignment.objects.select_related("employee__user", "duty_shift__branch")
        ).filter(
            employee__user=request.user,
            duty_shift__branch_id__in=access.get_accessible_branch_ids(
                request.user, permission="attendance.perform_own_checkin"
            ),
        )
        item = _service_call(
            services.check_in_for_duty,
            user=request.user,
            duty_assignment=get_object_or_404(assignments, pk=request.data["duty_assignment"]),
            event_time=parse_datetime(request.data.get("event_time", "")) or timezone.now(),
            gps=request.data.get("gps"),
            qr=request.data.get("qr"),
            client_event_id=request.data.get("client_event_id"),
            device_metadata=request.data.get("device_metadata"),
        )
        return Response(self.get_serializer(item).data, status=201)

    @action(detail=False, methods=["post"], url_path="check-out")
    def check_out(self, request):
        from django.utils.dateparse import parse_datetime

        from dsms.deployment.models import DutyAssignment

        assignments = consistent_duty_assignments(
            DutyAssignment.objects.select_related("employee__user", "duty_shift__branch")
        ).filter(
            employee__user=request.user,
            duty_shift__branch_id__in=access.get_accessible_branch_ids(
                request.user, permission="attendance.perform_own_checkout"
            ),
        )
        item = _service_call(
            services.check_out_from_duty,
            user=request.user,
            duty_assignment=get_object_or_404(assignments, pk=request.data["duty_assignment"]),
            event_time=parse_datetime(request.data.get("event_time", "")) or timezone.now(),
            client_event_id=request.data.get("client_event_id"),
        )
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        return Response(
            self.get_serializer(
                _service_call(
                    services.verify_attendance, record=self.get_object(), actor=request.user
                )
            ).data
        )

    @action(detail=True, methods=["post"], url_path="correction-request")
    def correction_request(self, request, pk=None):
        item = _service_call(
            services.request_attendance_correction,
            record=self.get_object(),
            actor=request.user,
            reason=request.data.get("reason", ""),
            proposed_check_in_at=request.data.get("proposed_check_in_at"),
            proposed_check_out_at=request.data.get("proposed_check_out_at"),
            proposed_outcome=request.data.get("proposed_outcome", ""),
            proposed_approved_worked_minutes=request.data.get("proposed_approved_worked_minutes"),
            proposed_overtime_minutes=request.data.get("proposed_overtime_minutes"),
        )
        return Response(SERIALIZERS["AttendanceCorrectionRequest"](item).data, status=201)

    @action(detail=True, methods=["post"], url_path="post-lock-adjustment")
    def post_lock_adjustment(self, request, pk=None):
        _service_call(
            services.flag_post_lock_adjustment,
            record=self.get_object(),
            actor=request.user,
            reason=request.data.get("reason", ""),
        )
        return Response({"status": "PAYROLL_ADJUSTMENT_REQUIRED"})


PolicyViewSet = basic(models.AttendancePolicy)


class PeriodViewSet(NoDeleteViewSet):
    queryset = models.AttendancePeriod.objects.select_related("company", "branch")
    serializer_class = SERIALIZERS["AttendancePeriod"]
    custom_action_permissions = {
        "generate_expected": "attendance.change_attendanceperiod",
        "approve": "attendance.change_attendanceperiod",
        "lock": "attendance.change_attendanceperiod",
    }

    @action(detail=True, methods=["post"], url_path="generate-expected")
    def generate_expected(self, request, pk=None):
        return Response(
            {
                "created": _service_call(
                    services.generate_expected_attendance,
                    attendance_period=self.get_object(),
                )
            }
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(
            self.get_serializer(
                _service_call(
                    services.approve_attendance_period,
                    period=self.get_object(),
                    actor=request.user,
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def lock(self, request, pk=None):
        return Response(
            self.get_serializer(
                _service_call(
                    services.lock_attendance_period,
                    period=self.get_object(),
                    actor=request.user,
                )
            ).data
        )


class CorrectionViewSet(ReadOnlyEvidenceViewSet):
    http_method_names = ["get", "post", "head", "options"]
    queryset = models.AttendanceCorrectionRequest.objects.select_related("attendance_record")
    serializer_class = SERIALIZERS["AttendanceCorrectionRequest"]
    custom_action_permissions = {"approve": "attendance.change_attendancecorrectionrequest"}

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        record = _service_call(
            services.approve_attendance_correction,
            correction=self.get_object(),
            actor=request.user,
            notes=request.data.get("notes", ""),
        )
        return Response(AttendanceRecordSerializer(record).data)


class ExceptionViewSet(ReadOnlyEvidenceViewSet):
    queryset = models.AttendanceException.objects.select_related(
        "attendance_record", "attendance_event"
    )
    serializer_class = SERIALIZERS["AttendanceException"]


class EventViewSet(ReadOnlyEvidenceViewSet):
    queryset = models.AttendanceEvent.objects.select_related(
        "attendance_record", "subject_employee", "actor_user"
    )
    serializer_class = SERIALIZERS["AttendanceEvent"]


class VerificationViewSet(ReadOnlyEvidenceViewSet):
    queryset = models.AttendanceVerification.objects.select_related(
        "attendance_event", "qr_station", "verified_by"
    )
    serializer_class = SERIALIZERS["AttendanceVerification"]


class ChangeEventViewSet(ReadOnlyEvidenceViewSet):
    queryset = models.AttendanceChangeEvent.objects.all()
    serializer_class = SERIALIZERS["AttendanceChangeEvent"]


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    from django.utils import timezone

    today = timezone.localdate()
    permission = "attendance.view_attendancerecord"
    if permission not in access.get_effective_permissions(request.user):
        raise PermissionDenied("Attendance dashboard permission is required.")
    records = consistent_queryset(models.AttendanceRecord.objects.all()).filter(
        scheduled_start_at__date=today,
        branch_id__in=access.get_accessible_branch_ids(request.user, permission=permission),
    )
    return Response(
        {
            "today_scheduled_employees": records.count(),
            "checked_in": records.filter(actual_check_in_at__isnull=False).count(),
            "verified_present": records.exclude(outcome="UNVERIFIED")
            .filter(actual_check_in_at__isnull=False)
            .count(),
            "late": records.filter(late_minutes__gt=0).count(),
            "completed": records.filter(status="COMPLETED").count(),
            "exceptions": consistent_attendance_exceptions(
                models.AttendanceException.objects.filter(
                    status="OPEN", attendance_record__in=records
                )
            ).count(),
            "payroll_posted": False,
            "continuous_gps_tracking": False,
        }
    )
