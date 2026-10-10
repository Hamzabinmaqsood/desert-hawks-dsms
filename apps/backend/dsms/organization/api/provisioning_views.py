from typing import Any, NoReturn, cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.identity.models import User
from dsms.organization.models import TenantProvisioningRequest
from dsms.organization.provisioning import (
    InitialAdminData,
    ProvisionCompanyRequest,
    ProvisionedCompanyData,
    provision_company,
)
from dsms.organization.provisioning_exceptions import (
    TenantProvisioningAuthorizationError,
    TenantProvisioningConfigurationError,
    TenantProvisioningConflictError,
    TenantProvisioningValidationError,
)

from .provisioning_serializers import (
    TenantProvisioningInputSerializer,
    TenantProvisioningResultSerializer,
)


class ProvisioningConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The provisioning request conflicts with an existing request."
    default_code = "provisioning_conflict"


class ProvisioningConfigurationUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Tenant provisioning is not configured."
    default_code = "provisioning_configuration"


def _require_platform_user(request: Request) -> User:
    user = cast(User, request.user)
    if not user.is_active or not user.is_superuser:
        raise PermissionDenied("Only an active platform superuser may provision tenants.")
    return user


def _service_error(exc: Exception) -> NoReturn:
    if isinstance(exc, TenantProvisioningAuthorizationError):
        raise PermissionDenied(str(exc)) from exc
    if isinstance(exc, TenantProvisioningConflictError):
        raise ProvisioningConflict(str(exc)) from exc
    if isinstance(exc, TenantProvisioningValidationError):
        raise ValidationError(exc.errors) from exc
    if isinstance(exc, TenantProvisioningConfigurationError):
        raise ProvisioningConfigurationUnavailable(str(exc)) from exc
    raise exc


class TenantProvisioningCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Tenant Provisioning"],
        request=TenantProvisioningInputSerializer,
        responses={
            200: TenantProvisioningResultSerializer,
            201: TenantProvisioningResultSerializer,
        },
    )
    def post(self, request: Request) -> Response:
        actor = _require_platform_user(request)
        serializer = TenantProvisioningInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        company_data = dict(data["company"])
        admin_data = dict(data["initial_admin"])
        try:
            result = provision_company(
                actor=actor,
                idempotency_key=data["idempotency_key"],
                request=ProvisionCompanyRequest(
                    company=ProvisionedCompanyData(**company_data),
                    initial_admin=InitialAdminData(**admin_data),
                ),
                request_context=request,
            )
        except Exception as exc:
            _service_error(exc)
        response_status = status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED
        return Response(
            TenantProvisioningResultSerializer(result.provisioning_request).data,
            status=response_status,
        )


class TenantProvisioningDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Platform - Tenant Provisioning"],
        responses=TenantProvisioningResultSerializer,
    )
    def get(self, request: Request, provisioning_id: Any) -> Response:
        _require_platform_user(request)
        record = get_object_or_404(
            TenantProvisioningRequest.objects.select_related("company", "initial_admin"),
            pk=provisioning_id,
        )
        return Response(TenantProvisioningResultSerializer(record).data)
