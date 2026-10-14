from __future__ import annotations

from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from dsms.common.validators import normalize_code
from dsms.identity.models import User
from dsms.identity.platform_access import (
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_PLAN_CATALOG,
    has_platform_capability,
)
from dsms.organization.models import Company

from .exceptions import (
    SubscriptionAuthorizationError,
    SubscriptionConflictError,
    SubscriptionTransitionError,
    SubscriptionValidationError,
)
from .models import Plan, Subscription, SubscriptionEvent, SubscriptionEventType, SubscriptionStatus

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    SubscriptionStatus.TRIAL: frozenset(
        {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.GRACE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.TERMINATED,
        }
    ),
    SubscriptionStatus.ACTIVE: frozenset(
        {
            SubscriptionStatus.GRACE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.TERMINATED,
        }
    ),
    SubscriptionStatus.GRACE: frozenset(
        {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.TERMINATED,
        }
    ),
    SubscriptionStatus.SUSPENDED: frozenset(
        {SubscriptionStatus.ACTIVE, SubscriptionStatus.TERMINATED}
    ),
    SubscriptionStatus.TERMINATED: frozenset(),
}


def _require(actor: User, capability: str) -> None:
    if not has_platform_capability(actor, capability):
        raise SubscriptionAuthorizationError(
            "The required platform commercial-subscription permission is missing."
        )


def _validation_errors(exc: ValidationError) -> dict[str, Any]:
    if hasattr(exc, "message_dict"):
        return dict(exc.message_dict)
    return {"non_field_errors": list(exc.messages)}


def _normalized_reason(reason: str) -> str:
    normalized = reason.strip()
    if len(normalized) > 255:
        raise SubscriptionValidationError({"reason": ["Reason must not exceed 255 characters."]})
    return normalized


def create_plan(*, actor: User, code: str, name: str, description: str = "") -> Plan:
    _require(actor, MANAGE_PLAN_CATALOG)
    plan = Plan(code=normalize_code(code), name=name, description=description)
    try:
        plan.full_clean(validate_unique=False)
        with transaction.atomic():
            plan.save()
    except ValidationError as exc:
        raise SubscriptionValidationError(_validation_errors(exc)) from exc
    except IntegrityError as exc:
        raise SubscriptionConflictError("A Plan with this normalized code already exists.") from exc
    return plan


def update_plan(
    *,
    actor: User,
    plan: Plan,
    name: str | None = None,
    description: str | None = None,
    is_active: bool | None = None,
) -> Plan:
    _require(actor, MANAGE_PLAN_CATALOG)
    try:
        with transaction.atomic():
            locked = Plan.objects.select_for_update().get(pk=plan.pk)
            update_fields = ["updated_at"]
            if name is not None:
                locked.name = name
                update_fields.append("name")
            if description is not None:
                locked.description = description
                update_fields.append("description")
            if is_active is not None:
                locked.is_active = is_active
                update_fields.append("is_active")
            locked.full_clean()
            locked.save(update_fields=update_fields)
            return locked
    except ValidationError as exc:
        raise SubscriptionValidationError(_validation_errors(exc)) from exc


def create_subscription(
    *,
    actor: User,
    company: Company,
    plan: Plan,
    status: str = SubscriptionStatus.ACTIVE,
    starts_at: datetime | None = None,
    trial_ends_at: datetime | None = None,
    reason: str = "",
) -> Subscription:
    _require(actor, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    if status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL}:
        raise SubscriptionValidationError(
            {"status": ["A new Subscription must start as ACTIVE or TRIAL."]}
        )
    normalized_reason = _normalized_reason(reason)
    try:
        with transaction.atomic():
            locked_company = Company.objects.select_for_update().get(pk=company.pk)
            locked_plan = Plan.objects.get(pk=plan.pk)
            if not locked_plan.is_active:
                raise SubscriptionValidationError(
                    {"plan_id": ["Inactive Plans cannot be assigned to new Subscriptions."]}
                )
            if Subscription.objects.filter(company=locked_company).exists():
                raise SubscriptionConflictError("This Company already has a Subscription.")
            subscription = Subscription(
                company=locked_company,
                plan=locked_plan,
                status=status,
                starts_at=starts_at or timezone.now(),
                trial_ends_at=trial_ends_at,
            )
            subscription.full_clean()
            subscription.save()
            SubscriptionEvent.objects.create(
                subscription=subscription,
                event_type=SubscriptionEventType.CREATED,
                previous_status="",
                resulting_status=subscription.status,
                actor=actor,
                reason=normalized_reason,
            )
            return subscription
    except ValidationError as exc:
        raise SubscriptionValidationError(_validation_errors(exc)) from exc
    except IntegrityError as exc:
        raise SubscriptionConflictError("This Company already has a Subscription.") from exc


def transition_subscription(
    *,
    actor: User,
    subscription: Subscription,
    target_status: str,
    grace_ends_at: datetime | None = None,
    reason: str = "",
) -> Subscription:
    _require(actor, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
    if target_status not in SubscriptionStatus.values:
        raise SubscriptionValidationError({"target_status": ["Unknown subscription status."]})
    normalized_reason = _normalized_reason(reason)
    try:
        with transaction.atomic():
            locked = Subscription.objects.select_for_update(of=("self",)).get(pk=subscription.pk)
            previous_status = locked.status
            if target_status not in ALLOWED_TRANSITIONS[previous_status]:
                raise SubscriptionTransitionError(
                    f"Transition from {previous_status} to {target_status} is not allowed."
                )
            changed_at = timezone.now()
            if target_status == SubscriptionStatus.GRACE:
                if grace_ends_at is None or grace_ends_at <= changed_at:
                    raise SubscriptionValidationError(
                        {"grace_ends_at": ["Entering GRACE requires a future explicit end."]}
                    )
                locked.grace_ends_at = grace_ends_at
            else:
                if grace_ends_at is not None:
                    raise SubscriptionValidationError(
                        {"grace_ends_at": ["Grace end is only accepted when entering GRACE."]}
                    )
                locked.grace_ends_at = None
            locked.suspended_at = (
                changed_at if target_status == SubscriptionStatus.SUSPENDED else None
            )
            locked.terminated_at = (
                changed_at if target_status == SubscriptionStatus.TERMINATED else None
            )
            locked.status = target_status
            locked.full_clean()
            locked.save(
                update_fields=[
                    "status",
                    "grace_ends_at",
                    "suspended_at",
                    "terminated_at",
                    "updated_at",
                ]
            )
            SubscriptionEvent.objects.create(
                subscription=locked,
                event_type=SubscriptionEventType.STATUS_CHANGED,
                previous_status=previous_status,
                resulting_status=target_status,
                actor=actor,
                reason=normalized_reason,
            )
            return locked
    except ValidationError as exc:
        raise SubscriptionValidationError(_validation_errors(exc)) from exc
