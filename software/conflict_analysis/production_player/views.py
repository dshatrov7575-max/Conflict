"""Session-admitted composition; all scoped domain reads use Foundation HTTP."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from production_player.claim_boundaries import ClaimBoundaryContractError, load_claim_boundaries


def _secure(response: HttpResponse) -> HttpResponse:
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "same-origin"
    response["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-src 'self'"
    )
    return response


def _shell(request: HttpRequest, template: str, **context: str) -> HttpResponse:
    try:
        contract = load_claim_boundaries()
    except ClaimBoundaryContractError:
        return _secure(HttpResponse("PLAYER_CLAIM_BOUNDARY_CONTRACT_UNAVAILABLE\n", status=503))
    user = request.user
    admitted = bool(
        user.is_authenticated and user.is_active and not user.is_staff
        and not user.is_superuser and not request.headers.get("Authorization")
    )
    # Shell admission is not object authorization. No domain ORM/lifecycle reads;
    # Foundation independently reauthorizes every exact scoped browser request.
    statements = [dict(item) for item in contract.statements]
    return _secure(render(request, template, {
        "player_authenticated": admitted,
        "claim_contract": contract.contract,
        "claim_sha256": contract.sha256,
        "claim_statements": statements,
        "claim_by_code": {item["code"]: item["text"] for item in statements},
        **context,
    }, status=200 if admitted else 401 if not user.is_authenticated else 404))


@require_GET
@ensure_csrf_cookie
def entry(request: HttpRequest) -> HttpResponse:
    return _shell(request, "production_player/entry.html", player_page="entry")


@require_GET
@ensure_csrf_cookie
def project(request: HttpRequest, project_id: object) -> HttpResponse:
    return _shell(request, "production_player/project.html", player_page="project", project_id=str(project_id))


@require_GET
@ensure_csrf_cookie
def workspace(request: HttpRequest, workspace_id: object) -> HttpResponse:
    return _shell(request, "production_player/workspace.html", player_page="workspace", workspace_id=str(workspace_id))
