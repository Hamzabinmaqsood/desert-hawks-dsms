# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def"
from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.workforce.models import Employee

from .. import models, selectors, services
from .serializers import SERIALIZERS


class NoDeleteViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "head", "options"]


def basic_viewset(model: type) -> type[NoDeleteViewSet]:
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    ViewSet.__name__ = f"{model.__name__}ViewSet"
    return ViewSet


class CourseViewSet(NoDeleteViewSet):
    queryset = selectors.training_course_list()
    serializer_class = SERIALIZERS["TrainingCourse"]

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_training_course(course=self.get_object())).data
        )

    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        course = self.get_object()
        course.status = "RETIRED"
        course.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(course).data)


class SessionViewSet(NoDeleteViewSet):
    queryset = selectors.training_session_list()
    serializer_class = SERIALIZERS["TrainingSession"]

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        return Response(
            self.get_serializer(services.schedule_training_session(session=self.get_object())).data
        )

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        item = services.enroll_employee(
            session=self.get_object(),
            employee=Employee.objects.get(pk=request.data["employee"]),
            actor=request.user,
            allow_waitlist=request.data.get("allow_waitlist", True),
        )
        return Response(SERIALIZERS["TrainingEnrollment"](item).data, status=201)


class EnrollmentViewSet(NoDeleteViewSet):
    queryset = models.TrainingEnrollment.objects.select_related("session", "employee", "company")
    serializer_class = SERIALIZERS["TrainingEnrollment"]

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


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    return Response(
        selectors.training_dashboard_summary(company_id=request.query_params.get("company"))
    )


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def guards_readiness(request):
    return Response(selectors.guard_readiness_list(company_id=request.query_params.get("company")))


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def employee_readiness(request, employee_id):
    result = services.evaluate_employee_readiness(
        employee=Employee.objects.select_related(
            "company", "branch", "department", "designation"
        ).get(pk=employee_id)
    )
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


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exception_center(request):
    return Response(selectors.training_exceptions(company_id=request.query_params.get("company")))
