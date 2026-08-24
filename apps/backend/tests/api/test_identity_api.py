import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory

pytestmark = pytest.mark.django_db


def _permission(codename: str, app_label: str = "identity") -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _auth(client: APIClient, user: User) -> APIClient:
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def plain_user() -> User:
    return UserFactory.create()


@pytest.fixture
def superuser() -> User:
    return UserFactory.create(is_superuser=True, is_staff=True)


@pytest.fixture
def access_admin_role() -> Role:
    role = RoleFactory.create()
    codes = [
        _permission("view_user"),
        _permission("add_user"),
        _permission("change_user"),
        _permission("manage_roles"),
        _permission("assign_roles"),
        _permission("view_access_matrix"),
        _permission("view_role"),
        _permission("view_userroleassignment"),
    ]
    role.permissions.set(codes)
    return role


@pytest.fixture
def access_admin(access_admin_role: Role) -> User:
    user = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=user, role=access_admin_role, scope_type=AccessScopeType.GLOBAL
    )
    return user


# --------------------------------------------------------------------------
# Users
# --------------------------------------------------------------------------


def test_users_list_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/v1/identity/users/").status_code == 401


def test_plain_user_cannot_list_users(client: APIClient, plain_user: User) -> None:
    _auth(client, plain_user)
    assert client.get("/api/v1/identity/users/").status_code == 403


def test_access_admin_can_list_and_create_users(client: APIClient, access_admin: User) -> None:
    _auth(client, access_admin)
    list_response = client.get("/api/v1/identity/users/")
    assert list_response.status_code == 200

    create_response = client.post(
        "/api/v1/identity/users/",
        {"email": "New.Person@Example.com", "password": "StrongTestPassword123!"},
        format="json",
    )
    assert create_response.status_code == 201
    assert create_response.json()["email"] == "new.person@example.com"
    assert "password" not in create_response.json()


def test_create_user_with_missing_email_returns_field_errors(
    client: APIClient, access_admin: User
) -> None:
    _auth(client, access_admin)
    response = client.post(
        "/api/v1/identity/users/", {"password": "StrongTestPassword123!"}, format="json"
    )
    assert response.status_code == 400
    assert "email" in response.json()


def test_user_cannot_deactivate_self_via_api(client: APIClient, access_admin: User) -> None:
    _auth(client, access_admin)
    response = client.post(f"/api/v1/identity/users/{access_admin.pk}/deactivate/")
    assert response.status_code == 403


def test_non_superuser_cannot_deactivate_superuser_via_api(
    client: APIClient, access_admin: User, superuser: User
) -> None:
    _auth(client, access_admin)
    response = client.post(f"/api/v1/identity/users/{superuser.pk}/deactivate/")
    assert response.status_code == 403


def test_access_admin_can_activate_and_deactivate_other_user(
    client: APIClient, access_admin: User
) -> None:
    target = UserFactory.create()
    _auth(client, access_admin)
    deactivate_response = client.post(f"/api/v1/identity/users/{target.pk}/deactivate/")
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    activate_response = client.post(f"/api/v1/identity/users/{target.pk}/activate/")
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True


def test_set_password_action_works_and_rejects_weak_password(
    client: APIClient, access_admin: User
) -> None:
    target = UserFactory.create()
    _auth(client, access_admin)
    weak_response = client.post(
        f"/api/v1/identity/users/{target.pk}/set-password/",
        {"password": "12345678"},
        format="json",
    )
    assert weak_response.status_code == 400

    strong_response = client.post(
        f"/api/v1/identity/users/{target.pk}/set-password/",
        {"password": "AnotherStrongPassword123!"},
        format="json",
    )
    assert strong_response.status_code == 204


def test_user_patch_rejects_password_field(client: APIClient, access_admin: User) -> None:
    target = UserFactory.create()
    _auth(client, access_admin)
    response = client.patch(
        f"/api/v1/identity/users/{target.pk}/",
        {"password": "NewStrongPassword123!"},
        format="json",
    )
    assert response.status_code == 400


def test_user_delete_is_not_allowed(client: APIClient, access_admin: User) -> None:
    target = UserFactory.create()
    _auth(client, access_admin)
    assert client.delete(f"/api/v1/identity/users/{target.pk}/").status_code == 405


def test_user_list_is_paginated(client: APIClient, access_admin: User) -> None:
    _auth(client, access_admin)
    response = client.get("/api/v1/identity/users/")
    assert response.json().keys() >= {"count", "next", "previous", "results"}


def test_user_list_can_search_by_email(client: APIClient, access_admin: User) -> None:
    UserFactory.create(email="findme-user@example.com")
    _auth(client, access_admin)
    response = client.get("/api/v1/identity/users/?search=findme-user")
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["email"] == "findme-user@example.com"


# --------------------------------------------------------------------------
# Roles
# --------------------------------------------------------------------------


def test_plain_user_cannot_create_role(client: APIClient, plain_user: User) -> None:
    _auth(client, plain_user)
    response = client.post(
        "/api/v1/identity/roles/", {"code": "NEW-ROLE", "name": "New Role"}, format="json"
    )
    assert response.status_code == 403


