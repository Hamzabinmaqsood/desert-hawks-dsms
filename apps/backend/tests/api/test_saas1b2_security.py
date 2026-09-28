from decimal import Decimal
from uuid import uuid4

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from dsms.assets.enums import (
    AssetCategoryType,
    AssetCondition,
    AssetStatus,
    CustodyType,
    IssueStatus,
    IssueType,
    TrackingMethod,
    UnitOfMeasure,
)
from dsms.assets.models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetIssueLine,
    AssetItem,
    AssetStore,
)
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from dsms.organization.models import Company
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db

GENERIC_FINANCE_RESOURCES = (
    "payroll-components",
    "salary-structures",
    "employee-compensations",
    "payroll-periods",
    "payroll-runs",
    "vendors",
    "purchase-requisitions",
    "purchase-orders",
    "purchase-receipts",
    "vendor-bills",
    "payment-vouchers",
    "expense-categories",
    "expenses",
    "expense-claims",
    "recurring-expenses",
    "petty-cash-funds",
    "cash-accounts",
    "bank-accounts",
    "fund-transfers",
    "budgets",
    "approval-policies",
)


def grant_assets(user: User, company: Company, *codenames: str) -> None:
    role = RoleFactory.create()
    role.permissions.set(
        Permission.objects.filter(content_type__app_label="assets", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.COMPANY,
        company=company,
    )


def grant_all_finance(user: User) -> None:
    role = RoleFactory.create()
    role.permissions.set(Permission.objects.filter(content_type__app_label="finance"))
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.GLOBAL,
    )


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def catalog(company: Company, suffix: str) -> tuple[AssetCategory, AssetItem]:
    category = AssetCategory.objects.create(
        company=company,
        code=f"CAT-{suffix}",
        name=f"Category {suffix}",
        category_type=AssetCategoryType.SECURITY_EQUIPMENT,
        tracking_method=TrackingMethod.SERIALIZED,
    )
    item = AssetItem.objects.create(
        company=company,
        category=category,
        item_code=f"ITEM-{suffix}",
        name=f"Item {suffix}",
        unit_of_measure=UnitOfMeasure.PIECE,
    )
    return category, item


def result_ids(response: object) -> set[str]:
    payload = response.data  # type: ignore[attr-defined]
    rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    return {str(row["id"]) for row in rows}


def test_generic_finance_registry_is_platform_only_for_fully_privileged_tenant() -> None:
    tenant_user = UserFactory.create()
    grant_all_finance(tenant_user)
    client = client_for(tenant_user)

    for resource in GENERIC_FINANCE_RESOURCES:
        collection = f"/api/v1/finance/domain/{resource}/"
        assert client.get(collection).status_code == 403, resource
        assert client.post(collection, {}, format="json").status_code == 403, resource
        assert client.get(f"{collection}{uuid4()}/").status_code == 403, resource

    assert (
        client.post(
            f"/api/v1/finance/domain/vendor-bills/{uuid4()}/submit/", {}, format="json"
        ).status_code
        == 403
    )


