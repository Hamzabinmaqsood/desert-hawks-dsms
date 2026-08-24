# mypy: disable-error-code="no-untyped-def"
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderDeliveryResult:
    provider_message_id: str = ""
    accepted: bool = False
    delivered_if_known: bool = False
    temporary_failure: bool = False
    permanent_failure: bool = False
    error_code: str = ""


class DisabledProvider:
    name = "DISABLED"

    def send(self, **kwargs: Any) -> ProviderDeliveryResult:
        return ProviderDeliveryResult(permanent_failure=True, error_code="PROVIDER_DISABLED")


class TestProvider:
    name = "TEST"

    def __init__(self, result: ProviderDeliveryResult | None = None) -> None:
        self.result = result or ProviderDeliveryResult(accepted=True)

    def send(self, **kwargs: Any) -> ProviderDeliveryResult:
        return self.result


class ConsoleProvider:
    name = "CONSOLE"

    def send(self, **kwargs: Any) -> ProviderDeliveryResult:
        # Intentionally does not print destinations or bodies; console mode records handoff only.
        return ProviderDeliveryResult(accepted=True)


DisabledEmailProvider = DisabledSMSProvider = DisabledPushProvider = DisabledProvider
TestEmailProvider = TestSMSProvider = TestPushProvider = TestProvider
ConsoleEmailProvider = ConsoleSMSProvider = ConsoleProvider
