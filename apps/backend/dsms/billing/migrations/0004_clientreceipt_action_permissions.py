from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("billing", "0003_alter_clientinvoicedocument_file")]

    operations = [
        migrations.AlterModelOptions(
            name="clientreceipt",
            options={
                "permissions": [
                    ("confirm_receipt", "Can confirm client receipts"),
                    ("allocate_receipt", "Can allocate client receipts"),
                    ("reverse_receipt", "Can reverse client receipts"),
                ]
            },
        )
    ]
