from decimal import Decimal
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from dsms.assets.enums import (
    AssetCategoryType,
    AssetCondition,
    AssetStatus,
    CustodyType,
    IssueStatus,
    IssueType,
    MovementType,
    ReturnCondition,
    TrackingMethod,
    UnitOfMeasure,
)
from dsms.assets.models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetIssueLine,
    AssetItem,
    AssetMovement,
    AssetReturn,
    AssetReturnLine,
    AssetStore,
    StockAccount,
)
from dsms.assets.selectors import (
    asset_category_list,
    asset_item_list,
    asset_list,
    assets_by_employee,
    available_assets,
    open_asset_issues,
    stock_balance_summary,
)
from dsms.assets.services import (
    approve_asset_issue,
    get_stock_balance,
    issue_assets,
    post_stock_transaction,
    receive_asset_return,
    submit_asset_issue,
)
from dsms.audit.models import AuditEvent
from tests.factories.identity import UserFactory
from tests.factories.organization import BranchFactory
from tests.factories.workforce import EmployeeFactory

pytestmark = pytest.mark.django_db


def asset_graph(*, serialized: bool = False) -> dict[str, Any]:
    branch = BranchFactory.create()
    company = branch.company
    requester, approver, custodian = UserFactory.create_batch(3)
    employee = EmployeeFactory.create(company=company, branch=branch)
    category = AssetCategory.objects.create(
        company=company,
        code="SERIAL" if serialized else "QTY",
        name="Equipment",
        category_type=AssetCategoryType.SECURITY_EQUIPMENT,
        tracking_method=TrackingMethod.SERIALIZED if serialized else TrackingMethod.QUANTITY,
        is_returnable=True,
    )
    item = AssetItem.objects.create(
        company=company,
        category=category,
        item_code="RADIO" if serialized else "UNIFORM",
        name="Radio" if serialized else "Uniform",
        unit_of_measure=UnitOfMeasure.PIECE,
    )
    store = AssetStore.objects.create(
        company=company, branch=branch, code="MAIN", name="Main store"
    )
    account = StockAccount.objects.create(company=company, item=item, store=store)
    issue = AssetIssue.objects.create(
        issue_number="ISS-001",
        company=company,
        issue_type=IssueType.EMPLOYEE_ASSIGNMENT,
        employee=employee,
        branch=branch,
        requested_by=requester,
        purpose="Operational issue",
    )
    return {
        "branch": branch,
        "company": company,
        "requester": requester,
        "approver": approver,
        "custodian": custodian,
        "employee": employee,
        "category": category,
        "item": item,
        "store": store,
        "account": account,
        "issue": issue,
    }


def test_stock_ledger_balances_bounds_audit_and_immutability() -> None:
    graph = asset_graph()
    account = graph["account"]
    actor = graph["custodian"]
    with pytest.raises(ValidationError, match="positive"):
        post_stock_transaction(
            stock_account=account,
            movement_type=MovementType.RECEIPT,
            quantity=Decimal("0"),
            actor=actor,
        )
    receipt = post_stock_transaction(
        stock_account=account,
        movement_type=MovementType.RECEIPT,
        quantity=Decimal("10"),
        actor=actor,
    )
    post_stock_transaction(
        stock_account=account,
        movement_type=MovementType.ISSUE,
        quantity=Decimal("3"),
        actor=actor,
    )
    post_stock_transaction(
        stock_account=account,
        movement_type=MovementType.RETURN,
        quantity=Decimal("1"),
        actor=actor,
    )
    adjustment = post_stock_transaction(
        stock_account=account,
        movement_type=MovementType.ADJUSTMENT,
        quantity=Decimal("2"),
        actor=actor,
        reason="Approved shrinkage",
    )
    balance = get_stock_balance(stock_account=account)
    assert balance == {
        "received": Decimal("10"),
        "issued": Decimal("3"),
        "returned": Decimal("1"),
        "adjusted": Decimal("2"),
        "lost": Decimal("0"),
        "available": Decimal("6"),
    }
    with pytest.raises(ValidationError, match="Insufficient"):
        post_stock_transaction(
            stock_account=account,
            movement_type=MovementType.LOSS,
            quantity=Decimal("7"),
            actor=actor,
        )
    assert AuditEvent.objects.filter(
        action="ASSET_STOCK_ADJUSTED", source_object_id=str(adjustment.id)
    ).exists()
    receipt.reason = "tamper"
    with pytest.raises(ValidationError, match="immutable"):
        receipt.save()
    with pytest.raises(ValidationError, match="cannot be deleted"):
        receipt.delete()


