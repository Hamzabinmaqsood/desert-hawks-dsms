from typing import Any


class TenantProvisioningError(Exception):
    """Base class for safe tenant-provisioning failures."""


class TenantProvisioningAuthorizationError(TenantProvisioningError):
    """The actor is not an active platform provisioning authority."""


class TenantProvisioningConflictError(TenantProvisioningError):
    """An idempotency key or unique tenant identity conflicts with prior data."""


class TenantProvisioningConfigurationError(TenantProvisioningError):
    """Required platform bootstrap configuration is unavailable."""


class TenantProvisioningValidationError(TenantProvisioningError):
    """The requested Company or administrator data is invalid."""

    def __init__(self, errors: dict[str, Any]) -> None:
        self.errors = errors
        super().__init__(str(errors))


class InactiveInitialAdminError(TenantProvisioningValidationError):
    """An existing inactive identity cannot silently be reactivated."""
