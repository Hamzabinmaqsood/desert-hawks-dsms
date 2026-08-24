# mypy: disable-error-code="type-arg,attr-defined,no-untyped-def,arg-type"
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from dsms.identity.access import filter_queryset_by_scope
from dsms.identity.permissions import HasRBACPermission

from .. import models, selectors, services
from .serializers import SERIALIZERS


class NoDeleteViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAuthenticated, HasRBACPermission]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return filter_queryset_by_scope(super().get_queryset(), self.request.user)


def basic_viewset(model: type) -> type[NoDeleteViewSet]:
    class ViewSet(NoDeleteViewSet):
        queryset = model.objects.all()
        serializer_class = SERIALIZERS[model.__name__]

    ViewSet.__name__ = f"{model.__name__}ViewSet"
    return ViewSet


class ClientViewSet(NoDeleteViewSet):
    queryset = selectors.client_list()
    serializer_class = SERIALIZERS["Client"]

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_client(client=self.get_object())).data
        )


class ContractViewSet(NoDeleteViewSet):
    queryset = selectors.contract_list()
    serializer_class = SERIALIZERS["ServiceContract"]

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
    queryset = selectors.security_site_list()
    serializer_class = SERIALIZERS["SecuritySite"]

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_security_site(site=self.get_object())).data
        )


class PostViewSet(NoDeleteViewSet):
    queryset = models.SecurityPost.objects.select_related("site", "company", "client")
    serializer_class = SERIALIZERS["SecurityPost"]

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        return Response(
            self.get_serializer(services.activate_security_post(post=self.get_object())).data
        )


class StaffingViewSet(NoDeleteViewSet):
    queryset = selectors.staffing_requirement_list()
    serializer_class = SERIALIZERS["StaffingRequirement"]

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


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard_summary(request):
    return Response(
        selectors.contract_dashboard_summary(company_id=request.query_params.get("company"))
    )


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staffing_demand_summary(request):
    return Response(
        selectors.contractual_demand_summary(company_id=request.query_params.get("company"))
    )


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exception_center(request):
    summary = selectors.contract_dashboard_summary(company_id=request.query_params.get("company"))
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
