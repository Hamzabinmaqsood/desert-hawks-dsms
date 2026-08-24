from typing import Any


class WorkforceError(Exception):
    """Base class for workforce/employee-master domain errors."""


class WorkforceValidationError(WorkforceError):
    """Wraps field-level validation failures raised by model constraints."""

    def __init__(self, errors: dict[str, list[str]] | str) -> None:
        self.errors: dict[str, list[str]] = (
            errors if isinstance(errors, dict) else {"detail": [errors]}
        )
        super().__init__(str(self.errors))


class InactiveRelatedRecordError(WorkforceError):
    """A related record (company, branch, department, designation, user) is inactive."""


class HierarchyMismatchError(WorkforceError):
    """Related records do not belong to a consistent company/branch/department chain."""


class InvalidStatusTransitionError(WorkforceError):
    """The requested employment-status transition is not permitted."""


class UserAlreadyLinkedError(WorkforceError):
    """The target user or employee already has a system-access link."""


def to_error_dict(exc: WorkforceError) -> dict[str, Any]:
    """Render a domain error as a JSON-serializable payload for API responses."""
    if isinstance(exc, WorkforceValidationError):
        return exc.errors
    return {"detail": [str(exc)]}
