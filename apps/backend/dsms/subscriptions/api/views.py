from typing import Any, NoReturn, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.identity.models import User
from dsms.identity.platform_access import (
    MANAGE_COMMERCIAL_SUBSCRIPTIONS,
    MANAGE_PLAN_CATALOG,
    VIEW_COMMERCIAL_SUBSCRIPTIONS,
    VIEW_PLAN_CATALOG,
    has_platform_capability,
)
from dsms.organization.models import Company

from .. import entitlements, services
from ..exceptions import (
    SubscriptionAuthorizationError,
    SubscriptionConflictError,
    SubscriptionValidationError,
)
from ..models import Plan, Subscription
from ..modules import TENANT_MODULE_REGISTRY
from .serializers import (
    EntitlementActionSerializer,
    ModuleCatalogSerializer,
    PlanCreateSerializer,
    PlanEntitlementResponseSerializer,
    PlanEntitlementUpdateSerializer,
    PlanSerializer,
    PlanUpdateSerializer,
    SubscriptionActivationSerializer,
    SubscriptionCreateSerializer,
    SubscriptionEntitlementResponseSerializer,
    SubscriptionEventSerializer,
    SubscriptionOverrideBatchSerializer,
    SubscriptionSerializer,
    SubscriptionTransitionSerializer,
)


class CommercialSubscriptionConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with current commercial subscription state."
    default_code = "commercial_subscription_conflict"


def _require_platform_user(request: Request, capability: str) -> User:
    user = cast(User, request.user)
    if not has_platform_capability(user, capability):
        raise PermissionDenied("The required platform administration permission is missing.")
    return user


def _service_error(exc: Exception) -> NoReturn:
    if isinstance(exc, SubscriptionAuthorizationError):
        raise PermissionDenied(str(exc)) from exc
    if isinstance(exc, SubscriptionConflictError):
        raise CommercialSubscriptionConflict(str(exc)) from exc
    if isinstance(exc, SubscriptionValidationError):
        raise ValidationError(exc.errors) from exc
    raise exc


def _module_catalog_data() -> list[dict[str, Any]]:
    return [
        {
            "id": module.module_id,
            "display_name": module.display_name,
            "classification": module.classification,
            "hard_dependencies": list(module.hard_dependencies),
            "legacy_default": module.legacy_default,
        }
        for module in TENANT_MODULE_REGISTRY
    ]


def _plan_entitlement_data(plan: Plan) -> dict[str, Any]:
    module_ids = TENANT_MODULE_REGISTRY.ordered_ids(
        plan.module_defaults.values_list("module_id", flat=True)
    )
    return {
        "plan_id": plan.pk,
        "plan_code": plan.code,
        "plan_name": plan.name,
        "entitlement_revision": plan.entitlement_revision,
        "enabled_module_ids": list(module_ids),
        "snapshot_notice": (
            "Plan updated; existing subscriptions retain their current snapshot "
            "until explicitly updated."
        ),
    }


def _subscription_entitlement_data(subscription: Subscription) -> dict[str, Any]:
    effective = entitlements.resolve_effective_modules(subscription.company)
    plan_module_ids = TENANT_MODULE_REGISTRY.ordered_ids(
        subscription.plan.module_defaults.values_list("module_id", flat=True)
    )
    snapshot_module_ids = TENANT_MODULE_REGISTRY.ordered_ids(
        subscription.module_snapshot.values_list("module_id", flat=True)
    )
    override_states = dict(subscription.module_overrides.values_list("module_id", "state"))
    return {
        "subscription_id": subscription.pk,
        "subscription_status": subscription.status,
        "company": subscription.company,
        "plan": subscription.plan,
        "policy_mode": effective.policy_mode,
        "plan_entitlement_revision": subscription.plan.entitlement_revision,
        "snapshot_plan_entitlement_revision": subscription.snapshot_plan_entitlement_revision,
        "entitlement_revision": effective.entitlement_revision,
        "snapshot_initialized": subscription.snapshot_initialized_at is not None,
        "plan_module_ids": list(plan_module_ids),
        "snapshot_module_ids": list(snapshot_module_ids),
        "overrides": [
            {"module_id": module_id, "state": override_states[module_id]}
            for module_id in TENANT_MODULE_REGISTRY.ordered_ids(override_states)
        ],
        "effective_module_ids": list(effective.module_ids),
    }


def _entitlement_subscription(subscription_id: Any) -> Subscription:
    return get_object_or_404(
        Subscription.objects.select_related("company", "plan").prefetch_related(
            "plan__module_defaults", "module_snapshot", "module_overrides"
        ),
        pk=subscription_id,
    )


class ModuleCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Product Modules"],
        responses=ModuleCatalogSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        _require_platform_user(request, VIEW_PLAN_CATALOG)
        return Response(ModuleCatalogSerializer(_module_catalog_data(), many=True).data)


class PlanCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Platform - Commercial Plans"], responses=PlanSerializer(many=True))
    def get(self, request: Request) -> Response:
        _require_platform_user(request, VIEW_PLAN_CATALOG)
        return Response(PlanSerializer(Plan.objects.order_by("code"), many=True).data)

    @extend_schema(
        tags=["Platform - Commercial Plans"],
        request=PlanCreateSerializer,
        responses={201: PlanSerializer},
    )
    def post(self, request: Request) -> Response:
        actor = _require_platform_user(request, MANAGE_PLAN_CATALOG)
        serializer = PlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = services.create_plan(actor=actor, **serializer.validated_data)
        except Exception as exc:
            _service_error(exc)
        return Response(PlanSerializer(plan).data, status=status.HTTP_201_CREATED)


class PlanDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Platform - Commercial Plans"], responses=PlanSerializer)
    def get(self, request: Request, plan_id: Any) -> Response:
        _require_platform_user(request, VIEW_PLAN_CATALOG)
        return Response(PlanSerializer(get_object_or_404(Plan, pk=plan_id)).data)

    @extend_schema(
        tags=["Platform - Commercial Plans"],
        request=PlanUpdateSerializer,
        responses=PlanSerializer,
    )
    def patch(self, request: Request, plan_id: Any) -> Response:
        actor = _require_platform_user(request, MANAGE_PLAN_CATALOG)
        serializer = PlanUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = services.update_plan(
                actor=actor,
                plan=get_object_or_404(Plan, pk=plan_id),
                **serializer.validated_data,
            )
        except Exception as exc:
            _service_error(exc)
        return Response(PlanSerializer(plan).data)


class PlanEntitlementView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Product Modules"],
        responses=PlanEntitlementResponseSerializer,
    )
    def get(self, request: Request, plan_id: Any) -> Response:
        _require_platform_user(request, VIEW_PLAN_CATALOG)
        plan = get_object_or_404(Plan.objects.prefetch_related("module_defaults"), pk=plan_id)
        return Response(PlanEntitlementResponseSerializer(_plan_entitlement_data(plan)).data)

    @extend_schema(
        tags=["Platform - Product Modules"],
        request=PlanEntitlementUpdateSerializer,
        responses=PlanEntitlementResponseSerializer,
    )
    def put(self, request: Request, plan_id: Any) -> Response:
        actor = _require_platform_user(request, MANAGE_PLAN_CATALOG)
        serializer = PlanEntitlementUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            plan = entitlements.set_plan_module_defaults(
                actor=actor,
                plan=get_object_or_404(Plan, pk=plan_id),
                module_ids=serializer.validated_data["enabled_module_ids"],
                reason=serializer.validated_data["reason"],
            )
        except Exception as exc:
            _service_error(exc)
        plan = Plan.objects.prefetch_related("module_defaults").get(pk=plan.pk)
        return Response(PlanEntitlementResponseSerializer(_plan_entitlement_data(plan)).data)


class SubscriptionCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Commercial Subscriptions"],
        responses=SubscriptionSerializer(many=True),
    )
    def get(self, request: Request) -> Response:
        _require_platform_user(request, VIEW_COMMERCIAL_SUBSCRIPTIONS)
        queryset = Subscription.objects.select_related("company", "plan").order_by("company__code")
        return Response(SubscriptionSerializer(queryset, many=True).data)

    @extend_schema(
        tags=["Platform - Commercial Subscriptions"],
        request=SubscriptionCreateSerializer,
        responses={201: SubscriptionSerializer},
    )
    def post(self, request: Request) -> Response:
        actor = _require_platform_user(request, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
        serializer = SubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        company = get_object_or_404(Company, pk=data.pop("company_id"))
        plan = get_object_or_404(Plan, pk=data.pop("plan_id"))
        try:
            subscription = services.create_subscription(
                actor=actor,
                company=company,
                plan=plan,
                **data,
            )
        except Exception as exc:
            _service_error(exc)
        return Response(
            SubscriptionSerializer(subscription).data,
            status=status.HTTP_201_CREATED,
        )


class SubscriptionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Platform - Commercial Subscriptions"], responses=SubscriptionSerializer)
    def get(self, request: Request, subscription_id: Any) -> Response:
        _require_platform_user(request, VIEW_COMMERCIAL_SUBSCRIPTIONS)
        subscription = get_object_or_404(
            Subscription.objects.select_related("company", "plan"),
            pk=subscription_id,
        )
        return Response(SubscriptionSerializer(subscription).data)


class SubscriptionEntitlementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Product Modules"],
        responses=SubscriptionEntitlementResponseSerializer,
    )
    def get(self, request: Request, subscription_id: Any) -> Response:
        _require_platform_user(request, VIEW_COMMERCIAL_SUBSCRIPTIONS)
        subscription = _entitlement_subscription(subscription_id)
        return Response(
            SubscriptionEntitlementResponseSerializer(
                _subscription_entitlement_data(subscription)
            ).data
        )


