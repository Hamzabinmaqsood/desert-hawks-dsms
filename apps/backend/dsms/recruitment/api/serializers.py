# mypy: disable-error-code="type-arg"
from rest_framework import serializers

from .. import models


def serializer_for(model: type) -> type[serializers.ModelSerializer]:
    class RecruitmentSerializer(serializers.ModelSerializer):
        class Meta:
            fields = "__all__"

    RecruitmentSerializer.Meta.model = model
    RecruitmentSerializer.__name__ = f"{model.__name__}Serializer"
    return RecruitmentSerializer


ManpowerRequisitionSerializer = serializer_for(models.ManpowerRequisition)
VacancySerializer = serializer_for(models.Vacancy)
CandidateSerializer = serializer_for(models.Candidate)
CandidateApplicationSerializer = serializer_for(models.CandidateApplication)
CandidateScreeningSerializer = serializer_for(models.CandidateScreening)
InterviewSerializer = serializer_for(models.Interview)
CandidateAssessmentSerializer = serializer_for(models.CandidateAssessment)
CandidateReferenceSerializer = serializer_for(models.CandidateReference)
BackgroundCheckSerializer = serializer_for(models.BackgroundCheck)
CandidateDocumentSerializer = serializer_for(models.CandidateDocument)
EmploymentOfferSerializer = serializer_for(models.EmploymentOffer)
OnboardingCaseSerializer = serializer_for(models.OnboardingCase)
OnboardingChecklistTemplateSerializer = serializer_for(models.OnboardingChecklistTemplate)
