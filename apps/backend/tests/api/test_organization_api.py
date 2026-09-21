import pytest
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.identity.models import Role, User
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import (
    BranchFactory,
    CityFactory,
    CompanyFactory,
    DepartmentFactory,
    DesignationFactory,
    OperationalZoneFactory,
    RegionFactory,
)

pytestmark = pytest.mark.django_db

_ORG_MODELS = [
    "company",
    "region",
    "city",
    "branch",
    "department",
    "designation",
    "operationalzone",
]


def _org_permissions(verbs: list[str]) -> list[Permission]:
    return [
        Permission.objects.get(content_type__app_label="organization", codename=f"{verb}_{model}")
        for model in _ORG_MODELS
        for verb in verbs
    ]


def _grant_org_role(user: User, *, verbs: list[str], scope_type: str, **scope: object) -> Role:
    role = RoleFactory.create()
    role.permissions.set(_org_permissions(verbs))
    UserRoleAssignmentFactory.create(user=user, role=role, scope_type=scope_type, **scope)
    return role


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _auth(client: APIClient, user: User) -> APIClient:
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def superuser() -> User:
    return UserFactory.create(is_superuser=True, is_staff=True)


@pytest.fixture
def plain_user() -> User:
    return UserFactory.create()


# --------------------------------------------------------------------------
# Authentication / baseline authorization
# --------------------------------------------------------------------------


def test_list_companies_requires_authentication(client: APIClient) -> None:
    response = client.get("/api/v1/organization/companies/")
    assert response.status_code == 401


def test_authenticated_user_without_any_role_is_forbidden(
    client: APIClient, plain_user: User
) -> None:
    CompanyFactory.create()
    _auth(client, plain_user)
    response = client.get("/api/v1/organization/companies/")
    assert response.status_code == 403


def test_superuser_can_list_and_create_company(client: APIClient, superuser: User) -> None:
    _auth(client, superuser)
    create_response = client.post(
        "/api/v1/organization/companies/", {"code": "st1", "legal_name": "Staff Co"}
    )
    assert create_response.status_code == 201
    assert create_response.json()["code"] == "ST1"

    company_id = create_response.json()["id"]
    update_response = client.patch(
        f"/api/v1/organization/companies/{company_id}/", {"legal_name": "Updated Name"}
    )
    assert update_response.status_code == 200
    assert update_response.json()["legal_name"] == "Updated Name"


def test_put_is_not_allowed(client: APIClient, superuser: User) -> None:
    company = CompanyFactory.create()
    _auth(client, superuser)
    response = client.put(
        f"/api/v1/organization/companies/{company.pk}/", {"legal_name": "Should Fail"}
    )
    assert response.status_code == 405


def test_delete_is_not_allowed(client: APIClient, superuser: User) -> None:
    company = CompanyFactory.create()
    _auth(client, superuser)
    response = client.delete(f"/api/v1/organization/companies/{company.pk}/")
    assert response.status_code == 405


# --------------------------------------------------------------------------
# RBAC scope filtering
# --------------------------------------------------------------------------


def test_company_scoped_viewer_only_sees_allowed_company(client: APIClient) -> None:
    company = CompanyFactory.create()
    other_company = CompanyFactory.create()
    user = UserFactory.create()
    _grant_org_role(user, verbs=["view"], scope_type=AccessScopeType.COMPANY, company=company)
    _auth(client, user)

    response = client.get("/api/v1/organization/companies/")
    codes = {item["code"] for item in response.json()["results"]}
    assert company.code in codes
    assert other_company.code not in codes


def test_company_scoped_viewer_cannot_retrieve_unrelated_company(client: APIClient) -> None:
    company = CompanyFactory.create()
    other_company = CompanyFactory.create()
    user = UserFactory.create()
    _grant_org_role(user, verbs=["view"], scope_type=AccessScopeType.COMPANY, company=company)
    _auth(client, user)

    response = client.get(f"/api/v1/organization/companies/{other_company.pk}/")
    assert response.status_code == 404


def test_branch_scoped_viewer_only_sees_allowed_branch(client: APIClient) -> None:
    branch = BranchFactory.create()
    other_branch = BranchFactory.create()
    user = UserFactory.create()
    _grant_org_role(
        user,
        verbs=["view"],
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )
    _auth(client, user)

    response = client.get("/api/v1/organization/branches/")
    ids = {item["id"] for item in response.json()["results"]}
    assert str(branch.pk) in ids
    assert str(other_branch.pk) not in ids


def test_viewer_cannot_post(client: APIClient) -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    _grant_org_role(user, verbs=["view"], scope_type=AccessScopeType.COMPANY, company=company)
    _auth(client, user)

    response = client.post(
        "/api/v1/organization/regions/",
        {"company": str(company.pk), "code": "R1", "name": "Region 1"},
        format="json",
    )
    assert response.status_code == 403


