from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

from django.core.cache import cache
from django.db import models
from django.http import Http404
from django.utils import timezone
from rest_framework import decorators, permissions, response, serializers, viewsets

from dsms.identity import access
from dsms.identity.models import User
from dsms.identity.permissions import HasRBACPermission
from dsms.organization.models import Company

from ..models import AnalyticsDataQualityIssue, AnalyticsMetricDefinition, DashboardDefinition
from ..services import calculate_metric, evaluate_kpi_health
from .serializers import DataQualityIssueSerializer, MetricDefinitionSerializer


def _company_for(request: Any) -> Company:
    company_id = request.query_params.get("company")
    if not company_id or company_id not in {
        str(value)
        for value in access.get_accessible_company_ids(
            request.user, permission="analytics.view_executive_dashboard"
        )
    }:
        raise Http404
    return Company.objects.get(pk=company_id)


class MetricCatalogViewSet(viewsets.ReadOnlyModelViewSet[AnalyticsMetricDefinition]):
    queryset = AnalyticsMetricDefinition.objects.filter(is_active=True).order_by("category", "code")
    serializer_class = MetricDefinitionSerializer
    permission_classes = [permissions.IsAuthenticated, HasRBACPermission]
    lookup_field = "code"
    search_fields = ["code", "name", "description"]
    filterset_fields = ["category", "value_type", "direction"]

    @decorators.action(detail=True, methods=["get"])
    def trend(self, request: Any, code: str | None = None) -> response.Response:
        metric = self.get_object()
        company = _company_for(request)
        date_from = date.fromisoformat(request.query_params["date_from"])
        date_to = date.fromisoformat(request.query_params["date_to"])
        points = []
        cursor = date_from
        while cursor <= date_to:
            end = min(cursor + timedelta(days=30) - timedelta(days=1), date_to)
            result = calculate_metric(
                metric_definition=metric, period_start=cursor, period_end=end, company=company
            )
            points.append(
                {
                    "period_start": cursor,
                    "period_end": end,
                    "value": result.value,
                    "unit": result.unit,
                    "data_quality": result.data_quality,
                    "source_count": result.source_count,
                    "warnings": result.warnings,
                }
            )
            cursor = end + timedelta(days=1)
        return response.Response(points)


class ExecutiveSummarySerializer(serializers.Serializer[Any]):
    """Schema marker for configured dashboard payloads with dynamic sections."""


class ExecutiveViewSet(viewsets.ViewSet):
    serializer_class = ExecutiveSummarySerializer
    permission_classes = [permissions.IsAuthenticated]

    def _summary(self, request: Any, dashboard_code: str) -> response.Response:
        company = _company_for(request)
        today = timezone.localdate()
        start = today.replace(day=1)
        cache_key = f"analytics:v1:{request.user.id}:{company.id}:{dashboard_code}:{start}:{today}"
        cached = cache.get(cache_key)
        if cached is not None:
            return response.Response(cached)
        dashboard = (
            DashboardDefinition.objects.filter(
                company__in=[company, None], code=dashboard_code, is_active=True
            )
            .prefetch_related("widgets__kpi__metric_definition")
            .first()
        )
        if dashboard is None:
            return response.Response({"sections": {}, "warnings": ["Dashboard is not configured."]})
        sections: dict[str, list[dict[str, Any]]] = {}
        for widget in dashboard.widgets.all():
            definition = widget.kpi.metric_definition
            result = calculate_metric(
                metric_definition=definition, period_start=start, period_end=today, company=company
            )
            value = result.value
            numeric = Decimal(value) if isinstance(value, (int, Decimal)) else None
            sections.setdefault(definition.category.lower(), []).append(
                {
                    "code": definition.code,
                    "label": widget.title,
                    "value": value,
                    "value_type": definition.value_type,
                    "unit": result.unit,
                    "currency": definition.currency or None,
                    "period": {"start": start, "end": today},
                    "comparison": None,
                    "absolute_change": None,
                    "percentage_change": None,
                    "health_status": evaluate_kpi_health(kpi=widget.kpi, value=numeric),
                    "data_quality": result.data_quality,
                    "warnings": result.warnings,
                    "drilldown": widget.drilldown_path or None,
                }
            )
        payload = {"as_of": timezone.now(), "sections": sections}
        cache.set(cache_key, payload, timeout=120)
        return response.Response(payload)

    @decorators.action(detail=False, methods=["get"])
    def summary(self, request: Any) -> response.Response:
        return self._summary(request, "CEO")

    @decorators.action(detail=False, methods=["get"])
    def today(self, request: Any) -> response.Response:
        return self._summary(request, "EXECUTIVE_TODAY")

    @decorators.action(detail=False, methods=["get"], url_path="financial-position")
    def financial_position(self, request: Any) -> response.Response:
        return self._summary(request, "FINANCIAL_POSITION")


class DataQualityViewSet(viewsets.ReadOnlyModelViewSet[AnalyticsDataQualityIssue]):
    serializer_class = DataQualityIssueSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["company", "status", "severity", "issue_code", "source_app"]

    def get_queryset(self) -> models.QuerySet[AnalyticsDataQualityIssue]:
        company_ids = access.get_accessible_company_ids(
            cast(User, self.request.user), permission="analytics.view_data_quality"
        )
        return AnalyticsDataQualityIssue.objects.filter(company_id__in=company_ids).select_related(
            "metric_definition", "branch", "client", "site"
        )

    @decorators.action(detail=False, methods=["get"])
    def summary(self, request: Any) -> response.Response:
        rows = self.get_queryset().values("status", "severity").annotate(count=models.Count("id"))
        return response.Response(list(rows))
