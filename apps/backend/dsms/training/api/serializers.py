# mypy: disable-error-code="type-arg"
from rest_framework import serializers

from .. import models


def serializer_for(model: type) -> type[serializers.ModelSerializer]:
    class TrainingSerializer(serializers.ModelSerializer):
        class Meta:
            fields = "__all__"

    TrainingSerializer.Meta.model = model
    TrainingSerializer.__name__ = f"{model.__name__}Serializer"
    return TrainingSerializer


SERIALIZERS = {
    model.__name__: serializer_for(model)
    for model in (
        models.TrainingCategory,
        models.TrainingCourse,
        models.TrainingCourseVersion,
        models.QualificationType,
        models.EmployeeQualification,
        models.TrainingRequirement,
        models.TrainingRequirementWaiver,
        models.TrainingVenue,
        models.TrainingInstructor,
        models.TrainingProgram,
        models.TrainingSession,
        models.TrainingEnrollment,
        models.TrainingSessionParticipation,
        models.TrainingAssessment,
        models.EmployeeTrainingAssessmentResult,
        models.TrainingCompletion,
        models.TrainingCertificate,
        models.ExternalCertification,
    )
}
