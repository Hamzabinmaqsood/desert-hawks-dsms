from datetime import date

import pytest
from django.utils import timezone

from dsms.analytics.models import AnalyticsDataQualityIssue
from dsms.assets.models import AssetCategory, AssetItem
from dsms.attendance.models import AttendancePolicy
from dsms.incidents.models import SOSAlert
from dsms.patrol.models import PatrolPolicy
from dsms.supervision.models import SupervisionAssignment
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory
from tests.support.tenant_adversarial import (
    assert_outgoing_only,
    force_cross_company_relation,
    scoped_scan,
    tenant_pair,
)

pytestmark = pytest.mark.django_db


def test_deferred_domains_and_repository_manifest_detect_outgoing_corruption() -> None:
    pair = tenant_pair("MANIFEST")
    branch_a = BranchFactory.create(company=pair.company_a, region__company=pair.company_a)
    branch_b = BranchFactory.create(company=pair.company_b, region__company=pair.company_b)
    employee_a = EmployeeFactory.create(company=pair.company_a, branch=branch_a)
    employee_b = EmployeeFactory.create(company=pair.company_b, branch=branch_b)
    actor = UserFactory.create()

    attendance = AttendancePolicy.objects.create(
        company=pair.company_a,
        branch=branch_a,
        name="A policy",
        effective_from=date(2026, 10, 13),
    )
    supervision = SupervisionAssignment.objects.create(
        company=pair.company_a,
        supervisor=employee_a,
        scope_type="BRANCH",
        branch=branch_a,
        effective_from=date(2026, 10, 13),
        created_by=actor,
    )
    patrol = PatrolPolicy.objects.create(
        company=pair.company_a,
        branch=branch_a,
        name="A patrol policy",
        effective_from=date(2026, 10, 13),
    )
    sos = SOSAlert.objects.create(
        sos_number="SOS-MANIFEST-A",
        company=pair.company_a,
        employee=employee_a,
        triggered_at=timezone.now(),
    )
    category_a = AssetCategory.objects.create(
        company=pair.company_a,
        code="CAT-A",
        name="Category A",
        category_type="OTHER",
        tracking_method="QUANTITY",
    )
    category_b = AssetCategory.objects.create(
        company=pair.company_b,
        code="CAT-B",
        name="Category B",
        category_type="OTHER",
        tracking_method="QUANTITY",
    )
    item = AssetItem.objects.create(
        company=pair.company_a,
        category=category_a,
        item_code="ITEM-A",
        name="Item A",
        unit_of_measure="PIECE",
    )
    quality_issue = AnalyticsDataQualityIssue.objects.create(
        company=pair.company_a,
        source_app="tests",
        issue_code="FOREIGN_BRANCH",
        severity="ERROR",
        description="Synthetic corruption",
        branch=branch_a,
        detected_at=timezone.now(),
    )

    force_cross_company_relation(branch_a, "region", branch_b.region)
    force_cross_company_relation(attendance, "branch", branch_b)
    force_cross_company_relation(supervision, "supervisor", employee_b)
    force_cross_company_relation(patrol, "branch", branch_b)
    force_cross_company_relation(sos, "employee", employee_b)
    force_cross_company_relation(item, "category", category_b)
    force_cross_company_relation(quality_issue, "branch", branch_b)

    expected = {
        "repository.remaining_tenant_relations": ("organization.Branch", "region"),
        "attendance.tenant_relations": ("attendance.AttendancePolicy", "branch"),
        "supervision.tenant_relations": ("supervision.SupervisionAssignment", "supervisor"),
        "patrol.tenant_relations": ("patrol.PatrolPolicy", "branch"),
        "incidents.tenant_relations": ("incidents.SOSAlert", "employee"),
        "assets.tenant_relations": ("assets.AssetItem", "category"),
        "analytics.tenant_relations": ("analytics.AnalyticsDataQualityIssue", "branch"),
    }
    for check_id, identity in expected.items():
        result_a = scoped_scan(pair.company_a, check_id)
        result_b = scoped_scan(pair.company_b, check_id)
        assert_outgoing_only(result_a, result_b)
        assert identity in {
            (finding.resource_type, finding.relation) for finding in result_a.findings
        }

    assert pair.company_b.is_active is False
