from typing import Any

from django.core.cache import cache
from django.db import connection
from django.db.utils import DatabaseError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE


@extend_schema(
    responses=inline_serializer(
        name="HealthResponse",
        fields={
            "status": serializers.CharField(),
            "database": serializers.CharField(),
        },
    )
)
@api_view(["GET"])
def health_check(request: Any) -> Response:
    """Report application and database availability without exposing internals."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return Response(
            {"status": "unavailable", "database": "unavailable"},
            status=HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"status": "ok", "database": "ok"}, status=HTTP_200_OK)


@extend_schema(
    responses=inline_serializer(
        name="ReadinessResponse",
        fields={
            "status": serializers.CharField(),
            "database": serializers.CharField(),
            "redis": serializers.CharField(),
        },
    )
)
@api_view(["GET"])
def readiness_check(request: Any) -> Response:
    """Check required request-serving dependencies without exposing connection details."""
    database_status = "ok"
    redis_status = "ok"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        database_status = "unavailable"
    try:
        cache.set("health:ready", "ok", timeout=10)
        if cache.get("health:ready") != "ok":
            redis_status = "unavailable"
    except Exception:  # Cache backends raise provider-specific connection errors.
        redis_status = "unavailable"
    ready = database_status == redis_status == "ok"
    return Response(
        {
            "status": "ok" if ready else "unavailable",
            "database": database_status,
            "redis": redis_status,
        },
        status=HTTP_200_OK if ready else HTTP_503_SERVICE_UNAVAILABLE,
    )
