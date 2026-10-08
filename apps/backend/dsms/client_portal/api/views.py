# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,assignment"
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.billing.api.security import consistent_queryset as consistent_billing_queryset
from dsms.billing.models import ClientInvoice, ClientReceipt
from dsms.billing.selectors import get_accounts_receivable_ageing, get_client_account_balance
from dsms.client_portal.access import resolve_membership, restrict_sites
from dsms.client_portal.models import (
    ClientPortalMembership,
    ClientServiceReport,
    ClientServiceRequest,
)
from dsms.client_portal.services import acknowledge_report, create_service_request
from dsms.client_portal.tenant_queries import (
    active_memberships,
    consistent_reports,
    consistent_service_requests,
)
from dsms.contracts.api.security import consistent_queryset as consistent_contract_queryset
from dsms.contracts.models import SecuritySite, ServiceContract
from dsms.incidents.models import Incident
from dsms.incidents.tenant_queries import consistent_incidents

from .serializers import (
    ClientIncidentSerializer,
    ContractSerializer,
    MembershipSerializer,
    PortalInvoiceSerializer,
    PortalReceiptSerializer,
    ReportSerializer,
    ServiceRequestSerializer,
    SiteSerializer,
)


class MembershipsView(APIView):
    serializer_class = MembershipSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = (
            active_memberships(
                ClientPortalMembership.objects.filter(user=request.user, status="ACTIVE")
            )
            .select_related("client", "role")
            .prefetch_related("role__permissions")
        )
        return Response(MembershipSerializer(items, many=True).data)


class PortalResponseSerializer(serializers.Serializer):
    """Schema marker for portal endpoints with resource-specific responses."""


class PortalBase(APIView):
    serializer_class = PortalResponseSerializer
    permission_classes = [IsAuthenticated]
    permission_codename = None

    def membership(self, request, client_uuid):
        return resolve_membership(
            user=request.user, client_id=client_uuid, permission=self.permission_codename
        )


class MeView(PortalBase):
    def get(self, request, client_uuid):
        return Response(MembershipSerializer(self.membership(request, client_uuid)).data)


class SitesView(PortalBase):
    permission_codename = "view_sites"

    def get(self, request, client_uuid):
        member = self.membership(request, client_uuid)
        return Response(
            SiteSerializer(restrict_sites(SecuritySite.objects.all(), member), many=True).data
        )


class ContractsView(PortalBase):
    permission_codename = "view_contracts"

    def get(self, request, client_uuid):
        member = self.membership(request, client_uuid)
        qs = consistent_contract_queryset(ServiceContract.objects.filter(client=member.client))
        restrictions = member.contract_access.filter(is_active=True)
        if restrictions.exists():
            qs = qs.filter(id__in=restrictions.values("contract_id"))
        return Response(ContractSerializer(qs, many=True).data)


class IncidentsView(PortalBase):
    permission_codename = "view_incident_summary"

    def get(self, request, client_uuid):
        member = self.membership(request, client_uuid)
        qs = consistent_incidents(
            Incident.objects.filter(
                client=member.client,
                client_visibility__visibility_status__in=[
                    "CLIENT_SUMMARY",
                    "CLIENT_DETAILED",
                ],
            ).select_related("client_visibility")
        )
        if member.access_mode == "SELECTED_SITES":
            qs = qs.filter(site_id__in=member.site_access.filter(is_active=True).values("site_id"))
        return Response(ClientIncidentSerializer(qs, many=True).data)


class ReportsView(PortalBase):
    permission_codename = "view_service_reports"

    def get(self, request, client_uuid):
        member = self.membership(request, client_uuid)
        return Response(
            ReportSerializer(
                consistent_reports(
                    ClientServiceReport.objects.filter(client=member.client, status="PUBLISHED")
                ),
                many=True,
            ).data
        )


class ReportAcknowledgeView(PortalBase):
    permission_codename = "acknowledge_service_report"

    def post(self, request, client_uuid, report_uuid):
        member = self.membership(request, client_uuid)
        report = get_object_or_404(
            consistent_reports(ClientServiceReport.objects.all()),
            id=report_uuid,
            client=member.client,
            status="PUBLISHED",
        )
        ack = acknowledge_report(
            membership=member, report=report, comments=request.data.get("comments", "")
        )
        return Response({"id": ack.id, "acknowledged_at": ack.acknowledged_at})


