from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from rest_framework.response import Response
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User, UserRoleAssignment
from dsms.organization.models import Branch, Company
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory, RegionFactory

pytestmark = pytest.mark.django_db

CONTEXT_URL = "/api/v1/auth/company-context/"
BRANDING_URL = "/api/v1/auth/company-branding/"


def grant_company(user: User, company: Company, *permissions: str) -> UserRoleAssignment:
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


def select(client: APIClient, company: Company) -> Response:
    return client.put(CONTEXT_URL, {"company_id": company.id}, format="json")


def test_a_only_receives_selected_a_branding_and_cannot_supply_b_as_authority() -> None:
    company_a = CompanyFactory.create(
        code="A",
        trade_name="Alpha Shield",
        brand_tagline="Alpha operations",
        brand_primary_color="#123456",
        brand_accent_color="#ABCDEF",
    )
    company_b = CompanyFactory.create(code="B", trade_name="Bravo Guard")
    user = UserFactory.create()
    grant_company(user, company_a, "view_company")
    client = authenticated_client(user)

    context = client.get(CONTEXT_URL)
    assert context.status_code == 200
    assert context.data["selected_company"]["id"] == str(company_a.id)
    assert context.data["selected_company"]["branding"] == {
        "display_name": "Alpha Shield",
        "tagline": "Alpha operations",
        "primary_color": "#123456",
        "accent_color": "#ABCDEF",
        "can_manage": False,
    }
    assert "branding" not in context.data["companies"][0]
    assert select(client, company_b).status_code == 404
    response = client.patch(
        BRANDING_URL,
        {"company_id": str(company_b.id), "display_name": "Hijacked"},
        format="json",
    )
    assert response.status_code == 403
    company_b.refresh_from_db()
    assert company_b.trade_name == "Bravo Guard"


def test_b_only_branding_is_symmetric_and_defaults_are_stable() -> None:
    company_a = CompanyFactory.create(code="A")
    company_b = CompanyFactory.create(code="B", legal_name="Bravo Limited", trade_name="")
    user = UserFactory.create()
    grant_company(user, company_b, "view_company")
    client = authenticated_client(user)

    response = client.get(BRANDING_URL)
    assert response.status_code == 200
    assert response.data == {
        "display_name": "Bravo Limited",
        "tagline": "Digital Transformation System",
        "primary_color": "#174D34",
        "accent_color": "#D6A84F",
        "can_manage": False,
    }
    assert select(client, company_a).status_code == 404


def test_a_b_switch_replaces_branding_without_exposing_unselected_branding() -> None:
    company_a = CompanyFactory.create(code="A", trade_name="Alpha", brand_tagline="A only")
    company_b = CompanyFactory.create(code="B", trade_name="Bravo", brand_tagline="B only")
    user = UserFactory.create()
    grant_company(user, company_a, "view_company")
    grant_company(user, company_b, "view_company")
    client = authenticated_client(user)

    initial = client.get(CONTEXT_URL)
    assert initial.data["selected_company"] is None
    assert all("branding" not in row for row in initial.data["companies"])

    selected_a = select(client, company_a)
    assert selected_a.data["selected_company"]["branding"]["display_name"] == "Alpha"
    selected_b = select(client, company_b)
    assert selected_b.data["selected_company"]["branding"]["display_name"] == "Bravo"
    assert selected_b.data["selected_company"]["branding"]["tagline"] == "B only"
    assert "A only" not in str(selected_b.data)


