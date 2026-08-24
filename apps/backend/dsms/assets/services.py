from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.identity.models import User

from .enums import AssetStatus, CustodyType, IssueStatus, MovementType, TrackingMethod
from .models import (
    Asset,
    AssetIssue,
    AssetIssueLine,
    AssetKitTemplate,
    AssetMovement,
    AssetReturn,
    StockAccount,
    StockTransaction,
)

POSITIVE_STOCK_MOVEMENTS = {
    MovementType.RECEIPT,
    MovementType.RETURN,
    MovementType.MAINTENANCE_RETURN,
    MovementType.RECOVERY,
}


def _signed_quantity(movement_type: str, quantity: Decimal) -> Decimal:
    return quantity if movement_type in POSITIVE_STOCK_MOVEMENTS else -quantity


def get_stock_balance(
    *, stock_account: StockAccount, as_of_datetime: Any = None
) -> dict[str, Decimal]:
    qs = StockTransaction.objects.filter(stock_account=stock_account)
    if as_of_datetime is not None:
        qs = qs.filter(effective_at__lte=as_of_datetime)
    totals: dict[str, Decimal] = {}
    for row in qs.values("movement_type").annotate(total=Sum("quantity")):
        totals[row["movement_type"]] = row["total"]
    received = totals.get(MovementType.RECEIPT, Decimal(0))
    issued = totals.get(MovementType.ISSUE, Decimal(0))
    returned = totals.get(MovementType.RETURN, Decimal(0))
    adjusted = totals.get(MovementType.ADJUSTMENT, Decimal(0)) + totals.get(
        MovementType.COUNT_CORRECTION, Decimal(0)
    )
    lost = totals.get(MovementType.LOSS, Decimal(0))
    available = sum((_signed_quantity(kind, value) for kind, value in totals.items()), Decimal(0))
    return {
        "received": received,
        "issued": issued,
        "returned": returned,
        "adjusted": adjusted,
        "lost": lost,
        "available": available,
    }


@transaction.atomic
def post_stock_transaction(
    *,
    stock_account: StockAccount,
    movement_type: str,
    quantity: Decimal,
    actor: User,
    reason: str = "",
    **links: Any,
) -> StockTransaction:
    account = StockAccount.objects.select_for_update().get(pk=stock_account.pk)
    quantity = Decimal(quantity)
    if quantity <= 0:
        raise ValidationError({"quantity": "Quantity must be positive."})
    if (
        _signed_quantity(movement_type, quantity) < 0
        and get_stock_balance(stock_account=account)["available"] < quantity
    ):
        raise ValidationError("Insufficient stock; negative inventory is not permitted.")
    entry = StockTransaction.objects.create(
        stock_account=account,
        movement_type=movement_type,
        quantity=quantity,
        effective_at=timezone.now(),
        created_by=actor,
        reason=reason,
        **links,
    )
    if movement_type in {MovementType.ADJUSTMENT, MovementType.COUNT_CORRECTION}:
        record_audit_event(
            action="ASSET_STOCK_ADJUSTED",
            category=AuditCategory.ASSETS,
            severity=AuditSeverity.HIGH,
            summary="Asset stock balance adjusted.",
            actor_user=actor,
            company=account.company,
            source_object=entry,
            metadata_safe={"movement_type": movement_type},
        )
    return entry


@transaction.atomic
def submit_asset_issue(*, issue: AssetIssue) -> AssetIssue:
    issue = AssetIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.status != IssueStatus.DRAFT or not issue.lines.exists():
        raise ValidationError("Only a non-empty draft issue can be submitted.")
    issue.status = IssueStatus.PENDING_APPROVAL
    issue.save(update_fields=["status", "updated_at"])
    return issue


