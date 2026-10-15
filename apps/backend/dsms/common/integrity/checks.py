from __future__ import annotations

from collections.abc import Iterable, Iterator
from functools import partial
from typing import Any, cast

from django.apps import apps

from dsms.billing.models import (
    ClientCreditNote,
    ClientDebitNote,
    ClientInvoice,
    ClientReceiptAllocation,
)
from dsms.deployment.models import EmployeeDeployment
from dsms.documents.models import EmployeeDocument
from dsms.finance.payment_models import PaymentAccountingProfile
from dsms.finance.procurement_models import PaymentVoucher, VendorBill
from dsms.identity.models import UserRoleAssignment
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    PlanEntitlementEvent,
    PlanModuleDefault,
    SubscriptionEntitlementEvent,
    SubscriptionModuleOverride,
    SubscriptionModuleSnapshot,
)
from dsms.subscriptions.modules import TENANT_MODULE_REGISTRY

from .coverage import TENANT_RELATION_SPECS
from .registry import IntegrityCheck
from .types import IntegrityFinding, IntegrityScanScope, IntegritySeverity

ERROR = IntegritySeverity.ERROR
FINDING_TYPE = "CROSS_COMPANY_RELATION"


def scan_subscription_entitlement_configuration(
    scope: IntegrityScanScope,
) -> Iterable[IntegrityFinding]:
    check_id = "subscriptions.entitlement_configuration"
    known_ids = set(TENANT_MODULE_REGISTRY.module_ids)
    derived_models = (
        SubscriptionModuleSnapshot,
        SubscriptionModuleOverride,
        SubscriptionEntitlementEvent,
    )
    for model in derived_models:
        queryset = model.objects.exclude(module_id="").values(
            "id", "module_id", "subscription__company_id"
        )
        if scope.company_id is not None:
            queryset = queryset.filter(subscription__company_id=scope.company_id)
        for row in queryset.order_by("pk").iterator():
            if row["module_id"] in known_ids:
                continue
            yield IntegrityFinding(
                check_id=check_id,
                domain="subscriptions",
                severity=ERROR,
                finding_type="UNKNOWN_MODULE_ID",
                resource_type=model._meta.label,
                record_id=str(row["id"]),
                owning_company_id=str(row["subscription__company_id"]),
                conflicting_company_id=None,
                relation="module_id",
                message=f"{model._meta.label}.module_id is not present in the code registry.",
                metadata={"module_id": row["module_id"]},
            )

    if scope.company_id is None:
        for global_model in (PlanModuleDefault, PlanEntitlementEvent):
            queryset = global_model.objects.exclude(module_id="").values("id", "module_id")
            for row in queryset.order_by("pk").iterator():
                if row["module_id"] in known_ids:
                    continue
                yield IntegrityFinding(
                    check_id=check_id,
                    domain="subscriptions",
                    severity=ERROR,
                    finding_type="UNKNOWN_MODULE_ID",
                    resource_type=global_model._meta.label,
                    record_id=str(row["id"]),
                    owning_company_id=None,
                    conflicting_company_id=None,
                    relation="module_id",
                    message=(
                        f"{global_model._meta.label}.module_id is not present in the code registry."
                    ),
                    metadata={"module_id": row["module_id"]},
                )

    policies = CompanyModulePolicy.objects.filter(
        mode=CompanyModulePolicyMode.SUBSCRIPTION,
        company__commercial_subscription__isnull=True,
    ).values("id", "company_id")
    if scope.company_id is not None:
        policies = policies.filter(company_id=scope.company_id)
    for row in policies.order_by("pk").iterator():
        yield IntegrityFinding(
            check_id=check_id,
            domain="subscriptions",
            severity=ERROR,
            finding_type="MISSING_SUBSCRIPTION_ENTITLEMENT_STATE",
            resource_type=CompanyModulePolicy._meta.label,
            record_id=str(row["id"]),
            owning_company_id=str(row["company_id"]),
            conflicting_company_id=None,
            relation="company.commercial_subscription",
            message="Subscription policy Company has no commercial Subscription.",
        )


def _rows(queryset: Any, scope: IntegrityScanScope, company_path: str) -> Iterator[dict[str, Any]]:
    if scope.company_id is not None:
        queryset = queryset.filter(**{company_path: scope.company_id})
    return cast(Iterator[dict[str, Any]], queryset.order_by("pk").iterator())


