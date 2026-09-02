from django.db import migrations, models
from django.db.models import Count, F, Q


def validate_purchase_receipt_lines(apps, schema_editor):  # type: ignore[no-untyped-def]
    receipt_line = apps.get_model("finance", "PurchaseReceiptLine")
    counts = {
        "quantity_lte_zero": receipt_line.objects.filter(quantity__lte=0).count(),
        "accepted_negative": receipt_line.objects.filter(accepted_quantity__lt=0).count(),
        "accepted_gt_quantity": receipt_line.objects.filter(
            accepted_quantity__gt=F("quantity")
        ).count(),
        "duplicate_pairs": receipt_line.objects.values(
            "receipt_id", "purchase_order_line_id"
        )
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
        .count(),
    }
    if any(counts.values()):
        summary = ", ".join(f"{key}={value}" for key, value in counts.items())
        raise RuntimeError(
            "PurchaseReceiptLine integrity preflight failed; correct historical rows before "
            f"applying constraints ({summary})."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0006_paymentprovidersettlement_payment_settlement_amounts_valid_and_more"),
    ]

    operations = [
        migrations.RunPython(validate_purchase_receipt_lines, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="purchasereceiptline",
            constraint=models.CheckConstraint(
                condition=Q(quantity__gt=0), name="receipt_line_qty_positive"
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasereceiptline",
            constraint=models.CheckConstraint(
                condition=Q(accepted_quantity__gte=0),
                name="receipt_line_accepted_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasereceiptline",
            constraint=models.CheckConstraint(
                condition=Q(accepted_quantity__lte=F("quantity")),
                name="receipt_line_accepted_lte_qty",
            ),
        ),
        migrations.AddConstraint(
            model_name="purchasereceiptline",
            constraint=models.UniqueConstraint(
                fields=("receipt", "purchase_order_line"), name="uniq_receipt_po_line"
            ),
        ),
    ]
