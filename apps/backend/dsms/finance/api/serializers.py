from decimal import Decimal
from typing import Any

from rest_framework import serializers

from dsms.organization.models import Company

from ..models import Account, AccountingPeriod, CostCenter, FiscalYear, JournalEntry


class AccountSerializer(serializers.ModelSerializer[Account]):
    class Meta:
        model = Account
        fields = [
            "id",
            "company",
            "code",
            "name",
            "account_type",
            "parent",
            "description",
            "allow_posting",
            "is_control_account",
            "is_active",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class FiscalYearSerializer(serializers.ModelSerializer[FiscalYear]):
    class Meta:
        model = FiscalYear
        fields = [
            "id",
            "company",
            "name",
            "start_date",
            "end_date",
            "is_active",
            "is_closed",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "is_closed", "created_at", "updated_at"]


class PeriodSerializer(serializers.ModelSerializer[AccountingPeriod]):
    class Meta:
        model = AccountingPeriod
        fields = [
            "id",
            "fiscal_year",
            "company",
            "name",
            "start_date",
            "end_date",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "company", "status", "created_at", "updated_at"]


class CostCenterSerializer(serializers.ModelSerializer[CostCenter]):
    class Meta:
        model = CostCenter
        fields = [
            "id",
            "company",
            "code",
            "name",
            "branch",
            "department",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class JournalLineWriteSerializer(serializers.Serializer[Any]):
    account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.all())
    cost_center = serializers.PrimaryKeyRelatedField(
        queryset=CostCenter.objects.all(), required=False, allow_null=True
    )
    description = serializers.CharField(required=False, allow_blank=True)
    debit = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, default=Decimal("0.00")
    )
    credit = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, default=Decimal("0.00")
    )


class JournalWriteSerializer(serializers.Serializer[Any]):
    company = serializers.PrimaryKeyRelatedField(queryset=Company.objects.all())
    fiscal_year = serializers.PrimaryKeyRelatedField(queryset=FiscalYear.objects.all())
    accounting_period = serializers.PrimaryKeyRelatedField(queryset=AccountingPeriod.objects.all())
    entry_date = serializers.DateField()
    reference = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField()
    lines = JournalLineWriteSerializer(many=True)


class JournalReadSerializer(serializers.ModelSerializer[JournalEntry]):
    lines = serializers.SerializerMethodField()
    total_debit = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "company",
            "fiscal_year",
            "accounting_period",
            "journal_number",
            "entry_date",
            "reference",
            "description",
            "source_type",
            "status",
            "created_by",
            "submitted_by",
            "submitted_at",
            "approved_by",
            "approved_at",
            "posted_by",
            "posted_at",
            "reversed_by_entry",
            "total_debit",
            "total_credit",
            "lines",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_lines(self, obj: JournalEntry) -> list[dict[str, Any]]:
        return [
            {
                "id": line.id,
                "account": line.account_id,
                "account_code": line.account.code,
                "cost_center": line.cost_center_id,
                "description": line.description,
                "debit": line.debit,
                "credit": line.credit,
            }
            for line in obj.lines.all()
        ]


class ReasonSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField()


class ReversalSerializer(ReasonSerializer):
    reversal_date = serializers.DateField()
