from django.db import IntegrityError
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from dsms.common.exceptions import safe_exception_handler


def test_safe_exception_handler_hides_integrity_details() -> None:
    response = safe_exception_handler(IntegrityError("constraint secret"), {})

    assert response is not None
    assert response.status_code == 409
    assert response.data == {
        "code": "conflict",
        "detail": "The request conflicts with existing data.",
        "errors": {},
    }


def test_safe_exception_handler_wraps_permission_and_not_found() -> None:
    permission = safe_exception_handler(PermissionDenied(), {})
    missing = safe_exception_handler(NotFound(), {})

    assert permission is not None and permission.status_code == 403
    assert permission.data["code"] == "permission_denied"
    assert missing is not None and missing.status_code == 404
    assert missing.data["code"] == "not_found"


def test_safe_exception_handler_preserves_validation_field_errors() -> None:
    response = safe_exception_handler(ValidationError({"name": ["Required."]}), {})

    assert response is not None
    assert response.status_code == 400
    assert response.data["detail"] == "The request could not be completed."
    assert response.data["name"] == ["Required."]
