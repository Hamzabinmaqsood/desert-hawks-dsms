from rest_framework.routers import DefaultRouter

from .views import DataQualityViewSet, ExecutiveViewSet, MetricCatalogViewSet

router = DefaultRouter()
router.register("metrics", MetricCatalogViewSet, basename="analytics-metric")
router.register("executive", ExecutiveViewSet, basename="analytics-executive")
router.register("data-quality", DataQualityViewSet, basename="analytics-data-quality")
urlpatterns = router.urls