def test_organization_admin_can_post_within_permitted_scope(client: APIClient) -> None:
    company = CompanyFactory.create()
    user = UserFactory.create()
    _grant_org_role(
        user, verbs=["view", "add", "change"], scope_type=AccessScopeType.COMPANY, company=company
    )
    _auth(client, user)

    response = client.post(
        "/api/v1/organization/regions/",
        {"company": str(company.pk), "code": "R1", "name": "Region 1"},
        format="json",
    )
    assert response.status_code == 201


def test_cannot_create_records_outside_permitted_scope(client: APIClient) -> None:
    company = CompanyFactory.create()
    other_company = CompanyFactory.create()
    user = UserFactory.create()
    _grant_org_role(
        user, verbs=["view", "add", "change"], scope_type=AccessScopeType.COMPANY, company=company
    )
    _auth(client, user)

    response = client.post(
        "/api/v1/organization/regions/",
        {"company": str(other_company.pk), "code": "R1", "name": "Region 1"},
        format="json",
    )
    assert response.status_code == 400


def test_region_scoped_admin_can_manage_branch_in_region_but_not_outside(
    client: APIClient,
) -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company)
    user = UserFactory.create()
    _grant_org_role(
        user,
        verbs=["view", "add", "change"],
        scope_type=AccessScopeType.REGION,
        company=region.company,
        region=region,
    )
    _auth(client, user)

    in_scope_response = client.post(
        "/api/v1/organization/branches/",
        {
            "company": str(region.company.pk),
            "region": str(region.pk),
            "city": str(city.pk),
            "code": "BR-IN",
            "name": "In Scope Branch",
            "address_line_1": "1 Street",
        },
        format="json",
    )
    assert in_scope_response.status_code == 201

    other_region = RegionFactory.create()
    other_city = CityFactory.create(region=other_region, company=other_region.company)
    out_of_scope_response = client.post(
        "/api/v1/organization/branches/",
        {
            "company": str(other_region.company.pk),
            "region": str(other_region.pk),
            "city": str(other_city.pk),
            "code": "BR-OUT",
            "name": "Out of Scope Branch",
            "address_line_1": "2 Street",
        },
        format="json",
    )
    assert out_of_scope_response.status_code == 400


# --------------------------------------------------------------------------
# Filtering / searching / ordering / pagination
# --------------------------------------------------------------------------


def test_region_list_can_filter_by_company(client: APIClient, superuser: User) -> None:
    company = CompanyFactory.create()
    RegionFactory.create(company=company, code="R1")
    RegionFactory.create(code="R2")
    _auth(client, superuser)
    response = client.get(f"/api/v1/organization/regions/?company={company.pk}")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["code"] == "R1"


def test_company_list_can_search_by_code(client: APIClient, superuser: User) -> None:
    CompanyFactory.create(code="FINDME")
    CompanyFactory.create(code="OTHER")
    _auth(client, superuser)
    response = client.get("/api/v1/organization/companies/?search=FINDME")
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["code"] == "FINDME"


def test_company_list_can_order_by_code_descending(client: APIClient, superuser: User) -> None:
    CompanyFactory.create(code="AAA")
    CompanyFactory.create(code="ZZZ")
    _auth(client, superuser)
    response = client.get("/api/v1/organization/companies/?ordering=-code")
    codes = [item["code"] for item in response.json()["results"]]
    assert codes.index("ZZZ") < codes.index("AAA")


def test_company_list_is_paginated(client: APIClient, superuser: User) -> None:
    for _ in range(3):
        CompanyFactory.create()
    _auth(client, superuser)
    response = client.get("/api/v1/organization/companies/")
    payload = response.json()
    assert payload.keys() >= {"count", "next", "previous", "results"}


# --------------------------------------------------------------------------
# Activate / deactivate
# --------------------------------------------------------------------------


def test_deactivate_and_activate_region(client: APIClient, superuser: User) -> None:
    region = RegionFactory.create()
    _auth(client, superuser)
    deactivate_response = client.post(f"/api/v1/organization/regions/{region.pk}/deactivate/")
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    activate_response = client.post(f"/api/v1/organization/regions/{region.pk}/activate/")
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True


def test_deactivate_region_with_active_branch_returns_validation_error(
    client: APIClient, superuser: User
) -> None:
    region = RegionFactory.create()
    BranchFactory.create(region=region, company=region.company)
    _auth(client, superuser)
    response = client.post(f"/api/v1/organization/regions/{region.pk}/deactivate/")
    assert response.status_code == 400


# --------------------------------------------------------------------------
# Hierarchy
# --------------------------------------------------------------------------


def test_hierarchy_endpoint_returns_nested_structure(client: APIClient, superuser: User) -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company)
    branch = BranchFactory.create(region=region, company=region.company, city=city)
    zone = OperationalZoneFactory.create(branch=branch, company=branch.company)
    DepartmentFactory.create(company=region.company)
    DesignationFactory.create(company=region.company)

    _auth(client, superuser)
    response = client.get(f"/api/v1/organization/hierarchy/?company={region.company.pk}")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    company_data = payload[0]
    assert company_data["regions"][0]["cities"][0]["id"] == str(city.pk)
    assert company_data["regions"][0]["branches"][0]["operational_zones"][0]["id"] == str(zone.pk)
    assert len(company_data["departments"]) == 1
    assert len(company_data["designations"]) == 1


