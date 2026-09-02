from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet, Sum

from dsms.identity import access
from dsms.identity.models import User
from dsms.organization.models import Company
from dsms.workforce.models import Employee

from .enums import AssetStatus, IssueStatus, MovementType
from .models import (
    Asset,
    AssetCategory,
    AssetIssue,
    AssetItem,
    AssetMovement,
    AssetStore,
    ProcurementInventoryHandoff,
    ProcurementInventoryRegistration,
    StockAccount,
)


def procurement_registration_totals(*, handoff: ProcurementInventoryHandoff) -> dict[str, Decimal]:
    registered = handoff.allocations.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
    return {
        "accepted": handoff.accepted_quantity_snapshot,
        "registered": registered,
        "remaining": handoff.accepted_quantity_snapshot - registered,
    }


def accessible_procurement_registrations(
    *, user: User
) -> QuerySet[ProcurementInventoryRegistration]:
    stores = accessible_asset_stores(
        user=user, permission="assets.view_procurementinventoryregistration"
    )
    procurement_companies = access.get_accessible_company_ids(
        user, permission="finance.view_purchasereceipt"
    )
    controlled = accessible_asset_stores(user=user, permission="assets.view_controlled_asset")
    return (
        ProcurementInventoryRegistration.objects.select_related(
            "handoff__asset_item__category",
            "handoff__receipt_line__receipt",
            "destination_store",
            "registered_by",
        )
        .prefetch_related("allocations__asset", "allocations__stock_transaction")
        .filter(destination_store__in=stores, handoff__company_id__in=procurement_companies)
        .filter(
            Q(handoff__asset_item__category__is_controlled=False)
            | Q(destination_store__in=controlled)
        )
        .order_by("-registered_at")
    )


def _company_scope(user: User, permission: str, *, include_global: bool = False) -> Q:
    condition = Q(company_id__in=access.get_accessible_company_ids(user, permission=permission))
    return condition | Q(company__isnull=True) if include_global else condition


def _location_scope(user: User, permission: str) -> Q:
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    return (
        Q(branch_id__in=branch_ids)
        | Q(site__managing_branch_id__in=branch_ids)
        | Q(store__branch_id__in=branch_ids)
        | Q(store__operational_zone__branch_id__in=branch_ids)
        | Q(
            branch__isnull=True,
            site__isnull=True,
            store__branch__isnull=True,
            store__operational_zone__isnull=True,
            company_id__in=company_ids,
        )
    )


def _asset_location_scope(user: User, permission: str) -> Q:
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    return (
        Q(current_branch_id__in=branch_ids)
        | Q(current_site__managing_branch_id__in=branch_ids)
        | Q(current_employee__branch_id__in=branch_ids)
        | Q(current_warehouse__branch_id__in=branch_ids)
        | Q(current_warehouse__operational_zone__branch_id__in=branch_ids)
        | Q(current_vehicle__current_branch_id__in=branch_ids)
        | Q(current_vehicle__current_site__managing_branch_id__in=branch_ids)
        | Q(current_vehicle__current_employee__branch_id__in=branch_ids)
        | Q(current_vehicle__current_warehouse__branch_id__in=branch_ids)
        | Q(company_id__in=company_ids)
    )


def accessible_asset_categories(*, user: User, permission: str) -> QuerySet[AssetCategory]:
    queryset = AssetCategory.objects.select_related("company").filter(
        _company_scope(user, permission, include_global=True)
    )
    controlled_scope = _company_scope(user, "assets.view_controlled_asset", include_global=True)
    return queryset.filter(Q(is_controlled=False) | controlled_scope).order_by("pk").distinct()


def accessible_asset_items(*, user: User, permission: str) -> QuerySet[AssetItem]:
    queryset = AssetItem.objects.select_related("company", "category").filter(
        _company_scope(user, permission, include_global=True)
    )
    controlled_scope = _company_scope(user, "assets.view_controlled_asset", include_global=True)
    return (
        queryset.filter(Q(category__is_controlled=False) | controlled_scope)
        .order_by("pk")
        .distinct()
    )


