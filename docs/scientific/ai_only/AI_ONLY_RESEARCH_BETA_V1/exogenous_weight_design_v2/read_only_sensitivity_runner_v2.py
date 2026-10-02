#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

Q8 = Decimal("0.00000001")


class DesignInputError(ValueError):
    pass


def q8(value: Decimal) -> str:
    return format(value.quantize(Q8, rounding=ROUND_HALF_EVEN), "f")


def D(value: object) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise DesignInputError("finite numeric value required")
    try:
        out = Decimal(str(value))
    except Exception as exc:
        raise DesignInputError("invalid numeric value") from exc
    if not out.is_finite():
        raise DesignInputError("non-finite numeric value")
    return out


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def get_binding(bindings: dict[str, Any], route_id: str) -> dict[str, Any]:
    if bindings.get("status") != "FROZEN_BEFORE_NEW_PRIMARY_RESULTS":
        raise DesignInputError("lane bindings are not frozen")
    for row in bindings.get("lanes", []):
        if row.get("route_id") == route_id:
            return row
    raise DesignInputError("route_id not bound to frozen design")


def validate_grid(grid: dict[str, Any]) -> None:
    if grid.get("design_id") != "AI_ONLY_COMMON_EXOGENOUS_WEIGHT_DESIGN_V2":
        raise DesignInputError("wrong design_id")
    if grid.get("status") != "FROZEN_BEFORE_NEW_PRIMARY_RESULTS":
        raise DesignInputError("grid is not frozen")
    if grid.get("baseline") != {"r_actor_a": "1", "r_actor_b": "1", "q": "1"}:
        raise DesignInputError("unexpected baseline")
    if len(grid.get("positive_rgu_scenarios", [])) != 7:
        raise DesignInputError("positive RGU grid must contain seven scenarios")
    if grid.get("positive_q_scale_checks") != ["0.1", "1", "10"]:
        raise DesignInputError("q-scale checks mismatch")
    if len(grid.get("zero_weight_stress", [])) != 4:
        raise DesignInputError("zero-weight stress set mismatch")


def consensus_value(row: dict[str, Any]) -> Decimal:
    if row.get("triage") != "CONSENSUS_NUMERIC":
        raise DesignInputError("non-consensus factor row")
    if row.get("ai1_value") != row.get("ai2_value"):
        raise DesignInputError("consensus row values differ")
    return D(row.get("ai1_value"))


def extract_company_only(comparison: dict[str, Any], binding: dict[str, Any]) -> dict[str, dict[str, Decimal]]:
    inherited = comparison.get("inherited_worker_record")
    if not isinstance(inherited, dict):
        raise DesignInputError("missing inherited actor record")
    if inherited.get("actor_id") != binding["actor_a"]:
        raise DesignInputError("inherited actor identity mismatch")
    actor_a = {
        "POS": D(inherited.get("POS_AO2")),
        "KVS": D(inherited.get("KVS_AO2")),
    }

    values: dict[str, Decimal] = {}
    for row in comparison.get("company_entries", []):
        factor = row.get("factor")
        if factor in {"POS_AO2", "KVS_AO2"}:
            values[factor] = consensus_value(row)
    if set(values) != {"POS_AO2", "KVS_AO2"}:
        raise DesignInputError("company factor set incomplete")
    actor_b = {"POS": values["POS_AO2"], "KVS": values["KVS_AO2"]}
    return {binding["actor_a"]: actor_a, binding["actor_b"]: actor_b}


def extract_full_dyad(comparison: dict[str, Any], binding: dict[str, Any]) -> dict[str, dict[str, Decimal]]:
    values: dict[tuple[str, str], Decimal] = {}
    for row in comparison.get("entries", []):
        actor = row.get("actor_id")
        factor = row.get("factor")
        if actor in {binding["actor_a"], binding["actor_b"]} and factor in {"POS_AO2", "KVS_AO2"}:
            values[(actor, factor)] = consensus_value(row)
    required = {
        (binding["actor_a"], "POS_AO2"),
        (binding["actor_a"], "KVS_AO2"),
        (binding["actor_b"], "POS_AO2"),
        (binding["actor_b"], "KVS_AO2"),
    }
    if set(values) != required:
        raise DesignInputError("full dyad factor set incomplete")
    return {
        binding["actor_a"]: {
            "POS": values[(binding["actor_a"], "POS_AO2")],
            "KVS": values[(binding["actor_a"], "KVS_AO2")],
        },
        binding["actor_b"]: {
            "POS": values[(binding["actor_b"], "POS_AO2")],
            "KVS": values[(binding["actor_b"], "KVS_AO2")],
        },
    }


