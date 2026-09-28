from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from rest_framework import serializers

from dsms.contracts.models import ContractService, SecuritySite, ServiceContract
from dsms.finance.models import Account, CostCenter
from dsms.finance.operations_models import BankAccount
from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Company

from ..enums import InvoiceType
from ..models import (
    BillingRule,
    BillingSchedule,
    ClientBillingProfile,
    ClientCollectionActivity,
    ClientCreditNote,
    ClientCreditNoteLine,
    ClientDebitNote,
    ClientDebitNoteLine,
    ClientInvoice,
    ClientInvoiceLine,
    ClientReceipt,
    ClientReceiptAllocation,
    TaxCode,
)

ZERO = Decimal("0.00")


class TenantSafeBillingSerializer(serializers.ModelSerializer[Any]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        from .security import COMPANY_PATHS, GLOBAL_REFERENCES

        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if not isinstance(actor, User) or actor.is_superuser:
            return
        view = self.context.get("view")
        permission = view.get_scope_permission() if view is not None else None
        ids = access.get_fully_accessible_company_ids(actor, permission=permission)
        for field in self.fields.values():
            if not isinstance(field, serializers.PrimaryKeyRelatedField) or field.queryset is None:
                continue
            remote = field.queryset.model
            if remote is Company:
                field.queryset = field.queryset.filter(pk__in=ids, is_active=True)
                continue
            path = COMPANY_PATHS.get(remote)
            if path:
                condition = Q(**{f"{path}__in": ids})
                if remote in GLOBAL_REFERENCES:
                    condition |= Q(company__isnull=True)
                field.queryset = field.queryset.filter(condition)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        from .security import COMPANY_PATHS, GLOBAL_REFERENCES, PRIMARY_PARENT, company_id_for

        model = self.Meta.model
        instance = self.instance
        parent = PRIMARY_PARENT.get(model)
        if parent:
            if (
                instance is not None
                and parent in attrs
                and attrs[parent] != getattr(instance, parent)
            ):
                raise serializers.ValidationError({parent: "Tenant ownership cannot be changed."})
            owner = attrs.get(parent, getattr(instance, parent, None))
        else:
            if instance is not None and "company" in attrs and attrs["company"] != instance.company:
                raise serializers.ValidationError(
                    {"company": "Company ownership cannot be changed."}
                )
            owner = attrs.get("company", getattr(instance, "company", None))
        company_id = company_id_for(owner)
        errors: dict[str, str] = {}
        for field in model._meta.fields:  # type: ignore[attr-defined]
            remote = getattr(getattr(field, "remote_field", None), "model", None)
            if field.name == "company" or remote not in COMPANY_PATHS:
                continue
            related = attrs.get(field.name, getattr(instance, field.name, None))
            related_company_id = company_id_for(related)
            if (
                related is not None
                and related_company_id != company_id
                and not (remote in GLOBAL_REFERENCES and related_company_id is None)
            ):
                errors[field.name] = "Must belong to the same company."
        if model is BillingSchedule:
            client = attrs.get("client", getattr(instance, "client", None))
            contract = attrs.get("contract", getattr(instance, "contract", None))
            if client and contract and contract.client_id != client.pk:
                errors["contract"] = "Must belong to the selected client."
        if model is BillingRule:
            schedule = attrs.get("billing_schedule", getattr(instance, "billing_schedule", None))
            service = attrs.get("contract_service", getattr(instance, "contract_service", None))
            site = attrs.get("site", getattr(instance, "site", None))
            if schedule and service and service.contract_id != schedule.contract_id:
                errors["contract_service"] = "Must belong to the schedule contract."
            if schedule and site and site.contract_id != schedule.contract_id:
                errors["site"] = "Must belong to the schedule contract."
        if model is ClientCollectionActivity:
            client = attrs.get("client", getattr(instance, "client", None))
            invoice = attrs.get("invoice", getattr(instance, "invoice", None))
            if client and invoice and invoice.client_id != client.pk:
                errors["invoice"] = "Must belong to the selected client."
        if errors:
            raise serializers.ValidationError(errors)
        candidate = model(**{**({"id": instance.pk} if instance else {}), **attrs})  # type: ignore[misc]
        if instance is not None:
            for field in model._meta.fields:  # type: ignore[attr-defined]
                if field.name not in attrs and field.name != "id":
                    setattr(candidate, field.name, getattr(instance, field.name))
        if model in {ClientBillingProfile, BillingSchedule}:
            try:
                candidate.clean()
            except DjangoValidationError as exc:
                raise serializers.ValidationError(
                    exc.message_dict if hasattr(exc, "message_dict") else exc.messages
                ) from exc
        return attrs


class BillingProfileSerializer(TenantSafeBillingSerializer):
    class Meta:
        model = ClientBillingProfile
        fields = (
            "id",
            "created_at",
            "updated_at",
            "is_active",
            "client",
            "company",
            "billing_name",
            "billing_address",
            "billing_email",
            "billing_phone",
            "tax_registration_number",
            "payment_terms_days",
            "currency",
            "default_billing_frequency",
            "default_revenue_account",
            "default_receivable_account",
            "default_tax_account",
            "default_discount_account",
            "default_payment_instructions",
            "invoice_notes",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class BillingScheduleSerializer(TenantSafeBillingSerializer):
    class Meta:
        model = BillingSchedule
        fields = (
            "id",
            "created_at",
            "updated_at",
            "is_active",
            "company",
            "client",
            "contract",
            "frequency",
            "billing_day",
            "period_alignment",
            "first_billing_date",
            "next_billing_date",
            "end_date",
            "generate_days_before_period_end",
            "payment_terms_days",
            "auto_generate_draft",
            "created_by",
        )
        read_only_fields = ("id", "created_by", "next_billing_date", "created_at", "updated_at")


class BillingRuleSerializer(TenantSafeBillingSerializer):
    class Meta:
        model = BillingRule
        fields = (
            "id",
            "created_at",
            "updated_at",
            "is_active",
            "billing_schedule",
            "contract_service",
            "site",
            "description",
            "calculation_method",
            "quantity_source",
            "unit_price",
            "minimum_quantity",
            "maximum_quantity",
            "tax_code",
            "revenue_account",
            "cost_center",
            "effective_from",
            "effective_to",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class TaxCodeSerializer(TenantSafeBillingSerializer):
    class Meta:
        model = TaxCode
        fields = (
            "id",
            "created_at",
            "updated_at",
            "is_active",
            "company",
            "code",
            "name",
            "rate",
            "tax_account",
            "effective_from",
            "effective_to",
            "notes",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class InvoiceLineSerializer(serializers.ModelSerializer[ClientInvoiceLine]):
    class Meta:
        model = ClientInvoiceLine
        exclude = ("invoice",)
        read_only_fields = (
            "id",
            "line_number",
            "gross_amount",
            "taxable_amount",
            "tax_amount",
            "line_total",
            "created_at",
        )


class InvoiceReadSerializer(serializers.ModelSerializer[ClientInvoice]):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    pdf_available = serializers.SerializerMethodField()
    receipt_allocations = serializers.SerializerMethodField()

    class Meta:
        model = ClientInvoice
        exclude = ("accounting_journal",)
        read_only_fields = tuple(
            field.name for field in ClientInvoice._meta.fields if field.name != "accounting_journal"
        )

    def get_pdf_available(self, obj: ClientInvoice) -> bool:
        return obj.documents.exists()

    def get_receipt_allocations(self, obj: ClientInvoice) -> list[dict[str, Any]]:
        return [
            {
                "id": item.id,
                "receipt": item.receipt_id,
                "receipt_number": item.receipt.receipt_number,
                "receipt_date": item.receipt.received_at,
                "payment_method": item.receipt.payment_method,
                "reference": item.receipt.external_reference or item.receipt.cheque_reference,
                "amount": item.amount,
                "allocated_at": item.allocated_at,
            }
            for item in obj.allocations.all()
        ]


class InvoiceLineWriteSerializer(serializers.Serializer[dict[str, object]]):
    description = serializers.CharField(max_length=255)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit = serializers.CharField(max_length=30, default="SERVICE")
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=2)
    discount_amount = serializers.DecimalField(max_digits=18, decimal_places=2, default=ZERO)
    tax_rate = serializers.DecimalField(max_digits=8, decimal_places=4, default=ZERO)
    revenue_account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())
    cost_center = serializers.PrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(),
        required=False,
        allow_null=True,
    )
    contract_service = serializers.PrimaryKeyRelatedField(
        queryset=ContractService.objects.all(),
        required=False,
        allow_null=True,
    )
    site = serializers.PrimaryKeyRelatedField(
        queryset=SecuritySite.objects.all(),
        required=False,
        allow_null=True,
    )
    billing_rule = serializers.PrimaryKeyRelatedField(
        queryset=BillingRule.objects.all(),
        required=False,
        allow_null=True,
    )


class InvoiceCreateSerializer(serializers.Serializer[dict[str, object]]):
    billing_profile = serializers.PrimaryKeyRelatedField(
        queryset=ClientBillingProfile.objects.all()
    )
    invoice_date = serializers.DateField()
    invoice_type = serializers.ChoiceField(choices=InvoiceType.choices)
    contract = serializers.PrimaryKeyRelatedField(
        queryset=ServiceContract.objects.all(),
        required=False,
        allow_null=True,
    )
    service_period_start = serializers.DateField(required=False, allow_null=True)
    service_period_end = serializers.DateField(required=False, allow_null=True)
    client_po_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    client_reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    lines = InvoiceLineWriteSerializer(many=True, required=False, default=list)


class InvoiceDraftUpdateSerializer(serializers.ModelSerializer[ClientInvoice]):
    class Meta:
        model = ClientInvoice
        fields = (
            "contract",
            "invoice_date",
            "service_period_start",
            "service_period_end",
            "client_po_reference",
            "client_reference",
        )


class InvoiceRevenueAccountSerializer(serializers.ModelSerializer[Account]):
    """Minimal, selection-only projection of Account for Invoice line entry.

    Deliberately excludes hierarchy/administration fields (parent,
    description, is_control_account, sort_order) that belong to chart-of-
    accounts management, not Invoice line authoring.
    """

    class Meta:
        model = Account
        fields = ("id", "company", "code", "name", "account_type")
        read_only_fields = fields


class ReceiptAllocationSerializer(serializers.ModelSerializer[ClientReceiptAllocation]):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)

    class Meta:
        model = ClientReceiptAllocation
        fields = ("id", "invoice", "invoice_number", "amount", "allocated_at")
        read_only_fields = fields


