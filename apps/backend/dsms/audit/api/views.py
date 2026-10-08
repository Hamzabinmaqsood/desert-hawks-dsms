from typing import cast

from django.db import models
from rest_framework import permissions, viewsets

from dsms.identity import access
from dsms.identity.models import User

from ..models import AuditEvent
from .filters import AuditEventFilter
from .serializers import AuditEventSerializer


class CanViewAuditEvents(permissions.BasePermission):
    def has_permission(self, request: object, view: object) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        return bool(
            user.is_superuser
            or access.get_accessible_company_ids(user, permission="audit.view_auditevent")
            or access.get_accessible_branch_ids(user, permission="audit.view_auditevent")
        )


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet[AuditEvent]):
    serializer_class = AuditEventSerializer
    permission_classes = [permissions.IsAuthenticated, CanViewAuditEvents]
    filterset_class = AuditEventFilter
    search_fields = ["action", "summary", "object_reference", "request_id"]
    ordering_fields = ["occurred_at", "created_at", "severity"]

    def get_queryset(self) -> models.QuerySet[AuditEvent]:
        user = cast(User, self.request.user)
        queryset = AuditEvent.objects.select_related(
            "actor_user", "actor_employee", "company", "region", "branch"
        )
        if user.is_superuser:
            return queryset
        company_ids = access.get_accessible_company_ids(user, permission="audit.view_auditevent")
        branch_ids = access.get_accessible_branch_ids(user, permission="audit.view_auditevent")
        scope = models.Q(company_id__in=company_ids) | models.Q(branch_id__in=branch_ids)
        consistent = (
            models.Q(company__is_active=True)
            & (models.Q(region__isnull=True) | models.Q(region__company_id=models.F("company_id")))
            & (models.Q(branch__isnull=True) | models.Q(branch__company_id=models.F("company_id")))
            & (
                models.Q(branch__isnull=True)
                | models.Q(region__isnull=True)
                | models.Q(branch__region_id=models.F("region_id"))
            )
            & (
                models.Q(actor_employee__isnull=True)
                | models.Q(actor_employee__company_id=models.F("company_id"))
            )
        )
        return queryset.filter(scope, consistent).distinct()
