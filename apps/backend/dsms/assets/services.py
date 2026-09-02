from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.finance import domain_selectors as finance_selectors
from dsms.finance.procurement_models import PurchaseOrderLine, PurchaseReceipt, PurchaseReceiptLine
from dsms.finance.services import next_document_number
from dsms.identity import access
from dsms.identity.models import User

from .enums import AssetStatus, CustodyType, IssueStatus, MovementType, TrackingMethod
from .models import (
    Asset,
    AssetIssue,
    AssetIssueLine,
    AssetItem,
    AssetKitTemplate,
    AssetMovement,
    AssetReturn,
    AssetStore,
    ProcurementInventoryAllocation,
    ProcurementInventoryHandoff,
    ProcurementInventoryRegistration,
    StockAccount,
    StockTransaction,
)


class ProcurementRegistrationConflict(ValidationError):
    pass


def _store_scope(store: AssetStore) -> dict[str, Any]:
    branch = store.branch or getattr(store.operational_zone, "branch", None)
    return {
        "company": store.company,
        "region": getattr(branch, "region", None),
        "branch": branch,
        "operational_zone": store.operational_zone,
    }


def _canonical_hash(
    *,
    receipt_line: PurchaseReceiptLine,
    asset_item: AssetItem,
    destination_store: AssetStore,
    quantity: Decimal | None,
    assets: list[dict[str, str]] | None,
) -> str:
    units = []
    for unit in assets or []:
        units.append(
            {
                key: (unit.get(key) or "").strip()
                for key in (
                    "receipt_unit_key",
                    "serial_number",
                    "manufacturer_serial",
                    "barcode_value",
                    "qr_identifier",
                )
            }
        )
    units.sort(key=lambda item: item["receipt_unit_key"])
    payload = {
        "receipt_line": str(receipt_line.pk),
        "asset_item": str(asset_item.pk),
        "destination_store": str(destination_store.pk),
        "quantity": str(quantity) if quantity is not None else None,
        "assets": units,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def procurement_registered_quantity(*, handoff: ProcurementInventoryHandoff) -> Decimal:
    return handoff.allocations.aggregate(total=Sum("quantity"))["total"] or Decimal("0")


@transaction.atomic
def establish_procurement_handoff(
    *, receipt_line: PurchaseReceiptLine, asset_item: AssetItem, actor: User
) -> ProcurementInventoryHandoff:
    receipt = PurchaseReceipt.objects.select_for_update().get(pk=receipt_line.receipt_id)
    PurchaseOrderLine.objects.select_for_update().get(pk=receipt_line.purchase_order_line_id)
    line = (
        PurchaseReceiptLine.objects.select_for_update()
        .select_related("receipt__purchase_order", "purchase_order_line")
        .get(pk=receipt_line.pk)
    )
    if not finance_selectors.is_inventory_registration_eligible(receipt_line=line):
        raise ValidationError("Receipt line is not eligible for inventory registration.")
    existing = (
        ProcurementInventoryHandoff.objects.select_for_update().filter(receipt_line=line).first()
    )
    if existing:
        if existing.asset_item_id != asset_item.pk:
            raise ProcurementRegistrationConflict("Receipt line mapping is immutable.")
        return existing
    if not asset_item.is_active or asset_item.company_id not in (None, receipt.company_id):
        raise ValidationError({"asset_item": "Active item must belong to the receipt company."})
    handoff = ProcurementInventoryHandoff.objects.create(
        receipt_line=line,
        company=receipt.company,
        asset_item=asset_item,
        tracking_method=asset_item.category.tracking_method,
        accepted_quantity_snapshot=line.accepted_quantity,
        unit_cost_snapshot=line.purchase_order_line.unit_price,
        created_by=actor,
    )
    record_audit_event(
        action="PROCUREMENT_INVENTORY_HANDOFF_ESTABLISHED",
        category=AuditCategory.ASSETS,
        summary="Procurement inventory handoff established.",
        actor_user=actor,
        company=receipt.company,
        source_object=handoff,
        metadata_safe={
            "handoff_id": str(handoff.pk),
            "receipt_id": str(receipt.pk),
            "asset_item_id": str(asset_item.pk),
            "tracking_method": handoff.tracking_method,
        },
    )
    return handoff


@transaction.atomic
def register_procurement_inventory(
    *,
    receipt_line: PurchaseReceiptLine,
    asset_item: AssetItem,
    destination_store: AssetStore,
    idempotency_key: Any,
    actor: User,
    quantity: Decimal | None = None,
    assets: list[dict[str, str]] | None = None,
) -> tuple[ProcurementInventoryRegistration, bool]:
    handoff = establish_procurement_handoff(
        receipt_line=receipt_line, asset_item=asset_item, actor=actor
    )
    handoff = (
        ProcurementInventoryHandoff.objects.select_for_update()
        .select_related("receipt_line__receipt__purchase_order", "asset_item__category")
        .get(pk=handoff.pk)
    )
    store = AssetStore.objects.select_for_update().get(pk=destination_store.pk)
    item = AssetItem.objects.select_for_update().select_related("category").get(pk=asset_item.pk)
    if store.company_id != handoff.company_id or not store.is_active:
        raise ValidationError(
            {"destination_store": "Active store must belong to the receipt company."}
        )
    operation = (
        "assets.register_asset"
        if handoff.tracking_method == TrackingMethod.SERIALIZED
        else "assets.receive_asset_stock"
    )
    if not access.has_permission(
        user=actor, permission=operation, **_store_scope(store)
    ) or not access.has_permission(
        user=actor, permission="finance.view_purchasereceipt", company=handoff.company
    ):
        raise PermissionError("Registration permission and procurement visibility are required.")
    if item.category.is_controlled and not access.has_permission(
        user=actor, permission="assets.view_controlled_asset", **_store_scope(store)
    ):
        raise PermissionError("Controlled inventory permission is required.")
    payload_hash = _canonical_hash(
        receipt_line=receipt_line,
        asset_item=item,
        destination_store=store,
        quantity=quantity,
        assets=assets,
    )
    prior = ProcurementInventoryRegistration.objects.filter(
        company=handoff.company, idempotency_key=idempotency_key
    ).first()
    if prior:
        if prior.payload_hash != payload_hash:
            raise ProcurementRegistrationConflict(
                "Idempotency key was already used for another payload."
            )
        record_audit_event(
            action="PROCUREMENT_REGISTRATION_REPLAYED",
            category=AuditCategory.ASSETS,
            summary="Procurement registration replay resolved idempotently.",
            actor_user=actor,
            company=handoff.company,
            source_object=prior,
            object_reference=prior.registration_number,
            metadata_safe={"registration_id": str(prior.pk), "handoff_id": str(handoff.pk)},
        )
        return prior, True
    requested = Decimal(quantity) if quantity is not None else Decimal(len(assets or []))
    if (
        requested <= 0
        or procurement_registered_quantity(handoff=handoff) + requested
        > handoff.accepted_quantity_snapshot
    ):
        raise ProcurementRegistrationConflict("Registration exceeds remaining accepted quantity.")
    registration_number = next_document_number(
        company=handoff.company,
        prefix="AIR",
        year=handoff.receipt_line.receipt.receipt_date.year,
    )
    try:
        with transaction.atomic():
            registration = ProcurementInventoryRegistration.objects.create(
                handoff=handoff,
                company=handoff.company,
                destination_store=store,
                registration_number=registration_number,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                registered_by=actor,
            )
    except IntegrityError:
        prior = ProcurementInventoryRegistration.objects.get(
            company=handoff.company, idempotency_key=idempotency_key
        )
        if prior.payload_hash != payload_hash:
            raise ProcurementRegistrationConflict(
                "Idempotency key was already used for another payload."
            ) from None
        return prior, True
    if handoff.tracking_method == TrackingMethod.SERIALIZED:
        units = assets or []
        keys = [(unit.get("receipt_unit_key") or "").strip() for unit in units]
        if any(not key for key in keys) or len(keys) != len(set(keys)) or quantity is not None:
            raise ValidationError(
                {"assets": "Serialized units require unique receipt_unit_key values."}
            )
        for unit, unit_key in zip(units, keys, strict=True):
            serial = (unit.get("serial_number") or "").strip() or None
            if item.category.requires_serial_number and not serial:
                raise ValidationError({"serial_number": "A serial number is required."})
            asset = Asset(
                company=handoff.company,
                item=item,
                asset_number=next_document_number(
                    company=handoff.company,
                    prefix="AST",
                    year=handoff.receipt_line.receipt.receipt_date.year,
                ),
                serial_number=serial,
                manufacturer_serial=(unit.get("manufacturer_serial") or "").strip() or None,
                barcode_value=(unit.get("barcode_value") or "").strip() or None,
                qr_identifier=(unit.get("qr_identifier") or "").strip() or None,
                acquired_on=handoff.receipt_line.receipt.receipt_date,
                procurement_receipt_reference=handoff.receipt_line.receipt.receipt_number,
                purchase_order_reference=handoff.receipt_line.receipt.purchase_order.order_number,
                acquisition_cost=handoff.unit_cost_snapshot,
                status=AssetStatus.AVAILABLE,
                current_custody_type=CustodyType.WAREHOUSE,
                current_warehouse=store,
            )
            asset.full_clean()
            asset.save()
            AssetMovement.objects.create(
                asset=asset,
                movement_type=MovementType.RECEIPT,
                to_custody_type=CustodyType.WAREHOUSE,
                to_store=store,
                moved_at=timezone.now(),
                actor=actor,
                reason="Procurement inventory registration",
            )
            ProcurementInventoryAllocation.objects.create(
                handoff=handoff,
                registration=registration,
                receipt_unit_key=unit_key,
                quantity=1,
                asset=asset,
            )
        event = "PROCUREMENT_SERIALIZED_ASSETS_REGISTERED"
    else:
        if (
            assets
            or quantity is None
            or Decimal(quantity) != Decimal(quantity).quantize(Decimal("0.001"))
        ):
            raise ValidationError(
                {"quantity": "Quantity tracking requires positive precision up to 3 decimals."}
            )
        try:
            with transaction.atomic():
                account, _ = StockAccount.objects.get_or_create(
                    company=handoff.company, item=item, store=store
                )
        except IntegrityError:
            account = StockAccount.objects.get(item=item, store=store)
        transaction_entry = post_stock_transaction(
            stock_account=account,
            movement_type=MovementType.RECEIPT,
            quantity=Decimal(quantity),
            actor=actor,
            reason="Procurement inventory registration",
            procurement_receipt_reference=handoff.receipt_line.receipt.receipt_number,
            source_reference=registration.registration_number,
        )
        ProcurementInventoryAllocation.objects.create(
            handoff=handoff,
            registration=registration,
            quantity=quantity,
            stock_transaction=transaction_entry,
        )
        event = "PROCUREMENT_QUANTITY_STOCK_RECEIVED"
    remaining = handoff.accepted_quantity_snapshot - procurement_registered_quantity(
        handoff=handoff
    )
    record_audit_event(
        action=event,
        category=AuditCategory.ASSETS,
        severity=AuditSeverity.HIGH if item.category.is_controlled else AuditSeverity.INFO,
        summary="Procurement inventory registered.",
        actor_user=actor,
        company=handoff.company,
        source_object=registration,
        object_reference=registration.registration_number,
        metadata_safe={
            "handoff_id": str(handoff.pk),
            "registration_id": str(registration.pk),
            "asset_item_id": str(item.pk),
            "destination_store_id": str(store.pk),
            "quantity": str(requested),
            "remaining_quantity": str(remaining),
            "tracking_method": handoff.tracking_method,
        },
    )
    record_audit_event(
        action=(
            "PROCUREMENT_REGISTRATION_COMPLETED"
            if remaining == 0
            else "PROCUREMENT_REGISTRATION_PARTIAL"
        ),
        category=AuditCategory.ASSETS,
        severity=AuditSeverity.HIGH if item.category.is_controlled else AuditSeverity.INFO,
        summary="Procurement registration budget updated.",
        actor_user=actor,
        company=handoff.company,
        source_object=registration,
        object_reference=registration.registration_number,
        metadata_safe={"handoff_id": str(handoff.pk), "remaining_quantity": str(remaining)},
    )
    return registration, False


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