def test_split_permission_can_edit_b_but_not_a() -> None:
    company_a = CompanyFactory.create(code="A", trade_name="Alpha")
    company_b = CompanyFactory.create(code="B", trade_name="Bravo")
    user = UserFactory.create()
    grant_company(user, company_a, "view_company")
    grant_company(user, company_b, "view_company", "change_company")
    client = authenticated_client(user)

    assert select(client, company_a).status_code == 200
    denied = client.patch(BRANDING_URL, {"display_name": "Wrong"}, format="json")
    assert denied.status_code == 403

    assert select(client, company_b).status_code == 200
    allowed = client.patch(
        BRANDING_URL,
        {
            "display_name": "  Bravo Response  ",
            "tagline": "  Always ready  ",
            "primary_color": "#a1b2c3",
            "accent_color": "#d4e5f6",
        },
        format="json",
    )
    assert allowed.status_code == 200
    assert allowed.data["display_name"] == "Bravo Response"
    assert allowed.data["primary_color"] == "#A1B2C3"
    assert allowed.data["accent_color"] == "#D4E5F6"
    assert allowed.data["can_manage"] is True
    company_a.refresh_from_db()
    company_b.refresh_from_db()
    assert company_a.trade_name == "Alpha"
    assert company_b.trade_name == "Bravo Response"
    assert company_b.brand_tagline == "Always ready"


@pytest.mark.parametrize(
    "field,value",
    [
        ("primary_color", "red"),
        ("primary_color", "url(https://attacker.test/x)"),
        ("accent_color", "#12345;"),
        ("accent_color", "javascript:alert(1)"),
    ],
)
def test_css_injection_payloads_are_rejected(field: str, value: str) -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    grant_company(user, company, "view_company", "change_company")
    response = authenticated_client(user).patch(BRANDING_URL, {field: value}, format="json")
    assert response.status_code == 400
    company.refresh_from_db()
    assert company.brand_primary_color == ""
    assert company.brand_accent_color == ""


def test_unsupported_owner_and_script_fields_are_rejected() -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    grant_company(user, company, "view_company", "change_company")
    client = authenticated_client(user)

    for payload in (
        {"company_id": str(uuid4())},
        {"custom_css": "body { display: none }"},
        {"logo_path": "../../secret"},
    ):
        response = client.patch(BRANDING_URL, payload, format="json")
        assert response.status_code == 400


def test_revoked_or_inactive_selected_company_branding_fails_closed() -> None:
    company = CompanyFactory.create(trade_name="Active Brand")
    user = UserFactory.create()
    assignment = grant_company(user, company, "view_company")
    client = authenticated_client(user)
    assert client.get(BRANDING_URL).status_code == 200

    assignment.is_active = False
    assignment.save(update_fields=["is_active"])
    assert client.get(BRANDING_URL).status_code == 404

    assignment.is_active = True
    assignment.save(update_fields=["is_active"])
    assert client.get(BRANDING_URL).status_code == 200
    company.is_active = False
    company.save(update_fields=["is_active"])
    assert client.get(BRANDING_URL).status_code == 404


def test_corrupt_assignment_and_selected_branding_do_not_weaken_resource_authorization() -> None:
    company_a = CompanyFactory.create(code="A", trade_name="Alpha")
    company_b = CompanyFactory.create(code="B", trade_name="Bravo")
    region_a = RegionFactory.create(company=company_a)
    branch_a = BranchFactory.create(company=company_a, region=region_a)
    user = UserFactory.create()
    for company in (company_a, company_b):
        grant_company(user, company, "view_company", "add_branch")
    client = authenticated_client(user)
    assert select(client, company_b).status_code == 200

    mixed = client.post(
        "/api/v1/organization/branches/",
        {
            "company": str(company_b.id),
            "region": str(region_a.id),
            "city": str(branch_a.city_id),
            "code": "MIXED-BRAND",
            "name": "Mixed relation probe",
            "address_line_1": "Test",
        },
        format="json",
    )
    assert mixed.status_code == 400
    assert not Branch.objects.filter(company=company_b, code="MIXED-BRAND").exists()

    corrupt_user = UserFactory.create()
    role = RoleFactory.create(company=None)
    corrupt_assignment = UserRoleAssignmentFactory.create(
        user=corrupt_user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=company_a,
        branch=branch_a,
    )
    UserRoleAssignment.objects.filter(pk=corrupt_assignment.pk).update(company=company_b)
    assert authenticated_client(corrupt_user).get(BRANDING_URL).status_code == 404
