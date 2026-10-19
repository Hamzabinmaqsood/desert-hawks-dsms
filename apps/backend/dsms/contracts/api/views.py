# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,arg-type,no-untyped-call"
import copy
from typing import cast

from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.identity import access
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission
from dsms.organization.models import Company
from dsms.subscriptions.api.enforcement import (
    TenantModuleViewMixin,
    entitled_company_ids,
    module_api_surface,
)

from .. import models, selectors, services
from . import security
from .serializers import SERIALIZERS


class NoDeleteViewSet(
    TenantModuleViewMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    required_module_ids = ("client_contracts",)
    permission_classes = [IsAuthenticated, HasRBACPermission]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    http_method_names = ["get", "post", "patch", "head", "options"]
    model: type

    def get_module_company_lookup(self):
        return security.COMPANY_PATHS[self.model]

    def get_scope_permission(self):
        custom = getattr(self, "custom_action_permissions", {}).get(self.action)
        if custom:
            return custom
        verb = (
            "view"
            if self.action in {"list", "retrieve"}
            else "add"
            if self.action == "create"
            else "change"
        )
        return f"contracts.{verb}_{self.model._meta.model_name}"

    def get_queryset(self):
        return security.scoped_queryset(
            super().get_queryset(), user=self.request.user, permission=self.get_scope_permission()
        )

    def _guard_write(self, candidate):
        self.require_modules_for(candidate)
        user = cast(User, self.request.user)
        company_id = security.company_id_for(candidate)
        if company_id is None:
            if not user.is_superuser:
                raise PermissionDenied("Only superusers may write global Contract references.")
            return
        company = Company.objects.filter(pk=company_id, is_active=True).first()
        if company is None or not access.has_permission(
            user=user, permission=self.get_scope_permission(), company=company
        ):
            raise PermissionDenied("You do not have permission in the requested company.")

    def perform_create(self, serializer):
        extra = {}
        if self.model is models.ServiceContract:
            extra["created_by"] = self.request.user
        if self.model is models.SiteOperationalProfile:
            extra["updated_by"] = self.request.user
        candidate = self.model(**serializer.validated_data, **extra)
        self._guard_write(candidate)
        serializer.save(**extra)

    def perform_update(self, serializer):
        candidate = copy.copy(serializer.instance)
        for name, value in serializer.validated_data.items():
            setattr(candidate, name, value)
        self._guard_write(candidate)
        extra = (
            {"updated_by": self.request.user} if self.model is models.SiteOperationalProfile else {}
        )
        serializer.save(**extra)


def basic_viewset(model: type) -> type[NoDeleteViewSet]:
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    ViewSet.__name__ = f"{model.__name__}ViewSet"
    ViewSet.model = model
    if model in {
        models.SiteType,
        models.SiteContact,
        models.SiteOperationalProfile,
        models.SiteEscalationContact,
        models.SiteCalendarException,
        models.PostType,
        models.PostQualificationRequirement,
        models.PostCredentialRequirement,
    }:
        ViewSet.required_module_ids = ("security_operations",)
    if model is models.ContractAmendment:
        ViewSet.http_method_names = ["get", "head", "options"]
    return ViewSet


class ClientViewSet(NoDeleteViewSet):
    model = models.Client
    queryset = selectors.client_list()
    serializer_class = SERIALIZERS["Client"]
    filterset_fields = ["company", "industry", "status"]
    search_fields = [
        "client_code",
        "legal_name",
        "trade_name",
        "registration_number",
        "tax_number",
        "main_email",
    ]
    ordering_fields = ["client_code", "legal_name", "status", "created_at", "updated_at"]
    ordering = ["legal_name"]
    custom_action_permissions = {"activate": "contracts.change_client"}

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_client(client=self.get_object())).data
        )


class ContractViewSet(NoDeleteViewSet):
    model = models.ServiceContract
    queryset = selectors.contract_list()
    serializer_class = SERIALIZERS["ServiceContract"]
    filterset_fields = ["company", "client", "contract_type", "status"]
    search_fields = ["contract_number", "title", "client__legal_name", "client_reference"]
    ordering_fields = ["contract_number", "title", "start_date", "end_date", "status"]
    ordering = ["-start_date", "contract_number"]
    custom_action_permissions = {
        "submit": "contracts.change_servicecontract",
        "approve": "contracts.approve_contract",
        "activate": "contracts.activate_contract",
    }

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.submit_contract_for_approval(contract=self.get_object())
            ).data
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.approve_contract(contract=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_contract(contract=self.get_object())).data
        )


class SiteViewSet(NoDeleteViewSet):
    required_module_ids = ("security_operations",)
    model = models.SecuritySite
    queryset = selectors.security_site_list()
    serializer_class = SERIALIZERS["SecuritySite"]
    custom_action_permissions = {"activate": "contracts.change_securitysite"}

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_security_site(site=self.get_object())).data
        )


