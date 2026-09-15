"""Session-only, zero-write HTTP transport for Foundation Analysis V1."""
from __future__ import annotations

import hashlib
from functools import wraps

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import DatabaseError
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers

from domain.services.analysis_contracts import (
    ERROR_MESSAGES,
    AnalysisError,
    canonical_bytes,
)
from domain.services.analysis_read_model import (
    comparison_snapshot,
    context_snapshot,
    matrix_snapshot,
    timeline_snapshot,
)


_SPOOF_HEADERS = frozenset({
    "HTTP_AUTHORIZATION", "HTTP_X_ACTOR", "HTTP_X_ACTOR_IDENTIFIER",
    "HTTP_X_ACTOR_TYPE", "HTTP_X_ROLE", "HTTP_X_PLAYER_ROLE",
    "HTTP_X_PLAYER_PERMISSIONS", "HTTP_X_STUDIO_ROLE",
    "HTTP_X_STUDIO_CAPABILITY", "HTTP_X_STUDIO_CAPABILITIES",
    "HTTP_X_PROJECT_ID", "HTTP_X_WORKSPACE_ID", "HTTP_X_CAPABILITIES",
    "HTTP_X_AUDIT_CONTEXT", "HTTP_X_SERVICE_CONTEXT", "HTTP_X_SERVICE_PURPOSE",
    "HTTP_X_EXPECTED_MANIFEST_HASH", "HTTP_X_HTTP_METHOD_OVERRIDE",
    "HTTP_IDEMPOTENCY_KEY", "HTTP_IF_MATCH",
})


def _response(payload: object, *, status: int = 200) -> HttpResponse:
    raw = canonical_bytes(payload)
    response = HttpResponse(
        raw,
        status=status,
        content_type="application/json; charset=utf-8",
    )
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["ETag"] = f'"{hashlib.sha256(raw).hexdigest()}"'
    response["Content-Length"] = str(len(raw))
    patch_vary_headers(response, ("Cookie",))
    return response


def _error(error: AnalysisError) -> HttpResponse:
    return _response(
        {"code": error.code, "errors": [ERROR_MESSAGES[error.code]]},
        status=error.status,
    )


def _clear_cookie_mutation(request: object, response: HttpResponse) -> None:
    request.META["CSRF_COOKIE_NEEDS_UPDATE"] = False
    session = getattr(request, "session", None)
    if session is not None:
        session.accessed = False
        session.modified = False
    response.cookies.clear()
    if response.has_header("Set-Cookie"):
        del response["Set-Cookie"]


def _endpoint(query_mode: str):
    def decorate(handler):
        @wraps(handler)
        def transport(request, **kwargs):
            response: HttpResponse | None = None
            try:
                if request.method != "GET":
                    response = _error(AnalysisError("ANALYSIS_REQUEST_INVALID", 405))
                    response["Allow"] = "GET"
                    return response
                if request.body or any(key in request.META for key in _SPOOF_HEADERS):
                    raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
                query = request.GET
                if query_mode == "none":
                    if query:
                        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
                    arguments = {}
                elif query_mode == "timeline":
                    expected = {"experiment_id", "actor_code", "element_code", "parameter_code"}
                    if set(query) != expected or any(len(query.getlist(key)) != 1 for key in expected):
                        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
                    arguments = {key: query[key] for key in expected}
                elif query_mode == "matrix":
                    expected = {"experiment_id", "time_slice_id", "parameter_code"}
                    if set(query) != expected or any(len(query.getlist(key)) != 1 for key in expected):
                        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
                    arguments = {key: query[key] for key in expected}
                elif query_mode == "comparison":
                    singleton = {"actor_code", "element_code", "parameter_code"}
                    if set(query) != singleton | {"experiment_id"}:
                        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
                    if any(len(query.getlist(key)) != 1 for key in singleton):
                        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
                    experiment_ids = query.getlist("experiment_id")
                    if len(experiment_ids) != 2:
                        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
                    arguments = {
                        **{key: query[key] for key in singleton},
                        "experiment_ids": experiment_ids,
                    }
                else:
                    raise AnalysisError("ANALYSIS_OPERATION_FAILED", 503)
                payload = handler(request, **kwargs, **arguments)
                response = _response(payload)
                return response
            except AnalysisError as exc:
                response = _error(exc)
                return response
            except RequestDataTooBig:
                response = _error(AnalysisError("ANALYSIS_REQUEST_INVALID", 400))
                return response
            except (DatabaseError, ValidationError, TypeError, ValueError, OverflowError, RecursionError):
                response = _error(AnalysisError("ANALYSIS_OPERATION_FAILED", 503))
                return response
            finally:
                if response is not None:
                    _clear_cookie_mutation(request, response)
        return transport
    return decorate


@_endpoint("none")
def context(request, project_id, workspace_id):
    return context_snapshot(
        user=request.user,
        project_id=project_id,
        workspace_id=workspace_id,
    )


@_endpoint("timeline")
def timeline(
    request, project_id, workspace_id,
    experiment_id, actor_code, element_code, parameter_code,
):
    return timeline_snapshot(
        user=request.user,
        project_id=project_id,
        workspace_id=workspace_id,
        experiment_id=experiment_id,
        actor_code=actor_code,
        element_code=element_code,
        parameter_code=parameter_code,
    )


@_endpoint("matrix")
def matrix(request, project_id, workspace_id, experiment_id, time_slice_id, parameter_code):
    return matrix_snapshot(
        user=request.user,
        project_id=project_id,
        workspace_id=workspace_id,
        experiment_id=experiment_id,
        time_slice_id=time_slice_id,
        parameter_code=parameter_code,
    )


@_endpoint("comparison")
def comparison(
    request, project_id, workspace_id,
    experiment_ids, actor_code, element_code, parameter_code,
):
    return comparison_snapshot(
        user=request.user,
        project_id=project_id,
        workspace_id=workspace_id,
        experiment_ids=experiment_ids,
        actor_code=actor_code,
        element_code=element_code,
        parameter_code=parameter_code,
    )
