# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def"
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .. import models, selectors, services
from . import serializers


class NoDeleteViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]


def basic_viewset(model: type, serializer: type) -> type[NoDeleteViewSet]:
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = serializer

    ViewSet.__name__ = f"{model.__name__}ViewSet"
    return ViewSet


class ManpowerRequisitionViewSet(NoDeleteViewSet):
    queryset = models.ManpowerRequisition.objects.select_related(
        "company", "branch", "department", "designation"
    )
    serializer_class = serializers.ManpowerRequisitionSerializer

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
    queryset = models.Vacancy.objects.select_related(
        "company", "designation", "manpower_requisition"
    )
    serializer_class = serializers.VacancySerializer

    @action(detail=True, methods=["post"])
    def open(self, request, pk=None):
        return Response(self.get_serializer(services.open_vacancy(vacancy=self.get_object())).data)


class EmploymentOfferViewSet(NoDeleteViewSet):
    queryset = models.EmploymentOffer.objects.select_related("application", "company")
    serializer_class = serializers.EmploymentOfferSerializer

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
    queryset = models.OnboardingCase.objects.select_related(
        "application", "candidate", "accepted_offer"
    )
    serializer_class = serializers.OnboardingCaseSerializer

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


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    return Response(selectors.recruitment_summary(company_id=request.query_params.get("company")))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_funnel(request):
    return Response(
        list(selectors.recruitment_funnel(company_id=request.query_params.get("company")))
    )


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exception_center(request):
    return Response(
        selectors.recruitment_exceptions(company_id=request.query_params.get("company"))
    )
