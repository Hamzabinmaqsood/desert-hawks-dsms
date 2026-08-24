# mypy: disable-error-code="arg-type"
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db


def test_attendance_dashboard_private_and_has_no_automatic_payroll_or_tracking() -> None:
    assert APIClient().get(reverse("attendance-dashboard-summary")).status_code == 401
    user = UserFactory(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    payload = client.get(reverse("attendance-dashboard-summary")).json()
    assert payload["payroll_posted"] is False
    assert payload["continuous_gps_tracking"] is False
