from django.urls import path

from .views import (
    ClientInvoiceDetailView,
    ClientInvoiceDownloadView,
    ClientInvoicesView,
    ClientReceiptsView,
    ClientStatementView,
    ContractsView,
    IncidentsView,
    MembershipsView,
    MeView,
    ReportAcknowledgeView,
    ReportsView,
    ServiceRequestsView,
    SitesView,
)

urlpatterns = [
    path("me/memberships/", MembershipsView.as_view()),
    path("<uuid:client_uuid>/me/", MeView.as_view()),
    path("<uuid:client_uuid>/sites/", SitesView.as_view()),
    path("<uuid:client_uuid>/contracts/", ContractsView.as_view()),
    path("<uuid:client_uuid>/incidents/", IncidentsView.as_view()),
    path("<uuid:client_uuid>/reports/", ReportsView.as_view()),
    path(
        "<uuid:client_uuid>/reports/<uuid:report_uuid>/acknowledge/",
        ReportAcknowledgeView.as_view(),
    ),
    path("<uuid:client_uuid>/service-requests/", ServiceRequestsView.as_view()),
    path("<uuid:client_uuid>/finance/invoices/", ClientInvoicesView.as_view()),
    path(
        "<uuid:client_uuid>/finance/invoices/<uuid:invoice_uuid>/",
        ClientInvoiceDetailView.as_view(),
    ),
    path(
        "<uuid:client_uuid>/finance/invoices/<uuid:invoice_uuid>/download/",
        ClientInvoiceDownloadView.as_view(),
    ),
    path("<uuid:client_uuid>/finance/receipts/", ClientReceiptsView.as_view()),
    path("<uuid:client_uuid>/finance/statement/", ClientStatementView.as_view()),
]