@transaction.atomic
def approve_asset_issue(*, issue: AssetIssue, approved_by: User) -> AssetIssue:
    issue = AssetIssue.objects.select_for_update().get(pk=issue.pk)
    if issue.status != IssueStatus.PENDING_APPROVAL:
        raise ValidationError("Issue is not pending approval.")
    if issue.requested_by_id == approved_by.pk:
        raise ValidationError("Maker/checker policy prevents self-approval.")
    issue.lines.filter(approved_quantity__isnull=True).update(
        approved_quantity=models.F("requested_quantity")
    )
    issue.status, issue.approved_by, issue.approved_at = (
        IssueStatus.APPROVED,
        approved_by,
        timezone.now(),
    )
    issue.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    record_audit_event(
        action="ASSET_ISSUE_APPROVED",
        category=AuditCategory.ASSETS,
        severity=AuditSeverity.HIGH,
        summary="Asset issue approved.",
        actor_user=approved_by,
        company=issue.company,
        branch=issue.branch,
        source_object=issue,
        object_reference=issue.issue_number,
    )
    return issue


def _recipient(issue: AssetIssue) -> tuple[str, dict[str, Any]]:
    if issue.employee_id:
        return CustodyType.EMPLOYEE, {
            "to_employee": issue.employee,
            "current_employee": issue.employee,
        }
    if issue.site_id:
        return CustodyType.SITE, {"to_site": issue.site, "current_site": issue.site}
    if issue.branch_id:
        return CustodyType.BRANCH, {"to_branch": issue.branch, "current_branch": issue.branch}
    if issue.vehicle_id:
        return CustodyType.VEHICLE, {"current_vehicle": issue.vehicle}
    raise ValidationError("Issue recipient is missing.")


@transaction.atomic
def issue_assets(*, issue: AssetIssue, issued_by: User) -> AssetIssue:
    issue = (
        AssetIssue.objects.select_for_update()
        .prefetch_related("lines__item__category")
        .get(pk=issue.pk)
    )
    if issue.status != IssueStatus.APPROVED:
        raise ValidationError("Only approved issues can be issued.")
    custody_type, destination = _recipient(issue)
    for line in issue.lines.all():
        qty = line.approved_quantity or line.requested_quantity
        if line.item.category.tracking_method == TrackingMethod.SERIALIZED:
            if not line.serialized_asset_id or qty != 1:
                raise ValidationError("Serialized lines require exactly one asset.")
            asset = Asset.objects.select_for_update().get(pk=line.serialized_asset_id)
            if asset.status != AssetStatus.AVAILABLE or asset.item_id != line.item_id:
                raise ValidationError("Serialized asset is unavailable or mismatched.")
            if line.item.category.is_controlled and not issue.approved_by_id:
                raise ValidationError("Controlled assets require approval.")
            old_type, old_store, old_branch = (
                asset.current_custody_type,
                asset.current_warehouse,
                asset.current_branch,
            )
            AssetMovement.objects.create(
                asset=asset,
                movement_type=MovementType.ISSUE,
                moved_at=timezone.now(),
                from_custody_type=old_type,
                from_store=old_store,
                from_branch=old_branch,
                to_custody_type=custody_type,
                issue=issue,
                actor=issued_by,
                **{k: v for k, v in destination.items() if k.startswith("to_")},
            )
            asset.current_warehouse = asset.current_branch = asset.current_site = (
                asset.current_employee
            ) = asset.current_vehicle = None
            for key, value in destination.items():
                if key.startswith("current_"):
                    setattr(asset, key, value)
            asset.current_custody_type, asset.status = custody_type, AssetStatus.ISSUED
            asset.save()
        else:
            stock_account = line.stock_account
            if stock_account is None:
                raise ValidationError("Quantity lines require a source stock account.")
            post_stock_transaction(
                stock_account=stock_account,
                movement_type=MovementType.ISSUE,
                quantity=qty,
                actor=issued_by,
                asset_issue=issue,
            )
        line.issued_quantity = qty
        line.save(update_fields=["issued_quantity"])
    issue.status, issue.issued_by, issue.issued_at = IssueStatus.ISSUED, issued_by, timezone.now()
    issue.save(update_fields=["status", "issued_by", "issued_at", "updated_at"])
    record_audit_event(
        action="ASSETS_ISSUED",
        category=AuditCategory.ASSETS,
        severity=AuditSeverity.HIGH,
        summary="Assets issued to approved recipient.",
        actor_user=issued_by,
        company=issue.company,
        branch=issue.branch,
        source_object=issue,
        object_reference=issue.issue_number,
    )
    return issue


