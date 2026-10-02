#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path

GRID = (
    ("WORKER_DOMINANT_10_1", Decimal("10"), Decimal("1")),
    ("WORKER_DOMINANT_4_1", Decimal("4"), Decimal("1")),
    ("WORKER_DOMINANT_2_1", Decimal("2"), Decimal("1")),
    ("EQUAL_1_1", Decimal("1"), Decimal("1")),
    ("COMPANY_DOMINANT_1_2", Decimal("1"), Decimal("2")),
    ("COMPANY_DOMINANT_1_4", Decimal("1"), Decimal("4")),
    ("COMPANY_DOMINANT_1_10", Decimal("1"), Decimal("10")),
)
Q8 = Decimal("0.00000001")


def q8(value: Decimal) -> str:
    return format(value.quantize(Q8, rounding=ROUND_HALF_EVEN), "f")


def calculate(worker_pos: Decimal, worker_kvs: Decimal,
              company_pos: Decimal, company_kvs: Decimal,
              worker_rgu: Decimal, company_rgu: Decimal) -> dict:
    rows = (
        ("OMG_WORKERS_INITIAL_STRIKE", worker_pos, worker_kvs, worker_rgu),
        ("RD_KMG_MANAGEMENT_FORMAL_RESPONSE_20110812", company_pos, company_kvs, company_rgu),
    )
    W = Decimal(0); pos_num = Decimal(0); neg_num = Decimal(0); trace = []
    for actor, x, k, r in rows:
        w = k * r
        p = Decimal(10) * w * max(x, Decimal(0))
        n = Decimal(10) * w * max(-x, Decimal(0))
        W += w; pos_num += p; neg_num += n
        trace.append({"actor_id": actor, "POS": q8(x), "KVS": q8(k), "RGU": q8(r), "effective_weight": q8(w)})
    if W == 0:
        return {"status": "NOT_COMPUTABLE", "trace": trace}
    P = pos_num / W; N = neg_num / W; A = P + N; B = P - N; Pol = Decimal(2) * min(P, N)
    return {"status": "COMPLETE", "W": q8(W), "P": q8(P), "N": q8(N), "A": q8(A), "B": q8(B), "Pol": q8(Pol), "trace": trace}


def extract_company(comparison: dict) -> tuple[Decimal, Decimal]:
    if comparison.get("state") != "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY":
        raise ValueError("comparison gate is not eligible")
    values = {}
    for row in comparison.get("company_entries", []):
        if row.get("triage") != "CONSENSUS_NUMERIC":
            raise ValueError("non-numeric company entry")
        if row.get("ai1_value") != row.get("ai2_value"):
            raise ValueError("company values do not match")
        values[row["factor"]] = Decimal(str(row["ai1_value"]))
    if set(values) != {"POS_AO2", "KVS_AO2"}:
        raise ValueError("company factor set incomplete")
    return values["POS_AO2"], values["KVS_AO2"]


def run(comparison: dict) -> dict:
    try:
        company_pos, company_kvs = extract_company(comparison)
    except ValueError as exc:
        return {
            "object_label": "AI_ONLY_DEMAND_TO_FORMAL_RESPONSE_DYAD_V102",
            "state": "HOLD_FACTOR_INCOMPLETE",
            "reason": str(exc),
            "calculation_release": False,
            "historical_snapshot": "NOT_ESTABLISHED",
            "historical_area_UNO": "NOT_COMPUTED"
        }
    scenarios = []
    for scenario_id, rw, rc in GRID:
        scenarios.append({
            "scenario_id": scenario_id,
            "weights": {"worker_RGU": q8(rw), "company_RGU": q8(rc), "KVPTN": "1.00000000"},
            "result": calculate(Decimal("-5"), Decimal("5"), company_pos, company_kvs, rw, rc)
        })
    pol = [Decimal(row["result"]["Pol"]) for row in scenarios if row["result"]["status"] == "COMPLETE"]
    return {
        "object_label": "AI_ONLY_DEMAND_TO_FORMAL_RESPONSE_DYAD_V102",
        "state": "COMPUTED_READ_ONLY_RESEARCH_SCENARIOS",
        "inherited_worker_factors": {"POS_AO2": -5, "KVS_AO2": 5},
        "company_consensus_factors": {"POS_AO2": int(company_pos), "KVS_AO2": int(company_kvs)},
        "baseline": next(row for row in scenarios if row["scenario_id"] == "EQUAL_1_1"),
        "positive_RGU_scenarios": scenarios,
        "envelope": {"Pol_min": q8(min(pol)), "Pol_max": q8(max(pol))},
        "calculation_release": True,
        "metric_label": "DYAD_POL_SCENARIO_NOT_AREA_UNO",
        "historical_snapshot": "NOT_ESTABLISHED",
        "historical_area_UNO": "NOT_COMPUTED",
        "human_validation": "NOT_PERFORMED",
        "predictive_validation": "NOT_CLAIMED"
    }


def self_test() -> None:
    def comparison(pos, kvs, eligible=True):
        state = "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY" if eligible else "HOLD_FACTOR_INCOMPLETE"
        return {"state": state, "company_entries": [
            {"factor": "POS_AO2", "triage": "CONSENSUS_NUMERIC", "ai1_value": pos, "ai2_value": pos},
            {"factor": "KVS_AO2", "triage": "CONSENSUS_NUMERIC", "ai1_value": kvs, "ai2_value": kvs}
        ]}
    assert run(comparison(5, 5))["baseline"]["result"]["Pol"] == "50.00000000"
    assert run(comparison(5, 8))["baseline"]["result"]["Pol"] == "38.46153846"
    assert run(comparison(0, 5))["baseline"]["result"]["Pol"] == "0.00000000"
    assert run(comparison(5, 5, eligible=False))["state"] == "HOLD_FACTOR_INCOMPLETE"
    print(json.dumps({"self_test": "PASS", "cases": 4}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparison"); parser.add_argument("--out"); parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if not (args.comparison and args.out):
        parser.error("--comparison and --out required")
    comparison = json.loads(Path(args.comparison).read_text(encoding="utf-8-sig"))
    result = run(comparison)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": result["state"]}))


if __name__ == "__main__":
    main()
