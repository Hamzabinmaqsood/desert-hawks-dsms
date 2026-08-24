from typing import Any, cast

from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dsms.identity import access
from dsms.identity.models import User

from .. import selectors, services
from ..exceptions import FinanceError, to_error_dict
from .serializers import (
    AccountSerializer,
    FiscalYearSerializer,
    JournalReadSerializer,
    JournalWriteSerializer,
    PeriodSerializer,
    ReasonSerializer,
    ReversalSerializer,
)


def call(function: Any, **kwargs: Any) -> Any:
    try:
        return function(**kwargs)
    except FinanceError as exc:
        raise ValidationError(to_error_dict(exc)) from exc


class FinancePermission(BasePermission):
    def has_permission(self, request: Request, view: APIView) -> bool:
        user = cast(User, request.user)
        if not user or not user.is_authenticated or not user.is_active:
            return False
        if user.is_superuser:
            return True
        permission = getattr(view, "action_permissions", {}).get(
            getattr(view, "action", "")
        ) or getattr(view, "permission_code", None)
        return bool(permission and permission in access.get_effective_permissions(user))


class CompanyScopedMixin:
    def require_company(self, request: Request, company: Any, permission: str) -> None:
        if not access.has_permission(
            user=cast(User, request.user), permission=permission, company=company
        ):
            raise PermissionDenied("Company-scoped finance permission required.")


class AccountViewSet(
    CompanyScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet[Any],
):
    permission_classes = [FinancePermission]
    permission_code = "finance.manage_chart_of_accounts"
    serializer_class: Any = AccountSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):  # type: ignore[no-untyped-def]
        user = cast(User, self.request.user)
        ids = access.get_fully_accessible_company_ids(user, permission=self.permission_code)
        return selectors.account_list().filter(company_id__in=ids)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.require_company(request, data["company"], self.permission_code)
        item = call(services.create_account, **data)
        return Response(AccountSerializer(item).data, status=status.HTTP_201_CREATED)


class FiscalYearViewSet(AccountViewSet):
    permission_code = "finance.manage_fiscal_periods"
    serializer_class = FiscalYearSerializer

    def get_queryset(self):  # type: ignore[no-untyped-def]
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self.permission_code
        )
        return selectors.fiscal_year_list().filter(company_id__in=ids)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.require_company(request, data["company"], self.permission_code)
        item = call(services.create_fiscal_year, **data)
        return Response(FiscalYearSerializer(item).data, status=status.HTTP_201_CREATED)


class PeriodViewSet(AccountViewSet):
    permission_code = "finance.manage_fiscal_periods"
    serializer_class = PeriodSerializer

    def get_queryset(self):  # type: ignore[no-untyped-def]
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=self.permission_code
        )
        return selectors.period_list().filter(company_id__in=ids)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fiscal_year = data.pop("fiscal_year")
        self.require_company(request, fiscal_year.company, self.permission_code)
        item = call(services.create_accounting_period, fiscal_year=fiscal_year, **data)
        return Response(PeriodSerializer(item).data, status=status.HTTP_201_CREATED)

    def workflow(self, request: Request, function: Any) -> Response:
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            PeriodSerializer(
                call(
                    function,
                    period=self.get_object(),
                    actor=request.user,
                    **serializer.validated_data,
                )
            ).data
        )

    @action(detail=True, methods=["post"], url_path="soft-close")
    def soft_close(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            PeriodSerializer(
                call(
                    services.soft_close_accounting_period,
                    period=self.get_object(),
                    actor=request.user,
                )
            ).data
        )

    @action(detail=True, methods=["post"])
    def close(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return Response(
            PeriodSerializer(
                call(services.close_accounting_period, period=self.get_object(), actor=request.user)
            ).data
        )

    @action(detail=True, methods=["post"])
    def reopen(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.workflow(request, services.reopen_accounting_period)


class JournalViewSet(
    CompanyScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet[Any],
):
    permission_classes = [FinancePermission]
    http_method_names = ["get", "post", "head", "options"]
    action_permissions = {
        "list": "finance.create_journal",
        "retrieve": "finance.create_journal",
        "create": "finance.create_journal",
        "submit": "finance.create_journal",
        "approve": "finance.approve_journal",
        "reject": "finance.approve_journal",
        "post": "finance.post_journal",
        "reverse": "finance.reverse_journal",
    }

    def get_queryset(self):  # type: ignore[no-untyped-def]
        permission = self.action_permissions.get(self.action, "finance.create_journal")
        ids = access.get_fully_accessible_company_ids(
            cast(User, self.request.user), permission=permission
        )
        return selectors.journal_list().filter(company_id__in=ids)

    def get_serializer_class(self) -> Any:
        return JournalWriteSerializer if self.action == "create" else JournalReadSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = JournalWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        self.require_company(request, data["company"], "finance.create_journal")
        item = call(services.create_journal, created_by=request.user, **data)
        return Response(JournalReadSerializer(item).data, status=status.HTTP_201_CREATED)

    def run(self, request: Request, function: Any, serializer_class: Any = None) -> Response:
        data = {}
        if serializer_class:
            serializer = serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
        return Response(
            JournalReadSerializer(
                call(function, journal=self.get_object(), actor=request.user, **data)
            ).data
        )

    @action(detail=True, methods=["post"])
    def submit(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.run(request, services.submit_journal)

    @action(detail=True, methods=["post"])
    def approve(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.run(request, services.approve_journal)

    @action(detail=True, methods=["post"])
    def reject(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.run(request, services.reject_journal, ReasonSerializer)

    @action(detail=True, methods=["post"])
    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.run(request, services.post_journal)

    @action(detail=True, methods=["post"])
    def reverse(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        return self.run(request, services.reverse_journal, ReversalSerializer)


class TrialBalanceResponseSerializer(serializers.Serializer[Any]):
    """Schema marker for calculated trial-balance rows."""


class TrialBalanceView(APIView):
    serializer_class = TrialBalanceResponseSerializer
    permission_classes = [FinancePermission]
    permission_code = "finance.view_financial_reports"

    def get(self, request: Request) -> Response:
        company = request.query_params.get("company")
        ids = access.get_fully_accessible_company_ids(
            cast(User, request.user), permission=self.permission_code
        )
        if not company or company not in {str(item) for item in ids}:
            raise PermissionDenied()
        return Response(selectors.trial_balance(company_id=company))  # type: ignore[arg-type]
