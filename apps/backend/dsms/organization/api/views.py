"""HTTP orchestration for the organization module.

Views only translate requests into selector/service calls and shape
responses. Business rules live in :mod:`dsms.organization.services`; domain
exceptions raised there are translated into DRF validation errors here.
Authorization is delegated to the RBAC engine in :mod:`dsms.identity.access`
via :class:`~dsms.identity.permissions.HasScopedOrganizationPermission` --
list querysets are scope-filtered up front (not just object-level gated) and
writes are checked against the requested/actual organizational scope.
"""

import copy
import uuid
from collections.abc import Callable
from typing import Any, cast

from django.db import models
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.request import Request
from rest_framework.response import Response

from dsms.identity import access as identity_access
from dsms.identity.models import User
from dsms.identity.permissions import HasScopedOrganizationPermission
from dsms.organization import selectors, services
from dsms.organization.exceptions import OrganizationError, to_error_dict
from dsms.organization.models import (
    Branch,
    City,
    Company,
    Department,
    Designation,
    OperationalZone,
    Region,
)

from .filters import (
    BranchFilterSet,
    CityFilterSet,
    CompanyFilterSet,
    DepartmentFilterSet,
    DesignationFilterSet,
    OperationalZoneFilterSet,
    RegionFilterSet,
)
from .serializers import (
    BranchReadSerializer,
    BranchWriteSerializer,
    CityReadSerializer,
    CityWriteSerializer,
    CompanyReadSerializer,
    CompanyWriteSerializer,
    DepartmentReadSerializer,
    DepartmentWriteSerializer,
    DesignationReadSerializer,
    DesignationWriteSerializer,
    OperationalZoneReadSerializer,
    OperationalZoneWriteSerializer,
    OrganizationHierarchySerializer,
    RegionReadSerializer,
    RegionWriteSerializer,
)


