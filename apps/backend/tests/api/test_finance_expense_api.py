import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_expense_category_api_create_and_list() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    created = client.post(
        "/api/v1/finance/domain/expense-categories/",
        {
            "company": str(company.id),
            "code": "MEALS",
            "name": "Meals",
            "expense_account": str(accounts["expense"].id),
            "receipt_required": True,
            "receipt_threshold": "100.00",
        },
        format="json",
    )
    assert created.status_code == 201
    listed = client.get("/api/v1/finance/domain/expense-categories/")
    assert listed.status_code == 200 and len(listed.data) == 1


def test_finance_attachment_is_private_and_download_is_hardened(settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private-finance"
    company = CompanyFactory.create()
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    uploaded = client.post(
        "/api/v1/finance/attachments/",
        {
            "company": str(company.id),
            "document_type": "EXPENSE",
            "object_id": str(company.id),
            "file": SimpleUploadedFile(
                "receipt.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"
            ),
        },
        format="multipart",
    )
    assert uploaded.status_code == 201 and "file" not in uploaded.data
    downloaded = client.get(f"/api/v1/finance/attachments/{uploaded.data['id']}/download/")
    assert downloaded.status_code == 200
    assert downloaded["Cache-Control"] == "private, no-store"
    assert downloaded["X-Content-Type-Options"] == "nosniff"
