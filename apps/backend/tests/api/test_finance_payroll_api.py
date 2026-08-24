import pytest
from rest_framework.test import APIClient

from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_payroll_component_api_is_scoped_and_has_no_delete() -> None:
    company = CompanyFactory.create()
    _year, _period, accounts = accounting_setup(company)
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    response = client.post(
        "/api/v1/finance/domain/payroll-components/",
        {
            "company": str(company.id),
            "code": "BASIC",
            "name": "Basic",
            "component_type": "EARNING",
            "calculation_type": "FIXED",
            "expense_account": str(accounts["expense"].id),
            "payable_account": str(accounts["payable"].id),
        },
        format="json",
    )
    assert response.status_code == 201
    assert "account_number_encrypted" not in response.data
    assert (
        client.delete(
            f"/api/v1/finance/domain/payroll-components/{response.data['id']}/"
        ).status_code
        == 405
    )
