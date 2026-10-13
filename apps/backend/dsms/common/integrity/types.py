from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

INTEGRITY_SCHEMA_VERSION = 1


class IntegritySeverity(StrEnum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True)
class IntegrityScanScope:
    company_id: UUID | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"company_id": str(self.company_id) if self.company_id is not None else None}


@dataclass(frozen=True)
class IntegrityFinding:
    check_id: str
    domain: str
    severity: IntegritySeverity
    finding_type: str
    resource_type: str
    record_id: str
    owning_company_id: str | None
    conflicting_company_id: str | None
    relation: str
    message: str
    metadata: dict[str, str | int | bool | None] = field(default_factory=dict)

    @property
    def identity(self) -> tuple[str, str, str, str, str | None]:
        return (
            self.check_id,
            self.resource_type,
            self.record_id,
            self.relation,
            self.conflicting_company_id,
        )

    @property
    def sort_key(self) -> tuple[str, str, str, str, str]:
        return (*self.identity[:-1], self.identity[-1] or "")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": INTEGRITY_SCHEMA_VERSION,
            "check_id": self.check_id,
            "domain": self.domain,
            "severity": self.severity.value,
            "finding_type": self.finding_type,
            "resource_type": self.resource_type,
            "record_id": self.record_id,
            "owning_company_id": self.owning_company_id,
            "conflicting_company_id": self.conflicting_company_id,
            "relation": self.relation,
            "message": self.message,
            "metadata": dict(sorted(self.metadata.items())),
        }


@dataclass(frozen=True)
class ExecutedIntegrityCheck:
    check_id: str
    domain: str
    description: str
    severity: IntegritySeverity
    status: str
    finding_count: int

    def as_dict(self) -> dict[str, str | int]:
        return {
            "check_id": self.check_id,
            "domain": self.domain,
            "description": self.description,
            "severity": self.severity.value,
            "status": self.status,
            "finding_count": self.finding_count,
        }


@dataclass(frozen=True)
class IntegrityScanSummary:
    total_checks: int
    passed_checks: int
    failed_checks: int
    total_findings: int
    errors: int
    warnings: int
    findings_by_domain: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "total_findings": self.total_findings,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings_by_domain": dict(sorted(self.findings_by_domain.items())),
        }


@dataclass(frozen=True)
class IntegrityScanResult:
    started_at: datetime
    completed_at: datetime
    scope: IntegrityScanScope
    checks_run: tuple[ExecutedIntegrityCheck, ...]
    summary: IntegrityScanSummary
    findings: tuple[IntegrityFinding, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": INTEGRITY_SCHEMA_VERSION,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "scope": self.scope.as_dict(),
            "checks_run": [check.as_dict() for check in self.checks_run],
            "summary": self.summary.as_dict(),
            "findings": [finding.as_dict() for finding in self.findings],
        }
