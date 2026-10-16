"""HTTP orchestration for the workforce/employee-master module.

Views only translate requests into selector/service calls and shape
responses. Business rules live in :mod:`dsms.workforce.services`; domain
exceptions raised there are translated into DRF errors here. Authorization
is delegated to the RBAC engine via
:class:`~dsms.workforce.permissions.HasScopedEmployeePermission` -- the list
queryset is scope-filtered up front (not just object-level gated), and
writes/lifecycle actions are checked against the employee's actual
organizational scope.
"""

from collections.abc import Callable
from typing import Any, cast

from django.db import transaction
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied as DRFPermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter
from rest_framework.request import Request
from rest_framework.response import Response

from dsms.identity import access as identity_access
from dsms.identity.models import User
from dsms.subscriptions.api.enforcement import TenantModuleViewMixin
from dsms.workforce import selectors, services
from dsms.workforce.exceptions import WorkforceError, to_error_dict
from dsms.workforce.models import EmergencyContact, Employee, EmployeeAddress
from dsms.workforce.permissions import HasScopedEmployeePermission

from .filters import EmployeeFilterSet, EmployeeSearchFilter
from .serializers import (
    ChangeAssignmentSerializer,
    EmergencyContactReadSerializer,
    EmergencyContactWriteSerializer,
    EmployeeAddressReadSerializer,
    EmployeeAddressWriteSerializer,
    EmployeeAssignmentHistorySerializer,
    EmployeeDetailSerializer,
    EmployeeListSerializer,
    EmployeeStatusHistorySerializer,
    EmployeeWriteSerializer,
    LinkUserSerializer,
    StatusChangeSerializer,
    TerminalStatusChangeSerializer,
)

_NON_PATCHABLE_FIELDS = frozenset(
    {"employee_number", "company", "branch", "department", "designation"}
)
_CONTACT_FIELDS = frozenset({"personal_email", "mobile_number", "alternate_mobile_number"})

_TAGS = ["Workforce"]
_LIFECYCLE_TAGS = ["Workforce", "Employee Lifecycle"]


def _service_call(func: Callable[..., Any], **kwargs: Any) -> Any:
    try:
        return func(**kwargs)
    except WorkforceError as exc:
        raise DRFValidationError(to_error_dict(exc)) from exc


