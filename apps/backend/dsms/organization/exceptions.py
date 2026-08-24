from typing import Any


class OrganizationError(Exception):
    """Base class for organization domain errors."""


class OrganizationValidationError(OrganizationError):
    """Wraps field-level validation failures raised by model constraints."""

    def __init__(self, errors: dict[str, list[str]] | str) -> None:
        self.errors: dict[str, list[str]] = (
            errors if isinstance(errors, dict) else {"detail": [errors]}
        )
        super().__init__(str(self.errors))


class InactiveRelatedRecordError(OrganizationError):
    """A parent or related record is inactive and cannot receive new children."""


class HierarchyMismatchError(OrganizationError):
    """Related records do not belong to a consistent company/region/branch chain."""


class HierarchyCycleError(OrganizationError):
    """A department parent assignment would create a direct or indirect cycle."""


class ScopeViolationError(OrganizationError):
    """A department's scope is broader than its parent's scope."""


class ActiveChildrenExistError(OrganizationError):
    """Deactivation is blocked because active child records still exist."""


class DuplicateHeadOfficeError(OrganizationError):
    """Only one active head office may exist per company."""


def to_error_dict(exc: OrganizationError) -> dict[str, Any]:
    """Render a domain error as a JSON-serializable payload for API responses."""
    if isinstance(exc, OrganizationValidationError):
        return exc.errors
    return {"detail": [str(exc)]}
