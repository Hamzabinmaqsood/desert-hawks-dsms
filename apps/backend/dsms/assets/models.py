from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from dsms.common.models import TimeStampedModel, UUIDModel

from .enums import (
    AssetCategoryType,
    AssetCondition,
    AssetStatus,
    CustodyType,
    IssueStatus,
    IssueType,
    MovementType,
    RequirementType,
    ReturnCondition,
    ReturnStatus,
    TrackingMethod,
    UnitOfMeasure,
)


class AssetBase(UUIDModel, TimeStampedModel):
    class Meta:
        abstract = True


class AssetCategory(AssetBase):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    category_type = models.CharField(max_length=40, choices=AssetCategoryType.choices)
    description = models.TextField(blank=True)
    tracking_method = models.CharField(max_length=20, choices=TrackingMethod.choices)
    is_returnable = models.BooleanField(default=True)
    is_consumable = models.BooleanField(default=False)
    requires_approval_for_issue = models.BooleanField(default=False)
    requires_employee_authorization = models.BooleanField(default=False)
    requires_serial_number = models.BooleanField(default=False)
    requires_periodic_inspection = models.BooleanField(default=False)
    default_inspection_interval_days = models.PositiveIntegerField(null=True, blank=True)
    requires_maintenance = models.BooleanField(default=False)
    is_controlled = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        permissions = [
            ("view_controlled_asset", "Can view controlled assets"),
            ("view_asset_financial_values", "Can view asset financial values"),
            ("approve_asset_issue", "Can approve asset issues"),
            ("issue_asset", "Can issue assets"),
            ("adjust_stock", "Can post stock adjustments"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="asset_category_company_code_uniq"
            ),
            models.UniqueConstraint(
                fields=["code"],
                condition=Q(company__isnull=True),
                name="asset_category_global_code_uniq",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        if self.is_controlled:
            self.requires_approval_for_issue = True
        super().save(*args, **kwargs)


class AssetItem(AssetBase):
    company = models.ForeignKey(
        "organization.Company", null=True, blank=True, on_delete=models.PROTECT
    )
    category = models.ForeignKey(AssetCategory, on_delete=models.PROTECT, related_name="items")
    item_code = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    manufacturer = models.CharField(max_length=150, blank=True)
    model = models.CharField(max_length=150, blank=True)
    unit_of_measure = models.CharField(max_length=20, choices=UnitOfMeasure.choices)
    standard_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    reorder_level = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    reorder_quantity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    expected_useful_life_months = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "item_code"], name="asset_item_company_code_uniq"
            )
        ]
        indexes = [
            models.Index(fields=["company", "is_active"], name="asset_item_company_active_idx")
        ]

    def clean(self) -> None:
        if self.category.company_id not in (None, self.company_id):
            raise ValidationError({"category": "Category belongs to another company."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.item_code = self.item_code.strip().upper()
        super().save(*args, **kwargs)


class AssetStore(AssetBase):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    operational_zone = models.ForeignKey(
        "organization.OperationalZone", null=True, blank=True, on_delete=models.PROTECT
    )
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    address = models.TextField(blank=True)
    store_manager = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    is_central_store = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "code"], name="asset_store_company_code_uniq"
            )
        ]

    def clean(self) -> None:
        errors = {}
        branch = self.branch
        manager = self.store_manager
        if branch is not None and branch.company_id != self.company_id:
            errors["branch"] = "Branch belongs to another company."
        if manager is not None and manager.company_id != self.company_id:
            errors["store_manager"] = "Manager belongs to another company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)


