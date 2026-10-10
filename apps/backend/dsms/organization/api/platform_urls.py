from django.urls import path

from .provisioning_views import PlatformTenantDirectoryView

urlpatterns = [
    path("tenants/", PlatformTenantDirectoryView.as_view(), name="platform-tenant-directory"),
]
