from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from typing import Any
from uuid import UUID

import pytest
from django.db import close_old_connections
from django.db.models import Sum

from dsms.finance import domain_services
from dsms.finance.enums import ReceiptType, WorkflowStatus
from dsms.finance.exceptions import FinanceError
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

pytestmark = pytest.mark.django_db(transaction=True)


def procurement_graph() -> dict[str, Any]:
    company = CompanyFactory.create()
    actor = UserFactory.create()
    _year, _period, accounts = accounting_setup(company)
    vendor = Vendor.objects.create(
        company=company,
        code="CONCURRENT-VENDOR",
        name="Supplier",
        payable_account=accounts["payable"],
    )
    requisition = PurchaseRequisition.objects.create(
        company=company,
        requisition_number="CONCURRENT-REQ",
        required_date=date(2026, 8, 10),
        purpose="Concurrent receipt test",
        status=WorkflowStatus.APPROVED,
        created_by=actor,
    )
    requisition_line = PurchaseRequisitionLine.objects.create(
        requisition=requisition,
        description="Equipment",
        quantity=Decimal("10"),
        estimated_unit_price=Decimal("100"),
        expense_account=accounts["expense"],
    )
    order = PurchaseOrder.objects.create(
        company=company,
        requisition=requisition,
        vendor=vendor,
        order_number="CONCURRENT-PO",
        order_date=date(2026, 8, 11),
        status=WorkflowStatus.APPROVED,
        created_by=actor,
    )
    order_line = PurchaseOrderLine.objects.create(
        purchase_order=order,
        requisition_line=requisition_line,
        description="Equipment",
        quantity=Decimal("10"),
        unit_price=Decimal("100"),
    )
    return {"company": company, "actor": actor, "order": order, "order_line": order_line}


def receipt_for(graph: dict[str, Any], number: str, quantity: Decimal) -> PurchaseReceipt:
    receipt = PurchaseReceipt.objects.create(
        company=graph["company"],
        purchase_order=graph["order"],
        receipt_number=number,
        receipt_date=date(2026, 8, 12),
        receipt_type=ReceiptType.GOODS,
        received_by=graph["actor"],
    )
    PurchaseReceiptLine.objects.create(
        receipt=receipt,
        purchase_order_line=graph["order_line"],
        quantity=quantity,
        accepted_quantity=quantity,
    )
    return receipt


def confirm_concurrently(receipt_ids: list[UUID]) -> list[bool]:
    barrier = Barrier(len(receipt_ids))

    def confirm(receipt_id: UUID) -> bool:
        close_old_connections()
        try:
            barrier.wait(timeout=10)
            domain_services.confirm_receipt(receipt=PurchaseReceipt.objects.get(pk=receipt_id))
        except FinanceError:
            return False
        finally:
            close_old_connections()
        return True

    with ThreadPoolExecutor(max_workers=len(receipt_ids)) as executor:
        return list(executor.map(confirm, receipt_ids))


def approved_total(order_line: PurchaseOrderLine) -> Decimal:
    return PurchaseReceiptLine.objects.filter(
        purchase_order_line=order_line,
        receipt__status=WorkflowStatus.APPROVED,
    ).aggregate(total=Sum("accepted_quantity"))["total"] or Decimal("0")


def test_concurrent_over_receipt_never_exceeds_ordered_quantity() -> None:
    graph = procurement_graph()
    first = receipt_for(graph, "RACE-7", Decimal("7"))
    second = receipt_for(graph, "RACE-6", Decimal("6"))
    results = confirm_concurrently([first.id, second.id])
    assert sorted(results) == [False, True]
    assert approved_total(graph["order_line"]) <= Decimal("10")
    assert PurchaseReceipt.objects.filter(status=WorkflowStatus.APPROVED).count() == 1


def test_concurrent_exact_fill_approves_both_receipts() -> None:
    graph = procurement_graph()
    first = receipt_for(graph, "RACE-4", Decimal("4"))
    second = receipt_for(graph, "RACE-6", Decimal("6"))
    results = confirm_concurrently([first.id, second.id])
    assert results == [True, True]
    assert approved_total(graph["order_line"]) == Decimal("10")
    assert PurchaseReceipt.objects.filter(status=WorkflowStatus.APPROVED).count() == 2


def test_concurrent_double_confirmation_transitions_once() -> None:
    graph = procurement_graph()
    receipt = receipt_for(graph, "RACE-SAME", Decimal("5"))
    results = confirm_concurrently([receipt.id, receipt.id])
    assert sorted(results) == [False, True]
    receipt.refresh_from_db()
    assert receipt.status == WorkflowStatus.APPROVED
    assert approved_total(graph["order_line"]) == Decimal("5")
