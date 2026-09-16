"""Session/CSRF-only Foundation Geography transport; bounded public errors."""
import json
from functools import wraps

from django.core.exceptions import RequestDataTooBig, ValidationError
from django.db import DatabaseError
from django.http import HttpResponse
from django.middleware.csrf import get_token
from django.utils.cache import patch_vary_headers
from django.views.decorators.csrf import csrf_exempt
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied

from domain.services.analysis_contracts import canonical_bytes, sha256
from domain.services.geography import (
    MESSAGES, GeographyError, admit, create_project_location_revision, invalid,
    read_project_location, read_project_location_history,
)


def response(payload, status=200):
    raw = canonical_bytes(payload)
    result = HttpResponse(raw, status=status, content_type="application/json; charset=utf-8")
    result["Cache-Control"] = "no-store"
    result["Content-Length"] = str(len(raw))
    result["X-Content-Type-Options"] = "nosniff"
    result["ETag"] = f'"{payload.get("etag_sha256", sha256(payload))}"'
    patch_vary_headers(result, ("Cookie",))
    return result


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            invalid()
        result[key] = value
    return result


def endpoint(method):
    def decorate(handler):
        @csrf_exempt  # CSRF is explicitly enforced *after* authorization below.
        @wraps(handler)
        def transport(request, project_id):
            try:
                admit(user=request.user, project_id=project_id, write=request.method == "POST")
                if request.method != method:
                    result = response({"code": "GEOGRAPHY_REQUEST_INVALID", "errors": [MESSAGES["GEOGRAPHY_REQUEST_INVALID"]]}, 405)
                    result["Allow"] = method
                    return result
                spoof = ("HTTP_AUTHORIZATION", "HTTP_X_ACTOR", "HTTP_X_ACTOR_IDENTIFIER", "HTTP_X_ROLE", "HTTP_X_CAPABILITIES", "HTTP_X_HTTP_METHOD_OVERRIDE", "HTTP_IDEMPOTENCY_KEY")
                if any(header in request.META for header in spoof):
                    invalid()
                if method == "POST":
                    try:
                        SessionAuthentication().enforce_csrf(request)
                    except PermissionDenied as exc:
                        raise GeographyError("GEOGRAPHY_PERMISSION_DENIED", 403) from exc
                    if request.GET or request.content_type != "application/json" or len(request.body) > 16384:
                        invalid()
                    try:
                        body = json.loads(request.body.decode("utf-8"), object_pairs_hook=pairs, parse_constant=lambda _: invalid())
                    except (UnicodeError, ValueError, RecursionError):
                        invalid()
                    result, replayed = create_project_location_revision(
                        user=request.user, project_id=project_id, body=body,
                        if_match=request.headers.get("If-Match"), operation_id=request.headers.get("X-Operation-ID"),
                    )
                    return response(result, 200 if replayed else 201)
                if request.body or "HTTP_IF_MATCH" in request.META or "HTTP_X_OPERATION_ID" in request.META:
                    invalid()
                payload = handler(request, project_id)
                get_token(request)
                return response(payload)
            except GeographyError as exc:
                return response({"code": exc.code, "errors": [MESSAGES[exc.code]]}, exc.status)
            except RequestDataTooBig:
                return response({"code": "GEOGRAPHY_REQUEST_INVALID", "errors": [MESSAGES["GEOGRAPHY_REQUEST_INVALID"]]}, 400)
            except (DatabaseError, ValidationError, ValueError, TypeError, KeyError, OSError):
                return response({"code": "GEOGRAPHY_OPERATION_FAILED", "errors": [MESSAGES["GEOGRAPHY_OPERATION_FAILED"]]}, 503)
        return transport
    return decorate


@endpoint("GET")
def location(request, project_id):
    if request.GET:
        invalid()
    return read_project_location(user=request.user, project_id=project_id)


@endpoint("GET")
def history(request, project_id):
    if set(request.GET) - {"limit"} or len(request.GET.getlist("limit")) > 1:
        invalid()
    raw = request.GET.get("limit", "50")
    if not raw.isascii() or not raw.isdecimal() or not 1 <= len(raw) <= 3:
        invalid()
    return read_project_location_history(user=request.user, project_id=project_id, limit=int(raw))


@endpoint("POST")
def revisions(request, project_id):
    raise AssertionError("POST is handled by the admitted transport")
