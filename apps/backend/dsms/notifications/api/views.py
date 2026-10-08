# mypy: disable-error-code="no-untyped-def,no-untyped-call,type-arg,misc"
from typing import cast

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.identity.models import User
from dsms.notifications.models import NotificationRecipient, UserNotificationPreference
from dsms.notifications.services import acknowledge_notification, mark_notification_read
from dsms.notifications.tenant_queries import consistent_recipients_for_user

from .serializers import AcknowledgeSerializer, InAppNotificationSerializer, PreferenceSerializer


class NotificationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]
    serializer_class = InAppNotificationSerializer
    filterset_fields = ["status", "notification__priority"]
    ordering_fields = ["created_at", "read_at", "acknowledged_at"]
    queryset = NotificationRecipient.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return (
            consistent_recipients_for_user(
                NotificationRecipient.objects.all(), user=cast(User, self.request.user)
            )
            .select_related("notification")
            .order_by("-created_at")
        )

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        return Response({"count": self.get_queryset().filter(read_at__isnull=True).count()})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        return Response(
            self.get_serializer(
                mark_notification_read(recipient=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def acknowledge(self, request, pk=None):
        payload = AcknowledgeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        obj = acknowledge_notification(
            recipient=self.get_object(),
            actor=request.user,
            comment=payload.validated_data.get("comment", ""),
        )
        return Response(self.get_serializer(obj).data)


class PreferenceViewSet(
    mixins.ListModelMixin, mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated]
    serializer_class = PreferenceSerializer
    queryset = UserNotificationPreference.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return self.queryset
        return UserNotificationPreference.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        serializer.save(user=self.request.user)
