from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    AccessMatrixView,
    PermissionViewSet,
    RoleViewSet,
    UserRoleAssignmentViewSet,
    UserViewSet,
)

app_name = "identity"

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")
router.register("role-assignments", UserRoleAssignmentViewSet, basename="role-assignment")
router.register("permissions", PermissionViewSet, basename="permission")

urlpatterns = [
    path("access-matrix/", AccessMatrixView.as_view(), name="access-matrix"),
    *router.urls,
]