class Asset(AssetBase):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    item = models.ForeignKey(AssetItem, on_delete=models.PROTECT, related_name="assets")
    asset_number = models.CharField(max_length=50)
    serial_number = models.CharField(max_length=150, null=True, blank=True)
    manufacturer_serial = models.CharField(max_length=150, null=True, blank=True)
    barcode_value = models.CharField(max_length=150, null=True, blank=True)
    qr_identifier = models.CharField(max_length=150, null=True, blank=True)
    acquired_on = models.DateField(null=True, blank=True)
    procurement_receipt_reference = models.CharField(max_length=200, null=True, blank=True)
    purchase_order_reference = models.CharField(max_length=200, null=True, blank=True)
    acquisition_cost = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    status = models.CharField(
        max_length=30, choices=AssetStatus.choices, default=AssetStatus.PENDING_REGISTRATION
    )
    condition = models.CharField(
        max_length=20, choices=AssetCondition.choices, default=AssetCondition.NEW
    )
    current_custody_type = models.CharField(max_length=40, choices=CustodyType.choices)
    current_warehouse = models.ForeignKey(
        AssetStore, null=True, blank=True, on_delete=models.PROTECT
    )
    current_branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    current_site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    current_employee = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    current_vehicle = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT)
    warranty_expires_on = models.DateField(null=True, blank=True)
    expected_retirement_on = models.DateField(null=True, blank=True)
    retired_on = models.DateField(null=True, blank=True)
    disposal_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "asset_number"], name="asset_company_number_uniq"
            ),
            models.UniqueConstraint(
                fields=["company", "serial_number"],
                condition=Q(serial_number__isnull=False),
                name="asset_company_serial_uniq",
            ),
        ]
        indexes = [models.Index(fields=["company", "status"], name="asset_company_status_idx")]

    def clean(self) -> None:
        if self.item.category.tracking_method != TrackingMethod.SERIALIZED:
            raise ValidationError({"item": "Only serialized catalog items can have Asset records."})
        if self.item.company_id not in (None, self.company_id):
            raise ValidationError({"item": "Item belongs to another company."})
        if self.item.category.requires_serial_number and not self.serial_number:
            raise ValidationError({"serial_number": "A serial number is required."})
        mapping: dict[str, Any] = {
            CustodyType.WAREHOUSE: self.current_warehouse_id,
            CustodyType.BRANCH: self.current_branch_id,
            CustodyType.SITE: self.current_site_id,
            CustodyType.EMPLOYEE: self.current_employee_id,
            CustodyType.VEHICLE: self.current_vehicle_id,
        }
        populated = sum(bool(v) for v in mapping.values())
        if self.current_custody_type in mapping and (
            not mapping[self.current_custody_type] or populated != 1
        ):
            raise ValidationError(
                "Exactly the custody field matching current_custody_type is required."
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.asset_number = self.asset_number.strip().upper()
        super().save(*args, **kwargs)


class StockAccount(UUIDModel):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    item = models.ForeignKey(AssetItem, on_delete=models.PROTECT, related_name="stock_accounts")
    store = models.ForeignKey(AssetStore, null=True, blank=True, on_delete=models.PROTECT)
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(store__isnull=False, branch__isnull=True, site__isnull=True)
                    | Q(store__isnull=True, branch__isnull=False, site__isnull=True)
                    | Q(store__isnull=True, branch__isnull=True, site__isnull=False)
                ),
                name="stock_account_one_location",
            ),
            models.UniqueConstraint(
                fields=["item", "store"],
                condition=Q(store__isnull=False),
                name="stock_account_item_store_uniq",
            ),
            models.UniqueConstraint(
                fields=["item", "branch"],
                condition=Q(branch__isnull=False),
                name="stock_account_item_branch_uniq",
            ),
            models.UniqueConstraint(
                fields=["item", "site"],
                condition=Q(site__isnull=False),
                name="stock_account_item_site_uniq",
            ),
        ]


class AssetIssue(AssetBase):
    issue_number = models.CharField(max_length=50)
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    issue_type = models.CharField(max_length=30, choices=IssueType.choices)
    employee = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    site = models.ForeignKey(
        "contracts.SecuritySite", null=True, blank=True, on_delete=models.PROTECT
    )
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    vehicle = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_asset_issues"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_asset_issues",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="issued_asset_issues",
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    expected_return_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=30, choices=IssueStatus.choices, default=IssueStatus.DRAFT)
    purpose = models.TextField()
    notes = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "issue_number"], name="asset_issue_company_number_uniq"
            )
        ]

    def clean(self) -> None:
        recipients = [self.employee_id, self.site_id, self.branch_id, self.vehicle_id]
        if sum(bool(x) for x in recipients) != 1:
            raise ValidationError("Exactly one issue recipient is required.")


class AssetIssueLine(UUIDModel):
    asset_issue = models.ForeignKey(AssetIssue, on_delete=models.PROTECT, related_name="lines")
    item = models.ForeignKey(AssetItem, on_delete=models.PROTECT)
    serialized_asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    stock_account = models.ForeignKey(StockAccount, null=True, blank=True, on_delete=models.PROTECT)
    requested_quantity = models.DecimalField(max_digits=18, decimal_places=3)
    approved_quantity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    issued_quantity = models.DecimalField(max_digits=18, decimal_places=3, null=True, blank=True)
    returned_quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    condition_at_issue = models.CharField(
        max_length=20, choices=AssetCondition.choices, null=True, blank=True
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_quantity__gt=0), name="asset_issue_line_qty_positive"
            ),
            models.CheckConstraint(
                condition=Q(returned_quantity__gte=0), name="asset_issue_line_return_nonnegative"
            ),
        ]


class AssetReturn(AssetBase):
    return_number = models.CharField(max_length=50, unique=True)
    original_issue = models.ForeignKey(AssetIssue, on_delete=models.PROTECT, related_name="returns")
    returned_by_employee = models.ForeignKey(
        "workforce.Employee", null=True, blank=True, on_delete=models.PROTECT
    )
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    returned_at = models.DateTimeField()
    status = models.CharField(
        max_length=20, choices=ReturnStatus.choices, default=ReturnStatus.DRAFT
    )
    notes = models.TextField(blank=True)


