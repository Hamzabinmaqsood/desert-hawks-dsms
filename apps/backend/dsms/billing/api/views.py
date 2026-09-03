from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
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
    ClientInvoiceLine,
    ClientReceipt,
    TaxCode,
)
from ..selectors import get_accounts_receivable_ageing, get_client_account_balance
from ..services import (
    add_invoice_line,
    allocate_receipt,
    approve_credit_note,
    approve_debit_note,
    approve_invoice,
    confirm_receipt,
    create_invoice,
    delete_invoice_line,
    issue_credit_note,
    issue_debit_note,
    issue_invoice,
    reverse_receipt,
    submit_invoice,
    update_invoice_draft,
    update_invoice_line,
)
from .serializers import (
    BillingProfileSerializer,
    BillingRuleSerializer,
    BillingScheduleSerializer,
    CollectionActivitySerializer,
    CreditNoteSerializer,
    DebitNoteSerializer,
    InvoiceCreateSerializer,
    InvoiceDraftUpdateSerializer,
    InvoiceLineSerializer,
    InvoiceLineWriteSerializer,
    InvoiceReadSerializer,
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


@extend_schema_view(
    line_detail=extend_schema(
        parameters=[OpenApiParameter("line_id", OpenApiTypes.UUID, OpenApiParameter.PATH)]
    )
)
class InvoiceViewSet(viewsets.ModelViewSet[ClientInvoice]):
    serializer_class = InvoiceReadSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]
    custom_action_permissions = {
        "submit": "billing.change_clientinvoice",
        "approve": "billing.approve_invoice",
        "issue": "billing.issue_invoice",
        "download": "billing.download_invoice",
        "lines": "billing.change_clientinvoice",
        "line_detail": "billing.change_clientinvoice",
    }
    filterset_fields = ["company", "client", "contract", "status", "invoice_type"]
    search_fields = ["invoice_number", "client_reference", "client_po_reference"]
    ordering_fields = ["invoice_date", "due_date", "total_amount", "created_at"]

    def _permission(self) -> str:
        if self.action in self.custom_action_permissions:
            return self.custom_action_permissions[self.action]
        return {
            "create": "billing.add_clientinvoice",
            "update": "billing.change_clientinvoice",
            "partial_update": "billing.change_clientinvoice",
        }.get(self.action, "billing.view_clientinvoice")

    def get_queryset(self) -> Any:
        queryset = ClientInvoice.objects.select_related(
            "company", "client", "contract"
        ).prefetch_related("lines")
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self._permission()
        )
        return queryset.filter(company_id__in=ids).order_by("-created_at")

    def get_serializer_class(self) -> Any:
        if self.action == "create":
            return InvoiceCreateSerializer
        if self.action in {"update", "partial_update"}:
            return InvoiceDraftUpdateSerializer
        if self.action in {"lines", "line_detail"}:
            return InvoiceLineWriteSerializer
        return InvoiceReadSerializer

    def create(self, request: Any) -> response.Response:
        writer = self.get_serializer(data=request.data)
        writer.is_valid(raise_exception=True)
        data = dict(writer.validated_data)
        profile = data.pop("billing_profile")
        if not access.has_permission(
            user=cast(User, request.user),
            permission="billing.add_clientinvoice",
            company=profile.company,
        ):
            raise PermissionDenied
        lines = data.pop("lines", [])
        try:
            item = create_invoice(profile=profile, actor=request.user, lines=lines, **data)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                exc.message_dict if hasattr(exc, "message_dict") else exc.messages
            ) from exc
        return response.Response(InvoiceReadSerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Any, *args: Any, **kwargs: Any) -> response.Response:
        item = self.get_object()
        writer = self.get_serializer(item, data=request.data, partial=True)
        writer.is_valid(raise_exception=True)
        try:
            updated = update_invoice_draft(
                invoice=item, actor=request.user, values=writer.validated_data
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return response.Response(InvoiceReadSerializer(updated).data)

    @decorators.action(detail=True, methods=["post"])
    def lines(self, request: Any, pk: Any = None) -> response.Response:
        invoice = self.get_object()
        writer = self.get_serializer(data=request.data)
        writer.is_valid(raise_exception=True)
        try:
            line = add_invoice_line(
                invoice=invoice, actor=request.user, values=writer.validated_data
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return response.Response(InvoiceLineSerializer(line).data, status=status.HTTP_201_CREATED)

    @decorators.action(
        detail=True, methods=["patch", "delete"], url_path=r"lines/(?P<line_id>[^/.]+)"
    )
    def line_detail(self, request: Any, pk: Any = None, line_id: Any = None) -> response.Response:
        invoice = self.get_object()
        line = get_object_or_404(ClientInvoiceLine.objects.filter(invoice=invoice), pk=line_id)
        try:
            if request.method == "DELETE":
                delete_invoice_line(invoice=invoice, line=line, actor=request.user)
                return response.Response(status=status.HTTP_204_NO_CONTENT)
            writer = self.get_serializer(data=request.data, partial=True)
            writer.is_valid(raise_exception=True)
            line = update_invoice_line(
                invoice=invoice, line=line, actor=request.user, values=writer.validated_data
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return response.Response(InvoiceLineSerializer(line).data)

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
    custom_action_permissions = {
        "confirm": "billing.confirm_receipt",
        "allocate": "billing.allocate_receipt",
        "reverse": "billing.reverse_receipt",
    }

    def _permission(self) -> str:
        return self.custom_action_permissions.get(
            self.action,
            "billing.add_clientreceipt"
            if self.action == "create"
            else "billing.change_clientreceipt"
            if self.action in {"update", "partial_update"}
            else "billing.view_clientreceipt",
        )

    def get_queryset(self) -> Any:
        queryset = ClientReceipt.objects.select_related(
            "company", "client", "received_by"
        ).prefetch_related("allocations")
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self._permission()
        )
        return queryset.filter(company_id__in=ids).order_by("-created_at")

    def perform_create(self, serializer: Any) -> None:
        company = serializer.validated_data["company"]
        if not access.has_permission(
            user=cast(User, self.request.user),
            permission="billing.add_clientreceipt",
            company=company,
        ):
            raise PermissionDenied
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
        receipt = self.get_object()
        invoice = get_object_or_404(
            ClientInvoice.objects.filter(company=receipt.company, client=receipt.client),
            pk=request.data.get("invoice"),
        )
        try:
            allocation = allocate_receipt(
                receipt=receipt,
                invoice=invoice,
                amount=Decimal(request.data["amount"]),
                actor=request.user,
            )
        except (
            DjangoValidationError,
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
        receipt = self.get_object()
        try:
            reverse_receipt(
                receipt=receipt,
                actor=request.user,
                reason=str(request.data.get("reason", "")),
            )
        except DjangoValidationError as exc:
            return response.Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        receipt.refresh_from_db()
        return response.Response(self.get_serializer(receipt).data)


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

        company = get_object_or_404(Company, pk=company_id)
        if not access.has_permission(
            user=cast(User, request.user), permission=self.required_permission, company=company
        ):
            raise Http404
        return response.Response({"ageing": get_accounts_receivable_ageing(company=company)})

    @decorators.action(detail=False, methods=["get"])
    def client_balance(self, request: Any) -> response.Response:
        from dsms.contracts.models import Client

        client = get_object_or_404(Client, pk=request.query_params.get("client"))
        if not access.has_permission(
            user=cast(User, request.user),
            permission=self.required_permission,
            company=client.company,
        ):
            raise Http404
        return response.Response(get_client_account_balance(client))


class CreditNoteViewSet(viewsets.ReadOnlyModelViewSet[ClientCreditNote]):
    queryset = ClientCreditNote.objects.select_related(
        "company", "client", "invoice"
    ).prefetch_related("lines")
    serializer_class = CreditNoteSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    custom_action_permissions = {
        "approve": "billing.approve_credit_note",
        "issue": "billing.issue_credit_note",
    }

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission="billing.view_clientcreditnote"
        )
        return self.queryset.filter(company_id__in=ids)

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
    custom_action_permissions = {
        "approve": "billing.approve_debit_note",
        "issue": "billing.issue_debit_note",
    }

    def get_queryset(self) -> Any:
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission="billing.view_clientdebitnote"
        )
        return self.queryset.filter(company_id__in=ids)

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
