from decimal import Decimal

from rest_framework import serializers

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
        fields = "__all__"


class InvoiceSerializer(serializers.ModelSerializer[ClientInvoice]):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = ClientInvoice
        fields = "__all__"


class ReceiptSerializer(serializers.ModelSerializer[ClientReceipt]):
    allocated_amount = serializers.SerializerMethodField()

    class Meta:
        model = ClientReceipt
        fields = "__all__"
        read_only_fields = (
            "id",
            "receipt_number",
            "received_by",
            "confirmed_by",
            "confirmed_at",
            "accounting_journal",
            "status",
            "created_at",
            "updated_at",
        )

    def get_allocated_amount(self, obj: ClientReceipt) -> Decimal:
        return sum((item.amount for item in obj.allocations.all()), ZERO)


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
