from rest_framework.routers import DefaultRouter

from .views import (
    BranchViewSet,
    CityViewSet,
    CompanyViewSet,
    DepartmentViewSet,
    DesignationViewSet,
    OperationalZoneViewSet,
    OrganizationHierarchyView,
    RegionViewSet,
)

app_name = "organization"

router = DefaultRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("regions", RegionViewSet, basename="region")
router.register("cities", CityViewSet, basename="city")
router.register("branches", BranchViewSet, basename="branch")
router.register("departments", DepartmentViewSet, basename="department")
router.register("designations", DesignationViewSet, basename="designation")
router.register("operational-zones", OperationalZoneViewSet, basename="operational-zone")
router.register("hierarchy", OrganizationHierarchyView, basename="hierarchy")

urlpatterns = router.urls
