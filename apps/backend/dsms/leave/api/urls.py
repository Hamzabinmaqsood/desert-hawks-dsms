from rest_framework.routers import DefaultRouter

from .views import LeaveTypeViewSet, MyLeaveRequestViewSet

router = DefaultRouter()
router.register("types", LeaveTypeViewSet)
router.register("me/requests", MyLeaveRequestViewSet, basename="my-leave-request")
urlpatterns = router.urls