def extract_factors(comparison: dict[str, Any], binding: dict[str, Any]) -> dict[str, dict[str, Decimal]]:
    if comparison.get("route_id") != binding["route_id"]:
        raise DesignInputError("comparison route mismatch")
    if comparison.get("input_sha256") != binding["input_sha256"]:
        raise DesignInputError("comparison input hash mismatch")
    if comparison.get("state") != binding["eligibility_state"]:
        raise DesignInputError("comparison gate is not eligible")
    if comparison.get("calculation_release") is not True:
        raise DesignInputError("comparison calculation_release is not true")

    if binding["route_id"] in {"AI_ONLY_DYAD_KBM_E02_V100", "AI_ONLY_PAIR_KBM_E05_V100"}:
        factors = extract_company_only(comparison, binding)
    elif binding["route_id"] == "AI_ONLY_DYAD_OMG_NOV24_V100":
        factors = extract_full_dyad(comparison, binding)
    else:
        raise DesignInputError("unsupported bound route")

    for actor in (binding["actor_a"], binding["actor_b"]):
        pos, kvs = factors[actor]["POS"], factors[actor]["KVS"]
        if pos < -10 or pos > 10:
            raise DesignInputError("POS outside -10..10")
        if kvs < 0 or kvs > 10:
            raise DesignInputError("KVS outside 0..10")
    return factors


def calculate(
    factors: dict[str, dict[str, Decimal]],
    actor_a: str,
    actor_b: str,
    r_a: Decimal,
    r_b: Decimal,
    q: Decimal,
) -> dict[str, Any]:
    if min(r_a, r_b, q) < 0 or max(r_a, r_b, q) > 10:
        raise DesignInputError("weights must be within 0..10")

    W = Decimal(0)
    pos_num = Decimal(0)
    neg_num = Decimal(0)
    trace = []
    for actor, r in ((actor_a, r_a), (actor_b, r_b)):
        row = factors[actor]
        x, k = row["POS"], row["KVS"]
        w = r * k
        pos_num += Decimal(10) * w * max(x, Decimal(0))
        neg_num += Decimal(10) * w * max(-x, Decimal(0))
        W += w
        trace.append({
            "actor_id": actor,
            "POS": q8(x),
            "KVS": q8(k),
            "RGU": q8(r),
            "effective_weight": q8(w),
        })

    if W == 0:
        return {
            "status": "NOT_COMPUTABLE",
            "W": "0.00000000",
            "P": None,
            "N": None,
            "A": None,
            "B": None,
            "Pol": None,
            "single_ptn_uno_field": None,
            "q": q8(q),
            "trace": trace,
        }

    P = pos_num / W
    N = neg_num / W
    Pol = Decimal(2) * min(P, N)
    return {
        "status": "COMPLETE",
        "W": q8(W),
        "P": q8(P),
        "N": q8(N),
        "A": q8(P + N),
        "B": q8(P - N),
        "Pol": q8(Pol),
        "single_ptn_uno_field": None if q == 0 else q8(Pol),
        "q": q8(q),
        "trace": trace,
    }


def scenario(sid: str, family: str, factors, binding, r_a, r_b, q):
    ra, rb, qv = D(r_a), D(r_b), D(q)
    return {
        "scenario_id": sid,
        "family": family,
        "weights": {
            "RGU": {
                binding["actor_a"]: str(r_a),
                binding["actor_b"]: str(r_b),
            },
            "KVPTN": {binding["ptn_id"]: str(q)},
        },
        "result": calculate(
            factors,
            binding["actor_a"],
            binding["actor_b"],
            ra,
            rb,
            qv,
        ),
    }


