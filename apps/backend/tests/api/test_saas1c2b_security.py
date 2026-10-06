# mypy: disable-error-code="arg-type,attr-defined,misc,no-untyped-call"
from __future__ import annotations

import uuid
from datetime import date, time, timedelta

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
from dsms.incidents.exceptions import IncidentValidationError
from dsms.incidents.services import (
    refer_patrol_exception_to_incident,
    refer_patrol_observation_to_incident,
)
from dsms.organization.models import Branch
from dsms.patrol.api.serializers import SERIALIZERS
from dsms.patrol.models import (
    CheckpointNFCCredential,
    CheckpointVisit,
    PatrolCheckpoint,
    PatrolEvent,
    PatrolEvidence,
    PatrolException,
    PatrolObservation,
    PatrolPolicy,
    PatrolRequirement,
    PatrolRoute,
    PatrolRouteCheckpoint,
    PatrolRouteVersion,
    PatrolRun,
    PatrolTask,
)
from dsms.patrol.selectors import get_active_patrol_runs, get_patrol_schedule
from dsms.patrol.services import (
    PatrolValidationError,
    assign_employee_to_patrol,
    complete_patrol,
    evaluate_patrol_eligibility,
    mark_missed_patrols,
    resolve_patrol_policy,
    rotate_checkpoint_qr,
    verify_checkpoint_qr,
    verify_patrol_checkpoint,
)
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
        Permission.objects.filter(content_type__app_label="patrol", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )


def graph(suffix: str, *, user: User | None = None, active: bool = True) -> dict[str, object]:
    if active:
        branch = BranchFactory.create()
    else:
        company = CompanyFactory.create(is_active=False)
        region = RegionFactory.create(company=company)
        branch = BranchFactory.create(company=company, region=region)
    actor = user or UserFactory.create()
    employee = EmployeeFactory.create(
        company=branch.company,
        branch=branch,
        user=actor if user else None,
        employment_status="ACTIVE",
        employee_type="SECURITY_GUARD",
    )
    industry = ClientIndustry.objects.create(
        company=branch.company, code=f"P-{suffix}", name=f"Patrol {suffix}"
    )
    client = Client.objects.create(
        company=branch.company,
        client_code=f"PC-{suffix}",
        legal_name=f"Patrol Client {suffix}",
        industry=industry,
        status="ACTIVE",
    )
    contract = ServiceContract.objects.create(
        company=branch.company,
        client=client,
        contract_number=f"PCTR-{suffix}",
        contract_type="FIXED_TERM",
        title="Patrol",
        start_date=date.today(),
        status="ACTIVE",
        created_by=actor,
    )
    site = SecuritySite.objects.create(
        company=branch.company,
        client=client,
        contract=contract,
        site_code=f"PS-{suffix}",
        name=f"Patrol Site {suffix}",
        managing_branch=branch,
        address_line_1="Street",
        city_name="Islamabad",
        latitude="33.684400",
        longitude="73.047900",
        risk_level="HIGH",
        status="ACTIVE",
    )
    post = SecurityPost.objects.create(
        company=branch.company,
        client=client,
        site=site,
        post_code=f"PP-{suffix}",
        name=f"Post {suffix}",
        status="ACTIVE",
    )
    checkpoint = PatrolCheckpoint.objects.create(
        company=branch.company,
        client=client,
        site=site,
        post=post,
        checkpoint_code=f"CP-{suffix}",
        name=f"Checkpoint {suffix}",
        checkpoint_type="GATE",
        latitude="33.684400",
        longitude="73.047900",
        geofence_radius_meters=50,
        requires_gps=True,
        is_sensitive_location=True,
    )
    route = PatrolRoute.objects.create(
        company=branch.company,
        client=client,
        site=site,
        route_code=f"RT-{suffix}",
        name=f"Route {suffix}",
        status="ACTIVE",
        created_by=actor,
    )
    version = PatrolRouteVersion.objects.create(
        patrol_route=route,
        version_number=1,
        effective_from=date.today(),
        order_mode="STRICT",
        is_current=True,
        created_by=actor,
    )
    route_checkpoint = PatrolRouteCheckpoint.objects.create(
        route_version=version, checkpoint=checkpoint, sequence=1, is_mandatory=True
    )
    requirement = PatrolRequirement.objects.create(
        company=branch.company,
        branch=branch,
        client=client,
        site=site,
        patrol_route=route,
        requirement_code=f"REQ-{suffix}",
        effective_from=date.today(),
        status="ACTIVE",
        start_time=time(8),
        created_by=actor,
    )
    task = PatrolTask.objects.create(
        company=branch.company,
        branch=branch,
        client=client,
        site=site,
        patrol_requirement=requirement,
        patrol_route=route,
        route_version=version,
        task_number=f"TASK-{suffix}",
        scheduled_start_at=timezone.now(),
        scheduled_end_at=timezone.now() + timedelta(hours=1),
        assigned_employee=employee,
        status="READY",
        generated_at=timezone.now(),
        generated_by=actor,
    )
    return {
        "actor": actor,
        "company": branch.company,
        "branch": branch,
        "employee": employee,
        "client": client,
        "contract": contract,
        "site": site,
        "post": post,
        "checkpoint": checkpoint,
        "route": route,
        "version": version,
        "route_checkpoint": route_checkpoint,
        "requirement": requirement,
        "task": task,
    }


