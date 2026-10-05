# mypy: disable-error-code="arg-type,attr-defined,misc,no-untyped-call"
from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.attendance.models import (
    AttendanceEvent,
    AttendanceException,
    AttendancePolicy,
    AttendanceQRStation,
    AttendanceRecord,
    AttendanceVerification,
)
from dsms.attendance.tasks import detect_attendance_missing_checkout
from dsms.contracts.models import (
    Client,
    ClientIndustry,
    SecurityPost,
    SecuritySite,
    ServiceContract,
    SiteType,
)
from dsms.deployment.models import DutyAssignment, DutyShift, RosterPeriod
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from dsms.incidents.exceptions import IncidentValidationError
from dsms.incidents.models import Incident
from dsms.incidents.services import refer_supervision_finding_to_incident
from dsms.organization.models import Branch
from dsms.supervision.models import (
    CorrectiveAction,
    FieldEvidence,
    InspectionFinding,
    InspectionTemplate,
    SiteInspection,
    SiteVisit,
    SupervisionAssignment,
)
from dsms.supervision.tasks import detect_overdue_corrective_actions
from dsms.workforce.models import Employee
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def grant(user: User, branch: Branch, app: str, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.set(
        Permission.objects.filter(content_type__app_label=app, codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=branch.company,
    )


def tenant_graph(suffix: str) -> dict[str, object]:
    branch = BranchFactory.create()
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
    return {
        "branch": branch,
        "company": branch.company,
        "actor": actor,
        "client": client,
        "contract": contract,
        "site": site,
        "post": post,
    }


def duty_assignment(
    graph: dict[str, object], employee: Employee, actor: User, suffix: str
) -> DutyAssignment:
    branch = graph["branch"]
    start = timezone.now() - timedelta(hours=1)
    roster = RosterPeriod.objects.create(
        company=graph["company"],
        branch=branch,
        roster_number=f"ROS-{suffix}",
        name=f"Roster {suffix}",
        period_start=start.date(),
        period_end=start.date(),
        status="PUBLISHED",
        created_by=actor,
    )
    shift = DutyShift.objects.create(
        roster_period=roster,
        company=graph["company"],
        branch=branch,
        client=graph["client"],
        contract=graph["contract"],
        site=graph["site"],
        post=graph["post"],
        duty_date=start.date(),
        starts_at=start,
        ends_at=start + timedelta(hours=8),
        required_headcount=1,
        employee_type="SECURITY_GUARD",
    )
    return DutyAssignment.objects.create(
        duty_shift=shift,
        employee=employee,
        assignment_type="REGULAR",
        status="PLANNED",
        assigned_by=actor,
    )


def attendance_record(
    graph: dict[str, object], assignment: DutyAssignment, *, checked_in: bool = False
) -> AttendanceRecord:
    shift = assignment.duty_shift
    return AttendanceRecord.objects.create(
        company=graph["company"],
        branch=graph["branch"],
        client=graph["client"],
        site=graph["site"],
        post=graph["post"],
        employee=assignment.employee,
        duty_assignment=assignment,
        scheduled_start_at=shift.starts_at,
        scheduled_end_at=timezone.now() - timedelta(minutes=1),
        actual_check_in_at=shift.starts_at if checked_in else None,
        status="IN_PROGRESS" if checked_in else "PENDING",
    )


def supervision_chain(
    graph: dict[str, object], suffix: str, *, supervisor: Employee | None = None
) -> tuple[SiteVisit, SiteInspection, InspectionFinding]:
    supervisor = supervisor or EmployeeFactory.create(
        company=graph["company"],
        branch=graph["branch"],
        user=UserFactory.create(),
        employee_type="SUPERVISOR",
        employment_status="ACTIVE",
    )
    visit = SiteVisit.objects.create(
        company=graph["company"],
        supervisor=supervisor,
        branch=graph["branch"],
        site=graph["site"],
        started_at=timezone.now(),
        status="IN_PROGRESS",
        verification_method="SUPERVISOR_MANUAL",
        verification_result="NOT_REQUIRED",
    )
    template = InspectionTemplate.objects.create(
        company=graph["company"],
        code=f"TPL-{suffix}",
        name=f"Template {suffix}",
        scope="SITE",
        effective_from=date.today(),
    )
    inspection = SiteInspection.objects.create(
        company=graph["company"],
        site_visit=visit,
        site=graph["site"],
        template=template,
        template_version=1,
        scope="SITE",
        status="IN_PROGRESS",
        started_at=timezone.now(),
        created_by=graph["actor"],
    )
    finding = InspectionFinding.objects.create(
        company=graph["company"],
        inspection=inspection,
        site=graph["site"],
        title=f"Finding {suffix}",
        description="Test",
        severity="HIGH",
        identified_by=graph["actor"],
        identified_at=timezone.now(),
    )
    return visit, inspection, finding


def test_attendance_crud_scopes_relations_and_protects_server_fields() -> None:
    a, b, c = tenant_graph("ATT-A"), tenant_graph("ATT-B"), tenant_graph("ATT-C")
    c["company"].is_active = False
    c["company"].save(update_fields=["is_active"])
    user = UserFactory.create()
    permissions = (
        "view_attendancepolicy",
        "add_attendancepolicy",
        "change_attendancepolicy",
        "view_attendanceqrstation",
        "add_attendanceqrstation",
        "change_attendanceqrstation",
    )
    for graph in (a, b, c):
        grant(user, graph["branch"], "attendance", *permissions)
    api = client_for(user)

    valid = api.post(
        "/api/v1/attendance/policies/",
        {
            "company": str(a["company"].id),
            "branch": str(a["branch"].id),
            "name": "A policy",
            "effective_from": str(date.today()),
        },
        format="json",
    )
    assert valid.status_code == 201
    mixed = api.post(
        "/api/v1/attendance/policies/",
        {
            "company": str(a["company"].id),
            "branch": str(b["branch"].id),
            "name": "Mixed",
            "effective_from": str(date.today()),
        },
        format="json",
    )
    assert mixed.status_code == 400
    patch = api.patch(
        f"/api/v1/attendance/policies/{valid.data['id']}/",
        {"company": str(b["company"].id), "branch": str(b["branch"].id)},
        format="json",
    )
    assert patch.status_code == 400
    stored = AttendancePolicy.objects.get(pk=valid.data["id"])
    assert stored.company_id == a["company"].id and stored.branch_id == a["branch"].id

    qr = api.post(
        "/api/v1/attendance/qr-stations/",
        {
            "company": str(a["company"].id),
            "site": str(a["site"].id),
            "post": str(a["post"].id),
            "station_code": "SECURE-A",
            "name": "Secure station",
            "status": "REVOKED",
            "generated_by": str(b["actor"].id),
            "token_hash": "forged",
        },
        format="json",
    )
    assert qr.status_code == 201
    station = AttendanceQRStation.objects.get(pk=qr.data["id"])
    assert station.status == "ACTIVE" and station.generated_by_id == user.id
    assert "token_hash" not in qr.data
    rotated = api.post(f"/api/v1/attendance/qr-stations/{station.id}/rotate/")
    assert rotated.status_code == 200
    station.refresh_from_db()
    assert rotated.data["token"] not in station.token_hash

    split_scope_user = UserFactory.create()
    grant(split_scope_user, a["branch"], "attendance", "view_attendanceqrstation")
    grant(split_scope_user, b["branch"], "attendance", "change_attendanceqrstation")
    assert (
        client_for(split_scope_user)
        .post(f"/api/v1/attendance/qr-stations/{station.id}/rotate/")
        .status_code
        == 404
    )

    corrupt = AttendancePolicy.objects.create(
        company=a["company"],
        branch=b["branch"],
        name="Corrupt",
        effective_from=date.today(),
    )
    inactive = AttendancePolicy.objects.create(
        company=c["company"], name="Inactive", effective_from=date.today()
    )
    listed = api.get("/api/v1/attendance/policies/")
    ids = {row["id"] for row in listed.data["results"]}
    assert str(stored.id) in ids
    assert str(corrupt.id) not in ids and str(inactive.id) not in ids
    assert api.get(f"/api/v1/attendance/policies/{corrupt.id}/").status_code == 404


def test_attendance_a_b_and_ab_read_matrix() -> None:
    a, b, c = tenant_graph("READ-A"), tenant_graph("READ-B"), tenant_graph("READ-C")
    policy_a = AttendancePolicy.objects.create(
        company=a["company"], branch=a["branch"], name="A", effective_from=date.today()
    )
    policy_b = AttendancePolicy.objects.create(
        company=b["company"], branch=b["branch"], name="B", effective_from=date.today()
    )
    policy_c = AttendancePolicy.objects.create(
        company=c["company"], branch=c["branch"], name="C", effective_from=date.today()
    )
    c["company"].is_active = False
    c["company"].save(update_fields=["is_active"])

    user_a, user_b, user_ab = UserFactory.create_batch(3)
    grant(user_a, a["branch"], "attendance", "view_attendancepolicy")
    grant(user_b, b["branch"], "attendance", "view_attendancepolicy")
    grant(user_ab, a["branch"], "attendance", "view_attendancepolicy")
    grant(user_ab, b["branch"], "attendance", "view_attendancepolicy")
    grant(user_ab, c["branch"], "attendance", "view_attendancepolicy")

    def ids_for(user: User) -> set[str]:
        response = client_for(user).get("/api/v1/attendance/policies/")
        assert response.status_code == 200
        return {row["id"] for row in response.data["results"]}

    assert ids_for(user_a) == {str(policy_a.id)}
    assert ids_for(user_b) == {str(policy_b.id)}
    assert ids_for(user_ab) == {str(policy_a.id), str(policy_b.id)}
    assert str(policy_c.id) not in ids_for(user_ab)


def test_attendance_nested_verification_scoping_and_consistency() -> None:
    a, b = tenant_graph("VERIFY-A"), tenant_graph("VERIFY-B")
    guard_a = EmployeeFactory.create(company=a["company"], branch=a["branch"])
    guard_b = EmployeeFactory.create(company=b["company"], branch=b["branch"])
    record_a = attendance_record(
        a, duty_assignment(a, guard_a, a["actor"], "VERIFY-A"), checked_in=True
    )
    record_b = attendance_record(
        b, duty_assignment(b, guard_b, b["actor"], "VERIFY-B"), checked_in=True
    )
    event_a = AttendanceEvent.objects.create(
        attendance_record=record_a,
        event_type="CHECK_IN",
        subject_employee=guard_a,
        observed_at=timezone.now(),
    )
    event_b = AttendanceEvent.objects.create(
        attendance_record=record_b,
        event_type="CHECK_IN",
        subject_employee=guard_b,
        observed_at=timezone.now(),
    )
    station_a = AttendanceQRStation.objects.create(
        company=a["company"],
        site=a["site"],
        post=a["post"],
        station_code="VERIFY-A",
        name="A",
        token_hash="hash-a",
        generated_by=a["actor"],
        generated_at=timezone.now(),
    )
    station_b = AttendanceQRStation.objects.create(
        company=b["company"],
        site=b["site"],
        post=b["post"],
        station_code="VERIFY-B",
        name="B",
        token_hash="hash-b",
        generated_by=b["actor"],
        generated_at=timezone.now(),
    )
    valid_a = AttendanceVerification.objects.create(
        attendance_event=event_a,
        method="QR",
        result="PASSED",
        qr_station=station_a,
        latitude="33.684400",
        provider_reference="provider-a",
    )
    valid_b = AttendanceVerification.objects.create(
        attendance_event=event_b,
        method="QR",
        result="PASSED",
        qr_station=station_b,
        latitude="31.520400",
        provider_reference="provider-b",
    )
    corrupt = AttendanceVerification.objects.create(
        attendance_event=event_a, method="QR", result="PASSED", qr_station=station_b
    )
    user_a, user_b, user_ab = UserFactory.create_batch(3)
    for user, graph in ((user_a, a), (user_b, b)):
        grant(user, graph["branch"], "attendance", "view_attendanceverification")
    grant(user_ab, a["branch"], "attendance", "view_attendanceverification")
    grant(user_ab, b["branch"], "attendance", "view_attendanceverification")
    grant(
        user_ab,
        a["branch"],
        "attendance",
        "view_sensitive_location_data",
        "view_biometric_verification_details",
    )

    def ids_for(user: User) -> set[str]:
        response = client_for(user).get("/api/v1/attendance/verifications/")
        assert response.status_code == 200
        return {row["id"] for row in response.data["results"]}

    assert ids_for(user_a) == {str(valid_a.id)}
    assert ids_for(user_b) == {str(valid_b.id)}
    assert ids_for(user_ab) == {str(valid_a.id), str(valid_b.id)}
    rows = {
        row["id"]: row
        for row in client_for(user_ab).get("/api/v1/attendance/verifications/").data["results"]
    }
    assert rows[str(valid_a.id)]["latitude"] == "33.684400"
    assert rows[str(valid_a.id)]["provider_reference"] == "provider-a"
    assert "latitude" not in rows[str(valid_b.id)]
    assert "provider_reference" not in rows[str(valid_b.id)]
    assert (
        client_for(user_ab).get(f"/api/v1/attendance/verifications/{corrupt.id}/").status_code
        == 404
    )


def test_attendance_actions_hide_mixed_assignment_and_corrupt_record_for_ab_actor() -> None:
    a, b = tenant_graph("ACT-A"), tenant_graph("ACT-B")
    guard_user = UserFactory.create()
    guard = EmployeeFactory.create(
        company=a["company"],
        branch=a["branch"],
        user=guard_user,
        employment_status="ACTIVE",
    )
    permissions = (
        "view_attendancerecord",
        "perform_own_checkin",
        "perform_own_checkout",
    )
    grant(guard_user, a["branch"], "attendance", *permissions)
    grant(guard_user, b["branch"], "attendance", *permissions)
    api = client_for(guard_user)
    valid_assignment = duty_assignment(a, guard, a["actor"], "VALID-A")
    mixed_assignment = duty_assignment(b, guard, b["actor"], "MIXED-B")
    AttendancePolicy.objects.create(
        company=a["company"], site=a["site"], name="A", effective_from=date.today()
    )

    assert (
        api.post(
            "/api/v1/attendance/records/check-in/",
            {"duty_assignment": str(mixed_assignment.id)},
            format="json",
        ).status_code
        == 404
    )
    checked_in = api.post(
        "/api/v1/attendance/records/check-in/",
        {"duty_assignment": str(valid_assignment.id)},
        format="json",
    )
    assert checked_in.status_code == 201
    checked_out = api.post(
        "/api/v1/attendance/records/check-out/",
        {"duty_assignment": str(valid_assignment.id)},
        format="json",
    )
    assert checked_out.status_code == 200
    record = AttendanceRecord.objects.get(duty_assignment=valid_assignment)
    AttendanceRecord.objects.filter(pk=record.pk).update(branch=b["branch"])
    assert api.get(f"/api/v1/attendance/records/{record.id}/").status_code == 404
    assert str(record.id) not in {
        row["id"] for row in api.get("/api/v1/attendance/records/").data["results"]
    }
    dashboard = api.get(reverse("attendance-dashboard-summary"))
    assert dashboard.status_code == 200
    assert dashboard.data["today_scheduled_employees"] == 0


def test_attendance_correction_uses_dedicated_scoped_workflow() -> None:
    a = tenant_graph("CORRECTION-A")
    guard = EmployeeFactory.create(company=a["company"], branch=a["branch"])
    record = attendance_record(
        a, duty_assignment(a, guard, a["actor"], "CORRECTION-A"), checked_in=True
    )
    record.status = "COMPLETED"
    record.save(update_fields=["status", "updated_at"])
    requester = UserFactory.create()
    grant(
        requester,
        a["branch"],
        "attendance",
        "add_attendancecorrectionrequest",
        "view_attendancerecord",
    )
    requested = client_for(requester).post(
        f"/api/v1/attendance/records/{record.id}/correction-request/",
        {"reason": "Correct the approved time"},
        format="json",
    )
    assert requested.status_code == 201

    approver = UserFactory.create()
    grant(
        approver,
        a["branch"],
        "attendance",
        "change_attendancecorrectionrequest",
    )
    approved = client_for(approver).post(
        f"/api/v1/attendance/corrections/{requested.data['id']}/approve/",
        {"notes": "Checked"},
        format="json",
    )
    assert approved.status_code == 200
    assert (
        client_for(requester).post("/api/v1/attendance/corrections/", {}, format="json").status_code
        == 405
    )


def test_attendance_task_skips_inactive_and_corrupt_tenants() -> None:
    a, b, c = tenant_graph("TASK-A"), tenant_graph("TASK-B"), tenant_graph("TASK-C")
    guard_a = EmployeeFactory.create(company=a["company"], branch=a["branch"])
    guard_corrupt = EmployeeFactory.create(company=a["company"], branch=a["branch"])
    guard_c = EmployeeFactory.create(company=c["company"], branch=c["branch"])
    valid = attendance_record(
        a, duty_assignment(a, guard_a, a["actor"], "TASK-VALID"), checked_in=True
    )
    corrupt = attendance_record(
        a,
        duty_assignment(a, guard_corrupt, a["actor"], "TASK-CORRUPT"),
        checked_in=True,
    )
    AttendanceRecord.objects.filter(pk=corrupt.pk).update(branch=b["branch"])
    inactive = attendance_record(
        c, duty_assignment(c, guard_c, c["actor"], "TASK-INACTIVE"), checked_in=True
    )
    c["company"].is_active = False
    c["company"].save(update_fields=["is_active"])

    assert detect_attendance_missing_checkout() == 1
    assert AttendanceException.objects.filter(attendance_record=valid).exists()
    assert not AttendanceException.objects.filter(attendance_record=corrupt).exists()
    assert not AttendanceException.objects.filter(attendance_record=inactive).exists()


def test_supervision_crud_rejects_mixed_patch_and_hides_corrupt_rows() -> None:
    a, b, c = tenant_graph("SUP-A"), tenant_graph("SUP-B"), tenant_graph("SUP-C")
    supervisor_a = EmployeeFactory.create(
        company=a["company"], branch=a["branch"], employee_type="SUPERVISOR"
    )
    supervisor_b = EmployeeFactory.create(
        company=b["company"], branch=b["branch"], employee_type="SUPERVISOR"
    )
    user = UserFactory.create()
    permissions = (
        "view_supervisionassignment",
        "add_supervisionassignment",
        "change_supervisionassignment",
        "add_siteobservation",
    )
    for graph in (a, b, c):
        grant(user, graph["branch"], "supervision", *permissions)
    api = client_for(user)
    valid = api.post(
        "/api/v1/supervision/assignments/",
        {
            "company": str(b["company"].id),
            "supervisor": str(supervisor_a.id),
            "scope_type": "BRANCH",
            "branch": str(a["branch"].id),
            "effective_from": str(date.today()),
            "status": "ACTIVE",
        },
        format="json",
    )
    assert valid.status_code == 201
    stored = SupervisionAssignment.objects.get(pk=valid.data["id"])
    assert stored.company_id == a["company"].id and stored.status == "DRAFT"
    assert (
        api.post(
            "/api/v1/supervision/assignments/",
            {
                "supervisor": str(supervisor_b.id),
                "scope_type": "BRANCH",
                "branch": str(a["branch"].id),
                "effective_from": str(date.today()),
            },
            format="json",
        ).status_code
        == 400
    )
    assert (
        api.patch(
            f"/api/v1/supervision/assignments/{stored.id}/",
            {"branch": str(b["branch"].id)},
            format="json",
        ).status_code
        == 400
    )
    stored.refresh_from_db()
    assert stored.branch_id == a["branch"].id

    corrupt = SupervisionAssignment.objects.create(
        company=a["company"],
        supervisor=supervisor_a,
        scope_type="BRANCH",
        branch=b["branch"],
        effective_from=date.today(),
        created_by=user,
    )
    inactive = SupervisionAssignment.objects.create(
        company=c["company"],
        supervisor=EmployeeFactory.create(company=c["company"], branch=c["branch"]),
        scope_type="BRANCH",
        branch=c["branch"],
        effective_from=date.today(),
        created_by=user,
    )
    c["company"].is_active = False
    c["company"].save(update_fields=["is_active"])
    ids = {row["id"] for row in api.get("/api/v1/supervision/assignments/").data["results"]}
    assert str(stored.id) in ids
    assert str(corrupt.id) not in ids and str(inactive.id) not in ids
    assert api.get(f"/api/v1/supervision/assignments/{corrupt.id}/").status_code == 404

    visit, _, _ = supervision_chain(a, "OBS-A", supervisor=supervisor_a)
    sibling_site = SecuritySite.objects.create(
        company=a["company"],
        client=a["client"],
        contract=a["contract"],
        site_code="SITE-OBS-SIBLING",
        name="Sibling site",
        managing_branch=a["branch"],
        address_line_1="Sibling address",
        city_name="Islamabad",
        risk_level="LOW",
        status="ACTIVE",
    )
    mixed_observation = api.post(
        "/api/v1/supervision/site-observations/",
        {
            "site_visit": str(visit.id),
            "site": str(sibling_site.id),
            "category": "OTHER",
            "title": "Mixed observation",
            "description": "Must not cross the visit boundary",
            "severity": "LOW",
        },
        format="json",
    )
    assert mixed_observation.status_code == 400


def test_global_inspection_templates_are_tenant_read_only() -> None:
    a, b = tenant_graph("GLOBAL-TEMPLATE-A"), tenant_graph("GLOBAL-TEMPLATE-B")
    global_template = InspectionTemplate.objects.create(
        company=None,
        code="GLOBAL",
        name="Global checklist",
        scope="SITE",
        effective_from=date.today(),
        is_system=True,
    )
    user = UserFactory.create()
    grant(
        user,
        a["branch"],
        "supervision",
        "view_inspectiontemplate",
        "add_inspectiontemplate",
        "change_inspectiontemplate",
    )
    grant(
        user,
        b["branch"],
        "supervision",
        "view_inspectiontemplate",
        "add_inspectiontemplate",
        "change_inspectiontemplate",
    )
    api = client_for(user)

    listed = api.get("/api/v1/supervision/inspection-templates/")
    assert listed.status_code == 200
    assert str(global_template.id) in {row["id"] for row in listed.data["results"]}
    assert (
        api.post(
            "/api/v1/supervision/inspection-templates/",
            {
                "code": "FORGED-GLOBAL",
                "name": "Forged",
                "scope": "SITE",
                "effective_from": str(date.today()),
            },
            format="json",
        ).status_code
        == 400
    )
    assert (
        api.patch(
            f"/api/v1/supervision/inspection-templates/{global_template.id}/",
            {"name": "Changed"},
            format="json",
        ).status_code
        == 400
    )
    global_template.refresh_from_db()
    assert global_template.name == "Global checklist"
    site_type_b = SiteType.objects.create(company=b["company"], code="B", name="Tenant B")
    mixed = api.post(
        "/api/v1/supervision/inspection-templates/",
        {
            "company": str(a["company"].id),
            "code": "MIXED",
            "name": "Mixed template",
            "scope": "SITE",
            "site_type": str(site_type_b.id),
            "effective_from": str(date.today()),
        },
        format="json",
    )
    assert mixed.status_code == 400


def test_supervision_actions_scope_request_ids_for_ab_actor() -> None:
    a, b = tenant_graph("VISIT-A"), tenant_graph("VISIT-B")
    user = UserFactory.create()
    supervisor = EmployeeFactory.create(
        company=a["company"],
        branch=a["branch"],
        user=user,
        employee_type="SUPERVISOR",
        employment_status="ACTIVE",
    )
    SupervisionAssignment.objects.create(
        company=a["company"],
        supervisor=supervisor,
        scope_type="SITE",
        branch=a["branch"],
        site=a["site"],
        effective_from=date.today(),
        status="ACTIVE",
        created_by=user,
    )
    permissions = (
        "view_sitevisit",
        "start_site_visit",
        "end_site_visit",
        "verify_guard",
    )
    grant(user, a["branch"], "supervision", *permissions)
    grant(user, b["branch"], "supervision", *permissions)
    api = client_for(user)

    mixed = api.post(
        "/api/v1/supervision/visits/start/",
        {"supervisor": str(supervisor.id), "site": str(b["site"].id)},
        format="json",
    )
    assert mixed.status_code == 400
    valid = api.post(
        "/api/v1/supervision/visits/start/",
        {"supervisor": str(supervisor.id), "site": str(a["site"].id)},
        format="json",
    )
    assert valid.status_code == 201
    visit_id = valid.data["id"]
    assert (
        api.post(
            f"/api/v1/supervision/visits/{visit_id}/verify-guard/",
            {"post": str(b["post"].id)},
            format="json",
        ).status_code
        == 404
    )
    ended = api.post(
        f"/api/v1/supervision/visits/{visit_id}/end/",
        {"summary": "Complete"},
        format="json",
    )
    assert ended.status_code == 200 and ended.data["status"] == "INCOMPLETE"
    assert "arrival_latitude" not in ended.data

    grant(user, a["branch"], "supervision", "view_sensitive_visit_location")
    supervisor_b = EmployeeFactory.create(
        company=b["company"], branch=b["branch"], employee_type="SUPERVISOR"
    )
    visit_b = SiteVisit.objects.create(
        company=b["company"],
        supervisor=supervisor_b,
        branch=b["branch"],
        site=b["site"],
        started_at=timezone.now(),
        status="IN_PROGRESS",
        verification_method="GPS",
        verification_result="WARNING",
        arrival_latitude="31.520400",
        arrival_longitude="74.358700",
    )
    rows = {row["id"]: row for row in api.get("/api/v1/supervision/visits/").data["results"]}
    assert "arrival_latitude" in rows[visit_id]
    assert "arrival_latitude" not in rows[str(visit_b.id)]


def test_supervision_dashboard_evidence_and_incident_referral_hide_corruption() -> None:
    a, b = tenant_graph("EVID-A"), tenant_graph("EVID-B")
    valid_visit, _, valid_finding = supervision_chain(a, "VALID-A")
    corrupt_supervisor = EmployeeFactory.create(
        company=a["company"], branch=a["branch"], employee_type="SUPERVISOR"
    )
    corrupt_visit = SiteVisit.objects.create(
        company=a["company"],
        supervisor=corrupt_supervisor,
        branch=a["branch"],
        site=b["site"],
        started_at=timezone.now(),
        status="IN_PROGRESS",
        verification_method="SUPERVISOR_MANUAL",
        verification_result="WARNING",
    )
    valid_evidence = FieldEvidence.objects.create(
        company=a["company"],
        site_visit=valid_visit,
        file="supervision-evidence/valid.pdf",
        original_filename="valid.pdf",
        file_size=10,
        mime_type="application/pdf",
        sha256_hash="a" * 64,
        uploaded_by=a["actor"],
    )
    corrupt_evidence = FieldEvidence.objects.create(
        company=a["company"],
        site_visit=corrupt_visit,
        file="supervision-evidence/secret.pdf",
        original_filename="secret.pdf",
        file_size=10,
        mime_type="application/pdf",
        sha256_hash="b" * 64,
        uploaded_by=a["actor"],
    )
    _, inspection_b, _ = supervision_chain(b, "INC-B")
    corrupt_finding = InspectionFinding.objects.create(
        company=a["company"],
        inspection=inspection_b,
        site=b["site"],
        title="Cross-tenant finding",
        description="Must not escalate",
        severity="CRITICAL",
        identified_by=a["actor"],
        identified_at=timezone.now(),
    )
    user = UserFactory.create()
    permissions = (
        "view_supervision_dashboard",
        "view_sensitive_field_evidence",
        "change_inspectionfinding",
        "view_correctiveaction",
        "add_correctiveaction",
    )
    grant(user, a["branch"], "supervision", *permissions)
    grant(user, b["branch"], "supervision", *permissions)
    api = client_for(user)

    dashboard = api.get(reverse("supervision-dashboard-summary"))
    assert dashboard.status_code == 200
    assert dashboard.data["visits_in_progress"] == 2
    evidence = api.get("/api/v1/supervision/evidence/")
    assert evidence.status_code == 200
    ids = {row["id"] for row in evidence.data["results"]}
    assert str(valid_evidence.id) in ids and str(corrupt_evidence.id) not in ids
    assert "file" not in evidence.data["results"][0]
    assert api.get(f"/api/v1/supervision/evidence/{corrupt_evidence.id}/").status_code == 404
    with pytest.raises(IncidentValidationError):
        refer_supervision_finding_to_incident(
            finding=corrupt_finding, actor=user, reason="Invalid boundary"
        )
    assert not Incident.objects.filter(supervision_finding=corrupt_finding).exists()
    assert (
        api.post(
            f"/api/v1/supervision/findings/{corrupt_finding.id}/refer-incident/",
            {"reason": "Invalid boundary"},
            format="json",
        ).status_code
        == 404
    )
    grant(b["actor"], b["branch"], "supervision", "view_correctiveaction")
    mixed_assignee = api.post(
        "/api/v1/supervision/corrective-actions/",
        {
            "finding": str(valid_finding.id),
            "site": str(a["site"].id),
            "title": "Mixed assignee",
            "description": "Must be rejected",
            "assigned_to_user": str(b["actor"].id),
        },
        format="json",
    )
    assert mixed_assignee.status_code == 400


def test_supervision_task_skips_inactive_and_corrupt_tenants() -> None:
    a, b, c = tenant_graph("OVER-A"), tenant_graph("OVER-B"), tenant_graph("OVER-C")
    _, _, finding_a = supervision_chain(a, "OVER-A")
    _, _, finding_c = supervision_chain(c, "OVER-C")
    valid = CorrectiveAction.objects.create(
        company=a["company"],
        finding=finding_a,
        site=a["site"],
        title="Valid",
        description="Test",
        assigned_by=a["actor"],
        assigned_at=timezone.now(),
        due_at=timezone.now() - timedelta(days=1),
    )
    corrupt = CorrectiveAction.objects.create(
        company=a["company"],
        finding=finding_a,
        site=b["site"],
        title="Corrupt",
        description="Test",
        assigned_by=a["actor"],
        assigned_at=timezone.now(),
        due_at=timezone.now() - timedelta(days=1),
    )
    inactive = CorrectiveAction.objects.create(
        company=c["company"],
        finding=finding_c,
        site=c["site"],
        title="Inactive",
        description="Test",
        assigned_by=c["actor"],
        assigned_at=timezone.now(),
        due_at=timezone.now() - timedelta(days=1),
    )
    c["company"].is_active = False
    c["company"].save(update_fields=["is_active"])

    assert detect_overdue_corrective_actions() == 1
    valid.refresh_from_db()
    corrupt.refresh_from_db()
    inactive.refresh_from_db()
    assert valid.status == "OVERDUE"
    assert corrupt.status == inactive.status == "OPEN"