def run(comparison: dict[str, Any], grid: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    validate_grid(grid)
    route_id = comparison.get("route_id")
    try:
        binding = get_binding(bindings, route_id)
        factors = extract_factors(comparison, binding)
    except DesignInputError as exc:
        return {
            "route_id": route_id,
            "design_id": grid.get("design_id"),
            "state": "NOT_COMPUTABLE",
            "reason": str(exc),
            "calculation_release": False,
            "historical_snapshot": "NOT_ESTABLISHED",
            "historical_area_UNO": "NOT_COMPUTED",
        }

    b = grid["baseline"]
    baseline = scenario(
        "BASELINE_EQUAL_POSITIVE", "BASELINE", factors, binding,
        b["r_actor_a"], b["r_actor_b"], b["q"],
    )

    main = [
        scenario(
            row["scenario_id"], "RGU_ONLY", factors, binding,
            row["r_actor_a"], row["r_actor_b"], "1",
        )
        for row in grid["positive_rgu_scenarios"]
    ]

    q_checks = [
        scenario(
            f"Q_SCALE_{q.replace('.', '_')}",
            "KVPTN_POSITIVE_SCALE_INVARIANCE",
            factors, binding, "1", "1", q,
        )
        for q in grid["positive_q_scale_checks"]
    ]
    q_pols = {x["result"]["Pol"] for x in q_checks}
    q_invariance = {
        "passed": len(q_pols) == 1,
        "values_checked": grid["positive_q_scale_checks"],
        "observed_Pol_values": sorted(q_pols),
        "interpretation": "Expected one-PTN q-scale invariance; not substantive KVPTN sensitivity.",
    }

    stress = [
        scenario(
            row["scenario_id"], "ZERO_WEIGHT_COVERAGE_STRESS", factors, binding,
            row["r_actor_a"], row["r_actor_b"], row["q"],
        )
        for row in grid["zero_weight_stress"]
    ]

    pols = [
        Decimal(x["result"]["Pol"])
        for x in main
        if x["result"]["Pol"] is not None
    ]
    return {
        "route_id": route_id,
        "input_sha256": binding["input_sha256"],
        "design_id": grid["design_id"],
        "state": "COMPUTED_READ_ONLY_RESEARCH_SCENARIOS",
        "actor_binding": {
            "actor_a": binding["actor_a"],
            "actor_b": binding["actor_b"],
            "ptn_id": binding["ptn_id"],
        },
        "factor_record": {
            actor: {
                "POS_AO2": int(row["POS"]),
                "KVS_AO2": int(row["KVS"]),
            }
            for actor, row in factors.items()
        },
        "baseline": baseline,
        "positive_RGU_scenarios": main,
        "positive_q_invariance": q_invariance,
        "zero_weight_stress": stress,
        "envelope": {
            "Pol_min": q8(min(pols)),
            "Pol_max": q8(max(pols)),
            "baseline_Pol": baseline["result"]["Pol"],
            "robustness_label": "NOT_ASSIGNED_BY_PROTOCOL",
        },
        "calculation_release": True,
        "metric_label": "SINGLE_PTN_PAIR_DYAD_SCENARIO_NOT_AREA_UNO",
        "historical_snapshot": "NOT_ESTABLISHED",
        "historical_area_UNO": "NOT_COMPUTED",
        "human_validation": "NOT_PERFORMED",
        "predictive_validation": "NOT_CLAIMED",
    }


def synthetic_company_comparison(route, input_sha, state, actor_a, company_pos=5, company_kvs=5):
    return {
        "route_id": route,
        "input_sha256": input_sha,
        "state": state,
        "inherited_worker_record": {
            "actor_id": actor_a,
            "POS_AO2": -5,
            "KVS_AO2": 5,
        },
        "company_entries": [
            {"factor": "POS_AO2", "triage": "CONSENSUS_NUMERIC", "ai1_value": company_pos, "ai2_value": company_pos},
            {"factor": "KVS_AO2", "triage": "CONSENSUS_NUMERIC", "ai1_value": company_kvs, "ai2_value": company_kvs},
        ],
        "calculation_release": True,
    }


def synthetic_full_comparison(binding, a_pos=-5, a_kvs=5, b_pos=5, b_kvs=5):
    rows = []
    for actor, pos, kvs in (
        (binding["actor_a"], a_pos, a_kvs),
        (binding["actor_b"], b_pos, b_kvs),
    ):
        rows += [
            {"actor_id": actor, "factor": "POS_AO2", "triage": "CONSENSUS_NUMERIC", "ai1_value": pos, "ai2_value": pos},
            {"actor_id": actor, "factor": "KVS_AO2", "triage": "CONSENSUS_NUMERIC", "ai1_value": kvs, "ai2_value": kvs},
        ]
    return {
        "route_id": binding["route_id"],
        "input_sha256": binding["input_sha256"],
        "state": binding["eligibility_state"],
        "entries": rows,
        "calculation_release": True,
    }


def self_test(grid: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    validate_grid(grid)
    lanes = {x["route_id"]: x for x in bindings["lanes"]}
    cases = 0

    b = lanes["AI_ONLY_DYAD_KBM_E02_V100"]
    c = synthetic_company_comparison(b["route_id"], b["input_sha256"], b["eligibility_state"], b["actor_a"])
    out = run(c, grid, bindings)
    assert out["baseline"]["result"]["Pol"] == "50.00000000"; cases += 1
    assert out["envelope"] == {"Pol_min": "9.09090909", "Pol_max": "50.00000000", "baseline_Pol": "50.00000000", "robustness_label": "NOT_ASSIGNED_BY_PROTOCOL"}; cases += 1
    assert out["positive_q_invariance"]["passed"] is True; cases += 1
    zero_a = next(x for x in out["zero_weight_stress"] if x["scenario_id"] == "R_ACTOR_A_ZERO")
    assert zero_a["result"]["Pol"] == "0.00000000"; cases += 1
    all_zero = next(x for x in out["zero_weight_stress"] if x["scenario_id"] == "R_ALL_ZERO")
    assert all_zero["result"]["status"] == "NOT_COMPUTABLE"; cases += 1

    b2 = lanes["AI_ONLY_DYAD_OMG_NOV24_V100"]
    out2 = run(synthetic_full_comparison(b2), grid, bindings)
    assert out2["state"] == "COMPUTED_READ_ONLY_RESEARCH_SCENARIOS"; cases += 1
    assert out2["baseline"]["result"]["Pol"] == "50.00000000"; cases += 1

    b3 = lanes["AI_ONLY_PAIR_KBM_E05_V100"]
    c3 = synthetic_company_comparison(b3["route_id"], b3["input_sha256"], b3["eligibility_state"], b3["actor_a"], company_pos=5, company_kvs=8)
    out3 = run(c3, grid, bindings)
    assert out3["baseline"]["result"]["Pol"] == "38.46153846"; cases += 1

    bad = dict(c)
    bad["state"] = "HOLD_FACTOR_INCOMPLETE"
    bad["calculation_release"] = False
    assert run(bad, grid, bindings)["state"] == "NOT_COMPUTABLE"; cases += 1

    bad_hash = dict(c)
    bad_hash["input_sha256"] = "0" * 64
    assert run(bad_hash, grid, bindings)["state"] == "NOT_COMPUTABLE"; cases += 1

    return {"self_test": "PASS", "cases": cases}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--comparison")
    p.add_argument("--grid", required=True)
    p.add_argument("--bindings", required=True)
    p.add_argument("--out")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    grid = load(args.grid)
    bindings = load(args.bindings)

    if args.self_test:
        print(json.dumps(self_test(grid, bindings)))
        return

    if not (args.comparison and args.out):
        p.error("--comparison and --out required unless --self-test")
    result = run(load(args.comparison), grid, bindings)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": result["state"], "route_id": result.get("route_id")}))


if __name__ == "__main__":
    main()
