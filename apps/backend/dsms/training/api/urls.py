from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
for prefix, viewset in (
    ("categories", views.CategoryViewSet),
    ("courses", views.CourseViewSet),
    ("course-versions", views.CourseVersionViewSet),
    ("qualification-types", views.QualificationTypeViewSet),
    ("employee-qualifications", views.EmployeeQualificationViewSet),
    ("requirements", views.RequirementViewSet),
    ("requirement-waivers", views.RequirementWaiverViewSet),
    ("venues", views.VenueViewSet),
    ("instructors", views.InstructorViewSet),
    ("programs", views.ProgramViewSet),
    ("sessions", views.SessionViewSet),
    ("enrollments", views.EnrollmentViewSet),
    ("assessments", views.AssessmentViewSet),
    ("assessment-results", views.AssessmentResultViewSet),
    ("completions", views.CompletionViewSet),
    ("certificates", views.CertificateViewSet),
    ("external-certifications", views.ExternalCertificationViewSet),
):
    router.register(prefix, viewset)

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/summary/", views.dashboard_summary, name="training-dashboard-summary"),
    path("readiness/guards/", views.guards_readiness, name="training-guard-readiness"),
    path(
        "readiness/employees/<uuid:employee_id>/",
        views.employee_readiness,
        name="training-employee-readiness",
    ),
    path("exceptions/", views.exception_center, name="training-exceptions"),
]
