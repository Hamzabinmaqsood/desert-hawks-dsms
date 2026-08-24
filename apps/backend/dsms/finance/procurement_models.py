from decimal import Decimal

from django.db import models
from django.db.models import Q

from dsms.common.models import ActiveModel, TimeStampedModel, UUIDModel
from dsms.identity.models import User
from dsms.organization.models import Branch, Company, Department

from .enums import MatchType, PaymentStatus, ReceiptType, WorkflowStatus
from .models import Account, CostCenter, JournalEntry


class Vendor(UUIDModel, TimeStampedModel, ActiveModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="vendors")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    tax_number = models.CharField(max_length=60, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    payment_terms_days = models.PositiveIntegerField(default=30)
    payable_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="vendors")
    bank_details_encrypted = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["company", "code"], name="uniq_vendor_code")]


class PurchaseRequisition(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(
        Company, on_delete=models.PROTECT, related_name="purchase_requisitions"
    )
    branch = models.ForeignKey(
        Branch,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_requisitions",
    )
    department = models.ForeignKey(
        Department,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_requisitions",
    )
    cost_center = models.ForeignKey(
        CostCenter,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_requisitions",
    )
    requisition_number = models.CharField(max_length=30)
    required_date = models.DateField()
    purpose = models.TextField()
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_requisitions"
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_requisitions"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "requisition_number"], name="uniq_requisition_number"
            )
        ]


class PurchaseRequisitionLine(UUIDModel):
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.PROTECT, related_name="lines"
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    estimated_unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="requisition_lines"
    )

    @property
    def estimated_total(self) -> Decimal:
        return self.quantity * self.estimated_unit_price


class PurchaseOrder(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="purchase_orders")
    requisition = models.ForeignKey(
        PurchaseRequisition, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="purchase_orders")
    order_number = models.CharField(max_length=30)
    order_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_purchase_orders"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_purchase_orders",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "order_number"], name="uniq_purchase_order_number"
            )
        ]


class PurchaseOrderLine(UUIDModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="lines"
    )
    requisition_line = models.ForeignKey(
        PurchaseRequisitionLine, on_delete=models.PROTECT, related_name="purchase_order_lines"
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price + self.tax_amount


class PurchaseReceipt(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="purchase_receipts")
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receipts"
    )
    receipt_number = models.CharField(max_length=30)
    receipt_date = models.DateField()
    receipt_type = models.CharField(max_length=20, choices=ReceiptType.choices)
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    received_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="purchase_receipts"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "receipt_number"], name="uniq_receipt_number"
            )
        ]


class PurchaseReceiptLine(UUIDModel):
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.PROTECT, related_name="lines")
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine, on_delete=models.PROTECT, related_name="receipt_lines"
    )
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    accepted_quantity = models.DecimalField(max_digits=18, decimal_places=4)
    notes = models.CharField(max_length=255, blank=True)


class VendorBill(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="vendor_bills")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="bills")
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.PROTECT, related_name="vendor_bills"
    )
    vendor_invoice_number = models.CharField(max_length=100)
    bill_number = models.CharField(max_length=30)
    bill_date = models.DateField()
    due_date = models.DateField()
    match_type = models.CharField(
        max_length=20, choices=MatchType.choices, default=MatchType.TWO_WAY
    )
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    match_exception = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_vendor_bills"
    )
    approved_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.PROTECT, related_name="approved_vendor_bills"
    )
    journal_entry = models.OneToOneField(
        JournalEntry, null=True, blank=True, on_delete=models.PROTECT, related_name="vendor_bill"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "vendor", "vendor_invoice_number"], name="uniq_vendor_invoice"
            )
        ]

    @property
    def outstanding_amount(self) -> Decimal:
        return self.total_amount - self.paid_amount


class VendorBillLine(UUIDModel):
    vendor_bill = models.ForeignKey(VendorBill, on_delete=models.PROTECT, related_name="lines")
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bill_lines",
    )
    receipt_line = models.ForeignKey(
        PurchaseReceiptLine,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="bill_lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    unit_price = models.DecimalField(max_digits=18, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    expense_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="vendor_bill_lines"
    )

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price + self.tax_amount


class PaymentVoucher(UUIDModel, TimeStampedModel):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name="payment_vouchers")
    vendor_bill = models.ForeignKey(
        VendorBill, null=True, blank=True, on_delete=models.PROTECT, related_name="payment_vouchers"
    )
    voucher_number = models.CharField(max_length=30)
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(
        max_length=20, choices=WorkflowStatus.choices, default=WorkflowStatus.DRAFT
    )
    payment_status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="created_payment_vouchers"
    )
    approved_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="approved_payment_vouchers",
    )
    journal_entry = models.OneToOneField(
        JournalEntry,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="payment_voucher",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "voucher_number"], name="uniq_payment_voucher_number"
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_voucher_positive"),
        ]
