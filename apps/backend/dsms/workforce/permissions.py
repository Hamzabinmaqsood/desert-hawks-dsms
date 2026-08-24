"""RBAC permission gate for the workforce module.

Mirrors :class:`dsms.identity.permissions.HasScopedOrganizationPermission`
but additionally supports per-action permission overrides (like
:class:`~dsms.identity.permissions.HasRBACPermission`), since ``Employee``
exposes many lifecycle/sub-resource actions that don't map onto the generic
GET/POST/PATCH -> view/add/change verbs (status transitions, assignment
changes, user linking, nested addresses/emergency contacts).
"""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from dsms.identity import access

_METHOD_VERBS: dict[str, str] = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "add",
    "PATCH": "change",
    "PUT": "change",
}


def _permission_code(request: Request, view: APIView) -> str:
    action: str | None = getattr(view, "action", None)
    custom_map: dict[str, str] = getattr(view, "custom_action_permissions", {})
    if action and action in custom_map:
        return custom_map[action]
    model = getattr(view, "model")  # noqa: B009
    verb = _METHOD_VERBS.get(request.method or "", "view")
    return f"{model._meta.app_label}.{verb}_{model._meta.model_name}"


class HasScopedEmployeePermission(BasePermission):
    """Scope-aware RBAC gate for the Employee resource and its nested actions.

    ``has_permission`` (list/create and every custom action) checks the
    permission is granted *somewhere*; ``get_queryset`` does the real scope
    filtering for lists. ``has_object_permission`` checks the permission
    against the target employee's actual organizational scope via
    ``view.get_scope_kwargs(obj)``.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        permission = _permission_code(request, view)
        return permission in access.get_effective_permissions(user)

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        permission = _permission_code(request, view)
        scope_kwargs = view.get_scope_kwargs(obj)  # type: ignore[attr-defined]
        return access.has_permission(user=user, permission=permission, **scope_kwargs)
