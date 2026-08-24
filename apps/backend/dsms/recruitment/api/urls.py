from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("manpower-requisitions", views.ManpowerRequisitionViewSet)
router.register("vacancies", views.VacancyViewSet)
router.register("candidates", views.CandidateViewSet)
router.register("applications", views.ApplicationViewSet)
router.register("screenings", views.ScreeningViewSet)
router.register("interviews", views.InterviewViewSet)
router.register("assessments", views.AssessmentViewSet)
router.register("references", views.ReferenceViewSet)
router.register("background-checks", views.BackgroundCheckViewSet)
router.register("candidate-documents", views.CandidateDocumentViewSet)
router.register("offers", views.EmploymentOfferViewSet)
router.register("onboarding", views.OnboardingViewSet)
router.register("onboarding-templates", views.OnboardingTemplateViewSet)

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/summary/", views.dashboard_summary, name="recruitment-dashboard-summary"),
    path("dashboard/funnel/", views.dashboard_funnel, name="recruitment-dashboard-funnel"),
    path("exceptions/", views.exception_center, name="recruitment-exceptions"),
]
