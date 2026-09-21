# mypy: disable-error-code="arg-type"
from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.recruitment.models import Candidate, CandidateApplication, Vacancy
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory, DesignationFactory

pytestmark = pytest.mark.django_db


def test_recruitment_dashboard_requires_authentication() -> None:
    response = APIClient().get(reverse("recruitment-dashboard-summary"))
    assert response.status_code == 401


def test_recruitment_dashboard_returns_real_counts() -> None:
    user = UserFactory(is_superuser=True)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(reverse("recruitment-dashboard-summary"))
    assert response.status_code == 200
    assert response.json()["open_vacancies"] == 0
    assert response.json()["hired"] == 0


def test_recruitment_dashboard_requires_view_permission() -> None:
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    assert client.get(reverse("recruitment-dashboard-summary")).status_code == 403


def test_recruitment_dashboard_rejects_foreign_company_parameter() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    actor = UserFactory.create()
    role = RoleFactory.create(company=company_a)
    role.permissions.add(
        Permission.objects.get(
            content_type__app_label="recruitment", codename="view_candidateapplication"
        )
    )
    UserRoleAssignmentFactory.create(
        user=actor, role=role, scope_type=AccessScopeType.COMPANY, company=company_a
    )
    client = APIClient()
    client.force_authenticate(actor)
    assert client.get(reverse("recruitment-dashboard-summary")).status_code == 200
    assert (
        client.get(reverse("recruitment-dashboard-summary"), {"company": company_b.pk}).status_code
        == 404
    )


def test_candidate_crud_enforces_tenant_and_sensitive_field_boundaries() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    actor = UserFactory.create()
    role = RoleFactory.create(company=company_a)
    role.permissions.set(
        Permission.objects.filter(
            content_type__app_label="recruitment",
            codename__in=["view_candidate", "add_candidate", "change_candidate"],
        )
    )
    UserRoleAssignmentFactory.create(
        user=actor, role=role, scope_type=AccessScopeType.COMPANY, company=company_a
    )
    candidate_a = Candidate.objects.create(
        candidate_number="CAND-A",
        company=company_a,
        first_name="A",
        mobile_number="03000000001",
        source_type="WEBSITE",
        national_identity_number="12345-1234567-1",
    )
    candidate_b = Candidate.objects.create(
        candidate_number="CAND-B",
        company=company_b,
        first_name="B",
        mobile_number="03000000002",
        source_type="WEBSITE",
    )
    client = APIClient()
    client.force_authenticate(actor)

    response = client.get("/api/v1/recruitment/candidates/")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["results"]}
    assert str(candidate_a.pk) in ids
    assert str(candidate_b.pk) not in ids
    assert "national_identity_number" not in response.json()["results"][0]
    assert client.get(f"/api/v1/recruitment/candidates/{candidate_b.pk}/").status_code == 404

    create_a = client.post(
        "/api/v1/recruitment/candidates/",
        {
            "company": str(company_a.pk),
            "first_name": "New",
            "mobile_number": "03000000003",
            "source_type": "WEBSITE",
        },
        format="json",
    )
    assert create_a.status_code == 201, create_a.json()
    assert create_a.json()["candidate_number"].startswith("CAND-")
    create_b = client.post(
        "/api/v1/recruitment/candidates/",
        {
            "company": str(company_b.pk),
            "first_name": "New",
            "mobile_number": "03000000004",
            "source_type": "WEBSITE",
        },
        format="json",
    )
    assert create_b.status_code == 400
    patch = client.patch(
        f"/api/v1/recruitment/candidates/{candidate_a.pk}/",
        {"company": str(company_b.pk)},
        format="json",
    )
    assert patch.status_code == 400
    candidate_a.refresh_from_db()
    assert candidate_a.company_id == company_a.pk


def test_application_parent_chain_rejects_cross_company_even_for_multi_company_actor() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    actor = UserFactory.create()
    for company in (company_a, company_b):
        role = RoleFactory.create(company=company)
        role.permissions.set(
            Permission.objects.filter(
                content_type__app_label="recruitment",
                codename__in=["view_candidateapplication", "add_candidateapplication"],
            )
        )
        UserRoleAssignmentFactory.create(
            user=actor, role=role, scope_type=AccessScopeType.COMPANY, company=company
        )
    candidate_a = Candidate.objects.create(
        candidate_number="PARENT-A",
        company=company_a,
        first_name="A",
        mobile_number="03000000011",
        source_type="WEBSITE",
    )
    vacancies = {}
    for company in (company_a, company_b):
        vacancies[company.pk] = Vacancy.objects.create(
            company=company,
            designation=DesignationFactory.create(company=company),
            employee_type="SECURITY_GUARD",
            employment_type="PERMANENT",
            vacancy_code=f"VAC-{company.code}",
            title="Guard",
            description="Guard role",
            number_of_positions=1,
            opening_date=date.today(),
            created_by=actor,
        )
    valid = CandidateApplication.objects.create(
        application_number="APP-VALID",
        candidate=candidate_a,
        vacancy=vacancies[company_a.pk],
        company=company_a,
        source_type="WEBSITE",
    )
    corrupt = CandidateApplication.objects.create(
        application_number="APP-CORRUPT",
        candidate=candidate_a,
        vacancy=vacancies[company_b.pk],
        company=company_a,
        source_type="WEBSITE",
    )
    client = APIClient()
    client.force_authenticate(actor)
    response = client.get("/api/v1/recruitment/applications/")
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["results"]}
    assert str(valid.pk) in ids
    assert str(corrupt.pk) not in ids
    assert client.get(f"/api/v1/recruitment/applications/{corrupt.pk}/").status_code == 404
    create = client.post(
        "/api/v1/recruitment/applications/",
        {
            "company": str(company_a.pk),
            "candidate": str(candidate_a.pk),
            "vacancy": str(vacancies[company_b.pk].pk),
            "source_type": "WEBSITE",
        },
        format="json",
    )
    assert create.status_code == 400
