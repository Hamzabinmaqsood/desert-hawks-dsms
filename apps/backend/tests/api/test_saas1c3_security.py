# mypy: disable-error-code="arg-type,attr-defined,misc,no-untyped-call"
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
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
from dsms.incidents.exceptions import IncidentPermissionError
from dsms.incidents.models import (
    Incident,
    IncidentEscalationPolicy,
    IncidentEvidence,
    IncidentException,
    IncidentType,
    SOSAlert,
)
from dsms.incidents.services import trigger_sos
from dsms.incidents.tasks import reconcile_incident_slas
from dsms.organization.models import Branch
from dsms.supervision.models import SiteVisit
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory, CompanyFactory, RegionFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def api_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def grant(user: User, branch: Branch, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.set(
        Permission.objects.filter(content_type__app_label="incidents", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )


def graph(suffix: str, *, active: bool = True) -> dict[str, object]:
    if active:
        branch = BranchFactory.create()
    else:
        company = CompanyFactory.create(is_active=False)
        region = RegionFactory.create(company=company)
        branch = BranchFactory.create(company=company, region=region)
    actor = UserFactory.create()
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
        title=f"Contract {suffix}",
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
        address_line_1="Test",
        city_name="Islamabad",
        risk_level="HIGH",
        status="ACTIVE",
    )
    post = SecurityPost.objects.create(
        company=branch.company,
        client=client,
        site=site,
        post_code=f"POST-{suffix}",
        name=f"Post {suffix}",
        status="ACTIVE",
    )
    incident_type = IncidentType.objects.create(
        company=branch.company,
        code=f"TYPE-{suffix}",
        name=f"Type {suffix}",
        default_severity="HIGH",
        default_priority="HIGH",
    )
    employee = EmployeeFactory.create(
        company=branch.company,
        branch=branch,
        user=actor,
        employee_type="SECURITY_GUARD",
        employment_status="ACTIVE",
    )
    return {
        "actor": actor,
        "branch": branch,
        "company": branch.company,
        "client": client,
        "contract": contract,
        "site": site,
        "post": post,
        "type": incident_type,
        "employee": employee,
    }


def incident(item: dict[str, object], suffix: str) -> Incident:
    return Incident.objects.create(
        incident_number=f"INC-{suffix}",
        company=item["company"],
        branch=item["branch"],
        client=item["client"],
        contract=item["contract"],
        site=item["site"],
        post=item["post"],
        incident_type=item["type"],
        severity="HIGH",
        priority="HIGH",
        status="NEW",
        verification_status="UNVERIFIED",
        source="OTHER",
        title=f"Incident {suffix}",
        description="Tenant boundary test",
        reported_at=timezone.now() - timedelta(minutes=30),
        created_by=item["actor"],
    )


def test_incident_reads_hide_other_inactive_and_corrupt_graphs_for_a_plus_b_user() -> None:
    a, b, inactive = graph("READ-A"), graph("READ-B"), graph("READ-INACTIVE", active=False)
    valid_a, valid_b = incident(a, "READ-A"), incident(b, "READ-B")
    inactive_incident = incident(inactive, "READ-INACTIVE")
    corrupt = incident(a, "READ-CORRUPT")
    Incident.objects.filter(pk=corrupt.pk).update(branch=b["branch"])
    corrupt_visit = SiteVisit.objects.create(
        company=a["company"],
        supervisor=a["employee"],
        branch=a["branch"],
        site=a["site"],
        started_at=timezone.now(),
        status="IN_PROGRESS",
        verification_method="OTHER",
        verification_result="NOT_REQUIRED",
    )
    corrupt_source = incident(a, "READ-CORRUPT-SOURCE")
    Incident.objects.filter(pk=corrupt_source.pk).update(site_visit=corrupt_visit)
    SiteVisit.objects.filter(pk=corrupt_visit.pk).update(supervisor=b["employee"])
    user = UserFactory.create()
    grant(user, a["branch"], "view_incident")
    grant(user, b["branch"], "view_incident")

    a_only = UserFactory.create()
    grant(a_only, a["branch"], "view_incident")
    assert {
        row["id"] for row in api_for(a_only).get("/api/v1/incidents/incidents/").json()["results"]
    } == {str(valid_a.id)}
    assert api_for(a_only).get(f"/api/v1/incidents/incidents/{valid_b.id}/").status_code == 404
    b_only = UserFactory.create()
    grant(b_only, b["branch"], "view_incident")
    assert {
        row["id"] for row in api_for(b_only).get("/api/v1/incidents/incidents/").json()["results"]
    } == {str(valid_b.id)}
    assert api_for(b_only).get(f"/api/v1/incidents/incidents/{valid_a.id}/").status_code == 404

    response = api_for(user).get("/api/v1/incidents/incidents/")

    assert response.status_code == 200
    assert {row["id"] for row in response.json()["results"]} == {
        str(valid_a.id),
        str(valid_b.id),
    }
    assert api_for(user).get(f"/api/v1/incidents/incidents/{corrupt.id}/").status_code == 404
    assert api_for(user).get(f"/api/v1/incidents/incidents/{corrupt_source.id}/").status_code == 404
    assert (
        api_for(UserFactory.create(is_superuser=True))
        .get(f"/api/v1/incidents/incidents/{inactive_incident.id}/")
        .status_code
        == 404
    )


def test_create_and_patch_validate_complete_graph_and_protect_workflow_fields() -> None:
    a, b = graph("WRITE-A"), graph("WRITE-B")
    user = UserFactory.create()
    grant(user, a["branch"], "report_incident", "manage_incident")
    grant(user, b["branch"], "report_incident", "manage_incident")
    api = api_for(user)
    payload = {
        "company": str(a["company"].id),
        "branch": str(a["branch"].id),
        "client": str(a["client"].id),
        "contract": str(a["contract"].id),
        "site": str(a["site"].id),
        "post": str(a["post"].id),
        "incident_type": str(a["type"].id),
        "source": "PATROL",
        "title": "Reported safely",
        "description": "Direct report",
        "status": "CLOSED",
        "resolution_summary": "Forged",
    }
    created = api.post("/api/v1/incidents/incidents/", payload, format="json")
    assert created.status_code == 201
    item = Incident.objects.get(pk=created.json()["id"])
    assert item.status == "NEW"
    assert item.source == "OTHER"
    assert item.resolution_summary == ""
    valid_patch = api.patch(
        f"/api/v1/incidents/incidents/{item.id}/",
        {"title": "Updated safely"},
        format="json",
    )
    assert valid_patch.status_code == 200
    item.refresh_from_db()
    assert item.title == "Updated safely"

    mixed = dict(payload)
    mixed.update(
        {
            "site": str(b["site"].id),
            "post": str(b["post"].id),
            "incident_type": str(b["type"].id),
        }
    )
    assert api.post("/api/v1/incidents/incidents/", mixed, format="json").status_code == 400
    changed = api.patch(
        f"/api/v1/incidents/incidents/{item.id}/",
        {
            "company": str(b["company"].id),
            "site": str(b["site"].id),
            "post": str(b["post"].id),
            "status": "CLOSED",
        },
        format="json",
    )
    assert changed.status_code == 400
    item.refresh_from_db()
    assert item.company_id == a["company"].id
    assert item.site_id == a["site"].id
    assert item.status == "NEW"

    b_only_writer = UserFactory.create()
    grant(b_only_writer, b["branch"], "manage_incident")
    assert (
        api_for(b_only_writer)
        .patch(
            f"/api/v1/incidents/incidents/{item.id}/",
            {"title": "Unauthorized"},
            format="json",
        )
        .status_code
        == 404
    )


def test_workflows_scope_incident_and_responder_relations() -> None:
    a, b = graph("ACTION-A"), graph("ACTION-B")
    item = incident(a, "ACTION-A")
    user = UserFactory.create()
    grant(user, a["branch"], "manage_responders")
    grant(user, b["branch"], "manage_responders")
    api = api_for(user)
    cross_employee = api.post(
        f"/api/v1/incidents/incidents/{item.id}/assign-responder/",
        {"employee": str(b["employee"].id), "responder_role": "OTHER"},
        format="json",
    )
    assert cross_employee.status_code == 404
    grant(b["actor"], b["branch"], "view_incident")
    cross_user = api.post(
        f"/api/v1/incidents/incidents/{item.id}/assign-responder/",
        {"user": str(b["actor"].id), "responder_role": "OTHER"},
        format="json",
    )
    assert cross_user.status_code == 404
    valid = api.post(
        f"/api/v1/incidents/incidents/{item.id}/assign-responder/",
        {"employee": str(a["employee"].id), "responder_role": "OTHER"},
        format="json",
    )
    assert valid.status_code == 201
    corrupt = incident(a, "ACTION-CORRUPT")
    Incident.objects.filter(pk=corrupt.pk).update(branch=b["branch"])
    assert (
        api.post(
            f"/api/v1/incidents/incidents/{corrupt.id}/assign-responder/",
            {"employee": str(a["employee"].id), "responder_role": "OTHER"},
            format="json",
        ).status_code
        == 404
    )

    wrong_scope = UserFactory.create()
    grant(wrong_scope, b["branch"], "acknowledge_incident")
    assert (
        api_for(wrong_scope)
        .post(f"/api/v1/incidents/incidents/{item.id}/acknowledge/", {}, format="json")
        .status_code
        == 404
    )


def test_sos_scope_sensitive_location_and_idempotency_are_resource_bound() -> None:
    a, b = graph("SOS-A"), graph("SOS-B")
    guard = a["actor"]
    grant(guard, a["branch"], "trigger_own_sos", "view_own_sos")
    grant(guard, b["branch"], "view_sensitive_incident_location")
    api = api_for(guard)
    event_id = uuid4()
    response = api.post(
        "/api/v1/incidents/sos/trigger/",
        {
            "employee": str(a["employee"].id),
            "client_event_id": str(event_id),
            "latitude": "33.710000",
            "longitude": "73.060000",
        },
        format="json",
    )
    assert response.status_code == 201
    assert "latitude" not in response.json()
    unrelated = incident(a, "SOS-UNRELATED")
    SOSAlert.objects.filter(pk=response.json()["id"]).update(linked_incident=unrelated)
    assert api.get(f"/api/v1/incidents/sos/{response.json()['id']}/").status_code == 404
    grant(b["actor"], b["branch"], "trigger_own_sos")
    same_key_other_tenant = api_for(b["actor"]).post(
        "/api/v1/incidents/sos/trigger/",
        {
            "employee": str(b["employee"].id),
            "client_event_id": str(event_id),
        },
        format="json",
    )
    assert same_key_other_tenant.status_code == 201
    assert same_key_other_tenant.json()["id"] != response.json()["id"]
    assert (
        api.post(
            "/api/v1/incidents/sos/trigger/",
            {"employee": str(b["employee"].id), "client_event_id": str(uuid4())},
            format="json",
        ).status_code
        == 404
    )

    manager = UserFactory.create()
    grant(manager, a["branch"], "manage_incident")
    other_employee = EmployeeFactory.create(
        company=a["company"],
        branch=a["branch"],
        employee_type="SECURITY_GUARD",
        employment_status="ACTIVE",
    )
    manager_event = uuid4()
    trigger_sos(
        actor=manager,
        employee=a["employee"],
        client_event_id=manager_event,
    )
    with pytest.raises(IncidentPermissionError):
        trigger_sos(
            actor=manager,
            employee=other_employee,
            client_event_id=manager_event,
        )


def test_evidence_projection_and_download_lookup_fail_closed() -> None:
    a, b = graph("EVID-A"), graph("EVID-B")
    incident_a, incident_b = incident(a, "EVID-A"), incident(b, "EVID-B")
    valid = IncidentEvidence.objects.create(
        company=a["company"],
        incident=incident_a,
        evidence_type="DOCUMENT",
        external_reference="private://reference",
        original_filename="valid.pdf",
        file_size=42,
        mime_type="application/pdf",
        sha256_hash="a" * 64,
        uploaded_by=a["actor"],
    )
    valid_b = IncidentEvidence.objects.create(
        company=b["company"],
        incident=incident_b,
        evidence_type="DOCUMENT",
        original_filename="valid-b.pdf",
        uploaded_by=b["actor"],
    )
    corrupt = IncidentEvidence.objects.create(
        company=a["company"],
        incident=incident_b,
        evidence_type="DOCUMENT",
        external_reference="private://cross-tenant",
        original_filename="corrupt.pdf",
        sha256_hash="b" * 64,
        uploaded_by=a["actor"],
    )
    user = UserFactory.create()
    grant(user, a["branch"], "download_incident_evidence")
    grant(user, b["branch"], "download_incident_evidence")
    api = api_for(user)

    rows = api.get("/api/v1/incidents/evidence/").json()["results"]
    assert {row["id"] for row in rows} == {str(valid.id), str(valid_b.id)}
    for row in rows:
        assert "file" not in row
        assert "sha256_hash" not in row
        assert "external_reference" not in row
    a_only = UserFactory.create()
    grant(a_only, a["branch"], "download_incident_evidence")
    a_rows = api_for(a_only).get("/api/v1/incidents/evidence/").json()["results"]
    assert [row["id"] for row in a_rows] == [str(valid.id)]
    assert api_for(a_only).get(f"/api/v1/incidents/evidence/{valid_b.id}/").status_code == 404
    assert api.get(f"/api/v1/incidents/evidence/{corrupt.id}/").status_code == 404
    assert api.get(f"/api/v1/incidents/evidence/{corrupt.id}/download/").status_code == 404


def test_dashboard_and_sla_task_ignore_corrupt_and_inactive_incidents() -> None:
    a, b, empty, inactive = (
        graph("TASK-A"),
        graph("TASK-B"),
        graph("TASK-EMPTY"),
        graph("TASK-INACTIVE", active=False),
    )
    valid = incident(a, "TASK-VALID")
    corrupt = incident(a, "TASK-CORRUPT")
    Incident.objects.filter(pk=corrupt.pk).update(branch=b["branch"])
    inactive_incident = incident(inactive, "TASK-INACTIVE")
    for item, owner in ((valid, a), (corrupt, a), (inactive_incident, inactive)):
        IncidentEscalationPolicy.objects.create(
            company=owner["company"],
            incident_type=owner["type"],
            site=owner["site"],
            name=f"Policy {item.incident_number}",
            effective_from=date.today(),
            acknowledgement_target_minutes=1,
        )
    user = UserFactory.create()
    grant(user, a["branch"], "view_incident_dashboard")
    grant(user, b["branch"], "view_incident_dashboard")

    rows = api_for(user).get("/api/v1/incidents/command-center/queue/").json()["results"]
    assert [row["id"] for row in rows] == [str(valid.id)]
    empty_user = UserFactory.create()
    grant(empty_user, empty["branch"], "view_incident_dashboard")
    empty_response = api_for(empty_user).get("/api/v1/incidents/command-center/queue/")
    assert empty_response.status_code == 200
    assert empty_response.json()["results"] == []
    assert reconcile_incident_slas() == 1
    assert IncidentException.objects.filter(incident=valid).exists()
    assert not IncidentException.objects.filter(incident=corrupt).exists()
    assert not IncidentException.objects.filter(incident=inactive_incident).exists()
