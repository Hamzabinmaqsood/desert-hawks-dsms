from rest_framework.routers import DefaultRouter

from .views import (
    HolidayViewSet,
    LeaveTypeViewSet,
    ManagerLeaveRequestViewSet,
    MyLeaveBalanceViewSet,
    MyLeaveRequestViewSet,
    TeamLeaveCalendarViewSet,
)

router = DefaultRouter()
router.register("types", LeaveTypeViewSet)
router.register("me/requests", MyLeaveRequestViewSet, basename="my-leave-request")
router.register("me/balances", MyLeaveBalanceViewSet, basename="my-leave-balance")
router.register("manager/requests", ManagerLeaveRequestViewSet, basename="manager-leave-request")
router.register("team/calendar", TeamLeaveCalendarViewSet, basename="team-leave-calendar")
router.register("holidays", HolidayViewSet, basename="leave-holiday")
urlpatterns = router.urls
