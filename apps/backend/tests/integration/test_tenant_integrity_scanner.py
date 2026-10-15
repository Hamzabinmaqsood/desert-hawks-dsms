from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from dsms.billing.models import (
    ClientCreditNote,
    ClientInvoice,
    ClientReceipt,
    ClientReceiptAllocation,
)
from dsms.common.integrity import run_integrity_scan
from dsms.contracts.models import (
    Client,
    ClientIndustry,
    SecurityPost,
    SecuritySite,
    ServiceContract,
)
from dsms.deployment.models import EmployeeDeployment
from dsms.documents.models import EmployeeDocument
from dsms.finance.enums import AccountType
from dsms.finance.models import Account
from dsms.finance.payment_models import PaymentAccountingProfile
from dsms.finance.procurement_models import PaymentVoucher, Vendor, VendorBill
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import UserRoleAssignment
from dsms.organization.models import Company
from dsms.subscriptions.models import PlanModuleDefault, SubscriptionModuleSnapshot
from tests.factories.documents import DocumentTypeFactory, EmployeeDocumentFactory
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory
from tests.factories.subscriptions import SubscriptionFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def test_entitlement_integrity_check_reports_unknown_code_registry_ids() -> None:
    subscription = SubscriptionFactory.create()
    PlanModuleDefault.objects.create(plan=subscription.plan, module_id="retired_module")
    SubscriptionModuleSnapshot.objects.create(
        subscription=subscription,
        module_id="historical_unknown",
        source_plan_entitlement_revision=0,
    )

    result = run_integrity_scan(check_ids=["subscriptions.entitlement_configuration"])
    scoped = run_integrity_scan(
        check_ids=["subscriptions.entitlement_configuration"],
        company_id=subscription.company_id,
    )

    assert result.summary.total_findings == 2
    assert {finding.metadata["module_id"] for finding in result.findings} == {
        "historical_unknown",
        "retired_module",
    }
    assert scoped.summary.total_findings == 1
    assert scoped.findings[0].owning_company_id == str(subscription.company_id)


def account(company: Company, code: str, account_type: str = AccountType.ASSET) -> Account:
    return Account.objects.create(
        company=company,
        code=code,
        name=f"Account {code}",
        account_type=account_type,
        allow_posting=True,
    )


def client(company: Company, suffix: str) -> Client:
    industry = ClientIndustry.objects.create(
        company=company, code=f"IND-{suffix}", name=f"Industry {suffix}"
    )
    return Client.objects.create(
        company=company,
        client_code=f"CLIENT-{suffix}",
        legal_name=f"Client {suffix}",
        industry=industry,
    )


def invoice(company: Company, owner: Client, suffix: str, actor) -> ClientInvoice:  # type: ignore[no-untyped-def]
    today = date(2026, 10, 12)
    return ClientInvoice.objects.create(
        company=company,
        client=owner,
        invoice_number=f"INV-{suffix}",
        invoice_type="STANDARD",
        invoice_date=today,
        due_date=today + timedelta(days=30),
        generated_by=actor,
        billing_name_snapshot=f"Client {suffix}",
        billing_address_snapshot="Safe test address",
        payment_terms_snapshot=30,
    )


def payment_profile(company: Company, suffix: str) -> PaymentAccountingProfile:
    return PaymentAccountingProfile.objects.create(
        company=company,
        payroll_payable_account=account(company, f"{suffix}-2010", AccountType.LIABILITY),
        vendor_payable_account=account(company, f"{suffix}-2020", AccountType.LIABILITY),
        gateway_clearing_account=account(company, f"{suffix}-2030", AccountType.LIABILITY),
        bank_account=account(company, f"{suffix}-1010"),
        provider_fee_account=account(company, f"{suffix}-5010", AccountType.EXPENSE),
    )


