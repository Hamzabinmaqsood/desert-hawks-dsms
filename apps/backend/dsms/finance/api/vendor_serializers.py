from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from ..models import Account
from ..procurement_models import Vendor, validate_vendor_payable_account


def vendor_account_error(company: Any, account: Account) -> None:
    try:
        validate_vendor_payable_account(company=company, account=account)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.message_dict) from exc


class VendorSerializer(serializers.ModelSerializer[Vendor]):
    payable_account_code = serializers.CharField(source="payable_account.code", read_only=True)
    payable_account_name = serializers.CharField(source="payable_account.name", read_only=True)

    class Meta:
        model = Vendor
        fields = (
            "id",
            "code",
            "name",
            "tax_number",
            "email",
            "phone",
            "payment_terms_days",
            "payable_account",
            "payable_account_code",
            "payable_account_name",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        account = attrs.get("payable_account") or getattr(self.instance, "payable_account", None)
        if not isinstance(account, Account):
            raise serializers.ValidationError({"payable_account": ["This field is required."]})
        company = getattr(self.instance, "company", None) or account.company
        vendor_account_error(company, account)
        code = attrs.get("code", getattr(self.instance, "code", ""))
        duplicate = Vendor.objects.filter(company=company, code=code)
        if self.instance:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise serializers.ValidationError({"code": ["A vendor with this code already exists."]})
        return attrs

    def create(self, validated_data: dict[str, Any]) -> Vendor:
        account = validated_data["payable_account"]
        return Vendor.objects.create(company=account.company, **validated_data)


class VendorPayableAccountSerializer(serializers.ModelSerializer[Account]):
    class Meta:
        model = Account
        fields = ("id", "code", "name")
        read_only_fields = fields