class AssetReturnLine(UUIDModel):
    return_record = models.ForeignKey(AssetReturn, on_delete=models.PROTECT, related_name="lines")
    issue_line = models.ForeignKey(
        AssetIssueLine, on_delete=models.PROTECT, related_name="return_lines"
    )
    serialized_asset = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    return_condition = models.CharField(max_length=20, choices=ReturnCondition.choices)
    damage_notes = models.TextField(blank=True)
    requires_maintenance = models.BooleanField(default=False)
    received_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0), name="asset_return_line_qty_positive"
            )
        ]


class StockTransaction(UUIDModel):
    stock_account = models.ForeignKey(
        StockAccount, on_delete=models.PROTECT, related_name="transactions"
    )
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    effective_at = models.DateTimeField()
    source_reference = models.CharField(max_length=200, blank=True)
    procurement_receipt_reference = models.CharField(max_length=200, null=True, blank=True)
    asset_issue = models.ForeignKey(AssetIssue, null=True, blank=True, on_delete=models.PROTECT)
    asset_return = models.ForeignKey(AssetReturn, null=True, blank=True, on_delete=models.PROTECT)
    reverses_transaction = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal"
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(quantity=Decimal("0")), name="stock_transaction_qty_nonzero"
            )
        ]
        indexes = [
            models.Index(fields=["stock_account", "effective_at"], name="stock_tx_account_time_idx")
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and StockTransaction.objects.filter(pk=self.pk).exists():
            raise ValidationError("Stock transactions are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Stock transactions cannot be deleted.")


class AssetMovement(UUIDModel):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    from_custody_type = models.CharField(
        max_length=40, choices=CustodyType.choices, null=True, blank=True
    )
    from_store = models.ForeignKey(
        AssetStore,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="outgoing_movements",
    )
    from_branch = models.ForeignKey(
        "organization.Branch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="asset_movements_from",
    )
    from_site = models.ForeignKey(
        "contracts.SecuritySite",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="asset_movements_from",
    )
    from_employee = models.ForeignKey(
        "workforce.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="asset_movements_from",
    )
    to_custody_type = models.CharField(
        max_length=40, choices=CustodyType.choices, null=True, blank=True
    )
    to_store = models.ForeignKey(
        AssetStore,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="incoming_movements",
    )
    to_branch = models.ForeignKey(
        "organization.Branch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="asset_movements_to",
    )
    to_site = models.ForeignKey(
        "contracts.SecuritySite",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="asset_movements_to",
    )
    to_employee = models.ForeignKey(
        "workforce.Employee",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="asset_movements_to",
    )
    moved_at = models.DateTimeField()
    issue = models.ForeignKey(AssetIssue, null=True, blank=True, on_delete=models.PROTECT)
    return_record = models.ForeignKey(AssetReturn, null=True, blank=True, on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["asset", "moved_at"], name="asset_move_asset_time_idx")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and AssetMovement.objects.filter(pk=self.pk).exists():
            raise ValidationError("Asset movements are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Asset movements cannot be deleted.")


class AssetKitTemplate(AssetBase):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    code = models.CharField(max_length=50)
    name = models.CharField(max_length=150)
    employee_type = models.CharField(max_length=30, null=True, blank=True)
    designation = models.ForeignKey(
        "organization.Designation", null=True, blank=True, on_delete=models.PROTECT
    )
    site_type = models.ForeignKey(
        "contracts.SiteType", null=True, blank=True, on_delete=models.PROTECT
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="asset_kit_company_code_uniq")
        ]


class AssetKitTemplateItem(UUIDModel):
    kit_template = models.ForeignKey(
        AssetKitTemplate, on_delete=models.PROTECT, related_name="items"
    )
    item = models.ForeignKey(AssetItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    mandatory = models.BooleanField(default=True)
    returnable_override = models.BooleanField(null=True, blank=True)
    replacement_cycle_days = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)


class AssetRequirementPolicy(AssetBase):
    company = models.ForeignKey("organization.Company", on_delete=models.PROTECT)
    employee_type = models.CharField(max_length=30, null=True, blank=True)
    designation = models.ForeignKey(
        "organization.Designation", null=True, blank=True, on_delete=models.PROTECT
    )
    branch = models.ForeignKey(
        "organization.Branch", null=True, blank=True, on_delete=models.PROTECT
    )
    item = models.ForeignKey(AssetItem, on_delete=models.PROTECT)
    required_quantity = models.DecimalField(max_digits=18, decimal_places=3)
    requirement_type = models.CharField(max_length=20, choices=RequirementType.choices)
    replacement_cycle_days = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(required_quantity__gt=0), name="asset_requirement_qty_positive"
            )
        ]
