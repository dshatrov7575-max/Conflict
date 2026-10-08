"""Explicit offline 1.1 contracts. No conversion from the 1.0 input schema.

TopologyAuthorityV1_1 is the frozen definition/method artifact, not a calculation
option. Its producer must be trusted by the capture boundary: hashes verify
content identity, not the producer's authorization or historical freeze time.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
import re

from .contracts import CalculationInputError, canonical_json, decimal_text


STRATEGY_ID_V1_1 = "POLARIZATION_V1_BETA"
STRATEGY_VERSION_V1_1 = "1.1.0"
NUMERIC_STATUSES_V1_1 = frozenset({"CONFIRMED", "PROVISIONAL", "RETROSPECTIVE_KNOWLEDGE"})
ABSENT_STATUSES_V1_1 = frozenset({"UNKNOWN", "INSUFFICIENT_DATA", "OPEN_METHOD",
                                "NOT_APPLICABLE", "DISPUTED"})
TEMPORAL_STATUSES_V1_1 = frozenset({"CONTEMPORANEOUS", "RETROSPECTIVE_KNOWLEDGE",
                                  "NO_DIRECT_POSITION", "UNKNOWN"})
_DECIMAL = re.compile(r"-?(0|[1-9][0-9]?)(\.[0-9]{1,32})?", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}", re.ASCII)


def _fail(code):
    raise CalculationInputError(code)


def _identity(value):
    if type(value) is not str or not value.strip():
        _fail("IDENTITY_INVALID")


def _digest(value):
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail("SHA256_INVALID")


def _hash(value):
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def decimal_v1_1(value, *, minimum=-10):
    """Lexical validation precedes domain validation; never use Decimal context."""
    if type(value) not in (str, int, Decimal):
        _fail("DECIMAL_LEXICAL_INVALID")
    text = str(value)
    if _DECIMAL.fullmatch(text) is None:
        _fail("DECIMAL_LEXICAL_INVALID")
    number = Decimal(text)
    if not minimum <= number <= 10:
        _fail("DECIMAL_DOMAIN_INVALID")
    # Normalize spelling, including negative zero, without normalize()/rounding.
    return Decimal(decimal_text(number))


@dataclass(frozen=True, slots=True)
class InputValueV1_1:
    value_status: str = "UNKNOWN"
    temporal_status: str = "UNKNOWN"
    value: Decimal | None = None
    alternatives: tuple[Decimal, ...] = ()
    source_id: str = "ABSENT"
    source_version: str = "1"

    def __post_init__(self):
        _identity(self.source_id)
        _identity(self.source_version)
        if self.value_status not in NUMERIC_STATUSES_V1_1 | ABSENT_STATUSES_V1_1:
            _fail("VALUE_STATUS_INVALID")
        if self.temporal_status not in TEMPORAL_STATUSES_V1_1:
            _fail("TEMPORAL_STATUS_INVALID")
        if self.temporal_status == "NO_DIRECT_POSITION" and self.value_status != "UNKNOWN":
            _fail("NO_DIRECT_POSITION_REQUIRES_UNKNOWN")
        if self.value_status in NUMERIC_STATUSES_V1_1:
            object.__setattr__(self, "value", decimal_v1_1(self.value))
        elif self.value is not None:
            _fail("NONNUMERIC_VALUE_MUST_BE_NULL")
        if type(self.alternatives) not in (tuple, list):
            _fail("ALTERNATIVES_INVALID")
        alternatives = tuple(sorted(decimal_v1_1(v) for v in self.alternatives))
        if alternatives and (self.value_status != "DISPUTED" or len(alternatives) < 2
                             or len(set(alternatives)) != len(alternatives)):
            _fail("ALTERNATIVES_INVALID")
        object.__setattr__(self, "alternatives", alternatives)

    @property
    def known(self):
        return self.value is not None


@dataclass(frozen=True, slots=True)
class DesignWeightInputV1_1:
    value: Decimal | None = None
    design_record_id: str | None = None
    design_record_sha256: str | None = None

    def __post_init__(self):
        if self.value is not None:
            object.__setattr__(self, "value", decimal_v1_1(self.value, minimum=0))
        if (self.design_record_id is None) != (self.design_record_sha256 is None):
            _fail("DESIGN_RECORD_IDENTITY_INVALID")
        if self.design_record_id is not None:
            _identity(self.design_record_id)
            _digest(self.design_record_sha256)

    @classmethod
    def from_payload(cls, payload):
        if type(payload) is not dict:
            _fail("DESIGN_WEIGHT_INVALID")
        if set(payload) & {"status", "value_status", "temporal_status", "alternatives"}:
            _fail("DESIGN_WEIGHT_STATUS_INVALID")
        try:
            return cls(**payload)
        except TypeError as exc:
            raise CalculationInputError("DESIGN_WEIGHT_INVALID") from exc


def _design(value):
    if type(value) is not DesignWeightInputV1_1:
        _fail("DESIGN_WEIGHT_STATUS_INVALID")


@dataclass(frozen=True, slots=True)
class ActorInputV1_1:
    actor_id: str
    relation_id: str
    assessment_id: str
    attitude: InputValueV1_1
    kvs: InputValueV1_1
    rgu: DesignWeightInputV1_1

    def __post_init__(self):
        for value in (self.actor_id, self.relation_id, self.assessment_id):
            _identity(value)
        if type(self.attitude) is not InputValueV1_1 or type(self.kvs) is not InputValueV1_1:
            _fail("EMPIRICAL_INPUT_SCHEMA_INVALID")
        if (self.kvs.known and self.kvs.value < 0) or any(v < 0 for v in self.kvs.alternatives):
            _fail("KVS_DOMAIN_INVALID")
        _design(self.rgu)


@dataclass(frozen=True, slots=True)
class PtnInputV1_1:
    ptn_id: str
    kvptn: DesignWeightInputV1_1
    actors: tuple[ActorInputV1_1, ...]

    def __post_init__(self):
        _identity(self.ptn_id)
        _design(self.kvptn)
        actors = tuple(self.actors)
        if any(type(row) is not ActorInputV1_1 for row in actors):
            _fail("ACTOR_INPUT_SCHEMA_INVALID")
        if len({row.actor_id for row in actors}) != len(actors):
            _fail("DUPLICATE_ACTOR")
        object.__setattr__(self, "actors", tuple(sorted(actors, key=lambda row: row.actor_id)))


@dataclass(frozen=True, slots=True)
class FreezeProvenanceV1_1:
    decision_record_id: str
    frozen_at: str
    subject_id: str

    def __post_init__(self):
        for value in (self.decision_record_id, self.frozen_at, self.subject_id):
            _identity(value)
        try:
            timestamp = datetime.fromisoformat(self.frozen_at.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError
        except ValueError as exc:
            raise CalculationInputError("FREEZE_PROVENANCE_TIME_INVALID") from exc


@dataclass(frozen=True, slots=True)
class TopologyRuleV1_1:
    rule_id: str
    rule_version: str
    rule_sha256: str
    reasons: tuple[str, ...]

    def __post_init__(self):
        _identity(self.rule_id)
        _identity(self.rule_version)
        _digest(self.rule_sha256)
        if type(self.reasons) not in (tuple, list):
            _fail("TOPOLOGY_RULE_REASONS_INVALID")
        reasons = tuple(self.reasons)
        for reason in reasons:
            _identity(reason)
        if not reasons or len(set(reasons)) != len(reasons):
            _fail("TOPOLOGY_RULE_REASONS_INVALID")
        object.__setattr__(self, "reasons", tuple(sorted(reasons)))


@dataclass(frozen=True, slots=True)
class TopologyExclusionV1_1:
    exclusion_id: str
    actor_id: str
    ptn_id: str
    relation_id: str
    rule_id: str
    rule_version: str
    rule_sha256: str
    reason: str
    definition_version_id: str
    method_contract_sha256: str | None
    provenance: FreezeProvenanceV1_1
    exclusion_record_sha256: str

    def __post_init__(self):
        for name in ("exclusion_id", "actor_id", "ptn_id", "relation_id", "rule_id",
                     "rule_version", "reason", "definition_version_id"):
            _identity(getattr(self, name))
        _digest(self.rule_sha256)
        _digest(self.exclusion_record_sha256)
        if self.method_contract_sha256 is not None:
            _digest(self.method_contract_sha256)
        if type(self.provenance) is not FreezeProvenanceV1_1:
            _fail("FREEZE_PROVENANCE_INVALID")
        payload = asdict(self)
        payload.pop("exclusion_record_sha256")
        if _hash(payload) != self.exclusion_record_sha256:
            _fail("TOPOLOGY_EXCLUSION_RECORD_DIGEST_MISMATCH")


@dataclass(frozen=True, slots=True)
class TopologyAuthorityV1_1:
    """Complete frozen definition export; strict method pins are all-or-none.

    No calculation/scenario API constructs or modifies exclusions. A trusted
    definition exporter supplies this artifact, including independently pinned
    set/record digests and the versioned rules. Offline replay retains it whole.
    """
    definition_version_id: str
    definition_sha256: str
    provenance: FreezeProvenanceV1_1
    rules: tuple[TopologyRuleV1_1, ...]
    exclusions: tuple[TopologyExclusionV1_1, ...]
    topology_exclusion_set_sha256: str
    method_contract_sha256: str | None = None
    method_topology_exclusion_set_sha256: str | None = None
    method_rules: tuple[TopologyRuleV1_1, ...] = ()

    def __post_init__(self):
        _identity(self.definition_version_id)
        _digest(self.definition_sha256)
        _digest(self.topology_exclusion_set_sha256)
        if type(self.provenance) is not FreezeProvenanceV1_1:
            _fail("FREEZE_PROVENANCE_INVALID")
        rules, exclusions, method_rules = tuple(self.rules), tuple(self.exclusions), tuple(self.method_rules)
        if any(type(r) is not TopologyRuleV1_1 for r in (*rules, *method_rules)):
            _fail("TOPOLOGY_RULE_INVALID")
        if any(type(e) is not TopologyExclusionV1_1 for e in exclusions):
            _fail("TOPOLOGY_EXCLUSION_INVALID")
        if len({r.rule_id for r in rules}) != len(rules):
            _fail("DUPLICATE_TOPOLOGY_RULE")
        if (len({e.exclusion_id for e in exclusions}) != len(exclusions)
                or len({e.relation_id for e in exclusions}) != len(exclusions)):
            _fail("DUPLICATE_TOPOLOGY_EXCLUSION")
        rules = tuple(sorted(rules, key=lambda r: r.rule_id))
        exclusions = tuple(sorted(exclusions, key=lambda e: e.exclusion_id))
        method_rules = tuple(sorted(method_rules, key=lambda r: r.rule_id))
        if _hash([asdict(e) for e in exclusions]) != self.topology_exclusion_set_sha256:
            _fail("TOPOLOGY_EXCLUSION_SET_MISMATCH")
        if self.method_contract_sha256 is None:
            if self.method_topology_exclusion_set_sha256 is not None or method_rules:
                _fail("METHOD_CONTRACT_PIN_INVALID")
        else:
            _digest(self.method_contract_sha256)
            if self.method_topology_exclusion_set_sha256 != self.topology_exclusion_set_sha256:
                _fail("TOPOLOGY_EXCLUSION_SET_MISMATCH")
            if method_rules != rules:
                _fail("METHOD_TOPOLOGY_RULE_MISMATCH")
        by_rule = {r.rule_id: r for r in rules}
        for exclusion in exclusions:
            rule = by_rule.get(exclusion.rule_id)
            if (exclusion.definition_version_id != self.definition_version_id
                    or exclusion.method_contract_sha256 != self.method_contract_sha256):
                _fail("TOPOLOGY_AUTHORITY_MISMATCH")
            if (rule is None or (rule.rule_version, rule.rule_sha256) !=
                    (exclusion.rule_version, exclusion.rule_sha256) or exclusion.reason not in rule.reasons):
                _fail("TOPOLOGY_RULE_MISMATCH")
        for name, value in (("rules", rules), ("exclusions", exclusions), ("method_rules", method_rules)):
            object.__setattr__(self, name, value)


def _authority_from_payload(payload):
    data = dict(payload)
    data["provenance"] = FreezeProvenanceV1_1(**data["provenance"])
    for name in ("rules", "method_rules"):
        data[name] = tuple(TopologyRuleV1_1(**r) for r in data[name])
    data["exclusions"] = tuple(TopologyExclusionV1_1(**{
        **e, "provenance": FreezeProvenanceV1_1(**e["provenance"]),
    }) for e in data["exclusions"])
    return TopologyAuthorityV1_1(**data)


@dataclass(frozen=True, slots=True)
class CalculationSnapshotV1_1:
    experiment_id: str
    assessment_set_id: str
    assessment_kind: str
    project_id: str
    time_slice_id: str
    workspace_id: str
    time_slice_version: str
    cutoff_date: str
    topology_authority: TopologyAuthorityV1_1
    ptns: tuple[PtnInputV1_1, ...]
    strategy_id: str = STRATEGY_ID_V1_1
    strategy_version: str = STRATEGY_VERSION_V1_1
    topology_exclusions: tuple[TopologyExclusionV1_1, ...] = field(init=False)
    topology_exclusion_set_sha256: str = field(init=False)
    input_digest: str = field(init=False)
    id: str = field(init=False)

    def __post_init__(self):
        for name in ("experiment_id", "assessment_set_id", "assessment_kind", "project_id",
                     "time_slice_id", "workspace_id", "time_slice_version", "cutoff_date"):
            _identity(getattr(self, name))
        if self.assessment_kind not in {"HUMAN", "AI"}:
            _fail("ASSESSMENT_KIND_INVALID")
        if (self.strategy_id, self.strategy_version) != (STRATEGY_ID_V1_1, STRATEGY_VERSION_V1_1):
            _fail("SNAPSHOT_STRATEGY_VERSION_MISMATCH")
        if type(self.topology_authority) is not TopologyAuthorityV1_1:
            _fail("TOPOLOGY_AUTHORITY_REQUIRED")
        ptns = tuple(self.ptns)
        if any(type(p) is not PtnInputV1_1 for p in ptns):
            _fail("PTN_INPUT_SCHEMA_INVALID")
        if len({p.ptn_id for p in ptns}) != len(ptns):
            _fail("DUPLICATE_PTN")
        weights, relations = {}, {}
        for ptn in ptns:
            for row in ptn.actors:
                if row.actor_id in weights and weights[row.actor_id] != row.rgu:
                    _fail("ACTOR_RGU_MISMATCH")
                weights[row.actor_id] = row.rgu
                if row.relation_id in relations:
                    _fail("DUPLICATE_RELATION")
                relations[row.relation_id] = (row.actor_id, ptn.ptn_id)
        for exclusion in self.topology_authority.exclusions:
            if relations.get(exclusion.relation_id) != (exclusion.actor_id, exclusion.ptn_id):
                _fail("TOPOLOGY_EXCLUSION_RELATION_MISMATCH")
        object.__setattr__(self, "ptns", tuple(sorted(ptns, key=lambda p: p.ptn_id)))
        object.__setattr__(self, "topology_exclusions", self.topology_authority.exclusions)
        object.__setattr__(self, "topology_exclusion_set_sha256",
                           self.topology_authority.topology_exclusion_set_sha256)
        payload = {name: getattr(self, name) for name in self.__dataclass_fields__
                   if name not in {"input_digest", "id"}}
        # asdict recursively freezes the serializable shape, never ORM lookups.
        payload["topology_authority"] = asdict(self.topology_authority)
        payload["topology_exclusions"] = [asdict(e) for e in self.topology_exclusions]
        payload["ptns"] = [asdict(p) for p in self.ptns]
        digest = _hash(payload)
        object.__setattr__(self, "input_digest", digest)
        object.__setattr__(self, "id", f"sha256:{digest}")

    def to_json(self):
        return canonical_json(asdict(self))

    @classmethod
    def from_json(cls, raw):
        try:
            data = json.loads(raw, object_pairs_hook=_unique_keys)
            if (data.get("strategy_id"), data.get("strategy_version")) != (
                    STRATEGY_ID_V1_1, STRATEGY_VERSION_V1_1):
                _fail("SNAPSHOT_STRATEGY_VERSION_MISMATCH")
            digest, identity = data.pop("input_digest"), data.pop("id")
            exclusions = data.pop("topology_exclusions")
            set_digest = data.pop("topology_exclusion_set_sha256")
            data["topology_authority"] = _authority_from_payload(data["topology_authority"])
            for ptn in data["ptns"]:
                if type(ptn) is not dict or set(ptn) != {"ptn_id", "kvptn", "actors"}:
                    _fail("PTN_PAYLOAD_INVALID")
            data["ptns"] = tuple(PtnInputV1_1(
                ptn_id=p["ptn_id"], kvptn=DesignWeightInputV1_1.from_payload(p["kvptn"]),
                actors=tuple(ActorInputV1_1(**{
                    **r, "attitude": InputValueV1_1(**r["attitude"]),
                    "kvs": InputValueV1_1(**r["kvs"]),
                    "rgu": DesignWeightInputV1_1.from_payload(r["rgu"]),
                }) for r in p["actors"]),
            ) for p in data["ptns"])
            result = cls(**data)
            if (set_digest != result.topology_exclusion_set_sha256 or
                    canonical_json(exclusions) != canonical_json([asdict(e) for e in result.topology_exclusions])):
                _fail("TOPOLOGY_EXCLUSION_SET_MISMATCH")
            if (digest, identity) != (result.input_digest, result.id):
                _fail("SNAPSHOT_DIGEST_MISMATCH")
            return result
        except CalculationInputError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise CalculationInputError("SNAPSHOT_PAYLOAD_INVALID") from exc


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _rational_payload(value):
    if isinstance(value, Fraction):
        return {"numerator": str(value.numerator), "denominator": str(value.denominator)}
    if isinstance(value, dict):
        return {key: _rational_payload(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_rational_payload(item) for item in value]
    return value


class _ResultJSONV1_1:
    __slots__ = ()

    def to_json(self):
        return canonical_json(_rational_payload(asdict(self)))

    @property
    def result_digest(self):
        return sha256(self.to_json().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class WitnessRowV1_1:
    relation_id: str
    position: Fraction
    kvs: Fraction
    weight: Fraction
    position_alternative: Fraction | None
    kvs_alternative: Fraction | None


@dataclass(frozen=True, slots=True)
class ActorTraceV1_1:
    input: ActorInputV1_1
    row_class: str
    exclusion_id: str | None = None
    rule_id: str | None = None


@dataclass(frozen=True, slots=True)
class PtnResultV1_1:
    ptn_id: str
    status: str
    reason: str | None
    Pol_point: Decimal | None
    Pol_lo: Decimal | None
    Pol_hi: Decimal | None
    exact_lo: Fraction | None
    exact_hi: Fraction | None
    envelope_sharpness: str | None
    witness_lo: tuple[WitnessRowV1_1, ...] | None
    witness_hi: tuple[WitnessRowV1_1, ...] | None
    Pol_observed_subset: Decimal | None
    expected_rows: int
    eligible_rows: int
    excluded_rows: int
    retrospective_value_count: int
    retrospective_temporal_count: int
    not_applicable_rows: int
    known_weight_fraction: Fraction | None
    envelope_width: Decimal | None
    kvptn: DesignWeightInputV1_1
    UNO_contribution_lo: Decimal | None
    UNO_contribution_hi: Decimal | None
    warnings: tuple[str, ...]
    trace: tuple[ActorTraceV1_1, ...]


@dataclass(frozen=True, slots=True)
class CalculationRunV1_1(_ResultJSONV1_1):
    snapshot_id: str
    strategy_id: str
    strategy_version: str
    ptns: tuple[PtnResultV1_1, ...]
    UNO_point: Decimal | None
    UNO_lo: Decimal | None
    UNO_hi: Decimal | None
    exact_lo: Fraction | None
    exact_hi: Fraction | None
    envelope_sharpness: str | None
    warnings: tuple[str, ...]
    status: str


@dataclass(frozen=True, slots=True)
class ScenarioDeltaV1_1(_ResultJSONV1_1):
    base_snapshot_id: str
    scenario_snapshot_id: str
    delta_point: Decimal | None
    delta_outer: tuple[Decimal, Decimal] | None
    exact_outer: tuple[Fraction, Fraction] | None
    envelope_sharpness: str | None
    direction: str
