from rest_framework.routers import DefaultRouter

from .views import CommandCenterQueueViewSet, EvidenceViewSet, IncidentViewSet, SOSViewSet

router = DefaultRouter()
router.register("incidents", IncidentViewSet)
router.register("sos", SOSViewSet)
router.register("command-center/queue", CommandCenterQueueViewSet, basename="command-center-queue")
router.register("evidence", EvidenceViewSet, basename="incident-evidence")
urlpatterns = router.urls
