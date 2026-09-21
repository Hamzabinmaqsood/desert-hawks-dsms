# mypy: disable-error-code="arg-type"
import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.training.models import TrainingVenue
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory, RegionFactory

pytestmark = pytest.mark.django_db


def test_training_dashboard_requires_authentication() -> None:
    assert APIClient().get(reverse("training-dashboard-summary")).status_code == 401


def test_training_dashboard_returns_calculated_totals() -> None:
    user = UserFactory(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(reverse("training-dashboard-summary"))
    assert response.status_code == 200
    assert response.json()["active_courses"] == 0


def test_training_dashboard_requires_dashboard_permission() -> None:
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    assert client.get(reverse("training-dashboard-summary")).status_code == 403


def test_training_dashboard_rejects_foreign_company_parameter() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    actor = UserFactory.create()
    role = RoleFactory.create(company=company_a)
    role.permissions.add(
        Permission.objects.get(
            content_type__app_label="training", codename="view_training_dashboard"
        )
    )
    UserRoleAssignmentFactory.create(
        user=actor, role=role, scope_type=AccessScopeType.COMPANY, company=company_a
    )
    client = APIClient()
    client.force_authenticate(actor)
    assert client.get(reverse("training-dashboard-summary")).status_code == 200
    assert (
        client.get(reverse("training-dashboard-summary"), {"company": company_b.pk}).status_code
        == 404
    )


def test_training_venue_crud_hides_corrupt_rows_and_rejects_cross_company_links() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    branch_b = BranchFactory.create(
        region=RegionFactory.create(company=company_b), company=company_b
    )
    actor = UserFactory.create()
    role_a = RoleFactory.create(company=company_a)
    role_a.permissions.set(
        Permission.objects.filter(
            content_type__app_label="training",
            codename__in=["view_trainingvenue", "add_trainingvenue", "change_trainingvenue"],
        )
    )
    UserRoleAssignmentFactory.create(
        user=actor, role=role_a, scope_type=AccessScopeType.COMPANY, company=company_a
    )
    venue_a = TrainingVenue.objects.create(
        company=company_a, code="A", name="A", address="A Street", city="Lahore"
    )
    venue_b = TrainingVenue.objects.create(
        company=company_b, code="B", name="B", address="B Street", city="Lahore"
    )
    corrupt = TrainingVenue.objects.create(
        company=company_a,
        branch=branch_b,
        code="CORRUPT",
        name="Corrupt",
        address="C Street",
        city="Lahore",
    )
    client = APIClient()
    client.force_authenticate(actor)

    response = client.get("/api/v1/training/venues/")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["results"]}
    assert str(venue_a.pk) in ids
    assert str(venue_b.pk) not in ids
    assert str(corrupt.pk) not in ids
    assert client.get(f"/api/v1/training/venues/{venue_b.pk}/").status_code == 404
    assert client.get(f"/api/v1/training/venues/{corrupt.pk}/").status_code == 404

    create_a = client.post(
        "/api/v1/training/venues/",
        {
            "company": str(company_a.pk),
            "code": "NEW",
            "name": "New",
            "address": "New Street",
            "city": "Lahore",
        },
        format="json",
    )
    assert create_a.status_code == 201
    create_b = client.post(
        "/api/v1/training/venues/",
        {
            "company": str(company_b.pk),
            "code": "OUT",
            "name": "Out",
            "address": "Out Street",
            "city": "Lahore",
        },
        format="json",
    )
    assert create_b.status_code == 400

    role_b = RoleFactory.create(company=company_b)
    role_b.permissions.set(role_a.permissions.all())
    UserRoleAssignmentFactory.create(
        user=actor, role=role_b, scope_type=AccessScopeType.COMPANY, company=company_b
    )
    patch = client.patch(
        f"/api/v1/training/venues/{venue_a.pk}/",
        {"branch": str(branch_b.pk)},
        format="json",
    )
    assert patch.status_code == 400
    venue_a.refresh_from_db()
    assert venue_a.branch_id is None
