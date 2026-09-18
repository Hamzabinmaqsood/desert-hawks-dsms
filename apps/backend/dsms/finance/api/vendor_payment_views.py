from typing import Any, cast

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404
from rest_framework import decorators, permissions, response, serializers, viewsets
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import BasePermission

from dsms.identity import access
from dsms.identity.models import User

from .. import domain_services
from ..enums import AccountType, PaymentStatus, WorkflowStatus
from ..exceptions import FinanceError, to_error_dict
from ..models import Account
from ..procurement_models import PaymentVoucher, VendorBill
from .vendor_payment_serializers import (
    PayableVendorBillSerializer,
    PaymentAccountSerializer,
    PayVendorPaymentSerializer,
    VendorPaymentDetailSerializer,
    VendorPaymentListSerializer,
    VendorPaymentWriteSerializer,
)

PAYMENT_REFERENCE_PERMISSIONS = (
    "finance.view_paymentvoucher",
    "finance.add_paymentvoucher",
    "finance.change_paymentvoucher",
    "finance.approve_finance",
    "finance.post_journal",
)


class VendorPaymentPermission(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        code = {
            "create": "finance.add_paymentvoucher",
            "partial_update": "finance.change_paymentvoucher",
            "update": "finance.change_paymentvoucher",
            "submit": "finance.change_paymentvoucher",
            "approve": "finance.approve_finance",
            "reject": "finance.approve_finance",
            "pay": "finance.post_journal",
        }.get(view.action, "finance.view_paymentvoucher")
        return code in access.get_effective_permissions(user)


class VendorPaymentViewSet(viewsets.ModelViewSet[PaymentVoucher]):
    permission_classes = [permissions.IsAuthenticated, VendorPaymentPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["status", "payment_status", "vendor_bill"]
    search_fields = ["voucher_number", "payment_reference", "vendor_bill__bill_number"]
    ordering_fields = ["payment_date", "amount", "created_at"]
    ordering = ["-created_at"]

    def _permission(self) -> str:
        return {
            "create": "finance.add_paymentvoucher",
            "partial_update": "finance.change_paymentvoucher",
            "update": "finance.change_paymentvoucher",
            "submit": "finance.change_paymentvoucher",
            "approve": "finance.approve_finance",
            "reject": "finance.approve_finance",
            "pay": "finance.post_journal",
        }.get(self.action, "finance.view_paymentvoucher")

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self._permission()
        )
        return PaymentVoucher.objects.filter(company_id__in=ids).select_related(
            "vendor_bill__vendor"
        )

    def get_serializer_class(self) -> Any:
        if self.action in {"create", "partial_update", "update"}:
            return VendorPaymentWriteSerializer
        if self.action == "pay":
            return PayVendorPaymentSerializer
        return (
            VendorPaymentDetailSerializer
            if self.action == "retrieve"
            else VendorPaymentListSerializer
        )

    def create(self, request: Any) -> response.Response:
        writer = self.get_serializer(data=request.data)
        writer.is_valid(raise_exception=True)
        data = dict(writer.validated_data)
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission="finance.add_paymentvoucher"
        )
        bill = get_object_or_404(
            VendorBill.objects.select_related("vendor__payable_account").filter(company_id__in=ids),
            pk=data.pop("vendor_bill"),
        )
        try:
            domain_services.validate_vendor_payment_values(bill=bill, amount=data["amount"])
            with transaction.atomic():
                item = PaymentVoucher.objects.create(
                    company=bill.company,
                    vendor_bill=bill,
                    created_by=request.user,
                    status=WorkflowStatus.DRAFT,
                    payment_status=PaymentStatus.PENDING,
                    **data,
                )
        except IntegrityError as exc:
            raise serializers.ValidationError(
                {"voucher_number": ["This Voucher number already exists."]}
            ) from exc
        except FinanceError as exc:
            raise serializers.ValidationError(to_error_dict(exc)) from exc
        return response.Response(VendorPaymentDetailSerializer(item).data, status=201)

    def partial_update(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        item = self.get_object()
        if item.status != WorkflowStatus.DRAFT:
            raise serializers.ValidationError({"status": ["Only a draft Voucher can be edited."]})
        writer = self.get_serializer(item, data=request.data, partial=True)
        writer.is_valid(raise_exception=True)
        data = dict(writer.validated_data)
        bill_id = data.pop("vendor_bill", item.vendor_bill_id)
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission="finance.change_paymentvoucher"
        )
        bill = get_object_or_404(VendorBill.objects.filter(company_id__in=ids), pk=bill_id)
        try:
            domain_services.validate_vendor_payment_values(
                bill=bill, amount=data.get("amount", item.amount)
            )
            for field, value in {**data, "vendor_bill": bill}.items():
                setattr(item, field, value)
            item.save()
        except (IntegrityError, FinanceError) as exc:
            if isinstance(exc, IntegrityError):
                raise serializers.ValidationError(
                    {"voucher_number": ["This Voucher number already exists."]}
                ) from exc
            raise serializers.ValidationError(to_error_dict(exc)) from exc
        return response.Response(VendorPaymentDetailSerializer(item).data)

    def destroy(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        raise MethodNotAllowed("DELETE")

    def _workflow(self, operation: Any, **kwargs: Any) -> response.Response:
        try:
            item = operation(
                voucher=self.get_object(), actor=cast(User, self.request.user), **kwargs
            )
        except FinanceError as exc:
            raise serializers.ValidationError(to_error_dict(exc)) from exc
        return response.Response(VendorPaymentDetailSerializer(item).data)

    @decorators.action(detail=True, methods=["post"])
    def submit(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow(domain_services.submit_vendor_payment)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow(domain_services.approve_vendor_payment)

    @decorators.action(detail=True, methods=["post"])
    def reject(self, request: Any, pk: Any = None) -> response.Response:
        return self._workflow(
            domain_services.reject_vendor_payment,
            reason=str(request.data.get("reason", "")),
        )

    @decorators.action(detail=True, methods=["post"])
    def pay(self, request: Any, pk: Any = None) -> response.Response:
        writer = self.get_serializer(data=request.data)
        writer.is_valid(raise_exception=True)
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission="finance.post_journal"
        )
        account = get_object_or_404(
            Account.objects.filter(company_id__in=ids),
            pk=writer.validated_data["payment_account"],
        )
        return self._workflow(
            domain_services.pay_vendor_voucher,
            cash_account=account,
            reference=str(writer.validated_data.get("payment_reference", "")),
        )


class PaymentReferencePermission(BasePermission):
    def has_permission(self, request: Any, view: Any) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or access.get_effective_permissions(user).intersection(
                    PAYMENT_REFERENCE_PERMISSIONS
                )
            )
        )


