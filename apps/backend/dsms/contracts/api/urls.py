from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
for prefix, viewset in (
    ("industries", views.ClientIndustryViewSet),
    ("clients", views.ClientViewSet),
    ("client-contacts", views.ClientContactViewSet),
    ("contracts", views.ContractViewSet),
    ("contract-services", views.ContractServiceViewSet),
    ("contract-amendments", views.ContractAmendmentViewSet),
    ("commercial-terms", views.CommercialTermsViewSet),
    ("site-types", views.SiteTypeViewSet),
    ("sites", views.SiteViewSet),
    ("site-contacts", views.SiteContactViewSet),
    ("site-operational-profiles", views.SiteOperationalProfileViewSet),
    ("site-escalations", views.SiteEscalationViewSet),
    ("site-calendar", views.SiteCalendarViewSet),
    ("post-types", views.PostTypeViewSet),
    ("posts", views.PostViewSet),
    ("post-qualification-requirements", views.PostQualificationViewSet),
    ("post-credential-requirements", views.PostCredentialViewSet),
    ("staffing-requirements", views.StaffingViewSet),
    ("slas", views.SLAViewSet),
):
    router.register(prefix, viewset)

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/summary/", views.dashboard_summary, name="contracts-dashboard-summary"),
    path(
        "staffing-demand/summary/", views.staffing_demand_summary, name="contracts-staffing-demand"
    ),
    path("exceptions/", views.exception_center, name="contracts-exceptions"),
]
