from typing import Any, cast

from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.serializers import BaseSerializer

from dsms.identity import access
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission

from ..enums import AccountType
from ..models import Account
from ..payment_models import PaymentAccountingProfile
from ..procurement_models import Vendor
from ..tenant_queries import tenant_consistent_vendors
from .vendor_serializers import VendorPayableAccountSerializer, VendorSerializer

VENDOR_REFERENCE_PERMISSIONS = (
    "finance.view_vendor",
    "finance.add_vendor",
    "finance.change_vendor",
)


class VendorReferencePermission(BasePermission):
    def has_permission(self, request: Request, view: Any) -> bool:
        user = cast(User, request.user)
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or access.get_effective_permissions(user).intersection(VENDOR_REFERENCE_PERMISSIONS)
            )
        )


class VendorViewSet(viewsets.ModelViewSet[Vendor]):
    serializer_class = VendorSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["is_active"]
    search_fields = ["code", "name", "tax_number", "email"]
    ordering_fields = ["code", "name", "created_at"]
    ordering = ["code"]

    def get_queryset(self) -> Any:
        permission = (
            "finance.change_vendor"
            if self.action in {"partial_update", "update"}
            else "finance.view_vendor"
        )
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=permission
        )
        return tenant_consistent_vendors(Vendor.objects.filter(company_id__in=ids)).select_related(
            "payable_account"
        )

    def perform_create(self, serializer: BaseSerializer[Vendor]) -> None:
        vendor_serializer = cast(VendorSerializer, serializer)
        account = vendor_serializer.validated_data["payable_account"]
        if not access.has_permission(
            user=cast(User, self.request.user),
            permission="finance.add_vendor",
            company=account.company,
        ):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Company-scoped Vendor permission required.")
        vendor_serializer.save()


class VendorPayableAccountViewSet(viewsets.ReadOnlyModelViewSet[Account]):
    serializer_class = VendorPayableAccountSerializer
    permission_classes = [permissions.IsAuthenticated, VendorReferencePermission]
    pagination_class = None

    def get_queryset(self) -> Any:
        user = cast(User, self.request.user)
        ids: set[Any] = set()
        for permission in VENDOR_REFERENCE_PERMISSIONS:
            ids.update(access.get_fully_accessible_company_ids(user, permission=permission))
        queryset = Account.objects.filter(
            company_id__in=ids,
            account_type=AccountType.LIABILITY,
            is_active=True,
            allow_posting=True,
        )
        configured = PaymentAccountingProfile.objects.filter(
            company_id__in=ids, is_active=True
        ).values("company_id", "vendor_payable_account_id")
        constrained_ids = {row["vendor_payable_account_id"] for row in configured}
        configured_companies = {row["company_id"] for row in configured}
        return queryset.filter(
            Q(company_id__in=ids - configured_companies) | Q(id__in=constrained_ids)
        ).order_by("code")
