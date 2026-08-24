# mypy: disable-error-code="arg-type"
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db


def test_supervision_dashboard_requires_authentication_and_returns_live_counts() -> None:
    url = reverse("supervision-dashboard-summary")
    assert APIClient().get(url).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True))
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["today_planned_visits"] == 0
    assert "overdue_corrective_actions" in response.json()


def test_supervision_resources_do_not_expose_delete() -> None:
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True))
    assert client.delete("/api/v1/supervision/assignments/not-a-uuid/").status_code == 405
