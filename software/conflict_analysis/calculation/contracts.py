"""Immutable, JSON-replayable calculation inputs and results; no ORM authority."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from types import MappingProxyType


STRATEGY_ID = "POLARIZATION_V1_BETA"
STRATEGY_VERSION = "1.0.0"
ABSENT_STATUSES = frozenset({"UNKNOWN", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "OPEN_METHOD"})
NUMERIC_STATUSES = frozenset({"PROVISIONAL", "CONFIRMED", "DISPUTED", "RETROSPECTIVE_KNOWLEDGE"})


class CalculationInputError(ValueError):
    """An input identity, scale, status or replay contract is invalid."""


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return (text.rstrip("0").rstrip(".") if "." in text else text) if value else "0"


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), default=lambda item: decimal_text(item)
                      if isinstance(item, Decimal) else _unsupported(item))


def _unsupported(item):
    raise TypeError(f"Not a calculation JSON value: {type(item).__name__}")


def _identity(value: str) -> None:
    if type(value) is not str or not value.strip():
        raise CalculationInputError("Identity fields require nonempty strings.")


@dataclass(frozen=True, slots=True)
class InputValue:
    status: str = "UNKNOWN"
    value: Decimal | None = None
    source_id: str = "ABSENT"
    source_version: str = "1"

    def __post_init__(self):
        _identity(self.source_id)
        _identity(self.source_version)
        if self.status in ABSENT_STATUSES:
            if self.value is not None:
                raise CalculationInputError("Absent statuses must have a null value, never zero.")
        elif self.status in NUMERIC_STATUSES:
            if type(self.value) not in {Decimal, int, float, str}:
                raise CalculationInputError("Numeric statuses require a finite decimal value.")
            try:
                number = Decimal(str(self.value))
            except InvalidOperation as exc:
                raise CalculationInputError("Invalid decimal value.") from exc
            if not number.is_finite() or number.copy_abs() > 10:
                raise CalculationInputError("Beta inputs must be finite and within -10..10.")
            object.__setattr__(self, "value", number)
        else:
            raise CalculationInputError(f"Unsupported input status: {self.status}")

    @property
    def known(self) -> bool:
        return self.value is not None


def _weight(value: InputValue) -> None:
    if not isinstance(value, InputValue) or (value.known and value.value < 0):
        raise CalculationInputError("Weights must be InputValue records on 0..10.")


@dataclass(frozen=True, slots=True)
class ActorInput:
    actor_id: str
    relation_id: str
    assessment_id: str
    attitude: InputValue
    kvs: InputValue
    rgu: InputValue

    def __post_init__(self):
        for identity in (self.actor_id, self.relation_id, self.assessment_id):
            _identity(identity)
        if not isinstance(self.attitude, InputValue):
            raise CalculationInputError("Attitude must be an InputValue.")
        _weight(self.kvs)
        _weight(self.rgu)


@dataclass(frozen=True, slots=True)
class PtnInput:
    ptn_id: str
    kvptn: InputValue
    actors: tuple[ActorInput, ...]

    def __post_init__(self):
        _identity(self.ptn_id)
        _weight(self.kvptn)
        actors = tuple(self.actors)
        if any(not isinstance(row, ActorInput) for row in actors):
            raise CalculationInputError("PTN actors must be ActorInput records.")
        if len({row.actor_id for row in actors}) != len(actors):
            raise CalculationInputError("Duplicate actor within a PTN.")
        object.__setattr__(self, "actors", tuple(sorted(actors, key=lambda row: row.actor_id)))


@dataclass(frozen=True, slots=True)
class CalculationSnapshot:
    experiment_id: str
    assessment_set_id: str
    project_id: str
    time_slice_id: str
    workspace_id: str
    definition_version_id: str
    definition_hash: str
    time_slice_version: str
    cutoff_date: str
    ptns: tuple[PtnInput, ...]
    strategy_id: str = STRATEGY_ID
    strategy_version: str = STRATEGY_VERSION
    input_digest: str = field(init=False)
    id: str = field(init=False)

    def __post_init__(self):
        for name in ("experiment_id", "assessment_set_id", "project_id", "time_slice_id",
                     "workspace_id", "definition_version_id", "definition_hash",
                     "time_slice_version", "cutoff_date", "strategy_id", "strategy_version"):
            _identity(getattr(self, name))
        ptns = tuple(self.ptns)
        if any(not isinstance(row, PtnInput) for row in ptns):
            raise CalculationInputError("Snapshot PTNs must be PtnInput records.")
        if len({row.ptn_id for row in ptns}) != len(ptns):
            raise CalculationInputError("Duplicate PTN identity.")
        # RGU is actor x time x experiment, not actor x PTN.
        actor_weights = {}
        relation_ids = set()
        for ptn in ptns:
            for actor in ptn.actors:
                if actor.actor_id in actor_weights and actor_weights[actor.actor_id] != actor.rgu:
                    raise CalculationInputError("One actor must have one exact RGU input per snapshot.")
                actor_weights[actor.actor_id] = actor.rgu
                if actor.relation_id in relation_ids:
                    raise CalculationInputError("Duplicate topology relation identity.")
                relation_ids.add(actor.relation_id)
        object.__setattr__(self, "ptns", tuple(sorted(ptns, key=lambda row: row.ptn_id)))
        payload = {name: getattr(self, name) for name in self.__dataclass_fields__
                   if name not in {"input_digest", "id", "ptns"}}
        payload["ptns"] = [asdict(row) for row in self.ptns]
        digest = sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        object.__setattr__(self, "input_digest", digest)
        object.__setattr__(self, "id", f"sha256:{digest}")

    def to_json(self) -> str:
        return canonical_json(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> CalculationSnapshot:
        """Reconstruct an offline snapshot and verify its content identity."""
        try:
            payload = json.loads(raw)
            digest, identity = payload.pop("input_digest"), payload.pop("id")
            payload["ptns"] = tuple(PtnInput(
                ptn_id=ptn["ptn_id"], kvptn=InputValue(**ptn["kvptn"]),
                actors=tuple(ActorInput(**{
                    **actor, **{name: InputValue(**actor[name]) for name in ("attitude", "kvs", "rgu")}
                }) for actor in ptn["actors"]),
            ) for ptn in payload["ptns"])
            snapshot = cls(**payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise CalculationInputError("Invalid calculation snapshot payload.") from exc
        if (snapshot.input_digest, snapshot.id) != (digest, identity):
            raise CalculationInputError("Snapshot digest mismatch.")
        return snapshot


@dataclass(frozen=True, slots=True)
class Completeness:
    expected_rows: int
    eligible_rows: int
    expected_ptns: int
    computable_ptns: int
    known_ptn_weights: int


@dataclass(frozen=True, slots=True)
class ActorTrace:
    input: ActorInput
    eligible: bool
    missing: tuple[str, ...]
    weight: Decimal | None
    positive_numerator: Decimal | None
    negative_numerator: Decimal | None
    P_contribution: Decimal | None
    N_contribution: Decimal | None


@dataclass(frozen=True, slots=True)
class PtnResult:
    ptn_id: str
    P: Decimal | None
    N: Decimal | None
    A: Decimal | None
    B: Decimal | None
    Pol: Decimal | None
    W: Decimal
    status: str
    expected_rows: int
    eligible_rows: int
    kvptn: InputValue
    UNO_contribution: Decimal | None
    trace: tuple[ActorTrace, ...]


@dataclass(frozen=True, slots=True)
class CalculationRun:
    snapshot_id: str
    strategy_id: str
    strategy_version: str
    ptns: tuple[PtnResult, ...]
    UNO: Decimal | None
    completeness: Completeness
    warnings: tuple[str, ...]
    status: str

    def _metric(self, name):
        return MappingProxyType({row.ptn_id: getattr(row, name) for row in self.ptns})

    P = property(lambda self: self._metric("P"))
    N = property(lambda self: self._metric("N"))
    A = property(lambda self: self._metric("A"))
    B = property(lambda self: self._metric("B"))
    Pol = property(lambda self: self._metric("Pol"))
    trace = property(lambda self: self.ptns)

    def to_json(self) -> str:
        return canonical_json(asdict(self))

    @property
    def result_digest(self) -> str:
        return sha256(self.to_json().encode("utf-8")).hexdigest()
