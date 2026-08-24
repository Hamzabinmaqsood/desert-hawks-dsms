import pytest
from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from dsms.audit.admin import AuditEventAdmin
from dsms.audit.models import AuditCategory, AuditEvent
from dsms.audit.services import record_audit_event, sanitize_audit_metadata
from dsms.identity.models import User
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_record_event_filters_secret_metadata() -> None:
    actor = User.objects.create_user(email="auditor@example.com", password="safe-password-1")
    event = record_audit_event(
        action="TEST_ACTION",
        category=AuditCategory.SYSTEM,
        summary="Safe test event.",
        actor_user=actor,
        metadata_safe={
            "operation": "test",
            "password": "never-store",
            "nested": {"access_token": "never-store", "result": "ok"},
            "bank_account_number": "123456789",
            "wallet_number": "03001234567",
        },
    )
    assert event.metadata_safe == {"operation": "test", "nested": {"result": "ok"}}


def test_event_cannot_be_updated_or_deleted() -> None:
    event = record_audit_event(
        action="IMMUTABLE", category=AuditCategory.SYSTEM, summary="Immutable event."
    )
    event.summary = "Changed"
    with pytest.raises(ValidationError, match="immutable"):
        event.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        event.delete()
    with pytest.raises(ValidationError, match="immutable"):
        AuditEvent.objects.filter(pk=event.pk).update(summary="Changed")
    with pytest.raises(ValidationError, match="cannot be deleted"):
        AuditEvent.objects.filter(pk=event.pk).delete()
    event.summary = "Bulk changed"
    with pytest.raises(ValidationError, match="immutable"):
        AuditEvent.objects.bulk_update([event], ["summary"])
    assert AuditEvent.objects.filter(pk=event.pk, summary="Immutable event.").exists()


def test_metadata_sanitization_is_recursive_and_preserves_safe_business_text() -> None:
    sensitive_keys = [
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "credential",
        "authorization",
        "bank_account",
        "iban",
        "wallet",
        "cnic",
        "biometric",
    ]
    payload = {
        "safe": "ordinary operational description",
        "nested": {"safe": "value", **{key: "remove" for key in sensitive_keys}},
        "items": [
            {"bank_account": "remove", "label": "safe"},
            {"description": "The token counter was inspected safely"},
        ],
    }
    sanitized = sanitize_audit_metadata(payload)
    assert sanitized["safe"] == "ordinary operational description"
    assert sanitized["nested"] == {"safe": "value"}
    assert sanitized["items"] == [
        {"label": "safe"},
        {"description": "The token counter was inspected safely"},
    ]


def test_event_records_actor_source_scope_request_and_ordering(rf: RequestFactory) -> None:
    company = CompanyFactory.create()
    actor = User.objects.create_user(email="scope@example.com", password="safe-password-1")
    request = rf.get(
        "/",
        HTTP_X_FORWARDED_FOR="192.0.2.10, 10.0.0.1",
        HTTP_X_REQUEST_ID="request-1",
        HTTP_USER_AGENT="safe-agent",
    )
    first = record_audit_event(
        action="FIRST",
        category=AuditCategory.SYSTEM,
        summary="First",
        actor_user=actor,
        source_object=company,
        request_context=request,
    )
    second = record_audit_event(
        action="SECOND", category=AuditCategory.SYSTEM, summary="Second", company=company
    )
    assert first.actor_type == "USER"
    assert first.source_app == "organization"
    assert first.source_model == "company"
    assert first.source_object_id == str(company.id)
    assert first.company == company
    assert first.ip_address == "192.0.2.10"
    assert first.request_id == "request-1"
    assert list(AuditEvent.objects.values_list("id", flat=True)[:2]) == [second.id, first.id]


def test_audit_admin_denies_all_mutation(rf: RequestFactory) -> None:
    request = rf.get("/admin/audit/auditevent/")
    admin = AuditEventAdmin(AuditEvent, AdminSite())
    event = record_audit_event(
        action="ADMIN_TEST", category=AuditCategory.SYSTEM, summary="Admin guard"
    )
    assert admin.has_add_permission(request) is False
    assert admin.has_change_permission(request, event) is False
    assert admin.has_delete_permission(request, event) is False