def _service_call(func: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        return func(**kwargs)
    except OrganizationError as exc:
        raise DRFValidationError(to_error_dict(exc)) from exc


def _crud_schema(
    tag: str, read_serializer: type[serializers.BaseSerializer[Any]]
) -> dict[str, Any]:
    activate_deactivate = extend_schema(
        tags=[tag],
        request=None,
        responses=read_serializer,
    )
    return {
        "list": extend_schema(tags=[tag]),
        "retrieve": extend_schema(tags=[tag]),
        "create": extend_schema(tags=[tag]),
        "partial_update": extend_schema(tags=[tag]),
        "activate": activate_deactivate,
        "deactivate": activate_deactivate,
    }


class BaseOrganizationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    """Shared list/retrieve/create/patch/activate/deactivate orchestration."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [HasScopedOrganizationPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["code", "name"]
    ordering_fields = ["code", "name", "created_at", "updated_at"]
    ordering = ["code"]

    model: type[models.Model]
    accessible_selector: Callable[..., Any]
    serializer_class: type[serializers.BaseSerializer[Any]]
    write_serializer_class: type[serializers.BaseSerializer[Any]]
    instance_kwarg = "instance"
    create_service: Callable[..., Any]
    update_service: Callable[..., Any]
    activate_service: Callable[..., Any]
    deactivate_service: Callable[..., Any]

    def get_serializer_class(self) -> type[serializers.BaseSerializer[Any]]:
        if self.action in {"create", "update", "partial_update"}:
            return self.write_serializer_class
        return self.serializer_class

    def get_queryset(self) -> Any:
        permission = f"{self.model._meta.app_label}.view_{self.model._meta.model_name}"
        return self.accessible_selector(self.request.user, permission=permission)

    def get_scope_kwargs(self, obj: Any) -> dict[str, Any]:
        """The organizational ancestor chain used for object-level RBAC checks."""
        raise NotImplementedError

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        """The organizational ancestor chain a creator must have ``add`` rights on."""
        return {"company": validated_data.get("company")}

    def _guard_create_scope(self, validated_data: dict[str, Any]) -> None:
        # `create()` only runs after `HasScopedOrganizationPermission` has
        # already required authentication, so this is always a real user.
        user = cast(User, self.request.user)
        if user.is_superuser:
            return
        permission = f"{self.model._meta.app_label}.add_{self.model._meta.model_name}"
        scope_kwargs = self.get_create_scope_kwargs(validated_data)
        if not identity_access.has_permission(user=user, permission=permission, **scope_kwargs):
            raise DRFPermissionDenied(
                "You do not have permission to create this resource in the requested scope."
            )

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._guard_create_scope(serializer.validated_data)
        instance = _service_call(self.create_service, **serializer.validated_data)
        read_serializer = self.serializer_class(instance)
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.get("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        candidate = copy.copy(instance)
        for name, value in serializer.validated_data.items():
            setattr(candidate, name, value)
        user = cast(User, request.user)
        permission = f"{self.model._meta.app_label}.change_{self.model._meta.model_name}"
        if not user.is_superuser and not identity_access.has_permission(
            user=user, permission=permission, **self.get_scope_kwargs(candidate)
        ):
            raise DRFPermissionDenied(
                "You do not have permission in the resulting organizational scope."
            )
        service_kwargs = {self.instance_kwarg: instance, **serializer.validated_data}
        updated = _service_call(self.update_service, **service_kwargs)
        read_serializer = self.serializer_class(updated)
        return Response(read_serializer.data)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        updated = _service_call(self.activate_service, **{self.instance_kwarg: instance})
        return Response(self.serializer_class(updated).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        instance = self.get_object()
        updated = _service_call(self.deactivate_service, **{self.instance_kwarg: instance})
        return Response(self.serializer_class(updated).data)


@extend_schema_view(**_crud_schema("Organization - Companies", CompanyReadSerializer))
class CompanyViewSet(BaseOrganizationViewSet):
    model = Company
    accessible_selector = staticmethod(selectors.get_accessible_companies)
    serializer_class = CompanyReadSerializer
    write_serializer_class = CompanyWriteSerializer
    filterset_class = CompanyFilterSet
    search_fields = ["code", "legal_name", "trade_name"]
    instance_kwarg = "company"
    create_service = staticmethod(services.create_company)
    update_service = staticmethod(services.update_company)
    activate_service = staticmethod(services.activate_company)
    deactivate_service = staticmethod(services.deactivate_company)

    def get_scope_kwargs(self, obj: Company) -> dict[str, Any]:
        return {"company": obj}

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        # A company has no parent scope: only a GLOBAL assignment (or a
        # superuser) may create new companies.
        return {}


@extend_schema_view(**_crud_schema("Organization - Regions", RegionReadSerializer))
class RegionViewSet(BaseOrganizationViewSet):
    model = Region
    accessible_selector = staticmethod(selectors.get_accessible_regions)
    serializer_class = RegionReadSerializer
    write_serializer_class = RegionWriteSerializer
    filterset_class = RegionFilterSet
    instance_kwarg = "region"
    create_service = staticmethod(services.create_region)
    update_service = staticmethod(services.update_region)
    activate_service = staticmethod(services.activate_region)
    deactivate_service = staticmethod(services.deactivate_region)

    def get_scope_kwargs(self, obj: Any) -> dict[str, Any]:
        return {"company": obj.company, "region": obj}

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {"company": validated_data.get("company")}


@extend_schema_view(**_crud_schema("Organization - Cities", CityReadSerializer))
class CityViewSet(BaseOrganizationViewSet):
    model = City
    accessible_selector = staticmethod(selectors.get_accessible_cities)
    serializer_class = CityReadSerializer
    write_serializer_class = CityWriteSerializer
    filterset_class = CityFilterSet
    instance_kwarg = "city"
    create_service = staticmethod(services.create_city)
    update_service = staticmethod(services.update_city)
    activate_service = staticmethod(services.activate_city)
    deactivate_service = staticmethod(services.deactivate_city)

    def get_scope_kwargs(self, obj: Any) -> dict[str, Any]:
        return {"company": obj.company, "region": obj.region}

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {"company": validated_data.get("company"), "region": validated_data.get("region")}


@extend_schema_view(**_crud_schema("Organization - Branches", BranchReadSerializer))
class BranchViewSet(BaseOrganizationViewSet):
    model = Branch
    accessible_selector = staticmethod(selectors.get_accessible_branches)
    serializer_class = BranchReadSerializer
    write_serializer_class = BranchWriteSerializer
    filterset_class = BranchFilterSet
    instance_kwarg = "branch"
    create_service = staticmethod(services.create_branch)
    update_service = staticmethod(services.update_branch)
    activate_service = staticmethod(services.activate_branch)
    deactivate_service = staticmethod(services.deactivate_branch)

    def get_scope_kwargs(self, obj: Any) -> dict[str, Any]:
        return {"company": obj.company, "region": obj.region, "branch": obj}

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {"company": validated_data.get("company"), "region": validated_data.get("region")}


@extend_schema_view(**_crud_schema("Organization - Departments", DepartmentReadSerializer))
class DepartmentViewSet(BaseOrganizationViewSet):
    model = Department
    accessible_selector = staticmethod(selectors.get_accessible_departments)
    serializer_class = DepartmentReadSerializer
    write_serializer_class = DepartmentWriteSerializer
    filterset_class = DepartmentFilterSet
    ordering_fields = ["code", "name", "sort_order", "created_at", "updated_at"]
    ordering = ["sort_order", "code"]
    instance_kwarg = "department"
    create_service = staticmethod(services.create_department)
    update_service = staticmethod(services.update_department)
    activate_service = staticmethod(services.activate_department)
    deactivate_service = staticmethod(services.deactivate_department)

    def get_scope_kwargs(self, obj: Any) -> dict[str, Any]:
        return {"company": obj.company, "department": obj}

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {"company": validated_data.get("company")}


@extend_schema_view(**_crud_schema("Organization - Designations", DesignationReadSerializer))
class DesignationViewSet(BaseOrganizationViewSet):
    model = Designation
    accessible_selector = staticmethod(selectors.get_accessible_designations)
    serializer_class = DesignationReadSerializer
    write_serializer_class = DesignationWriteSerializer
    filterset_class = DesignationFilterSet
    ordering_fields = ["code", "name", "sort_order", "created_at", "updated_at"]
    ordering = ["sort_order", "code"]
    instance_kwarg = "designation"
    create_service = staticmethod(services.create_designation)
    update_service = staticmethod(services.update_designation)
    activate_service = staticmethod(services.activate_designation)
    deactivate_service = staticmethod(services.deactivate_designation)

    def get_scope_kwargs(self, obj: Any) -> dict[str, Any]:
        return {"company": obj.company}

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        return {"company": validated_data.get("company")}


@extend_schema_view(
    **_crud_schema("Organization - Operational Zones", OperationalZoneReadSerializer)
)
class OperationalZoneViewSet(BaseOrganizationViewSet):
    model = OperationalZone
    accessible_selector = staticmethod(selectors.get_accessible_operational_zones)
    serializer_class = OperationalZoneReadSerializer
    write_serializer_class = OperationalZoneWriteSerializer
    filterset_class = OperationalZoneFilterSet
    instance_kwarg = "operational_zone"
    create_service = staticmethod(services.create_operational_zone)
    update_service = staticmethod(services.update_operational_zone)
    activate_service = staticmethod(services.activate_operational_zone)
    deactivate_service = staticmethod(services.deactivate_operational_zone)

    def get_scope_kwargs(self, obj: Any) -> dict[str, Any]:
        return {
            "company": obj.company,
            "region": obj.branch.region,
            "branch": obj.branch,
            "operational_zone": obj,
        }

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        branch = validated_data.get("branch")
        return {
            "company": validated_data.get("company"),
            "region": branch.region if branch else None,
            "branch": branch,
        }


class OrganizationHierarchyView(viewsets.GenericViewSet[Company], mixins.ListModelMixin):
    """Read-only nested organization hierarchy, optionally filtered by company.

    Restricted to companies the caller can fully see (GLOBAL/COMPANY scope);
    narrower (region/branch/...) assignments do not receive the nested
    hierarchy view, only the plain list/retrieve endpoints for their scope.
    """

    permission_classes = [HasScopedOrganizationPermission]
    serializer_class = OrganizationHierarchySerializer
    model = Company
    queryset = Company.objects.none()

    def get_queryset(self) -> Any:
        return selectors.get_accessible_companies(
            cast(User, self.request.user), permission="organization.view_company"
        )

    @extend_schema(tags=["Organization - Hierarchy"])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        raw_company_id = request.query_params.get("company")
        company_id: uuid.UUID | None = None
        if raw_company_id:
            try:
                company_id = uuid.UUID(raw_company_id)
            except ValueError as exc:
                raise DRFValidationError({"company": ["Must be a valid UUID."]}) from exc
        accessible_ids = set(self.get_queryset().values_list("id", flat=True))
        if company_id is not None:
            if company_id not in accessible_ids:
                return Response([])
            accessible_ids = {company_id}
        data = [
            selectors.build_company_hierarchy(company=company)
            for company in Company.objects.filter(id__in=accessible_ids).order_by("code")
        ]
        serializer = self.get_serializer(data, many=True)
        return Response(serializer.data)
