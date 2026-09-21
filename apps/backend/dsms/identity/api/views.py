"""HTTP orchestration for the identity/RBAC module.

Views only translate requests into selector/service calls and shape
responses. Business rules live in :mod:`dsms.identity.services`; domain
exceptions raised there are translated into DRF errors here.
"""

from collections.abc import Callable
from typing import Any, cast

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, mixins, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.request import Request
from rest_framework.response import Response

from dsms.identity import access, selectors, services
from dsms.identity.exceptions import (
    IdentityError,
    ScopeAuthorizationError,
    SelfDeactivationError,
    SuperuserProtectionError,
    SystemRoleProtectedError,
    to_error_dict,
)
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission, RequiresPermission

from .filters import PermissionFilterSet, RoleFilterSet, UserFilterSet, UserRoleAssignmentFilterSet
from .serializers import (
    AccessMatrixEntrySerializer,
    PermissionSerializer,
    RoleReadSerializer,
    RoleWriteSerializer,
    SetPasswordSerializer,
    UserReadSerializer,
    UserRoleAssignmentReadSerializer,
    UserRoleAssignmentWriteSerializer,
    UserWriteSerializer,
)

_PERMISSION_ERROR_TYPES = (
    ScopeAuthorizationError,
    SelfDeactivationError,
    SuperuserProtectionError,
    SystemRoleProtectedError,
)


