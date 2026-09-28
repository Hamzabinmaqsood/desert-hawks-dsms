"""Explicit tenant-consistency predicates for Assets API projections."""

from __future__ import annotations

from typing import Any

from django.db import models
from django.db.models import Exists, F, OuterRef, Q, QuerySet

from dsms.contracts.models import SecuritySite
from dsms.organization.models import Branch, Company, OperationalZone
from dsms.workforce.models import Employee

from .models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetIssueLine,
    AssetItem,
    AssetMovement,
    AssetStore,
    ProcurementInventoryAllocation,
    ProcurementInventoryHandoff,
    ProcurementInventoryRegistration,
    StockAccount,
)

COMPANY_PATHS: dict[type[models.Model], str] = {
    AssetCategory: "company_id",
    AssetItem: "company_id",
    AssetStore: "company_id",
    Asset: "company_id",
    StockAccount: "company_id",
    AssetIssue: "company_id",
    ProcurementInventoryHandoff: "company_id",
    ProcurementInventoryRegistration: "company_id",
    Branch: "company_id",
    OperationalZone: "company_id",
    Employee: "company_id",
    SecuritySite: "company_id",
}
GLOBAL_REFERENCES = {AssetCategory, AssetItem}


def company_id_for(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Company):
        return value.pk
    path = COMPANY_PATHS.get(type(value))
    if path is None:
        return None
    for segment in path.split("__"):
        value = getattr(value, segment, None)
        if value is None:
            return None
    return value


def tenant_consistent_asset_categories(
    queryset: QuerySet[AssetCategory],
) -> QuerySet[AssetCategory]:
    return queryset.filter(Q(company__isnull=True) | Q(company__is_active=True))


def tenant_consistent_asset_items(queryset: QuerySet[AssetItem]) -> QuerySet[AssetItem]:
    return (
        queryset.filter(Q(company__isnull=True) | Q(company__is_active=True))
        .filter(Q(category__company__isnull=True) | Q(category__company_id=F("company_id")))
        .filter(category__is_active=True)
    )


def _store_relations(prefix: str = "") -> tuple[Q, ...]:
    return (
        Q(**{f"{prefix}branch__isnull": True})
        | Q(**{f"{prefix}branch__company_id": F(f"{prefix}company_id")}),
        Q(**{f"{prefix}operational_zone__isnull": True})
        | Q(**{f"{prefix}operational_zone__company_id": F(f"{prefix}company_id")}),
        Q(**{f"{prefix}operational_zone__isnull": True})
        | Q(**{f"{prefix}operational_zone__branch__company_id": F(f"{prefix}company_id")}),
        Q(**{f"{prefix}store_manager__isnull": True})
        | Q(**{f"{prefix}store_manager__company_id": F(f"{prefix}company_id")}),
    )


def tenant_consistent_asset_stores(queryset: QuerySet[AssetStore]) -> QuerySet[AssetStore]:
    queryset = queryset.filter(company__is_active=True)
    for condition in _store_relations():
        queryset = queryset.filter(condition)
    return queryset


def _asset_relations(prefix: str = "") -> tuple[Q, ...]:
    owner = f"{prefix}company_id"
    return (
        Q(**{f"{prefix}item__company__isnull": True})
        | Q(**{f"{prefix}item__company_id": F(owner)}),
        Q(**{f"{prefix}item__category__company__isnull": True})
        | Q(**{f"{prefix}item__category__company_id": F(f"{prefix}item__company_id")}),
        Q(**{f"{prefix}current_warehouse__isnull": True})
        | Q(**{f"{prefix}current_warehouse__company_id": F(owner)}),
        Q(**{f"{prefix}current_branch__isnull": True})
        | Q(**{f"{prefix}current_branch__company_id": F(owner)}),
        Q(**{f"{prefix}current_site__isnull": True})
        | Q(**{f"{prefix}current_site__company_id": F(owner)}),
        Q(**{f"{prefix}current_employee__isnull": True})
        | Q(**{f"{prefix}current_employee__company_id": F(owner)}),
        Q(**{f"{prefix}current_vehicle__isnull": True})
        | Q(**{f"{prefix}current_vehicle__company_id": F(owner)}),
    )


def tenant_consistent_assets(queryset: QuerySet[Asset]) -> QuerySet[Asset]:
    queryset = queryset.filter(company__is_active=True, item__category__is_active=True)
    for condition in _asset_relations():
        queryset = queryset.filter(condition)
    for condition in _store_relations("current_warehouse__"):
        queryset = queryset.filter(Q(current_warehouse__isnull=True) | condition)
    return queryset


def tenant_consistent_stock_accounts(
    queryset: QuerySet[StockAccount],
) -> QuerySet[StockAccount]:
    return (
        queryset.filter(company__is_active=True, item__category__is_active=True)
        .filter(Q(item__company__isnull=True) | Q(item__company_id=F("company_id")))
        .filter(
            Q(item__category__company__isnull=True)
            | Q(item__category__company_id=F("item__company_id"))
        )
        .filter(Q(store__isnull=True) | Q(store__company_id=F("company_id")))
        .filter(
            Q(store__isnull=True)
            | Q(store__in=tenant_consistent_asset_stores(AssetStore.objects.all()))
        )
        .filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
    )


