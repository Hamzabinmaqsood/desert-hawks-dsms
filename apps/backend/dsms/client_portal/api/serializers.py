# mypy: disable-error-code="type-arg,no-untyped-def,var-annotated"
from rest_framework import serializers

from dsms.billing.models import ClientInvoice, ClientReceipt
from dsms.client_portal import models


class MembershipSerializer(serializers.ModelSerializer[models.ClientPortalMembership]):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = models.ClientPortalMembership
        fields = [
            "id",
            "client",
            "role",
            "status",
            "access_mode",
            "starts_at",
            "ends_at",
            "permissions",
        ]

    def get_permissions(self, obj: models.ClientPortalMembership) -> list[str]:
        return list(obj.role.permissions.values_list("codename", flat=True))


class SiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = __import__("dsms.contracts.models", fromlist=["SecuritySite"]).SecuritySite
        fields = ["id", "site_code", "name", "status", "address_line_1", "city_name"]


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = __import__("dsms.contracts.models", fromlist=["ServiceContract"]).ServiceContract
        fields = ["id", "contract_number", "title", "status", "start_date", "end_date"]


class ClientIncidentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    incident_number = serializers.CharField()
    site = serializers.PrimaryKeyRelatedField(read_only=True)
    severity = serializers.CharField()
    status = serializers.CharField()
    reported_at = serializers.DateTimeField()
    client_summary = serializers.CharField(source="client_visibility.client_summary")
    client_resolution_summary = serializers.CharField(
        source="client_visibility.client_resolution_summary"
    )


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ClientServiceReport
        fields = [
            "id",
            "report_number",
            "report_type",
            "period_start",
            "period_end",
            "title",
            "published_at",
            "executive_summary",
            "revision_number",
            "supersedes",
        ]


class ServiceRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.ClientServiceRequest
        fields = [
            "id",
            "request_number",
            "contract",
            "site",
            "request_type",
            "priority",
            "title",
            "description",
            "status",
            "acknowledged_at",
            "resolved_at",
            "resolution_summary",
            "created_at",
        ]
        read_only_fields = [
            "request_number",
            "status",
            "acknowledged_at",
            "resolved_at",
            "resolution_summary",
        ]


class PortalInvoiceSerializer(serializers.ModelSerializer[ClientInvoice]):
    class Meta:
        model = ClientInvoice
        fields = [
            "id",
            "invoice_number",
            "contract",
            "invoice_date",
            "due_date",
            "currency",
            "subtotal",
            "discount_total",
            "tax_total",
            "total_amount",
            "amount_paid",
            "balance_due",
            "status",
            "issued_at",
        ]


class PortalReceiptSerializer(serializers.ModelSerializer[ClientReceipt]):
    class Meta:
        model = ClientReceipt
        fields = [
            "id",
            "receipt_number",
            "received_at",
            "value_date",
            "currency",
            "amount",
            "payment_method",
            "status",
            "external_reference",
        ]
