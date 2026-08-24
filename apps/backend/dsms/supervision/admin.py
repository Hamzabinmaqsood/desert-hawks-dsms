# mypy: disable-error-code="assignment,type-arg,no-untyped-def"
from django.contrib import admin
from django.db import models as django_models

from . import models


class NoDeleteAdmin(admin.ModelAdmin[django_models.Model]):
    def has_delete_permission(self, request, obj=None):
        return False


class EvidenceAdmin(NoDeleteAdmin):
    def has_change_permission(self, request, obj=None):
        return obj is None


for model in (
    models.SupervisionAssignment,
    models.VisitFrequencyRequirement,
    models.SupervisorVisitPlan,
    models.InspectionTemplate,
    models.InspectionTemplateSection,
    models.InspectionTemplateItem,
    models.InspectionTemplateItemOption,
    models.CorrectiveAction,
    models.SupervisorDailyReport,
):
    admin.site.register(model, NoDeleteAdmin)
for model in (
    models.SiteVisit,
    models.SiteInspection,
    models.InspectionResponse,
    models.FieldEvidence,
    models.GuardObservation,
    models.InspectionFinding,
    models.SiteObservation,
    models.SiteVisitClientFeedback,
):
    admin.site.register(model, EvidenceAdmin)
