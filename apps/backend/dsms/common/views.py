from typing import Any

from django.db import connection
from django.db.utils import DatabaseError
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE


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