def _service_call(func: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        return func(**kwargs)
    except _PERMISSION_ERROR_TYPES as exc:
        raise DRFPermissionDenied(to_error_dict(exc)) from exc
    except IdentityError as exc:
        raise DRFValidationError(to_error_dict(exc)) from exc


def _crud_schema(
    tag: str, read_serializer: type[serializers.BaseSerializer[Any]]
) -> dict[str, Any]:
    activate_deactivate = extend_schema(tags=[tag], request=None, responses=read_serializer)
    return {
        "list": extend_schema(tags=[tag]),
        "retrieve": extend_schema(tags=[tag]),
        "create": extend_schema(tags=[tag]),
        "partial_update": extend_schema(tags=[tag]),
        "activate": activate_deactivate,
        "deactivate": activate_deactivate,
    }


@extend_schema_view(**_crud_schema("Identity - Users", UserReadSerializer))
class UserViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [HasRBACPermission]
    custom_action_permissions = {"set_password": "identity.change_user"}
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UserFilterSet
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["email", "created_at", "updated_at", "last_login"]
    ordering = ["email"]
    serializer_class = UserReadSerializer

    def get_queryset(self) -> Any:
        permission = {
            "create": "identity.add_user",
            "update": "identity.change_user",
            "partial_update": "identity.change_user",
            "activate": "identity.change_user",
            "deactivate": "identity.change_user",
            "set_password": "identity.change_user",
        }.get(self.action, "identity.view_user")
        return selectors.get_accessible_users(
            actor=cast(User, self.request.user), permission=permission
        )

    def _require_complete_user_scope(self, user: User) -> None:
        actor = cast(User, self.request.user)
        if actor.is_superuser:
            return
        if user.is_superuser:
            raise DRFPermissionDenied("Only superusers may administer a superuser account.")
        all_assignment_ids = set(user.role_assignments.values_list("id", flat=True))
        manageable_ids = set(
            selectors.get_accessible_role_assignments(
                actor=actor, permission="identity.change_user"
            ).values_list("id", flat=True)
        )
        if not all_assignment_ids.issubset(manageable_ids):
            raise DRFPermissionDenied(
                "Users with assignments outside your tenant scope require platform administration."
            )

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        if self.action in {"create", "update", "partial_update"}:
            return UserWriteSerializer
        return UserReadSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        password = data.pop("password", None)
        instance = _service_call(services.create_user, password=password, **data)
        read_serializer = UserReadSerializer(instance)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.get("partial", False)
        instance = self.get_object()
        self._require_complete_user_scope(instance)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        if "password" in data:
            raise DRFValidationError(
                {"password": ["Use the set-password action to change a password."]}
            )
        updated = _service_call(services.update_user, user=instance, **data)
        return Response(UserReadSerializer(updated).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        self._require_complete_user_scope(instance)
        updated = _service_call(services.activate_user, user=instance)
        return Response(UserReadSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        self._require_complete_user_scope(instance)
        updated = _service_call(services.deactivate_user, user=instance, actor=request.user)
        return Response(UserReadSerializer(updated).data)

    @extend_schema(tags=["Identity - Users"], request=SetPasswordSerializer, responses=None)
    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        self._require_complete_user_scope(instance)
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _service_call(
            services.set_user_password,
            user=instance,
            password=serializer.validated_data["password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema_view(**_crud_schema("Access Control - Roles", RoleReadSerializer))
class RoleViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [HasRBACPermission]
    custom_action_permissions = {
        "create": "identity.manage_roles",
        "partial_update": "identity.manage_roles",
        "activate": "identity.manage_roles",
        "deactivate": "identity.manage_roles",
    }
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = RoleFilterSet
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at", "updated_at"]
    ordering = ["code"]
    serializer_class = RoleReadSerializer

    def get_queryset(self) -> Any:
        write_action = self.action in {
            "create",
            "update",
            "partial_update",
            "activate",
            "deactivate",
        }
        actor = cast(User, self.request.user)
        queryset = selectors.get_accessible_roles(
            actor=actor,
            permission="identity.manage_roles" if write_action else "identity.view_role",
        )
        if write_action and not actor.is_superuser:
            return queryset.filter(company__isnull=False)
        return queryset

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        if self.action in {"create", "update", "partial_update"}:
            return RoleWriteSerializer
        return RoleReadSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        role_permissions = data.pop("permissions", None)
        company = data.get("company")
        actor = cast(User, request.user)
        if company is None and not actor.is_superuser:
            raise DRFPermissionDenied("Only superusers may create global roles.")
        if company is not None and not access.has_permission(
            user=actor, permission="identity.manage_roles", company=company
        ):
            raise DRFPermissionDenied("You cannot create roles for this company.")
        instance = _service_call(services.create_role, **data)
        if role_permissions is not None:
            instance = _service_call(
                services.set_role_permissions,
                role=instance,
                actor=request.user,
                permissions=role_permissions,
            )
        read_serializer = RoleReadSerializer(instance)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.get("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        role_permissions = data.pop("permissions", None)
        updated = _service_call(services.update_role, role=instance, actor=request.user, **data)
        if role_permissions is not None:
            updated = _service_call(
                services.set_role_permissions,
                role=updated,
                actor=request.user,
                permissions=role_permissions,
            )
        return Response(RoleReadSerializer(updated).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        updated = _service_call(services.activate_role, role=instance, actor=request.user)
        return Response(RoleReadSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        updated = _service_call(services.deactivate_role, role=instance, actor=request.user)
        return Response(RoleReadSerializer(updated).data)


@extend_schema_view(
    **_crud_schema("Access Control - Role Assignments", UserRoleAssignmentReadSerializer)
)
class UserRoleAssignmentViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [HasRBACPermission]
    custom_action_permissions = {
        "create": "identity.assign_roles",
        "partial_update": "identity.assign_roles",
        "activate": "identity.assign_roles",
        "deactivate": "identity.assign_roles",
    }
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = UserRoleAssignmentFilterSet
    search_fields = ["user__email", "role__code"]
    ordering_fields = ["created_at", "updated_at", "starts_at", "ends_at"]
    ordering = ["-created_at"]
    serializer_class = UserRoleAssignmentReadSerializer

    def get_queryset(self) -> Any:
        permission = (
            "identity.assign_roles"
            if self.action in {"create", "update", "partial_update", "activate", "deactivate"}
            else "identity.view_userroleassignment"
        )
        return selectors.get_accessible_role_assignments(
            actor=cast(User, self.request.user), permission=permission
        )

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        if self.action in {"create", "update", "partial_update"}:
            return UserRoleAssignmentWriteSerializer
        return UserRoleAssignmentReadSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = _service_call(
            services.assign_role, actor=request.user, **serializer.validated_data
        )
        read_serializer = UserRoleAssignmentReadSerializer(instance)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.get("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.update_role_assignment,
            assignment=instance,
            actor=request.user,
            **serializer.validated_data,
        )
        return Response(UserRoleAssignmentReadSerializer(updated).data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        updated = _service_call(
            services.activate_role_assignment, assignment=instance, actor=request.user
        )
        return Response(UserRoleAssignmentReadSerializer(updated).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        updated = _service_call(
            services.deactivate_role_assignment, assignment=instance, actor=request.user
        )
        return Response(UserRoleAssignmentReadSerializer(updated).data)


@extend_schema_view(list=extend_schema(tags=["Access Control - Permissions"]))
class PermissionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet[Any]):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = PermissionSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PermissionFilterSet
    search_fields = ["name", "codename"]
    ordering_fields = ["codename"]
    ordering = ["content_type__app_label", "content_type__model", "codename"]

    def get_queryset(self) -> Any:
        return selectors.get_permissions()


class AccessMatrixView(generics.GenericAPIView[Any]):
    permission_classes = [RequiresPermission]
    required_permission = "identity.view_access_matrix"
    serializer_class = AccessMatrixEntrySerializer

    @extend_schema(tags=["Access Control - Permissions"])
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        data = selectors.get_accessible_access_matrix(actor=cast(User, request.user))
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
