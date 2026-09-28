# mypy: disable-error-code="arg-type"
from decimal import Decimal
from typing import Any

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
    AssetItem,
    AssetStore,
    StockAccount,
)
from dsms.identity.enums import AccessScopeType
from dsms.identity.models import User
from dsms.organization.models import Branch, Company
from tests.factories.identity import RoleFactory, UserFactory, UserRoleAssignmentFactory
from tests.factories.organization import BranchFactory

pytestmark = pytest.mark.django_db


def grant(
    user: User,
    *codenames: str,
    branch: Branch | None = None,
    company: Company | None = None,
) -> None:
    role = RoleFactory.create()
    role.permissions.set(
        Permission.objects.filter(content_type__app_label="assets", codename__in=codenames)
    )
    UserRoleAssignmentFactory.create(
        user=user,
        role=role,
        scope_type=AccessScopeType.BRANCH if branch else AccessScopeType.COMPANY,
        company=branch.company if branch else company,
        branch=branch,
    )


def asset_record(
    branch: Branch, suffix: str, *, controlled: bool = False, cost: Decimal = Decimal("125.00")
) -> dict[str, Any]:
    category = AssetCategory.objects.create(
        company=branch.company,
        code=f"CAT-{suffix}",
        name=f"Category {suffix}",
        category_type=AssetCategoryType.CONTROLLED_ITEM
        if controlled
        else AssetCategoryType.SECURITY_EQUIPMENT,
        tracking_method=TrackingMethod.SERIALIZED,
        is_controlled=controlled,
    )
    item = AssetItem.objects.create(
        company=branch.company,
        category=category,
        item_code=f"ITEM-{suffix}",
        name=f"Item {suffix}",
        unit_of_measure=UnitOfMeasure.PIECE,
        standard_cost=cost,
    )
    store = AssetStore.objects.create(
        company=branch.company, branch=branch, code=f"STORE-{suffix}", name=f"Store {suffix}"
    )
    asset = Asset.objects.create(
        company=branch.company,
        item=item,
        asset_number=f"ASSET-{suffix}",
        serial_number=f"SERIAL-{suffix}",
        acquisition_cost=cost,
        status=AssetStatus.AVAILABLE,
        condition=AssetCondition.GOOD,
        current_custody_type=CustodyType.WAREHOUSE,
        current_warehouse=store,
    )
    stock = StockAccount.objects.create(company=branch.company, item=item, store=store)
    issue = AssetIssue.objects.create(
        issue_number=f"ISSUE-{suffix}",
        company=branch.company,
        issue_type=IssueType.SITE_ASSIGNMENT,
        branch=branch,
        requested_by=UserFactory.create(),
        purpose=f"Purpose {suffix}",
    )
    return {
        "category": category,
        "item": item,
        "store": store,
        "asset": asset,
        "stock": stock,
        "issue": issue,
    }


def result_ids(response: Any) -> set[str]:
    payload = response.data
    rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    return {str(row["id"]) for row in rows}


def test_assets_api_rejects_anonymous_and_user_without_role() -> None:
    branch = BranchFactory.create()
    record = asset_record(branch, "PRIVATE")
    detail = reverse("asset-detail", args=[record["asset"].id])
    action = reverse("asset-issue-approve", args=[record["issue"].id])
    assert APIClient().get(reverse("asset-list")).status_code == 401
    assert APIClient().get(detail).status_code == 401
    assert APIClient().post(action).status_code == 401
    client = APIClient()
    client.force_authenticate(UserFactory.create())
    assert client.get(reverse("asset-list")).status_code == 403
    assert client.get(detail).status_code == 403
    assert client.post(action).status_code == 403


def test_asset_lists_and_details_are_branch_and_company_scoped() -> None:
    allowed_branch = BranchFactory.create()
    sibling_branch = BranchFactory.create(
        company=allowed_branch.company, region=allowed_branch.region
    )
    other_branch = BranchFactory.create()
    allowed = asset_record(allowed_branch, "ALLOWED")
    sibling = asset_record(sibling_branch, "SIBLING")
    other = asset_record(other_branch, "OTHER")
    user = UserFactory.create()
    grant(
        user,
        "view_asset",
        "view_assetstore",
        "view_stockaccount",
        "view_assetissue",
        branch=allowed_branch,
    )
    client = APIClient()
    client.force_authenticate(user)

    assert result_ids(client.get(reverse("asset-list"))) == {str(allowed["asset"].id)}
    assert result_ids(client.get(reverse("asset-store-list"))) == {str(allowed["store"].id)}
    assert result_ids(client.get(reverse("stock-account-list"))) == {str(allowed["stock"].id)}
    assert result_ids(client.get(reverse("asset-issue-list"))) == {str(allowed["issue"].id)}
    for hidden in (sibling, other):
        assert client.get(reverse("asset-detail", args=[hidden["asset"].id])).status_code == 404
        assert (
            client.get(reverse("asset-store-detail", args=[hidden["store"].id])).status_code == 404
        )
        assert (
            client.get(reverse("stock-account-detail", args=[hidden["stock"].id])).status_code
            == 404
        )
        assert (
            client.get(reverse("asset-issue-detail", args=[hidden["issue"].id])).status_code == 404
        )


