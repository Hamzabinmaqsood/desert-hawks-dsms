import pytest
from django.db.utils import DatabaseError
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_readiness_reports_database_and_cache() -> None:
    response = APIClient().get("/api/v1/health/ready/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok", "redis": "ok"}


def test_readiness_reports_cache_unavailable_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_cache(*args: object, **kwargs: object) -> None:
        raise ConnectionError("redis secret")

    monkeypatch.setattr("dsms.common.views.cache.set", unavailable_cache)

    response = APIClient().get("/api/v1/health/ready/")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "ok",
        "redis": "unavailable",
    }
    assert "secret" not in response.content.decode()


def test_readiness_reports_database_unavailable_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable_database(*args: object, **kwargs: object) -> None:
        raise DatabaseError("database secret")

    monkeypatch.setattr("dsms.common.views.connection.cursor", unavailable_database)

    response = APIClient().get("/api/v1/health/ready/")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
        "redis": "ok",
    }
    assert "secret" not in response.content.decode()


def test_readiness_reports_both_dependencies_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable(*args: object, **kwargs: object) -> None:
        raise DatabaseError("host=db password=secret")

    monkeypatch.setattr("dsms.common.views.connection.cursor", unavailable)
    monkeypatch.setattr("dsms.common.views.cache.set", unavailable)
    response = APIClient().get("/api/v1/health/ready/")
    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
        "redis": "unavailable",
    }
    body = response.content.decode().lower()
    assert "password" not in body
    assert "host=db" not in body
