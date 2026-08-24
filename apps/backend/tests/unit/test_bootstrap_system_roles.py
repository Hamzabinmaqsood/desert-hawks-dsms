import pytest
from django.core.management import call_command

from dsms.identity.management.commands.bootstrap_system_roles import _SYSTEM_ROLES
from dsms.identity.models import Role

pytestmark = pytest.mark.django_db


def test_bootstrap_creates_expected_system_roles() -> None:
    call_command("bootstrap_system_roles")
    codes = set(Role.objects.filter(is_system=True).values_list("code", flat=True))
    assert {
        "ORGANIZATION_ADMIN",
        "ORGANIZATION_VIEWER",
        "ACCESS_ADMIN",
        "DOCUMENT_ADMIN",
        "DOCUMENT_VERIFIER",
        "DOCUMENT_VIEWER",
        "FINANCE_ADMIN",
        "PAYROLL_ADMIN",
        "ACCOUNTANT",
        "FINANCE_APPROVER",
        "PROCUREMENT_OFFICER",
        "FINANCE_AUDITOR",
        "FINANCE_EXECUTIVE_VIEWER",
        "RECRUITMENT_ADMIN",
        "RECRUITER",
        "RECRUITMENT_APPROVER",
        "INTERVIEWER",
        "BACKGROUND_VERIFIER",
        "ONBOARDING_ADMIN",
        "RECRUITMENT_VIEWER",
        "TRAINING_ADMIN",
        "TRAINING_COORDINATOR",
        "TRAINER",
        "TRAINING_VERIFIER",
        "TRAINING_VIEWER",
        "READINESS_VIEWER",
        "CONTRACT_ADMIN",
        "CLIENT_RELATIONSHIP_MANAGER",
        "CONTRACT_APPROVER",
        "OPERATIONS_CONTRACT_VIEWER",
        "SITE_CONFIGURATION_ADMIN",
        "COMMERCIAL_VIEWER",
        "CONTRACT_AUDITOR",
        "DEPLOYMENT_ADMIN",
        "ROSTER_PLANNER",
        "ROSTER_APPROVER",
        "OPERATIONS_MANAGER",
        "BRANCH_OPERATIONS_VIEWER",
        "RELIEF_COORDINATOR",
        "DEPLOYMENT_AUDITOR",
        "ATTENDANCE_ADMIN",
        "ATTENDANCE_REVIEWER",
        "ATTENDANCE_APPROVER",
        "SITE_ATTENDANCE_SUPERVISOR",
        "BRANCH_ATTENDANCE_VIEWER",
        "ATTENDANCE_AUDITOR",
        "GUARD_ATTENDANCE_SELF_SERVICE",
        "BILLING_ADMIN",
        "NOTIFICATION_ADMIN",
        "LEAVE_ADMIN",
        "ASSET_ADMIN",
        "HR_CASE_MANAGER",
        "PERFORMANCE_ADMIN",
        "ANALYTICS_ADMIN",
        "INCIDENT_MANAGER",
        "CLIENT_PORTAL_ADMIN",
        "AUDIT_ADMIN",
    } <= codes

    admin_role = Role.objects.get(code="ORGANIZATION_ADMIN")
    assert admin_role.permissions.count() == 21
    viewer_role = Role.objects.get(code="ORGANIZATION_VIEWER")
    assert viewer_role.permissions.count() == 7
    access_admin_role = Role.objects.get(code="ACCESS_ADMIN")
    assert access_admin_role.permissions.filter(codename="manage_roles").exists()
    assert access_admin_role.permissions.filter(codename="assign_roles").exists()


def test_bootstrap_is_idempotent() -> None:
    call_command("bootstrap_system_roles")
    first_count = Role.objects.filter(is_system=True).count()
    call_command("bootstrap_system_roles")
    second_count = Role.objects.filter(is_system=True).count()
    assert first_count == second_count == len(_SYSTEM_ROLES) == 88
    for spec in _SYSTEM_ROLES:
        role = Role.objects.get(code=spec["code"], company=None)
        actual = set(role.permissions.values_list("content_type__app_label", "codename"))
        assert actual == set(spec["permissions"]), spec["code"]
