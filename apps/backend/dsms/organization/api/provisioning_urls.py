from django.urls import path

from .provisioning_views import TenantProvisioningCollectionView, TenantProvisioningDetailView

urlpatterns = [
    path("", TenantProvisioningCollectionView.as_view(), name="tenant-provisioning-list"),
    path(
        "<uuid:provisioning_id>/",
        TenantProvisioningDetailView.as_view(),
        name="tenant-provisioning-detail",
    ),
]
