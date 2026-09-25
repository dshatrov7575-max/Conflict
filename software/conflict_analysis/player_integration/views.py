"""Session/CSRF-protected HTML and JSON composition without result storage."""
from functools import wraps

from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, ValidationError
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.cache import patch_vary_headers
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie

from calculation import CalculationInputError
from domain.services.player_experiments import (
    PlayerExperimentError, assessment_principal,
)
from domain.services.player_workspaces import PlayerError

from .inputs import MAX_BODY_BYTES, ExperimentForm, WeightForm, weights_from_json
from .services import calculate_experiment, capture_for_player, open_experiment, time_slices

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
        "default-src 'none'; style-src 'self'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    patch_vary_headers(response, ("Cookie",))
    return response


def _error(code, status):
    return JsonResponse({"code": code, "errors": ["Запрос не выполнен."]}, status=status)


def _endpoint(methods):
    def decorate(handler):
        @wraps(handler)
        def wrapped(request, **kwargs):
            try:
                if request.method not in methods:
                    response = _error("PLAYER_METHOD_NOT_ALLOWED", 405)
                    response["Allow"] = ", ".join(methods)
                    return _secure(response)
                assessment_principal(request.user)
                if any(key in request.META for key in _SPOOF_HEADERS):
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


@_endpoint(["GET", "POST"])
@csrf_protect
@ensure_csrf_cookie
def result(request, experiment_id, time_slice_id):
    # Object access is checked even for malformed payloads, before reading them.
    open_experiment(user=request.user, experiment_id=experiment_id)
    if request.GET:
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
            weights = weights_from_json(request.body)
            view = calculate_experiment(user=request.user, experiment_id=experiment_id,
                                        time_slice_id=time_slice_id, beta_weights=weights)
            return JsonResponse(view.as_dict(), json_dumps_params={"ensure_ascii": False})
    elif request.body:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    selected, snapshot = capture_for_player(user=request.user, experiment_id=experiment_id,
                                           time_slice_id=time_slice_id)
    form = WeightForm(snapshot, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        view = calculate_experiment(user=request.user, experiment_id=experiment_id,
                                    time_slice_id=time_slice_id, beta_weights=form.beta_weights)
        from scenario_modeling.session import from_result
        return render(request, "player_integration/result.html", {
            **view.as_dict(), "snapshot_json": view.snapshot.to_json(), "run_json": view.run.to_json(),
            "scenario_token": from_result(request, view),
        })
    return render(request, "player_integration/inputs.html", {
        "experiment": selected, "snapshot": snapshot, "form": form, "rows": form.rows(),
    }, status=400 if form.is_bound else 200)