def test_company_catalog_scope_does_not_cross_company() -> None:
    allowed_branch, hidden_branch = BranchFactory.create(), BranchFactory.create()
    allowed, hidden = (
        asset_record(allowed_branch, "CATALOG-A"),
        asset_record(hidden_branch, "CATALOG-B"),
    )
    user = UserFactory.create()
    grant(user, "view_assetcategory", "view_assetitem", company=allowed_branch.company)
    client = APIClient()
    client.force_authenticate(user)
    assert result_ids(client.get(reverse("asset-category-list"))) == {str(allowed["category"].id)}
    assert result_ids(client.get(reverse("asset-item-list"))) == {str(allowed["item"].id)}
    assert (
        client.get(reverse("asset-category-detail", args=[hidden["category"].id])).status_code
        == 404
    )
    assert client.get(reverse("asset-item-detail", args=[hidden["item"].id])).status_code == 404


def test_controlled_assets_require_scoped_controlled_permission() -> None:
    branch = BranchFactory.create()
    ordinary = asset_record(branch, "ORDINARY")
    controlled = asset_record(branch, "CONTROLLED", controlled=True)
    user = UserFactory.create()
    grant(user, "view_asset", branch=branch)
    client = APIClient()
    client.force_authenticate(user)
    assert result_ids(client.get(reverse("asset-list"))) == {str(ordinary["asset"].id)}
    denied = client.get(reverse("asset-detail", args=[controlled["asset"].id]))
    assert denied.status_code == 404
    assert "SERIAL-CONTROLLED" not in denied.content.decode()

    grant(user, "view_controlled_asset", branch=branch)
    assert controlled["asset"].id.hex in {
        value.replace("-", "") for value in result_ids(client.get(reverse("asset-list")))
    }
    assert client.get(reverse("asset-detail", args=[controlled["asset"].id])).status_code == 200


def test_asset_financial_fields_require_scoped_financial_permission() -> None:
    branch = BranchFactory.create()
    record = asset_record(branch, "FINANCE")
    user = UserFactory.create()
    grant(user, "view_asset", branch=branch)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(reverse("asset-detail", args=[record["asset"].id]))
    assert response.status_code == 200
    assert "acquisition_cost" not in response.data

    grant(user, "view_asset_financial_values", branch=branch)
    response = client.get(reverse("asset-detail", args=[record["asset"].id]))
    assert response.data["acquisition_cost"] == "125.00"


def test_item_standard_cost_requires_company_financial_permission() -> None:
    branch = BranchFactory.create()
    record = asset_record(branch, "ITEM-COST")
    user = UserFactory.create()
    grant(user, "view_assetitem", company=branch.company)
    client = APIClient()
    client.force_authenticate(user)
    response = client.get(reverse("asset-item-detail", args=[record["item"].id]))
    assert "standard_cost" not in response.data
    grant(user, "view_asset_financial_values", company=branch.company)
    response = client.get(reverse("asset-item-detail", args=[record["item"].id]))
    assert response.data["standard_cost"] == "125.00"


def test_item_standard_cost_write_requires_financial_permission() -> None:
    branch = BranchFactory.create()
    record = asset_record(branch, "ITEM-COST-WRITE")
    user = UserFactory.create()
    grant(user, "change_assetitem", company=branch.company)
    client = APIClient()
    client.force_authenticate(user)
    response = client.patch(
        reverse("asset-item-detail", args=[record["item"].id]),
        {"standard_cost": "999.00"},
        format="json",
    )
    assert response.status_code == 400
    record["item"].refresh_from_db()
    assert record["item"].standard_cost == Decimal("125.00")