class ReceiptBankAccountSerializer(serializers.ModelSerializer[BankAccount]):
    class Meta:
        model = BankAccount
        fields = ("id", "company", "name", "bank_name", "currency")
        read_only_fields = fields


class ReceiptClientSerializer(serializers.ModelSerializer[ClientBillingProfile]):
    class Meta:
        model = ClientBillingProfile
        fields = ("client", "company", "billing_name", "currency")
        read_only_fields = fields


class ReceiptSerializer(serializers.ModelSerializer[ClientReceipt]):
    allocated_amount = serializers.SerializerMethodField()
    unallocated_amount = serializers.SerializerMethodField()
    client_name = serializers.CharField(source="client.legal_name", read_only=True)
    allocations = ReceiptAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = ClientReceipt
        exclude = ("accounting_journal",)
        read_only_fields = (
            "id",
            "receipt_number",
            "received_by",
            "confirmed_by",
            "confirmed_at",
            "status",
            "created_at",
            "updated_at",
        )

    def get_allocated_amount(self, obj: ClientReceipt) -> Decimal:
        return sum((item.amount for item in obj.allocations.all()), ZERO)

    def get_unallocated_amount(self, obj: ClientReceipt) -> Decimal:
        return obj.amount - self.get_allocated_amount(obj)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        company = attrs.get("company", getattr(self.instance, "company", None))
        client = attrs.get("client", getattr(self.instance, "client", None))
        bank = attrs.get("bank_account", getattr(self.instance, "bank_account", None))
        if client and company and client.company_id != company.id:
            raise serializers.ValidationError({"client": "Client belongs to another company."})
        if bank and company and bank.company_id != company.id:
            raise serializers.ValidationError(
                {"bank_account": "Bank account belongs to another company."}
            )
        if (
            bank
            and attrs.get("currency", getattr(self.instance, "currency", None)) != bank.currency
        ):
            raise serializers.ValidationError(
                {"currency": "Currency differs from the bank account."}
            )
        if self.instance and self.instance.status != "DRAFT":
            raise serializers.ValidationError("Only draft receipts can be edited.")
        return attrs


