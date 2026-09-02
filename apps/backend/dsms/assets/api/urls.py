from rest_framework.routers import DefaultRouter

from .views import (
    AssetCategoryViewSet,
    AssetIssueViewSet,
    AssetItemViewSet,
    AssetMovementViewSet,
    AssetStoreViewSet,
    AssetViewSet,
    ProcurementReceiptLineViewSet,
    ProcurementRegistrationViewSet,
    StockAccountViewSet,
)

router = DefaultRouter()
router.register("categories", AssetCategoryViewSet, basename="asset-category")
router.register("items", AssetItemViewSet, basename="asset-item")
router.register("stores", AssetStoreViewSet, basename="asset-store")
router.register("assets", AssetViewSet, basename="asset")
router.register("stock-accounts", StockAccountViewSet, basename="stock-account")
router.register("issues", AssetIssueViewSet, basename="asset-issue")
router.register("movements", AssetMovementViewSet, basename="asset-movement")
router.register(
    "procurement-registrations", ProcurementRegistrationViewSet, basename="procurement-registration"
)
router.register(
    "procurement-receipt-lines", ProcurementReceiptLineViewSet, basename="procurement-receipt-line"
)
urlpatterns = router.urls
