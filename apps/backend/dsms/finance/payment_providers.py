from dataclasses import dataclass
from typing import Protocol

from .payment_models import ProviderTransactionStatus, ProviderType


@dataclass(frozen=True)
class PaymentProviderResult:
    provider_reference: str = ""
    status: str = ProviderTransactionStatus.UNKNOWN
    failure_code: str = ""
    safe_failure_message: str = ""


class PaymentProviderAdapter(Protocol):
    def submit_payment(
        self, *, instruction: object, idempotency_key: str
    ) -> PaymentProviderResult: ...

    def query_payment_status(self, *, provider_reference: str) -> PaymentProviderResult: ...


class SuccessfulTestPaymentProvider:
    def submit_payment(self, *, instruction: object, idempotency_key: str) -> PaymentProviderResult:
        return PaymentProviderResult(f"TEST-{idempotency_key}", ProviderTransactionStatus.SUCCEEDED)

    def query_payment_status(self, *, provider_reference: str) -> PaymentProviderResult:
        return PaymentProviderResult(provider_reference, ProviderTransactionStatus.SUCCEEDED)


class TemporaryFailureTestPaymentProvider:
    def submit_payment(self, *, instruction: object, idempotency_key: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            status=ProviderTransactionStatus.FAILED,
            failure_code="TEMPORARY_FAILURE",
            safe_failure_message="Temporary test provider failure.",
        )

    def query_payment_status(self, *, provider_reference: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            provider_reference,
            ProviderTransactionStatus.FAILED,
            "TEMPORARY_FAILURE",
            "Temporary test provider failure.",
        )


class PermanentFailureTestPaymentProvider(TemporaryFailureTestPaymentProvider):
    def submit_payment(self, *, instruction: object, idempotency_key: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            status=ProviderTransactionStatus.FAILED,
            failure_code="PERMANENT_FAILURE",
            safe_failure_message="Permanent test provider failure.",
        )


class PendingThenSuccessTestPaymentProvider:
    def __init__(self) -> None:
        self.queries = 0

    def submit_payment(self, *, instruction: object, idempotency_key: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            f"PENDING-{idempotency_key}", ProviderTransactionStatus.PENDING
        )

    def query_payment_status(self, *, provider_reference: str) -> PaymentProviderResult:
        self.queries += 1
        status = (
            ProviderTransactionStatus.SUCCEEDED
            if self.queries
            else ProviderTransactionStatus.PENDING
        )
        return PaymentProviderResult(provider_reference, status)


class UnknownAfterSubmitTestPaymentProvider:
    def submit_payment(self, *, instruction: object, idempotency_key: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            f"UNKNOWN-{idempotency_key}",
            ProviderTransactionStatus.UNKNOWN,
            "UNKNOWN_AFTER_SUBMIT",
            "Provider outcome is unknown.",
        )

    def query_payment_status(self, *, provider_reference: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            provider_reference,
            ProviderTransactionStatus.UNKNOWN,
            "UNKNOWN",
            "Provider outcome remains unknown.",
        )


class DuplicateProviderReferenceTestProvider(SuccessfulTestPaymentProvider):
    def submit_payment(self, *, instruction: object, idempotency_key: str) -> PaymentProviderResult:
        return PaymentProviderResult("DUPLICATE-REFERENCE", ProviderTransactionStatus.SUCCEEDED)


class DisabledPaymentProvider:
    def submit_payment(self, *, instruction: object, idempotency_key: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            status=ProviderTransactionStatus.FAILED,
            failure_code="PROVIDER_DISABLED",
            safe_failure_message="Payment provider is disabled.",
        )

    def query_payment_status(self, *, provider_reference: str) -> PaymentProviderResult:
        return PaymentProviderResult(
            provider_reference,
            ProviderTransactionStatus.UNKNOWN,
            "PROVIDER_DISABLED",
            "Payment provider is disabled.",
        )


class EasypaisaPaymentProvider(DisabledPaymentProvider):
    """Production boundary only; activation requires official merchant API specifications."""


def configured_adapter(configuration: object) -> PaymentProviderAdapter:
    adapter_code = getattr(configuration, "adapter_code", "")
    if getattr(configuration, "provider_type", "") == ProviderType.EASYPAISA:
        return EasypaisaPaymentProvider()
    adapters: dict[str, type[PaymentProviderAdapter]] = {
        "TEST_SUCCESS": SuccessfulTestPaymentProvider,
        "TEST_TEMPORARY_FAILURE": TemporaryFailureTestPaymentProvider,
        "TEST_PERMANENT_FAILURE": PermanentFailureTestPaymentProvider,
        "TEST_PENDING_SUCCESS": PendingThenSuccessTestPaymentProvider,
        "TEST_UNKNOWN": UnknownAfterSubmitTestPaymentProvider,
        "TEST_DUPLICATE_REFERENCE": DuplicateProviderReferenceTestProvider,
    }
    adapter = adapters.get(adapter_code)
    return (
        adapter()
        if adapter and getattr(configuration, "is_active", False)
        else DisabledPaymentProvider()
    )