@transaction.atomic
def receive_asset_return(*, return_record: AssetReturn) -> AssetReturn:
    record = (
        AssetReturn.objects.select_for_update()
        .prefetch_related("lines__issue_line__item__category")
        .get(pk=return_record.pk)
    )
    issue = AssetIssue.objects.select_for_update().get(pk=record.original_issue_id)
    for return_line in record.lines.all():
        line = AssetIssueLine.objects.select_for_update().get(pk=return_line.issue_line_id)
        if line.returned_quantity + return_line.quantity > (line.issued_quantity or 0):
            raise ValidationError("Return quantity exceeds outstanding issued quantity.")
        if line.serialized_asset_id:
            if (
                return_line.serialized_asset_id != line.serialized_asset_id
                or return_line.quantity != 1
            ):
                raise ValidationError("Serialized returned asset does not match the issue.")
            asset = Asset.objects.select_for_update().get(pk=line.serialized_asset_id)
            stock_account = line.stock_account
            target = stock_account.store if stock_account is not None else None
            AssetMovement.objects.create(
                asset=asset,
                movement_type=MovementType.RETURN,
                moved_at=timezone.now(),
                from_custody_type=asset.current_custody_type,
                from_employee=asset.current_employee,
                from_site=asset.current_site,
                to_custody_type=CustodyType.WAREHOUSE if target else CustodyType.BRANCH,
                to_store=target,
                return_record=record,
                actor=record.received_by,
            )
            asset.current_employee = asset.current_site = asset.current_vehicle = (
                asset.current_branch
            ) = None
            asset.current_warehouse = target
            asset.current_custody_type = CustodyType.WAREHOUSE if target else CustodyType.BRANCH
            asset.status = (
                AssetStatus.UNDER_MAINTENANCE
                if return_line.requires_maintenance
                else AssetStatus.AVAILABLE
            )
            asset.condition = return_line.return_condition
            asset.save()
        elif line.stock_account is not None:
            post_stock_transaction(
                stock_account=line.stock_account,
                movement_type=MovementType.RETURN,
                quantity=return_line.quantity,
                actor=record.received_by,
                asset_return=record,
            )
        line.returned_quantity += return_line.quantity
        line.save(update_fields=["returned_quantity"])
    outstanding = (
        AssetIssueLine.objects.filter(asset_issue=issue, item__category__is_returnable=True)
        .filter(
            Q(issued_quantity__isnull=True) | Q(returned_quantity__lt=models.F("issued_quantity"))
        )
        .exists()
    )
    issue.status = IssueStatus.PARTIALLY_RETURNED if outstanding else IssueStatus.RETURNED
    issue.save(update_fields=["status", "updated_at"])
    record.status = "COMPLETED"
    record.save(update_fields=["status", "updated_at"])
    record_audit_event(
        action="ASSETS_RETURNED",
        category=AuditCategory.ASSETS,
        summary="Issued assets returned.",
        actor_user=record.received_by,
        company=issue.company,
        branch=issue.branch,
        source_object=record,
        object_reference=record.return_number,
    )
    return record


@transaction.atomic
def create_issue_from_kit(
    *, kit: AssetKitTemplate, requested_by: User, employee: Any = None, site: Any = None
) -> AssetIssue:
    if bool(employee) == bool(site):
        raise ValidationError("Provide exactly one employee or site.")
    count = AssetIssue.objects.filter(company=kit.company).count() + 1
    issue = AssetIssue.objects.create(
        issue_number=f"ISS-{timezone.localdate():%Y%m}-{count:06d}",
        company=kit.company,
        issue_type="EMPLOYEE_ASSIGNMENT" if employee else "SITE_ASSIGNMENT",
        employee=employee,
        site=site,
        requested_by=requested_by,
        purpose=f"Kit: {kit.name}",
    )
    AssetIssueLine.objects.bulk_create(
        [
            AssetIssueLine(asset_issue=issue, item=row.item, requested_quantity=row.quantity)
            for row in kit.items.select_related("item")
        ]
    )
    return issue


# Imported late only to keep model symbols grouped above.
from django.db import models  # noqa: E402
