from typing import Any

from rest_framework import serializers

from dsms.organization.models import Company

from ..models import Plan, Subscription, SubscriptionEvent, SubscriptionStatus


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

    class Meta:
        model = Subscription
        fields = [
            "id",
            "company",
            "plan",
            "status",
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
