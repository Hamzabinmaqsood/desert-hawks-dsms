from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.analytics.models import AnalyticsDataQualityIssue
from dsms.analytics.providers import InvoiceValueProvider
from dsms.audit.models import AuditCategory
from dsms.audit.services import record_audit_event
from dsms.billing.api.security import consistent_queryset as consistent_billing_queryset
from dsms.billing.models import ClientCreditNote, ClientDebitNote, ClientInvoice
from dsms.billing.services import approve_credit_note, approve_debit_note
from dsms.client_portal.models import (
    ClientPortalMembership,
    ClientPortalRole,
    ClientServiceReport,
    ClientServiceRequest,
)
from dsms.client_portal.services import acknowledge_report
from dsms.finance.operations_models import CompanyExpense, ExpenseCategory, RecurringExpenseTemplate
from dsms.finance.tasks import generate_recurring_expense_drafts
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from dsms.leave.models import LeaveType
from dsms.notifications.models import (
    Notification,
    NotificationEvent,
    NotificationRecipient,
    NotificationRecipientRule,
    NotificationRule,
)
from dsms.notifications.services import (
    acknowledge_notification,
    deliver_external,
    list_in_app_notifications,
    mark_notification_read,
    process_notification_event,
    publish_notification_event,
)
from dsms.notifications.tenant_queries import consistent_recipients_for_user
from tests.factories.documents import DocumentTypeFactory, EmployeeDocumentFactory
from tests.factories.finance import accounting_setup
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory
from tests.factories.workforce import EmployeeFactory
from tests.unit.test_billing_core import billing_graph, make_invoice

pytestmark = pytest.mark.django_db