def accessible_asset_stores(*, user: User, permission: str) -> QuerySet[AssetStore]:
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    scope = (
        Q(branch_id__in=branch_ids)
        | Q(operational_zone__branch_id__in=branch_ids)
        | Q(
            branch__isnull=True,
            operational_zone__isnull=True,
            company_id__in=company_ids,
        )
    )
    return (
        AssetStore.objects.select_related(
            "company", "branch", "operational_zone__branch", "store_manager"
        )
        .filter(scope)
        .order_by("pk")
        .distinct()
    )


def accessible_assets(*, user: User, permission: str) -> QuerySet[Asset]:
    queryset = Asset.objects.select_related(
        "company",
        "item__category",
        "current_warehouse__branch",
        "current_branch__region",
        "current_site__managing_branch",
        "current_employee__branch",
        "current_vehicle",
    ).filter(_asset_location_scope(user, permission))
    controlled_scope = _asset_location_scope(user, "assets.view_controlled_asset")
    return (
        queryset.filter(Q(item__category__is_controlled=False) | controlled_scope)
        .order_by("pk")
        .distinct()
    )


def accessible_stock_accounts(*, user: User, permission: str) -> QuerySet[StockAccount]:
    queryset = StockAccount.objects.select_related(
        "company", "item__category", "store__branch", "branch__region", "site__managing_branch"
    ).filter(_location_scope(user, permission))
    controlled_branches = access.get_accessible_branch_ids(
        user, permission="assets.view_controlled_asset"
    )
    controlled_companies = access.get_fully_accessible_company_ids(
        user, permission="assets.view_controlled_asset"
    )
    controlled_scope = (
        Q(branch_id__in=controlled_branches)
        | Q(site__managing_branch_id__in=controlled_branches)
        | Q(store__branch_id__in=controlled_branches)
        | Q(store__operational_zone__branch_id__in=controlled_branches)
        | Q(company_id__in=controlled_companies)
    )
    return (
        queryset.filter(Q(item__category__is_controlled=False) | controlled_scope)
        .order_by("pk")
        .distinct()
    )


def accessible_asset_issues(*, user: User, permission: str) -> QuerySet[AssetIssue]:
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    scope = (
        Q(branch_id__in=branch_ids)
        | Q(site__managing_branch_id__in=branch_ids)
        | Q(employee__branch_id__in=branch_ids)
        | Q(vehicle__current_branch_id__in=branch_ids)
        | Q(vehicle__current_site__managing_branch_id__in=branch_ids)
        | Q(lines__stock_account__branch_id__in=branch_ids)
        | Q(lines__stock_account__site__managing_branch_id__in=branch_ids)
        | Q(lines__stock_account__store__branch_id__in=branch_ids)
        | Q(company_id__in=company_ids)
    )
    controlled_branches = access.get_accessible_branch_ids(
        user, permission="assets.view_controlled_asset"
    )
    controlled_companies = access.get_fully_accessible_company_ids(
        user, permission="assets.view_controlled_asset"
    )
    controlled_scope = (
        Q(branch_id__in=controlled_branches)
        | Q(site__managing_branch_id__in=controlled_branches)
        | Q(employee__branch_id__in=controlled_branches)
        | Q(company_id__in=controlled_companies)
    )
    controlled_issues = AssetIssue.objects.filter(lines__item__category__is_controlled=True)
    return (
        AssetIssue.objects.select_related(
            "company",
            "employee__branch",
            "site__managing_branch",
            "branch",
            "requested_by",
            "approved_by",
            "issued_by",
        )
        .prefetch_related("lines__item__category")
        .filter(scope)
        .filter(~Q(pk__in=controlled_issues) | controlled_scope)
        .order_by("pk")
        .distinct()
    )