class SubscriptionOverrideView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Product Modules"],
        request=SubscriptionOverrideBatchSerializer,
        responses=SubscriptionEntitlementResponseSerializer,
    )
    def put(self, request: Request, subscription_id: Any) -> Response:
        actor = _require_platform_user(request, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
        serializer = SubscriptionOverrideBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        overrides = data.pop("overrides")
        data.pop("enabled_module_ids")
        data.pop("disabled_module_ids")
        try:
            entitlements.replace_subscription_module_overrides(
                actor=actor,
                subscription=get_object_or_404(Subscription, pk=subscription_id),
                overrides=overrides,
                **data,
            )
        except Exception as exc:
            _service_error(exc)
        subscription = _entitlement_subscription(subscription_id)
        return Response(
            SubscriptionEntitlementResponseSerializer(
                _subscription_entitlement_data(subscription)
            ).data
        )


class SubscriptionApplyPlanRevisionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Product Modules"],
        request=EntitlementActionSerializer,
        responses=SubscriptionEntitlementResponseSerializer,
    )
    def post(self, request: Request, subscription_id: Any) -> Response:
        actor = _require_platform_user(request, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
        serializer = EntitlementActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entitlements.apply_plan_entitlement_revision(
                actor=actor,
                subscription=get_object_or_404(Subscription, pk=subscription_id),
                **serializer.validated_data,
            )
        except Exception as exc:
            _service_error(exc)
        subscription = _entitlement_subscription(subscription_id)
        return Response(
            SubscriptionEntitlementResponseSerializer(
                _subscription_entitlement_data(subscription)
            ).data
        )


class SubscriptionActivateEntitlementsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Product Modules"],
        request=SubscriptionActivationSerializer,
        responses=SubscriptionEntitlementResponseSerializer,
    )
    def post(self, request: Request, subscription_id: Any) -> Response:
        actor = _require_platform_user(request, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
        serializer = SubscriptionActivationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        overrides = data.pop("overrides")
        data.pop("enabled_module_ids")
        data.pop("disabled_module_ids")
        subscription = get_object_or_404(
            Subscription.objects.select_related("company"), pk=subscription_id
        )
        try:
            entitlements.convert_company_to_subscription_entitlements(
                actor=actor,
                company=subscription.company,
                overrides=overrides,
                **data,
            )
        except Exception as exc:
            _service_error(exc)
        subscription = _entitlement_subscription(subscription_id)
        return Response(
            SubscriptionEntitlementResponseSerializer(
                _subscription_entitlement_data(subscription)
            ).data
        )


class SubscriptionTransitionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Commercial Subscriptions"],
        request=SubscriptionTransitionSerializer,
        responses=SubscriptionSerializer,
    )
    def post(self, request: Request, subscription_id: Any) -> Response:
        actor = _require_platform_user(request, MANAGE_COMMERCIAL_SUBSCRIPTIONS)
        serializer = SubscriptionTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            subscription = services.transition_subscription(
                actor=actor,
                subscription=get_object_or_404(Subscription, pk=subscription_id),
                **serializer.validated_data,
            )
        except Exception as exc:
            _service_error(exc)
        return Response(SubscriptionSerializer(subscription).data)


class SubscriptionHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Commercial Subscriptions"],
        responses=SubscriptionEventSerializer(many=True),
    )
    def get(self, request: Request, subscription_id: Any) -> Response:
        _require_platform_user(request, VIEW_COMMERCIAL_SUBSCRIPTIONS)
        subscription = get_object_or_404(Subscription, pk=subscription_id)
        events = subscription.events.select_related("actor").order_by("occurred_at", "id")
        return Response(SubscriptionEventSerializer(events, many=True).data)
