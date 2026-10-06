"""Pure scenario value objects. No ORM models, source writes or formulas."""
from dataclasses import dataclass, replace
from decimal import Decimal
import json
import re
from uuid import UUID, uuid4

from calculation import CalculationInputError, CalculationRun, CalculationSnapshot, InputValue
from calculation.contracts import canonical_json, decimal_text

MAX_OVERRIDES = 256
_NUMBER = re.compile(r"-?(?:0|[1-9][0-9]?)(?:\.[0-9]{1,32})?\Z")


@dataclass(frozen=True, slots=True)
class Parameter:
    key: str
    code: str
    label: str
    baseline: InputValue
    minimum: int
    maximum: int = 10


def parameters(snapshot):
    """POS/KVS are relation-scoped; RGU is actor-scoped; KVPTN is PTN-scoped."""
    result, actors = [], set()
    for ptn in snapshot.ptns:
        result.append(Parameter(f"kvptn:{ptn.ptn_id}", "KVPTN", f"KVPTN · ПТН {ptn.ptn_id}", ptn.kvptn, 0))
        for actor in ptn.actors:
            label = f"ПТН {ptn.ptn_id} · участник {actor.actor_id}"
            result.extend((
                Parameter(f"attitude:{actor.relation_id}", "POS", f"POS · {label}", actor.attitude, -10),
                Parameter(f"kvs:{actor.relation_id}", "KVS", f"KVS (SAL) · {label}", actor.kvs, 0),
            ))
            if actor.actor_id not in actors:
                actors.add(actor.actor_id)
                result.append(Parameter(f"rgu:{actor.actor_id}", "RGU", f"RGU · участник {actor.actor_id} · все ПТН", actor.rgu, 0))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ScenarioOverride:
    parameter: str
    value: Decimal

    def __post_init__(self):
        if type(self.parameter) is not str or not self.parameter:
            raise CalculationInputError("Override requires a parameter identity.")
        if type(self.value) not in {str, int, Decimal}:
            raise CalculationInputError("Override requires an exact decimal, never float or bool.")
        if isinstance(self.value, Decimal):
            if not self.value.is_finite() or self.value.copy_abs() > 10 or self.value.as_tuple().exponent < -32:
                raise CalculationInputError("Override requires a finite beta value with up to 32 decimal places.")
            raw = format(self.value, "f") if self.value else "0"
        else:
            raw = str(self.value)
        if not _NUMBER.fullmatch(raw):
            raise CalculationInputError("Override requires a finite plain decimal (up to 32 decimal places).")
        number = Decimal(raw)
        if not -10 <= number <= 10:
            raise CalculationInputError("Override is outside the beta scale.")
        object.__setattr__(self, "value", number)

    def as_dict(self):
        return {"parameter": self.parameter, "value": decimal_text(self.value)}


@dataclass(frozen=True, slots=True)
class ScenarioModel:
    id: str
    baseline: CalculationSnapshot
    overrides: tuple[ScenarioOverride, ...] = ()

    def __post_init__(self):
        try:
            if str(UUID(self.id)) != self.id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError) as exc:
            raise CalculationInputError("Scenario requires a UUID identity.") from exc
        if not isinstance(self.baseline, CalculationSnapshot):
            raise CalculationInputError("Scenario requires an existing CalculationSnapshot.")
        overrides = tuple(self.overrides)
        if len(overrides) > MAX_OVERRIDES or any(not isinstance(row, ScenarioOverride) for row in overrides):
            raise CalculationInputError("Invalid override collection.")
        if len({row.parameter for row in overrides}) != len(overrides):
            raise CalculationInputError("Duplicate override target.")
        targets = {row.key: row for row in parameters(self.baseline)}
        for row in overrides:
            target = targets.get(row.parameter)
            if target is None or not target.baseline.known:
                raise CalculationInputError("Only known numeric baseline parameters can be overridden.")
            if not target.minimum <= row.value <= target.maximum:
                raise CalculationInputError("Override is outside the parameter scale.")
        object.__setattr__(self, "overrides", tuple(sorted(
            (row for row in overrides if row.value != targets[row.parameter].baseline.value),
            key=lambda row: row.parameter,
        )))

    @classmethod
    def from_calculation(cls, snapshot: CalculationSnapshot, run: CalculationRun):
        if run.snapshot_id != snapshot.id or (run.strategy_id, run.strategy_version) != (
            snapshot.strategy_id, snapshot.strategy_version,
        ):
            raise CalculationInputError("The calculation does not belong to this baseline.")
        return cls(str(uuid4()), snapshot)

    def with_override(self, parameter, value):
        return replace(self, overrides=tuple(row for row in self.overrides if row.parameter != parameter)
                       + (ScenarioOverride(parameter, value),))

    def without_override(self, parameter):
        if parameter not in {row.parameter for row in self.overrides}:
            raise CalculationInputError("Override not found in this scenario.")
        return replace(self, overrides=tuple(row for row in self.overrides if row.parameter != parameter))

    def as_dict(self):
        return {"contract": "SCENARIO_MODEL_V1", "id": self.id,
                "baseline": json.loads(self.baseline.to_json()),
                "overrides": [row.as_dict() for row in self.overrides]}

    def to_json(self):
        return canonical_json(self.as_dict())

    @classmethod
    def from_dict(cls, payload):
        try:
            if set(payload) != {"contract", "id", "baseline", "overrides"} or payload["contract"] != "SCENARIO_MODEL_V1":
                raise ValueError()
            if type(payload["overrides"]) is not list or len(payload["overrides"]) > MAX_OVERRIDES:
                raise ValueError()
            return cls(payload["id"], CalculationSnapshot.from_json(canonical_json(payload["baseline"])),
                       tuple(ScenarioOverride(**row) for row in payload["overrides"]))
        except (ValueError, TypeError, KeyError) as exc:
            raise CalculationInputError("Invalid scenario model.") from exc
