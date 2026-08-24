from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
for prefix, viewset in (
    ("policies", views.PolicyViewSet),
    ("qr-stations", views.QRStationViewSet),
    ("periods", views.PeriodViewSet),
    ("records", views.AttendanceRecordViewSet),
    ("events", views.EventViewSet),
    ("verifications", views.VerificationViewSet),
    ("exceptions", views.ExceptionViewSet),
    ("corrections", views.CorrectionViewSet),
    ("change-events", views.ChangeEventViewSet),
):
    router.register(prefix, viewset)
urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/summary/", views.dashboard_summary, name="attendance-dashboard-summary"),
]
