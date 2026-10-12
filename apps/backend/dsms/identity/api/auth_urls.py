from django.urls import path

from .auth_views import (
    CompanyBrandingView,
    CompanyBusinessSettingsView,
    CompanyContextView,
    CompanyOperationalReadinessView,
    LoginView,
    LogoutView,
    MeAccessScopesView,
    MePermissionsView,
    MePlatformCapabilitiesView,
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
    path("company-context/", CompanyContextView.as_view(), name="company-context"),
    path("company-branding/", CompanyBrandingView.as_view(), name="company-branding"),
    path(
        "company-business-settings/",
        CompanyBusinessSettingsView.as_view(),
        name="company-business-settings",
    ),
    path(
        "company-operational-readiness/",
        CompanyOperationalReadinessView.as_view(),
        name="company-operational-readiness",
    ),
    path("me/", MeView.as_view(), name="me"),
    path("me/permissions/", MePermissionsView.as_view(), name="me-permissions"),
    path(
        "me/platform-capabilities/",
        MePlatformCapabilitiesView.as_view(),
        name="me-platform-capabilities",
    ),
    path("me/access-scopes/", MeAccessScopesView.as_view(), name="me-access-scopes"),
]