def _finding(
    *,
    check_id: str,
    domain: str,
    resource_type: str,
    record_id: Any,
    owning_company_id: Any,
    conflicting_company_id: Any,
    relation: str,
) -> IntegrityFinding:
    return IntegrityFinding(
        check_id=check_id,
        domain=domain,
        severity=ERROR,
        finding_type=FINDING_TYPE,
        resource_type=resource_type,
        record_id=str(record_id),
        owning_company_id=str(owning_company_id) if owning_company_id is not None else None,
        conflicting_company_id=(
            str(conflicting_company_id) if conflicting_company_id is not None else None
        ),
        relation=relation,
        message=f"{resource_type}.{relation} belongs to a different Company.",
    )


def scan_role_assignment_scope(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "identity.role_assignment.scope_company_match"
    queryset = UserRoleAssignment.objects.values(
        "id",
        "company_id",
        "role__company_id",
        "region__company_id",
        "branch__company_id",
        "department__company_id",
        "operational_zone__company_id",
    )
    relations = (
        ("role", "role__company_id", True),
        ("region", "region__company_id", False),
        ("branch", "branch__company_id", False),
        ("department", "department__company_id", False),
        ("operational_zone", "operational_zone__company_id", False),
    )
    for row in _rows(queryset, scope, "company_id"):
        owner = row["company_id"]
        for relation, field, nullable_global in relations:
            related_company = row[field]
            if related_company is None and nullable_global:
                continue
            if related_company is not None and related_company != owner:
                yield _finding(
                    check_id=check_id,
                    domain="identity",
                    resource_type="identity.UserRoleAssignment",
                    record_id=row["id"],
                    owning_company_id=owner,
                    conflicting_company_id=related_company,
                    relation=relation,
                )


def scan_invoice_relations(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "billing.invoice.tenant_relations"
    queryset = ClientInvoice.objects.values(
        "id",
        "company_id",
        "client__company_id",
        "contract__company_id",
        "source_billing_schedule__company_id",
        "accounting_journal__company_id",
    )
    relations = (
        ("client", "client__company_id"),
        ("contract", "contract__company_id"),
        ("source_billing_schedule", "source_billing_schedule__company_id"),
        ("accounting_journal", "accounting_journal__company_id"),
    )
    yield from _direct_company_findings(
        queryset=queryset,
        scope=scope,
        company_path="company_id",
        check_id=check_id,
        domain="billing",
        resource_type="billing.ClientInvoice",
        relations=relations,
    )


def scan_receipt_allocations(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "billing.receipt_allocation.invoice_company_match"
    queryset = ClientReceiptAllocation.objects.values(
        "id", "receipt__company_id", "invoice__company_id"
    )
    for row in _rows(queryset, scope, "receipt__company_id"):
        owner = row["receipt__company_id"]
        conflicting = row["invoice__company_id"]
        if owner != conflicting:
            yield _finding(
                check_id=check_id,
                domain="billing",
                resource_type="billing.ClientReceiptAllocation",
                record_id=row["id"],
                owning_company_id=owner,
                conflicting_company_id=conflicting,
                relation="invoice",
            )


def scan_adjustment_relations(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "billing.adjustment.invoice_company_match"
    for model, resource_type in (
        (ClientCreditNote, "billing.ClientCreditNote"),
        (ClientDebitNote, "billing.ClientDebitNote"),
    ):
        queryset = model.objects.values(
            "id",
            "company_id",
            "client__company_id",
            "invoice__company_id",
            "accounting_journal__company_id",
        )
        yield from _direct_company_findings(
            queryset=queryset,
            scope=scope,
            company_path="company_id",
            check_id=check_id,
            domain="billing",
            resource_type=resource_type,
            relations=(
                ("client", "client__company_id"),
                ("invoice", "invoice__company_id"),
                ("accounting_journal", "accounting_journal__company_id"),
            ),
        )


def scan_payment_accounting_profile(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "finance.payment_accounting_profile.account_company_match"
    queryset = PaymentAccountingProfile.objects.values(
        "id",
        "company_id",
        "payroll_payable_account__company_id",
        "vendor_payable_account__company_id",
        "gateway_clearing_account__company_id",
        "bank_account__company_id",
        "provider_fee_account__company_id",
    )
    relations = tuple(
        (name, f"{name}__company_id")
        for name in (
            "payroll_payable_account",
            "vendor_payable_account",
            "gateway_clearing_account",
            "bank_account",
            "provider_fee_account",
        )
    )
    yield from _direct_company_findings(
        queryset=queryset,
        scope=scope,
        company_path="company_id",
        check_id=check_id,
        domain="finance",
        resource_type="finance.PaymentAccountingProfile",
        relations=relations,
    )


def scan_vendor_bill_relations(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "finance.vendor_bill.tenant_relations"
    queryset = VendorBill.objects.values(
        "id",
        "company_id",
        "vendor__company_id",
        "purchase_order__company_id",
        "journal_entry__company_id",
    )
    yield from _direct_company_findings(
        queryset=queryset,
        scope=scope,
        company_path="company_id",
        check_id=check_id,
        domain="finance",
        resource_type="finance.VendorBill",
        relations=(
            ("vendor", "vendor__company_id"),
            ("purchase_order", "purchase_order__company_id"),
            ("journal_entry", "journal_entry__company_id"),
        ),
    )


def scan_payment_voucher_relations(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "finance.payment_voucher.tenant_relations"
    queryset = PaymentVoucher.objects.values(
        "id", "company_id", "vendor_bill__company_id", "journal_entry__company_id"
    )
    yield from _direct_company_findings(
        queryset=queryset,
        scope=scope,
        company_path="company_id",
        check_id=check_id,
        domain="finance",
        resource_type="finance.PaymentVoucher",
        relations=(
            ("vendor_bill", "vendor_bill__company_id"),
            ("journal_entry", "journal_entry__company_id"),
        ),
    )


def scan_employee_deployment_relations(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "deployment.employee_deployment.tenant_relations"
    queryset = EmployeeDeployment.objects.values(
        "id",
        "company_id",
        "employee__company_id",
        "client__company_id",
        "contract__company_id",
        "site__company_id",
        "primary_post__company_id",
        "managing_branch__company_id",
    )
    yield from _direct_company_findings(
        queryset=queryset,
        scope=scope,
        company_path="company_id",
        check_id=check_id,
        domain="deployment",
        resource_type="deployment.EmployeeDeployment",
        relations=(
            ("employee", "employee__company_id"),
            ("client", "client__company_id"),
            ("contract", "contract__company_id"),
            ("site", "site__company_id"),
            ("primary_post", "primary_post__company_id"),
            ("managing_branch", "managing_branch__company_id"),
        ),
    )


def scan_employee_document_relations(scope: IntegrityScanScope) -> Iterable[IntegrityFinding]:
    check_id = "documents.employee_document.tenant_relations"
    queryset = EmployeeDocument.objects.values(
        "id",
        "company_id",
        "employee__company_id",
        "document_type__company_id",
        "superseded_by__company_id",
    )
    for row in _rows(queryset, scope, "company_id"):
        owner = row["company_id"]
        for relation, field, allow_global in (
            ("employee", "employee__company_id", False),
            ("document_type", "document_type__company_id", True),
            ("superseded_by", "superseded_by__company_id", False),
        ):
            conflicting = row[field]
            if allow_global and conflicting is None:
                continue
            if conflicting is not None and conflicting != owner:
                yield _finding(
                    check_id=check_id,
                    domain="documents",
                    resource_type="documents.EmployeeDocument",
                    record_id=row["id"],
                    owning_company_id=owner,
                    conflicting_company_id=conflicting,
                    relation=relation,
                )


def _direct_company_findings(
    *,
    queryset: Any,
    scope: IntegrityScanScope,
    company_path: str,
    check_id: str,
    domain: str,
    resource_type: str,
    relations: tuple[tuple[str, str], ...],
) -> Iterable[IntegrityFinding]:
    for row in _rows(queryset, scope, company_path):
        owner = row["company_id"]
        for relation, field in relations:
            conflicting = row[field]
            if conflicting is not None and conflicting != owner:
                yield _finding(
                    check_id=check_id,
                    domain=domain,
                    resource_type=resource_type,
                    record_id=row["id"],
                    owning_company_id=owner,
                    conflicting_company_id=conflicting,
                    relation=relation,
                )


def scan_manifest_relations(
    scope: IntegrityScanScope, *, check_id: str
) -> Iterable[IntegrityFinding]:
    for spec in TENANT_RELATION_SPECS:
        if spec.check_id != check_id or spec.model_label in {
            "billing.ClientCreditNote",
            "billing.ClientDebitNote",
            "billing.ClientInvoice",
            "deployment.EmployeeDeployment",
            "documents.EmployeeDocument",
            "finance.PaymentAccountingProfile",
            "finance.PaymentVoucher",
            "finance.VendorBill",
            "identity.UserRoleAssignment",
        }:
            continue
        model = apps.get_model(spec.model_label)
        relation_paths = tuple((name, f"{name}__company_id") for name in spec.relation_fields)
        queryset = model.objects.values("id", "company_id", *(path for _, path in relation_paths))
        yield from _direct_company_findings(
            queryset=queryset,
            scope=scope,
            company_path="company_id",
            check_id=check_id,
            domain=check_id.partition(".")[0],
            resource_type=spec.model_label,
            relations=relation_paths,
        )


MANIFEST_CHECKS = tuple(
    IntegrityCheck(
        check_id=check_id,
        domain=check_id.partition(".")[0],
        description=f"Explicit tenant-relation manifest coverage for {check_id.partition('.')[0]}.",
        severity=ERROR,
        scanner=partial(scan_manifest_relations, check_id=check_id),
    )
    for check_id in (
        "analytics.tenant_relations",
        "assets.tenant_relations",
        "attendance.tenant_relations",
        "incidents.tenant_relations",
        "patrol.tenant_relations",
        "repository.remaining_tenant_relations",
        "supervision.tenant_relations",
    )
)


DEFAULT_INTEGRITY_CHECKS = (
    IntegrityCheck(
        check_id="subscriptions.entitlement_configuration",
        domain="subscriptions",
        description="Commercial entitlement module IDs and rollout state are structurally valid.",
        severity=ERROR,
        scanner=scan_subscription_entitlement_configuration,
    ),
    IntegrityCheck(
        check_id="billing.adjustment.invoice_company_match",
        domain="billing",
        description="Credit/debit note client and invoice Companies match the note Company.",
        severity=ERROR,
        scanner=scan_adjustment_relations,
    ),
    IntegrityCheck(
        check_id="billing.invoice.tenant_relations",
        domain="billing",
        description="Invoice tenant-bearing relations match the invoice Company.",
        severity=ERROR,
        scanner=scan_invoice_relations,
    ),
    IntegrityCheck(
        check_id="billing.receipt_allocation.invoice_company_match",
        domain="billing",
        description="Receipt allocations do not link invoices from another Company.",
        severity=ERROR,
        scanner=scan_receipt_allocations,
    ),
    IntegrityCheck(
        check_id="deployment.employee_deployment.tenant_relations",
        domain="deployment",
        description="Employee deployment relations match the deployment Company.",
        severity=ERROR,
        scanner=scan_employee_deployment_relations,
    ),
    IntegrityCheck(
        check_id="documents.employee_document.tenant_relations",
        domain="documents",
        description="Employee-document metadata belongs to one Company.",
        severity=ERROR,
        scanner=scan_employee_document_relations,
    ),
    IntegrityCheck(
        check_id="finance.payment_accounting_profile.account_company_match",
        domain="finance",
        description="Payment accounting profile accounts match the profile Company.",
        severity=ERROR,
        scanner=scan_payment_accounting_profile,
    ),
    IntegrityCheck(
        check_id="finance.payment_voucher.tenant_relations",
        domain="finance",
        description="Payment voucher bill and journal match the voucher Company.",
        severity=ERROR,
        scanner=scan_payment_voucher_relations,
    ),
    IntegrityCheck(
        check_id="finance.vendor_bill.tenant_relations",
        domain="finance",
        description="Vendor bill tenant-bearing relations match the bill Company.",
        severity=ERROR,
        scanner=scan_vendor_bill_relations,
    ),
    IntegrityCheck(
        check_id="identity.role_assignment.scope_company_match",
        domain="identity",
        description="Role-assignment scope resources match the assignment Company.",
        severity=ERROR,
        scanner=scan_role_assignment_scope,
    ),
) + MANIFEST_CHECKS
