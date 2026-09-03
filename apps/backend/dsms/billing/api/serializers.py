from decimal import Decimal
from typing import Any

from rest_framework import serializers

from dsms.contracts.models import ContractService, SecuritySite, ServiceContract
from dsms.finance.models import Account, CostCenter

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
    TaxCode,
)

ZERO = Decimal("0.00")


class BillingProfileSerializer(serializers.ModelSerializer[ClientBillingProfile]):
    class Meta:
        model = ClientBillingProfile
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class BillingScheduleSerializer(serializers.ModelSerializer[BillingSchedule]):
    class Meta:
        model = BillingSchedule
        fields = "__all__"
        read_only_fields = ("id", "created_by", "created_at", "updated_at")


class BillingRuleSerializer(serializers.ModelSerializer[BillingRule]):
    class Meta:
        model = BillingRule
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")


class TaxCodeSerializer(serializers.ModelSerializer[TaxCode]):
    class Meta:
        model = TaxCode
        fields = "__all__"
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

    class Meta:
        model = ClientInvoice
        exclude = ("accounting_journal",)
        read_only_fields = tuple(
            field.name for field in ClientInvoice._meta.fields if field.name != "accounting_journal"
        )

    def get_pdf_available(self, obj: ClientInvoice) -> bool:
        return obj.documents.exists()


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


class ReceiptSerializer(serializers.ModelSerializer[ClientReceipt]):
    allocated_amount = serializers.SerializerMethodField()

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


class CollectionActivitySerializer(serializers.ModelSerializer[ClientCollectionActivity]):
    class Meta:
        model = ClientCollectionActivity
        fields = "__all__"
        read_only_fields = ("id", "actor", "created_at", "updated_at")
