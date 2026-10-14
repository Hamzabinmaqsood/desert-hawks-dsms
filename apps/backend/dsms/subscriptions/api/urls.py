from django.urls import path

from .views import (
    PlanCollectionView,
    PlanDetailView,
    SubscriptionCollectionView,
    SubscriptionDetailView,
    SubscriptionHistoryView,
    SubscriptionTransitionView,
)

urlpatterns = [
    path("plans/", PlanCollectionView.as_view(), name="platform-plan-list"),
    path("plans/<uuid:plan_id>/", PlanDetailView.as_view(), name="platform-plan-detail"),
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
]
