from typing import Any

from django.contrib import admin
from django.db import models as django_models
from django.http import HttpRequest

from . import models


class NoDeleteAdmin(admin.ModelAdmin[django_models.Model]):
    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


for model in (
    models.ManpowerRequisition,
    models.Vacancy,
    models.Candidate,
    models.CandidateApplication,
    models.ApplicationStatusHistory,
    models.CandidateScreening,
    models.Interview,
    models.InterviewPanelMember,
    models.InterviewEvaluation,
    models.CandidateAssessment,
    models.CandidateReference,
    models.ReferenceVerification,
    models.BackgroundCheck,
    models.CandidateDocument,
    models.CandidateDocumentVersion,
    models.CandidateNote,
    models.EmploymentOffer,
    models.EmploymentOfferRevision,
    models.OnboardingCase,
    models.OnboardingChecklistTemplate,
    models.OnboardingChecklistTemplateItem,
    models.OnboardingChecklistItem,
):
    admin.site.register(model, NoDeleteAdmin)
