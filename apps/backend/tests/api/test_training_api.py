# mypy: disable-error-code="arg-type"
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db


def test_training_dashboard_requires_authentication() -> None:
    assert APIClient().get(reverse("training-dashboard-summary")).status_code == 401


def test_training_dashboard_returns_calculated_totals() -> None:
    user = UserFactory(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(reverse("training-dashboard-summary"))
    assert response.status_code == 200
    assert response.json()["active_courses"] == 0
