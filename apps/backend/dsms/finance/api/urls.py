from django.urls import path
from rest_framework.routers import DefaultRouter

from .domain_views import (
    ApprovalInboxView,
    BankImportView,
    BankReconcileView,
    DashboardView,
    DomainCollectionView,
    DomainDetailView,
    FinanceActionView,
    FinanceAttachmentView,
    PayrollActionView,
    ReportView,
)
from .payment_views import (
    PaymentBatchViewSet,
    PaymentBeneficiaryViewSet,
    PaymentInstructionViewSet,
    PaymentProviderViewSet,
    PaymentSettlementViewSet,
)
from .vendor_bill_views import VendorBillExpenseAccountViewSet, VendorBillViewSet
from .vendor_payment_views import (
    PayableVendorBillViewSet,
    PaymentAccountViewSet,
    VendorPaymentViewSet,
)
from .vendor_views import VendorPayableAccountViewSet, VendorViewSet
from .views import (
    AccountViewSet,
    FiscalYearViewSet,
    JournalViewSet,
    PeriodViewSet,
    TrialBalanceView,
)

app_name = "finance"
router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="account")
router.register("fiscal-years", FiscalYearViewSet, basename="fiscal-year")
router.register("periods", PeriodViewSet, basename="period")
router.register("journals", JournalViewSet, basename="journal")
router.register("payment-providers", PaymentProviderViewSet, basename="payment-provider")
router.register("payment-beneficiaries", PaymentBeneficiaryViewSet, basename="payment-beneficiary")
router.register("payment-batches", PaymentBatchViewSet, basename="payment-batch")
router.register("payment-instructions", PaymentInstructionViewSet, basename="payment-instruction")
router.register("payment-settlements", PaymentSettlementViewSet, basename="payment-settlement")
router.register("vendors", VendorViewSet, basename="vendor")
router.register("vendor-bills", VendorBillViewSet, basename="vendor-bill")
router.register("vendor-payments", VendorPaymentViewSet, basename="vendor-payment")
router.register(
    "ap-reference/payable-bills", PayableVendorBillViewSet, basename="payable-vendor-bill"
)
router.register("ap-reference/payment-accounts", PaymentAccountViewSet, basename="payment-account")
router.register(
    "ap-reference/expense-accounts",
    VendorBillExpenseAccountViewSet,
    basename="vendor-bill-expense-account",
)
router.register(
    "ap-reference/payable-accounts",
    VendorPayableAccountViewSet,
    basename="vendor-payable-account",
)
urlpatterns = [
    *router.urls,
    path("reports/trial-balance/", TrialBalanceView.as_view(), name="trial-balance"),
    path("domain/<slug:resource>/", DomainCollectionView.as_view(), name="domain-collection"),
    path("domain/<slug:resource>/<uuid:pk>/", DomainDetailView.as_view(), name="domain-detail"),
    path(
        "domain/<slug:resource>/<uuid:pk>/<slug:action>/",
        FinanceActionView.as_view(),
        name="finance-action",
    ),
    path(
        "payroll-runs/<uuid:pk>/<slug:action>/", PayrollActionView.as_view(), name="payroll-action"
    ),
    path("dashboard/<slug:section>/", DashboardView.as_view(), name="dashboard"),
    path("approval-inbox/", ApprovalInboxView.as_view(), name="approval-inbox"),
    path("bank-accounts/<uuid:pk>/import-csv/", BankImportView.as_view(), name="bank-import"),
    path(
        "bank-statement-lines/<uuid:pk>/<slug:action>/",
        BankReconcileView.as_view(),
        name="bank-reconcile",
    ),
    path("attachments/", FinanceAttachmentView.as_view(), name="attachment-upload"),
    path(
        "attachments/<uuid:pk>/download/",
        FinanceAttachmentView.as_view(),
        name="attachment-download",
    ),
    path("reports/<slug:report>/", ReportView.as_view(), name="report"),
]