def test_store_create_rejects_cross_scope_target() -> None:
    allowed_branch, hidden_branch = BranchFactory.create(), BranchFactory.create()
    user = UserFactory.create()
    grant(user, "add_assetstore", branch=allowed_branch)
    client = APIClient()
    client.force_authenticate(user)
    response = client.post(
        reverse("asset-store-list"),
        {
            "company": str(hidden_branch.company_id),
            "branch": str(hidden_branch.id),
            "code": "CROSS-SCOPE",
            "name": "Cross Scope Store",
        },
        format="json",
    )
    assert response.status_code == 400
    assert not AssetStore.objects.filter(code="CROSS-SCOPE").exists()


def test_generic_asset_patch_cannot_change_service_owned_state() -> None:
    branch = BranchFactory.create()
    record = asset_record(branch, "PROTECTED")
    user = UserFactory.create()
    grant(user, "add_asset", "change_asset", branch=branch)
    client = APIClient()
    client.force_authenticate(user)
    response = client.patch(
        reverse("asset-detail", args=[record["asset"].id]),
        {
            "status": AssetStatus.DISPOSED,
            "condition": AssetCondition.DAMAGED,
            "current_branch": str(branch.id),
            "notes": "Permitted metadata update",
        },
        format="json",
    )
    assert response.status_code == 200
    record["asset"].refresh_from_db()
    assert record["asset"].status == AssetStatus.AVAILABLE
    assert record["asset"].condition == AssetCondition.GOOD
    assert record["asset"].current_warehouse == record["store"]
    assert record["asset"].notes == "Permitted metadata update"
    assert client.post(reverse("asset-list"), {}, format="json").status_code == 405


def test_issue_identity_fields_are_fixed_after_creation() -> None:
    branch = BranchFactory.create()
    record = asset_record(branch, "ISSUE-PROTECTED")
    user = UserFactory.create()
    grant(user, "change_assetissue", branch=branch)
    client = APIClient()
    client.force_authenticate(user)
    response = client.patch(
        reverse("asset-issue-detail", args=[record["issue"].id]),
        {"issue_number": "TAMPERED", "purpose": "Changed"},
        format="json",
    )
    assert response.status_code == 400
    record["issue"].refresh_from_db()
    assert record["issue"].issue_number == "ISSUE-ISSUE-PROTECTED"


def test_issue_workflow_actions_use_distinct_permissions_and_scope() -> None:
    allowed_branch, hidden_branch = BranchFactory.create(), BranchFactory.create()
    allowed, hidden = (
        asset_record(allowed_branch, "ACTION-A"),
        asset_record(hidden_branch, "ACTION-B"),
    )
    allowed["issue"].status = hidden["issue"].status = IssueStatus.PENDING_APPROVAL
    allowed["issue"].save(update_fields=["status"])
    hidden["issue"].save(update_fields=["status"])
    approver = UserFactory.create()
    grant(approver, "approve_asset_issue", branch=allowed_branch)
    client = APIClient()
    client.force_authenticate(approver)
    assert client.post(reverse("asset-issue-approve", args=[hidden["issue"].id])).status_code == 404
    assert client.post(reverse("asset-issue-issue", args=[allowed["issue"].id])).status_code == 403
    assert (
        client.post(reverse("asset-issue-approve", args=[allowed["issue"].id])).status_code == 200
    )

    issuer = UserFactory.create()
    grant(issuer, "issue_asset", branch=allowed_branch)
    client.force_authenticate(issuer)
    assert (
        client.post(reverse("asset-issue-approve", args=[allowed["issue"].id])).status_code == 403
    )


def test_issue_approval_preserves_maker_checker() -> None:
    branch = BranchFactory.create()
    record = asset_record(branch, "MAKER")
    issue = record["issue"]
    issue.status = IssueStatus.PENDING_APPROVAL
    issue.save(update_fields=["status"])
    grant(issue.requested_by, "approve_asset_issue", branch=branch)
    client = APIClient()
    client.force_authenticate(issue.requested_by)
    response = client.post(reverse("asset-issue-approve", args=[issue.id]))
    assert response.status_code == 400
    assert "self-approval" in response.content.decode()


def test_assets_superuser_retains_unrestricted_operational_and_financial_access() -> None:
    first, second = (
        asset_record(BranchFactory.create(), "SUPER-A"),
        asset_record(BranchFactory.create(), "SUPER-B", controlled=True),
    )
    client = APIClient()
    client.force_authenticate(UserFactory.create(is_superuser=True))
    assert result_ids(client.get(reverse("asset-list"))) == {
        str(first["asset"].id),
        str(second["asset"].id),
    }
    response = client.get(reverse("asset-detail", args=[second["asset"].id]))
    assert response.status_code == 200
    assert response.data["acquisition_cost"] == "125.00"
