from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .types import IntegrityFinding, IntegrityScanScope, IntegritySeverity

IntegrityScanner = Callable[[IntegrityScanScope], Iterable[IntegrityFinding]]


class DuplicateIntegrityCheckError(ValueError):
    pass


class UnknownIntegrityCheckError(ValueError):
    pass


class UnknownIntegrityDomainError(ValueError):
    pass


@dataclass(frozen=True)
class IntegrityCheck:
    check_id: str
    domain: str
    description: str
    severity: IntegritySeverity
    scanner: IntegrityScanner


class IntegrityCheckRegistry:
    def __init__(self, checks: Iterable[IntegrityCheck] = ()) -> None:
        self._checks: dict[str, IntegrityCheck] = {}
        for check in checks:
            self.register(check)

    def register(self, check: IntegrityCheck) -> None:
        if check.check_id in self._checks:
            raise DuplicateIntegrityCheckError(
                f"Integrity check ID is already registered: {check.check_id}"
            )
        self._checks[check.check_id] = check

    @property
    def checks(self) -> tuple[IntegrityCheck, ...]:
        return tuple(self._checks[key] for key in sorted(self._checks))

    @property
    def domains(self) -> tuple[str, ...]:
        return tuple(sorted({check.domain for check in self._checks.values()}))

    def select(
        self,
        *,
        check_ids: Iterable[str] | None = None,
        domains: Iterable[str] | None = None,
    ) -> tuple[IntegrityCheck, ...]:
        requested_ids = set(check_ids or ())
        requested_domains = set(domains or ())
        unknown_ids = requested_ids - self._checks.keys()
        if unknown_ids:
            raise UnknownIntegrityCheckError(
                f"Unknown integrity check ID(s): {', '.join(sorted(unknown_ids))}"
            )
        unknown_domains = requested_domains - set(self.domains)
        if unknown_domains:
            raise UnknownIntegrityDomainError(
                f"Unknown integrity domain(s): {', '.join(sorted(unknown_domains))}"
            )

        selected = self.checks
        if requested_ids:
            selected = tuple(check for check in selected if check.check_id in requested_ids)
        if requested_domains:
            selected = tuple(check for check in selected if check.domain in requested_domains)
        return selected
