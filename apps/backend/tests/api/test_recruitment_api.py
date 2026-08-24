# mypy: disable-error-code="arg-type"
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db


def test_recruitment_dashboard_requires_authentication() -> None:
    response = APIClient().get(reverse("recruitment-dashboard-summary"))
    assert response.status_code == 401


def test_recruitment_dashboard_returns_real_counts() -> None:
    user = UserFactory(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(reverse("recruitment-dashboard-summary"))
    assert response.status_code == 200
    assert response.json()["open_vacancies"] == 0
    assert response.json()["hired"] == 0
