from decimal import Decimal
from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Company
from dsms.workforce.models import Employee

from ..payment_models import (
    PaymentBatch,
    PaymentBeneficiaryProfile,
    PaymentInstruction,
    PaymentProviderConfiguration,
    PaymentProviderSettlement,
    PaymentProviderSettlementLine,
)
from ..payment_services import (
    activate_payment_destination,
    approve_payment_batch,
    approve_payment_destination_change,
    create_payroll_disbursement_batch,
    create_vendor_payment_batch,
    query_payment_instruction_status,
    reconcile_settlement,
    record_manual_payment_success,
    release_payment_batch,
    request_payment_destination_change,
    retry_failed_payment,
    submit_payment_batch,
    verify_payment_destination_change,
)
from ..payroll_models import PayrollRun
from ..procurement_models import PaymentVoucher, Vendor
from .payment_serializers import (
    DestinationRequestSerializer,
    ManualPaymentSuccessSerializer,
    PaymentBatchCreateSerializer,
    PaymentBatchSerializer,
    PaymentBeneficiarySerializer,
    PaymentInstructionSerializer,
    PaymentProviderSerializer,
    PaymentSettlementSerializer,
)
from .views import FinancePermission


def _call(function: Any, **kwargs: Any) -> Any:
    try:
        return function(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        ) from exc


class PaymentScopedViewSet(viewsets.GenericViewSet[Any]):
    permission_classes = [FinancePermission]

    def company_ids(self) -> set[Any]:
        permission = getattr(self, "action_permissions", {}).get(
            self.action, getattr(self, "permission_code", "finance.view_paymentbatch")
        )
        return access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=permission
        )

    def guard_company(self, company: Company, permission: str) -> None:
        if not access.has_permission(
            user=cast(User, self.request.user), permission=permission, company=company
        ):
            raise PermissionDenied("Company-scoped payment permission required.")


class PaymentProviderViewSet(viewsets.ModelViewSet[PaymentProviderConfiguration]):
    permission_classes = [FinancePermission]
    permission_code = "finance.manage_payment_providers"
    serializer_class = PaymentProviderSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self.permission_code
        )
        return PaymentProviderConfiguration.objects.filter(company_id__in=ids)

    def perform_create(self, serializer: Any) -> None:
        company = serializer.validated_data["company"]
        if company.id not in access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self.permission_code
        ):
            raise PermissionDenied
        serializer.save(created_by=self.request.user)


class PaymentBeneficiaryViewSet(PaymentScopedViewSet):
    serializer_class = PaymentBeneficiarySerializer
    permission_code = "finance.view_sensitive_payment_destination"
    action_permissions = {
        "create": "finance.prepare_payment_batch",
        "verify": "finance.approve_payment_destination",
        "approve": "finance.approve_payment_destination",
        "activate": "finance.approve_payment_destination",
    }

    def get_queryset(self) -> Any:
        return PaymentBeneficiaryProfile.objects.filter(company_id__in=self.company_ids())

    def list(self, request: Request) -> Response:
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def retrieve(self, request: Request, pk: Any = None) -> Response:
        return Response(self.get_serializer(self.get_object()).data)

    def create(self, request: Request) -> Response:
        payload = DestinationRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        company = Company.objects.get(pk=data.pop("company"))
        self.guard_company(company, self.action_permissions["create"])
        employee = Employee.objects.filter(pk=data.pop("employee", None), company=company).first()
        vendor = Vendor.objects.filter(pk=data.pop("vendor", None), company=company).first()
        item = _call(
            request_payment_destination_change,
            company=company,
            actor=request.user,
            employee=employee,
            vendor=vendor,
            **data,
        )
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    def _transition(self, request: Request, function: Any) -> Response:
        return Response(
            self.get_serializer(_call(function, profile=self.get_object(), actor=request.user)).data
        )

    @action(detail=True, methods=["post"])
    def verify(self, request: Request, pk: Any = None) -> Response:
        return self._transition(request, verify_payment_destination_change)

    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: Any = None) -> Response:
        return self._transition(request, approve_payment_destination_change)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, pk: Any = None) -> Response:
        return self._transition(request, activate_payment_destination)


