from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from dsms.common.models import TimeStampedModel, UUIDModel
from dsms.common.validators import CODE_VALIDATOR, normalize_code

from .modules import validate_registered_module_id


class SubscriptionStatus(models.TextChoices):
    TRIAL = "TRIAL", "Trial"
    ACTIVE = "ACTIVE", "Active"
    GRACE = "GRACE", "Grace"
    SUSPENDED = "SUSPENDED", "Suspended"
    TERMINATED = "TERMINATED", "Terminated"


class SubscriptionEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    STATUS_CHANGED = "STATUS_CHANGED", "Status changed"


class CompanyModulePolicyMode(models.TextChoices):
    LEGACY_FULL = "LEGACY_FULL", "Legacy full access"
    SUBSCRIPTION = "SUBSCRIPTION", "Subscription entitlements"


class ModuleOverrideState(models.TextChoices):
    ENABLED = "ENABLED", "Enabled"
    DISABLED = "DISABLED", "Disabled"


class PlanEntitlementEventType(models.TextChoices):
    MODULE_ENABLED = "MODULE_ENABLED", "Module enabled"
    MODULE_DISABLED = "MODULE_DISABLED", "Module disabled"


class SubscriptionEntitlementEventType(models.TextChoices):
    SNAPSHOT_INITIALIZED = "SNAPSHOT_INITIALIZED", "Snapshot initialized"
    PLAN_REVISION_APPLIED = "PLAN_REVISION_APPLIED", "Plan revision applied"
    OVERRIDE_ENABLED = "OVERRIDE_ENABLED", "Override enabled"
    OVERRIDE_DISABLED = "OVERRIDE_DISABLED", "Override disabled"
    OVERRIDE_CLEARED = "OVERRIDE_CLEARED", "Override cleared"
    POLICY_CONVERTED = "POLICY_CONVERTED", "Policy converted"


