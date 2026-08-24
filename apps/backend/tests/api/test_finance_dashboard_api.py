import pytest
from rest_framework.test import APIClient

from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def test_all_dashboard_sections_are_real_scoped_endpoints() -> None:
    company = CompanyFactory.create()
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    for section in [
        "summary",
        "payroll",
        "expenses",
        "procurement",
        "payables",
        "cash-and-bank",
        "budget",
        "approvals",
        "exceptions",
    ]:
        response = client.get(f"/api/v1/finance/dashboard/{section}/?company={company.id}")
        assert response.status_code == 200


def test_dashboard_rejects_anonymous_access() -> None:
    company = CompanyFactory.create()
    assert (
        APIClient().get(f"/api/v1/finance/dashboard/summary/?company={company.id}").status_code
        == 401
    )
