"""Reusable DRF permission classes backed by the RBAC engine in :mod:`dsms.identity.access`.

Views never compute permission strings or scope containment themselves --
they declare *what* is required (a model, a custom action/permission map,
optionally a scope-kwargs resolver) and these classes ask ``access`` for the
answer. GET/HEAD/OPTIONS map to the model's ``view`` permission, POST to
``add``, PATCH/PUT to ``change``. DELETE is never mapped, so it is denied by
default unless a view explicitly opts in (none do).
"""

from typing import Any

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from . import access

_METHOD_VERBS: dict[str, str] = {
    "GET": "view",
    "HEAD": "view",
    "OPTIONS": "view",
    "POST": "add",
    "PATCH": "change",
    "PUT": "change",
}
_DEFAULT_ACTION_VERBS: dict[str, str] = {"activate": "change", "deactivate": "change"}


def _model_permission_code(
    request: Request, view: APIView, *, verb_overrides: dict[str, str]
) -> str:
    action: str | None = getattr(view, "action", None)
    verb = verb_overrides.get(action or "", _METHOD_VERBS.get(request.method or "", "view"))
    # Prefer an explicit `model` attribute: `get_queryset()` on scoped
    # organization views itself depends on the permission being requested,
    # so deriving the model from a live queryset would recurse.
    model = getattr(view, "model", None) or view.get_queryset().model  # type: ignore[attr-defined]
    return f"{model._meta.app_label}.{verb}_{model._meta.model_name}"


class HasRBACPermission(BasePermission):
    """Coarse (non-scoped) RBAC gate for identity's own resources.

    Views may set ``custom_action_permissions: dict[str, str]`` mapping an
    action name straight to a full ``app_label.codename`` permission string
    (used e.g. for role-assignment writes, which require
    ``identity.assign_roles`` rather than the generic add/change codes).
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        custom_map: dict[str, str] = getattr(view, "custom_action_permissions", {})
        action: str | None = getattr(view, "action", None)
        permission = custom_map.get(action or "") or _model_permission_code(
            request, view, verb_overrides=_DEFAULT_ACTION_VERBS
        )
        # Coarse gate: granted *anywhere*, in any scope (a COMPANY-scoped
        # `assign_roles` holder must still pass this to reach list/create;
        # `has_permission()` with no scope kwargs would only match GLOBAL).
        return permission in access.get_effective_permissions(user)


class HasScopedOrganizationPermission(BasePermission):
    """Scope-aware RBAC gate for organization master-data resources.

    ``has_permission`` (list/create) checks the permission is granted
    *somewhere*; the view's ``get_queryset`` is expected to further restrict
    results to the caller's accessible scope. ``has_object_permission``
    (retrieve/update/activate/deactivate) checks the permission against the
    object's actual organizational scope via ``view.get_scope_kwargs(obj)``.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        permission = _model_permission_code(request, view, verb_overrides=_DEFAULT_ACTION_VERBS)
        # Coarse gate: granted *anywhere*. `get_queryset()` (list) and
        # `_guard_create_scope()` (create) do the real scope filtering/check.
        return permission in access.get_effective_permissions(user)

    def has_object_permission(self, request: Request, view: APIView, obj: Any) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        permission = _model_permission_code(request, view, verb_overrides=_DEFAULT_ACTION_VERBS)
        scope_kwargs = view.get_scope_kwargs(obj)  # type: ignore[attr-defined]
        return access.has_permission(user=user, permission=permission, **scope_kwargs)


class RequiresPermission(BasePermission):
    """Gate requiring a single fixed permission declared as ``view.required_permission``."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser:
            return True
        required = getattr(view, "required_permission", None)
        if not required:
            return True
        return required in access.get_effective_permissions(user)
