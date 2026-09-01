# mypy: disable-error-code="arg-type"
from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.contracts.models import (
    Client,
    ClientIndustry,
    SecurityPost,
    SecuritySite,
    ServiceContract,
)
from dsms.identity.enums import AccessScopeType
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def grant_branch_permission(user, branch, codename: str) -> None:
    role = RoleFactory.create()
    role.permissions.add(
        Permission.objects.get(content_type__app_label="deployment", codename=codename)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )


def eligibility_context(branch, suffix: str | None = None):
    suffix = suffix or branch.code
    actor = UserFactory.create()
    employee = EmployeeFactory.create(
        company=branch.company, branch=branch, employment_status="ACTIVE"
    )
    industry = ClientIndustry.objects.create(
        company=branch.company, code=f"IND-{suffix}", name="Operations"
    )
    client = Client.objects.create(
        company=branch.company,
        client_code=f"CLI-{suffix}",
        legal_name=f"Client {suffix}",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=branch.company,
        client=client,
        contract_number=f"CTR-{suffix}",
        contract_type="FIXED_TERM",
        title="Guarding",
        start_date=date.today(),
        status="ACTIVE",
        created_by=actor,
    )
    site = SecuritySite.objects.create(
        company=branch.company,
        client=client,
        contract=contract,
        site_code=f"SITE-{suffix}",
        name=f"Site {suffix}",
        managing_branch=branch,
        address_line_1="Test address",
        city_name="Islamabad",
        risk_level="MEDIUM",
        status="ACTIVE",
    )
    post = SecurityPost.objects.create(
        company=branch.company,
        client=client,
        site=site,
        post_code=f"POST-{suffix}",
        name="Main gate",
        status="ACTIVE",
    )
    return employee, site, post


def eligibility_url(employee, site, post) -> str:
    base = reverse("deployment-eligibility", kwargs={"employee_id": employee.id})
    return f"{base}?site={site.id}&post={post.id}"


def test_deployment_eligibility_rejects_anonymous_and_no_role() -> None:
    employee, site, post = eligibility_context(BranchFactory.create())
    url = eligibility_url(employee, site, post)
    assert APIClient().get(url).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    response = client.get(url)
    assert response.status_code == 403
    assert "blocking_reasons" not in response.data


def test_deployment_eligibility_wrong_scope_is_non_enumerating() -> None:
    allowed, hidden = BranchFactory.create(), BranchFactory.create()
    employee, site, post = eligibility_context(hidden)
    user = UserFactory.create()
    grant_branch_permission(user, allowed, "view_dutyshift")
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(eligibility_url(employee, site, post))
    assert response.status_code == 404
    assert "blocking_reasons" not in response.data


def test_deployment_eligibility_same_scope_and_superuser_retain_access() -> None:
    branch = BranchFactory.create()
    employee, site, post = eligibility_context(branch)
    url = eligibility_url(employee, site, post)
    user = UserFactory.create()
    grant_branch_permission(user, branch, "view_dutyshift")
    client = APIClient()
    client.force_authenticate(user)
    assert client.get(url).status_code == 200
    client.force_authenticate(UserFactory.create(is_superuser=True))
    assert client.get(url).status_code == 200


def test_deployment_eligibility_rejects_post_from_another_site() -> None:
    branch = BranchFactory.create()
    employee, site, _ = eligibility_context(branch)
    _, other_site, other_post = eligibility_context(branch, f"{branch.code}-OTHER")
    user = UserFactory.create()
    grant_branch_permission(user, branch, "view_dutyshift")
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(eligibility_url(employee, site, other_post))
    assert other_site != site
    assert response.status_code == 404


def test_deployment_dashboard_is_private_and_planned_only() -> None:
    url = reverse("deployment-dashboard-summary")
    assert APIClient().get(url).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    assert client.get(url).status_code == 403
    client.force_authenticate(UserFactory(is_superuser=True))
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["attendance_records_created"] == 0
