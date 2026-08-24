import pytest
from rest_framework.test import APIClient

from dsms.identity.models import User
from tests.factories.identity import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user() -> User:
    return UserFactory.create(email="login@example.com", password="StrongTestPassword123!")


def test_login_with_correct_credentials_succeeds(client: APIClient, user: User) -> None:
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert "access" in payload
    assert "refresh" in payload


def test_login_normalizes_email_case(client: APIClient, user: User) -> None:
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "LOGIN@EXAMPLE.COM", "password": "StrongTestPassword123!"},
        format="json",
    )
    assert response.status_code == 200


def test_login_with_incorrect_password_fails_generically(client: APIClient, user: User) -> None:
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "WrongPassword123!"},
        format="json",
    )
    assert response.status_code == 401
    assert "password" not in response.json()


def test_login_with_nonexistent_email_fails_generically(client: APIClient) -> None:
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "nobody@example.com", "password": "WhateverPassword123!"},
        format="json",
    )
    assert response.status_code == 401


def test_login_with_nonexistent_email_and_wrong_password_have_same_error_shape(
    client: APIClient, user: User
) -> None:
    missing = client.post(
        "/api/v1/auth/login/",
        {"email": "nobody@example.com", "password": "WhateverPassword123!"},
        format="json",
    )
    wrong = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "WrongPassword123!"},
        format="json",
    )
    assert missing.status_code == wrong.status_code == 401
    assert set(missing.json().keys()) == set(wrong.json().keys())


def test_inactive_user_cannot_log_in(client: APIClient) -> None:
    UserFactory.create(
        email="inactive@example.com", password="StrongTestPassword123!", is_active=False
    )
    response = client.post(
        "/api/v1/auth/login/",
        {"email": "inactive@example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    assert response.status_code == 401


def test_token_refresh_returns_new_access_token(client: APIClient, user: User) -> None:
    login_response = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    refresh_token = login_response.json()["refresh"]
    refresh_response = client.post(
        "/api/v1/auth/refresh/", {"refresh": refresh_token}, format="json"
    )
    assert refresh_response.status_code == 200
    assert "access" in refresh_response.json()


def test_token_verify_accepts_valid_access_token(client: APIClient, user: User) -> None:
    login_response = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    access_token = login_response.json()["access"]
    verify_response = client.post("/api/v1/auth/verify/", {"token": access_token}, format="json")
    assert verify_response.status_code == 200


def test_token_verify_rejects_garbage_token(client: APIClient) -> None:
    response = client.post("/api/v1/auth/verify/", {"token": "not-a-token"}, format="json")
    assert response.status_code == 401


def test_logout_blacklists_refresh_token(client: APIClient, user: User) -> None:
    login_response = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    tokens = login_response.json()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    logout_response = client.post(
        "/api/v1/auth/logout/", {"refresh": tokens["refresh"]}, format="json"
    )
    assert logout_response.status_code == 204

    reuse_response = client.post(
        "/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json"
    )
    assert reuse_response.status_code == 401


def test_me_requires_authentication(client: APIClient) -> None:
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 401


def test_me_returns_current_user(client: APIClient, user: User) -> None:
    login_response = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    access_token = login_response.json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    response = client.get("/api/v1/auth/me/")
    assert response.status_code == 200
    assert response.json()["email"] == "login@example.com"
    assert "password" not in response.json()


def test_me_permissions_and_access_scopes_require_authentication(client: APIClient) -> None:
    assert client.get("/api/v1/auth/me/permissions/").status_code == 401
    assert client.get("/api/v1/auth/me/access-scopes/").status_code == 401


def test_me_access_scopes_returns_summary_shape(client: APIClient, user: User) -> None:
    login_response = client.post(
        "/api/v1/auth/login/",
        {"email": "login@example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    access_token = login_response.json()["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    response = client.get("/api/v1/auth/me/access-scopes/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_superuser"] is False
    assert payload["accessible_company_ids"] == []
    assert payload["assignments"] == []