class PaymentBatchViewSet(PaymentScopedViewSet):
    serializer_class = PaymentBatchSerializer
    permission_code = "finance.prepare_payment_batch"
    action_permissions = {
        "approve": "finance.approve_payment_batch",
        "release": "finance.release_payment_batch",
    }

    def get_queryset(self) -> Any:
        return PaymentBatch.objects.filter(company_id__in=self.company_ids()).prefetch_related(
            "instructions"
        )

    def list(self, request: Request) -> Response:
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def retrieve(self, request: Request, pk: Any = None) -> Response:
        return Response(self.get_serializer(self.get_object()).data)

    def create(self, request: Request) -> Response:
        payload = PaymentBatchCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        provider = data["provider"]
        self.guard_company(provider.company, self.permission_code)
        if data.get("payroll_run"):
            item = _call(
                create_payroll_disbursement_batch,
                payroll_run=PayrollRun.objects.get(pk=data["payroll_run"]),
                provider=provider,
                actor=request.user,
            )
        else:
            vouchers = list(PaymentVoucher.objects.filter(pk__in=data.get("vouchers", [])))
            item = _call(
                create_vendor_payment_batch,
                vouchers=vouchers,
                provider=provider,
                actor=request.user,
            )
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    def _transition(self, request: Request, function: Any) -> Response:
        return Response(
            self.get_serializer(_call(function, batch=self.get_object(), actor=request.user)).data
        )

    @action(detail=True, methods=["post"])
    def submit(self, request: Request, pk: Any = None) -> Response:
        return self._transition(request, submit_payment_batch)

    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: Any = None) -> Response:
        return self._transition(request, approve_payment_batch)

    @action(detail=True, methods=["post"])
    def release(self, request: Request, pk: Any = None) -> Response:
        return self._transition(request, release_payment_batch)


class PaymentInstructionViewSet(PaymentScopedViewSet):
    serializer_class = PaymentInstructionSerializer
    permission_code = "finance.view_paymentinstruction"
    action_permissions = {
        "retry": "finance.retry_payment",
        "query": "finance.retry_payment",
        "manual_success": "finance.reconcile_payment_settlement",
    }

    def get_queryset(self) -> Any:
        return PaymentInstruction.objects.filter(batch__company_id__in=self.company_ids())

    def list(self, request: Request) -> Response:
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def retrieve(self, request: Request, pk: Any = None) -> Response:
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"])
    def retry(self, request: Request, pk: Any = None) -> Response:
        item = _call(retry_failed_payment, instruction=self.get_object(), actor=request.user)
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def query(self, request: Request, pk: Any = None) -> Response:
        item = _call(query_payment_instruction_status, instruction=self.get_object())
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"], url_path="manual-success")
    def manual_success(self, request: Request, pk: Any = None) -> Response:
        payload = ManualPaymentSuccessSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        item = _call(
            record_manual_payment_success,
            instruction=self.get_object(),
            actor=request.user,
            **payload.validated_data,
        )
        return Response(self.get_serializer(item).data)


class PaymentSettlementViewSet(PaymentScopedViewSet):
    serializer_class = PaymentSettlementSerializer
    permission_code = "finance.import_payment_settlement"
    action_permissions = {"reconcile": "finance.reconcile_payment_settlement"}

    def get_queryset(self) -> Any:
        return PaymentProviderSettlement.objects.filter(
            company_id__in=self.company_ids()
        ).prefetch_related("lines")

    def list(self, request: Request) -> Response:
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    def retrieve(self, request: Request, pk: Any = None) -> Response:
        return Response(self.get_serializer(self.get_object()).data)

    @transaction.atomic
    def create(self, request: Request) -> Response:
        payload = self.get_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data
        lines = data.pop("lines")
        provider = data["provider"]
        self.guard_company(provider.company, self.permission_code)
        gross = sum((line["amount"] for line in lines), Decimal("0"))
        fees = sum((line.get("fee_amount", Decimal("0")) for line in lines), Decimal("0"))
        if (
            gross != data["gross_amount"]
            or fees != data["fee_amount"]
            or data["net_amount"] != data["gross_amount"] + data["fee_amount"]
            or any(line["currency"] != data["currency"] for line in lines)
            or len({line["provider_reference"] for line in lines}) != len(lines)
        ):
            raise ValidationError("Settlement totals, currency, or references are invalid.")
        item = PaymentProviderSettlement.objects.create(
            imported_by=cast(User, request.user), **data
        )
        PaymentProviderSettlementLine.objects.bulk_create(
            [PaymentProviderSettlementLine(settlement=item, **line) for line in lines]
        )
        return Response(self.get_serializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def reconcile(self, request: Request, pk: Any = None) -> Response:
        item = _call(reconcile_settlement, settlement=self.get_object(), actor=request.user)
        return Response(self.get_serializer(item).data)
