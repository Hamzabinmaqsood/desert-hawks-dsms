from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError, CommandParser

from dsms.common.integrity import IntegrityAuditOptions, IntegrityExecutionError, run_integrity_scan
from dsms.common.integrity.registry import (
    UnknownIntegrityCheckError,
    UnknownIntegrityDomainError,
)
from dsms.organization.models import Company


class Command(BaseCommand):
    help = "Run the read-only tenant integrity scanner."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.add_argument("--domain", action="append", dest="domains")
        parser.add_argument("--check", action="append", dest="check_ids")
        parser.add_argument("--company", dest="company_selector")
        parser.add_argument("--audit", action="store_true")
        parser.add_argument("--statement-timeout-ms", type=int, default=30_000)
        parser.add_argument("--lock-timeout-ms", type=int, default=1_000)
        parser.add_argument("--max-findings", type=int, default=1_000)

    def handle(self, *args: Any, **options: Any) -> None:
        company = self._resolve_company(options["company_selector"])
        try:
            audit_options = (
                IntegrityAuditOptions(
                    statement_timeout_ms=options["statement_timeout_ms"],
                    lock_timeout_ms=options["lock_timeout_ms"],
                    detail_limit=options["max_findings"],
                )
                if options["audit"]
                else None
            )
            result = run_integrity_scan(
                domains=options["domains"],
                check_ids=options["check_ids"],
                company_id=company.id if company is not None else None,
                audit_options=audit_options,
            )
        except ValueError as exc:
            raise CommandError(str(exc), returncode=2) from exc
        except (UnknownIntegrityCheckError, UnknownIntegrityDomainError) as exc:
            raise CommandError(str(exc), returncode=2) from exc
        except IntegrityExecutionError as exc:
            raise CommandError(str(exc), returncode=2) from exc

        if options["format"] == "json":
            self.stdout.write(json.dumps(result.as_dict(), sort_keys=True, separators=(",", ":")))
        else:
            self._write_text(result.as_dict())

        if result.summary.errors:
            raise CommandError(
                f"Tenant integrity scan found {result.summary.errors} ERROR finding(s).",
                returncode=1,
            )

    def _resolve_company(self, selector: str | None) -> Company | None:
        if selector is None:
            return None
        try:
            company_id = UUID(selector)
        except ValueError:
            company = Company.objects.filter(code__iexact=selector).first()
        else:
            company = Company.objects.filter(pk=company_id).first()
        if company is None:
            raise CommandError(f"Unknown Company: {selector}", returncode=2)
        return company

    def _write_text(self, payload: dict[str, Any]) -> None:
        summary = payload["summary"]
        self.stdout.write(
            "Tenant integrity scan: "
            f"{summary['total_checks']} checks, {summary['total_findings']} findings "
            f"({summary['errors']} errors, {summary['warnings']} warnings)"
        )
        for finding in payload["findings"]:
            self.stdout.write(
                f"[{finding['severity']}] {finding['check_id']} "
                f"{finding['resource_type']}:{finding['record_id']} "
                f"relation={finding['relation']}"
            )
