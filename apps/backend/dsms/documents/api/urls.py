from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    ComplianceSummaryView,
    DocumentTypeViewSet,
    EmployeeDocumentsView,
    EmployeeDocumentViewSet,
)

app_name = "documents"
router = DefaultRouter()
router.register("types", DocumentTypeViewSet, basename="document-type")
router.register("employee-documents", EmployeeDocumentViewSet, basename="employee-document")

urlpatterns = [
    *router.urls,
    path(
        "employees/<uuid:employee_id>/documents/",
        EmployeeDocumentsView.as_view(),
        name="employee-documents",
    ),
    path(
        "employees/<uuid:employee_id>/compliance-summary/",
        ComplianceSummaryView.as_view(),
        name="compliance-summary",
    ),
]
