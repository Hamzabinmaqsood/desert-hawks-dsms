from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import decorators, permissions, response, serializers, status, viewsets
from rest_framework.exceptions import PermissionDenied

from dsms.finance.services import next_document_number
from dsms.identity import access
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission, RequiresPermission

from ..models import (
    BillingRule,
    BillingSchedule,
    ClientBillingProfile,
    ClientCollectionActivity,
    ClientCreditNote,
    ClientDebitNote,
    ClientInvoice,
    ClientReceipt,
    TaxCode,
)
from ..selectors import get_accounts_receivable_ageing, get_client_account_balance
from ..services import (
    allocate_receipt,
    approve_credit_note,
    approve_debit_note,
    approve_invoice,
    confirm_receipt,
    create_credit_note,
    create_debit_note,
    issue_credit_note,
    issue_debit_note,
    issue_invoice,
    reverse_receipt,
    submit_invoice,
)
from .serializers import (
    BillingProfileSerializer,
    BillingRuleSerializer,
    BillingScheduleSerializer,
    CollectionActivitySerializer,
    CreditNoteSerializer,
    DebitNoteSerializer,
    InvoiceSerializer,
    ReceiptSerializer,
    TaxCodeSerializer,
)


class NoDeleteViewSet(viewsets.ModelViewSet[Any]):
    http_method_names = ["get", "post", "put", "patch", "head", "options"]
    company_lookup = "company_id"

    def get_queryset(self) -> Any:
        queryset = super().get_queryset()
        model = queryset.model
        permission = f"{model._meta.app_label}.view_{model._meta.model_name}"
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=permission
        )
        return queryset.filter(**{f"{self.company_lookup}__in": ids})


class BillingProfileViewSet(NoDeleteViewSet):
    queryset = ClientBillingProfile.objects.select_related("company", "client")
    serializer_class = BillingProfileSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "client", "is_active"]
    search_fields = ["billing_name", "billing_email"]


class BillingScheduleViewSet(NoDeleteViewSet):
    queryset = BillingSchedule.objects.select_related("company", "client", "contract")
    serializer_class = BillingScheduleSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "client", "contract", "frequency", "is_active"]

    def perform_create(self, serializer: Any) -> None:
        serializer.save(created_by=self.request.user)


class BillingRuleViewSet(NoDeleteViewSet):
    queryset = BillingRule.objects.select_related("billing_schedule", "revenue_account", "tax_code")
    serializer_class = BillingRuleSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    company_lookup = "billing_schedule__company_id"


class TaxCodeViewSet(NoDeleteViewSet):
    queryset = TaxCode.objects.select_related("company", "tax_account")
    serializer_class = TaxCodeSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet[ClientInvoice]):
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "client", "contract", "status", "invoice_type"]
    search_fields = ["invoice_number", "client_reference", "client_po_reference"]
    ordering_fields = ["invoice_date", "due_date", "total_amount", "created_at"]

    def get_queryset(self) -> Any:
        queryset = ClientInvoice.objects.select_related(
            "company", "client", "contract"
        ).prefetch_related("lines")
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission="billing.view_clientinvoice"
        )
        return queryset.filter(company_id__in=ids)

    def _run(self, function: Callable[..., ClientInvoice]) -> response.Response:
        try:
            kwargs: dict[str, Any] = {"invoice": self.get_object()}
            if function in {approve_invoice, issue_invoice}:
                kwargs["actor"] = self.request.user
            item = function(**kwargs)
        except DjangoValidationError as exc:
            return response.Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response(self.get_serializer(item).data)

    @decorators.action(detail=True, methods=["post"])
    def submit(self, request: Any, pk: Any = None) -> response.Response:
        return self._run(submit_invoice)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request: Any, pk: Any = None) -> response.Response:
        return self._run(approve_invoice)

    @decorators.action(detail=True, methods=["post"])
    def issue(self, request: Any, pk: Any = None) -> response.Response:
        return self._run(issue_invoice)

    @decorators.action(detail=True, methods=["get"])
    def download(self, request: Any, pk: Any = None) -> FileResponse:
        document = self.get_object().documents.order_by("-revision_number").first()
        if not document:
            raise Http404
        return FileResponse(
            document.file.open("rb"),
            as_attachment=True,
            filename=f"invoice-{document.invoice.invoice_number}.pdf",
            content_type="application/pdf",
        )


