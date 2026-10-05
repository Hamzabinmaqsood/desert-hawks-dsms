# mypy: disable-error-code="arg-type,attr-defined,misc,no-untyped-call"
from __future__ import annotations

from datetime import date, time, timedelta
from unittest.mock import patch

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
    StaffingRequirement,
)
from dsms.deployment.models import (
    DeploymentPool,
    DeploymentPoolMembership,
    DutyAssignment,
    DutyShift,
    EmployeeDeployment,
    ReplacementRequest,
    RosterAvailabilityConflict,
    RosterChangeEvent,
    RosterPeriod,
)
from dsms.deployment.selectors import get_roster, get_unfilled_positions
from dsms.deployment.services import evaluate_deployment_eligibility
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from dsms.leave.models import LeavePolicy, LeavePolicyRule, LeaveRequest, LeaveType
from dsms.organization.models import Branch
from dsms.workforce.models import Employee
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def api_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def grant(user: User, branch: Branch, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.set(
        Permission.objects.filter(content_type__app_label="deployment", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH,
        company=branch.company,
        branch=branch,
    )


def graph(suffix: str, *, duty_date: date | None = None) -> dict[str, object]:
    branch = BranchFactory.create()
    actor = UserFactory.create()
    employee = EmployeeFactory.create(
        company=branch.company,
        branch=branch,
        employment_status="ACTIVE",
        employee_type="SECURITY_GUARD",
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
    duty_day = duty_date or date.today() + timedelta(days=1)
    start = timezone.now().replace(microsecond=0) + timedelta(days=(duty_day - date.today()).days)
    roster = RosterPeriod.objects.create(
        company=branch.company,
        branch=branch,
        roster_number=f"ROS-{suffix}",
        name=f"Roster {suffix}",
        period_start=duty_day,
        period_end=duty_day,
        status="GENERATED",
        created_by=actor,
    )
    shift = DutyShift.objects.create(
        roster_period=roster,
        company=branch.company,
        branch=branch,
        client=client,
        contract=contract,
        site=site,
        post=post,
        duty_date=duty_day,
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        required_headcount=2,
        employee_type="SECURITY_GUARD",
    )
    return {
        "branch": branch,
        "company": branch.company,
        "actor": actor,
        "employee": employee,
        "client": client,
        "contract": contract,
        "site": site,
        "post": post,
        "roster": roster,
        "shift": shift,
    }


def assignment(item: dict[str, object], employee: Employee | None = None) -> DutyAssignment:
    return DutyAssignment.objects.create(
        duty_shift=item["shift"],
        employee=employee or item["employee"],
        assignment_type="REGULAR",
        status="PLANNED",
        assigned_by=item["actor"],
    )


def leave_request(item: dict[str, object], suffix: str) -> LeaveRequest:
    leave_type = LeaveType.objects.create(
        company=item["company"],
        code=f"LT-{suffix}",
        name=f"Leave {suffix}",
        unit="DAYS",
        pay_treatment="PAID",
    )
    policy = LeavePolicy.objects.create(
        company=item["company"],
        code=f"LP-{suffix}",
        name=f"Policy {suffix}",
        effective_from=date.today(),
    )
    rule = LeavePolicyRule.objects.create(
        policy=policy,
        leave_type=leave_type,
        entitlement_units=10,
    )
    now = timezone.now()
    return LeaveRequest.objects.create(
        request_number=f"LR-{suffix}",
        company=item["company"],
        employee=item["employee"],
        leave_type=leave_type,
        policy=policy,
        policy_rule=rule,
        starts_at=now,
        ends_at=now + timedelta(days=1),
        requested_units=1,
        reason="Test",
        created_by=item["actor"],
    )


def test_deployment_read_matrix_hides_mixed_and_inactive_rows() -> None:
    a, b, c = graph("READ-A"), graph("READ-B"), graph("READ-C")
    c["company"].is_active = False
    c["company"].save(update_fields=["is_active"])
    corrupt = RosterPeriod.objects.create(
        company=a["company"],
        branch=b["branch"],
        roster_number="ROS-CORRUPT",
        name="Corrupt",
        period_start=date.today(),
        period_end=date.today(),
        created_by=a["actor"],
    )
    user_a, user_b, user_ab = UserFactory.create_batch(3)
    grant(user_a, a["branch"], "view_rosterperiod")
    grant(user_b, b["branch"], "view_rosterperiod")
    for item in (a, b, c):
        grant(user_ab, item["branch"], "view_rosterperiod")

    def ids(user: User) -> set[str]:
        response = api_for(user).get("/api/v1/deployment/rosters/")
        assert response.status_code == 200
        return {row["id"] for row in response.data["results"]}

    assert ids(user_a) == {str(a["roster"].id)}
    assert ids(user_b) == {str(b["roster"].id)}
    assert ids(user_ab) == {str(a["roster"].id), str(b["roster"].id)}
    assert api_for(user_ab).get(f"/api/v1/deployment/rosters/{corrupt.id}/").status_code == 404


def test_deployment_crud_derives_company_and_rejects_mixed_resulting_state() -> None:
    a, b = graph("CRUD-A"), graph("CRUD-B")
    user = UserFactory.create()
    permissions = (
        "view_employeedeployment",
        "add_employeedeployment",
        "change_employeedeployment",
        "view_deploymentpool",
        "add_deploymentpool",
        "view_deploymentpoolmembership",
        "add_deploymentpoolmembership",
    )
    grant(user, a["branch"], *permissions)
    grant(user, b["branch"], *permissions)
    api = api_for(user)
    created = api.post(
        "/api/v1/deployment/deployments/",
        {
            "company": str(b["company"].id),
            "employee": str(a["employee"].id),
            "client": str(a["client"].id),
            "contract": str(a["contract"].id),
            "site": str(a["site"].id),
            "primary_post": str(a["post"].id),
            "managing_branch": str(a["branch"].id),
            "deployment_type": "REGULAR",
            "effective_from": str(date.today()),
            "status": "ACTIVE",
            "created_by": str(b["actor"].id),
        },
        format="json",
    )
    assert created.status_code == 201
    stored = EmployeeDeployment.objects.get(pk=created.data["id"])
    assert stored.company_id == a["company"].id
    assert stored.status == "DRAFT" and stored.created_by_id == user.id
    mixed = api.post(
        "/api/v1/deployment/deployments/",
        {
            "employee": str(b["employee"].id),
            "client": str(a["client"].id),
            "contract": str(a["contract"].id),
            "site": str(a["site"].id),
            "managing_branch": str(a["branch"].id),
            "deployment_type": "REGULAR",
            "effective_from": str(date.today()),
        },
        format="json",
    )
    assert mixed.status_code == 400
    patched = api.patch(
        f"/api/v1/deployment/deployments/{stored.id}/",
        {"employee": str(b["employee"].id)},
        format="json",
    )
    assert patched.status_code == 400
    stored.refresh_from_db()
    assert stored.employee_id == a["employee"].id

    pool_response = api.post(
        "/api/v1/deployment/deployment-pools/",
        {"branch": str(a["branch"].id), "code": "POOL-A", "name": "Pool A"},
        format="json",
    )
    assert pool_response.status_code == 201
    pool = DeploymentPool.objects.get(pk=pool_response.data["id"])
    assert pool.company_id == a["company"].id
    assert (
        api.post(
            "/api/v1/deployment/pool-memberships/",
            {
                "pool": str(pool.id),
                "employee": str(b["employee"].id),
                "effective_from": str(date.today()),
            },
            format="json",
        ).status_code
        == 400
    )


def test_patch_requires_change_permission_in_the_existing_scope() -> None:
    a, b = graph("PATCH-SOURCE-A"), graph("PATCH-SOURCE-B")
    pool_a = DeploymentPool.objects.create(
        company=a["company"], branch=a["branch"], code="POOL-SOURCE-A", name="Pool A"
    )
    pool_b = DeploymentPool.objects.create(
        company=b["company"], branch=b["branch"], code="POOL-SOURCE-B", name="Pool B"
    )
    membership = DeploymentPoolMembership.objects.create(
        pool=pool_a, employee=a["employee"], effective_from=date.today()
    )
    user = UserFactory.create()
    grant(user, a["branch"], "view_deploymentpoolmembership")
    grant(
        user,
        b["branch"],
        "view_deploymentpoolmembership",
        "change_deploymentpoolmembership",
    )
    response = api_for(user).patch(
        f"/api/v1/deployment/pool-memberships/{membership.id}/",
        {"pool": str(pool_b.id), "employee": str(b["employee"].id)},
        format="json",
    )
    assert response.status_code == 404
    membership.refresh_from_db()
    assert membership.pool_id == pool_a.id and membership.employee_id == a["employee"].id


def test_duty_shift_create_patch_and_server_fields_are_tenant_safe() -> None:
    a, b = graph("SHIFT-A"), graph("SHIFT-B")
    user = UserFactory.create()
    for item in (a, b):
        grant(user, item["branch"], "view_dutyshift", "add_dutyshift", "change_dutyshift")
    api = api_for(user)
    start = timezone.now() + timedelta(days=2)
    payload = {
        "roster_period": str(a["roster"].id),
        "company": str(b["company"].id),
        "branch": str(b["branch"].id),
        "client": str(a["client"].id),
        "contract": str(a["contract"].id),
        "site": str(a["site"].id),
        "post": str(a["post"].id),
        "duty_date": str(start.date()),
        "starts_at": start.isoformat(),
        "ends_at": (start + timedelta(hours=8)).isoformat(),
        "required_headcount": 1,
        "employee_type": "SECURITY_GUARD",
        "status": "PUBLISHED",
    }
    response = api.post("/api/v1/deployment/duty-shifts/", payload, format="json")
    assert response.status_code == 201
    shift = DutyShift.objects.get(pk=response.data["id"])
    assert shift.company_id == a["company"].id and shift.branch_id == a["branch"].id
    assert shift.status == "PLANNED"
    mixed_payload = payload | {
        "site": str(b["site"].id),
        "post": str(b["post"].id),
    }
    assert (
        api.post("/api/v1/deployment/duty-shifts/", mixed_payload, format="json").status_code == 400
    )
    assert (
        api.patch(
            f"/api/v1/deployment/duty-shifts/{shift.id}/",
            {"site": str(b["site"].id), "post": str(b["post"].id)},
            format="json",
        ).status_code
        == 400
    )
    shift.refresh_from_db()
    assert shift.site_id == a["site"].id


def test_assignment_action_coverage_and_dashboard_exclude_mixed_employee() -> None:
    a, b = graph("ASSIGN-A", duty_date=date.today()), graph("ASSIGN-B")
    user = UserFactory.create()
    for item in (a, b):
        grant(
            user,
            item["branch"],
            "view_dutyshift",
            "view_dutyassignment",
            "assign_employee",
        )
    api = api_for(user)
    assert (
        api.post(
            f"/api/v1/deployment/duty-shifts/{a['shift'].id}/assign/", {}, format="json"
        ).status_code
        == 400
    )
    assigned = api.post(
        f"/api/v1/deployment/duty-shifts/{a['shift'].id}/assign/",
        {"employee": str(a["employee"].id)},
        format="json",
    )
    assert assigned.status_code == 201
    assert (
        api.post(
            f"/api/v1/deployment/duty-shifts/{a['shift'].id}/assign/",
            {"employee": str(b["employee"].id)},
            format="json",
        ).status_code
        == 404
    )
    corrupt = assignment(a, b["employee"])
    second_employee = EmployeeFactory.create(
        company=a["company"],
        branch=a["branch"],
        employment_status="ACTIVE",
        employee_type="SECURITY_GUARD",
    )
    foreign_deployment = EmployeeDeployment.objects.create(
        company=b["company"],
        employee=b["employee"],
        client=b["client"],
        contract=b["contract"],
        site=b["site"],
        primary_post=b["post"],
        managing_branch=b["branch"],
        deployment_type="REGULAR",
        effective_from=date.today(),
        created_by=b["actor"],
    )
    corrupt_original = DutyAssignment.objects.create(
        duty_shift=a["shift"],
        employee=second_employee,
        deployment=foreign_deployment,
        assignment_type="REGULAR",
        status="REPLACED",
        assigned_by=a["actor"],
    )
    corrupt_replacement = DutyAssignment.objects.create(
        duty_shift=a["shift"],
        employee=second_employee,
        assignment_type="REPLACEMENT",
        status="PLANNED",
        assigned_by=a["actor"],
        replaces_assignment=corrupt_original,
    )
    coverage = api.get(f"/api/v1/deployment/duty-shifts/{a['shift'].id}/coverage/")
    assert coverage.status_code == 200 and coverage.data["assigned_headcount"] == 1
    dashboard = api.get("/api/v1/deployment/dashboard/summary/")
    assert dashboard.status_code == 200
    assert dashboard.data["today_assigned_positions"] == 1
    assert list(get_unfilled_positions(roster=a["roster"])) == [a["shift"]]
    selected_shift = get_roster(roster_id=a["roster"].id).duty_shifts.all()[0]
    assert {item.id for item in selected_shift.assignments.all()} == {
        DutyAssignment.objects.get(duty_shift=a["shift"], employee=a["employee"]).id
    }
    listed_ids = {
        row["id"] for row in api.get("/api/v1/deployment/duty-assignments/").data["results"]
    }
    assert str(corrupt.id) not in listed_ids
    assert str(corrupt_replacement.id) not in listed_ids


def test_replacement_workflow_scopes_employee_and_generic_mutation_is_closed() -> None:
    a, b = graph("REPLACE-A"), graph("REPLACE-B")
    original = assignment(a)
    replacement = EmployeeFactory.create(
        company=a["company"],
        branch=a["branch"],
        employment_status="ACTIVE",
        employee_type="SECURITY_GUARD",
    )
    user = UserFactory.create()
    for item in (a, b):
        grant(
            user,
            item["branch"],
            "view_dutyassignment",
            "add_dutyassignment",
            "view_replacementrequest",
            "add_replacementrequest",
            "replace_employee",
        )
    api = api_for(user)
    assert (
        api.post(
            f"/api/v1/deployment/duty-assignments/{original.id}/request-replacement/",
            {"priority": "FORGED"},
            format="json",
        ).status_code
        == 400
    )
    assert not ReplacementRequest.objects.filter(original_assignment=original).exists()
    requested = api.post(
        f"/api/v1/deployment/duty-assignments/{original.id}/request-replacement/",
        {"reason": "OTHER", "priority": "URGENT"},
        format="json",
    )
    assert requested.status_code == 201
    request = ReplacementRequest.objects.get(pk=requested.data["id"])
    assert request.company_id == a["company"].id and request.requested_by_id == user.id
    assert (
        api.post(
            f"/api/v1/deployment/replacement-requests/{request.id}/assign-replacement/",
            {"employee": str(b["employee"].id)},
            format="json",
        ).status_code
        == 404
    )
    completed = api.post(
        f"/api/v1/deployment/replacement-requests/{request.id}/assign-replacement/",
        {"employee": str(replacement.id)},
        format="json",
    )
    assert completed.status_code == 201
    assert api.post("/api/v1/deployment/duty-assignments/", {}, format="json").status_code == 405
    assert (
        api.post("/api/v1/deployment/replacement-requests/", {}, format="json").status_code == 405
    )


def test_eligibility_rejects_ab_mixed_company_and_wrong_post() -> None:
    a, b = graph("ELIG-A"), graph("ELIG-B")
    user = UserFactory.create()
    grant(user, a["branch"], "view_dutyshift")
    grant(user, b["branch"], "view_dutyshift")
    api = api_for(user)
    valid = api.get(
        f"/api/v1/deployment/eligibility/employees/{a['employee'].id}/?site={a['site'].id}&post={a['post'].id}"
    )
    assert valid.status_code == 200
    assert (
        api.get(
            f"/api/v1/deployment/eligibility/employees/{a['employee'].id}/?site={b['site'].id}&post={b['post'].id}"
        ).status_code
        == 404
    )
    assert (
        api.get(
            f"/api/v1/deployment/eligibility/employees/{a['employee'].id}/?site={a['site'].id}&post={b['post'].id}"
        ).status_code
        == 404
    )


def test_service_eligibility_short_circuits_cross_company_relations() -> None:
    a, b = graph("ELIG-SVC-A"), graph("ELIG-SVC-B")
    with (
        patch(
            "dsms.deployment.services.evaluate_employee_readiness",
            side_effect=AssertionError("readiness must not inspect a mixed tenant request"),
        ),
        patch(
            "dsms.deployment.services.evaluate_employee_availability",
            side_effect=AssertionError("availability must not inspect a mixed tenant request"),
        ),
    ):
        result = evaluate_deployment_eligibility(
            employee=a["employee"],
            site=b["site"],
            post=b["post"],
            duty_shift=b["shift"],
        )
    assert result.status == "INELIGIBLE"
    assert result.blocking_reasons == ("CROSS_COMPANY_MISMATCH",)

    other_post = SecurityPost.objects.create(
        company=a["company"],
        client=a["client"],
        site=a["site"],
        post_code="POST-ELIG-SVC-OTHER",
        name="Other post",
        status="ACTIVE",
    )
    with patch(
        "dsms.deployment.services.evaluate_employee_readiness",
        side_effect=AssertionError("readiness must not inspect a mismatched Shift/Post"),
    ):
        mismatch = evaluate_deployment_eligibility(
            employee=a["employee"],
            site=a["site"],
            post=other_post,
            duty_shift=a["shift"],
        )
    assert mismatch.blocking_reasons == ("SHIFT_TENANT_INCONSISTENT",)


def test_roster_lifecycle_uses_server_actors_and_blocks_corrupt_graph() -> None:
    a, b = graph("FLOW-A"), graph("FLOW-B")
    roster = a["roster"]
    roster.status = "DRAFT"
    roster.save(update_fields=["status", "updated_at"])
    a["shift"].delete()
    StaffingRequirement.objects.create(
        company=a["company"],
        contract=a["contract"],
        site=a["site"],
        post=a["post"],
        requirement_code="REQ-FLOW-A",
        employee_type="SECURITY_GUARD",
        required_headcount=1,
        coverage_type="FIXED",
        start_time=time(8),
        end_time=time(16),
        effective_from=roster.period_start,
        status="ACTIVE",
    )
    maker, checker = UserFactory.create_batch(2)
    grant(maker, a["branch"], "view_rosterperiod", "change_rosterperiod", "generate_roster")
    grant(
        checker,
        a["branch"],
        "view_rosterperiod",
        "approve_roster",
        "publish_roster",
        "lock_roster",
    )
    assert (
        api_for(maker).post(f"/api/v1/deployment/rosters/{roster.id}/generate-demand/").status_code
        == 200
    )
    roster.refresh_from_db()
    assert roster.generated_by_id == maker.id and roster.status == "GENERATED"
    assert api_for(maker).post(f"/api/v1/deployment/rosters/{roster.id}/submit/").status_code == 200
    assert (
        api_for(checker).post(f"/api/v1/deployment/rosters/{roster.id}/approve/").status_code == 200
    )
    assert (
        api_for(checker).post(f"/api/v1/deployment/rosters/{roster.id}/publish/").status_code == 200
    )
    assert api_for(checker).post(f"/api/v1/deployment/rosters/{roster.id}/lock/").status_code == 200

    corrupt_roster = RosterPeriod.objects.create(
        company=a["company"],
        branch=a["branch"],
        roster_number="ROS-FLOW-CORRUPT",
        name="Corrupt flow",
        period_start=date.today(),
        period_end=date.today(),
        status="GENERATED",
        created_by=a["actor"],
    )
    start = timezone.now()
    DutyShift.objects.create(
        roster_period=corrupt_roster,
        company=a["company"],
        branch=a["branch"],
        client=b["client"],
        contract=b["contract"],
        site=b["site"],
        post=b["post"],
        duty_date=date.today(),
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        required_headcount=1,
        employee_type="SECURITY_GUARD",
    )
    assert (
        api_for(maker).post(f"/api/v1/deployment/rosters/{corrupt_roster.id}/submit/").status_code
        == 400
    )


def test_roster_evidence_and_conflicts_hide_corrupt_relations_and_are_read_only() -> None:
    a, b = graph("EVID-A"), graph("EVID-B")
    assignment_a, assignment_b = assignment(a), assignment(b)
    valid_change = RosterChangeEvent.objects.create(
        roster_period=a["roster"],
        duty_shift=a["shift"],
        duty_assignment=assignment_a,
        change_type="ASSIGNED",
        actor=a["actor"],
        new_employee=a["employee"],
    )
    corrupt_change = RosterChangeEvent.objects.create(
        roster_period=a["roster"],
        duty_shift=b["shift"],
        duty_assignment=assignment_b,
        change_type="ASSIGNED",
        actor=a["actor"],
        new_employee=b["employee"],
    )
    leave_a, leave_b = leave_request(a, "EVID-A"), leave_request(b, "EVID-B")
    valid_conflict = RosterAvailabilityConflict.objects.create(
        company=a["company"], duty_assignment=assignment_a, leave_request=leave_a
    )
    corrupt_conflict = RosterAvailabilityConflict.objects.create(
        company=a["company"], duty_assignment=assignment_a, leave_request=leave_b
    )
    user = UserFactory.create()
    for item in (a, b):
        grant(
            user,
            item["branch"],
            "view_rosterchangeevent",
            "add_rosterchangeevent",
            "view_rosteravailabilityconflict",
            "add_rosteravailabilityconflict",
        )
    api = api_for(user)
    changes = {row["id"] for row in api.get("/api/v1/deployment/roster-changes/").data["results"]}
    conflicts = {
        row["id"] for row in api.get("/api/v1/deployment/availability-conflicts/").data["results"]
    }
    assert changes == {str(valid_change.id)} and str(corrupt_change.id) not in changes
    assert conflicts == {str(valid_conflict.id)} and str(corrupt_conflict.id) not in conflicts
    assert api.post("/api/v1/deployment/roster-changes/", {}, format="json").status_code == 405
    assert (
        api.post("/api/v1/deployment/availability-conflicts/", {}, format="json").status_code == 405
    )