# Compatibility name for imports outside the Billing API module.
InvoiceSerializer = InvoiceReadSerializer


class CreditNoteLineSerializer(serializers.ModelSerializer[ClientCreditNoteLine]):
    class Meta:
        model = ClientCreditNoteLine
        exclude = ("credit_note",)
        read_only_fields = ("id", "line_number")


class CreditNoteSerializer(serializers.ModelSerializer[ClientCreditNote]):
    lines = CreditNoteLineSerializer(many=True)

    class Meta:
        model = ClientCreditNote
        fields = "__all__"
        read_only_fields = (
            "id",
            "company",
            "client",
            "note_number",
            "note_date",
            "currency",
            "total_amount",
            "status",
            "created_by",
            "approved_by",
            "issued_by",
            "accounting_journal",
            "created_at",
            "updated_at",
        )


class DebitNoteLineSerializer(serializers.ModelSerializer[ClientDebitNoteLine]):
    class Meta:
        model = ClientDebitNoteLine
        exclude = ("debit_note",)
        read_only_fields = ("id", "line_number")


class DebitNoteSerializer(serializers.ModelSerializer[ClientDebitNote]):
    lines = DebitNoteLineSerializer(many=True)

    class Meta:
        model = ClientDebitNote
        fields = "__all__"
        read_only_fields = (
            "id",
            "company",
            "client",
            "note_number",
            "note_date",
            "currency",
            "total_amount",
            "status",
            "created_by",
            "approved_by",
            "issued_by",
            "accounting_journal",
            "created_at",
            "updated_at",
        )


class CollectionActivitySerializer(TenantSafeBillingSerializer):
    class Meta:
        model = ClientCollectionActivity
        fields = (
            "id",
            "created_at",
            "updated_at",
            "company",
            "client",
            "invoice",
            "activity_type",
            "activity_at",
            "notes",
            "promised_amount",
            "promised_date",
            "next_follow_up",
            "actor",
        )
        read_only_fields = ("id", "actor", "created_at", "updated_at")
