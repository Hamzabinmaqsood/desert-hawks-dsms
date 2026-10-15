import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

MIGRATE_FROM = [("subscriptions", "0001_initial")]
MIGRATE_TO = [("subscriptions", "0003_backfill_legacy_company_module_policies")]


def test_legacy_policy_backfill_preserves_companies_and_commercial_rows() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate(MIGRATE_FROM)
    old_apps = executor.loader.project_state(MIGRATE_FROM).apps
    Company = old_apps.get_model("organization", "Company")
    Plan = old_apps.get_model("subscriptions", "Plan")
    Subscription = old_apps.get_model("subscriptions", "Subscription")
    first = Company.objects.create(code="MIG-A", legal_name="Migration Company A")
    second = Company.objects.create(code="MIG-B", legal_name="Migration Company B")
    plan = Plan.objects.create(code="MIGRATION", name="Existing Plan", is_active=True)
    subscription = Subscription.objects.create(
        company=first,
        plan=plan,
        status="ACTIVE",
        starts_at=timezone.now(),
    )

    try:
        executor = MigrationExecutor(connection)
        executor.migrate(MIGRATE_TO)
        new_apps = executor.loader.project_state(MIGRATE_TO).apps
        NewCompany = new_apps.get_model("organization", "Company")
        NewPlan = new_apps.get_model("subscriptions", "Plan")
        NewSubscription = new_apps.get_model("subscriptions", "Subscription")
        CompanyModulePolicy = new_apps.get_model("subscriptions", "CompanyModulePolicy")
        PlanModuleDefault = new_apps.get_model("subscriptions", "PlanModuleDefault")
        SubscriptionModuleSnapshot = new_apps.get_model(
            "subscriptions", "SubscriptionModuleSnapshot"
        )
        SubscriptionModuleOverride = new_apps.get_model(
            "subscriptions", "SubscriptionModuleOverride"
        )

        assert CompanyModulePolicy.objects.count() == 2
        assert set(CompanyModulePolicy.objects.values_list("company_id", "mode")) == {
            (first.pk, "LEGACY_FULL"),
            (second.pk, "LEGACY_FULL"),
        }
        assert NewPlan.objects.count() == 1
        assert NewSubscription.objects.count() == 1
        migrated_subscription = NewSubscription.objects.get(pk=subscription.pk)
        assert migrated_subscription.status == "ACTIVE"
        assert migrated_subscription.entitlement_revision == 0
        assert migrated_subscription.snapshot_initialized_at is None
        assert PlanModuleDefault.objects.count() == 0
        assert SubscriptionModuleSnapshot.objects.count() == 0
        assert SubscriptionModuleOverride.objects.count() == 0
        assert NewCompany.objects.get(pk=first.pk).legal_name == "Migration Company A"
        assert NewCompany.objects.get(pk=second.pk).legal_name == "Migration Company B"
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
