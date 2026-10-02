#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROUTE_ID = "AI_ONLY_DYAD_OMG_NOV24_V101"
CONTRACT_VERSION = "1.0.1"
RUBRIC_VERSION = "2.1.0"
INPUT_SHA256 = "72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4"
ROLES = ("OMG_NOV24_V101_AI1", "OMG_NOV24_V101_AI2")
ACTORS = (
    "OMG_DISMISSED_WORKERS_NOV23_24_AS_REPORTED_CONTUR",
    "RD_KMG_OMG_EMPLOYER_SIDE_NOV23_24_AS_REPORTED_CONTUR",
)
FACTORS = ("POS_AO2", "KVS_AO2")
GATES = tuple(f"C{i}" for i in range(1, 9))
STATUSES = {"NUMERIC", "UNKNOWN", "DISPUTED"}
POS_VALUES = {-10, -5, 0, 5, 10}
KVS_VALUES = {0, 2, 5, 8, 10}
ATTESTATIONS = (
    "other_coder_output_seen",
    "prior_episode_outputs_seen",
    "outcome_used_as_evidence",
    "external_sources_used",
)
TOP_LEVEL = {
    "route_id", "contract_version", "rubric_version", "input_sha256",
    "coder_role", "actual_model_label", "model_label_source", "run_id",
    "completed_at_utc", "attestation", "entries",
}
CONFIDENCE_VALUES = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def nonempty_text(run: dict[str, Any], key: str) -> str:
    value = run.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} missing")
    return value.strip()


def validate(run: dict[str, Any], role: str) -> dict[tuple[str, str], dict[str, Any]]:
    if set(run) != TOP_LEVEL:
        raise ValueError("top-level field set mismatch")
    if run.get("route_id") != ROUTE_ID:
        raise ValueError("route_id mismatch")
    if run.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("contract_version mismatch")
    if run.get("rubric_version") != RUBRIC_VERSION:
        raise ValueError("rubric_version mismatch")
    if run.get("input_sha256") != INPUT_SHA256:
        raise ValueError("input_sha256 mismatch")
    if run.get("coder_role") != role:
        raise ValueError("coder_role mismatch")

    nonempty_text(run, "actual_model_label")
    nonempty_text(run, "model_label_source")
    nonempty_text(run, "run_id")
    completed = nonempty_text(run, "completed_at_utc")
    if not completed.endswith("Z"):
        raise ValueError("completed_at_utc must end in Z")

    att = run.get("attestation")
    if not isinstance(att, dict) or set(att) != set(ATTESTATIONS):
        raise ValueError("attestation field set mismatch")
    for key in ATTESTATIONS:
        if att.get(key) is not False:
            raise ValueError(f"ineligible attestation: {key}")

    entries = run.get("entries")
    if not isinstance(entries, list) or len(entries) != 4:
        raise ValueError("exactly four entries required")

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        actor = entry.get("actor_id")
        factor = entry.get("factor")
        key = (actor, factor)
        if actor not in ACTORS or factor not in FACTORS or key in out:
            raise ValueError("actor×factor set mismatch or duplicate")

        required_entry = {
            "actor_id", "factor", "status", "value", "admission_checks",
            "evidence_references", "rationale", "confidence", "calculation_release",
        }
        if set(entry) != required_entry:
            raise ValueError("entry field set mismatch")

        status = entry.get("status")
        value = entry.get("value")
        checks = entry.get("admission_checks")
        if status not in STATUSES:
            raise ValueError("invalid status")
        if not isinstance(checks, dict) or set(checks) != set(GATES):
            raise ValueError("C1-C8 set mismatch")
        if any(type(checks[g]) is not bool for g in GATES):
            raise ValueError("C1-C8 values must be booleans")
        if not isinstance(entry.get("evidence_references"), list):
            raise ValueError("evidence_references must be a list")
        if not isinstance(entry.get("rationale"), str) or not entry["rationale"].strip():
            raise ValueError("rationale missing")
        if entry.get("calculation_release") is not False:
            raise ValueError("primary calculation_release must be false")

        confidence = entry.get("confidence")
        if not isinstance(confidence, dict) or set(confidence) != {"kind", "value", "meaning", "rationale"}:
            raise ValueError("confidence field set mismatch")
        if confidence.get("kind") != "QUALITATIVE_UNCALIBRATED":
            raise ValueError("confidence kind mismatch")
        if confidence.get("value") not in CONFIDENCE_VALUES:
            raise ValueError("confidence value mismatch")
        if confidence.get("meaning") != "CONFIDENCE_IN_RECORDED_CODING_DECISION":
            raise ValueError("confidence meaning mismatch")
        if not isinstance(confidence.get("rationale"), str) or not confidence["rationale"].strip():
            raise ValueError("confidence rationale missing")

        if status == "NUMERIC":
            allowed = POS_VALUES if factor == "POS_AO2" else KVS_VALUES
            if value not in allowed:
                raise ValueError("unlicensed numeric anchor")
            if not all(checks[g] for g in GATES):
                raise ValueError("NUMERIC with failed gate")
        elif status == "UNKNOWN":
            if value is not None:
                raise ValueError("UNKNOWN value must be null")
            if all(checks[g] for g in GATES):
                raise ValueError("UNKNOWN must expose at least one failed gate")
        else:
            if value is not None:
                raise ValueError("DISPUTED value must be null")
        out[key] = entry

    if set(out) != {(a, f) for a in ACTORS for f in FACTORS}:
        raise ValueError("actor×factor set incomplete")
    return out


