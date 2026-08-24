import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.audit.models import AuditCategory
from dsms.audit.services import record_audit_event
from dsms.identity.models import User
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_audit_api_is_read_only_and_restricted() -> None:
    event = record_audit_event(
        action="API_TEST", category=AuditCategory.SYSTEM, summary="API test event."
    )
    ordinary = User.objects.create_user(email="ordinary@example.com", password="safe-password-1")
    client = APIClient()
    client.force_authenticate(ordinary)
    assert client.get("/api/v1/audit/events/").status_code == 403

    admin = User.objects.create_superuser(email="admin@example.com", password="safe-password-1")
    client.force_authenticate(admin)
    assert client.get("/api/v1/audit/events/").status_code == 200
    assert client.get(f"/api/v1/audit/events/{event.id}/").status_code == 200
    assert client.post("/api/v1/audit/events/", {}).status_code == 405
    assert client.patch(f"/api/v1/audit/events/{event.id}/", {}).status_code == 405
    assert client.delete(f"/api/v1/audit/events/{event.id}/").status_code == 405


def test_audit_api_filters_company_and_masks_sensitive_metadata() -> None:
    own_company = CompanyFactory.create()
    other_company = CompanyFactory.create()
    viewer = UserFactory.create()
    role = RoleFactory.create(code="SCOPED_AUDITOR")
    role.permissions.add(Permission.objects.get(codename="view_auditevent"))
    UserRoleAssignmentFactory.create(
        user=viewer, role=role, scope_type="COMPANY", company=own_company
    )
    own = record_audit_event(
        action="OWN_EVENT",
        category=AuditCategory.SYSTEM,
        summary="Own event.",
        company=own_company,
        metadata_safe={"result": "ok"},
    )
    record_audit_event(
        action="OTHER_EVENT",
        category=AuditCategory.SYSTEM,
        summary="Other event.",
        company=other_company,
    )

    client = APIClient()
    client.force_authenticate(viewer)
    response = client.get("/api/v1/audit/events/?action=OWN_EVENT")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["id"] == str(own.id)
    assert response.json()["results"][0]["metadata_safe"] == {}

    role.permissions.add(Permission.objects.get(codename="view_sensitive_audit_metadata"))
    response = client.get(f"/api/v1/audit/events/{own.id}/")
    assert response.status_code == 200
    assert response.json()["metadata_safe"] == {"result": "ok"}
    assert client.get(f"/api/v1/audit/events/?company={other_company.id}").json()["count"] == 0
