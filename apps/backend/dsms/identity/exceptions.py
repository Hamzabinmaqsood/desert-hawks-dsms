from typing import Any


class IdentityError(Exception):
    """Base class for identity/RBAC domain errors."""


class IdentityValidationError(IdentityError):
    """Wraps field-level validation failures raised by model constraints."""

    def __init__(self, errors: dict[str, list[str]] | str) -> None:
        self.errors: dict[str, list[str]] = (
            errors if isinstance(errors, dict) else {"detail": [errors]}
        )
        super().__init__(str(self.errors))


class InactiveRelatedRecordError(IdentityError):
    """A related record (user, role, company, scope target) is inactive."""


class HierarchyMismatchError(IdentityError):
    """Related records do not belong to a consistent company/scope chain."""


class DuplicateAssignmentError(IdentityError):
    """An equivalent active role assignment already exists."""


class SystemRoleProtectedError(IdentityError):
    """System roles cannot be modified through normal (non-superuser) channels."""


class ScopeAuthorizationError(IdentityError):
    """The acting user is not permitted to grant the requested access."""


class SelfDeactivationError(IdentityError):
    """A user cannot deactivate their own account through this API."""


class SuperuserProtectionError(IdentityError):
    """A non-superuser cannot deactivate a superuser account."""


def to_error_dict(exc: IdentityError) -> dict[str, Any]:
    """Render a domain error as a JSON-serializable payload for API responses."""
    if isinstance(exc, IdentityValidationError):
        return exc.errors
    return {"detail": [str(exc)]}
