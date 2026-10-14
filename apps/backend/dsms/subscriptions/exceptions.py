from typing import Any


class SubscriptionDomainError(Exception):
    """Base error for provider-neutral commercial subscription operations."""


class SubscriptionAuthorizationError(SubscriptionDomainError):
    """The actor lacks the required platform capability."""


class SubscriptionConflictError(SubscriptionDomainError):
    """The requested operation conflicts with current commercial state."""


class SubscriptionTransitionError(SubscriptionConflictError):
    """The requested lifecycle transition is not allowed."""


class SubscriptionValidationError(SubscriptionDomainError):
    def __init__(self, errors: dict[str, Any]) -> None:
        self.errors = errors
        super().__init__("Commercial subscription data is invalid.")
