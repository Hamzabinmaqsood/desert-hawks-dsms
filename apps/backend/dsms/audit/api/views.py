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
        company_ids = access.get_accessible_company_ids(user, permission="audit.view_auditevent")
        branch_ids = access.get_accessible_branch_ids(user, permission="audit.view_auditevent")
        scope = models.Q(company_id__in=company_ids) | models.Q(branch_id__in=branch_ids)
        if user.is_superuser:
            scope |= models.Q(company__isnull=True, branch__isnull=True)
        return AuditEvent.objects.filter(scope).select_related(
            "actor_user", "actor_employee", "company", "region", "branch"
        )