def triage(a: dict[str, Any], b: dict[str, Any]) -> str:
    same = (
        a["status"] == b["status"]
        and a.get("value") == b.get("value")
        and a["admission_checks"] == b["admission_checks"]
    )
    if not same:
        return "HOLD_DISAGREEMENT"
    if a["status"] == "NUMERIC":
        return "CONSENSUS_NUMERIC"
    if a["status"] == "UNKNOWN":
        return "SHARED_UNKNOWN"
    return "SHARED_DISPUTED"


def compare(ai1: dict[str, Any], ai2: dict[str, Any]) -> dict[str, Any]:
    if ai1.get("run_id") == ai2.get("run_id"):
        raise ValueError("run_id must differ")
    left = validate(ai1, ROLES[0])
    right = validate(ai2, ROLES[1])

    rows = []
    for actor in ACTORS:
        for factor in FACTORS:
            a, b = left[(actor, factor)], right[(actor, factor)]
            rows.append({
                "actor_id": actor,
                "factor": factor,
                "ai1_status": a["status"],
                "ai1_value": a.get("value"),
                "ai2_status": b["status"],
                "ai2_value": b.get("value"),
                "same_C1_C8": a["admission_checks"] == b["admission_checks"],
                "triage": triage(a, b),
            })

    states = [row["triage"] for row in rows]
    if "HOLD_DISAGREEMENT" in states:
        state = "HOLD_DISAGREEMENT"
    elif any(x in {"SHARED_UNKNOWN", "SHARED_DISPUTED"} for x in states):
        state = "HOLD_FACTOR_INCOMPLETE"
    else:
        state = "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY"

    return {
        "route_id": ROUTE_ID,
        "contract_version": CONTRACT_VERSION,
        "input_sha256": INPUT_SHA256,
        "state": state,
        "entries": rows,
        "coordinator_substitution": "FORBIDDEN",
        "targeted_content_review_rounds": 0,
        "calculation_release": state == "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY",
        "simultaneous_snapshot": False,
        "carry_forward": "NONE",
        "historical_snapshot": "NOT_ESTABLISHED",
        "historical_area_UNO": "NOT_COMPUTED",
        "human_validation": "NOT_PERFORMED",
        "technical_repair_route": "AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR",
    }