def test_quantity_issue_maker_checker_issue_and_return_workflow() -> None:
    graph = asset_graph()
    account, issue = graph["account"], graph["issue"]
    post_stock_transaction(
        stock_account=account,
        movement_type=MovementType.RECEIPT,
        quantity=Decimal("5"),
        actor=graph["custodian"],
    )
    with pytest.raises(ValidationError, match="non-empty"):
        submit_asset_issue(issue=issue)
    line = AssetIssueLine.objects.create(
        asset_issue=issue,
        item=graph["item"],
        stock_account=account,
        requested_quantity=2,
    )
    submitted = submit_asset_issue(issue=issue)
    assert submitted.status == IssueStatus.PENDING_APPROVAL
    with pytest.raises(ValidationError, match="self-approval"):
        approve_asset_issue(issue=submitted, approved_by=graph["requester"])
    approved = approve_asset_issue(issue=submitted, approved_by=graph["approver"])
    line.refresh_from_db()
    assert approved.status == IssueStatus.APPROVED
    assert line.approved_quantity == 2
    issued = issue_assets(issue=approved, issued_by=graph["custodian"])
    assert issued.status == IssueStatus.ISSUED
    assert get_stock_balance(stock_account=account)["available"] == 3
    with pytest.raises(ValidationError, match="Only approved"):
        issue_assets(issue=issued, issued_by=graph["custodian"])

    returned = AssetReturn.objects.create(
        return_number="RET-001",
        original_issue=issued,
        returned_by_employee=graph["employee"],
        received_by=graph["custodian"],
        returned_at=timezone.now(),
    )
    AssetReturnLine.objects.create(
        return_record=returned,
        issue_line=line,
        quantity=1,
        return_condition=ReturnCondition.GOOD,
        received_at=timezone.now(),
    )
    completed = receive_asset_return(return_record=returned)
    issued.refresh_from_db()
    line.refresh_from_db()
    assert completed.status == "COMPLETED"
    assert issued.status == IssueStatus.PARTIALLY_RETURNED
    assert line.returned_quantity == 1
    assert get_stock_balance(stock_account=account)["available"] == 4
    assert AuditEvent.objects.filter(action="ASSETS_ISSUED").exists()
    assert AuditEvent.objects.filter(action="ASSETS_RETURNED").exists()

    excess = AssetReturn.objects.create(
        return_number="RET-002",
        original_issue=issued,
        received_by=graph["custodian"],
        returned_at=timezone.now(),
    )
    AssetReturnLine.objects.create(
        return_record=excess,
        issue_line=line,
        quantity=2,
        return_condition=ReturnCondition.GOOD,
        received_at=timezone.now(),
    )
    with pytest.raises(ValidationError, match="exceeds"):
        receive_asset_return(return_record=excess)


def test_serialized_asset_issue_double_issue_guard_and_return_custody() -> None:
    graph = asset_graph(serialized=True)
    asset = Asset.objects.create(
        company=graph["company"],
        item=graph["item"],
        asset_number="RAD-001",
        serial_number="SECRET-SERIAL",
        status=AssetStatus.AVAILABLE,
        condition=AssetCondition.GOOD,
        current_custody_type=CustodyType.WAREHOUSE,
        current_warehouse=graph["store"],
    )
    line = AssetIssueLine.objects.create(
        asset_issue=graph["issue"],
        item=graph["item"],
        serialized_asset=asset,
        stock_account=graph["account"],
        requested_quantity=1,
    )
    approved = approve_asset_issue(
        issue=submit_asset_issue(issue=graph["issue"]), approved_by=graph["approver"]
    )
    issued = issue_assets(issue=approved, issued_by=graph["custodian"])
    asset.refresh_from_db()
    assert asset.status == AssetStatus.ISSUED
    assert asset.current_employee == graph["employee"]
    assert AssetMovement.objects.filter(asset=asset, movement_type=MovementType.ISSUE).exists()

    approved.status = IssueStatus.APPROVED
    approved.save(update_fields=["status"])
    with pytest.raises(ValidationError, match="unavailable"):
        issue_assets(issue=approved, issued_by=graph["custodian"])

    returned = AssetReturn.objects.create(
        return_number="RET-SERIAL",
        original_issue=issued,
        received_by=graph["custodian"],
        returned_at=timezone.now(),
    )
    AssetReturnLine.objects.create(
        return_record=returned,
        issue_line=line,
        serialized_asset=asset,
        quantity=1,
        return_condition=ReturnCondition.DAMAGED,
        requires_maintenance=True,
        received_at=timezone.now(),
    )
    receive_asset_return(return_record=returned)
    asset.refresh_from_db()
    assert asset.status == AssetStatus.UNDER_MAINTENANCE
    assert asset.condition == ReturnCondition.DAMAGED
    assert asset.current_warehouse == graph["store"]


def test_asset_selectors_preserve_company_scope_and_derived_stock() -> None:
    graph = asset_graph()
    other = asset_graph()
    post_stock_transaction(
        stock_account=graph["account"],
        movement_type=MovementType.RECEIPT,
        quantity=Decimal("4"),
        actor=graph["custodian"],
    )
    assert list(asset_category_list(company=graph["company"])) == [graph["category"]]
    assert list(asset_item_list(company=graph["company"])) == [graph["item"]]
    assert not asset_list(company=graph["company"]).filter(company=other["company"]).exists()
    assert not available_assets(company=graph["company"]).exists()
    assert not assets_by_employee(employee=graph["employee"]).exists()
    assert list(open_asset_issues(company=graph["company"])) == [graph["issue"]]
    summary: Any = stock_balance_summary(company=graph["company"]).get(pk=graph["account"].pk)
    assert summary.total_in == Decimal("4")
    assert summary.total_out is None
