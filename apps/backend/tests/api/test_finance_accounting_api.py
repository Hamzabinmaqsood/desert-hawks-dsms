from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_journal_api_full_cycle_and_no_delete() -> None:
    company = CompanyFactory.create()
    maker = UserFactory.create(is_superuser=True)
    _checker = UserFactory.create(is_superuser=True)
    year, period, accounts = accounting_setup(company)
    client = APIClient()
    client.force_authenticate(maker)
    response = client.post(
        "/api/v1/finance/journals/",
        {
            "company": str(company.id),
            "fiscal_year": str(year.id),
            "accounting_period": str(period.id),
            "entry_date": "2026-08-18",
            "description": "API journal",
            "lines": [
                {"account": str(accounts["cash"].id), "debit": "25.00"},
                {"account": str(accounts["equity"].id), "credit": "25.00"},
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    journal_id = response.data["id"]
    assert client.post(f"/api/v1/finance/journals/{journal_id}/submit/").status_code == 200
    assert client.post(f"/api/v1/finance/journals/{journal_id}/approve/").status_code == 200
    posted = client.post(f"/api/v1/finance/journals/{journal_id}/post/")
    assert posted.status_code == 200 and Decimal(posted.data["total_debit"]) == Decimal("25")
    assert client.delete(f"/api/v1/finance/journals/{journal_id}/").status_code == 405


def test_finance_accounting_requires_authentication() -> None:
    assert APIClient().get("/api/v1/finance/accounts/").status_code == 401
