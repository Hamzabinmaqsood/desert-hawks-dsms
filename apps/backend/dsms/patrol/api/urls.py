from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
for prefix, viewset in (
    ("policies", views.PolicyViewSet),
    ("checkpoints", views.CheckpointViewSet),
    ("routes", views.RouteViewSet),
    ("requirements", views.RequirementViewSet),
    ("tasks", views.TaskViewSet),
    ("runs", views.RunViewSet),
    ("observations", views.ObservationViewSet),
    ("exceptions", views.ExceptionViewSet),
    ("reviews", views.ReviewViewSet),
    ("evidence", views.EvidenceViewSet),
):
    router.register(prefix, viewset)

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/summary/", views.dashboard_summary, name="patrol-dashboard-summary"),
]
