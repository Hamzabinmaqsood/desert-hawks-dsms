import json
from collections.abc import Callable, Iterable
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection

from dsms.common.integrity import (
    IntegrityAuditOptions,
    IntegrityCheck,
    IntegrityCheckRegistry,
    IntegrityExecutionError,
    IntegrityFinding,
    IntegrityScanScope,
    IntegritySeverity,
    run_integrity_scan,
)
from dsms.organization.models import Company
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db(transaction=True)


def _finding(record_id: str) -> IntegrityFinding:
    return IntegrityFinding(
        check_id="tests.audit",
        domain="tests",
        severity=IntegritySeverity.ERROR,
        finding_type="SYNTHETIC_TEST_FINDING",
        resource_type="tests.Resource",
        record_id=record_id,
        owning_company_id=None,
        conflicting_company_id=None,
        relation="synthetic",
        message="Synthetic test finding.",
    )


def _registry(
    scanner: Callable[[IntegrityScanScope], Iterable[IntegrityFinding]],
) -> IntegrityCheckRegistry:
    return IntegrityCheckRegistry(
        [
            IntegrityCheck(
                check_id="tests.audit",
                domain="tests",
                description="Audit behavior test.",
                severity=IntegritySeverity.ERROR,
                scanner=scanner,
            )
        ]
    )


def test_audit_mode_is_postgresql_read_only_and_settings_are_transaction_local() -> None:
    observed: dict[str, str] = {}

    def inspect_settings(scope):  # type: ignore[no-untyped-def]
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            observed["read_only"] = cursor.fetchone()[0]
            cursor.execute("SHOW statement_timeout")
            observed["statement_timeout"] = cursor.fetchone()[0]
            cursor.execute("SHOW lock_timeout")
            observed["lock_timeout"] = cursor.fetchone()[0]
        return ()

    result = run_integrity_scan(
        registry=_registry(inspect_settings),
        audit_options=IntegrityAuditOptions(statement_timeout_ms=4_321, lock_timeout_ms=321),
    )

    assert observed == {
        "read_only": "on",
        "statement_timeout": "4321ms",
        "lock_timeout": "321ms",
    }
    assert result.audit is not None
    assert result.audit.read_only is True
    with connection.cursor() as cursor:
        cursor.execute("SHOW transaction_read_only")
        assert cursor.fetchone()[0] == "off"


def test_audit_mode_rejects_mutation_rolls_back_and_clean_rerun_succeeds() -> None:
    company = CompanyFactory.create(code="AUDIT-MUTATION", legal_name="Original")

    def mutate(scope):  # type: ignore[no-untyped-def]
        Company.objects.filter(pk=company.pk).update(legal_name="Changed")
        return ()

    with pytest.raises(IntegrityExecutionError, match="tests.audit"):
        run_integrity_scan(
            registry=_registry(mutate),
            audit_options=IntegrityAuditOptions(),
        )

    company.refresh_from_db()
    assert company.legal_name == "Original"
    clean = run_integrity_scan(
        registry=_registry(lambda scope: ()),
        audit_options=IntegrityAuditOptions(),
    )
    assert clean.summary.total_findings == 0


def test_audit_finding_details_are_bounded_without_losing_exact_totals() -> None:
    result = run_integrity_scan(
        registry=_registry(lambda scope: (_finding(str(index)) for index in range(5))),
        audit_options=IntegrityAuditOptions(detail_limit=2),
    )

    assert result.summary.total_findings == 5
    assert result.summary.errors == 5
    assert len(result.findings) == 2
    assert result.audit is not None
    assert result.audit.reported_findings == 2
    assert result.audit.findings_truncated is True


def test_audit_command_emits_valid_versioned_json() -> None:
    output = StringIO()
    call_command(
        "tenant_integrity_scan",
        "--audit",
        "--format",
        "json",
        "--check",
        "attendance.tenant_relations",
        "--max-findings",
        "10",
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert payload["schema_version"] == 1
    assert payload["audit"] == {
        "read_only": True,
        "statement_timeout_ms": 30_000,
        "lock_timeout_ms": 1_000,
        "detail_limit": 10,
        "reported_findings": 0,
        "findings_truncated": False,
    }
