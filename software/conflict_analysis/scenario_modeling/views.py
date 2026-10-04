from dataclasses import replace
from functools import wraps
from hashlib import sha256
from uuid import uuid4

from django import forms
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

from calculation import CalculationInputError, CalculationSnapshot, calculate
from calculation.contracts import decimal_text
from domain.services.player_workspaces import canonical_receipt_bytes
from player_integration.quality import summarize_quality
from player_integration.receipts import parse_operation_id, record_calculation_receipt
from player_integration.views import _endpoint

from .adapter import result_view
from .model import parameters
from .session import MAX_TOKEN_LENGTH, restore, seal


class OverrideForm(forms.Form):
    parameter = forms.ChoiceField(label="Параметр")
    value = forms.CharField(label="Числовое значение", max_length=36,
                            widget=forms.NumberInput(attrs={"step": "any", "min": -10, "max": 10}))

    def __init__(self, model, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parameter"].choices = [(row.key, row.label) for row in parameters(model.baseline) if row.baseline.known]
        self.model = model

    def clean(self):
        data = super().clean()
        if not self.errors:
            try:
                self.updated_model = self.model.with_override(data["parameter"], data["value"])
            except CalculationInputError:
                raise forms.ValidationError("Введите число в диапазоне параметра: POS −10…10; KVS, RGU, KVPTN 0…10.")
        return data


def _scenario_endpoint(handler):
    @wraps(handler)
    def wrapped(request):
        response = _endpoint(["POST"])(handler)(request)
        response["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'self'; script-src 'self'; form-action 'self'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        return response
    return wrapped


@_scenario_endpoint
@csrf_protect
def update(request):
    if request.GET or request.content_type != "application/x-www-form-urlencoded":
        raise CalculationInputError("Expected a scenario form.")
    if len(request.body) > MAX_TOKEN_LENGTH + 16384:
        raise CalculationInputError("Scenario request too large.")
    fields = {
        "csrfmiddlewaretoken", "scenario_token", "operation_id", "action", "parameter", "value",
    }
    if set(request.POST) - fields or any(len(request.POST.getlist(key)) != 1 for key in request.POST):
        raise CalculationInputError("Unknown or repeated form field.")
    operation_id = parse_operation_id(request.POST.get("operation_id"))
    model, experiment = restore(request, request.POST.get("scenario_token"))
    action = request.POST.get("action")
    expected = {"set": {"parameter", "value"}, "remove": {"parameter"}, "start": set(),
                "recalculate": set(), "reset": set()}
    common = {"csrfmiddlewaretoken", "scenario_token", "operation_id", "action"}
    if action not in expected or set(request.POST) - common != expected[action]:
        raise CalculationInputError("Invalid scenario action fields.")
    form, status = OverrideForm(model), 200
    if action == "set":
        form = OverrideForm(model, request.POST)
        if form.is_valid():
            model = form.updated_model
            form = OverrideForm(model, initial={
                "parameter": form.cleaned_data["parameter"],
                "value": form.cleaned_data["value"],
            })
        else:
            status = 400
    elif action == "remove":
        model = model.without_override(request.POST["parameter"])
    elif action == "reset":
        model = replace(model, overrides=())
    current = {row.parameter: row.value for row in model.overrides}
    choices = [{"key": row.key, "label": row.label, "min": row.minimum, "max": row.maximum,
                "value": decimal_text(current.get(row.key, row.baseline.value)) if row.baseline.known else None,
                "status": row.baseline.status} for row in parameters(model.baseline)]
    payload = result_view(model)
    receipt = None
    if status == 200:
        scenario_snapshot = CalculationSnapshot.from_json(payload["scenario_snapshot_json"])
        scenario_run = calculate(scenario_snapshot)
        if scenario_run.to_json() != payload["scenario_run_json"]:
            raise CalculationInputError("Scenario result replay mismatch.")
        receipt = record_calculation_receipt(
            user=request.user,
            experiment=experiment,
            snapshot=scenario_snapshot,
            run=scenario_run,
            quality=summarize_quality(scenario_snapshot, scenario_run),
            operation_id=operation_id,
            context_kind="SCENARIO",
            scenario_id=model.id,
            baseline_snapshot_id=model.baseline.id,
            scenario_model_sha256=sha256(model.to_json().encode("utf-8")).hexdigest(),
        )
        payload = {
            **payload,
            "contract": "SCENARIO_RESULT_V3",
            "receipt": dict(receipt.payload),
            "receipt_replayed": receipt.replayed,
            "receipt_json": canonical_receipt_bytes(receipt.payload).decode("utf-8"),
        }
    response = render(request, "scenario_modeling/result.html", {
        **payload,
        "model": model,
        "experiment": experiment,
        "scenario_token": seal(request, model),
        "operation_id": uuid4(),
        "form": form,
        "choices": choices,
        "has_parameters": any(row["value"] is not None for row in choices),
    }, status=status)
    if receipt is not None:
        response["X-Calculation-Receipt-ID"] = str(receipt.payload["operation_id"])
        response["X-Calculation-Receipt-Replayed"] = "true" if receipt.replayed else "false"
    return response
