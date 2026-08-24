import pytest
from rest_framework.test import APIClient

from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_bank_api_accepts_but_never_returns_sensitive_account_data() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    created = client.post(
        "/api/v1/finance/domain/bank-accounts/",
        {
            "company": str(company.id),
            "name": "Operating",
            "bank_name": "Test Bank",
            "account_number_encrypted": "ciphertext",
            "ledger_account": str(accounts["bank"].id),
        },
        format="json",
    )
    assert created.status_code == 201
    assert "account_number_encrypted" not in created.data
    assert "iban_encrypted" not in created.data
