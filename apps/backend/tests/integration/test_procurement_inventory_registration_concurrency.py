from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from typing import Any
from uuid import UUID, uuid4

import pytest
from django.db import close_old_connections

from dsms.assets.enums import TrackingMethod
from dsms.assets.models import (
    Asset,
    ProcurementInventoryAllocation,
    ProcurementInventoryRegistration,
    StockAccount,
)
from dsms.assets.services import procurement_registered_quantity, register_procurement_inventory
from dsms.finance.procurement_models import PurchaseReceiptLine
from tests.unit.test_procurement_inventory_registration import graph

pytestmark = pytest.mark.django_db(transaction=True)


def concurrent_requests(
    line_id: UUID, item_id: UUID, store_id: UUID, requests: list[dict[str, Any]]
) -> list[tuple[bool, UUID | None, bool]]:
    barrier = Barrier(len(requests))

    def run(request: dict[str, Any]) -> tuple[bool, UUID | None, bool]:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            from dsms.assets.models import AssetItem, AssetStore

            result, replayed = register_procurement_inventory(
                receipt_line=PurchaseReceiptLine.objects.get(pk=line_id),
                asset_item=AssetItem.objects.get(pk=item_id),
                destination_store=AssetStore.objects.get(pk=store_id),
                **request,
            )
            return True, result.pk, replayed
        except Exception:
            return False, None, False
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        return list(executor.map(run, requests))


def test_concurrent_quantity_over_registration_7_plus_6() -> None:
    _company, actor, item, store, line = graph()
    results = concurrent_requests(
        line.pk,
        item.pk,
        store.pk,
        [
            {"idempotency_key": uuid4(), "actor": actor, "quantity": Decimal("7")},
            {"idempotency_key": uuid4(), "actor": actor, "quantity": Decimal("6")},
        ],
    )
    assert sum(success for success, _pk, _replay in results) == 1
    handoff = line.inventory_handoff
    assert procurement_registered_quantity(handoff=handoff) <= 10


def test_concurrent_quantity_exact_fill_4_plus_6() -> None:
    _company, actor, item, store, line = graph()
    results = concurrent_requests(
        line.pk,
        item.pk,
        store.pk,
        [
            {"idempotency_key": uuid4(), "actor": actor, "quantity": Decimal("4")},
            {"idempotency_key": uuid4(), "actor": actor, "quantity": Decimal("6")},
        ],
    )
    assert all(success for success, _pk, _replay in results)
    assert procurement_registered_quantity(handoff=line.inventory_handoff) == 10


def test_concurrent_serialized_receipt_unit_collision() -> None:
    _company, actor, item, store, line = graph(TrackingMethod.SERIALIZED, Decimal("2"))
    results = concurrent_requests(
        line.pk,
        item.pk,
        store.pk,
        [
            {
                "idempotency_key": uuid4(),
                "actor": actor,
                "assets": [{"receipt_unit_key": "same-unit", "serial_number": "SER-A"}],
            },
            {
                "idempotency_key": uuid4(),
                "actor": actor,
                "assets": [{"receipt_unit_key": "same-unit", "serial_number": "SER-B"}],
            },
        ],
    )
    assert sum(success for success, _pk, _replay in results) == 1
    assert ProcurementInventoryAllocation.objects.filter(receipt_unit_key="same-unit").count() == 1


def test_concurrent_same_idempotency_same_payload_replays() -> None:
    _company, actor, item, store, line = graph()
    key = uuid4()
    request = {"idempotency_key": key, "actor": actor, "quantity": Decimal("4")}
    results = concurrent_requests(line.pk, item.pk, store.pk, [request, request])
    assert all(success for success, _pk, _replay in results)
    assert len({pk for _success, pk, _replay in results}) == 1
    assert ProcurementInventoryRegistration.objects.count() == 1


def test_concurrent_same_idempotency_different_payload_conflicts() -> None:
    _company, actor, item, store, line = graph()
    key = uuid4()
    results = concurrent_requests(
        line.pk,
        item.pk,
        store.pk,
        [
            {"idempotency_key": key, "actor": actor, "quantity": Decimal("4")},
            {"idempotency_key": key, "actor": actor, "quantity": Decimal("6")},
        ],
    )
    assert sum(success for success, _pk, _replay in results) == 1
    assert ProcurementInventoryRegistration.objects.count() == 1


def test_concurrent_stock_account_creation_produces_one_account() -> None:
    _company, actor, item, store, line = graph()
    results = concurrent_requests(
        line.pk,
        item.pk,
        store.pk,
        [
            {"idempotency_key": uuid4(), "actor": actor, "quantity": Decimal("2")},
            {"idempotency_key": uuid4(), "actor": actor, "quantity": Decimal("3")},
        ],
    )
    assert all(success for success, _pk, _replay in results)
    assert StockAccount.objects.filter(item=item, store=store).count() == 1


def test_concurrent_asset_numbering_is_unique() -> None:
    _company, actor, item, store, line = graph(TrackingMethod.SERIALIZED, Decimal("2"))
    results = concurrent_requests(
        line.pk,
        item.pk,
        store.pk,
        [
            {
                "idempotency_key": uuid4(),
                "actor": actor,
                "assets": [{"receipt_unit_key": "unit-a", "serial_number": "SER-A"}],
            },
            {
                "idempotency_key": uuid4(),
                "actor": actor,
                "assets": [{"receipt_unit_key": "unit-b", "serial_number": "SER-B"}],
            },
        ],
    )
    assert all(success for success, _pk, _replay in results)
    assert Asset.objects.count() == 2
    assert len(set(Asset.objects.values_list("asset_number", flat=True))) == 2