class Plan(UUIDModel, TimeStampedModel):
    """Global provider-neutral commercial plan catalog entry."""

    code = models.CharField(max_length=40, unique=True, validators=[CODE_VALIDATOR])
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    entitlement_revision = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["code"]
        permissions = [
            ("view_plan_catalog", "Can view the commercial plan catalog"),
            ("manage_plan_catalog", "Can manage the commercial plan catalog"),
        ]

    def clean(self) -> None:
        super().clean()
        self.code = normalize_code(self.code)
        CODE_VALIDATOR(self.code)
        self.name = self.name.strip()
        self.description = self.description.strip()
        if not self.name:
            raise ValidationError({"name": "Plan name is required."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.code = normalize_code(self.code)
        self.name = self.name.strip()
        self.description = self.description.strip()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"


class CompanyModulePolicy(UUIDModel, TimeStampedModel):
    """Explicit rollout mode; commercial module grants remain Subscription-owned."""

    company = models.OneToOneField(
        "organization.Company",
        on_delete=models.PROTECT,
        related_name="module_policy",
    )
    mode = models.CharField(
        max_length=20,
        choices=CompanyModulePolicyMode.choices,
        default=CompanyModulePolicyMode.LEGACY_FULL,
    )

    class Meta:
        ordering = ["company__code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(mode__in=CompanyModulePolicyMode.values),
                name="subs_company_module_policy_mode_valid",
            )
        ]

    def __str__(self) -> str:
        return f"{self.company_id} / {self.mode}"


class PlanModuleDefault(UUIDModel, TimeStampedModel):
    """One enabled code-owned product module in a global commercial Plan."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="module_defaults")
    module_id = models.CharField(max_length=64, validators=[validate_registered_module_id])

    class Meta:
        ordering = ["module_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "module_id"],
                name="subs_plan_module_default_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.plan_id} / {self.module_id}"


class PlanEntitlementEventQuerySet(models.QuerySet["PlanEntitlementEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Plan entitlement events are immutable.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Plan entitlement events cannot be deleted.")

    def bulk_update(
        self,
        objs: Iterable[PlanEntitlementEvent],
        fields: Iterable[str],
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Plan entitlement events are immutable.")


class PlanEntitlementEvent(UUIDModel):
    """Append-only evidence for a normalized Plan module-default change."""

    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="entitlement_events")
    event_type = models.CharField(max_length=30, choices=PlanEntitlementEventType.choices)
    module_id = models.CharField(max_length=64, validators=[validate_registered_module_id])
    previous_state = models.CharField(max_length=20)
    resulting_state = models.CharField(max_length=20)
    plan_entitlement_revision = models.PositiveBigIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="plan_entitlement_events",
    )
    reason = models.CharField(max_length=255, blank=True)
    batch_id = models.UUIDField(default=uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = PlanEntitlementEventQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [
            models.Index(fields=["plan", "occurred_at"], name="subs_plan_ent_event_time_idx")
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(event_type__in=PlanEntitlementEventType.values),
                name="subs_plan_ent_event_type_valid",
            )
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Plan entitlement events are immutable.")
        self.reason = self.reason.strip()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Plan entitlement events cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.plan_id} / {self.module_id} / {self.event_type}"


class SubscriptionQuerySet(models.QuerySet["Subscription"]):
    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Subscriptions cannot be deleted; use a lifecycle transition.")


class Subscription(UUIDModel, TimeStampedModel):
    """One provider-neutral commercial lifecycle per tenant Company."""

    company = models.OneToOneField(
        "organization.Company",
        on_delete=models.PROTECT,
        related_name="commercial_subscription",
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=SubscriptionStatus.choices)
    starts_at = models.DateTimeField()
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)
    suspended_at = models.DateTimeField(null=True, blank=True)
    terminated_at = models.DateTimeField(null=True, blank=True)
    snapshot_initialized_at = models.DateTimeField(null=True, blank=True)
    snapshot_plan_entitlement_revision = models.PositiveBigIntegerField(null=True, blank=True)
    entitlement_revision = models.PositiveBigIntegerField(default=0)

    objects = SubscriptionQuerySet.as_manager()

    class Meta:
        ordering = ["company__code"]
        permissions = [
            ("view_commercial_subscriptions", "Can view commercial subscriptions"),
            ("manage_commercial_subscriptions", "Can manage commercial subscriptions"),
        ]
        indexes = [
            models.Index(fields=["status", "created_at"], name="subs_status_time_idx"),
            models.Index(fields=["plan", "status"], name="subs_plan_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=SubscriptionStatus.values),
                name="subs_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(trial_ends_at__isnull=True) | Q(trial_ends_at__gte=F("starts_at")),
                name="subs_trial_dates_valid",
            ),
            models.CheckConstraint(
                condition=~Q(status=SubscriptionStatus.TRIAL) | Q(trial_ends_at__isnull=False),
                name="subs_trial_end_required",
            ),
            models.CheckConstraint(
                condition=Q(grace_ends_at__isnull=True) | Q(grace_ends_at__gte=F("starts_at")),
                name="subs_grace_dates_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=SubscriptionStatus.GRACE, grace_ends_at__isnull=False)
                    | (~Q(status=SubscriptionStatus.GRACE) & Q(grace_ends_at__isnull=True))
                ),
                name="subs_grace_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=SubscriptionStatus.SUSPENDED, suspended_at__isnull=False)
                    | (~Q(status=SubscriptionStatus.SUSPENDED) & Q(suspended_at__isnull=True))
                ),
                name="subs_suspended_state_valid",
            ),
            models.CheckConstraint(
                condition=(
                    Q(status=SubscriptionStatus.TERMINATED, terminated_at__isnull=False)
                    | (~Q(status=SubscriptionStatus.TERMINATED) & Q(terminated_at__isnull=True))
                ),
                name="subs_terminated_state_valid",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.trial_ends_at is not None and self.trial_ends_at < self.starts_at:
            errors["trial_ends_at"] = "Trial end cannot precede the subscription start."
        if self.status == SubscriptionStatus.TRIAL and self.trial_ends_at is None:
            errors["trial_ends_at"] = "Trial subscriptions require an explicit trial end."
        if self.status == SubscriptionStatus.GRACE:
            if self.grace_ends_at is None:
                errors["grace_ends_at"] = "Grace status requires an explicit grace end."
            elif self.grace_ends_at <= self.starts_at:
                errors["grace_ends_at"] = "Grace end must follow the subscription start."
        elif self.grace_ends_at is not None:
            errors["grace_ends_at"] = "Grace end is only valid while status is GRACE."
        if (self.status == SubscriptionStatus.SUSPENDED) != (self.suspended_at is not None):
            errors["suspended_at"] = "Suspension timestamp must match SUSPENDED status."
        if (self.status == SubscriptionStatus.TERMINATED) != (self.terminated_at is not None):
            errors["terminated_at"] = "Termination timestamp must match TERMINATED status."
        if errors:
            raise ValidationError(errors)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Subscriptions cannot be deleted; use a lifecycle transition.")

    def __str__(self) -> str:
        return f"{self.company.code} / {self.plan.code} / {self.status}"


class SubscriptionModuleSnapshot(UUIDModel, TimeStampedModel):
    """One enabled module captured from a specific Plan entitlement revision."""

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="module_snapshot",
    )
    module_id = models.CharField(max_length=64, validators=[validate_registered_module_id])
    source_plan_entitlement_revision = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["module_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "module_id"],
                name="subs_subscription_module_snapshot_unique",
            )
        ]

    @property
    def company(self) -> Any:
        return self.subscription.company

    @property
    def company_id(self) -> Any:
        return self.subscription.company_id

    def __str__(self) -> str:
        return f"{self.subscription_id} / {self.module_id}"


class SubscriptionModuleOverride(UUIDModel, TimeStampedModel):
    """Explicit Subscription-owned deviation from its captured Plan snapshot."""

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.CASCADE,
        related_name="module_overrides",
    )
    module_id = models.CharField(max_length=64, validators=[validate_registered_module_id])
    state = models.CharField(max_length=10, choices=ModuleOverrideState.choices)

    class Meta:
        ordering = ["module_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "module_id"],
                name="subs_subscription_module_override_unique",
            ),
            models.CheckConstraint(
                condition=Q(state__in=ModuleOverrideState.values),
                name="subs_subscription_module_override_state_valid",
            ),
        ]

    @property
    def company(self) -> Any:
        return self.subscription.company

    @property
    def company_id(self) -> Any:
        return self.subscription.company_id

    def __str__(self) -> str:
        return f"{self.subscription_id} / {self.module_id} / {self.state}"


class SubscriptionEntitlementEventQuerySet(models.QuerySet["SubscriptionEntitlementEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Subscription entitlement events are immutable.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Subscription entitlement events cannot be deleted.")

    def bulk_update(
        self,
        objs: Iterable[SubscriptionEntitlementEvent],
        fields: Iterable[str],
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Subscription entitlement events are immutable.")


class SubscriptionEntitlementEvent(UUIDModel):
    """Append-only commercial entitlement evidence derived through Subscription."""

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="entitlement_events",
    )
    event_type = models.CharField(
        max_length=40,
        choices=SubscriptionEntitlementEventType.choices,
    )
    module_id = models.CharField(
        max_length=64,
        blank=True,
        validators=[validate_registered_module_id],
    )
    previous_state = models.CharField(max_length=40, blank=True)
    resulting_state = models.CharField(max_length=40)
    plan_entitlement_revision = models.PositiveBigIntegerField(null=True, blank=True)
    subscription_entitlement_revision = models.PositiveBigIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="subscription_entitlement_events",
    )
    reason = models.CharField(max_length=255, blank=True)
    batch_id = models.UUIDField(default=uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = SubscriptionEntitlementEventQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [
            models.Index(
                fields=["subscription", "occurred_at"],
                name="subs_sub_ent_event_time_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(event_type__in=SubscriptionEntitlementEventType.values),
                name="subs_subscription_ent_event_type_valid",
            )
        ]

    @property
    def company(self) -> Any:
        return self.subscription.company

    @property
    def company_id(self) -> Any:
        return self.subscription.company_id

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Subscription entitlement events are immutable.")
        self.reason = self.reason.strip()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Subscription entitlement events cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.subscription_id} / {self.event_type} / {self.module_id or '-'}"


class SubscriptionEventQuerySet(models.QuerySet["SubscriptionEvent"]):
    def update(self, **kwargs: Any) -> int:
        raise ValidationError("Subscription events are immutable.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise ValidationError("Subscription events cannot be deleted.")

    def bulk_update(
        self,
        objs: Iterable[SubscriptionEvent],
        fields: Iterable[str],
        batch_size: int | None = None,
    ) -> int:
        raise ValidationError("Subscription events are immutable.")


class SubscriptionEvent(UUIDModel):
    """Append-only lifecycle evidence whose Company ownership derives from Subscription."""

    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.PROTECT,
        related_name="events",
    )
    event_type = models.CharField(max_length=30, choices=SubscriptionEventType.choices)
    previous_status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        blank=True,
    )
    resulting_status = models.CharField(max_length=20, choices=SubscriptionStatus.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="commercial_subscription_events",
    )
    reason = models.CharField(max_length=255, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    objects = SubscriptionEventQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [
            models.Index(fields=["subscription", "occurred_at"], name="subs_event_time_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(resulting_status__in=SubscriptionStatus.values),
                name="subs_event_result_valid",
            ),
            models.CheckConstraint(
                condition=Q(previous_status="") | Q(previous_status__in=SubscriptionStatus.values),
                name="subs_event_previous_valid",
            ),
        ]

    @property
    def company(self) -> Any:
        return self.subscription.company

    @property
    def company_id(self) -> Any:
        return self.subscription.company_id

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise ValidationError("Subscription events are immutable.")
        self.reason = self.reason.strip()
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError("Subscription events cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.subscription_id} / {self.event_type} / {self.resulting_status}"
