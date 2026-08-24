import logging
from typing import Any

from django.db import IntegrityError
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def safe_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Return a stable API error envelope without leaking infrastructure details."""
    if isinstance(exc, IntegrityError):
        logger.warning("Database integrity error", exc_info=True)
        return Response(
            {
                "code": "conflict",
                "detail": "The request conflicts with existing data.",
                "errors": {},
            },
            status=409,
        )
    response = exception_handler(exc, context)
    if response is None:
        return None
    original = response.data
    if isinstance(original, dict) and set(original) == {"detail"}:
        detail = str(original["detail"])
        errors: Any = {}
    else:
        detail = "The request could not be completed."
        errors = original
    code = getattr(exc, "default_code", None) or "error"
    envelope = {"code": str(code), "detail": detail, "errors": errors}
    # Preserve the established top-level serializer field errors during the
    # transition to the common envelope so existing API clients do not break.
    if isinstance(errors, dict):
        envelope.update(errors)
    response.data = envelope
    return response
