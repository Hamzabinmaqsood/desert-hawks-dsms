# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,no-untyped-call,arg-type"
import copy
from decimal import Decimal
from typing import Any

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.identity import access
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission
from dsms.subscriptions.api.enforcement import (
    TenantModuleViewMixin,
    entitled_company_ids,
    module_api_surface,
)
from dsms.workforce.models import Employee

from .. import models, selectors, services
from ..exceptions import TrainingError
from . import security
from .serializers import SERIALIZERS

CREATE_ACTOR_FIELDS = {
    models.TrainingCourseVersion: "created_by",
    models.TrainingRequirementWaiver: "approved_by",
    models.TrainingSession: "created_by",
    models.TrainingEnrollment: "enrolled_by",
    models.EmployeeTrainingAssessmentResult: "evaluator",
}


class NoDeleteViewSet(
    TenantModuleViewMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("learning",)
    module_company_lookup = "company_id"
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    model: type[Any]

    def get_scope_permission(self):
        custom_permission = getattr(self, "custom_action_permissions", {}).get(self.action)
        if custom_permission:
            return custom_permission
        verb = (
            "view"
            if self.action in {"list", "retrieve"}
            else "add"
            if self.action == "create"
            else "change"
        )
        return f"training.{verb}_{self.model._meta.model_name}"

    def get_queryset(self):
        return security.scoped_queryset(
            super().get_queryset(), user=self.request.user, permission=self.get_scope_permission()
        )

    def _guard_write(self, candidate):
        self.require_modules_for(candidate)
        user = self.request.user
        company = security.company_for(candidate)
        if company is None:
            if not user.is_superuser:
                raise PermissionDenied("Only superusers may write global training records.")
            return
        if not access.has_permission(
            user=user, permission=self.get_scope_permission(), **security.scope_kwargs(candidate)
        ):
            raise PermissionDenied("You do not have permission in the requested tenant scope.")

    def perform_create(self, serializer):
        extra: dict[str, Any] = {}
        actor_field = CREATE_ACTOR_FIELDS.get(self.model)
        if actor_field:
            extra[actor_field] = self.request.user
        candidate = self.model(**serializer.validated_data, **extra)
        self._guard_write(candidate)
        serializer.save(**extra)

    def perform_update(self, serializer):
        candidate = copy.copy(serializer.instance)
        for name, value in serializer.validated_data.items():
            setattr(candidate, name, value)
        self._guard_write(candidate)
        serializer.save()


def basic_viewset(model: type) -> type[NoDeleteViewSet]:
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    ViewSet.__name__ = f"{model.__name__}ViewSet"
    ViewSet.model = model
    if model in {
        models.EmployeeTrainingAssessmentResult,
        models.TrainingCompletion,
        models.TrainingCertificate,
    }:
        ViewSet.http_method_names = ["get", "head", "options"]
    return ViewSet


class CourseViewSet(NoDeleteViewSet):
    model = models.TrainingCourse
    queryset = selectors.training_course_list()
    serializer_class = SERIALIZERS["TrainingCourse"]
    custom_action_permissions = {
        "activate": "training.change_trainingcourse",
        "retire": "training.change_trainingcourse",
    }
    filterset_fields = ["company", "status", "category", "delivery_method"]
    search_fields = ["code", "title", "description"]
    ordering_fields = ["code", "title", "created_at", "updated_at"]

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        try:
            item = services.activate_training_course(course=self.get_object())
        except TrainingError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        course = self.get_object()
        course.status = "RETIRED"
        course.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(course).data)


class SessionViewSet(NoDeleteViewSet):
    model = models.TrainingSession
    queryset = selectors.training_session_list()
    serializer_class = SERIALIZERS["TrainingSession"]
    custom_action_permissions = {
        "schedule": "training.change_trainingsession",
        "open_enrollment": "training.change_trainingsession",
        "start": "training.change_trainingsession",
        "complete": "training.change_trainingsession",
        "enroll": "training.add_trainingenrollment",
    }
    filterset_fields = ["company", "status", "course", "program", "branch"]
    search_fields = ["session_number", "course__code", "course__title"]
    ordering_fields = ["start_datetime", "end_datetime", "created_at"]

    def _session_action(self, function):
        try:
            item = function(session=self.get_object())
        except TrainingError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        return self._session_action(services.schedule_training_session)

    @action(detail=True, methods=["post"], url_path="open-enrollment")
    def open_enrollment(self, request, pk=None):
        return self._session_action(services.open_training_session_enrollment)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        return self._session_action(services.start_training_session)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._session_action(services.complete_training_session)

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        employee = get_object_or_404(
            Employee,
            pk=request.data.get("employee"),
            company_id__in=access.get_accessible_company_ids(
                request.user, permission="training.add_trainingenrollment"
            ),
            company__is_active=True,
        )
        try:
            item = services.enroll_employee(
                session=self.get_object(),
                employee=employee,
                actor=request.user,
                allow_waitlist=request.data.get("allow_waitlist", True),
            )
        except TrainingError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc
        return Response(SERIALIZERS["TrainingEnrollment"](item).data, status=201)


