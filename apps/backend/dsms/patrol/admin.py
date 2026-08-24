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
    models.PatrolPolicy,
    models.PatrolCheckpoint,
    models.CheckpointQRCredential,
    models.CheckpointNFCCredential,
    models.PatrolRoute,
    models.PatrolRouteVersion,
    models.PatrolRouteCheckpoint,
    models.PatrolRequirement,
    models.PatrolRequirementDay,
    models.PatrolRequirementTime,
    models.PatrolTask,
):
    admin.site.register(model, NoDeleteAdmin)
for model in (
    models.PatrolRun,
    models.PatrolEvent,
    models.CheckpointVisit,
    models.PatrolEvidence,
    models.PatrolObservation,
    models.PatrolException,
    models.PatrolReview,
):
    admin.site.register(model, EvidenceAdmin)
