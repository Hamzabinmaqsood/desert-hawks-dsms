import pytest
from rest_framework.test import APIClient

from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_vendor_api_redacts_bank_details() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    response = client.post(
        "/api/v1/finance/domain/vendors/",
        {
            "company": str(company.id),
            "code": "V-API",
            "name": "Vendor API",
            "payable_account": str(accounts["payable"].id),
            "bank_details_encrypted": "ciphertext",
        },
        format="json",
    )
    assert response.status_code == 201
    assert "bank_details_encrypted" not in response.data
    assert client.get("/api/v1/finance/domain/vendors/").status_code == 200