def deployment_graph(company: Company, suffix: str) -> dict[str, Any]:
    branch = BranchFactory.create(company=company, region__company=company)
    actor = UserFactory.create()
    employee = EmployeeFactory.create(company=company, branch=branch)
    owner = client(company, f"DEP-{suffix}")
    contract = ServiceContract.objects.create(
        company=company,
        client=owner,
        contract_number=f"CTR-{suffix}",
        contract_type="FIXED_TERM",
        title="Guarding",
        start_date=date(2026, 1, 1),
        created_by=actor,
    )
    site = SecuritySite.objects.create(
        company=company,
        client=owner,
        contract=contract,
        site_code=f"SITE-{suffix}",
        name=f"Site {suffix}",
        managing_branch=branch,
        address_line_1="Safe test address",
        city_name="Islamabad",
        risk_level="LOW",
    )
    post = SecurityPost.objects.create(
        company=company,
        client=owner,
        site=site,
        post_code=f"POST-{suffix}",
        name="Main Gate",
    )
    deployment = EmployeeDeployment.objects.create(
        company=company,
        employee=employee,
        client=owner,
        contract=contract,
        site=site,
        primary_post=post,
        managing_branch=branch,
        deployment_type="PERMANENT",
        effective_from=date(2026, 1, 1),
        created_by=actor,
    )
    return {"branch": branch, "employee": employee, "deployment": deployment}


def create_corrupt_graph() -> dict[str, Any]:
    company_a = CompanyFactory.create(code="SCAN-A")
    company_b = CompanyFactory.create(code="SCAN-B", is_active=False)
    actor = UserFactory.create()
    client_a = client(company_a, "A")
    client_b = client(company_b, "B")
    invoice_a = invoice(company_a, client_a, "A", actor)
    invoice_b = invoice(company_b, client_b, "B", actor)

    ClientInvoice.objects.filter(pk=invoice_a.pk).update(client=client_b)

    receipt_a = ClientReceipt.objects.create(
        company=company_a,
        client=client_a,
        receipt_number="REC-A",
        received_at=datetime(2026, 10, 12, tzinfo=UTC),
        amount=Decimal("100.00"),
        payment_method="CASH",
        received_by=actor,
    )
    allocation = ClientReceiptAllocation.objects.create(
        receipt=receipt_a,
        invoice=invoice_b,
        amount=Decimal("25.00"),
        allocated_by=actor,
        allocated_at=datetime(2026, 10, 12, tzinfo=UTC),
    )
    credit_note = ClientCreditNote.objects.create(
        company=company_a,
        client=client_a,
        invoice=invoice_b,
        note_number="CN-A",
        note_date=date(2026, 10, 12),
        reason="Historical fixture",
        created_by=actor,
    )

    profile_a = payment_profile(company_a, "A")
    foreign_bank = account(company_b, "B-1010")
    PaymentAccountingProfile.objects.filter(pk=profile_a.pk).update(bank_account=foreign_bank)

    payable_a = account(company_a, "A-2100", AccountType.LIABILITY)
    payable_b = account(company_b, "B-2100", AccountType.LIABILITY)
    vendor_a = Vendor.objects.create(
        company=company_a, code="VEN-A", name="Vendor A", payable_account=payable_a
    )
    vendor_b = Vendor.objects.create(
        company=company_b, code="VEN-B", name="Vendor B", payable_account=payable_b
    )
    bill_a = VendorBill.objects.create(
        company=company_a,
        vendor=vendor_a,
        vendor_invoice_number="EXT-A",
        bill_number="BILL-A",
        bill_date=date(2026, 10, 12),
        due_date=date(2026, 11, 12),
        created_by=actor,
    )
    bill_b = VendorBill.objects.create(
        company=company_b,
        vendor=vendor_b,
        vendor_invoice_number="EXT-B",
        bill_number="BILL-B",
        bill_date=date(2026, 10, 12),
        due_date=date(2026, 11, 12),
        created_by=actor,
    )
    VendorBill.objects.filter(pk=bill_a.pk).update(vendor=vendor_b)
    voucher = PaymentVoucher.objects.create(
        company=company_a,
        vendor_bill=bill_b,
        voucher_number="PV-A",
        payment_date=date(2026, 10, 12),
        amount=Decimal("25.00"),
        created_by=actor,
    )

    deployment_a = deployment_graph(company_a, "A")
    employee_b = EmployeeFactory.create(company=company_b)
    EmployeeDeployment.objects.filter(pk=deployment_a["deployment"].pk).update(employee=employee_b)

    document_type = DocumentTypeFactory.create(company=company_a)
    employee_a = EmployeeFactory.create(company=company_a)
    document = EmployeeDocumentFactory.create(
        company=company_a, employee=employee_a, document_type=document_type
    )
    EmployeeDocument.objects.filter(pk=document.pk).update(employee=employee_b)

    shared_user = UserFactory.create()
    role_a = RoleFactory.create(company=company_a)
    assignment_a = UserRoleAssignmentFactory.create(
        user=shared_user,
        role=role_a,
        scope_type=AccessScopeType.BRANCH,
        company=company_a,
        branch=deployment_a["branch"],
    )
    branch_b = BranchFactory.create(company=company_b, region__company=company_b)
    UserRoleAssignment.objects.filter(pk=assignment_a.pk).update(branch=branch_b)
    UserRoleAssignmentFactory.create(
        user=shared_user,
        role=RoleFactory.create(company=company_b),
        scope_type=AccessScopeType.COMPANY,
        company=company_b,
    )

    return {
        "company_a": company_a,
        "company_b": company_b,
        "invoice_a": invoice_a,
        "allocation": allocation,
        "credit_note": credit_note,
        "profile_a": profile_a,
        "bill_a": bill_a,
        "voucher": voucher,
        "deployment": deployment_a["deployment"],
        "document": document,
        "assignment": assignment_a,
    }


