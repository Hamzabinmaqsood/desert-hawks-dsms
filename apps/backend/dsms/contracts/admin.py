from typing import Any

from django.contrib import admin
from django.db import models as django_models
from django.http import HttpRequest

from . import models


class NoDeleteAdmin(admin.ModelAdmin[django_models.Model]):
    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


for model in (
    models.ClientIndustry,
    models.Client,
    models.ClientContact,
    models.ServiceContract,
    models.ContractCommercialTerms,
    models.ContractAmendment,
    models.ContractService,
    models.SiteType,
    models.SecuritySite,
    models.SiteContact,
    models.SiteOperationalProfile,
    models.PostType,
    models.SecurityPost,
    models.PostQualificationRequirement,
    models.PostCredentialRequirement,
    models.StaffingRequirement,
    models.StaffingRequirementDay,
    models.StaffingRequirementRevision,
    models.ServiceLevelAgreement,
    models.SiteEscalationContact,
    models.SiteCalendarException,
):
    admin.site.register(model, NoDeleteAdmin)
