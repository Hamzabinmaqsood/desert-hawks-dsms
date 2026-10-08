"""JWT authentication endpoints and the current-user (/me) endpoints."""

from typing import Any, cast

from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status, views
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView

from dsms.audit.models import AuditCategory, AuditSeverity
from dsms.audit.services import record_audit_event
from dsms.identity import access, company_context, selectors
from dsms.identity.models import User

from .auth_serializers import (
    AccessScopeSummarySerializer,
    CompanyContextResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    PermissionsResponseSerializer,
    SelectCompanySerializer,
    TokenPairResponseSerializer,
    TokenRefreshResponseSerializer,
    TokenVerifyResponseSerializer,
)
from .serializers import UserReadSerializer


@extend_schema(tags=["Authentication"], responses=TokenPairResponseSerializer)
class LoginView(TokenObtainPairView):
    """Email + password login. Returns a short-lived access token and a
    rotating, longer-lived refresh token."""

    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        try:
            response = super().post(request, *args, **kwargs)
        except APIException:
            record_audit_event(
                action="LOGIN_FAILED",
                category=AuditCategory.AUTHENTICATION,
                severity=AuditSeverity.WARNING,
                summary="Authentication attempt failed.",
                success=False,
                reason_code="INVALID_CREDENTIALS",
                request_context=request,
            )
            raise
        user = User.objects.filter(email__iexact=request.data.get("email", "")).first()
        record_audit_event(
            action="LOGIN_SUCCEEDED",
            category=AuditCategory.AUTHENTICATION,
            summary="User authenticated successfully.",
            actor_user=user,
            source_object=user,
            request_context=request,
        )
        return response


@extend_schema(tags=["Authentication"], responses=TokenRefreshResponseSerializer)
class RefreshView(TokenRefreshView):
    """Exchange a valid refresh token for a new token pair.

    The submitted refresh token is rotated and blacklisted per
    ``SIMPLE_JWT['ROTATE_REFRESH_TOKENS']``/``BLACKLIST_AFTER_ROTATION``.
    """


@extend_schema(tags=["Authentication"], responses=TokenVerifyResponseSerializer)
class VerifyView(TokenVerifyView):
    """Verify that a token is well-formed, unexpired, and not blacklisted."""


@extend_schema(tags=["Authentication"], responses=None)
class LogoutView(generics.GenericAPIView[Any]):
    """Blacklist the submitted refresh token, ending that session."""

    serializer_class = LogoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        company_context.clear_selected_company(request)
        record_audit_event(
            action="LOGOUT",
            category=AuditCategory.AUTHENTICATION,
            summary="User session logged out.",
            actor_user=request.user,
            source_object=request.user,
            request_context=request,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["Authentication"])
class MeView(generics.RetrieveAPIView[Any]):
    """The authenticated user's own profile."""

    serializer_class = UserReadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self) -> Any:
        return self.request.user


@extend_schema(tags=["Authentication"])
class MePermissionsView(generics.GenericAPIView[Any]):
    """The authenticated user's effective permission codes, ignoring scope."""

    serializer_class = PermissionsResponseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = cast(User, request.user)
        data = {"permissions": selectors.get_current_user_context(user)["permissions"]}
        return Response(self.get_serializer(data).data)


@extend_schema(tags=["Authentication"])
class MeAccessScopesView(generics.GenericAPIView[Any]):
    """The authenticated user's organizational access-scope summary."""

    serializer_class = AccessScopeSummarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        user = cast(User, request.user)
        data = access.get_access_scope_summary(user)
        return Response(self.get_serializer(data).data)


class CompanyContextView(views.APIView):
    """Bootstrap and switch the authenticated user's selected Company context."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["Authentication"], responses=CompanyContextResponseSerializer)
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        payload = company_context.build_company_context(request)
        return Response(CompanyContextResponseSerializer(payload).data)

    @extend_schema(
        tags=["Authentication"],
        request=SelectCompanySerializer,
        responses=CompanyContextResponseSerializer,
    )
    def put(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = SelectCompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        company_context.select_company(request, serializer.validated_data["company_id"])
        payload = company_context.build_company_context(request)
        return Response(CompanyContextResponseSerializer(payload).data)
