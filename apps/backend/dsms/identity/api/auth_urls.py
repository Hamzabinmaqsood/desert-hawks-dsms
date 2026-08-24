from django.urls import path

from .auth_views import (
    LoginView,
    LogoutView,
    MeAccessScopesView,
    MePermissionsView,
    MeView,
    RefreshView,
    VerifyView,
)

app_name = "auth"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", RefreshView.as_view(), name="refresh"),
    path("verify/", VerifyView.as_view(), name="verify"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/permissions/", MePermissionsView.as_view(), name="me-permissions"),
    path("me/access-scopes/", MeAccessScopesView.as_view(), name="me-access-scopes"),
]
