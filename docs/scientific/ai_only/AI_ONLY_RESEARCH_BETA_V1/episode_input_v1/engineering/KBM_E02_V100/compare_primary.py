#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROUTE_ID = "AI_ONLY_DYAD_KBM_E02_V100"
CONTRACT_VERSION = "1.0.0"
RUBRIC_VERSION = "2.1.0"
INPUT_SHA256 = "d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42"
ACTOR_ID = "KBM_MANAGEMENT_FORMAL_RESPONSE_20110527"
ROLES = ("KBM_COMPANY_E02_V100_AI1", "KBM_COMPANY_E02_V100_AI2")
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


def validate(run: dict[str, Any], role: str) -> dict[str, dict[str, Any]]:
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
    if not isinstance(entries, list) or len(entries) != 2:
        raise ValueError("exactly two entries required")

    out: dict[str, dict[str, Any]] = {}
    for entry in entries:
        factor = entry.get("factor")
        if factor not in FACTORS or factor in out:
            raise ValueError("factor set mismatch or duplicate")
        if entry.get("actor_id") != ACTOR_ID:
            raise ValueError("actor_id mismatch")

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

        out[factor] = entry

    if set(out) != set(FACTORS):
        raise ValueError("factor set incomplete")
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
    for factor in FACTORS:
        a, b = left[factor], right[factor]
        rows.append({
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
        "inherited_worker_record": {
            "unit_id": "AO2S-C1-03",
            "actor_id": "AOV2_KBM_STRIKERS",
            "source_id": "D01-FPAY",
            "source_report_date": "2011-05-17",
            "POS_AO2": -5,
            "KVS_AO2": 5,
            "status": "INHERITED_TWO_PRIMARY_NUMERIC_AGREEMENT",
        },
        "company_entries": rows,
        "coordinator_substitution": "FORBIDDEN",
        "targeted_content_review_rounds": 0,
        "calculation_release": state == "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY",
        "simultaneous_snapshot": False,
        "carry_forward": "NONE",
        "historical_snapshot": "NOT_ESTABLISHED",
        "historical_area_UNO": "NOT_COMPUTED",
        "human_validation": "NOT_PERFORMED",
    }


def sample(role: str, pos=("NUMERIC", 5), kvs=("NUMERIC", 5), *, fail=None):
    fail = fail or {}
    entries = []
    for factor, (status, value) in (("POS_AO2", pos), ("KVS_AO2", kvs)):
        checks = {g: g not in set(fail.get(factor, ())) for g in GATES}
        entries.append({
            "actor_id": ACTOR_ID,
            "factor": factor,
            "status": status,
            "value": value,
            "admission_checks": checks,
            "evidence_references": ["KBM_NOMAD_PRESS_RESPONSE_20110527"],
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

    assert compare(sample(ROLES[0]), sample(ROLES[1]))["state"] == "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY"; cases += 1

    fail = {"KVS_AO2": ("C5",)}
    a = sample(ROLES[0], kvs=("UNKNOWN", None), fail=fail)
    b = sample(ROLES[1], kvs=("UNKNOWN", None), fail=fail)
    assert compare(a, b)["state"] == "HOLD_FACTOR_INCOMPLETE"; cases += 1

    a = sample(ROLES[0])
    b = sample(ROLES[1], kvs=("UNKNOWN", None), fail=fail)
    assert compare(a, b)["state"] == "HOLD_DISAGREEMENT"; cases += 1

    a = sample(ROLES[0], pos=("NUMERIC", 5))
    b = sample(ROLES[1], pos=("NUMERIC", 10))
    assert compare(a, b)["state"] == "HOLD_DISAGREEMENT"; cases += 1

    bad = sample(ROLES[0]); bad["attestation"]["other_coder_output_seen"] = True
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
    print(json.dumps({"state": result["state"], "entries": len(result["company_entries"])}))


if __name__ == "__main__":
    main()
