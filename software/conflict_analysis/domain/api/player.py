"""Session-only Foundation Player HTTP admission and canonical byte responses."""

from __future__ import annotations

import hashlib
import json
import re
from functools import wraps

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import DatabaseError
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.utils.cache import patch_vary_headers
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied

from domain.services.foundation_packages import RawJSONError, validate_json_content_type
from domain.services.player_help_catalog import PlayerHelpCatalogError
from domain.services.player_projection import AssessmentProjectionError
from domain.services.player_workspaces import (
    PLAYER_ERROR_MESSAGES, PlayerError, admit_player_scope, canonical_receipt_bytes,
    create_player_time_slice, create_player_workspace, list_player_definitions,
    list_player_experiments, list_player_time_slices, list_player_workspaces,
    open_player_definition, open_player_workspace, player_help,
)


_MAX_BODY_BYTES = 65536
_SPOOF_HEADERS = frozenset({
    "HTTP_X_ACTOR", "HTTP_X_ACTOR_IDENTIFIER", "HTTP_X_ACTOR_TYPE",
    "HTTP_X_ROLE", "HTTP_X_PLAYER_ROLE", "HTTP_X_PLAYER_PERMISSIONS",
    "HTTP_X_STUDIO_ROLE", "HTTP_X_STUDIO_CAPABILITY", "HTTP_X_STUDIO_CAPABILITIES",
    "HTTP_X_PROJECT_ID", "HTTP_X_WORKSPACE_ID", "HTTP_X_CAPABILITIES",
    "HTTP_X_AUDIT_CONTEXT", "HTTP_X_SERVICE_CONTEXT", "HTTP_X_SERVICE_PURPOSE",
    "HTTP_X_EXPECTED_MANIFEST_HASH", "HTTP_X_HTTP_METHOD_OVERRIDE",
})


class _PlayerSessionAuthentication(SessionAuthentication):
    """Acquire the existing session only; scope admission precedes real CSRF.

    Every admitted POST below calls the inherited enforce_csrf on the original
    Django request, before reading/parsing its JSON and before any service write.
    DRF's view wrapper handles middleware exemption; no token comparison or
    alternate Basic/bearer mode is implemented here.
    """

    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if user is None or not user.is_active:
            return None
        return user, None


def _response(payload=None, *, status=200, body=None):
    raw = canonical_receipt_bytes(payload) if body is None else body
    response = HttpResponse(raw, status=status, content_type="application/json; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["ETag"] = f'"{hashlib.sha256(raw).hexdigest()}"'
    response["Content-Length"] = str(len(raw))
    patch_vary_headers(response, ("Cookie",))
    return response


def _error(error):
    return _response({"code": error.code, "errors": [PLAYER_ERROR_MESSAGES[error.code]]},
                     status=error.status)


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON number")


def _body(request):
    length = request.META.get("CONTENT_LENGTH", "")
    if length and (
        not str(length).isascii() or not str(length).isdigit()
        or len(str(length)) > 8 or int(length) > _MAX_BODY_BYTES
    ):
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    raw = request.body
    if not raw or len(raw) > _MAX_BODY_BYTES:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_object,
                             parse_constant=_reject_constant)
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400) from exc
    if type(payload) is not dict:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    return payload


