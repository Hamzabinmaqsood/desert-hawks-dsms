from django.db import migrations


def backfill_legacy_company_module_policies(apps, schema_editor):  # type: ignore[no-untyped-def]
    Company = apps.get_model("organization", "Company")
    CompanyModulePolicy = apps.get_model("subscriptions", "CompanyModulePolicy")
    database = schema_editor.connection.alias
    existing_company_ids = set(
        CompanyModulePolicy.objects.using(database).values_list("company_id", flat=True)
    )
    CompanyModulePolicy.objects.using(database).bulk_create(
        [
            CompanyModulePolicy(company_id=company_id, mode="LEGACY_FULL")
            for company_id in Company.objects.using(database)
            .values_list("pk", flat=True)
            .iterator(chunk_size=1_000)
            if company_id not in existing_company_ids
        ],
        batch_size=1_000,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("subscriptions", "0002_plan_entitlement_revision_and_more"),
    ]

    operations = [
        migrations.RunPython(
            backfill_legacy_company_module_policies,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