def snapshot(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    model_by_key: dict[str, Any] = {
        "invoice_a": ClientInvoice,
        "allocation": ClientReceiptAllocation,
        "credit_note": ClientCreditNote,
        "profile_a": PaymentAccountingProfile,
        "bill_a": VendorBill,
        "voucher": PaymentVoucher,
        "deployment": EmployeeDeployment,
        "document": EmployeeDocument,
        "assignment": UserRoleAssignment,
    }
    return {
        key: model.objects.filter(pk=graph[key].pk).values().get()
        for key, model in model_by_key.items()
    }


def test_scanner_detects_representative_corruption_without_mutation() -> None:
    graph = create_corrupt_graph()
    before = snapshot(graph)
    fixed_time = datetime(2026, 10, 12, 13, 0, tzinfo=UTC)

    first = run_integrity_scan(clock=lambda: fixed_time)
    second = run_integrity_scan(clock=lambda: fixed_time)

    assert first.as_dict() == second.as_dict()
    assert snapshot(graph) == before
    assert first.summary.total_findings == 9
    assert first.summary.errors == 9
    assert first.summary.warnings == 0
    assert {finding.check_id for finding in first.findings} == {
        "billing.adjustment.invoice_company_match",
        "billing.invoice.tenant_relations",
        "billing.receipt_allocation.invoice_company_match",
        "deployment.employee_deployment.tenant_relations",
        "documents.employee_document.tenant_relations",
        "finance.payment_accounting_profile.account_company_match",
        "finance.payment_voucher.tenant_relations",
        "finance.vendor_bill.tenant_relations",
        "identity.role_assignment.scope_company_match",
    }
    assert all(finding.metadata == {} for finding in first.findings)


def test_company_scope_uses_outer_owner_and_keeps_outgoing_corruption_visible() -> None:
    graph = create_corrupt_graph()

    scoped_a = run_integrity_scan(company_id=graph["company_a"].id)
    scoped_b = run_integrity_scan(company_id=graph["company_b"].id)

    assert scoped_a.summary.total_findings == 9
    assert scoped_b.summary.total_findings == 0
    assert all(
        finding.owning_company_id == str(graph["company_a"].id) for finding in scoped_a.findings
    )
    assert any(
        finding.conflicting_company_id == str(graph["company_b"].id)
        for finding in scoped_a.findings
    )
    # Company B is inactive; inactivity does not hide structural corruption.
    assert graph["company_b"].is_active is False


def test_document_check_does_not_open_private_files() -> None:
    graph = create_corrupt_graph()

    with patch("dsms.documents.storage.private_document_storage.open") as storage_open:
        result = run_integrity_scan(domains=["documents"])

    assert result.summary.total_findings == 1
    assert result.findings[0].record_id == str(graph["document"].id)
    storage_open.assert_not_called()


def test_single_check_has_one_bounded_values_query(django_assert_num_queries) -> None:  # type: ignore[no-untyped-def]
    graph = create_corrupt_graph()

    with django_assert_num_queries(1):
        result = run_integrity_scan(
            check_ids=["finance.payment_accounting_profile.account_company_match"],
            company_id=graph["company_a"].id,
        )

    assert result.summary.total_findings == 1