class PostViewSet(NoDeleteViewSet):
    required_module_ids = ("security_operations",)
    model = models.SecurityPost
    queryset = models.SecurityPost.objects.select_related("site", "company", "client")
    serializer_class = SERIALIZERS["SecurityPost"]
    custom_action_permissions = {"activate": "contracts.change_securitypost"}

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_security_post(post=self.get_object())).data
        )


class StaffingViewSet(NoDeleteViewSet):
    required_module_ids = ("security_operations",)
    model = models.StaffingRequirement
    queryset = selectors.staffing_requirement_list()
    serializer_class = SERIALIZERS["StaffingRequirement"]
    custom_action_permissions = {"activate": "contracts.change_staffingrequirement"}

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(
                services.activate_staffing_requirement(requirement=self.get_object())
            ).data
        )


ClientIndustryViewSet = basic_viewset(models.ClientIndustry)
ClientContactViewSet = basic_viewset(models.ClientContact)
ContractServiceViewSet = basic_viewset(models.ContractService)
ContractAmendmentViewSet = basic_viewset(models.ContractAmendment)
CommercialTermsViewSet = basic_viewset(models.ContractCommercialTerms)
SiteTypeViewSet = basic_viewset(models.SiteType)
SiteContactViewSet = basic_viewset(models.SiteContact)
SiteOperationalProfileViewSet = basic_viewset(models.SiteOperationalProfile)
SiteEscalationViewSet = basic_viewset(models.SiteEscalationContact)
SiteCalendarViewSet = basic_viewset(models.SiteCalendarException)
PostTypeViewSet = basic_viewset(models.PostType)
PostQualificationViewSet = basic_viewset(models.PostQualificationRequirement)
PostCredentialViewSet = basic_viewset(models.PostCredentialRequirement)
SLAViewSet = basic_viewset(models.ServiceLevelAgreement)

# Bounded parent filters support client-ready nested panels without fetching a
# tenant-wide collection and filtering it in the browser.
ClientIndustryViewSet.filterset_fields = ["company", "is_active"]
ClientIndustryViewSet.ordering_fields = ["code", "name"]
ClientIndustryViewSet.ordering = ["name"]
ClientContactViewSet.filterset_fields = ["client", "contact_type", "is_active"]
ClientContactViewSet.ordering_fields = ["name", "created_at"]
ClientContactViewSet.ordering = ["name"]
ContractServiceViewSet.filterset_fields = ["contract", "service_type", "is_active"]
ContractServiceViewSet.ordering_fields = ["name", "start_date", "created_at"]
ContractServiceViewSet.ordering = ["name"]
ContractAmendmentViewSet.filterset_fields = ["contract"]
ContractAmendmentViewSet.ordering_fields = ["amendment_number", "effective_date"]
ContractAmendmentViewSet.ordering = ["-effective_date", "-amendment_number"]
CommercialTermsViewSet.filterset_fields = ["contract"]
SLAViewSet.filterset_fields = {
    "contract": ["exact"],
    "site": ["exact", "isnull"],
    "is_active": ["exact"],
}
SLAViewSet.ordering_fields = ["name", "effective_from"]
SLAViewSet.ordering = ["name"]


@module_api_surface("client_contracts")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    return Response(
        selectors.contract_dashboard_summary(
            company_ids=_dashboard_company_ids(request, ("client_contracts",))
        )
    )


@module_api_surface("security_operations")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staffing_demand_summary(request):
    return Response(
        selectors.contractual_demand_summary(
            company_ids=_dashboard_company_ids(request, ("security_operations",))
        )
    )


@module_api_surface("security_operations")
@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exception_center(request):
    summary = selectors.contract_dashboard_summary(
        company_ids=_dashboard_company_ids(request, ("security_operations",))
    )
    return Response(
        [
            {
                "code": "ACTIVE_SITE_WITHOUT_STAFFING",
                "severity": "HIGH",
                "count": summary["sites_without_staffing_requirements"],
            },
            {
                "code": "ACTIVE_POST_WITHOUT_REQUIREMENT",
                "severity": "WARNING",
                "count": summary["posts_without_requirements"],
            },
        ]
    )


def _dashboard_company_ids(request, module_ids):
    user: User = request.user
    permission = "contracts.view_servicecontract"
    if user.is_superuser:
        requested = request.query_params.get("company")
        requested_ids = [requested] if requested else None
        return entitled_company_ids(request, requested_ids, module_ids)
    if permission not in access.get_effective_permissions(user):
        raise PermissionDenied("You do not have permission to view Contract data.")
    accessible_ids = access.get_fully_accessible_company_ids(user, permission=permission)
    requested = request.query_params.get("company")
    if requested:
        if str(requested) not in {str(value) for value in accessible_ids}:
            raise Http404
        return [requested]
    return entitled_company_ids(request, list(accessible_ids), module_ids)