def _reference_company_ids(user: User) -> set[Any]:
    ids: set[Any] = set()
    for permission in PAYMENT_REFERENCE_PERMISSIONS:
        ids.update(access.get_fully_accessible_company_ids(user, permission=permission))
    return ids


class PayableVendorBillViewSet(viewsets.ReadOnlyModelViewSet[VendorBill]):
    serializer_class = PayableVendorBillSerializer
    permission_classes = [permissions.IsAuthenticated, PaymentReferencePermission]
    pagination_class = None

    def get_queryset(self) -> Any:
        return (
            VendorBill.objects.filter(
                company_id__in=_reference_company_ids(cast(User, self.request.user)),
                status__in=[WorkflowStatus.POSTED, WorkflowStatus.PARTIALLY_PAID],
                total_amount__gt=F("paid_amount"),
            )
            .select_related("vendor")
            .order_by("due_date", "bill_number")
        )


class PaymentAccountViewSet(viewsets.ReadOnlyModelViewSet[Account]):
    serializer_class = PaymentAccountSerializer
    permission_classes = [permissions.IsAuthenticated, PaymentReferencePermission]
    pagination_class = None

    def get_queryset(self) -> Any:
        return (
            Account.objects.filter(
                company_id__in=_reference_company_ids(cast(User, self.request.user)),
                account_type=AccountType.ASSET,
                is_active=True,
                allow_posting=True,
            )
            .filter(
                Q(cash_account__company_id=F("company_id"), cash_account__is_active=True)
                | Q(bank_account__company_id=F("company_id"), bank_account__is_active=True)
            )
            .distinct()
            .order_by("company_id", "code")
        )
