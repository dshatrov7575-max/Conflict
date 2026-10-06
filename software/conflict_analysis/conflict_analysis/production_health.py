"""Minimal production readiness endpoint with a live database check."""

from __future__ import annotations

from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_GET


def _plain(body: str, *, status: int) -> HttpResponse:
    response = HttpResponse(body, status=status, content_type="text/plain; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def ready(request: HttpRequest) -> HttpResponse:
    del request
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            row = cursor.fetchone()
        if row != (1,):
            return _plain("NOT_READY\n", status=503)
    except DatabaseError:
        return _plain("NOT_READY\n", status=503)
    return _plain("READY\n", status=200)
