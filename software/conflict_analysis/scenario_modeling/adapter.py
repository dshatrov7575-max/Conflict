"""Only the existing Core calculates metrics; overrides live in derived inputs."""
from dataclasses import dataclass, replace
from decimal import localcontext
import json

from calculation import CalculationRun, CalculationSnapshot, InputValue, calculate
from calculation.contracts import decimal_text

from .model import ScenarioModel, parameters


def delta(before, after):
    if before is None or after is None:
        return None
    # Subtraction of published UNO values, not a new polarization formula.
    with localcontext() as context:
        context.prec = 50
        return decimal_text(after - before)


class CalculationAdapter:
    @staticmethod
    def snapshot(model: ScenarioModel) -> CalculationSnapshot:
        overrides = {row.parameter: row.value for row in model.overrides}

        def effective(key, baseline):
            if key not in overrides:
                return baseline
            return InputValue("PROVISIONAL", overrides[key], f"SCENARIO:{model.id}:{key}", "1")

        return replace(model.baseline, ptns=tuple(replace(
            ptn, kvptn=effective(f"kvptn:{ptn.ptn_id}", ptn.kvptn),
            actors=tuple(replace(
                actor,
                attitude=effective(f"attitude:{actor.relation_id}", actor.attitude),
                kvs=effective(f"kvs:{actor.relation_id}", actor.kvs),
                rgu=effective(f"rgu:{actor.actor_id}", actor.rgu),
            ) for actor in ptn.actors),
        ) for ptn in model.baseline.ptns))

    @classmethod
    def run(cls, model: ScenarioModel):
        snapshot = cls.snapshot(model)
        return ScenarioCalculationRun(model.id, model.baseline.id, snapshot, calculate(snapshot))


@dataclass(frozen=True, slots=True)
class ScenarioCalculationRun:
    scenario_id: str
    baseline_snapshot_id: str
    snapshot: CalculationSnapshot
    run: CalculationRun


_EXPLANATIONS = {
    "POS": "POS задаёт сторону и величину позиции участника; её вклад зависит от KVS и RGU.",
    "KVS": "KVS меняет вес позиции участника в выбранном ПТН. Нулевой вес исключает её числовой вклад.",
    "RGU": "RGU меняет вес участника во всех ПТН этого snapshot. KVS по-прежнему задаёт вес в каждом ПТН.",
    "KVPTN": "KVPTN меняет вес ПТН в UNO. Известный ноль исключает ПТН из итогового взвешивания.",
}


def result_view(model):
    baseline = calculate(model.baseline)
    scenario = CalculationAdapter.run(model)
    targets = {row.key: row for row in parameters(model.baseline)}
    changes = []
    for override in model.overrides:
        target = targets[override.parameter]
        isolated = CalculationAdapter.run(replace(model, overrides=(override,))).run
        changes.append({
            **override.as_dict(), "label": target.label, "code": target.code,
            "baseline_value": decimal_text(target.baseline.value),
            "baseline_status": target.baseline.status,
            "baseline_source_id": target.baseline.source_id,
            "baseline_source_version": target.baseline.source_version,
            "explanation": _EXPLANATIONS[target.code],
            "isolated_uno": None if isolated.UNO is None else decimal_text(isolated.UNO),
            "isolated_delta": delta(baseline.UNO, isolated.UNO),
        })
    return {
        "contract": "SCENARIO_RESULT_V1", "scenario_id": model.id,
        "baseline": json.loads(baseline.to_json()),
        "scenario": json.loads(scenario.run.to_json()),
        "delta_uno": delta(baseline.UNO, scenario.run.UNO), "changes": changes,
        "result_digest": scenario.run.result_digest,
        "scenario_snapshot_json": scenario.snapshot.to_json(),
        "scenario_run_json": scenario.run.to_json(), "model_json": model.to_json(),
    }
