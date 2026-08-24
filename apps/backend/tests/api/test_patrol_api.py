# mypy: disable-error-code="arg-type"
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db


def test_patrol_dashboard_is_private_and_uses_live_aggregates() -> None:
    url = reverse("patrol-dashboard-summary")
    assert APIClient().get(url).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True))
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["scheduled"] == 0
    assert "checkpoint_failures" in response.json()


def test_patrol_history_has_no_delete_api() -> None:
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True))
    assert client.delete("/api/v1/patrol/runs/not-a-uuid/").status_code == 405