class ServiceRequestsView(PortalBase):
    permission_codename = "view_service_request"

    def get(self, request, client_uuid):
        member = self.membership(
            request,
            client_uuid,
        )
        return Response(
            ServiceRequestSerializer(
                consistent_service_requests(
                    ClientServiceRequest.objects.filter(client=member.client)
                ),
                many=True,
            ).data
        )

    def post(self, request, client_uuid):
        member = resolve_membership(
            user=request.user, client_id=client_uuid, permission="create_service_request"
        )
        serializer = ServiceRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        item = create_service_request(
            membership=member,
            request_type=data["request_type"],
            priority=data.get("priority", "NORMAL"),
            title=data["title"],
            description=data["description"],
            site=data.get("site"),
            contract=data.get("contract"),
        )
        return Response(ServiceRequestSerializer(item).data, status=201)


class ClientInvoicesView(PortalBase):
    permission_codename = "view_client_invoices"

    @extend_schema(operation_id="client_portal_invoice_list")
    def get(self, request, client_uuid):
        member = self.membership(request, client_uuid)
        queryset = consistent_billing_queryset(
            ClientInvoice.objects.filter(
                client=member.client,
                status__in=["ISSUED", "PARTIALLY_PAID", "PAID", "DISPUTED"],
            ).select_related("contract")
        )
        return Response(PortalInvoiceSerializer(queryset, many=True).data)


class ClientInvoiceDetailView(PortalBase):
    permission_codename = "view_client_invoices"

    @extend_schema(operation_id="client_portal_invoice_detail")
    def get(self, request, client_uuid, invoice_uuid):
        member = self.membership(request, client_uuid)
        invoice = get_object_or_404(
            consistent_billing_queryset(
                ClientInvoice.objects.filter(
                    client=member.client,
                    status__in=["ISSUED", "PARTIALLY_PAID", "PAID", "DISPUTED"],
                ).select_related("contract")
            ),
            pk=invoice_uuid,
        )
        return Response(PortalInvoiceSerializer(invoice).data)


class ClientInvoiceDownloadView(PortalBase):
    permission_codename = "download_client_invoice"

    def get(self, request, client_uuid, invoice_uuid):
        member = self.membership(request, client_uuid)
        invoice = get_object_or_404(
            consistent_billing_queryset(
                ClientInvoice.objects.filter(
                    client=member.client,
                    status__in=["ISSUED", "PARTIALLY_PAID", "PAID", "DISPUTED"],
                )
            ),
            pk=invoice_uuid,
        )
        document = consistent_billing_queryset(
            invoice.documents.order_by("-revision_number")
        ).first()
        if not document:
            raise Http404
        record_audit_event(
            action="CLIENT_INVOICE_PORTAL_DOWNLOAD",
            category=AuditCategory.BILLING,
            severity=AuditSeverity.WARNING,
            summary="Client invoice downloaded through portal.",
            actor_user=request.user,
            company=invoice.company,
            source_object=invoice,
            object_reference=invoice.invoice_number,
        )
        return FileResponse(
            document.file.open("rb"),
            content_type="application/pdf",
            as_attachment=True,
            filename=f"invoice-{invoice.invoice_number}.pdf",
        )


class ClientReceiptsView(PortalBase):
    permission_codename = "view_client_receipts"

    def get(self, request, client_uuid):
        member = self.membership(request, client_uuid)
        queryset = consistent_billing_queryset(
            ClientReceipt.objects.filter(client=member.client)
        ).exclude(status__in=["DRAFT", "CANCELLED"])
        return Response(PortalReceiptSerializer(queryset, many=True).data)


class ClientStatementView(PortalBase):
    permission_codename = "view_client_statement"

    def get(self, request, client_uuid):
        member = self.membership(request, client_uuid)
        transactions = consistent_billing_queryset(
            member.client.ar_transactions.order_by("effective_at", "id")
        )
        running = 0
        rows = []
        for item in transactions:
            running += item.debit - item.credit
            rows.append(
                {
                    "date": item.effective_at,
                    "type": item.transaction_type,
                    "reference": item.source_reference,
                    "debit": item.debit,
                    "credit": item.credit,
                    "balance": running,
                }
            )
        return Response(
            {
                "opening_balance": 0,
                "transactions": rows,
                "closing_balance": running,
                "ageing": get_accounts_receivable_ageing(
                    company=member.client.company, client=member.client
                ),
                "account": get_client_account_balance(member.client),
            }
        )