def sample(role: str, overrides: dict[tuple[str, str], tuple[str, Any, tuple[str, ...]]] | None = None):
    overrides = overrides or {}
    entries = []
    for actor in ACTORS:
        for factor in FACTORS:
            status, value, failed = overrides.get((actor, factor), ("NUMERIC", 5, ()))
            checks = {g: g not in set(failed) for g in GATES}
            entries.append({
                "actor_id": actor,
                "factor": factor,
                "status": status,
                "value": value,
                "admission_checks": checks,
                "evidence_references": ["CONTUR_1822_20111130"],
                "rationale": "synthetic self-test",
                "confidence": {
                    "kind": "QUALITATIVE_UNCALIBRATED",
                    "value": "HIGH",
                    "meaning": "CONFIDENCE_IN_RECORDED_CODING_DECISION",
                    "rationale": "synthetic self-test",
                },
                "calculation_release": False,
            })
    return {
        "route_id": ROUTE_ID,
        "contract_version": CONTRACT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "input_sha256": INPUT_SHA256,
        "coder_role": role,
        "actual_model_label": "SYNTHETIC",
        "model_label_source": "SELF_TEST",
        "run_id": role + "-run",
        "completed_at_utc": "2026-10-01T00:00:00Z",
        "attestation": {k: False for k in ATTESTATIONS},
        "entries": entries,
    }


def self_test() -> dict[str, Any]:
    cases = 0
    assert compare(sample(ROLES[0]), sample(ROLES[1]))["state"] == "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY"; cases += 1

    key = (ACTORS[0], "KVS_AO2")
    unknown = {key: ("UNKNOWN", None, ("C4",))}
    assert compare(sample(ROLES[0], unknown), sample(ROLES[1], unknown))["state"] == "HOLD_FACTOR_INCOMPLETE"; cases += 1
    assert compare(sample(ROLES[0]), sample(ROLES[1], unknown))["state"] == "HOLD_DISAGREEMENT"; cases += 1

    different = sample(ROLES[1]); different["entries"][0]["value"] = 10
    assert compare(sample(ROLES[0]), different)["state"] == "HOLD_DISAGREEMENT"; cases += 1

    bad = sample(ROLES[0]); bad["attestation"]["external_sources_used"] = True
    try: validate(bad, ROLES[0])
    except ValueError: cases += 1
    else: raise AssertionError("contaminated attestation accepted")

    bad = sample(ROLES[0]); bad["entries"][0]["admission_checks"]["C6"] = False
    try: validate(bad, ROLES[0])
    except ValueError: cases += 1
    else: raise AssertionError("NUMERIC with failed gate accepted")

    bad = sample(ROLES[0]); bad["entries"].append(dict(bad["entries"][0]))
    try: validate(bad, ROLES[0])
    except ValueError: cases += 1
    else: raise AssertionError("extra entry accepted")

    bad = sample(ROLES[0]); bad["entries"][0]["value"] = 8
    try: validate(bad, ROLES[0])
    except ValueError: cases += 1
    else: raise AssertionError("unlicensed POS anchor accepted")

    bad = sample(ROLES[0]); bad["run_id"] = ""
    try: validate(bad, ROLES[0])
    except ValueError: cases += 1
    else: raise AssertionError("missing run_id accepted")

    bad = sample(ROLES[0]); bad.pop("completed_at_utc")
    try: validate(bad, ROLES[0])
    except ValueError: cases += 1
    else: raise AssertionError("missing top-level field accepted")

    return {"self_test": "PASS", "cases": cases}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai1")
    parser.add_argument("--ai2")
    parser.add_argument("--out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test()))
        return
    if not (args.ai1 and args.ai2 and args.out):
        parser.error("--ai1, --ai2 and --out are required")

    result = compare(load(args.ai1), load(args.ai2))
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": result["state"], "entries": len(result["entries"])}))


if __name__ == "__main__":
    main()
