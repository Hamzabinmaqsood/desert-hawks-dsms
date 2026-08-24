from typing import Any


class DocumentError(Exception):
    def __init__(self, detail: Any) -> None:
        self.detail = detail
        super().__init__("Document operation failed")


class DocumentValidationError(DocumentError):
    pass


class InvalidDocumentTransitionError(DocumentError):
    pass


class ProtectedSystemDocumentTypeError(DocumentError):
    pass


def to_error_dict(exc: DocumentError) -> dict[str, Any]:
    if isinstance(exc.detail, dict):
        return exc.detail
    return {"detail": [str(exc.detail)]}
