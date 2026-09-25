"""Bounded transport adapters for explicit, transient beta weights."""
import json
import re

from django import forms

from calculation import CalculationInputError, InputValue
from calculation.contracts import ABSENT_STATUSES, NUMERIC_STATUSES
from calculation.foundation import BetaWeights

MAX_BODY_BYTES = 262144
MAX_WEIGHT_ROWS = 1000
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]?)(?:\.[0-9]{1,32})?\Z")
STATUSES = [(name, name) for name in ("UNKNOWN", *sorted(ABSENT_STATUSES - {"UNKNOWN"}),
                                    *sorted(NUMERIC_STATUSES))]


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CalculationInputError("Duplicate JSON field.")
        result[key] = value
    return result


def _reject_constant(value):
    raise CalculationInputError("Non-finite JSON number.")


def _input(payload):
    if type(payload) is not dict or set(payload) != {"status", "value", "source_id", "source_version"}:
        raise CalculationInputError("An input requires status, value and source identity/version.")
    if type(payload["status"]) is not str:
        raise CalculationInputError("Invalid input status.")
    for name in ("source_id", "source_version"):
        if type(payload[name]) is not str or not payload[name].strip() or len(payload[name]) > 255:
            raise CalculationInputError("Invalid source identity/version.")
    value = payload["value"]
    if value is not None and (type(value) is not str or _DECIMAL.fullmatch(value) is None):
        raise CalculationInputError("Weights require plain decimal strings on 0..10 or null.")
    return InputValue(**payload)


def weights_from_json(raw):
    if not raw or len(raw) > MAX_BODY_BYTES:
        raise CalculationInputError("Invalid request size.")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_object,
                             parse_constant=_reject_constant)
        if type(payload) is not dict or set(payload) != {"experiment_id", "time_slice_id", "rgu", "kvptn"}:
            raise CalculationInputError("Expected an explicitly scoped beta-weight object.")
        groups = {}
        for name in ("rgu", "kvptn"):
            rows = payload[name]
            if type(rows) is not dict or len(rows) > MAX_WEIGHT_ROWS:
                raise CalculationInputError("Invalid weight collection.")
            groups[name] = tuple((key, _input(value)) for key, value in rows.items())
        return BetaWeights(payload["experiment_id"], payload["time_slice_id"], **groups)
    except (UnicodeError, ValueError, TypeError, KeyError, RecursionError) as exc:
        raise CalculationInputError("Invalid beta-weight request.") from exc


class ExperimentForm(forms.Form):
    experiment_id = forms.UUIDField(label="Идентификатор эксперимента")


class WeightForm(forms.Form):
    experiment_id = forms.CharField(widget=forms.HiddenInput)
    time_slice_id = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, snapshot, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snapshot = snapshot
        self.groups = {
            "rgu": sorted({actor.actor_id for ptn in snapshot.ptns for actor in ptn.actors}),
            "kvptn": [ptn.ptn_id for ptn in snapshot.ptns],
        }
        self.initial.update(experiment_id=snapshot.experiment_id, time_slice_id=snapshot.time_slice_id)
        for group, identities in self.groups.items():
            for identity in identities:
                prefix = f"{group}.{identity}."
                self.fields[prefix + "status"] = forms.ChoiceField(choices=STATUSES, initial="UNKNOWN")
                self.fields[prefix + "value"] = forms.CharField(required=False, max_length=36)
                self.fields[prefix + "source_id"] = forms.CharField(required=False, max_length=255)
                self.fields[prefix + "source_version"] = forms.CharField(required=False, max_length=255)

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        if (data["experiment_id"], data["time_slice_id"]) != (
            self.snapshot.experiment_id, self.snapshot.time_slice_id,
        ):
            raise forms.ValidationError("Веса относятся к другому эксперименту или временному срезу.")
        if set(self.data) - {"csrfmiddlewaretoken", *self.fields} or any(
            len(self.data.getlist(key)) != 1 for key in self.data
        ):
            raise forms.ValidationError("Некорректные или повторные поля запроса.")
        groups = {}
        try:
            for group, identities in self.groups.items():
                rows = []
                for identity in identities:
                    prefix = f"{group}.{identity}."
                    payload = {name: data[prefix + name] for name in
                               ("status", "value", "source_id", "source_version")}
                    payload["value"] = payload["value"] or None
                    if payload["value"] is None and not payload["source_id"] and not payload["source_version"]:
                        payload.update(source_id="ABSENT", source_version="1")
                    rows.append((identity, _input(payload)))
                groups[group] = tuple(rows)
            self.beta_weights = BetaWeights(data["experiment_id"], data["time_slice_id"], **groups)
        except CalculationInputError as exc:
            raise forms.ValidationError(
                "Проверьте веса 0…10, статус, источник и версию. UNKNOWN требует пустого значения; "
                "число требует числового статуса и явного источника."
            ) from exc
        return data

    def rows(self):
        return [
            {"group": group.upper(), "identity": identity,
             "fields": [self[f"{group}.{identity}.{name}"] for name in
                        ("status", "value", "source_id", "source_version")]}
            for group, identities in self.groups.items() for identity in identities
        ]