def test_asset_create_and_patch_reject_mixed_tenant_relations_for_ab_actor() -> None:
    branch_a, branch_b = BranchFactory.create(), BranchFactory.create()
    company_a, company_b = branch_a.company, branch_b.company
    category_a, item_a = catalog(company_a, "A")
    category_b, _item_b = catalog(company_b, "B")
    employee_a = EmployeeFactory.create(company=company_a, branch=branch_a)
    employee_b = EmployeeFactory.create(company=company_b, branch=branch_b)
    user = UserFactory.create()
    permissions = (
        "add_assetcategory",
        "change_assetcategory",
        "add_assetitem",
        "change_assetitem",
        "add_assetstore",
        "change_assetstore",
        "add_assetissue",
        "change_assetissue",
    )
    grant_assets(user, company_a, *permissions)
    grant_assets(user, company_b, *permissions)
    client = client_for(user)

    created_a = client.post(
        reverse("asset-category-list"),
        {
            "company": str(company_a.id),
            "code": "API-A",
            "name": "API A",
            "category_type": AssetCategoryType.SECURITY_EQUIPMENT,
            "tracking_method": TrackingMethod.SERIALIZED,
            "is_system": True,
        },
        format="json",
    )
    created_b = client.post(
        reverse("asset-category-list"),
        {
            "company": str(company_b.id),
            "code": "API-B",
            "name": "API B",
            "category_type": AssetCategoryType.SECURITY_EQUIPMENT,
            "tracking_method": TrackingMethod.SERIALIZED,
        },
        format="json",
    )
    assert created_a.status_code == created_b.status_code == 201
    assert created_a.data["is_system"] is False
    category_patch = client.patch(
        reverse("asset-category-detail", args=[created_a.data["id"]]),
        {"company": str(company_b.id)},
        format="json",
    )
    assert category_patch.status_code == 400
    assert AssetCategory.objects.get(pk=created_a.data["id"]).company_id == company_a.id

    mixed_item = client.post(
        reverse("asset-item-list"),
        {
            "company": str(company_a.id),
            "category": str(category_b.id),
            "item_code": "MIXED",
            "name": "Mixed",
            "unit_of_measure": UnitOfMeasure.PIECE,
        },
        format="json",
    )
    assert mixed_item.status_code == 400
    item_patch = client.patch(
        reverse("asset-item-detail", args=[item_a.id]),
        {"category": str(category_b.id), "company": str(company_b.id)},
        format="json",
    )
    assert item_patch.status_code == 400
    item_a.refresh_from_db()
    assert item_a.company_id == company_a.id and item_a.category_id == category_a.id

    store_a = AssetStore.objects.create(
        company=company_a, branch=branch_a, code="STORE-A", name="Store A"
    )
    mixed_store = client.post(
        reverse("asset-store-list"),
        {
            "company": str(company_a.id),
            "branch": str(branch_b.id),
            "code": "MIXED",
            "name": "Mixed",
        },
        format="json",
    )
    assert mixed_store.status_code == 400
    store_patch = client.patch(
        reverse("asset-store-detail", args=[store_a.id]),
        {"company": str(company_b.id), "branch": str(branch_b.id)},
        format="json",
    )
    assert store_patch.status_code == 400
    store_a.refresh_from_db()
    assert store_a.company_id == company_a.id and store_a.branch_id == branch_a.id

    valid_issue = client.post(
        reverse("asset-issue-list"),
        {
            "issue_number": "API-ISSUE-A",
            "company": str(company_a.id),
            "issue_type": IssueType.EMPLOYEE_ASSIGNMENT,
            "employee": str(employee_a.id),
            "purpose": "Valid issue",
            "status": IssueStatus.ISSUED,
            "requested_by": str(UserFactory.create().id),
        },
        format="json",
    )
    assert valid_issue.status_code == 201
    assert valid_issue.data["status"] == IssueStatus.DRAFT
    assert str(valid_issue.data["requested_by"]) == str(user.id)
    mixed_issue = client.post(
        reverse("asset-issue-list"),
        {
            "issue_number": "API-ISSUE-MIXED",
            "company": str(company_a.id),
            "issue_type": IssueType.EMPLOYEE_ASSIGNMENT,
            "employee": str(employee_b.id),
            "purpose": "Mixed issue",
        },
        format="json",
    )
    assert mixed_issue.status_code == 400


def test_asset_create_and_read_scope_is_symmetric_for_b_only_actor() -> None:
    branch_a, branch_b = BranchFactory.create(), BranchFactory.create()
    company_a, company_b = branch_a.company, branch_b.company
    category_a, item_a = catalog(company_a, "B-ONLY-A")
    category_b, item_b = catalog(company_b, "B-ONLY-B")
    store_a = AssetStore.objects.create(
        company=company_a, branch=branch_a, code="B-ONLY-A", name="A Store"
    )
    store_b = AssetStore.objects.create(
        company=company_b, branch=branch_b, code="B-ONLY-B", name="B Store"
    )
    employee_a = EmployeeFactory.create(company=company_a, branch=branch_a)
    employee_b = EmployeeFactory.create(company=company_b, branch=branch_b)
    issue_a = AssetIssue.objects.create(
        issue_number="B-ONLY-A",
        company=company_a,
        issue_type=IssueType.EMPLOYEE_ASSIGNMENT,
        employee=employee_a,
        requested_by=UserFactory.create(),
        purpose="A issue",
    )
    issue_b = AssetIssue.objects.create(
        issue_number="B-ONLY-B",
        company=company_b,
        issue_type=IssueType.EMPLOYEE_ASSIGNMENT,
        employee=employee_b,
        requested_by=UserFactory.create(),
        purpose="B issue",
    )
    actor = UserFactory.create()
    grant_assets(
        actor,
        company_b,
        "view_assetcategory",
        "add_assetcategory",
        "view_assetitem",
        "add_assetitem",
        "view_assetstore",
        "add_assetstore",
        "view_assetissue",
        "add_assetissue",
    )
    client = client_for(actor)

    assert str(category_b.id) in result_ids(client.get(reverse("asset-category-list")))
    assert str(category_a.id) not in result_ids(client.get(reverse("asset-category-list")))
    assert str(item_b.id) in result_ids(client.get(reverse("asset-item-list")))
    assert str(item_a.id) not in result_ids(client.get(reverse("asset-item-list")))
    assert str(store_b.id) in result_ids(client.get(reverse("asset-store-list")))
    assert str(store_a.id) not in result_ids(client.get(reverse("asset-store-list")))
    assert str(issue_b.id) in result_ids(client.get(reverse("asset-issue-list")))
    assert str(issue_a.id) not in result_ids(client.get(reverse("asset-issue-list")))

    valid_category = client.post(
        reverse("asset-category-list"),
        {
            "company": str(company_b.id),
            "code": "B-VALID",
            "name": "B Valid",
            "category_type": AssetCategoryType.SECURITY_EQUIPMENT,
            "tracking_method": TrackingMethod.SERIALIZED,
        },
        format="json",
    )
    assert valid_category.status_code == 201
    assert (
        client.post(
            reverse("asset-category-list"),
            {
                "company": str(company_a.id),
                "code": "A-DENIED",
                "name": "A Denied",
                "category_type": AssetCategoryType.SECURITY_EQUIPMENT,
                "tracking_method": TrackingMethod.SERIALIZED,
            },
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            reverse("asset-item-list"),
            {
                "company": str(company_b.id),
                "category": str(category_b.id),
                "item_code": "B-VALID",
                "name": "B Valid",
                "unit_of_measure": UnitOfMeasure.PIECE,
            },
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            reverse("asset-item-list"),
            {
                "company": str(company_a.id),
                "category": str(category_a.id),
                "item_code": "A-DENIED",
                "name": "A Denied",
                "unit_of_measure": UnitOfMeasure.PIECE,
            },
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            reverse("asset-store-list"),
            {
                "company": str(company_b.id),
                "branch": str(branch_b.id),
                "code": "B-VALID",
                "name": "B Valid",
            },
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            reverse("asset-store-list"),
            {
                "company": str(company_a.id),
                "branch": str(branch_a.id),
                "code": "A-DENIED",
                "name": "A Denied",
            },
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            reverse("asset-issue-list"),
            {
                "issue_number": "B-VALID",
                "company": str(company_b.id),
                "issue_type": IssueType.EMPLOYEE_ASSIGNMENT,
                "employee": str(employee_b.id),
                "purpose": "B valid",
            },
            format="json",
        ).status_code
        == 201
    )
    assert (
        client.post(
            reverse("asset-issue-list"),
            {
                "issue_number": "A-DENIED",
                "company": str(company_a.id),
                "issue_type": IssueType.EMPLOYEE_ASSIGNMENT,
                "employee": str(employee_a.id),
                "purpose": "A denied",
            },
            format="json",
        ).status_code
        == 400
    )


