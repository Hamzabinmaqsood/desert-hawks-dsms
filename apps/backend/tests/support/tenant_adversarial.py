from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.db.models import Model

from dsms.common.integrity import IntegrityScanResult, run_integrity_scan
from dsms.organization.models import Company
from tests.factories.organization import CompanyFactory


@dataclass(frozen=True)
class TenantPair:
    company_a: Company
    company_b: Company


def tenant_pair(prefix: str) -> TenantPair:
    return TenantPair(
        company_a=CompanyFactory.create(code=f"{prefix}-A"),
        company_b=CompanyFactory.create(code=f"{prefix}-B", is_active=False),
    )


def force_cross_company_relation(instance: Model, relation: str, foreign: Model) -> None:
    """Test-only corruption helper that deliberately bypasses model validation."""
    cast(Any, type(instance)).objects.filter(pk=instance.pk).update(**{relation: foreign})


def scoped_scan(company: Company, check_id: str) -> IntegrityScanResult:
    return run_integrity_scan(check_ids=[check_id], company_id=company.id)


def assert_outgoing_only(result_a: IntegrityScanResult, result_b: IntegrityScanResult) -> None:
    assert result_a.summary.total_findings > 0
    assert result_b.summary.total_findings == 0
    assert all(
        finding.owning_company_id == str(result_a.scope.company_id) for finding in result_a.findings
    )


def model_snapshot(instance: Model) -> dict[str, Any]:
    return cast(
        dict[str, Any], cast(Any, type(instance)).objects.filter(pk=instance.pk).values().get()
    )
