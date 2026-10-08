from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.identity.company_context import SELECTED_COMPANY_SESSION_KEY
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User, UserRoleAssignment
from dsms.organization.models import Branch
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory, RegionFactory

pytestmark = pytest.mark.django_db

CONTEXT_URL = "/api/v1/auth/company-context/"


def grant_company(user: User, company, *permissions: str) -> UserRoleAssignment:  # type: ignore[no-untyped-def]
    role = RoleFactory.create(company=company)
    if permissions:
        role.permissions.set(
            Permission.objects.filter(
                content_type__app_label="organization", codename__in=permissions
            )
        )
    return UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def authenticated_client(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def selected_id(response) -> str | None:  # type: ignore[no-untyped-def]
    selected = response.data["selected_company"]
    return selected["id"] if selected else None


def test_a_only_lists_and_selects_a_but_does_not_enumerate_b_or_inactive_c() -> None:
    company_a = CompanyFactory.create(code="A")
    company_b = CompanyFactory.create(code="B")
    company_c = CompanyFactory.create(code="C", is_active=False)
    user = UserFactory.create()
    grant_company(user, company_a, "view_company")
    client = authenticated_client(user)

    context = client.get(CONTEXT_URL)
    assert context.status_code == 200
    assert [row["id"] for row in context.data["companies"]] == [str(company_a.id)]
    assert selected_id(context) == str(company_a.id)
    assert context.data["selection_required"] is False
    assert client.get(f"/api/v1/organization/companies/{company_b.id}/").status_code == 404
    for company_id in (company_b.id, company_c.id, uuid4()):
        response = client.put(CONTEXT_URL, {"company_id": company_id}, format="json")
        assert response.status_code == 404
    assert selected_id(client.get(CONTEXT_URL)) == str(company_a.id)


def test_b_only_is_symmetric() -> None:
    company_a = CompanyFactory.create(code="A")
    company_b = CompanyFactory.create(code="B")
    user = UserFactory.create()
    grant_company(user, company_b)
    client = authenticated_client(user)

    context = client.get(CONTEXT_URL)
    assert [row["id"] for row in context.data["companies"]] == [str(company_b.id)]
    assert selected_id(context) == str(company_b.id)
    assert client.put(CONTEXT_URL, {"company_id": company_a.id}, format="json").status_code == 404


def test_multiple_companies_require_explicit_selection_and_can_switch() -> None:
    company_a = CompanyFactory.create(code="A")
    company_b = CompanyFactory.create(code="B")
    user = UserFactory.create()
    grant_company(user, company_a)
    grant_company(user, company_b)
    client = authenticated_client(user)

    initial = client.get(CONTEXT_URL)
    assert [row["id"] for row in initial.data["companies"]] == [
        str(company_a.id),
        str(company_b.id),
    ]
    assert selected_id(initial) is None
    assert initial.data["selection_required"] is True

    selected_a = client.put(CONTEXT_URL, {"company_id": company_a.id}, format="json")
    assert selected_a.status_code == 200
    assert selected_id(selected_a) == str(company_a.id)
    assert selected_id(client.get(CONTEXT_URL)) == str(company_a.id)

    selected_b = client.put(CONTEXT_URL, {"company_id": company_b.id}, format="json")
    assert selected_b.status_code == 200
    assert selected_id(selected_b) == str(company_b.id)
    assert selected_id(client.get(CONTEXT_URL)) == str(company_b.id)


def test_authenticated_user_with_no_company_has_safe_context() -> None:
    user = UserFactory.create()
    response = authenticated_client(user).get(CONTEXT_URL)
    assert response.status_code == 200
    assert response.data["user"]["id"] == str(user.id)
    assert response.data["companies"] == []
    assert response.data["selected_company"] is None
    assert response.data["selection_required"] is False


def test_revoked_membership_clears_stale_selection() -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    assignment = grant_company(user, company)
    client = authenticated_client(user)
    assert selected_id(client.get(CONTEXT_URL)) == str(company.id)

    assignment.is_active = False
    assignment.save(update_fields=["is_active"])
    response = client.get(CONTEXT_URL)
    assert response.data["companies"] == []
    assert response.data["selected_company"] is None
    assert SELECTED_COMPANY_SESSION_KEY not in client.session


def test_inactive_company_clears_stale_selection() -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    grant_company(user, company)
    client = authenticated_client(user)
    assert selected_id(client.get(CONTEXT_URL)) == str(company.id)

    company.is_active = False
    company.save(update_fields=["is_active"])
    response = client.get(CONTEXT_URL)
    assert response.data["companies"] == []
    assert response.data["selected_company"] is None


def test_corrupt_assignment_does_not_make_company_selectable() -> None:
    branch_a = BranchFactory.create()
    company_b = CompanyFactory.create()
    user = UserFactory.create()
    role = RoleFactory.create(company=None)
    assignment = UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch_a.company,
        branch=branch_a,
    )
    UserRoleAssignment.objects.filter(pk=assignment.pk).update(company=company_b)

    response = authenticated_client(user).get(CONTEXT_URL)
    assert response.data["companies"] == []


def test_superuser_can_select_active_companies_only() -> None:
    active = CompanyFactory.create(code="ACTIVE")
    CompanyFactory.create(code="INACTIVE", is_active=False)
    user = UserFactory.create(is_staff=True, is_superuser=True)
    client = authenticated_client(user)

    response = client.get(CONTEXT_URL)
    assert [row["id"] for row in response.data["companies"]] == [str(active.id)]
    assert selected_id(response) == str(active.id)


def test_selected_company_does_not_replace_resource_or_resulting_state_authorization() -> None:
    company_a = CompanyFactory.create(code="A")
    company_b = CompanyFactory.create(code="B")
    region_a = RegionFactory.create(company=company_a)
    branch_a = BranchFactory.create(company=company_a, region=region_a)
    user = UserFactory.create()
    for company in (company_a, company_b):
        grant_company(user, company, "view_company", "add_branch")
    client = authenticated_client(user)

    assert client.put(CONTEXT_URL, {"company_id": company_b.id}, format="json").status_code == 200
    # Selecting B does not revoke legitimate, resource-derived access to A.
    assert client.get(f"/api/v1/organization/companies/{company_a.id}/").status_code == 200
    # Nor does selecting B allow an A-owned relation to be written into B.
    response = client.post(
        "/api/v1/organization/branches/",
        {
            "company": str(company_b.id),
            "region": str(region_a.id),
            "city": str(branch_a.city_id),
            "code": "MIXED",
            "name": "Mixed relation probe",
            "address_line_1": "Test",
        },
        format="json",
    )
    assert response.status_code == 400
    assert not Branch.objects.filter(company=company_b, code="MIXED").exists()


def test_logout_clears_selected_company_session_state() -> None:
    company = CompanyFactory.create()
    user = UserFactory.create(email="context@example.test")
    grant_company(user, company)
    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"email": user.email, "password": "StrongTestPassword123!"},
        format="json",
    )
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    assert client.get(CONTEXT_URL).status_code == 200
    assert SELECTED_COMPANY_SESSION_KEY in client.session

    logout = client.post("/api/v1/auth/logout/", {"refresh": login.data["refresh"]}, format="json")
    assert logout.status_code == 204
    assert SELECTED_COMPANY_SESSION_KEY not in client.session