def run_for(item: dict[str, object], *, status: str = "IN_PROGRESS") -> PatrolRun:
    task = item["task"]
    task.status = "IN_PROGRESS"
    task.save(update_fields=["status", "updated_at"])
    return PatrolRun.objects.create(
        patrol_task=task,
        company=item["company"],
        site=item["site"],
        employee=item["employee"],
        route_version=item["version"],
        started_at=timezone.now(),
        status=status,
        start_latitude="33.684400",
        start_longitude="73.047900",
        mandatory_checkpoint_count=1,
        total_checkpoint_count=1,
    )


def test_patrol_reads_hide_other_inactive_and_corrupt_rows() -> None:
    a, b, inactive = graph("READ-A"), graph("READ-B"), graph("READ-C", active=False)
    corrupt = PatrolCheckpoint.objects.create(
        company=a["company"],
        client=a["client"],
        site=b["site"],
        checkpoint_code="CP-CORRUPT",
        name="Corrupt",
        checkpoint_type="GATE",
    )
    a_user, b_user, both = UserFactory.create(), UserFactory.create(), UserFactory.create()
    grant(a_user, a["branch"], "view_patrolcheckpoint")
    grant(b_user, b["branch"], "view_patrolcheckpoint")
    grant(both, a["branch"], "view_patrolcheckpoint")
    grant(both, b["branch"], "view_patrolcheckpoint")

    a_rows = api_for(a_user).get("/api/v1/patrol/checkpoints/").json()["results"]
    assert {row["id"] for row in a_rows} == {str(a["checkpoint"].id)}
    b_rows = api_for(b_user).get("/api/v1/patrol/checkpoints/").json()["results"]
    assert {row["id"] for row in b_rows} == {str(b["checkpoint"].id)}
    assert (
        api_for(b_user).get(f"/api/v1/patrol/checkpoints/{a['checkpoint'].id}/").status_code == 404
    )
    both_rows = api_for(both).get("/api/v1/patrol/checkpoints/").json()["results"]
    both_ids = {row["id"] for row in both_rows}
    assert both_ids == {str(a["checkpoint"].id), str(b["checkpoint"].id)}
    assert str(corrupt.id) not in both_ids
    assert str(inactive["checkpoint"].id) not in both_ids
    assert (
        api_for(a_user).get(f"/api/v1/patrol/checkpoints/{b['checkpoint'].id}/").status_code == 404
    )


def test_checkpoint_create_patch_rejects_mixed_graph_and_preserves_company() -> None:
    a, b = graph("WRITE-A"), graph("WRITE-B")
    user = UserFactory.create()
    for item in (a, b):
        grant(
            user,
            item["branch"],
            "view_patrolcheckpoint",
            "add_patrolcheckpoint",
            "change_patrolcheckpoint",
        )
    client = api_for(user)
    payload = {
        "site": str(a["site"].id),
        "post": str(b["post"].id),
        "checkpoint_code": "MIXED",
        "name": "Mixed",
        "checkpoint_type": "GATE",
    }
    assert client.post("/api/v1/patrol/checkpoints/", payload, format="json").status_code == 400
    response = client.patch(
        f"/api/v1/patrol/checkpoints/{a['checkpoint'].id}/",
        {"site": str(b["site"].id)},
        format="json",
    )
    assert response.status_code == 400
    a["checkpoint"].refresh_from_db()
    assert a["checkpoint"].company_id == a["company"].id
    assert a["checkpoint"].site_id == a["site"].id