def _valid_issue_line() -> Q:
    return (
        (Q(item__company__isnull=True) | Q(item__company_id=OuterRef("company_id")))
        & (
            Q(item__category__company__isnull=True)
            | Q(item__category__company_id=F("item__company_id"))
        )
        & (
            Q(serialized_asset__isnull=True)
            | Q(serialized_asset__company_id=OuterRef("company_id"))
        )
        & (
            Q(serialized_asset__isnull=True)
            | Q(serialized_asset__in=tenant_consistent_assets(Asset.objects.all()))
        )
        & (Q(serialized_asset__isnull=True) | Q(serialized_asset__item_id=F("item_id")))
        & (Q(stock_account__isnull=True) | Q(stock_account__company_id=OuterRef("company_id")))
        & (
            Q(stock_account__isnull=True)
            | Q(stock_account__in=tenant_consistent_stock_accounts(StockAccount.objects.all()))
        )
        & (Q(stock_account__isnull=True) | Q(stock_account__item_id=F("item_id")))
    )


def tenant_consistent_asset_issues(queryset: QuerySet[AssetIssue]) -> QuerySet[AssetIssue]:
    invalid_lines = AssetIssueLine.objects.filter(asset_issue_id=OuterRef("pk")).exclude(
        _valid_issue_line()
    )
    return (
        queryset.filter(company__is_active=True)
        .filter(Q(employee__isnull=True) | Q(employee__company_id=F("company_id")))
        .filter(Q(site__isnull=True) | Q(site__company_id=F("company_id")))
        .filter(Q(branch__isnull=True) | Q(branch__company_id=F("company_id")))
        .filter(Q(vehicle__isnull=True) | Q(vehicle__company_id=F("company_id")))
        .annotate(_has_inconsistent_line=Exists(invalid_lines))
        .filter(_has_inconsistent_line=False)
    )


def tenant_consistent_asset_movements(
    queryset: QuerySet[AssetMovement],
) -> QuerySet[AssetMovement]:
    queryset = queryset.filter(
        asset__company__is_active=True,
        asset__in=tenant_consistent_assets(Asset.objects.all()),
    )
    for field in (
        "from_store",
        "to_store",
        "from_branch",
        "to_branch",
        "from_site",
        "to_site",
        "from_employee",
        "to_employee",
    ):
        queryset = queryset.filter(
            Q(**{f"{field}__isnull": True}) | Q(**{f"{field}__company_id": F("asset__company_id")})
        )
    return queryset.filter(
        Q(issue__isnull=True) | Q(issue__company_id=F("asset__company_id")),
        Q(return_record__isnull=True)
        | Q(return_record__original_issue__company_id=F("asset__company_id")),
    )


def tenant_consistent_procurement_handoffs(
    queryset: QuerySet[ProcurementInventoryHandoff],
) -> QuerySet[ProcurementInventoryHandoff]:
    return (
        queryset.filter(company__is_active=True)
        .filter(receipt_line__receipt__company_id=F("company_id"))
        .filter(Q(asset_item__company__isnull=True) | Q(asset_item__company_id=F("company_id")))
        .filter(
            Q(asset_item__category__company__isnull=True)
            | Q(asset_item__category__company_id=F("asset_item__company_id"))
        )
    )


def tenant_consistent_procurement_registrations(
    queryset: QuerySet[ProcurementInventoryRegistration],
) -> QuerySet[ProcurementInventoryRegistration]:
    invalid_allocations = ProcurementInventoryAllocation.objects.filter(
        registration_id=OuterRef("pk")
    ).exclude(
        (Q(asset__isnull=True) | Q(asset__company_id=OuterRef("company_id")))
        & (Q(asset__isnull=True) | Q(asset__in=tenant_consistent_assets(Asset.objects.all())))
        & (
            Q(stock_transaction__isnull=True)
            | Q(stock_transaction__stock_account__company_id=OuterRef("company_id"))
        )
        & (
            Q(stock_transaction__isnull=True)
            | Q(
                stock_transaction__stock_account__in=tenant_consistent_stock_accounts(
                    StockAccount.objects.all()
                )
            )
        )
    )
    return (
        queryset.filter(company__is_active=True)
        .filter(handoff__company_id=F("company_id"))
        .filter(handoff__receipt_line__receipt__company_id=F("company_id"))
        .filter(destination_store__company_id=F("company_id"))
        .filter(destination_store__in=tenant_consistent_asset_stores(AssetStore.objects.all()))
        .filter(
            Q(handoff__asset_item__company__isnull=True)
            | Q(handoff__asset_item__company_id=F("company_id"))
        )
        .filter(
            Q(handoff__asset_item__category__company__isnull=True)
            | Q(handoff__asset_item__category__company_id=F("handoff__asset_item__company_id"))
        )
        .annotate(_has_inconsistent_allocation=Exists(invalid_allocations))
        .filter(_has_inconsistent_allocation=False)
    )
