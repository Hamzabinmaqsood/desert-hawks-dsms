from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
for prefix, viewset in (
    ("assignments", views.AssignmentViewSet),
    ("visit-frequency-requirements", views.FrequencyViewSet),
    ("visit-plans", views.VisitPlanViewSet),
    ("visits", views.VisitViewSet),
    ("inspection-templates", views.TemplateViewSet),
    ("inspections", views.InspectionViewSet),
    ("responses", views.ResponseViewSet),
    ("evidence", views.EvidenceViewSet),
    ("guard-observations", views.GuardObservationViewSet),
    ("findings", views.FindingViewSet),
    ("corrective-actions", views.CorrectiveActionViewSet),
    ("site-observations", views.ObservationViewSet),
    ("client-feedback", views.FeedbackViewSet),
    ("daily-reports", views.DailyReportViewSet),
):
    router.register(prefix, viewset)

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/summary/", views.dashboard_summary, name="supervision-dashboard-summary"),
    path("exceptions/", views.exceptions),
]
