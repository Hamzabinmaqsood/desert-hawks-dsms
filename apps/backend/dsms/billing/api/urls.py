from rest_framework.routers import DefaultRouter

from .views import (
    BillingProfileViewSet,
    BillingRuleViewSet,
    BillingScheduleViewSet,
    CollectionActivityViewSet,
    CreditNoteViewSet,
    DashboardViewSet,
    DebitNoteViewSet,
    InvoiceRevenueAccountViewSet,
    InvoiceViewSet,
    ReceiptBankAccountViewSet,
    ReceiptClientViewSet,
    ReceiptViewSet,
    TaxCodeViewSet,
)

router = DefaultRouter()
router.register("billing-profiles", BillingProfileViewSet)
router.register("billing-schedules", BillingScheduleViewSet)
router.register("billing-rules", BillingRuleViewSet)
router.register("tax-codes", TaxCodeViewSet)
router.register("invoices", InvoiceViewSet, basename="billing-invoice")
router.register(
    "invoice-reference/revenue-accounts",
    InvoiceRevenueAccountViewSet,
    basename="billing-invoice-revenue-accounts",
)
router.register(
    "receipt-reference/bank-accounts",
    ReceiptBankAccountViewSet,
    basename="billing-receipt-bank-accounts",
)
router.register(
    "receipt-reference/clients",
    ReceiptClientViewSet,
    basename="billing-receipt-clients",
)
router.register("receipts", ReceiptViewSet, basename="billing-receipt")
router.register("dashboard", DashboardViewSet, basename="billing-dashboard")
router.register("credit-notes", CreditNoteViewSet, basename="billing-credit-note")
router.register("debit-notes", DebitNoteViewSet, basename="billing-debit-note")
router.register("collections", CollectionActivityViewSet, basename="billing-collection")
urlpatterns = router.urls