def test_patch_requires_permission_for_original_scope() -> None:
    a, b = graph("SOURCE-A"), graph("SOURCE-B")
    user = UserFactory.create()
    grant(user, a["branch"], "view_patrolcheckpoint")
    grant(user, b["branch"], "view_patrolcheckpoint", "change_patrolcheckpoint")
    response = api_for(user).patch(
        f"/api/v1/patrol/checkpoints/{a['checkpoint'].id}/",
        {"site": str(b["site"].id)},
        format="json",
    )
    assert response.status_code == 404
    a["checkpoint"].refresh_from_db()
    assert a["checkpoint"].site_id == a["site"].id


def test_workflow_and_evidence_generic_mutation_is_closed() -> None:
    item = graph("READONLY")
    run = run_for(item)
    exception = PatrolException.objects.create(
        company=item["company"],
        patrol_task=item["task"],
        patrol_run=run,
        exception_type="OTHER",
        severity="MEDIUM",
        detected_at=timezone.now(),
        message="Test",
    )
    admin = api_for(UserFactory.create(is_superuser=True))
    assert admin.post("/api/v1/patrol/tasks/", {}, format="json").status_code == 405
    assert admin.patch(f"/api/v1/patrol/runs/{run.id}/", {}, format="json").status_code == 405
    assert (
        admin.patch(
            f"/api/v1/patrol/exceptions/{exception.id}/", {"status": "RESOLVED"}, format="json"
        ).status_code
        == 405
    )
    assert admin.post("/api/v1/patrol/reviews/", {}, format="json").status_code == 405
    assert admin.post("/api/v1/patrol/evidence/", {}, format="json").status_code == 405


def test_task_assignment_scopes_direct_employee_uuid_for_a_b_and_service() -> None:
    a, b = graph("ASSIGN-A"), graph("ASSIGN-B")
    a["task"].assigned_employee = None
    a["task"].status = "SCHEDULED"
    a["task"].save(update_fields=["assigned_employee", "status", "updated_at"])
    a_user, b_user, both = UserFactory.create(), UserFactory.create(), UserFactory.create()
    grant(a_user, a["branch"], "view_patroltask", "assign_patroltask")
    grant(b_user, b["branch"], "view_patroltask", "assign_patroltask")
    grant(both, a["branch"], "view_patroltask", "assign_patroltask")
    grant(both, b["branch"], "view_patroltask", "assign_patroltask")
    assert (
        api_for(a_user)
        .post(
            f"/api/v1/patrol/tasks/{a['task'].id}/assign/",
            {"employee": str(b["employee"].id)},
            format="json",
        )
        .status_code
        == 404
    )
    assert (
        api_for(b_user)
        .post(
            f"/api/v1/patrol/tasks/{a['task'].id}/assign/",
            {"employee": str(a["employee"].id)},
            format="json",
        )
        .status_code
        == 404
    )
    client = api_for(both)
    assert (
        client.post(
            f"/api/v1/patrol/tasks/{a['task'].id}/assign/",
            {"employee": str(b["employee"].id)},
            format="json",
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/patrol/tasks/{a['task'].id}/assign/",
            {"employee": str(a["employee"].id)},
            format="json",
        ).status_code
        == 200
    )
    with pytest.raises(PatrolValidationError):
        assign_employee_to_patrol(patrol_task=a["task"], employee=b["employee"], actor=both)


def test_start_idempotency_is_bound_to_authorized_task_and_tenant() -> None:
    user_a, user_b = UserFactory.create(), UserFactory.create()
    a, b = graph("START-A", user=user_a), graph("START-B", user=user_b)
    grant(user_a, a["branch"], "perform_own_patrol")
    grant(user_b, b["branch"], "perform_own_patrol")
    event_id = uuid.uuid4()
    response_b = api_for(user_b).post(
        "/api/v1/patrol/runs/start/",
        {"patrol_task": str(b["task"].id), "client_event_id": str(event_id)},
        format="json",
    )
    assert response_b.status_code == 201
    response_a = api_for(user_a).post(
        "/api/v1/patrol/runs/start/",
        {"patrol_task": str(a["task"].id), "client_event_id": str(event_id)},
        format="json",
    )
    assert response_a.status_code == 400
    assert PatrolRun.objects.filter(patrol_task=a["task"]).count() == 0


