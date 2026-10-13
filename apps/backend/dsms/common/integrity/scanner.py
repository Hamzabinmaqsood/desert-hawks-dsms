from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from uuid import UUID

from .registry import IntegrityCheckRegistry
from .types import (
    ExecutedIntegrityCheck,
    IntegrityFinding,
    IntegrityScanResult,
    IntegrityScanScope,
    IntegrityScanSummary,
    IntegritySeverity,
)


class IntegrityExecutionError(RuntimeError):
    def __init__(self, check_id: str) -> None:
        self.check_id = check_id
        super().__init__(f"Integrity check execution failed: {check_id}")


def get_default_registry() -> IntegrityCheckRegistry:
    # Explicit discovery avoids app-loading/import-order registration side effects.
    from .checks import DEFAULT_INTEGRITY_CHECKS

    return IntegrityCheckRegistry(DEFAULT_INTEGRITY_CHECKS)


def run_integrity_scan(
    *,
    registry: IntegrityCheckRegistry | None = None,
    check_ids: Iterable[str] | None = None,
    domains: Iterable[str] | None = None,
    company_id: UUID | None = None,
    clock: Callable[[], datetime] | None = None,
) -> IntegrityScanResult:
    active_registry = registry or get_default_registry()
    selected = active_registry.select(check_ids=check_ids, domains=domains)
    scope = IntegrityScanScope(company_id=company_id)
    now = clock or (lambda: datetime.now(UTC))
    started_at = now()
    findings_by_identity: dict[tuple[str, str, str, str, str | None], IntegrityFinding] = {}
    executed: list[ExecutedIntegrityCheck] = []

    for check in selected:
        try:
            check_findings = tuple(check.scanner(scope))
        except Exception as exc:
            raise IntegrityExecutionError(check.check_id) from exc

        for finding in check_findings:
            if finding.check_id != check.check_id or finding.domain != check.domain:
                raise IntegrityExecutionError(check.check_id)
            findings_by_identity.setdefault(finding.identity, finding)

        unique_count = len({finding.identity for finding in check_findings})
        executed.append(
            ExecutedIntegrityCheck(
                check_id=check.check_id,
                domain=check.domain,
                description=check.description,
                severity=check.severity,
                status="FAILED" if unique_count else "PASSED",
                finding_count=unique_count,
            )
        )

    findings = tuple(sorted(findings_by_identity.values(), key=lambda finding: finding.sort_key))
    domain_counts = Counter(finding.domain for finding in findings)
    failed_checks = sum(check.status == "FAILED" for check in executed)
    summary = IntegrityScanSummary(
        total_checks=len(executed),
        passed_checks=len(executed) - failed_checks,
        failed_checks=failed_checks,
        total_findings=len(findings),
        errors=sum(finding.severity == IntegritySeverity.ERROR for finding in findings),
        warnings=sum(finding.severity == IntegritySeverity.WARNING for finding in findings),
        findings_by_domain=dict(sorted(domain_counts.items())),
    )
    return IntegrityScanResult(
        started_at=started_at,
        completed_at=now(),
        scope=scope,
        checks_run=tuple(executed),
        summary=summary,
        findings=findings,
    )
