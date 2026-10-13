from datetime import UTC, datetime

import pytest

from dsms.common.integrity import (
    INTEGRITY_SCHEMA_VERSION,
    DuplicateIntegrityCheckError,
    IntegrityCheck,
    IntegrityCheckRegistry,
    IntegrityExecutionError,
    IntegrityFinding,
    IntegritySeverity,
    UnknownIntegrityCheckError,
    UnknownIntegrityDomainError,
    get_default_registry,
    run_integrity_scan,
)


def finding(
    *,
    check_id: str,
    domain: str,
    severity: IntegritySeverity,
    record_id: str,
) -> IntegrityFinding:
    return IntegrityFinding(
        check_id=check_id,
        domain=domain,
        severity=severity,
        finding_type="TEST_FINDING",
        resource_type="tests.Resource",
        record_id=record_id,
        owning_company_id="00000000-0000-0000-0000-000000000001",
        conflicting_company_id="00000000-0000-0000-0000-000000000002",
        relation="test_relation",
        message="Safe test finding.",
        metadata={"safe_code": "TEST"},
    )


def test_default_registry_discovery_is_explicit_and_deterministic() -> None:
    first = get_default_registry()
    second = get_default_registry()

    expected = (
        "billing.adjustment.invoice_company_match",
        "billing.invoice.tenant_relations",
        "billing.receipt_allocation.invoice_company_match",
        "deployment.employee_deployment.tenant_relations",
        "documents.employee_document.tenant_relations",
        "finance.payment_accounting_profile.account_company_match",
        "finance.payment_voucher.tenant_relations",
        "finance.vendor_bill.tenant_relations",
        "identity.role_assignment.scope_company_match",
    )
    assert tuple(check.check_id for check in first.checks) == expected
    assert tuple(check.check_id for check in second.checks) == expected
    assert first is not second


def test_registry_rejects_duplicate_check_ids() -> None:
    check = IntegrityCheck(
        check_id="tests.duplicate",
        domain="tests",
        description="Duplicate test.",
        severity=IntegritySeverity.ERROR,
        scanner=lambda scope: (),
    )
    registry = IntegrityCheckRegistry([check])

    with pytest.raises(DuplicateIntegrityCheckError, match="tests.duplicate"):
        registry.register(check)


def test_registry_filters_and_rejects_unknown_selectors() -> None:
    registry = get_default_registry()

    assert {check.domain for check in registry.select(domains=["billing"])} == {"billing"}
    assert [
        check.check_id
        for check in registry.select(
            check_ids=["finance.payment_accounting_profile.account_company_match"]
        )
    ] == ["finance.payment_accounting_profile.account_company_match"]

    with pytest.raises(UnknownIntegrityDomainError, match="typo"):
        registry.select(domains=["typo"])
    with pytest.raises(UnknownIntegrityCheckError, match="tests.missing"):
        registry.select(check_ids=["tests.missing"])


def test_result_schema_summary_deduplication_and_ordering() -> None:
    error_check = IntegrityCheck(
        check_id="z.error",
        domain="zeta",
        description="Error check.",
        severity=IntegritySeverity.ERROR,
        scanner=lambda scope: (
            finding(
                check_id="z.error",
                domain="zeta",
                severity=IntegritySeverity.ERROR,
                record_id="2",
            ),
            finding(
                check_id="z.error",
                domain="zeta",
                severity=IntegritySeverity.ERROR,
                record_id="2",
            ),
        ),
    )
    warning_check = IntegrityCheck(
        check_id="a.warning",
        domain="alpha",
        description="Warning check.",
        severity=IntegritySeverity.WARNING,
        scanner=lambda scope: (
            finding(
                check_id="a.warning",
                domain="alpha",
                severity=IntegritySeverity.WARNING,
                record_id="1",
            ),
        ),
    )
    clean_check = IntegrityCheck(
        check_id="m.clean",
        domain="middle",
        description="Clean check.",
        severity=IntegritySeverity.ERROR,
        scanner=lambda scope: (),
    )
    fixed_time = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)

    result = run_integrity_scan(
        registry=IntegrityCheckRegistry([error_check, warning_check, clean_check]),
        clock=lambda: fixed_time,
    )
    payload = result.as_dict()

    assert payload["schema_version"] == INTEGRITY_SCHEMA_VERSION == 1
    assert payload["started_at"] == payload["completed_at"] == fixed_time.isoformat()
    assert [item["check_id"] for item in payload["checks_run"]] == [
        "a.warning",
        "m.clean",
        "z.error",
    ]
    assert [item["check_id"] for item in payload["findings"]] == [
        "a.warning",
        "z.error",
    ]
    assert payload["summary"] == {
        "total_checks": 3,
        "passed_checks": 1,
        "failed_checks": 2,
        "total_findings": 2,
        "errors": 1,
        "warnings": 1,
        "findings_by_domain": {"alpha": 1, "zeta": 1},
    }
    assert set(payload["findings"][0]) == {
        "schema_version",
        "check_id",
        "domain",
        "severity",
        "finding_type",
        "resource_type",
        "record_id",
        "owning_company_id",
        "conflicting_company_id",
        "relation",
        "message",
        "metadata",
    }


def test_scanner_execution_failure_is_not_converted_to_finding() -> None:
    def crash(scope):  # type: ignore[no-untyped-def]
        raise RuntimeError("private database detail")

    check = IntegrityCheck(
        check_id="tests.crash",
        domain="tests",
        description="Crash test.",
        severity=IntegritySeverity.ERROR,
        scanner=crash,
    )

    with pytest.raises(IntegrityExecutionError, match="tests.crash") as captured:
        run_integrity_scan(registry=IntegrityCheckRegistry([check]))

    assert isinstance(captured.value.__cause__, RuntimeError)
