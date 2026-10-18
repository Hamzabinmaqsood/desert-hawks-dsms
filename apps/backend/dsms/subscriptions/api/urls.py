from django.urls import path

from .views import (
    ModuleCatalogView,
    PlanCollectionView,
    PlanDetailView,
    PlanEntitlementView,
    SubscriptionActivateEntitlementsView,
    SubscriptionApplyPlanRevisionView,
    SubscriptionCollectionView,
    SubscriptionDetailView,
    SubscriptionEntitlementDetailView,
    SubscriptionHistoryView,
    SubscriptionOverrideView,
    SubscriptionTransitionView,
)

urlpatterns = [
    path("modules/", ModuleCatalogView.as_view(), name="platform-module-catalog"),
    path("plans/", PlanCollectionView.as_view(), name="platform-plan-list"),
    path("plans/<uuid:plan_id>/", PlanDetailView.as_view(), name="platform-plan-detail"),
    path(
        "plans/<uuid:plan_id>/entitlements/",
        PlanEntitlementView.as_view(),
        name="platform-plan-entitlements",
    ),
    path(
        "subscriptions/",
        SubscriptionCollectionView.as_view(),
        name="platform-subscription-list",
    ),
    path(
        "subscriptions/<uuid:subscription_id>/",
        SubscriptionDetailView.as_view(),
        name="platform-subscription-detail",
    ),
    path(
        "subscriptions/<uuid:subscription_id>/transition/",
        SubscriptionTransitionView.as_view(),
        name="platform-subscription-transition",
    ),
    path(
        "subscriptions/<uuid:subscription_id>/history/",
        SubscriptionHistoryView.as_view(),
        name="platform-subscription-history",
    ),
    path(
        "subscriptions/<uuid:subscription_id>/entitlements/",
        SubscriptionEntitlementDetailView.as_view(),
        name="platform-subscription-entitlements",
    ),
    path(
        "subscriptions/<uuid:subscription_id>/overrides/",
        SubscriptionOverrideView.as_view(),
        name="platform-subscription-overrides",
    ),
    path(
        "subscriptions/<uuid:subscription_id>/apply-plan-revision/",
        SubscriptionApplyPlanRevisionView.as_view(),
        name="platform-subscription-apply-plan-revision",
    ),
    path(
        "subscriptions/<uuid:subscription_id>/activate-entitlements/",
        SubscriptionActivateEntitlementsView.as_view(),
        name="platform-subscription-activate-entitlements",
    ),
]
