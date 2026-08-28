"""Server-rendered composition only; Foundation remains the sole data authority."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.http import require_GET

from production_studio.authoring_claim_boundaries import (
    AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256,
    AuthoringClaimBoundaryContractError,
    VerifiedAuthoringClaimBoundaries,
    load_authoring_claim_boundaries,
)
from production_studio.claim_boundaries import (
    CLAIM_BOUNDARY_CONTRACT_SHA256,
    ClaimBoundaryContractError,
    VerifiedClaimBoundaries,
    load_claim_boundaries,
)


def _claim_context(contract: VerifiedClaimBoundaries) -> dict[str, Any]:
    statements = [dict(statement) for statement in contract.statements]
    return {
        "claim_contract": contract.contract,
        "claim_contract_version": contract.version,
        "claim_sha256": contract.sha256,
        "claim_statements": statements,
        "claim_by_code": {item["code"]: item["text"] for item in statements},
    }


def _authoring_claim_context(
    contract: VerifiedAuthoringClaimBoundaries,
) -> dict[str, Any]:
    statements = [dict(statement) for statement in contract.statements]
    return {
        "authoring_claim_contract": contract.contract,
        "authoring_claim_contract_version": contract.version,
        "authoring_claim_payload_bytes": len(contract.payload),
        "authoring_claim_sha256": contract.sha256,
        "authoring_claim_statements": statements,
        "authoring_claim_by_code": {
            item["code"]: item["text"] for item in statements
        },
    }


def _contract_failure() -> HttpResponse:
    response = HttpResponse(
        "STUDIO_CLAIM_BOUNDARY_CONTRACT_UNAVAILABLE\n",
        status=503,
        content_type="text/plain; charset=utf-8",
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _authoring_contract_failure() -> HttpResponse:
    response = HttpResponse(
        "STUDIO_AUTHORING_CLAIM_BOUNDARY_CONTRACT_UNAVAILABLE\n",
        status=503,
        content_type="text/plain; charset=utf-8",
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _verified_contract() -> VerifiedClaimBoundaries | None:
    try:
        return load_claim_boundaries()
    except ClaimBoundaryContractError:
        return None


def _verified_authoring_contract() -> VerifiedAuthoringClaimBoundaries | None:
    try:
        return load_authoring_claim_boundaries()
    except AuthoringClaimBoundaryContractError:
        return None


def _render_shell(
    request: HttpRequest,
    template_name: str,
    context: dict[str, Any] | None = None,
) -> HttpResponse:
    contract = _verified_contract()
    if contract is None:
        return _contract_failure()
    authenticated = bool(request.user.is_authenticated)
    response = render(
        request,
        template_name,
        {
            **_claim_context(contract),
            **(context or {}),
            "studio_authenticated": authenticated,
        },
        status=200 if authenticated else 401,
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _render_authoring_shell(
    request: HttpRequest,
    template_name: str,
    context: dict[str, Any] | None = None,
) -> HttpResponse:
    contract = _verified_authoring_contract()
    if contract is None:
        return _authoring_contract_failure()
    authenticated = bool(request.user.is_authenticated)
    if authenticated:
        get_token(request)
    response = render(
        request,
        template_name,
        {
            **_authoring_claim_context(contract),
            **(context or {}),
            "studio_authenticated": authenticated,
        },
        status=200 if authenticated else 401,
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def entry(request: HttpRequest) -> HttpResponse:
    """Render a credential-free exact-definition entry for a pre-issued session."""

    return _render_shell(request, "production_studio/entry.html")


@require_GET
def definition(request: HttpRequest, definition_id: object) -> HttpResponse:
    """Render the read-only shell; JavaScript performs verified Foundation GETs."""

    identifier = str(definition_id)
    return _render_shell(
        request,
        "production_studio/definition.html",
        {
            "definition_id": identifier,
            "foundation_open_url": f"/api/foundation/definitions/{identifier}/",
            "foundation_export_url": (
                f"/api/foundation/definitions/{identifier}/package/2.1/"
            ),
        },
    )


@require_GET
def audited_draft_entry(request: HttpRequest) -> HttpResponse:
    """Render the C1 pre-issued-session entry and exact bootstrap composition."""

    return _render_authoring_shell(
        request,
        "production_studio/audited_draft_entry.html",
        {
            "foundation_bootstrap_url": (
                "/api/foundation/projects/bootstrap-first-draft/"
            ),
            "audited_draft_definition_base": "/studio/drafts/definitions/",
        },
    )


@require_GET
def audited_draft_definition(
    request: HttpRequest,
    definition_id: object,
) -> HttpResponse:
    """Render the C1 shell; JavaScript composes only canonical Foundation HTTP."""

    identifier = str(definition_id)
    return _render_authoring_shell(
        request,
        "production_studio/audited_draft_definition.html",
        {
            "definition_id": identifier,
            "foundation_open_url": f"/api/foundation/definitions/{identifier}/",
            "foundation_save_url": (
                f"/api/foundation/definitions/{identifier}/draft/"
            ),
            "foundation_validation_preview_url": (
                f"/api/foundation/definitions/{identifier}/validation-preview/"
            ),
            "foundation_help_base": "/api/foundation/help/",
        },
    )


@require_GET
def claim_boundaries_read_only_v1(request: HttpRequest) -> HttpResponse:
    """Return the public immutable contract without touching auth or session state."""

    contract = _verified_contract()
    if contract is None:
        return _contract_failure()
    response = HttpResponse(
        contract.payload,
        content_type="application/json; charset=utf-8",
    )
    response["Content-Length"] = str(len(contract.payload))
    response["ETag"] = f'"{CLAIM_BOUNDARY_CONTRACT_SHA256}"'
    response["Cache-Control"] = (
        "public, max-age=31536000, immutable, no-transform"
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
def claim_boundaries_audited_draft_v1(request: HttpRequest) -> HttpResponse:
    """Return public immutable C1 claim bytes without auth or session mutation."""

    contract = _verified_authoring_contract()
    if contract is None:
        return _authoring_contract_failure()
    response = HttpResponse(
        contract.payload,
        content_type="application/json; charset=utf-8",
    )
    response["Content-Length"] = str(len(contract.payload))
    response["ETag"] = f'"{AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256}"'
    response["Cache-Control"] = (
        "public, max-age=31536000, immutable, no-transform"
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response