def test_checkpoint_verification_scopes_checkpoint_credential_and_event_id() -> None:
    user_a, user_b = UserFactory.create(), UserFactory.create()
    a, b = graph("VERIFY-A", user=user_a), graph("VERIFY-B", user=user_b)
    grant(user_a, a["branch"], "perform_own_patrol")
    grant(user_b, b["branch"], "perform_own_patrol")
    run_a, run_b = run_for(a), run_for(b)
    _, token_a = rotate_checkpoint_qr(checkpoint=a["checkpoint"], actor=user_a)
    _, token_b = rotate_checkpoint_qr(checkpoint=b["checkpoint"], actor=user_b)
    reused = uuid.uuid4()
    visit_b = verify_patrol_checkpoint(
        actor=user_b,
        patrol_run=run_b,
        checkpoint=b["checkpoint"],
        event_time=timezone.now(),
        qr_token=token_b,
        client_event_id=reused,
    )
    assert visit_b.patrol_run_id == run_b.id
    mixed = api_for(user_a).post(
        f"/api/v1/patrol/runs/{run_a.id}/verify-checkpoint/",
        {"checkpoint": str(b["checkpoint"].id)},
        format="json",
    )
    assert mixed.status_code == 404
    with pytest.raises(PatrolValidationError):
        verify_patrol_checkpoint(
            actor=user_a,
            patrol_run=run_a,
            checkpoint=a["checkpoint"],
            event_time=timezone.now(),
            qr_token=token_a,
            client_event_id=reused,
        )
    corrupt_event = PatrolEvent.objects.create(
        patrol_run=run_a,
        event_type="CHECKPOINT",
        actor_user=user_a,
        employee=a["employee"],
        observed_at=timezone.now(),
    )
    CheckpointVisit.objects.create(
        patrol_run=run_a,
        patrol_event=corrupt_event,
        route_checkpoint=b["route_checkpoint"],
        checkpoint=b["checkpoint"],
        sequence_observed=1,
        observed_at=timezone.now(),
        status="VERIFIED",
        gps_result="VERIFIED",
        token_result="VERIFIED",
        overall_verification_result="VERIFIED",
        verification_method="GPS",
    )
    completed = complete_patrol(actor=user_a, patrol_run=run_a)
    assert completed.status == "INCOMPLETE"
    assert completed.verified_mandatory_count == 0


def test_sensitive_location_requires_permission_in_exact_resource_scope() -> None:
    a, b = graph("GPS-A"), graph("GPS-B")
    run_a, run_b = run_for(a), run_for(b)
    user = UserFactory.create()
    grant(user, a["branch"], "view_patrolrun", "view_patrolcheckpoint")
    grant(
        user,
        b["branch"],
        "view_patrolrun",
        "view_patrolcheckpoint",
        "view_sensitive_patrol_location",
        "view_sensitive_checkpoint_location",
    )
    response_a = api_for(user).get(f"/api/v1/patrol/runs/{run_a.id}/")
    response_b = api_for(user).get(f"/api/v1/patrol/runs/{run_b.id}/")
    assert response_a.status_code == response_b.status_code == 200
    assert "start_latitude" not in response_a.json()
    assert response_b.json()["start_latitude"] == "33.684400"
    checkpoint_a = api_for(user).get(f"/api/v1/patrol/checkpoints/{a['checkpoint'].id}/")
    checkpoint_b = api_for(user).get(f"/api/v1/patrol/checkpoints/{b['checkpoint'].id}/")
    assert "latitude" not in checkpoint_a.json()
    assert checkpoint_b.json()["latitude"] == "33.684400"


def test_evidence_is_private_and_corrupt_parent_graph_is_hidden() -> None:
    a, b = graph("EVID-A"), graph("EVID-B")
    run_a = run_for(a)
    valid = PatrolEvidence.objects.create(
        company=a["company"],
        patrol_run=run_a,
        file="patrol-evidence/aa/private.jpg",
        original_filename="private.jpg",
        file_size=123,
        mime_type="image/jpeg",
        sha256_hash="a" * 64,
        uploaded_by=a["actor"],
    )
    corrupt = PatrolEvidence.objects.create(
        company=b["company"],
        patrol_run=run_a,
        file="patrol-evidence/bb/corrupt.jpg",
        original_filename="corrupt.jpg",
        file_size=456,
        mime_type="image/jpeg",
        sha256_hash="b" * 64,
        uploaded_by=b["actor"],
    )
    user = UserFactory.create()
    grant(user, a["branch"], "view_patrolevidence")
    grant(user, b["branch"], "view_patrolevidence")
    rows = api_for(user).get("/api/v1/patrol/evidence/").json()["results"]
    assert [row["id"] for row in rows] == [str(valid.id)]
    assert "file" not in rows[0]
    assert "sha256_hash" not in rows[0]
    assert api_for(user).get(f"/api/v1/patrol/evidence/{corrupt.id}/").status_code == 404


