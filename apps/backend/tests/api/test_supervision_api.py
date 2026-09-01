# mypy: disable-error-code="arg-type"
from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.contracts.models import (
    Client,
    ClientIndustry,
    SecurityPost,
    SecuritySite,
    ServiceContract,
)
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from dsms.organization.models import Branch
from dsms.supervision.models import (
    CorrectiveAction,
    FieldEvidence,
    GuardObservation,
    InspectionFinding,
    InspectionTemplate,
    SiteInspection,
    SiteVisit,
    SupervisorVisitPlan,
)
from dsms.workforce.models import Employee
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def grant(user: User, branch: Branch, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.set(
        Permission.objects.filter(content_type__app_label="supervision", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )


def supervision_context(
    branch: Branch, suffix: str
) -> tuple[User, Employee, SecuritySite, SiteVisit, GuardObservation, FieldEvidence]:
    actor = UserFactory.create()
    supervisor = EmployeeFactory.create(
        company=branch.company,
        branch=branch,
        user=actor,
        employee_type="SUPERVISOR",
        employment_status="ACTIVE",
    )
    guard = EmployeeFactory.create(
        company=branch.company, branch=branch, employment_status="ACTIVE"
    )
    industry = ClientIndustry.objects.create(
        company=branch.company, code=f"IND-{suffix}", name=f"Industry {suffix}"
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
        risk_level="HIGH",
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
    visit = SiteVisit.objects.create(
        company=branch.company,
        supervisor=supervisor,
        branch=branch,
        site=site,
        started_at=timezone.now(),
        status="IN_PROGRESS",
        verification_method="GPS",
        verification_result="WARNING",
    )
    observation = GuardObservation.objects.create(
        company=branch.company,
        site_visit=visit,
        site=site,
        post=post,
        employee=guard,
        observation_status="ABSENT",
        observed_at=timezone.now(),
        remarks=f"Sensitive {suffix}",
        created_by=actor,
    )
    evidence = FieldEvidence.objects.create(
        company=branch.company,
        site_visit=visit,
        file=f"supervision-evidence/{suffix}.pdf",
        original_filename=f"{suffix}.pdf",
        file_size=10,
        mime_type="application/pdf",
        sha256_hash="a" * 64,
        caption=f"Evidence {suffix}",
        uploaded_by=actor,
    )
    return actor, supervisor, site, visit, observation, evidence


def test_supervision_observation_and_evidence_reject_anonymous_and_no_role() -> None:
    *_, observation, evidence = supervision_context(BranchFactory.create(), "PRIVATE")
    observation_url = f"/api/v1/supervision/guard-observations/{observation.id}/"
    evidence_url = f"/api/v1/supervision/evidence/{evidence.id}/"
    assert APIClient().get(observation_url).status_code == 401
    assert APIClient().get(evidence_url).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    assert client.get(observation_url).status_code == 403
    assert client.get(evidence_url).status_code == 403


def test_supervision_direct_object_probes_are_non_enumerating_across_branches() -> None:
    allowed, hidden = BranchFactory.create(), BranchFactory.create()
    *_, observation, evidence = supervision_context(hidden, "HIDDEN")
    user = UserFactory.create()
    grant(user, allowed, "view_guard_observation", "view_sensitive_field_evidence")
    client = APIClient()
    client.force_authenticate(user)
    observation_response = client.get(f"/api/v1/supervision/guard-observations/{observation.id}/")
    evidence_response = client.get(f"/api/v1/supervision/evidence/{evidence.id}/")
    assert observation_response.status_code == evidence_response.status_code == 404
    assert "Sensitive HIDDEN" not in observation_response.content.decode()
    assert "HIDDEN.pdf" not in evidence_response.content.decode()


def test_supervision_scoped_lists_and_private_evidence_metadata() -> None:
    allowed, hidden = BranchFactory.create(), BranchFactory.create()
    *_, allowed_observation, allowed_evidence = supervision_context(allowed, "ALLOWED")
    supervision_context(hidden, "HIDDEN")
    user = UserFactory.create()
    grant(user, allowed, "view_guard_observation", "view_sensitive_field_evidence")
    client = APIClient()
    client.force_authenticate(user)
    observations = client.get("/api/v1/supervision/guard-observations/")
    evidence = client.get("/api/v1/supervision/evidence/")
    assert observations.status_code == evidence.status_code == 200
    assert [item["id"] for item in observations.data["results"]] == [str(allowed_observation.id)]
    assert [item["id"] for item in evidence.data["results"]] == [str(allowed_evidence.id)]
    assert "file" not in evidence.data["results"][0]


def test_supervision_observation_and_evidence_superuser_access() -> None:
    *_, observation, evidence = supervision_context(BranchFactory.create(), "SUPER")
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    assert (
        client.get(f"/api/v1/supervision/guard-observations/{observation.id}/").status_code == 200
    )
    assert client.get(f"/api/v1/supervision/evidence/{evidence.id}/").status_code == 200


def create_exception_records(branch: Branch, suffix: str) -> None:
    actor, supervisor, site, visit, _, _ = supervision_context(branch, suffix)
    SupervisorVisitPlan.objects.create(
        company=branch.company,
        supervisor=supervisor,
        branch=branch,
        site=site,
        planned_date=timezone.localdate(),
        purpose="Security review",
        status="MISSED",
        created_by=actor,
    )
    template = InspectionTemplate.objects.create(
        company=branch.company,
        code=f"TPL-{suffix}",
        name="Security review",
        scope="SITE",
        effective_from=date.today(),
    )
    inspection = SiteInspection.objects.create(
        company=branch.company,
        site_visit=visit,
        site=site,
        template=template,
        template_version=1,
        scope="SITE",
        started_at=timezone.now(),
        status="IN_PROGRESS",
        created_by=actor,
    )
    finding = InspectionFinding.objects.create(
        company=branch.company,
        inspection=inspection,
        site=site,
        title="Critical finding",
        description="Test",
        severity="CRITICAL",
        status="OPEN",
        identified_by=actor,
        identified_at=timezone.now(),
    )
    CorrectiveAction.objects.create(
        company=branch.company,
        finding=finding,
        site=site,
        title="Correct issue",
        description="Test",
        assigned_by=actor,
        assigned_at=timezone.now(),
        due_at=timezone.now() - timedelta(days=1),
        status="OPEN",
    )


def test_supervision_exceptions_require_permission_and_aggregate_only_scope() -> None:
    allowed, hidden = BranchFactory.create(), BranchFactory.create()
    create_exception_records(allowed, "ALLOWED-EX")
    create_exception_records(hidden, "HIDDEN-EX")
    url = "/api/v1/supervision/exceptions/"
    assert APIClient().get(url).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    assert client.get(url).status_code == 403
    user = UserFactory.create()
    grant(user, allowed, "view_supervision_dashboard")
    client.force_authenticate(user)
    response = client.get(url)
    assert response.status_code == 200
    assert response.data == {
        "missed_visits": 1,
        "outside_geofence": 1,
        "critical_findings": 1,
        "overdue_corrective_actions": 1,
    }
    client.force_authenticate(UserFactory.create(is_superuser=True))
    assert client.get(url).data["critical_findings"] == 2


def test_supervision_dashboard_requires_scoped_permission() -> None:
    url = reverse("supervision-dashboard-summary")
    assert APIClient().get(url).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    assert client.get(url).status_code == 403
    branch = BranchFactory.create()
    user = UserFactory.create()
    grant(user, branch, "view_supervision_dashboard")
    client.force_authenticate(user)
    response = client.get(url)
    assert response.status_code == 200
    assert response.json()["today_planned_visits"] == 0


def test_supervision_resources_do_not_expose_delete() -> None:
    client = APIClient()
    client.force_authenticate(UserFactory(is_superuser=True))
    assert client.delete("/api/v1/supervision/assignments/not-a-uuid/").status_code == 405
