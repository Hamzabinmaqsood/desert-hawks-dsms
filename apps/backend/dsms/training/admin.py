from typing import Any

from django.contrib import admin
from django.db import models as django_models
from django.http import HttpRequest

from . import models


class NoDeleteAdmin(admin.ModelAdmin[django_models.Model]):
    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


for model in (
    models.TrainingCategory,
    models.TrainingCourse,
    models.TrainingCourseVersion,
    models.QualificationType,
    models.CourseQualificationOutcome,
    models.EmployeeQualification,
    models.TrainingRequirement,
    models.TrainingRequirementWaiver,
    models.TrainingVenue,
    models.TrainingInstructor,
    models.TrainingProgram,
    models.TrainingProgramCourse,
    models.TrainingSession,
    models.TrainingSessionInstructor,
    models.TrainingEnrollment,
    models.TrainingSessionParticipation,
    models.TrainingAssessment,
    models.EmployeeTrainingAssessmentResult,
    models.TrainingCompletion,
    models.TrainingCertificate,
    models.ExternalCertification,
    models.EmployeeReadinessSnapshot,
):
    admin.site.register(model, NoDeleteAdmin)
