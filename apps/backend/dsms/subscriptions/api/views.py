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

from .. import services
from ..exceptions import (
    SubscriptionAuthorizationError,
    SubscriptionConflictError,
    SubscriptionValidationError,
)
from ..models import Plan, Subscription
from .serializers import (
    PlanCreateSerializer,
    PlanSerializer,
    PlanUpdateSerializer,
    SubscriptionCreateSerializer,
    SubscriptionEventSerializer,
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
