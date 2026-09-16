"""Read-only method-safe Analysis V1 shell.

The Product shell performs no domain ORM reads.  Every object and value is
reauthorized by Foundation Analysis HTTP endpoints.
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET


def _secure(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "same-origin"
    response["X-Frame-Options"] = "DENY"
    response["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'; worker-src 'self'"
    )
    return response


def _shell(request: HttpRequest, *, project_id: object | None = None,
           workspace_id: object | None = None) -> HttpResponse:
    user = request.user
    admitted = bool(
        user.is_authenticated and user.is_active
        and not user.is_staff and not user.is_superuser
        and not request.headers.get("Authorization")
    )
    response = render(
        request,
        "analysis_dashboard/analytics.html",
        {
            "analysis_authenticated": admitted,
            "project_id": str(project_id or ""),
            "workspace_id": str(workspace_id or ""),
        },
        status=200 if admitted else 401 if not user.is_authenticated else 404,
    )
    session = getattr(request, "session", None)
    if session is not None:
        session.accessed = False
        session.modified = False
    response.cookies.clear()
    return _secure(response)


@require_GET
def entry(request: HttpRequest) -> HttpResponse:
    return _shell(request)


@require_GET
def workspace(
    request: HttpRequest,
    project_id: object,
    workspace_id: object,
) -> HttpResponse:
    return _shell(request, project_id=project_id, workspace_id=workspace_id)
