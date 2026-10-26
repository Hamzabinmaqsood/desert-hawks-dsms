# mypy: disable-error-code="arg-type"
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone
from rest_framework.test import APIClient

from dsms.identity.enums import AccessScopeType
from dsms.leave.models import LeavePolicy, LeavePolicyRule, LeaveRequest, LeaveType
from dsms.organization.models import Company
from dsms.recruitment.enums import RequisitionStatus
from dsms.recruitment.models import ManpowerRequisition
from dsms.subscriptions.models import (
    CompanyModulePolicy,
    CompanyModulePolicyMode,
    SubscriptionModuleSnapshot,
)
from dsms.training.enums import CourseDeliveryMethod, CourseStatus, TrainingSessionStatus
from dsms.training.models import (
    TrainingCategory,
    TrainingCourse,
    TrainingCourseVersion,
    TrainingSession,
)
from dsms.workforce.enums import EmploymentStatus
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import CompanyFactory, DesignationFactory
from tests.factories.subscriptions import SubscriptionFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def enable_modules(company, *module_ids: str):  # type: ignore[no-untyped-def]
    subscription = SubscriptionFactory.create(
        company=company,
        snapshot_initialized_at=timezone.now(),
        snapshot_plan_entitlement_revision=0,
        entitlement_revision=1,
    )
    CompanyModulePolicy.objects.create(
        company=company,
        mode=CompanyModulePolicyMode.SUBSCRIPTION,
    )
    SubscriptionModuleSnapshot.objects.bulk_create(
        [
            SubscriptionModuleSnapshot(
                subscription=subscription,
                module_id=module_id,
                source_plan_entitlement_revision=0,
            )
            for module_id in module_ids
        ]
    )


def grant_company_permissions(user, company, *permissions: str):  # type: ignore[no-untyped-def]
    role = RoleFactory.create(company=company)
    requested = []
    for permission in permissions:
        app_label, codename = permission.split(".", 1)
        requested.append(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    role.permissions.set(requested)
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def leave_configuration(
    company: Company,
) -> tuple[LeaveType, LeavePolicy, LeavePolicyRule]:
    leave_type = LeaveType.objects.create(
        company=company,
        code="ANNUAL",
        name="Annual Leave",
        unit="DAYS",
        pay_treatment="PAID",
        requires_balance=False,
    )
    policy = LeavePolicy.objects.create(
        company=company,
        code="DEFAULT",
        name="Default policy",
        effective_from=date.today() - timedelta(days=365),
        is_default=True,
    )
    rule = LeavePolicyRule.objects.create(
        policy=policy,
        leave_type=leave_type,
        entitlement_units=Decimal("20.00"),
        approval_required=True,
    )
    return leave_type, policy, rule


def test_employee_leave_self_service_works_without_security_or_scheduling_modules() -> None:
    company = CompanyFactory.create()
    enable_modules(company, "people", "leave")
    user = UserFactory.create()
    EmployeeFactory.create(
        company=company,
        user=user,
        employment_status=EmploymentStatus.ACTIVE,
    )
    grant_company_permissions(
        user,
        company,
        "leave.view_own_leave_request",
        "leave.create_own_leave_request",
        "leave.change_own_draft_leave_request",
    )
    leave_type, _policy, _rule = leave_configuration(company)
    client = APIClient()
    client.force_authenticate(user)
    starts_at = timezone.now() + timedelta(days=5)

    created = client.post(
        "/api/v1/leave/me/requests/",
        {
            "leave_type": str(leave_type.pk),
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(days=1)).isoformat(),
            "reason": "Family commitment",
        },
        format="json",
    )

    assert created.status_code == 201, created.json()
    submitted = client.post(
        f"/api/v1/leave/me/requests/{created.json()['id']}/submit/", {}, format="json"
    )
    assert submitted.status_code == 200, submitted.json()
    assert submitted.json()["status"] == "SUBMITTED"
    assert client.get("/api/v1/leave/me/balances/").status_code == 200
    assert client.get("/api/v1/deployment/deployments/").status_code == 403