def _endpoint(*, methods, scope, identity_key, is_help=False):
    def decorate(handler):
        @api_view(methods)
        @authentication_classes((_PlayerSessionAuthentication,))
        @permission_classes(())
        def admitted(request, **kwargs):
            try:
                # This read admission cannot access AuditEvent/idempotency state.
                admit_player_scope(user=request.user, kind=scope, identity=kwargs[identity_key])
                raw = request._request
                if any(key in raw.META for key in _SPOOF_HEADERS) or raw.META.get("HTTP_AUTHORIZATION"):
                    raise PlayerError("PLAYER_REQUEST_INVALID", 400)
                if is_help:
                    if set(raw.GET) != {"locale", "version"} or any(
                        len(raw.GET.getlist(key)) != 1 for key in raw.GET
                    ):
                        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
                    if (
                        raw.GET["locale"] != "ru"
                        or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", raw.GET["version"]) is None
                        or len(raw.GET["version"]) > 64 or len(kwargs["ui_key"]) > 255
                    ):
                        raise PlayerError("PLAYER_NOT_FOUND", 404)
                elif raw.GET:
                    raise PlayerError("PLAYER_REQUEST_INVALID", 400)
                if raw.method == "POST":
                    # Real Django cookie/header/origin enforcement, never bypassed.
                    try:
                        SessionAuthentication().enforce_csrf(raw)
                    except PermissionDenied as exc:
                        raise PlayerError("PLAYER_CSRF_FAILED", 403) from exc
                    body = _body(raw)
                    result = handler(request, body=body, **kwargs)
                    return _response(body=result.body, status=200 if result.replayed else 201)
                if raw.body or "HTTP_IDEMPOTENCY_KEY" in raw.META or "HTTP_IF_MATCH" in raw.META:
                    raise PlayerError("PLAYER_REQUEST_INVALID", 400)
                payload = handler(request, **kwargs)
                # A successful, scoped GET may issue/refresh the CSRF cookie.
                # This is session transport state, never a domain-table write.
                get_token(raw)
                return _response(payload)
            except PlayerError as exc:
                return _error(exc)
            except RequestDataTooBig:
                return _error(PlayerError("PLAYER_REQUEST_INVALID", 400))
            except PlayerHelpCatalogError:
                return _error(PlayerError("PLAYER_HELP_CATALOG_CONFLICT"))
            except AssessmentProjectionError as exc:
                code = exc.code if exc.code in {
                    "ASSESSMENT_PROJECTION_NOT_PROVEN", "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT",
                } else "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT"
                return _error(PlayerError(code))
            except (DatabaseError, ValidationError):
                # Preserve a bounded non-success outcome, with transactions already
                # unwound. Do not disclose database/model exception text.
                return _error(PlayerError("PLAYER_OPERATION_FAILED", 503))

        @wraps(handler)
        def transport(request, **kwargs):
            # Method/media admission is outside DRF authentication and body parsing.
            if request.method not in methods:
                response = _error(PlayerError("PLAYER_METHOD_NOT_ALLOWED", 405))
                response["Allow"] = ", ".join(methods)
                return response
            if request.method == "POST":
                try:
                    validate_json_content_type(str(request.META.get("CONTENT_TYPE", "")))
                except RawJSONError:
                    return _error(PlayerError("PLAYER_REQUEST_INVALID", 400))
            return admitted(request, **kwargs)

        # Retain DRF's standard wrapper flag, so the one explicit session CSRF
        # enforcement above occurs after object scope, not before admission.
        transport.csrf_exempt = admitted.csrf_exempt
        return transport
    return decorate


def _write_headers(request):
    return {"operation_id": request.META.get("HTTP_IDEMPOTENCY_KEY"),
            "if_match": request.META.get("HTTP_IF_MATCH")}


@_endpoint(methods=["GET"], scope="project", identity_key="project_id")
def definitions(request, project_id):
    return list_player_definitions(user=request.user, project_id=project_id)


@_endpoint(methods=["GET"], scope="definition", identity_key="definition_id")
def definition(request, definition_id):
    return open_player_definition(user=request.user, definition_id=definition_id)


@_endpoint(methods=["GET", "POST"], scope="project", identity_key="project_id")
def workspaces(request, project_id, body=None):
    if request.method == "POST":
        return create_player_workspace(user=request.user, project_id=project_id, body=body,
                                       **_write_headers(request))
    return list_player_workspaces(user=request.user, project_id=project_id)


@_endpoint(methods=["GET"], scope="workspace", identity_key="workspace_id")
def workspace(request, workspace_id):
    return open_player_workspace(user=request.user, workspace_id=workspace_id)


@_endpoint(methods=["GET", "POST"], scope="workspace", identity_key="workspace_id")
def time_slices(request, workspace_id, body=None):
    if request.method == "POST":
        return create_player_time_slice(user=request.user, workspace_id=workspace_id, body=body,
                                        **_write_headers(request))
    return list_player_time_slices(user=request.user, workspace_id=workspace_id)


@_endpoint(methods=["GET"], scope="workspace", identity_key="workspace_id")
def experiments(request, workspace_id):
    return list_player_experiments(user=request.user, workspace_id=workspace_id)


@_endpoint(methods=["GET"], scope="workspace", identity_key="workspace_id", is_help=True)
def help_topic(request, workspace_id, ui_key):
    return player_help(user=request.user, workspace_id=workspace_id, ui_key=ui_key,
                       locale=request.GET["locale"], version=request.GET["version"])
