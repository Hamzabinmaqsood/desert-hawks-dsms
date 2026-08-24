from typing import Any


class FinanceError(Exception):
    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__("Finance operation failed")


class FinanceValidationError(FinanceError):
    pass


class InvalidFinanceTransitionError(FinanceError):
    pass


class MakerCheckerError(FinanceError):
    pass


class ClosedPeriodError(FinanceError):
    pass


class PostedRecordImmutableError(FinanceError):
    pass


def to_error_dict(exc: FinanceError) -> dict[str, Any]:
    return exc.detail if isinstance(exc.detail, dict) else {"detail": [str(exc.detail)]}
