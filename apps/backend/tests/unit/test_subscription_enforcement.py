from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from dsms.analytics.providers import registry as analytics_registry
from dsms.analytics.services import calculate_metric
from dsms.finance.models import Account
from dsms.finance.payment_models import PaymentBatch, PaymentInstruction
from dsms.finance.payment_services import payment_origin_module
from dsms.finance.payment_tasks import (
    process_payment_batch_task,
    process_payment_instruction_task,
)
from dsms.finance.services import create_account
from dsms.organization.models import Company
from dsms.subscriptions import enforcement, entitlements
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    SubscriptionModuleSnapshot,
    SubscriptionStatus,
)
from tests.factories.organization import CompanyFactory
from tests.factories.subscriptions import SubscriptionFactory

pytestmark = pytest.mark.django_db


def test_service_guard_rejects_unknown_authority_argument_at_import_time() -> None:
    with pytest.raises(ValueError, match="Unknown Company authority argument"):

        @enforcement.requires_company_module("people", argument="missing")
        def invalid_guard(*, employee: object) -> None:
            return None


def subscription_company(*module_ids: str, status: str = SubscriptionStatus.ACTIVE) -> Company:
    company = CompanyFactory.create()
    subscription = SubscriptionFactory.create(
        company=company,
        status=status,
        suspended_at=timezone.now() if status == SubscriptionStatus.SUSPENDED else None,
        terminated_at=timezone.now() if status == SubscriptionStatus.TERMINATED else None,
        snapshot_initialized_at=timezone.now(),
        snapshot_plan_entitlement_revision=0,
        entitlement_revision=7,
    )
    CompanyModulePolicy.objects.create(
        company=company,
        mode=CompanyModulePolicyMode.SUBSCRIPTION,
    )
    SubscriptionModuleSnapshot.objects.bulk_create(
        [
            SubscriptionModuleSnapshot(
                subscription=subscription,
                module_id=module_id,
                source_plan_entitlement_revision=0,
            )
            for module_id in module_ids
        ]
    )
    return company


def test_missing_policy_and_legacy_policy_remain_full_access() -> None:
    missing = CompanyFactory.create()
    legacy = CompanyFactory.create()
    CompanyModulePolicy.objects.create(company=legacy)

    assert enforcement.company_has_module(missing, "finance_core")
    assert enforcement.company_has_module(legacy, "security_incidents")


@pytest.mark.parametrize("status", [SubscriptionStatus.SUSPENDED, SubscriptionStatus.TERMINATED])
def test_subscription_lifecycle_status_does_not_override_effective_modules(status: str) -> None:
    company = subscription_company("finance_core", status=status)

    assert enforcement.company_has_module(company, "finance_core")


def test_service_guard_blocks_before_business_mutation_and_reenable_restores_access() -> None:
    company = subscription_company()

    with pytest.raises(enforcement.ModuleNotEnabled) as raised:
        create_account(company=company, code="1000", name="Cash", account_type="ASSET")
    assert raised.value.default_code == "module_not_enabled"
    assert not Account.objects.filter(company=company).exists()

    subscription = company.commercial_subscription
    SubscriptionModuleSnapshot.objects.create(
        subscription=subscription,
        module_id="finance_core",
        source_plan_entitlement_revision=0,
    )
    account = create_account(company=company, code="1000", name="Cash", account_type="ASSET")
    assert account.company_id == company.id


def test_request_cache_is_company_and_revision_scoped() -> None:
    company = subscription_company("finance_core")
    request = SimpleNamespace()

    with patch(
        "dsms.subscriptions.enforcement.resolve_effective_modules",
        wraps=entitlements.resolve_effective_modules,
    ) as resolver:
        first = enforcement.resolve_company_modules(company, request=request)
        second = enforcement.resolve_company_modules(company, request=request)

    assert first is second
    assert first.entitlement_revision == 7
    assert resolver.call_count == 1
    assert (company.pk, CompanyModulePolicyMode.SUBSCRIPTION, 7) in (
        request._tenant_module_entitlement_cache
    )


def test_analytics_does_not_invoke_disabled_source_provider() -> None:
    company = subscription_company("analytics")
    definition = SimpleNamespace(
        is_active=True,
        provider_code="finance.invoice_value",
        supports_company=True,
        supports_region=False,
        supports_branch=False,
        supports_client=False,
        supports_contract=False,
        supports_site=False,
        supports_department=False,
    )

    with patch.object(analytics_registry, "get") as provider_lookup:
        result = calculate_metric(
            metric_definition=definition,
            period_start=date(2026, 10, 1),
            period_end=date(2026, 10, 15),
            company=company,
        )

    assert result.data_quality == "NOT_AVAILABLE"
    assert result.source_count == 0
    provider_lookup.assert_not_called()


def test_payment_tasks_recheck_origin_module_and_skip_without_mutation() -> None:
    company = subscription_company()
    batch = PaymentBatch(company=company, batch_type="PAYROLL")
    instruction = PaymentInstruction(batch=batch, payslip_id=uuid4())

    with patch.object(PaymentBatch.objects, "get", return_value=batch):
        assert process_payment_batch_task.run(str(uuid4())) == 0
    with patch.object(PaymentInstruction.objects, "get", return_value=instruction):
        result = process_payment_instruction_task.run(str(uuid4()))

    assert result == "SKIPPED_MODULE_NOT_ENABLED"
    assert instruction.status == "QUEUED"


def test_payment_origin_mapping_is_resource_derived() -> None:
    company = CompanyFactory.create()

    assert payment_origin_module(PaymentBatch(company=company, batch_type="PAYROLL")) == "payroll"
    assert (
        payment_origin_module(PaymentBatch(company=company, batch_type="VENDOR"))
        == "procurement_payables"
    )
    assert payment_origin_module(SimpleNamespace(company=company)) == "finance_core"