class ReceiptViewSet(NoDeleteViewSet):
    serializer_class = ReceiptSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    filterset_fields = ["company", "client", "status", "payment_method"]

    def get_queryset(self) -> Any:
        queryset = ClientReceipt.objects.select_related(
            "company", "client", "received_by"
        ).prefetch_related("allocations")
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission="billing.view_clientreceipt"
        )
        return queryset.filter(company_id__in=ids)

    def perform_create(self, serializer: Any) -> None:
        company = serializer.validated_data["company"]
        number = next_document_number(
            company=company, prefix="RCPT", year=timezone.localdate().year
        )
        serializer.save(received_by=self.request.user, receipt_number=number)

    @decorators.action(detail=True, methods=["post"])
    def confirm(self, request: Any, pk: Any = None) -> response.Response:
        try:
            item = confirm_receipt(receipt=self.get_object(), actor=request.user)
        except DjangoValidationError as exc:
            return response.Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response(self.get_serializer(item).data)

    @decorators.action(detail=True, methods=["post"])
    def allocate(self, request: Any, pk: Any = None) -> response.Response:
        try:
            allocation = allocate_receipt(
                receipt=self.get_object(),
                invoice=ClientInvoice.objects.get(pk=request.data["invoice"]),
                amount=Decimal(request.data["amount"]),
                actor=request.user,
            )
        except (
            DjangoValidationError,
            ClientInvoice.DoesNotExist,
            KeyError,
            ArithmeticError,
        ) as exc:
            detail = (
                exc.messages
                if isinstance(exc, DjangoValidationError)
                else ["Invalid allocation request."]
            )
            return response.Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response(
            {"id": allocation.pk, "amount": allocation.amount}, status=status.HTTP_201_CREATED
        )

    @decorators.action(detail=True, methods=["post"])
    def reverse(self, request: Any, pk: Any = None) -> response.Response:
        try:
            item = reverse_receipt(
                receipt=self.get_object(),
                actor=request.user,
                reason=str(request.data.get("reason", "")),
            )
        except DjangoValidationError as exc:
            return response.Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        return response.Response(self.get_serializer(item).data)


class BillingDashboardSerializer(serializers.Serializer[Any]):
    """Schema marker for aggregate dashboard dictionaries."""


class DashboardViewSet(viewsets.ViewSet):
    serializer_class = BillingDashboardSerializer
    permission_classes = [permissions.IsAuthenticated, RequiresPermission]
    required_permission = "billing.view_clientinvoice"

    def list(self, request: Any) -> response.Response:
        company_id = request.query_params.get("company")
        if not company_id:
            return response.Response({"detail": "company is required"}, status=400)
        from dsms.organization.models import Company

        company = Company.objects.get(pk=company_id)
        if not access.has_permission(
            user=cast(User, request.user), permission=self.required_permission, company=company
        ):
            raise PermissionDenied
        return response.Response({"ageing": get_accounts_receivable_ageing(company=company)})

    @decorators.action(detail=False, methods=["get"])
    def client_balance(self, request: Any) -> response.Response:
        from dsms.contracts.models import Client

        client = Client.objects.get(pk=request.query_params["client"])
        if not access.has_permission(
            user=cast(User, request.user),
            permission=self.required_permission,
            company=client.company,
        ):
            raise PermissionDenied
        return response.Response(get_client_account_balance(client))


class CreditNoteViewSet(viewsets.ReadOnlyModelViewSet[ClientCreditNote]):
    queryset = ClientCreditNote.objects.select_related(
        "company", "client", "invoice"
    ).prefetch_related("lines")
    serializer_class = CreditNoteSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "approve": "billing.approve_invoice",
        "issue": "billing.issue_invoice",
    }

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission="billing.view_clientcreditnote"
        )
        return self.queryset.filter(company_id__in=ids)

    def create(self, request: Any) -> response.Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lines = data.pop("lines")
        item = create_credit_note(
            invoice=data["invoice"], actor=request.user, reason=data["reason"], lines=lines
        )
        return response.Response(self.get_serializer(item).data, status=201)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request: Any, pk: Any = None) -> response.Response:
        return response.Response(
            self.get_serializer(
                approve_credit_note(note=self.get_object(), actor=request.user)
            ).data
        )

    @decorators.action(detail=True, methods=["post"])
    def issue(self, request: Any, pk: Any = None) -> response.Response:
        return response.Response(
            self.get_serializer(issue_credit_note(note=self.get_object(), actor=request.user)).data
        )


class DebitNoteViewSet(viewsets.ReadOnlyModelViewSet[ClientDebitNote]):
    queryset = ClientDebitNote.objects.select_related(
        "company", "client", "invoice"
    ).prefetch_related("lines")
    serializer_class = DebitNoteSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    custom_action_permissions = CreditNoteViewSet.custom_action_permissions

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission="billing.view_clientdebitnote"
        )
        return self.queryset.filter(company_id__in=ids)

    def create(self, request: Any) -> response.Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        lines = data.pop("lines")
        invoice = data.get("invoice")
        if invoice is None:
            raise serializers.ValidationError({"invoice": "A source invoice is required."})
        profile = ClientBillingProfile.objects.get(client=invoice.client)
        item = create_debit_note(
            profile=profile, invoice=invoice, actor=request.user, reason=data["reason"], lines=lines
        )
        return response.Response(self.get_serializer(item).data, status=201)

    @decorators.action(detail=True, methods=["post"])
    def approve(self, request: Any, pk: Any = None) -> response.Response:
        return response.Response(
            self.get_serializer(approve_debit_note(note=self.get_object(), actor=request.user)).data
        )

    @decorators.action(detail=True, methods=["post"])
    def issue(self, request: Any, pk: Any = None) -> response.Response:
        return response.Response(
            self.get_serializer(issue_debit_note(note=self.get_object(), actor=request.user)).data
        )


class CollectionActivityViewSet(NoDeleteViewSet):
    queryset = ClientCollectionActivity.objects.select_related("company", "client", "invoice")
    serializer_class = CollectionActivitySerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]

    def perform_create(self, serializer: Any) -> None:
        serializer.save(actor=self.request.user)
