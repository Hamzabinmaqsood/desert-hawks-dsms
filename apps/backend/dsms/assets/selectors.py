from django.db.models import QuerySet, Sum

from dsms.organization.models import Company
from dsms.workforce.models import Employee

from .enums import AssetStatus, IssueStatus, MovementType
from .models import Asset, AssetCategory, AssetIssue, AssetItem, AssetMovement, StockAccount


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