def test_corrupt_asset_relations_are_hidden_from_a_only_and_ab_actors() -> None:
    branch_a, branch_b = BranchFactory.create(), BranchFactory.create()
    company_a, company_b = branch_a.company, branch_b.company
    category_a, item_a = catalog(company_a, "CORRUPT-A")
    category_b, item_b = catalog(company_b, "CORRUPT-B")
    store_a = AssetStore.objects.create(
        company=company_a, branch=branch_a, code="CORRUPT-A", name="Corrupt A"
    )
    store_b = AssetStore.objects.create(
        company=company_b, branch=branch_b, code="CORRUPT-B", name="Corrupt B"
    )
    asset_a = Asset.objects.create(
        company=company_a,
        item=item_a,
        asset_number="CORRUPT-ASSET-A",
        status=AssetStatus.AVAILABLE,
        condition=AssetCondition.GOOD,
        current_custody_type=CustodyType.WAREHOUSE,
        current_warehouse=store_a,
    )
    issue_a = AssetIssue.objects.create(
        issue_number="CORRUPT-ISSUE-A",
        company=company_a,
        issue_type=IssueType.LONG_TERM,
        branch=branch_a,
        requested_by=UserFactory.create(),
        purpose="Corrupt relation",
        status=IssueStatus.PENDING_APPROVAL,
    )
    line_corrupt_issue = AssetIssue.objects.create(
        issue_number="CORRUPT-LINE-A",
        company=company_a,
        issue_type=IssueType.LONG_TERM,
        branch=branch_a,
        requested_by=UserFactory.create(),
        purpose="Corrupt line relation",
    )
    AssetIssueLine.objects.create(
        asset_issue=line_corrupt_issue,
        item=item_b,
        requested_quantity=Decimal("1"),
    )

    AssetItem.objects.filter(pk=item_a.pk).update(category=category_b)
    AssetStore.objects.filter(pk=store_a.pk).update(branch=branch_b)
    Asset.objects.filter(pk=asset_a.pk).update(current_warehouse=store_b)
    AssetIssue.objects.filter(pk=issue_a.pk).update(branch=branch_b)

    permissions = (
        "view_assetitem",
        "view_assetstore",
        "view_asset",
        "view_assetissue",
        "approve_asset_issue",
    )
    a_only, ab_actor = UserFactory.create(), UserFactory.create()
    grant_assets(a_only, company_a, *permissions)
    grant_assets(ab_actor, company_a, *permissions)
    grant_assets(ab_actor, company_b, *permissions)

    hidden = (
        ("asset-item-list", "asset-item-detail", item_a.id),
        ("asset-store-list", "asset-store-detail", store_a.id),
        ("asset-list", "asset-detail", asset_a.id),
        ("asset-issue-list", "asset-issue-detail", issue_a.id),
        ("asset-issue-list", "asset-issue-detail", line_corrupt_issue.id),
    )
    for actor in (a_only, ab_actor):
        client = client_for(actor)
        for list_name, detail_name, object_id in hidden:
            assert str(object_id) not in result_ids(client.get(reverse(list_name)))
            detail = client.get(reverse(detail_name, args=[object_id]))
            assert detail.status_code == 404
            assert str(company_b.id) not in detail.content.decode()
        assert client.post(reverse("asset-issue-approve", args=[issue_a.id])).status_code == 404

    assert category_a.company_id == company_a.id
