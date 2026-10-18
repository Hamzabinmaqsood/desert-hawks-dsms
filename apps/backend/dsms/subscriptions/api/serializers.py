from typing import Any

from rest_framework import serializers

from dsms.organization.models import Company

from .. import entitlements
from ..models import (
    ModuleOverrideState,
    Plan,
    Subscription,
    SubscriptionEvent,
    SubscriptionStatus,
)


class PlanSerializer(serializers.ModelSerializer[Plan]):
    class Meta:
        model = Plan
        fields = ["id", "code", "name", "description", "is_active", "created_at", "updated_at"]
        read_only_fields = fields


class PlanCreateSerializer(serializers.Serializer[Any]):
    code = serializers.CharField(max_length=40)
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class PlanUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, required=False)
    description = serializers.CharField(max_length=10_000, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs:
            raise serializers.ValidationError("At least one mutable Plan field is required.")
        return attrs


class SubscriptionCompanySerializer(serializers.ModelSerializer[Company]):
    class Meta:
        model = Company
        fields = ["id", "code", "legal_name", "trade_name", "is_active"]
        read_only_fields = fields


class SubscriptionSerializer(serializers.ModelSerializer[Subscription]):
    company = SubscriptionCompanySerializer(read_only=True)
    plan = PlanSerializer(read_only=True)
    policy_mode = serializers.SerializerMethodField()
    effective_module_count = serializers.SerializerMethodField()
    entitlement_revision = serializers.SerializerMethodField()

    def _effective(self, obj: Subscription) -> entitlements.EffectiveModuleResult:
        return entitlements.resolve_effective_modules(obj.company)

    def get_policy_mode(self, obj: Subscription) -> str:
        return self._effective(obj).policy_mode

    def get_effective_module_count(self, obj: Subscription) -> int:
        return len(self._effective(obj).module_ids)

    def get_entitlement_revision(self, obj: Subscription) -> int:
        return self._effective(obj).entitlement_revision

    class Meta:
        model = Subscription
        fields = [
            "id",
            "company",
            "plan",
            "status",
            "policy_mode",
            "effective_module_count",
            "entitlement_revision",
            "starts_at",
            "trial_ends_at",
            "grace_ends_at",
            "suspended_at",
            "terminated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SubscriptionCreateSerializer(serializers.Serializer[Any]):
    company_id = serializers.UUIDField()
    plan_id = serializers.UUIDField()
    status = serializers.ChoiceField(
        choices=(SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL),
        default=SubscriptionStatus.ACTIVE,
    )
    starts_at = serializers.DateTimeField(required=False)
    trial_ends_at = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SubscriptionTransitionSerializer(serializers.Serializer[Any]):
    target_status = serializers.ChoiceField(choices=SubscriptionStatus.choices)
    grace_ends_at = serializers.DateTimeField(required=False, allow_null=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SubscriptionEventSerializer(serializers.ModelSerializer[SubscriptionEvent]):
    actor_id = serializers.UUIDField(read_only=True)
    previous_status = serializers.CharField(read_only=True)

    class Meta:
        model = SubscriptionEvent
        fields = [
            "id",
            "event_type",
            "previous_status",
            "resulting_status",
            "actor_id",
            "reason",
            "occurred_at",
        ]
        read_only_fields = fields


class ModuleCatalogSerializer(serializers.Serializer[Any]):
    id = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    classification = serializers.CharField(read_only=True)
    hard_dependencies = serializers.ListField(child=serializers.CharField(), read_only=True)
    legacy_default = serializers.BooleanField(read_only=True)


class PlanEntitlementUpdateSerializer(serializers.Serializer[Any]):
    enabled_module_ids = serializers.ListField(
        child=serializers.CharField(max_length=64), allow_empty=True
    )
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class SubscriptionOverrideBatchSerializer(serializers.Serializer[Any]):
    enabled_module_ids = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, allow_empty=True, default=list
    )
    disabled_module_ids = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, allow_empty=True, default=list
    )
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        enabled = set(attrs["enabled_module_ids"])
        disabled = set(attrs["disabled_module_ids"])
        contradictory = sorted(enabled & disabled)
        if contradictory:
            raise serializers.ValidationError({"contradictory_module_ids": contradictory})
        attrs["overrides"] = {
            **{module_id: ModuleOverrideState.ENABLED for module_id in enabled},
            **{module_id: ModuleOverrideState.DISABLED for module_id in disabled},
        }
        return attrs


class EntitlementActionSerializer(serializers.Serializer[Any]):
    reason = serializers.CharField(max_length=255, required=True, allow_blank=False)


class SubscriptionActivationSerializer(SubscriptionOverrideBatchSerializer):
    pass


class PlanEntitlementResponseSerializer(serializers.Serializer[Any]):
    plan_id = serializers.UUIDField(read_only=True)
    plan_code = serializers.CharField(read_only=True)
    plan_name = serializers.CharField(read_only=True)
    entitlement_revision = serializers.IntegerField(read_only=True)
    enabled_module_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    snapshot_notice = serializers.CharField(read_only=True)


class SubscriptionOverrideSerializer(serializers.Serializer[Any]):
    module_id = serializers.CharField(read_only=True)
    state = serializers.CharField(read_only=True)


class SubscriptionEntitlementResponseSerializer(serializers.Serializer[Any]):
    subscription_id = serializers.UUIDField(read_only=True)
    subscription_status = serializers.CharField(read_only=True)
    company = SubscriptionCompanySerializer(read_only=True)
    plan = PlanSerializer(read_only=True)
    policy_mode = serializers.CharField(read_only=True)
    plan_entitlement_revision = serializers.IntegerField(read_only=True)
    snapshot_plan_entitlement_revision = serializers.IntegerField(read_only=True, allow_null=True)
    entitlement_revision = serializers.IntegerField(read_only=True)
    snapshot_initialized = serializers.BooleanField(read_only=True)
    plan_module_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    snapshot_module_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
    overrides = SubscriptionOverrideSerializer(many=True, read_only=True)
    effective_module_ids = serializers.ListField(child=serializers.CharField(), read_only=True)
