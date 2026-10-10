from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from dsms.common.views import health_check, readiness_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health_check, name="health-check"),
    path("api/v1/health/ready/", readiness_check, name="readiness-check"),
    path("api/v1/auth/", include("dsms.identity.api.auth_urls")),
    path("api/v1/identity/", include("dsms.identity.api.urls")),
    path("api/v1/organization/", include("dsms.organization.api.urls")),
    path(
        "api/v1/platform/provisioning/",
        include("dsms.organization.api.provisioning_urls"),
    ),
    path("api/v1/workforce/", include("dsms.workforce.api.urls")),
    path("api/v1/documents/", include("dsms.documents.api.urls")),
    path("api/v1/finance/", include("dsms.finance.api.urls")),
    path("api/v1/billing/", include("dsms.billing.api.urls")),
    path("api/v1/analytics/", include("dsms.analytics.api.urls")),
    path("api/v1/recruitment/", include("dsms.recruitment.api.urls")),
    path("api/v1/training/", include("dsms.training.api.urls")),
    path("api/v1/contracts/", include("dsms.contracts.api.urls")),
    path("api/v1/deployment/", include("dsms.deployment.api.urls")),
    path("api/v1/attendance/", include("dsms.attendance.api.urls")),
    path("api/v1/supervision/", include("dsms.supervision.api.urls")),
    path("api/v1/patrol/", include("dsms.patrol.api.urls")),
    path("api/v1/incidents/", include("dsms.incidents.api.urls")),
    path("api/v1/client-portal/", include("dsms.client_portal.api.urls")),
    path("api/v1/notifications/", include("dsms.notifications.api.urls")),
    path("api/v1/leave/", include("dsms.leave.api.urls")),
    path("api/v1/assets/", include("dsms.assets.api.urls")),
    path("api/v1/audit/", include("dsms.audit.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]