def _employee_schema() -> dict[str, Any]:
    def lifecycle(request: Any) -> Any:
        return extend_schema(
            tags=_LIFECYCLE_TAGS,
            request=request,
            responses=EmployeeDetailSerializer,
        )

    return {
        "list": extend_schema(tags=_TAGS),
        "retrieve": extend_schema(tags=_TAGS),
        "create": extend_schema(
            tags=_TAGS, request=EmployeeWriteSerializer, responses=EmployeeDetailSerializer
        ),
        "partial_update": extend_schema(
            tags=_TAGS, request=EmployeeWriteSerializer, responses=EmployeeDetailSerializer
        ),
        "activate": lifecycle(StatusChangeSerializer),
        "leave": lifecycle(StatusChangeSerializer),
        "return_from_leave": lifecycle(StatusChangeSerializer),
        "suspend": lifecycle(StatusChangeSerializer),
        "reinstate": lifecycle(StatusChangeSerializer),
        "resign": lifecycle(TerminalStatusChangeSerializer),
        "terminate": lifecycle(TerminalStatusChangeSerializer),
        "retire": lifecycle(TerminalStatusChangeSerializer),
        "mark_absconded": lifecycle(TerminalStatusChangeSerializer),
        "change_assignment": lifecycle(ChangeAssignmentSerializer),
        "link_user": lifecycle(LinkUserSerializer),
        "unlink_user": lifecycle(None),
        "status_history": extend_schema(
            tags=_LIFECYCLE_TAGS, responses=EmployeeStatusHistorySerializer(many=True)
        ),
        "assignment_history": extend_schema(
            tags=_LIFECYCLE_TAGS, responses=EmployeeAssignmentHistorySerializer(many=True)
        ),
        "addresses": extend_schema(
            tags=_TAGS,
            request=EmployeeAddressWriteSerializer,
            responses=EmployeeAddressReadSerializer(many=True),
        ),
        "address_detail": extend_schema(
            tags=_TAGS,
            parameters=[OpenApiParameter("address_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
            request=EmployeeAddressWriteSerializer,
            responses=EmployeeAddressReadSerializer,
        ),
        "emergency_contacts": extend_schema(
            tags=_TAGS,
            request=EmergencyContactWriteSerializer,
            responses=EmergencyContactReadSerializer(many=True),
        ),
        "emergency_contact_detail": extend_schema(
            tags=_TAGS,
            parameters=[OpenApiParameter("contact_id", OpenApiTypes.UUID, OpenApiParameter.PATH)],
            request=EmergencyContactWriteSerializer,
            responses=EmergencyContactReadSerializer,
        ),
    }


@extend_schema_view(**_employee_schema())
class EmployeeViewSet(
    TenantModuleViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet[Any],
):
    required_module_ids = ("people",)
    module_company_lookup = "company_id"
    http_method_names = ["get", "post", "patch", "head", "options"]
    permission_classes = [HasScopedEmployeePermission]
    model = Employee
    filter_backends = [DjangoFilterBackend, EmployeeSearchFilter, OrderingFilter]
    filterset_class = EmployeeFilterSet
    search_fields = [
        "employee_number",
        "first_name",
        "middle_name",
        "last_name",
        "personal_email",
        "mobile_number",
    ]
    ordering_fields = [
        "employee_number",
        "first_name",
        "last_name",
        "joining_date",
        "created_at",
        "updated_at",
    ]
    ordering = ["employee_number"]
    serializer_class = EmployeeDetailSerializer

    custom_action_permissions = {
        "activate": "workforce.manage_employee_status",
        "leave": "workforce.manage_employee_status",
        "return_from_leave": "workforce.manage_employee_status",
        "suspend": "workforce.manage_employee_status",
        "reinstate": "workforce.manage_employee_status",
        "resign": "workforce.manage_employee_status",
        "terminate": "workforce.manage_employee_status",
        "retire": "workforce.manage_employee_status",
        "mark_absconded": "workforce.manage_employee_status",
        "change_assignment": "workforce.manage_employee_assignment",
        "link_user": "workforce.link_employee_user",
        "unlink_user": "workforce.link_employee_user",
        "status_history": "workforce.view_employee",
        "assignment_history": "workforce.view_employee",
        "addresses": "workforce.view_employee",
        "address_detail": "workforce.view_employee",
        "emergency_contacts": "workforce.view_employee",
        "emergency_contact_detail": "workforce.view_employee",
    }

    # -- Plumbing ------------------------------------------------------------

    def get_queryset(self) -> Any:
        user = cast(User, self.request.user)
        return selectors.get_accessible_employees(user, permission="workforce.view_employee")

    def get_serializer_class(self) -> Any:
        if self.action in {"create", "update", "partial_update"}:
            return EmployeeWriteSerializer
        if self.action == "list":
            return EmployeeListSerializer
        return EmployeeDetailSerializer

    def get_scope_kwargs(self, obj: Employee) -> dict[str, Any]:
        branch = obj.branch
        return {
            "company": obj.company,
            "region": branch.region if branch is not None else None,
            "branch": branch,
            "department": obj.department,
        }

    def get_create_scope_kwargs(self, validated_data: dict[str, Any]) -> dict[str, Any]:
        branch = validated_data.get("branch")
        return {
            "company": validated_data.get("company"),
            "region": branch.region if branch else None,
            "branch": branch,
            "department": validated_data.get("department"),
        }

    def _guard_create_scope(self, validated_data: dict[str, Any]) -> None:
        self.require_modules_for(validated_data.get("company"))
        user = cast(User, self.request.user)
        if user.is_superuser:
            return
        scope_kwargs = self.get_create_scope_kwargs(validated_data)
        if not identity_access.has_permission(
            user=user, permission="workforce.add_employee", **scope_kwargs
        ):
            raise DRFPermissionDenied(
                "You do not have permission to create an employee in the requested scope."
            )

    def _require_permission(self, request: Request, codename: str, employee: Employee) -> None:
        user = cast(User, request.user)
        if user.is_superuser:
            return
        if not identity_access.has_permission(
            user=user, permission=codename, **self.get_scope_kwargs(employee)
        ):
            raise DRFPermissionDenied("You do not have permission to perform this action.")

    def _read(self, instance: Employee) -> Response:
        return Response(
            EmployeeDetailSerializer(instance, context=self.get_serializer_context()).data
        )

    # -- CRUD ------------------------------------------------------------------

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._guard_create_scope(serializer.validated_data)
        instance = _service_call(
            services.create_employee, actor=request.user, **serializer.validated_data
        )
        read_serializer = EmployeeDetailSerializer(instance, context=self.get_serializer_context())
        headers = self.get_success_headers(read_serializer.data)
        return Response(read_serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        partial = kwargs.get("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        disallowed = _NON_PATCHABLE_FIELDS & data.keys()
        if disallowed:
            raise DRFValidationError(
                {
                    field: [
                        "This field cannot be changed through this endpoint; "
                        "use the dedicated change-assignment action for organizational fields."
                    ]
                    for field in disallowed
                }
            )
        contact_fields = {key: data.pop(key) for key in list(data) if key in _CONTACT_FIELDS}
        with transaction.atomic():
            if data:
                instance = _service_call(
                    services.update_employee_personal_details, employee=instance, **data
                )
            if contact_fields:
                instance = _service_call(
                    services.update_employee_contact_details, employee=instance, **contact_fields
                )
        return self._read(instance)

    def partial_update(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    # -- Employment status lifecycle --------------------------------------------

    @action(detail=True, methods=["post"])
    def activate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.activate_employee,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"])
    def leave(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.place_employee_on_leave,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"], url_path="return-from-leave")
    def return_from_leave(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.return_employee_from_leave,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"])
    def suspend(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.suspend_employee,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"])
    def reinstate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.reinstate_employee,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"])
    def resign(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = TerminalStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.resign_employee,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"])
    def terminate(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = TerminalStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.terminate_employee,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"])
    def retire(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = TerminalStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.retire_employee,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    @action(detail=True, methods=["post"], url_path="mark-absconded")
    def mark_absconded(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = TerminalStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.mark_employee_absconded,
            employee=employee,
            changed_by=request.user,
            **serializer.validated_data,
        )
        return self._read(updated)

    # -- Organizational assignment --------------------------------------------

    @action(detail=True, methods=["post"], url_path="change-assignment")
    def change_assignment(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = ChangeAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        user = cast(User, request.user)
        if not user.is_superuser:
            branch = data.get("branch")
            target_scope = {
                "company": employee.company,
                "region": branch.region if branch else None,
                "branch": branch,
                "department": data.get("department"),
            }
            if not identity_access.has_permission(
                user=user, permission="workforce.manage_employee_assignment", **target_scope
            ):
                raise DRFPermissionDenied(
                    "You do not have permission to assign this employee to the requested scope."
                )
        updated = _service_call(
            services.change_employee_organization, employee=employee, actor=request.user, **data
        )
        return self._read(updated)

    # -- User access linking --------------------------------------------------

    @action(detail=True, methods=["post"], url_path="link-user")
    def link_user(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        serializer = LinkUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = _service_call(
            services.link_employee_user, employee=employee, **serializer.validated_data
        )
        return self._read(updated)

    @action(detail=True, methods=["post"], url_path="unlink-user")
    def unlink_user(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        updated = _service_call(services.unlink_employee_user, employee=employee)
        return self._read(updated)

    # -- History (read-only) ---------------------------------------------------

    @action(detail=True, methods=["get"], url_path="status-history")
    def status_history(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        queryset = selectors.employee_status_history(employee=employee)
        return Response(EmployeeStatusHistorySerializer(queryset, many=True).data)

    @action(detail=True, methods=["get"], url_path="assignment-history")
    def assignment_history(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        queryset = selectors.employee_assignment_history(employee=employee)
        return Response(EmployeeAssignmentHistorySerializer(queryset, many=True).data)

    # -- Addresses ---------------------------------------------------------------

    @action(detail=True, methods=["get", "post"], url_path="addresses")
    def addresses(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        if request.method == "POST":
            self._require_permission(request, "workforce.add_employeeaddress", employee)
            serializer = EmployeeAddressWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            address = _service_call(
                services.add_employee_address, employee=employee, **serializer.validated_data
            )
            return Response(
                EmployeeAddressReadSerializer(address).data, status=status.HTTP_201_CREATED
            )
        self._require_permission(request, "workforce.view_employeeaddress", employee)
        queryset = selectors.employee_addresses(employee=employee)
        return Response(EmployeeAddressReadSerializer(queryset, many=True).data)

    @action(
        detail=True,
        methods=["get", "patch"],
        url_path=r"addresses/(?P<address_id>[^/.]+)",
        url_name="address-detail",
    )
    def address_detail(
        self, request: Request, address_id: str | None = None, *args: Any, **kwargs: Any
    ) -> Response:
        employee = self.get_object()
        address = get_object_or_404(EmployeeAddress, pk=address_id, employee=employee)
        if request.method == "PATCH":
            self._require_permission(request, "workforce.change_employeeaddress", employee)
            serializer = EmployeeAddressWriteSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            address = _service_call(
                services.update_employee_address, address=address, **serializer.validated_data
            )
            return Response(EmployeeAddressReadSerializer(address).data)
        self._require_permission(request, "workforce.view_employeeaddress", employee)
        return Response(EmployeeAddressReadSerializer(address).data)

    # -- Emergency contacts --------------------------------------------------------

    @action(detail=True, methods=["get", "post"], url_path="emergency-contacts")
    def emergency_contacts(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        employee = self.get_object()
        if request.method == "POST":
            self._require_permission(request, "workforce.add_emergencycontact", employee)
            serializer = EmergencyContactWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            contact = _service_call(
                services.add_emergency_contact, employee=employee, **serializer.validated_data
            )
            return Response(
                EmergencyContactReadSerializer(contact).data, status=status.HTTP_201_CREATED
            )
        self._require_permission(request, "workforce.view_emergencycontact", employee)
        queryset = selectors.employee_emergency_contacts(employee=employee)
        return Response(EmergencyContactReadSerializer(queryset, many=True).data)

    @action(
        detail=True,
        methods=["get", "patch"],
        url_path=r"emergency-contacts/(?P<contact_id>[^/.]+)",
        url_name="emergency-contact-detail",
    )
    def emergency_contact_detail(
        self, request: Request, contact_id: str | None = None, *args: Any, **kwargs: Any
    ) -> Response:
        employee = self.get_object()
        contact = get_object_or_404(EmergencyContact, pk=contact_id, employee=employee)
        if request.method == "PATCH":
            self._require_permission(request, "workforce.change_emergencycontact", employee)
            serializer = EmergencyContactWriteSerializer(data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            contact = _service_call(
                services.update_emergency_contact, contact=contact, **serializer.validated_data
            )
            return Response(EmergencyContactReadSerializer(contact).data)
        self._require_permission(request, "workforce.view_emergencycontact", employee)
        return Response(EmergencyContactReadSerializer(contact).data)