def test_leave_manager_inbox_is_scoped_and_rejects_with_exact_permission() -> None:
    company_a = CompanyFactory.create()
    company_b = CompanyFactory.create()
    manager = UserFactory.create()
    requester_a = UserFactory.create()
    requester_b = UserFactory.create()
    employee_a = EmployeeFactory.create(
        company=company_a, user=requester_a, employment_status=EmploymentStatus.ACTIVE
    )
    employee_b = EmployeeFactory.create(
        company=company_b, user=requester_b, employment_status=EmploymentStatus.ACTIVE
    )
    grant_company_permissions(
        manager,
        company_a,
        "leave.view_team_availability",
        "leave.reject_leave_request",
    )
    type_a, policy_a, rule_a = leave_configuration(company_a)
    type_b, policy_b, rule_b = leave_configuration(company_b)
    starts_at = timezone.now() + timedelta(days=8)
    request_a = LeaveRequest.objects.create(
        request_number="LR-A",
        company=company_a,
        employee=employee_a,
        leave_type=type_a,
        policy=policy_a,
        policy_rule=rule_a,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=1),
        requested_units=Decimal("1.00"),
        reason="Private reason A",
        status="SUBMITTED",
        created_by=requester_a,
    )
    request_b = LeaveRequest.objects.create(
        request_number="LR-B",
        company=company_b,
        employee=employee_b,
        leave_type=type_b,
        policy=policy_b,
        policy_rule=rule_b,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=1),
        requested_units=Decimal("1.00"),
        reason="Private reason B",
        status="SUBMITTED",
        created_by=requester_b,
    )
    client = APIClient()
    client.force_authenticate(manager)

    listing = client.get("/api/v1/leave/manager/requests/")
    assert listing.status_code == 200
    assert [row["id"] for row in listing.json()["results"]] == [str(request_a.pk)]
    assert "reason" not in listing.json()["results"][0]
    assert (
        client.post(
            f"/api/v1/leave/manager/requests/{request_b.pk}/reject/",
            {"reason": "Out of scope"},
            format="json",
        ).status_code
        == 404
    )
    rejected = client.post(
        f"/api/v1/leave/manager/requests/{request_a.pk}/reject/",
        {"reason": "Coverage unavailable"},
        format="json",
    )
    assert rejected.status_code == 200, rejected.json()
    assert rejected.json()["status"] == "REJECTED"


def test_requisition_approval_uses_exact_approval_permission() -> None:
    company = CompanyFactory.create()
    maker = UserFactory.create()
    approver = UserFactory.create()
    requisition = ManpowerRequisition.objects.create(
        company=company,
        designation=DesignationFactory.create(company=company),
        employee_type="OFFICE_STAFF",
        employment_type="PERMANENT",
        requested_headcount=2,
        reason="Growth",
        requested_by=maker,
        status=RequisitionStatus.SUBMITTED,
    )
    grant_company_permissions(
        approver,
        company,
        "recruitment.view_manpowerrequisition",
        "recruitment.approve_requisition",
    )
    client = APIClient()
    client.force_authenticate(approver)

    response = client.post(
        f"/api/v1/recruitment/manpower-requisitions/{requisition.pk}/approve/",
        {"approved_headcount": 2},
        format="json",
    )

    assert response.status_code == 200, response.json()
    assert response.json()["status"] == RequisitionStatus.APPROVED


def test_learning_session_actions_are_generic_and_module_scoped() -> None:
    company = CompanyFactory.create()
    enable_modules(company, "people", "learning")
    actor = UserFactory.create()
    grant_company_permissions(
        actor,
        company,
        "training.view_trainingsession",
        "training.change_trainingsession",
    )
    category = TrainingCategory.objects.create(company=company, code="GEN", name="General")
    course = TrainingCourse.objects.create(
        company=company,
        category=category,
        code="COMM",
        title="Business communication",
        description="Generic communication course",
        delivery_method=CourseDeliveryMethod.CLASSROOM,
        duration_hours=Decimal("2.00"),
        status=CourseStatus.ACTIVE,
    )
    version = TrainingCourseVersion.objects.create(
        course=course,
        version_number=1,
        effective_from=date.today(),
        syllabus_summary="Communication fundamentals",
        duration_hours=Decimal("2.00"),
        created_by=actor,
    )
    start = timezone.now() + timedelta(days=4)
    session = TrainingSession.objects.create(
        company=company,
        session_number="LS-001",
        course=course,
        course_version=version,
        start_datetime=start,
        end_datetime=start + timedelta(hours=2),
        capacity=10,
        created_by=actor,
    )
    client = APIClient()
    client.force_authenticate(actor)

    for action, expected in (
        ("schedule", TrainingSessionStatus.SCHEDULED),
        ("open-enrollment", TrainingSessionStatus.OPEN_FOR_ENROLLMENT),
        ("start", TrainingSessionStatus.IN_PROGRESS),
        ("complete", TrainingSessionStatus.COMPLETED),
    ):
        response = client.post(
            f"/api/v1/training/sessions/{session.pk}/{action}/", {}, format="json"
        )
        assert response.status_code == 200, response.json()
        assert response.json()["status"] == expected

    assert client.get("/api/v1/training/readiness/guards/").status_code == 403