def accessible_asset_movements(*, user: User, permission: str) -> QuerySet[AssetMovement]:
    branch_ids = access.get_accessible_branch_ids(user, permission=permission)
    company_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    scope = (
        Q(asset__company_id__in=company_ids)
        | Q(asset__current_branch_id__in=branch_ids)
        | Q(asset__current_site__managing_branch_id__in=branch_ids)
        | Q(asset__current_employee__branch_id__in=branch_ids)
        | Q(asset__current_warehouse__branch_id__in=branch_ids)
        | Q(from_branch_id__in=branch_ids)
        | Q(to_branch_id__in=branch_ids)
        | Q(from_site__managing_branch_id__in=branch_ids)
        | Q(to_site__managing_branch_id__in=branch_ids)
        | Q(from_employee__branch_id__in=branch_ids)
        | Q(to_employee__branch_id__in=branch_ids)
        | Q(from_store__branch_id__in=branch_ids)
        | Q(to_store__branch_id__in=branch_ids)
    )
    controlled_scope = _asset_location_scope(user, "assets.view_controlled_asset")
    return (
        AssetMovement.objects.select_related(
            "asset__item__category",
            "actor",
            "from_store",
            "to_store",
            "from_employee",
            "to_employee",
        )
        .filter(scope)
        .filter(
            Q(asset__item__category__is_controlled=False)
            | Q(asset__in=Asset.objects.filter(controlled_scope))
        )
        .order_by("-moved_at")
        .distinct()
    )


def asset_scope_kwargs(asset: Asset) -> dict[str, Any]:
    branch = (
        asset.current_branch
        or getattr(asset.current_site, "managing_branch", None)
        or getattr(asset.current_employee, "branch", None)
        or getattr(asset.current_warehouse, "branch", None)
    )
    return {
        "company": asset.company,
        "region": getattr(branch, "region", None),
        "branch": branch,
        "operational_zone": getattr(asset.current_warehouse, "operational_zone", None),
    }


def asset_category_list(*, company: Company) -> QuerySet[AssetCategory]:
    return AssetCategory.objects.filter(company__in=[company, None]).order_by("code")


def asset_item_list(*, company: Company) -> QuerySet[AssetItem]:
    return AssetItem.objects.filter(company__in=[company, None]).select_related("category")


def asset_list(*, company: Company) -> QuerySet[Asset]:
    return Asset.objects.filter(company=company).select_related(
        "item__category", "current_warehouse", "current_branch", "current_site", "current_employee"
    )


def available_assets(*, company: Company) -> QuerySet[Asset]:
    return asset_list(company=company).filter(status=AssetStatus.AVAILABLE)


def assets_by_employee(*, employee: Employee) -> QuerySet[Asset]:
    return Asset.objects.filter(company=employee.company, current_employee=employee).select_related(
        "item__category"
    )


def asset_custody_history(*, asset: Asset) -> QuerySet[AssetMovement]:
    return (
        AssetMovement.objects.filter(asset=asset)
        .select_related("actor", "from_store", "to_store", "from_employee", "to_employee")
        .order_by("-moved_at")
    )


def open_asset_issues(*, company: Company) -> QuerySet[AssetIssue]:
    return (
        AssetIssue.objects.filter(company=company)
        .exclude(status__in=[IssueStatus.RETURNED, IssueStatus.CANCELLED, IssueStatus.REJECTED])
        .prefetch_related("lines__item")
    )


def stock_balance_summary(*, company: Company) -> QuerySet[StockAccount]:
    positive = [
        MovementType.RECEIPT,
        MovementType.RETURN,
        MovementType.RECOVERY,
        MovementType.MAINTENANCE_RETURN,
    ]
    return (
        StockAccount.objects.filter(company=company)
        .select_related("item", "store", "branch", "site")
        .annotate(
            total_in=Sum(
                "transactions__quantity", filter=models.Q(transactions__movement_type__in=positive)
            ),
            total_out=Sum(
                "transactions__quantity", filter=~models.Q(transactions__movement_type__in=positive)
            ),
        )
    )


from django.db import models  # noqa: E402