class EnrollmentViewSet(NoDeleteViewSet):
    model = models.TrainingEnrollment
    queryset = models.TrainingEnrollment.objects.select_related("session", "employee", "company")
    serializer_class = SERIALIZERS["TrainingEnrollment"]
    custom_action_permissions = {
        "assessment_result": "training.add_employeetrainingassessmentresult",
        "finalize_result": "training.finalize_training_result",
    }
    filterset_fields = ["company", "status", "session", "employee"]
    ordering_fields = ["enrolled_at", "created_at", "status"]

    @action(detail=True, methods=["post"], url_path="assessment-result")
    def assessment_result(self, request, pk=None):
        result = services.record_assessment_result(
            enrollment=self.get_object(),
            assessment_id=request.data["assessment"],
            score=Decimal(request.data["score"]),
            evaluator=request.user,
            remarks=request.data.get("remarks", ""),
        )
        return Response(SERIALIZERS["EmployeeTrainingAssessmentResult"](result).data, status=201)

    @action(detail=True, methods=["post"], url_path="finalize-result")
    def finalize_result(self, request, pk=None):
        result = services.finalize_training_result(enrollment=self.get_object(), actor=request.user)
        return Response(SERIALIZERS["TrainingCompletion"](result).data, status=201)


CategoryViewSet = basic_viewset(models.TrainingCategory)
CourseVersionViewSet = basic_viewset(models.TrainingCourseVersion)
QualificationTypeViewSet = basic_viewset(models.QualificationType)
EmployeeQualificationViewSet = basic_viewset(models.EmployeeQualification)
RequirementViewSet = basic_viewset(models.TrainingRequirement)
RequirementWaiverViewSet = basic_viewset(models.TrainingRequirementWaiver)
VenueViewSet = basic_viewset(models.TrainingVenue)
InstructorViewSet = basic_viewset(models.TrainingInstructor)
ProgramViewSet = basic_viewset(models.TrainingProgram)
AssessmentViewSet = basic_viewset(models.TrainingAssessment)
AssessmentResultViewSet = basic_viewset(models.EmployeeTrainingAssessmentResult)
CompletionViewSet = basic_viewset(models.TrainingCompletion)
CertificateViewSet = basic_viewset(models.TrainingCertificate)
ExternalCertificationViewSet = basic_viewset(models.ExternalCertification)

CategoryViewSet.filterset_fields = ["company", "is_active"]
CategoryViewSet.search_fields = ["code", "name"]
CourseVersionViewSet.filterset_fields = ["course", "is_current"]
QualificationTypeViewSet.filterset_fields = ["company", "is_active", "category"]
QualificationTypeViewSet.search_fields = ["code", "name"]
EmployeeQualificationViewSet.filterset_fields = [
    "company",
    "employee",
    "qualification_type",
    "status",
]
ProgramViewSet.filterset_fields = ["company", "is_active", "designation"]
ProgramViewSet.search_fields = ["code", "name"]
AssessmentViewSet.filterset_fields = ["session", "assessment_type"]
CompletionViewSet.filterset_fields = ["employee", "course", "session", "passed"]
CertificateViewSet.filterset_fields = ["company", "employee", "status"]
ExternalCertificationViewSet.filterset_fields = [
    "company",
    "employee",
    "qualification_type",
    "verification_status",
]


@module_api_surface("learning")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    return Response(
        selectors.training_dashboard_summary(company_ids=_dashboard_company_ids(request))
    )


@module_api_surface("learning")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def guards_readiness(request):
    return Response(
        selectors.guard_readiness_list(
            company_ids=_dashboard_company_ids(request, permission="training.view_readiness")
        )
    )


@module_api_surface("learning")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def employee_readiness(request, employee_id):
    user: User = request.user
    company_ids = access.get_fully_accessible_company_ids(
        user, permission="training.view_readiness"
    )
    branch_ids = access.get_accessible_branch_ids(user, permission="training.view_readiness")
    employee = get_object_or_404(
        Employee.objects.select_related("company", "branch", "department", "designation"),
        Q(company_id__in=company_ids) | Q(branch_id__in=branch_ids),
        pk=employee_id,
        company__is_active=True,
    )
    if employee.company_id not in entitled_company_ids(
        request, [employee.company_id], ("learning",)
    ):
        raise Http404
    result = services.evaluate_employee_readiness(employee=employee)
    return Response(
        {
            "employee_id": str(result.employee.pk),
            "status": result.status,
            "blocking_issues": [issue.__dict__ for issue in result.blocking_issues],
            "warnings": [issue.__dict__ for issue in result.warnings],
            "requirements_checked": result.requirements_checked,
            "requirements_satisfied": result.requirements_satisfied,
            "requirements_missing": result.requirements_missing,
        }
    )


@module_api_surface("learning")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exception_center(request):
    return Response(selectors.training_exceptions(company_ids=_dashboard_company_ids(request)))


def _dashboard_company_ids(request, *, permission="training.view_training_dashboard"):
    user: User = request.user
    if user.is_superuser:
        requested = request.query_params.get("company")
        requested_ids = [requested] if requested else None
        return entitled_company_ids(request, requested_ids, ("learning",))
    if permission not in access.get_effective_permissions(user):
        raise PermissionDenied("You do not have permission to view this training data.")
    accessible_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    requested = request.query_params.get("company")
    if requested:
        if str(requested) not in {str(value) for value in accessible_ids}:
            raise Http404
        return [requested]
    return entitled_company_ids(request, list(accessible_ids), ("learning",))
