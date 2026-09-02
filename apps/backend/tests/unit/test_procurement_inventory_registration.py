from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError

from dsms.assets.enums import (
    AssetCategoryType,
    AssetStatus,
    CustodyType,
    MovementType,
    TrackingMethod,
    UnitOfMeasure,
)
from dsms.assets.models import (
    Asset,
    AssetCategory,
    AssetItem,
    AssetMovement,
    AssetStore,
    ProcurementInventoryAllocation,
    ProcurementInventoryHandoff,
    ProcurementInventoryRegistration,
    StockAccount,
    StockTransaction,
)
from dsms.assets.services import (
    ProcurementRegistrationConflict,
    establish_procurement_handoff,
    get_stock_balance,
    procurement_registered_quantity,
    register_procurement_inventory,
)
from dsms.finance import domain_services
from dsms.finance.enums import ReceiptType, WorkflowStatus
from dsms.finance.procurement_models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseReceipt,
    PurchaseReceiptLine,
    PurchaseRequisition,
    PurchaseRequisitionLine,
    Vendor,
)
from tests.factories.finance import accounting_setup
from tests.factories.identity import UserFactory
from tests.factories.organization import CompanyFactory

pytestmark = pytest.mark.django_db


def graph(
    tracking: str = TrackingMethod.QUANTITY, accepted: Decimal = Decimal("10")
) -> tuple[Any, Any, AssetItem, AssetStore, PurchaseReceiptLine]:
    company, actor = CompanyFactory.create(), UserFactory.create(is_superuser=True)
    _year, _period, accounts = accounting_setup(company)
    category = AssetCategory.objects.create(
        company=company,
        code=f"CAT-{tracking}",
        name="Procured",
        category_type=AssetCategoryType.OTHER,
        tracking_method=tracking,
        requires_serial_number=tracking == TrackingMethod.SERIALIZED,
    )
    item = AssetItem.objects.create(
        company=company,
        category=category,
        item_code=f"ITEM-{tracking}",
        name="Procured item",
        unit_of_measure=UnitOfMeasure.PIECE,
    )
    store = AssetStore.objects.create(company=company, code="MAIN", name="Main")
    vendor = Vendor.objects.create(
        company=company, code="VENDOR", name="Supplier", payable_account=accounts["payable"]
    )
    req = PurchaseRequisition.objects.create(
        company=company,
        requisition_number="REQ",
        required_date=date(2026, 9, 1),
        purpose="Inventory",
        status=WorkflowStatus.APPROVED,
        created_by=actor,
    )
    req_line = PurchaseRequisitionLine.objects.create(
        requisition=req,
        description="Inventory",
        quantity=10,
        estimated_unit_price=Decimal("25.50"),
        expense_account=accounts["expense"],
    )
    order = PurchaseOrder.objects.create(
        company=company,
        requisition=req,
        vendor=vendor,
        order_number="PO",
        order_date=date(2026, 9, 1),
        status=WorkflowStatus.APPROVED,
        created_by=actor,
    )
    order_line = PurchaseOrderLine.objects.create(
        purchase_order=order,
        requisition_line=req_line,
        description="Inventory",
        quantity=10,
        unit_price=Decimal("25.50"),
    )
    receipt = PurchaseReceipt.objects.create(
        company=company,
        purchase_order=order,
        receipt_number="GRN",
        receipt_date=date(2026, 9, 2),
        receipt_type=ReceiptType.GOODS,
        received_by=actor,
    )
    line = PurchaseReceiptLine.objects.create(
        receipt=receipt, purchase_order_line=order_line, quantity=10, accepted_quantity=accepted
    )
    domain_services.confirm_receipt(receipt=receipt)
    return company, actor, item, store, line


def test_handoff_snapshots_and_mapping_is_immutable() -> None:
    company, actor, item, _store, line = graph()
    handoff = establish_procurement_handoff(receipt_line=line, asset_item=item, actor=actor)
    assert handoff.company == company
    assert handoff.tracking_method == TrackingMethod.QUANTITY
    assert handoff.accepted_quantity_snapshot == 10
    assert handoff.unit_cost_snapshot == Decimal("25.50")
    assert establish_procurement_handoff(receipt_line=line, asset_item=item, actor=actor) == handoff
    other = AssetItem.objects.create(
        company=company,
        category=item.category,
        item_code="OTHER",
        name="Other",
        unit_of_measure=UnitOfMeasure.PIECE,
    )
    with pytest.raises(ProcurementRegistrationConflict):
        establish_procurement_handoff(receipt_line=line, asset_item=other, actor=actor)


