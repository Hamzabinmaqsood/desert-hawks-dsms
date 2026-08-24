from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.documents.enums import DocumentStatus
from dsms.documents.models import EmployeeDocumentVersion
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from tests.factories.documents import DocumentTypeFactory, EmployeeDocumentFactory
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n% safe API test\n%%EOF"


@pytest.fixture(autouse=True)
def private_storage(settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def superuser() -> User:
    return UserFactory.create(is_superuser=True, is_staff=True)


def grant(user: User, permissions: list[str], branch) -> None:  # type: ignore[no-untyped-def]
    role = RoleFactory.create()
    role.permissions.set(
        Permission.objects.filter(content_type__app_label="documents", codename__in=permissions)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )


def test_document_api_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/v1/documents/employee-documents/").status_code == 401


def test_superuser_create_upload_workflow_and_secure_download(
    client: APIClient, superuser: User
) -> None:
    employee = EmployeeFactory.create()
    kind = DocumentTypeFactory.create(
        code="CNIC-API", is_sensitive=True, requires_document_number=True
    )
    client.force_authenticate(superuser)
    created = client.post(
        "/api/v1/documents/employee-documents/",
        {
            "employee": str(employee.id),
            "document_type": str(kind.id),
            "document_number": "35202-1234567-9",
        },
        format="json",
    )
    assert created.status_code == 201
    document_id = created.data["id"]
    uploaded = client.post(
        f"/api/v1/documents/employee-documents/{document_id}/versions/",
        {"file": SimpleUploadedFile("cnic.pdf", PDF, content_type="application/pdf")},
        format="multipart",
    )
    assert uploaded.status_code == 201
    version_id = uploaded.data["id"]
    assert "file" not in uploaded.data and "stored_filename" not in uploaded.data
    assert (
        client.post(f"/api/v1/documents/employee-documents/{document_id}/submit/").status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/documents/employee-documents/{document_id}/verify/").status_code
        == 200
    )
    download = client.get(
        f"/api/v1/documents/employee-documents/{document_id}/versions/{version_id}/download/"
    )
    assert download.status_code == 200
    assert download["Cache-Control"] == "private, no-store"
    assert download["X-Content-Type-Options"] == "nosniff"
    assert client.delete(f"/api/v1/documents/employee-documents/{document_id}/").status_code == 405


def test_ordinary_scoped_reader_gets_masked_number_and_cannot_download(
    client: APIClient,
) -> None:
    branch = BranchFactory.create()
    employee = EmployeeFactory.create(company=branch.company, branch=branch)
    document = EmployeeDocumentFactory.create(
        employee=employee,
        company=branch.company,
        document_type=DocumentTypeFactory.create(is_sensitive=True),
        document_number="35202-1234567-1",
    )
    viewer = UserFactory.create()
    grant(viewer, ["view_employeedocument", "view_employeedocumentversion"], branch)
    client.force_authenticate(viewer)
    response = client.get(f"/api/v1/documents/employee-documents/{document.id}/")
    assert response.status_code == 200
    assert response.data["display_document_number"] == "*****-*******-1"
    assert response.data["document_number"] is None
    assert response.data["notes"] is None


def test_sensitive_permission_reveals_number(client: APIClient) -> None:
    branch = BranchFactory.create()
    employee = EmployeeFactory.create(company=branch.company, branch=branch)
    document = EmployeeDocumentFactory.create(
        employee=employee,
        company=branch.company,
        document_type=DocumentTypeFactory.create(is_sensitive=True),
        document_number="35202-1234567-1",
    )
    user = UserFactory.create()
    grant(user, ["view_employeedocument", "view_sensitive_document_data"], branch)
    client.force_authenticate(user)
    response = client.get(f"/api/v1/documents/employee-documents/{document.id}/")
    assert response.data["document_number"] == "35202-1234567-1"


def test_cross_branch_document_and_download_do_not_leak(client: APIClient) -> None:
    allowed = BranchFactory.create()
    hidden = BranchFactory.create()
    document = EmployeeDocumentFactory.create(
        employee=EmployeeFactory.create(company=hidden.company, branch=hidden),
        company=hidden.company,
    )
    user = UserFactory.create()
    grant(
        user,
        ["view_employeedocument", "download_employee_document"],
        allowed,
    )
    client.force_authenticate(user)
    assert client.get(f"/api/v1/documents/employee-documents/{document.id}/").status_code == 404
    fake_version = "00000000-0000-0000-0000-000000000001"
    url = f"/api/v1/documents/employee-documents/{document.id}/versions/{fake_version}/download/"
    assert client.get(url).status_code == 404
    assert (
        client.get(
            f"/api/v1/documents/employees/{document.employee_id}/compliance-summary/"
        ).status_code
        == 404
    )


def test_expiry_reports_and_compliance_summary(client: APIClient, superuser: User) -> None:
    employee = EmployeeFactory.create()
    EmployeeDocumentFactory.create(
        employee=employee,
        company=employee.company,
        expires_on=timezone.localdate() + timedelta(days=7),
        status=DocumentStatus.VERIFIED,
    )
    EmployeeDocumentFactory.create(
        employee=employee,
        company=employee.company,
        expires_on=timezone.localdate() - timedelta(days=1),
    )
    client.force_authenticate(superuser)
    expiring = client.get("/api/v1/documents/employee-documents/expiring/?days=7")
    expired = client.get("/api/v1/documents/employee-documents/expired/")
    summary = client.get(f"/api/v1/documents/employees/{employee.id}/compliance-summary/")
    assert expiring.status_code == expired.status_code == summary.status_code == 200
    assert expiring.data["count"] == 1 and expired.data["count"] == 1
    assert summary.data["total_documents"] == 2
    assert summary.data["missing_required_documents"] is None
    assert summary.data["compliance_determined"] is False


def test_private_file_has_no_public_media_route(client: APIClient, superuser: User) -> None:
    document = EmployeeDocumentFactory.create()
    client.force_authenticate(superuser)
    response = client.post(
        f"/api/v1/documents/employee-documents/{document.id}/versions/",
        {"file": SimpleUploadedFile("proof.pdf", PDF)},
        format="multipart",
    )
    version = EmployeeDocumentVersion.objects.get(pk=response.data["id"])
    assert client.get(f"/media/{version.file.name}").status_code == 404


def test_expiring_days_validation(client: APIClient, superuser: User) -> None:
    client.force_authenticate(superuser)
    assert client.get("/api/v1/documents/employee-documents/expiring/?days=0").status_code == 400
    assert client.get("/api/v1/documents/employee-documents/expiring/?days=nope").status_code == 400
