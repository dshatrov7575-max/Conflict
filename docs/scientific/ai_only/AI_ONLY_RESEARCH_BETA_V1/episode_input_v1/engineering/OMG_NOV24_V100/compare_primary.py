#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROUTE_ID = "AI_ONLY_DYAD_OMG_NOV24_V100"
CONTRACT_VERSION = "1.0.0"
RUBRIC_VERSION = "2.1.0"
INPUT_SHA256 = "72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4"
ROLES = ("OMG_NOV24_V100_AI1", "OMG_NOV24_V100_AI2")
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


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def validate(run: dict[str, Any], role: str) -> dict[tuple[str, str], dict[str, Any]]:
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
    if not isinstance(run.get("run_id"), str) or not run["run_id"].strip():
        raise ValueError("run_id missing")
    att = run.get("attestation")
    if not isinstance(att, dict):
        raise ValueError("attestation missing")
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
        status = entry.get("status")
        value = entry.get("value")
        checks = entry.get("admission_checks")
        if status not in STATUSES:
            raise ValueError("invalid status")
        if not isinstance(checks, dict) or set(checks) != set(GATES):
            raise ValueError("C1-C8 set mismatch")
        if any(type(checks[g]) is not bool for g in GATES):
            raise ValueError("C1-C8 values must be booleans")
        if entry.get("calculation_release") is not False:
            raise ValueError("primary calculation_release must be false")

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

    required = {(a, f) for a in ACTORS for f in FACTORS}
    if set(out) != required:
        raise ValueError("actor×factor set incomplete")
    return out


def compare_entry(a: dict[str, Any], b: dict[str, Any]) -> str:
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
                "triage": compare_entry(a, b),
            })

    triage = [row["triage"] for row in rows]
    if "HOLD_DISAGREEMENT" in triage:
        state = "HOLD_DISAGREEMENT"
    elif any(x in {"SHARED_UNKNOWN", "SHARED_DISPUTED"} for x in triage):
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
        "completed_at_utc": "2026-09-30T00:00:00Z",
        "attestation": {k: False for k in ATTESTATIONS},
        "entries": entries,
    }


def self_test() -> dict[str, Any]:
    cases = 0

    a, b = sample(ROLES[0]), sample(ROLES[1])
    assert compare(a, b)["state"] == "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY"; cases += 1

    key = (ACTORS[0], "KVS_AO2")
    ov = {key: ("UNKNOWN", None, ("C4",))}
    assert compare(sample(ROLES[0], ov), sample(ROLES[1], ov))["state"] == "HOLD_FACTOR_INCOMPLETE"; cases += 1

    a, b = sample(ROLES[0]), sample(ROLES[1], {key: ("UNKNOWN", None, ("C4",))})
    assert compare(a, b)["state"] == "HOLD_DISAGREEMENT"; cases += 1

    a, b = sample(ROLES[0]), sample(ROLES[1])
    b["entries"][0]["value"] = 10
    assert compare(a, b)["state"] == "HOLD_DISAGREEMENT"; cases += 1

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

    return {"self_test": "PASS", "cases": cases}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--ai1")
    p.add_argument("--ai2")
    p.add_argument("--out")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    if args.self_test:
        print(json.dumps(self_test()))
        return
    if not (args.ai1 and args.ai2 and args.out):
        p.error("--ai1, --ai2 and --out are required")

    result = compare(load(args.ai1), load(args.ai2))
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": result["state"], "entries": len(result["entries"])}))


if __name__ == "__main__":
    main()