def test_credential_serializers_never_expose_hash_material() -> None:
    item, other = graph("SECRET"), graph("SECRET-OTHER")
    qr, _ = rotate_checkpoint_qr(checkpoint=item["checkpoint"], actor=item["actor"])
    nfc = CheckpointNFCCredential.objects.create(
        checkpoint=item["checkpoint"],
        public_identifier="NFC-SECRET",
        credential_hash="never-project-this",
        generated_by=item["actor"],
        generated_at=timezone.now(),
    )
    assert "token_hash" not in SERIALIZERS["CheckpointQRCredential"](qr).data
    assert "credential_hash" not in SERIALIZERS["CheckpointNFCCredential"](nfc).data
    assert not verify_checkpoint_qr(
        credential=qr, checkpoint=other["checkpoint"], token="not-returned"
    )


def test_eligibility_referrals_and_corrupt_historical_graphs_fail_closed() -> None:
    a, b = graph("SERVICE-A"), graph("SERVICE-B")
    PatrolPolicy.objects.create(
        company=a["company"],
        branch=b["branch"],
        site=a["site"],
        name="Corrupt policy",
        effective_from=date.today(),
    )
    assert resolve_patrol_policy(company=a["company"], branch=a["branch"], site=a["site"]) is None
    PatrolTask.objects.filter(pk=a["task"].pk).update(site=b["site"])
    a["task"].refresh_from_db()
    result = evaluate_patrol_eligibility(employee=a["employee"], patrol_task=a["task"])
    assert result.status == "INELIGIBLE"
    assert result.reasons == ("PATROL_TASK_TENANT_GRAPH_INVALID",)

    run_a = PatrolRun.objects.create(
        patrol_task=b["task"],
        company=b["company"],
        site=b["site"],
        employee=b["employee"],
        route_version=b["version"],
        started_at=timezone.now(),
    )
    observation = PatrolObservation.objects.create(
        company=a["company"],
        patrol_run=run_a,
        site=a["site"],
        category="SECURITY",
        title="Corrupt",
        description="Cross tenant",
        severity="HIGH",
        observed_at=timezone.now(),
        created_by=a["actor"],
    )
    exception = PatrolException.objects.create(
        company=a["company"],
        patrol_task=b["task"],
        patrol_run=run_a,
        exception_type="OTHER",
        severity="HIGH",
        detected_at=timezone.now(),
        message="Cross tenant",
    )
    admin = UserFactory.create(is_superuser=True)
    with pytest.raises(IncidentValidationError):
        refer_patrol_observation_to_incident(observation=observation, actor=admin, reason="No leak")
    with pytest.raises(IncidentValidationError):
        refer_patrol_exception_to_incident(exception=exception, actor=admin, reason="No leak")


def test_dashboard_selectors_and_missed_task_processing_ignore_invalid_tenants() -> None:
    valid, mixed, inactive = (
        graph("TASK-VALID"),
        graph("TASK-MIXED"),
        graph("TASK-INACTIVE", active=False),
    )
    now = timezone.now()
    for item in (valid, mixed, inactive):
        PatrolTask.objects.filter(pk=item["task"].pk).update(
            status="SCHEDULED", scheduled_end_at=now - timedelta(minutes=1)
        )
    PatrolTask.objects.filter(pk=mixed["task"].pk).update(site=valid["site"])
    user = UserFactory.create()
    grant(user, valid["branch"], "view_patrol_dashboard")
    response = api_for(user).get("/api/v1/patrol/dashboard/summary/")
    assert response.status_code == 200
    assert response.json()["scheduled"] == 1
    assert list(get_patrol_schedule(company=valid["company"])) == [valid["task"]]
    assert list(get_active_patrol_runs(company=valid["company"])) == []
    assert mark_missed_patrols(at=now) == 1
    valid["task"].refresh_from_db()
    mixed["task"].refresh_from_db()
    inactive["task"].refresh_from_db()
    assert valid["task"].status == "MISSED"
    assert mixed["task"].status == "SCHEDULED"
    assert inactive["task"].status == "SCHEDULED"
