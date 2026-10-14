from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

from dsms.common.models import TimeStampedModel, UUIDModel
from dsms.common.validators import CODE_VALIDATOR, normalize_code


class SubscriptionStatus(models.TextChoices):
    TRIAL = "TRIAL", "Trial"
    ACTIVE = "ACTIVE", "Active"
    GRACE = "GRACE", "Grace"
    SUSPENDED = "SUSPENDED", "Suspended"
    TERMINATED = "TERMINATED", "Terminated"


class SubscriptionEventType(models.TextChoices):
    CREATED = "CREATED", "Created"
    STATUS_CHANGED = "STATUS_CHANGED", "Status changed"


class Plan(UUIDModel, TimeStampedModel):
    """Global provider-neutral commercial plan catalog entry."""

    code = models.CharField(max_length=40, unique=True, validators=[CODE_VALIDATOR])
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

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
