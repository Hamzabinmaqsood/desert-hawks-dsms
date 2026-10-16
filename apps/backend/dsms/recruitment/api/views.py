# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,no-untyped-call,arg-type"
import copy
import uuid
from typing import Any

from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
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

from .. import models, selectors, services
from . import security, serializers

CREATE_ACTOR_FIELDS = {
    models.ManpowerRequisition: "requested_by",
    models.Vacancy: "created_by",
    models.CandidateApplication: "recruiter",
    models.CandidateScreening: "screened_by",
    models.Interview: "created_by",
    models.CandidateAssessment: "assessed_by",
    models.CandidateDocument: "uploaded_by",
    models.EmploymentOffer: "created_by",
    models.OnboardingCase: "assigned_to",
}


class NoDeleteViewSet(
    TenantModuleViewMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("recruitment",)
    module_company_lookup = "company_id"
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    model: type[Any]

    def get_scope_permission(self):
        verb = (
            "view"
            if self.action in {"list", "retrieve"}
            else "add"
            if self.action == "create"
            else "change"
        )
        return f"recruitment.{verb}_{self.model._meta.model_name}"

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
                raise PermissionDenied("Only superusers may write global recruitment records.")
            return
        if not access.has_permission(
            user=user, permission=self.get_scope_permission(), **security.scope_kwargs(candidate)
        ):
            raise PermissionDenied("You do not have permission in the requested tenant scope.")

    def perform_create(self, serializer):
        extra: dict[str, Any] = {}
        generated_number = {
            models.Candidate: ("candidate_number", "CAND"),
            models.CandidateApplication: ("application_number", "APP"),
            models.EmploymentOffer: ("offer_number", "OFFER"),
        }.get(self.model)
        if generated_number:
            field_name, prefix = generated_number
            extra[field_name] = f"{prefix}-{uuid.uuid4().hex[:16].upper()}"
        actor_field = CREATE_ACTOR_FIELDS.get(self.model)
        if actor_field:
            extra[actor_field] = self.request.user
        if self.model is models.CandidateScreening:
            from django.utils import timezone

            extra["screened_at"] = timezone.now()
        candidate = self.model(**serializer.validated_data, **extra)
        self._guard_write(candidate)
        serializer.save(**extra)

    def perform_update(self, serializer):
        candidate = copy.copy(serializer.instance)
        for name, value in serializer.validated_data.items():
            setattr(candidate, name, value)
        self._guard_write(candidate)
        serializer.save()


def basic_viewset(model: type, serializer: type) -> type[NoDeleteViewSet]:
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = serializer

    ViewSet.__name__ = f"{model.__name__}ViewSet"
    ViewSet.model = model
    return ViewSet


class ManpowerRequisitionViewSet(NoDeleteViewSet):
    model = models.ManpowerRequisition
    queryset = models.ManpowerRequisition.objects.select_related(
        "company", "branch", "department", "designation"
    )
    serializer_class = serializers.ManpowerRequisitionSerializer
    custom_action_permissions = {
        "submit": "recruitment.change_manpowerrequisition",
        "approve": "recruitment.change_manpowerrequisition",
    }

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.submit_requisition(requisition=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        item = services.approve_requisition(
            requisition=self.get_object(),
            actor=request.user,
            approved_headcount=int(request.data["approved_headcount"]),
        )
        return Response(self.get_serializer(item).data)


class VacancyViewSet(NoDeleteViewSet):
    model = models.Vacancy
    queryset = models.Vacancy.objects.select_related(
        "company", "designation", "manpower_requisition"
    )
    serializer_class = serializers.VacancySerializer
    custom_action_permissions = {"open": "recruitment.change_vacancy"}

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        return Response(self.get_serializer(services.open_vacancy(vacancy=self.get_object())).data)


class EmploymentOfferViewSet(NoDeleteViewSet):
    model = models.EmploymentOffer
    queryset = models.EmploymentOffer.objects.select_related("application", "company")
    serializer_class = serializers.EmploymentOfferSerializer
    custom_action_permissions = {
        "approve": "recruitment.change_employmentoffer",
        "accept": "recruitment.change_employmentoffer",
    }

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.approve_offer(offer=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.accept_offer(offer=self.get_object(), actor=request.user)
            ).data
        )


class OnboardingViewSet(NoDeleteViewSet):
    model = models.OnboardingCase
    queryset = models.OnboardingCase.objects.select_related(
        "application", "candidate", "accepted_offer"
    )
    serializer_class = serializers.OnboardingCaseSerializer
    custom_action_permissions = {
        "ready_to_hire": "recruitment.change_onboardingcase",
        "hire": "recruitment.change_onboardingcase",
    }

    @action(detail=True, methods=["post"], url_path="ready-to-hire")
    def ready_to_hire(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.mark_ready_to_hire(onboarding=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def hire(self, request, pk=None):
        employee = services.hire_candidate(
            onboarding=self.get_object(),
            actor=request.user,
            employee_number=request.data.get("employee_number"),
        )
        return Response(
            {"employee_id": employee.pk, "employee_number": employee.employee_number},
            status=status.HTTP_201_CREATED,
        )


CandidateViewSet = basic_viewset(models.Candidate, serializers.CandidateSerializer)
ApplicationViewSet = basic_viewset(
    models.CandidateApplication, serializers.CandidateApplicationSerializer
)
ScreeningViewSet = basic_viewset(
    models.CandidateScreening, serializers.CandidateScreeningSerializer
)
InterviewViewSet = basic_viewset(models.Interview, serializers.InterviewSerializer)
AssessmentViewSet = basic_viewset(
    models.CandidateAssessment, serializers.CandidateAssessmentSerializer
)
ReferenceViewSet = basic_viewset(
    models.CandidateReference, serializers.CandidateReferenceSerializer
)
BackgroundCheckViewSet = basic_viewset(
    models.BackgroundCheck, serializers.BackgroundCheckSerializer
)
CandidateDocumentViewSet = basic_viewset(
    models.CandidateDocument, serializers.CandidateDocumentSerializer
)
OnboardingTemplateViewSet = basic_viewset(
    models.OnboardingChecklistTemplate, serializers.OnboardingChecklistTemplateSerializer
)


@module_api_surface("recruitment")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    company_ids = _dashboard_company_ids(request)
    return Response(selectors.recruitment_summary(company_ids=company_ids))


@module_api_surface("recruitment")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_funnel(request):
    return Response(list(selectors.recruitment_funnel(company_ids=_dashboard_company_ids(request))))


@module_api_surface("recruitment")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exception_center(request):
    return Response(selectors.recruitment_exceptions(company_ids=_dashboard_company_ids(request)))


def _dashboard_company_ids(request):
    user: User = request.user
    if user.is_superuser:
        requested = request.query_params.get("company")
        requested_ids = [requested] if requested else None
        return entitled_company_ids(request, requested_ids, ("recruitment",))
    if "recruitment.view_candidateapplication" not in access.get_effective_permissions(user):
        raise PermissionDenied("You do not have permission to view recruitment data.")
    accessible_ids = access.get_fully_accessible_company_ids(
        user, permission="recruitment.view_candidateapplication"
    )
    requested = request.query_params.get("company")
    if requested:
        if str(requested) not in {str(value) for value in accessible_ids}:
            raise Http404
        return [requested]
    return entitled_company_ids(request, list(accessible_ids), ("recruitment",))