def test_quantity_registration_partial_replay_and_ledger_balance() -> None:
    _company, actor, item, store, line = graph()
    key = uuid4()
    first, replayed = register_procurement_inventory(
        receipt_line=line,
        asset_item=item,
        destination_store=store,
        idempotency_key=key,
        actor=actor,
        quantity=Decimal("4"),
    )
    replay, was_replayed = register_procurement_inventory(
        receipt_line=line,
        asset_item=item,
        destination_store=store,
        idempotency_key=key,
        actor=actor,
        quantity=Decimal("4"),
    )
    assert (replayed, was_replayed, replay.pk) == (False, True, first.pk)
    handoff = first.handoff
    assert procurement_registered_quantity(handoff=handoff) == 4
    assert ProcurementInventoryRegistration.objects.count() == 1
    assert StockTransaction.objects.get().movement_type == MovementType.RECEIPT
    assert get_stock_balance(stock_account=StockAccount.objects.get())["available"] == 4
    assert ProcurementInventoryAllocation.objects.get().stock_transaction_id is not None


def test_quantity_over_registration_and_idempotency_conflict() -> None:
    _company, actor, item, store, line = graph()
    key = uuid4()
    register_procurement_inventory(
        receipt_line=line,
        asset_item=item,
        destination_store=store,
        idempotency_key=key,
        actor=actor,
        quantity=Decimal("7"),
    )
    with pytest.raises(ProcurementRegistrationConflict):
        register_procurement_inventory(
            receipt_line=line,
            asset_item=item,
            destination_store=store,
            idempotency_key=uuid4(),
            actor=actor,
            quantity=Decimal("4"),
        )
    with pytest.raises(ProcurementRegistrationConflict):
        register_procurement_inventory(
            receipt_line=line,
            asset_item=item,
            destination_store=store,
            idempotency_key=key,
            actor=actor,
            quantity=Decimal("6"),
        )


def test_serialized_batch_creates_available_assets_movements_and_allocations() -> None:
    _company, actor, item, store, line = graph(TrackingMethod.SERIALIZED, Decimal("2"))
    registration, _ = register_procurement_inventory(
        receipt_line=line,
        asset_item=item,
        destination_store=store,
        idempotency_key=uuid4(),
        actor=actor,
        assets=[
            {"receipt_unit_key": "unit-2", "serial_number": "SER-2"},
            {"receipt_unit_key": "unit-1", "serial_number": "SER-1"},
        ],
    )
    assert (
        Asset.objects.filter(
            status=AssetStatus.AVAILABLE,
            current_custody_type=CustodyType.WAREHOUSE,
            current_warehouse=store,
        ).count()
        == 2
    )
    assert (
        AssetMovement.objects.filter(movement_type=MovementType.RECEIPT, to_store=store).count()
        == 2
    )
    assert registration.allocations.filter(quantity=1, stock_transaction=None).count() == 2
    assert len(set(Asset.objects.values_list("asset_number", flat=True))) == 2


def test_serialized_batch_is_atomic_on_duplicate_serial() -> None:
    _company, actor, item, store, line = graph(TrackingMethod.SERIALIZED, Decimal("2"))
    with pytest.raises(ValidationError):
        register_procurement_inventory(
            receipt_line=line,
            asset_item=item,
            destination_store=store,
            idempotency_key=uuid4(),
            actor=actor,
            assets=[
                {"receipt_unit_key": "one", "serial_number": "DUP"},
                {"receipt_unit_key": "two", "serial_number": "DUP"},
            ],
        )
    assert not Asset.objects.exists()
    assert not ProcurementInventoryHandoff.objects.exists()


def test_service_receipt_is_not_eligible_for_handoff() -> None:
    _company, actor, item, _store, line = graph()
    line.receipt.receipt_type = ReceiptType.SERVICE
    line.receipt.save(update_fields=["receipt_type"])
    with pytest.raises(ValidationError):
        establish_procurement_handoff(receipt_line=line, asset_item=item, actor=actor)