def test_hierarchy_endpoint_rejects_invalid_company_uuid(
    client: APIClient, superuser: User
) -> None:
    _auth(client, superuser)
    response = client.get("/api/v1/organization/hierarchy/?company=not-a-uuid")
    assert response.status_code == 400


def test_hierarchy_endpoint_hides_companies_outside_scope(client: APIClient) -> None:
    company = CompanyFactory.create()
    other_company = CompanyFactory.create()
    user = UserFactory.create()
    _grant_org_role(user, verbs=["view"], scope_type=AccessScopeType.COMPANY, company=company)
    _auth(client, user)

    response = client.get(f"/api/v1/organization/hierarchy/?company={other_company.pk}")
    assert response.status_code == 200
    assert response.json() == []


# --------------------------------------------------------------------------
# Validation error shape
# --------------------------------------------------------------------------


def test_create_company_with_missing_legal_name_returns_field_errors(
    client: APIClient, superuser: User
) -> None:
    _auth(client, superuser)
    response = client.post("/api/v1/organization/companies/", {"code": "NOLEGAL"})
    assert response.status_code == 400
    assert "legal_name" in response.json()


def test_create_region_with_inactive_company_returns_clear_error(
    client: APIClient, superuser: User
) -> None:
    company = CompanyFactory.create(is_active=False)
    _auth(client, superuser)
    response = client.post(
        "/api/v1/organization/regions/",
        {"company": str(company.pk), "code": "R-INACTIVE", "name": "Inactive Region"},
    )
    assert response.status_code == 400


# --------------------------------------------------------------------------
# Remaining resource list/retrieve/create/patch round-trips
# --------------------------------------------------------------------------


def test_city_list_and_retrieve(client: APIClient, superuser: User) -> None:
    city = CityFactory.create()
    _auth(client, superuser)
    list_response = client.get("/api/v1/organization/cities/")
    assert list_response.status_code == 200
    detail_response = client.get(f"/api/v1/organization/cities/{city.pk}/")
    assert detail_response.status_code == 200
    assert detail_response.json()["code"] == city.code


def test_branch_create_and_filter_by_is_head_office(client: APIClient, superuser: User) -> None:
    region = RegionFactory.create()
    city = CityFactory.create(region=region, company=region.company)
    _auth(client, superuser)
    response = client.post(
        "/api/v1/organization/branches/",
        {
            "company": str(region.company.pk),
            "region": str(region.pk),
            "city": str(city.pk),
            "code": "BR-API",
            "name": "API Branch",
            "address_line_1": "1 Street",
            "is_head_office": True,
        },
    )
    assert response.status_code == 201
    assert response.json()["is_head_office"] is True

    filtered = client.get("/api/v1/organization/branches/?is_head_office=true")
    assert filtered.status_code == 200
    assert len(filtered.json()["results"]) == 1


def test_department_create_and_patch(client: APIClient, superuser: User) -> None:
    company = CompanyFactory.create()
    _auth(client, superuser)
    response = client.post(
        "/api/v1/organization/departments/",
        {
            "company": str(company.pk),
            "code": "HR",
            "name": "Human Resources",
            "scope": "COMPANY",
        },
    )
    assert response.status_code == 201
    department_id = response.json()["id"]

    patch_response = client.patch(
        f"/api/v1/organization/departments/{department_id}/", {"sort_order": 2}
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["sort_order"] == 2


def test_designation_list_can_filter_by_supervisory(client: APIClient, superuser: User) -> None:
    DesignationFactory.create(is_supervisory=True)
    DesignationFactory.create(is_supervisory=False)
    _auth(client, superuser)
    response = client.get("/api/v1/organization/designations/?is_supervisory=true")
    assert response.status_code == 200
    assert all(item["is_supervisory"] for item in response.json()["results"])


def test_operational_zone_create_and_deactivate(client: APIClient, superuser: User) -> None:
    branch = BranchFactory.create()
    _auth(client, superuser)
    create_response = client.post(
        "/api/v1/organization/operational-zones/",
        {
            "company": str(branch.company.pk),
            "branch": str(branch.pk),
            "code": "Z-API",
            "name": "API Zone",
        },
    )
    assert create_response.status_code == 201
    zone_id = create_response.json()["id"]

    deactivate_response = client.post(
        f"/api/v1/organization/operational-zones/{zone_id}/deactivate/"
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False


def test_branch_region_patch_cannot_leave_city_in_previous_region(
    client: APIClient, superuser: User
) -> None:
    original_region = RegionFactory.create()
    new_region = RegionFactory.create(company=original_region.company)
    city = CityFactory.create(region=original_region, company=original_region.company)
    branch = BranchFactory.create(
        region=original_region, company=original_region.company, city=city
    )
    _auth(client, superuser)

    response = client.patch(
        f"/api/v1/organization/branches/{branch.pk}/",
        {"region": str(new_region.pk)},
        format="json",
    )

    assert response.status_code == 400
    branch.refresh_from_db()
    assert branch.region_id == original_region.pk
    assert branch.city_id == city.pk
