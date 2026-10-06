from functools import wraps
from uuid import uuid4

from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, ValidationError
from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie

from calculation import CalculationInputError
from domain.services.player_experiments import (
    PlayerExperimentError, assessment_principal,
)
from domain.services.player_workspaces import PlayerError, canonical_receipt_bytes

from .inputs import MAX_BODY_BYTES, ExperimentForm, WeightForm, weights_from_json
from .quality import quality_ui
from .receipts import (
    get_calculation_receipt, list_calculation_receipts, parse_operation_id,
)
from .services import (
    calculate_and_record_experiment, capture_for_player, open_experiment, time_slices,
)

_SPOOF_HEADERS = {
    "HTTP_AUTHORIZATION", "HTTP_X_ACTOR", "HTTP_X_ACTOR_IDENTIFIER", "HTTP_X_ACTOR_TYPE",
    "HTTP_X_ROLE", "HTTP_X_PLAYER_ROLE", "HTTP_X_PLAYER_PERMISSIONS", "HTTP_X_STUDIO_ROLE",
    "HTTP_X_STUDIO_CAPABILITY", "HTTP_X_STUDIO_CAPABILITIES", "HTTP_X_PROJECT_ID",
    "HTTP_X_WORKSPACE_ID", "HTTP_X_CAPABILITIES", "HTTP_X_AUDIT_CONTEXT",
    "HTTP_X_SERVICE_CONTEXT", "HTTP_X_SERVICE_PURPOSE", "HTTP_X_EXPECTED_MANIFEST_HASH",
    "HTTP_X_HTTP_METHOD_OVERRIDE", "HTTP_IDEMPOTENCY_KEY", "HTTP_IF_MATCH",
}


def _secure(response):
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "same-origin"
    response["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    patch_vary_headers(response, ("Cookie",))
    return response


def _error(code, status):
    return JsonResponse({"code": code, "errors": ["Запрос не выполнен."]}, status=status)


def _canonical_response(payload, *, status=200):
    raw = canonical_receipt_bytes(payload)
    response = HttpResponse(raw, status=status, content_type="application/json; charset=utf-8")
    response["Content-Length"] = str(len(raw))
    return response


def _receipt_headers(response, receipt):
    response["X-Calculation-Receipt-ID"] = str(receipt.payload["operation_id"])
    response["X-Calculation-Receipt-Replayed"] = "true" if receipt.replayed else "false"
    return response


def _endpoint(methods, *, allow_idempotency=False):
    def decorate(handler):
        @wraps(handler)
        def wrapped(request, **kwargs):
            try:
                if request.method not in methods:
                    response = _error("PLAYER_METHOD_NOT_ALLOWED", 405)
                    response["Allow"] = ", ".join(methods)
                    return _secure(response)
                assessment_principal(request.user)
                forbidden = _SPOOF_HEADERS - ({"HTTP_IDEMPOTENCY_KEY"} if allow_idempotency else set())
                if any(key in request.META for key in forbidden):
                    raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
                response = handler(request, **kwargs)
            except (PlayerExperimentError, PlayerError) as exc:
                response = _error(exc.code, exc.status)
            except (CalculationInputError, RequestDataTooBig, TooManyFieldsSent):
                response = _error("PLAYER_CALCULATION_INPUT_INVALID", 400)
            except (DatabaseError, ValidationError):
                response = _error("PLAYER_OPERATION_FAILED", 503)
            return _secure(response)
        return wrapped
    return decorate


@_endpoint(["GET"])
def start(request):
    if request.body or set(request.GET) - {"experiment_id"} or any(
        len(request.GET.getlist(key)) != 1 for key in request.GET
    ):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    form = ExperimentForm(request.GET or None)
    if form.is_bound and form.is_valid():
        return redirect("player_integration:experiment", experiment_id=form.cleaned_data["experiment_id"])
    return render(request, "player_integration/start.html", {"form": form})


@_endpoint(["GET"])
def experiment(request, experiment_id):
    if request.GET or request.body:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    selected, slices = time_slices(user=request.user, experiment_id=experiment_id)
    return render(request, "player_integration/experiment.html", {"experiment": selected, "slices": slices})


@_endpoint(["GET", "POST"], allow_idempotency=True)
@csrf_protect
@ensure_csrf_cookie
def result(request, experiment_id, time_slice_id):
    # Object access is checked even for malformed payloads, before reading them.
    open_experiment(user=request.user, experiment_id=experiment_id)
    if request.GET:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    if request.method == "GET" and "HTTP_IDEMPOTENCY_KEY" in request.META:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    if request.method == "POST":
        # CSRF middleware may already have parsed multipart. Reject unsupported
        # media before accessing its consumed stream; never turn it into a 500.
        if request.content_type not in {"application/json", "application/x-www-form-urlencoded"}:
            return _error("PLAYER_REQUEST_INVALID", 415)
        length = request.META.get("CONTENT_LENGTH", "")
        if length and (not length.isascii() or not length.isdigit() or len(length) > 8
                       or int(length) > MAX_BODY_BYTES):
            raise CalculationInputError("Invalid body size.")
        if len(request.body) > MAX_BODY_BYTES:
            raise CalculationInputError("Invalid body size.")
        if request.content_type == "application/json":
            operation_id = parse_operation_id(request.META.get("HTTP_IDEMPOTENCY_KEY"))
            weights = weights_from_json(request.body)
            view, receipt = calculate_and_record_experiment(
                user=request.user, experiment_id=experiment_id,
                time_slice_id=time_slice_id, beta_weights=weights,
                operation_id=operation_id,
            )
            return _receipt_headers(
                _canonical_response(view.as_dict(receipt=receipt)), receipt,
            )
    elif request.body:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    selected, snapshot = capture_for_player(
        user=request.user, experiment_id=experiment_id, time_slice_id=time_slice_id,
    )
    form = WeightForm(snapshot, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        view, receipt = calculate_and_record_experiment(
            user=request.user, experiment_id=experiment_id,
            time_slice_id=time_slice_id, beta_weights=form.beta_weights,
            operation_id=form.cleaned_data["operation_id"],
        )
        from scenario_modeling.session import from_result
        payload = view.as_dict(receipt=receipt)
        response = render(request, "player_integration/result.html", {
            **payload,
            "quality_ui": quality_ui(payload["quality"]),
            "snapshot_json": view.snapshot.to_json(),
            "run_json": view.run.to_json(),
            "receipt_json": canonical_receipt_bytes(receipt.payload).decode("utf-8"),
            "scenario_token": from_result(request, view),
            "scenario_operation_id": uuid4(),
        })
        return _receipt_headers(response, receipt)
    return render(request, "player_integration/inputs.html", {
        "experiment": selected, "snapshot": snapshot, "form": form, "rows": form.rows(),
    }, status=400 if form.is_bound else 200)


@_endpoint(["GET"])
def receipts(request, experiment_id):
    if request.GET or request.body:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    selected = open_experiment(user=request.user, experiment_id=experiment_id)
    return _canonical_response(list_calculation_receipts(user=request.user, experiment=selected))


@_endpoint(["GET"])
def receipt(request, experiment_id, operation_id):
    if request.GET or request.body:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    selected = open_experiment(user=request.user, experiment_id=experiment_id)
    return _canonical_response(get_calculation_receipt(
        user=request.user, experiment=selected, operation_id=operation_id,
    ))
