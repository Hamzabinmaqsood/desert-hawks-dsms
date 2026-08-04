from unittest.mock import patch

from django.db import DatabaseError
from rest_framework.test import APIClient


def test_health_returns_service_unavailable_when_database_fails() -> None:
    client = APIClient()

    with patch(
        "dsms.common.views.connection.cursor",
        side_effect=DatabaseError("Database unavailable"),
    ):
        response = client.get("/api/v1/health/")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
    }