def grant_company(user: User, company, app_label: str, *codenames: str) -> None:  # type: ignore[no-untyped-def]
    role = RoleFactory.create(company=company)
    role.permissions.set(
        Permission.objects.filter(content_type__app_label=app_label, codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def grant_branch(user: User, branch, *codenames: str) -> None:  # type: ignore[no-untyped-def]
    role = RoleFactory.create(company=branch.company)
    role.permissions.set(
        Permission.objects.filter(content_type__app_label="documents", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )


def test_document_split_scope_and_corrupt_graph_fail_closed() -> None:
    branch_a = BranchFactory.create()
    branch_b = BranchFactory.create()
    employee_a = EmployeeFactory.create(company=branch_a.company, branch=branch_a)
    employee_b = EmployeeFactory.create(company=branch_b.company, branch=branch_b)
    sensitive_type = DocumentTypeFactory.create(company=branch_a.company, is_sensitive=True)
    valid = EmployeeDocumentFactory.create(
        company=branch_a.company,
        employee=employee_a,
        document_type=sensitive_type,
        document_number="35202-1234567-1",
        expires_on=timezone.localdate() - timedelta(days=1),
    )
    corrupt = EmployeeDocumentFactory.create(
        company=branch_a.company,
        employee=employee_b,
        document_type=sensitive_type,
        expires_on=timezone.localdate() - timedelta(days=1),
    )
    viewer = UserFactory.create()
    grant_branch(viewer, branch_a, "view_employeedocument", "download_employee_document")
    grant_branch(viewer, branch_b, "view_employeedocument", "view_sensitive_document_data")

    client = APIClient()
    client.force_authenticate(viewer)
    detail = client.get(f"/api/v1/documents/employee-documents/{valid.id}/")
    assert detail.status_code == 200
    assert detail.data["document_number"] is None
    assert client.get(f"/api/v1/documents/employee-documents/{corrupt.id}/").status_code == 404
    download = client.get(
        f"/api/v1/documents/employee-documents/{corrupt.id}/versions/"
        "00000000-0000-0000-0000-000000000001/download/"
    )
    assert download.status_code == 404
    expired = client.get("/api/v1/documents/employee-documents/expired/")
    assert expired.status_code == 200
    assert [row["id"] for row in expired.data["results"]] == [str(valid.id)]

    corrupt_employee = EmployeeFactory.create(company=branch_a.company, branch=branch_b)
    assert (
        client.get(f"/api/v1/documents/employees/{corrupt_employee.id}/documents/").status_code
        == 404
    )
    assert (
        client.get(
            f"/api/v1/documents/employees/{corrupt_employee.id}/compliance-summary/"
        ).status_code
        == 404
    )


def test_document_type_configuration_is_company_scoped_and_global_is_platform_only() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    own = DocumentTypeFactory.create(company=company_a)
    hidden = DocumentTypeFactory.create(company=company_b)
    global_type = DocumentTypeFactory.create(company=None)
    manager = UserFactory.create()
    grant_company(manager, company_a, "documents", "manage_document_types")

    client = APIClient()
    client.force_authenticate(manager)
    listed = client.get("/api/v1/documents/types/")
    assert listed.status_code == 200
    ids = {row["id"] for row in listed.data["results"]}
    assert ids == {str(own.id), str(global_type.id)}
    assert (
        client.patch(
            f"/api/v1/documents/types/{hidden.id}/", {"name": "Probe"}, format="json"
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/documents/types/{global_type.id}/",
            {"name": "Tenant mutation"},
            format="json",
        ).status_code
        == 403
    )


def test_audit_api_hides_mixed_company_branch_and_employee_rows() -> None:
    branch_a = BranchFactory.create()
    branch_b = BranchFactory.create()
    employee_b = EmployeeFactory.create(company=branch_b.company, branch=branch_b)
    valid = record_audit_event(
        action="SAAS1D_VALID",
        category=AuditCategory.SYSTEM,
        summary="Valid tenant graph.",
        company=branch_a.company,
        region=branch_a.region,
        branch=branch_a,
    )
    record_audit_event(
        action="SAAS1D_CORRUPT_BRANCH",
        category=AuditCategory.SYSTEM,
        summary="Mixed branch graph.",
        company=branch_a.company,
        branch=branch_b,
    )
    record_audit_event(
        action="SAAS1D_CORRUPT_EMPLOYEE",
        category=AuditCategory.SYSTEM,
        summary="Mixed employee graph.",
        company=branch_a.company,
        actor_employee=employee_b,
    )
    auditor = UserFactory.create()
    grant_company(auditor, branch_a.company, "audit", "view_auditevent")
    grant_company(auditor, branch_b.company, "audit", "view_auditevent")

    client = APIClient()
    client.force_authenticate(auditor)
    response = client.get("/api/v1/audit/events/")
    assert response.status_code == 200
    assert {row["id"] for row in response.data["results"]} == {str(valid.id)}


def test_data_quality_api_hides_corrupt_cross_company_relation() -> None:
    branch_a = BranchFactory.create()
    branch_b = BranchFactory.create()
    now = timezone.now()
    valid = AnalyticsDataQualityIssue.objects.create(
        company=branch_a.company,
        branch=branch_a,
        source_app="tests",
        issue_code="VALID",
        severity="HIGH",
        description="Valid graph",
        detected_at=now,
    )
    AnalyticsDataQualityIssue.objects.create(
        company=branch_a.company,
        branch=branch_b,
        source_app="tests",
        issue_code="CORRUPT",
        severity="HIGH",
        description="Mixed graph",
        detected_at=now,
    )
    viewer = UserFactory.create()
    grant_company(viewer, branch_a.company, "analytics", "view_data_quality")
    grant_company(viewer, branch_b.company, "analytics", "view_data_quality")

    client = APIClient()
    client.force_authenticate(viewer)
    response = client.get("/api/v1/analytics/data-quality/")
    assert response.status_code == 200
    assert {row["id"] for row in response.data["results"]} == {str(valid.id)}


def test_billing_selector_and_analytics_provider_exclude_corrupt_invoice() -> None:
    graph_a = billing_graph()
    graph_b = billing_graph()
    valid = make_invoice(graph_a)
    valid.status = "ISSUED"
    valid.save(update_fields=["status"])
    corrupt = make_invoice(graph_a)
    ClientInvoice.objects.filter(pk=corrupt.pk).update(client=graph_b["client"], status="ISSUED")

    visible = consistent_billing_queryset(ClientInvoice.objects.filter(company=graph_a["company"]))
    assert set(visible.values_list("id", flat=True)) == {valid.id}
    metric = type("Metric", (), {"currency": ""})()
    result = InvoiceValueProvider().calculate(
        metric_definition=metric,
        period_start=date(2026, 8, 1),
        period_end=date(2026, 8, 31),
        company=graph_a["company"],
    )
    assert result.value == valid.total_amount
    assert result.source_count == 1


def test_billing_adjustment_apis_hide_corrupt_cross_tenant_graphs() -> None:
    graph_a = billing_graph()
    graph_b = billing_graph()
    invoice = make_invoice(graph_a)
    valid_credit = ClientCreditNote.objects.create(
        company=graph_a["company"],
        client=graph_a["client"],
        invoice=invoice,
        note_number="CN-VALID",
        note_date=timezone.localdate(),
        reason="Valid",
        created_by=graph_a["maker"],
    )
    corrupt_credit = ClientCreditNote.objects.create(
        company=graph_a["company"],
        client=graph_b["client"],
        invoice=invoice,
        note_number="CN-CORRUPT",
        note_date=timezone.localdate(),
        reason="Mixed tenant graph",
        created_by=graph_a["maker"],
    )
    valid_debit = ClientDebitNote.objects.create(
        company=graph_a["company"],
        client=graph_a["client"],
        invoice=invoice,
        note_number="DN-VALID",
        note_date=timezone.localdate(),
        reason="Valid",
        created_by=graph_a["maker"],
    )
    corrupt_debit = ClientDebitNote.objects.create(
        company=graph_a["company"],
        client=graph_b["client"],
        invoice=invoice,
        note_number="DN-CORRUPT",
        note_date=timezone.localdate(),
        reason="Mixed tenant graph",
        created_by=graph_a["maker"],
    )
    viewer = UserFactory.create()
    for company in (graph_a["company"], graph_b["company"]):
        grant_company(
            viewer,
            company,
            "billing",
            "view_clientcreditnote",
            "view_clientdebitnote",
        )

    client = APIClient()
    client.force_authenticate(viewer)
    credits = client.get("/api/v1/billing/credit-notes/")
    debits = client.get("/api/v1/billing/debit-notes/")
    assert credits.status_code == debits.status_code == 200
    assert {row["id"] for row in credits.data["results"]} == {str(valid_credit.id)}
    assert {row["id"] for row in debits.data["results"]} == {str(valid_debit.id)}
    with pytest.raises(ClientCreditNote.DoesNotExist):
        approve_credit_note(note=corrupt_credit, actor=graph_a["checker"])
    with pytest.raises(ClientDebitNote.DoesNotExist):
        approve_debit_note(note=corrupt_debit, actor=graph_a["checker"])


def test_client_portal_hides_inconsistent_resources_and_inactive_tenants() -> None:
    graph_a = billing_graph()
    graph_b = billing_graph()
    user = graph_a["maker"]
    role = ClientPortalRole.objects.create(code="SAAS1D_PORTAL", name="SaaS-1D portal")
    role.permissions.add(
        *Permission.objects.filter(
            content_type__app_label="client_portal",
            codename__in=[
                "view_service_reports",
                "acknowledge_service_report",
                "view_service_request",
            ],
        )
    )
    member = ClientPortalMembership.objects.create(
        user=user,
        client=graph_a["client"],
        role=role,
        status="ACTIVE",
    )
    other_member = ClientPortalMembership.objects.create(
        user=graph_b["maker"],
        client=graph_b["client"],
        role=role,
        status="ACTIVE",
    )
    common_report = {
        "report_type": "MONTHLY",
        "period_start": date(2026, 8, 1),
        "period_end": date(2026, 8, 31),
        "status": "PUBLISHED",
        "generated_by": user,
        "generated_at": timezone.now(),
        "published_at": timezone.now(),
    }
    valid_report = ClientServiceReport.objects.create(
        company=graph_a["company"],
        client=graph_a["client"],
        report_number="SAAS1D-VALID",
        title="Valid report",
        **common_report,
    )
    corrupt_report = ClientServiceReport.objects.create(
        company=graph_b["company"],
        client=graph_a["client"],
        report_number="SAAS1D-CORRUPT",
        title="Mixed tenant report",
        **common_report,
    )
    valid_request = ClientServiceRequest.objects.create(
        request_number="CSR-SAAS1D-VALID",
        client=graph_a["client"],
        created_by_membership=member,
        request_type="GENERAL",
        title="Valid request",
        description="Valid tenant graph",
    )
    ClientServiceRequest.objects.create(
        request_number="CSR-SAAS1D-CORRUPT",
        client=graph_a["client"],
        created_by_membership=other_member,
        request_type="GENERAL",
        title="Mixed tenant request",
        description="Must remain hidden",
    )

    client = APIClient()
    client.force_authenticate(user)
    base = f"/api/v1/client-portal/{graph_a['client'].id}"
    reports = client.get(f"{base}/reports/")
    requests = client.get(f"{base}/service-requests/")
    assert reports.status_code == requests.status_code == 200
    assert {row["id"] for row in reports.data} == {str(valid_report.id)}
    assert {row["id"] for row in requests.data} == {str(valid_request.id)}
    assert client.post(f"{base}/reports/{corrupt_report.id}/acknowledge/").status_code == 404
    with pytest.raises(ValueError, match="unavailable"):
        acknowledge_report(membership=member, report=corrupt_report)

    graph_a["company"].is_active = False
    graph_a["company"].save(update_fields=["is_active"])
    assert client.get("/api/v1/client-portal/me/memberships/").data == []
    assert client.get(f"{base}/reports/").status_code == 404


def test_notification_idempotency_recipients_and_inactive_company_fail_closed() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    user_a = UserFactory.create()
    user_b = UserFactory.create()
    grant_company(user_a, company_a, "audit", "view_auditevent")
    grant_company(user_b, company_b, "audit", "view_auditevent")
    rule = NotificationRule.objects.create(
        company=company_a, event_type="SAAS1D", code="SAAS1D", name="SaaS-1D"
    )
    NotificationRecipientRule.objects.create(
        notification_rule=rule, audience_type="USER", explicit_user=user_a
    )
    NotificationRecipientRule.objects.create(
        notification_rule=rule, audience_type="USER", explicit_user=user_b
    )
    event = publish_notification_event(
        event_key="saas1d:tenant-bound",
        event_type="SAAS1D",
        source_app="tests",
        source_model="Example",
        company=company_a,
    )
    notification = process_notification_event(event_id=event.id)[0]
    assert set(notification.recipients.values_list("user_id", flat=True)) == {user_a.id}
    with pytest.raises(ValueError, match="another operation"):
        publish_notification_event(
            event_key="saas1d:tenant-bound",
            event_type="SAAS1D",
            source_app="tests",
            source_model="Example",
            company=company_b,
        )

    company_b.is_active = False
    company_b.save(update_fields=["is_active"])
    inactive = publish_notification_event(
        event_key="saas1d:inactive",
        event_type="SAAS1D",
        source_app="tests",
        source_model="Example",
        company=company_b,
    )
    assert process_notification_event(event_id=inactive.id) == []
    inactive.refresh_from_db()
    assert inactive.status == "IGNORED"
    assert inactive.last_error_code == "INACTIVE_COMPANY"


def test_notification_projection_hides_corrupt_recipient_graph() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    user = UserFactory.create()
    grant_company(user, company_a, "audit", "view_auditevent")
    employee_b = EmployeeFactory.create(company=company_b)
    event_b = NotificationEvent.objects.create(
        event_key="saas1d:corrupt-projection",
        event_type="SAAS1D",
        source_app="tests",
        source_model="Example",
        company=company_b,
        occurred_at=timezone.now(),
    )
    notification = Notification.objects.create(
        event=event_b,
        company=company_a,
        notification_type="SAAS1D",
        priority="NORMAL",
        title="Hidden",
        body="Cross-tenant body",
    )
    recipient = NotificationRecipient.objects.create(
        notification=notification, user=user, employee=employee_b
    )
    assert not consistent_recipients_for_user(
        NotificationRecipient.objects.filter(pk=recipient.pk), user=user
    ).exists()
    assert not list_in_app_notifications(user).filter(pk=recipient.pk).exists()
    with pytest.raises(NotificationRecipient.DoesNotExist):
        mark_notification_read(recipient=recipient, actor=user)
    with pytest.raises(NotificationRecipient.DoesNotExist):
        acknowledge_notification(recipient=recipient, actor=user)
    with pytest.raises(NotificationRecipient.DoesNotExist):
        deliver_external(recipient=recipient, channel="EMAIL", destination="safe@example.com")


def test_recurring_expense_task_skips_corrupt_and_inactive_templates() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    actor = UserFactory.create()
    _year_a, _period_a, accounts_a = accounting_setup(company_a)
    _year_b, _period_b, accounts_b = accounting_setup(company_b)
    valid_category = ExpenseCategory.objects.create(
        company=company_a,
        code="VALID",
        name="Valid",
        expense_account=accounts_a["expense"],
    )
    foreign_category = ExpenseCategory.objects.create(
        company=company_b,
        code="FOREIGN",
        name="Foreign",
        expense_account=accounts_b["expense"],
    )
    RecurringExpenseTemplate.objects.create(
        company=company_a,
        category=valid_category,
        description="Valid recurring expense",
        amount=Decimal("100"),
        next_due_date=timezone.localdate(),
        created_by=actor,
    )
    RecurringExpenseTemplate.objects.create(
        company=company_a,
        category=foreign_category,
        description="Corrupt recurring expense",
        amount=Decimal("200"),
        next_due_date=timezone.localdate(),
        created_by=actor,
    )
    company_b.is_active = False
    company_b.save(update_fields=["is_active"])
    RecurringExpenseTemplate.objects.create(
        company=company_b,
        category=foreign_category,
        description="Inactive tenant expense",
        amount=Decimal("300"),
        next_due_date=timezone.localdate(),
        created_by=actor,
    )

    assert generate_recurring_expense_drafts() == 1
    assert list(CompanyExpense.objects.values_list("company_id", "amount")) == [
        (company_a.id, Decimal("100.00"))
    ]


def test_leave_type_list_is_employee_company_scoped_and_requires_active_employee() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    user = UserFactory.create()
    EmployeeFactory.create(company=company_a, user=user, employment_status="ACTIVE")
    global_type = LeaveType.objects.create(
        company=None,
        code="GLOBAL",
        name="Global",
        unit="DAYS",
        pay_treatment="PAID",
    )
    own = LeaveType.objects.create(
        company=company_a,
        code="OWN",
        name="Own",
        unit="DAYS",
        pay_treatment="PAID",
    )
    LeaveType.objects.create(
        company=company_b,
        code="FOREIGN",
        name="Foreign",
        unit="DAYS",
        pay_treatment="PAID",
    )

    client = APIClient()
    client.force_authenticate(user)
    response = client.get("/api/v1/leave/types/")
    assert response.status_code == 200
    assert {row["id"] for row in response.data["results"]} == {
        str(global_type.id),
        str(own.id),
    }

    company_a.is_active = False
    company_a.save(update_fields=["is_active"])
    assert client.get("/api/v1/leave/types/").status_code == 404
