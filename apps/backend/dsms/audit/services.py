from collections.abc import Mapping
from typing import Any

from django.utils import timezone

from .models import AuditCategory, AuditEvent, AuditSeverity

_SECRET_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "jwt",
    "otp",
    "pin",
    "credential",
    "api_key",
    "authorization",
    "bank_account",
    "account_number",
    "iban",
    "wallet",
    "cnic",
    "national_identity",
    "biometric",
)


def sanitize_audit_metadata(value: Any) -> Any:
    """Recursively remove secret-bearing keys from audit metadata."""
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_audit_metadata(item)
            for key, item in value.items()
            if not any(fragment in str(key).lower() for fragment in _SECRET_FRAGMENTS)
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_audit_metadata(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _request_values(request_context: Any) -> dict[str, Any]:
    if request_context is None:
        return {}
    meta = getattr(request_context, "META", {})
    forwarded = meta.get("HTTP_X_FORWARDED_FOR", "")
    ip_address = forwarded.split(",")[0].strip() if forwarded else meta.get("REMOTE_ADDR")
    return {
        "request_id": meta.get("HTTP_X_REQUEST_ID", "")[:100],
        "ip_address": ip_address or None,
        "user_agent_summary": meta.get("HTTP_USER_AGENT", "")[:255],
    }


def record_audit_event(
    *,
    action: str,
    category: str,
    summary: str,
    actor_user: Any = None,
    actor_employee: Any = None,
    company: Any = None,
    region: Any = None,
    branch: Any = None,
    source_object: Any = None,
    source_app: str | None = None,
    source_model: str | None = None,
    source_object_id: Any = None,
    object_reference: str = "",
    metadata_safe: Mapping[str, Any] | None = None,
    severity: str = AuditSeverity.INFO,
    success: bool = True,
    reason_code: str | None = None,
    request_context: Any = None,
    correlation_id: str = "",
) -> AuditEvent:
    if source_object is not None:
        meta = source_object._meta
        source_app = source_app or meta.app_label
        source_model = source_model or meta.model_name
        source_object_id = source_object_id or source_object.pk
        company = company or (
            source_object
            if meta.app_label == "organization" and meta.model_name == "company"
            else getattr(source_object, "company", None)
        )
        branch = branch or getattr(source_object, "branch", None)
    request_values = _request_values(request_context)
    return AuditEvent.objects.create(
        occurred_at=timezone.now(),
        actor_user=actor_user,
        actor_employee=actor_employee,
        actor_type="USER" if actor_user else "SYSTEM",
        action=action,
        category=category or AuditCategory.OTHER,
        severity=severity,
        company=company,
        region=region,
        branch=branch,
        source_app=source_app or "system",
        source_model=source_model or "",
        source_object_id=str(source_object_id or ""),
        object_reference=object_reference[:255],
        success=success,
        reason_code=reason_code or "",
        summary=summary[:500],
        metadata_safe=sanitize_audit_metadata(metadata_safe or {}),
        correlation_id=correlation_id[:100],
        **request_values,
    )
