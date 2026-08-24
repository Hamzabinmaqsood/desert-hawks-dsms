# mypy: disable-error-code="type-arg,no-untyped-def"
from django.contrib import admin

from . import models

for model in [
    models.ClientPortalRole,
    models.ClientPortalMembership,
    models.ClientPortalSiteAccess,
    models.ClientPortalContractAccess,
    models.ClientDataSharingPolicy,
    models.IncidentClientVisibility,
    models.SLAMeasurementPeriod,
    models.SLAMeasurement,
    models.ClientServiceReport,
    models.ClientServiceRequest,
    models.ClientFeedback,
]:
    admin.site.register(model)


@admin.register(
    models.ClientPortalInvitation,
    models.ClientPortalAuditEvent,
    models.ClientServiceReportAcknowledgement,
    models.ClientIncidentAcknowledgement,
)
class ReadOnlyHistoryAdmin(admin.ModelAdmin):
    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
