from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
for prefix, viewset in (
    ("deployments", views.DeploymentViewSet),
    ("deployment-pools", views.PoolViewSet),
    ("pool-memberships", views.PoolMembershipViewSet),
    ("shift-templates", views.ShiftTemplateViewSet),
    ("scheduling-policies", views.SchedulingPolicyViewSet),
    ("rosters", views.RosterViewSet),
    ("duty-shifts", views.DutyShiftViewSet),
    ("duty-assignments", views.DutyAssignmentViewSet),
    ("schedule-blocks", views.ScheduleBlockViewSet),
    ("replacement-requests", views.ReplacementRequestViewSet),
    ("roster-changes", views.RosterChangeViewSet),
    ("availability-conflicts", views.AvailabilityConflictViewSet),
):
    router.register(prefix, viewset)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "eligibility/employees/<uuid:employee_id>/",
        views.eligibility,
        name="deployment-eligibility",
    ),
    path("dashboard/summary/", views.dashboard_summary, name="deployment-dashboard-summary"),
]
