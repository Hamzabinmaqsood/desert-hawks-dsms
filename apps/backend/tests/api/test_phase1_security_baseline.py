import pytest
from rest_framework.test import APIClient

from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db

PROTECTED_ROUTES = [
    "/api/v1/finance/accounts/",
    "/api/v1/billing/invoices/",
    "/api/v1/assets/assets/",
    "/api/v1/analytics/metrics/",
    "/api/v1/audit/events/",
    "/api/v1/workforce/employees/",
]


@pytest.mark.parametrize("path", PROTECTED_ROUTES)
def test_representative_internal_routes_reject_anonymous(path: str) -> None:
    response = APIClient().get(path)
    assert response.status_code in {401, 403}
    assert "traceback" not in response.content.decode().lower()


@pytest.mark.parametrize("path", PROTECTED_ROUTES)
def test_external_style_authenticated_user_has_no_implicit_internal_access(path: str) -> None:
    user = UserFactory.create()
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(path)
    assert response.status_code == 403
    assert "database" not in response.content.decode().lower()
