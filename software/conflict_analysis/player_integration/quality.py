"""Separate arithmetic computability from evidence/admission quality."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from calculation import CalculationRun, CalculationSnapshot, InputValue
from calculation.contracts import ABSENT_STATUSES, NUMERIC_STATUSES

QUALITY_CONTRACT = "PLAYER_CALCULATION_QUALITY_V1"
QUALITY_CONTRACT_V2 = "PLAYER_CALCULATION_QUALITY_V2"
SCIENTIFIC_ADMISSION_STATUS = "NOT_ESTABLISHED"
HUMAN_VALIDATION_STATUS = "NOT_PERFORMED"
PREDICTIVE_VALIDITY_STATUS = "NOT_CLAIMED"

_EVIDENCE_LABELS_RU = {
    "NO_REQUIRED_INPUTS": "нет входов",
    "REQUIRED_INPUTS_MISSING": "есть пропуски",
    "DISPUTED_INPUTS_PRESENT": "есть спорные входы",
    "PROVISIONAL_INPUTS_PRESENT": "предварительные входы",
    "RETROSPECTIVE_KNOWLEDGE_PRESENT": "ретроспективные входы",
    "CONFIRMED_INPUTS_ONLY": "только подтверждённые входы",
    "MIXED_NUMERIC_INPUTS": "смешанные числовые входы",
}
_COMPUTATION_LABELS_RU = {
    "COMPLETE": "полно",
    "PARTIAL": "частично",
    "NOT_COMPUTABLE": "не вычисляется",
}


def _inputs(snapshot: CalculationSnapshot) -> Iterable[InputValue]:
    for ptn in snapshot.ptns:
        yield ptn.kvptn
        for actor in ptn.actors:
            yield actor.attitude
            yield actor.kvs
            yield actor.rgu


@dataclass(frozen=True, slots=True)
class CalculationQuality:
    computation_status: str
    evidence_status: str
    scientific_admission_status: str
    human_validation_status: str
    predictive_validity_status: str
    required_input_count: int
    known_input_count: int
    missing_input_count: int
    scenario_input_count: int
    status_counts: tuple[tuple[str, int], ...]
    temporal_status_counts: tuple[tuple[str, int], ...] = ()
    contract: str = QUALITY_CONTRACT

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "computation_status": self.computation_status,
            "evidence_status": self.evidence_status,
            "scientific_admission_status": self.scientific_admission_status,
            "human_validation_status": self.human_validation_status,
            "predictive_validity_status": self.predictive_validity_status,
            "required_input_count": self.required_input_count,
            "known_input_count": self.known_input_count,
            "missing_input_count": self.missing_input_count,
            "scenario_input_count": self.scenario_input_count,
            "status_counts": dict(self.status_counts),
            **({"temporal_status_counts": dict(self.temporal_status_counts)}
               if self.contract == QUALITY_CONTRACT_V2 else {}),
        }


def summarize_quality(
    snapshot: CalculationSnapshot,
    run: CalculationRun,
    input_metadata: dict[str, object] | None = None,
) -> CalculationQuality:
    """Return a deterministic quality summary without changing Core or its digest."""

    if run.snapshot_id != snapshot.id:
        raise ValueError("CalculationRun does not belong to CalculationSnapshot.")
    values = tuple(_inputs(snapshot))
    counts = Counter(value.status for value in values)
    unsupported = set(counts) - ABSENT_STATUSES - NUMERIC_STATUSES
    if unsupported:
        raise ValueError(f"Unsupported input status in quality summary: {sorted(unsupported)}")
    missing = sum(counts[status] for status in ABSENT_STATUSES)
    known = len(values) - missing
    scenario = sum(value.source_id.startswith("SCENARIO:") for value in values)
    temporal_counts = Counter()
    if input_metadata is not None:
        for item in input_metadata.get("inputs", []):
            if isinstance(item, dict) and item.get("temporal_status"):
                temporal_counts[str(item["temporal_status"])] += 1
    if not values:
        evidence = "NO_REQUIRED_INPUTS"
    elif missing:
        evidence = "REQUIRED_INPUTS_MISSING"
    elif counts["DISPUTED"]:
        evidence = "DISPUTED_INPUTS_PRESENT"
    elif temporal_counts["RETROSPECTIVE_KNOWLEDGE"] or counts["RETROSPECTIVE_KNOWLEDGE"]:
        evidence = "RETROSPECTIVE_KNOWLEDGE_PRESENT"
    elif counts["PROVISIONAL"]:
        evidence = "PROVISIONAL_INPUTS_PRESENT"
    elif counts["CONFIRMED"] == len(values):
        evidence = "CONFIRMED_INPUTS_ONLY"
    else:
        evidence = "MIXED_NUMERIC_INPUTS"
    return CalculationQuality(
        computation_status=run.status,
        evidence_status=evidence,
        scientific_admission_status=SCIENTIFIC_ADMISSION_STATUS,
        human_validation_status=HUMAN_VALIDATION_STATUS,
        predictive_validity_status=PREDICTIVE_VALIDITY_STATUS,
        required_input_count=len(values),
        known_input_count=known,
        missing_input_count=missing,
        scenario_input_count=scenario,
        status_counts=tuple(sorted(counts.items())),
        temporal_status_counts=tuple(sorted(temporal_counts.items())),
        contract=QUALITY_CONTRACT_V2 if input_metadata is not None else QUALITY_CONTRACT,
    )


def quality_ui(quality: CalculationQuality | dict[str, object]) -> dict[str, str]:
    """Russian compact labels for UI; exact machine codes remain in JSON/title."""

    payload = quality.as_dict() if isinstance(quality, CalculationQuality) else quality
    computation = str(payload["computation_status"])
    evidence = str(payload["evidence_status"])
    admission = str(payload["scientific_admission_status"])
    return {
        "computation_code": computation,
        "computation_label": _COMPUTATION_LABELS_RU.get(computation, computation),
        "evidence_code": evidence,
        "evidence_label": _EVIDENCE_LABELS_RU.get(evidence, evidence),
        "admission_code": admission,
        "admission_label": "не установлен" if admission == SCIENTIFIC_ADMISSION_STATUS else admission,
    }
