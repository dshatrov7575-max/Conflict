from dataclasses import replace
from functools import wraps

from django import forms
from django.shortcuts import render
from django.views.decorators.csrf import csrf_protect

from calculation import CalculationInputError
from calculation.contracts import decimal_text
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
    fields = {"csrfmiddlewaretoken", "scenario_token", "action", "parameter", "value"}
    if set(request.POST) - fields or any(len(request.POST.getlist(key)) != 1 for key in request.POST):
        raise CalculationInputError("Unknown or repeated form field.")
    model, experiment = restore(request, request.POST.get("scenario_token"))
    action = request.POST.get("action")
    expected = {"set": {"parameter", "value"}, "remove": {"parameter"}, "start": set(),
                "recalculate": set(), "reset": set()}
    if action not in expected or set(request.POST) - {"csrfmiddlewaretoken", "scenario_token", "action"} != expected[action]:
        raise CalculationInputError("Invalid scenario action fields.")
    form, status = OverrideForm(model), 200
    if action == "set":
        form = OverrideForm(model, request.POST)
        if form.is_valid():
            model = form.updated_model
            form = OverrideForm(model, initial={"parameter": form.cleaned_data["parameter"], "value": form.cleaned_data["value"]})
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
    return render(request, "scenario_modeling/result.html", {
        **result_view(model), "model": model, "experiment": experiment,
        "scenario_token": seal(request, model), "form": form, "choices": choices,
        "has_parameters": any(row["value"] is not None for row in choices),
    }, status=status)
