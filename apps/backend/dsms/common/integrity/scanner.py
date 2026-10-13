from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from django.db import connection, transaction

from .registry import IntegrityCheck, IntegrityCheckRegistry
from .types import (
    ExecutedIntegrityCheck,
    IntegrityAuditMetadata,
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


@dataclass(frozen=True)
class IntegrityAuditOptions:
    statement_timeout_ms: int = 30_000
    lock_timeout_ms: int = 1_000
    detail_limit: int = 1_000

    def __post_init__(self) -> None:
        if self.statement_timeout_ms <= 0:
            raise ValueError("statement_timeout_ms must be positive")
        if self.lock_timeout_ms <= 0:
            raise ValueError("lock_timeout_ms must be positive")
        if self.detail_limit < 0:
            raise ValueError("detail_limit must not be negative")


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
    audit_options: IntegrityAuditOptions | None = None,
) -> IntegrityScanResult:
    if audit_options is not None and connection.vendor != "postgresql":
        raise IntegrityExecutionError("audit.requires_postgresql")
    active_registry = registry or get_default_registry()
    selected = active_registry.select(check_ids=check_ids, domains=domains)
    scope = IntegrityScanScope(company_id=company_id)
    now = clock or (lambda: datetime.now(UTC))
    started_at = now()
    findings_by_identity: dict[tuple[str, str, str, str, str | None], IntegrityFinding] = {}
    finding_counts_by_domain: Counter[str] = Counter()
    error_count = 0
    warning_count = 0
    total_findings = 0
    executed: list[ExecutedIntegrityCheck] = []

    def consume(check: IntegrityCheck, candidates: Iterable[IntegrityFinding]) -> int:
        nonlocal error_count, total_findings, warning_count
        seen: set[tuple[str, str, str, str, str | None]] | None = (
            set() if audit_options is None else None
        )
        check_count = 0
        for finding in candidates:
            if finding.check_id != check.check_id or finding.domain != check.domain:
                raise IntegrityExecutionError(check.check_id)
            if seen is not None:
                if finding.identity in seen:
                    continue
                seen.add(finding.identity)
            check_count += 1
            total_findings += 1
            finding_counts_by_domain[finding.domain] += 1
            error_count += finding.severity == IntegritySeverity.ERROR
            warning_count += finding.severity == IntegritySeverity.WARNING
            if audit_options is None or len(findings_by_identity) < audit_options.detail_limit:
                findings_by_identity.setdefault(finding.identity, finding)
        return check_count

    for check in selected:
        try:
            if audit_options is None:
                unique_count = consume(check, check.scanner(scope))
            else:
                with transaction.atomic():
                    with connection.cursor() as cursor:
                        cursor.execute("SET TRANSACTION READ ONLY")
                        cursor.execute(
                            "SELECT set_config('statement_timeout', %s, true)",
                            [f"{audit_options.statement_timeout_ms}ms"],
                        )
                        cursor.execute(
                            "SELECT set_config('lock_timeout', %s, true)",
                            [f"{audit_options.lock_timeout_ms}ms"],
                        )
                    unique_count = consume(check, check.scanner(scope))
        except Exception as exc:
            raise IntegrityExecutionError(check.check_id) from exc
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
    failed_checks = sum(check.status == "FAILED" for check in executed)
    summary = IntegrityScanSummary(
        total_checks=len(executed),
        passed_checks=len(executed) - failed_checks,
        failed_checks=failed_checks,
        total_findings=total_findings,
        errors=error_count,
        warnings=warning_count,
        findings_by_domain=dict(sorted(finding_counts_by_domain.items())),
    )
    return IntegrityScanResult(
        started_at=started_at,
        completed_at=now(),
        scope=scope,
        checks_run=tuple(executed),
        summary=summary,
        findings=findings,
        audit=(
            IntegrityAuditMetadata(
                read_only=True,
                statement_timeout_ms=audit_options.statement_timeout_ms,
                lock_timeout_ms=audit_options.lock_timeout_ms,
                detail_limit=audit_options.detail_limit,
                reported_findings=len(findings),
                findings_truncated=total_findings > len(findings),
            )
            if audit_options is not None
            else None
        ),
    )