def test_access_admin_can_create_role_with_permissions(
    client: APIClient, access_admin: User
) -> None:
    view_branch = Permission.objects.get(
        content_type__app_label="organization", codename="view_branch"
    )
    _auth(client, access_admin)
    response = client.post(
        "/api/v1/identity/roles/",
        {"code": "branch-viewer", "name": "Branch Viewer", "permissions": [view_branch.pk]},
        format="json",
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["code"] == "BRANCH-VIEWER"
    assert any(p["codename"] == "view_branch" for p in payload["permissions"])


def test_access_admin_cannot_modify_system_role(client: APIClient, access_admin: User) -> None:
    system_role = RoleFactory.create(is_system=True)
    _auth(client, access_admin)
    response = client.patch(
        f"/api/v1/identity/roles/{system_role.pk}/", {"name": "Renamed"}, format="json"
    )
    assert response.status_code == 403


def test_superuser_can_modify_system_role(client: APIClient, superuser: User) -> None:
    system_role = RoleFactory.create(is_system=True)
    _auth(client, superuser)
    response = client.patch(
        f"/api/v1/identity/roles/{system_role.pk}/", {"name": "Renamed"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"


def test_role_delete_is_not_allowed(client: APIClient, access_admin: User) -> None:
    role = RoleFactory.create()
    _auth(client, access_admin)
    assert client.delete(f"/api/v1/identity/roles/{role.pk}/").status_code == 405


# --------------------------------------------------------------------------
# Role assignments
# --------------------------------------------------------------------------


def test_non_superuser_cannot_create_global_assignment_via_api(
    client: APIClient, access_admin: User
) -> None:
    target_user = UserFactory.create()
    role = RoleFactory.create()
    _auth(client, access_admin)
    response = client.post(
        "/api/v1/identity/role-assignments/",
        {"user": str(target_user.pk), "role": str(role.pk), "scope_type": "GLOBAL"},
        format="json",
    )
    assert response.status_code == 403


def test_superuser_can_create_global_assignment_via_api(client: APIClient, superuser: User) -> None:
    target_user = UserFactory.create()
    role = RoleFactory.create()
    _auth(client, superuser)
    response = client.post(
        "/api/v1/identity/role-assignments/",
        {"user": str(target_user.pk), "role": str(role.pk), "scope_type": "GLOBAL"},
        format="json",
    )
    assert response.status_code == 201


def test_access_admin_can_create_company_scoped_assignment(
    client: APIClient, access_admin: User
) -> None:
    target_user = UserFactory.create()
    role = RoleFactory.create()
    company = CompanyFactory.create()
    _auth(client, access_admin)
    response = client.post(
        "/api/v1/identity/role-assignments/",
        {
            "user": str(target_user.pk),
            "role": str(role.pk),
            "scope_type": "COMPANY",
            "company": str(company.pk),
        },
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["scope_type"] == "COMPANY"


def test_plain_user_cannot_create_assignment(client: APIClient, plain_user: User) -> None:
    target_user = UserFactory.create()
    role = RoleFactory.create()
    company = CompanyFactory.create()
    _auth(client, plain_user)
    response = client.post(
        "/api/v1/identity/role-assignments/",
        {
            "user": str(target_user.pk),
            "role": str(role.pk),
            "scope_type": "COMPANY",
            "company": str(company.pk),
        },
        format="json",
    )
    assert response.status_code == 403


def test_branch_scoped_admin_cannot_grant_company_wide_role_via_api(client: APIClient) -> None:
    branch = BranchFactory.create()
    assign_role = RoleFactory.create()
    assign_role.permissions.set([_permission("assign_roles")])
    actor = UserFactory.create()
    UserRoleAssignmentFactory.create(
        user=actor,
        role=assign_role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    target_user = UserFactory.create()
    granted_role = RoleFactory.create()
    _auth(client, actor)
    response = client.post(
        "/api/v1/identity/role-assignments/",
        {
            "user": str(target_user.pk),
            "role": str(granted_role.pk),
            "scope_type": "COMPANY",
            "company": str(branch.company.pk),
        },
        format="json",
    )
    assert response.status_code == 403


def test_role_assignment_delete_is_not_allowed(client: APIClient, access_admin: User) -> None:
    assignment = UserRoleAssignmentFactory.create()
    _auth(client, access_admin)
    assert client.delete(f"/api/v1/identity/role-assignments/{assignment.pk}/").status_code == 405


# --------------------------------------------------------------------------
# Permissions catalog / access matrix
# --------------------------------------------------------------------------


def test_permission_catalog_requires_authentication(client: APIClient) -> None:
    assert client.get("/api/v1/identity/permissions/").status_code == 401


def test_any_authenticated_user_can_browse_permission_catalog(
    client: APIClient, plain_user: User
) -> None:
    _auth(client, plain_user)
    response = client.get("/api/v1/identity/permissions/?app_label=organization")
    assert response.status_code == 200
    results = response.json()["results"]
    assert all(item["app_label"] == "organization" for item in results)


def test_access_matrix_denied_without_permission(client: APIClient, plain_user: User) -> None:
    _auth(client, plain_user)
    assert client.get("/api/v1/identity/access-matrix/").status_code == 403


def test_access_matrix_returns_role_permission_entries(
    client: APIClient, access_admin: User, access_admin_role: Role
) -> None:
    _auth(client, access_admin)
    response = client.get("/api/v1/identity/access-matrix/")
    assert response.status_code == 200
    codes = {entry["role_code"] for entry in response.json()}
    assert access_admin_role.code in codes
