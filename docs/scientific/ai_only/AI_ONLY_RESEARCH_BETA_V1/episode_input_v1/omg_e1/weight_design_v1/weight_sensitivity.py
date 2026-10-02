#!/usr/bin/env python3
"""Deterministic weight-sensitivity runner for one frozen MVP7 episode/PTN.

This utility is a read-only research helper. It does not write to Foundation,
ParameterValue, CalculationSnapshot, or CalculationRun, and it does not assign
historical RGU/KVPTN. The input weights are exogenous design parameters.
"""
from __future__ import annotations

import argparse
import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from typing import Any

EPISODE_ID = "OMG_INITIAL_WAGE_DISPUTE_2011_05_26_2011_06_28"
PTN_ID = "E02_PAY"
WORKER = "OMG_WORKERS_INITIAL_STRIKE"
COMPANY = "KMG_EP_MANAGEMENT_FORMAL_RESPONSE"


class SensitivityInputError(ValueError):
    pass


def _fraction(value: object) -> Fraction:
    if isinstance(value, bool) or value is None:
        raise SensitivityInputError("Expected a finite numeric value.")
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise SensitivityInputError("Invalid numeric value.") from exc
    if not number.is_finite():
        raise SensitivityInputError("Value must be finite.")
    return Fraction(number)


def _rounded(number: Fraction) -> str:
    """Eight decimal places, ties to even, matching POLARIZATION_V1_BETA."""
    scaled = abs(number) * 100_000_000
    whole, remainder = divmod(scaled.numerator, scaled.denominator)
    twice = 2 * remainder
    if twice > scaled.denominator or (twice == scaled.denominator and whole % 2):
        whole += 1
    sign = "-" if number < 0 and whole else ""
    return f"{sign}{whole // 100_000_000}.{whole % 100_000_000:08d}"


def _validate_factor_record(payload: dict[str, Any]) -> dict[str, dict[str, Fraction]]:
    if payload.get("episode_id") != EPISODE_ID:
        raise SensitivityInputError("Unexpected episode_id.")
    if payload.get("ptn_id") != PTN_ID:
        raise SensitivityInputError("Unexpected ptn_id.")
    actors = payload.get("actors")
    if not isinstance(actors, dict) or set(actors) != {WORKER, COMPANY}:
        raise SensitivityInputError("Factor input must contain exactly the two frozen actors.")

    out: dict[str, dict[str, Fraction]] = {}
    for actor_id in (WORKER, COMPANY):
        row = actors[actor_id]
        if not isinstance(row, dict):
            raise SensitivityInputError("Actor factor row must be an object.")
        if row.get("status") != "VERIFIED_NUMERIC":
            raise SensitivityInputError(f"{actor_id} is not VERIFIED_NUMERIC.")
        pos = _fraction(row.get("POS"))
        kvs = _fraction(row.get("KVS"))
        if pos < -10 or pos > 10:
            raise SensitivityInputError("POS outside -10..10.")
        if kvs < 0 or kvs > 10:
            raise SensitivityInputError("KVS outside 0..10.")
        out[actor_id] = {"POS": pos, "KVS": kvs}
    return out


def _validate_grid(grid: dict[str, Any]) -> None:
    if grid.get("episode_id") != EPISODE_ID or grid.get("ptn_id") != PTN_ID:
        raise SensitivityInputError("Grid identity mismatch.")
    if grid.get("status") != "FROZEN_BEFORE_EPISODE_PRIMARY_RESPONSES":
        raise SensitivityInputError("Grid is not the frozen preregistered version.")
    baseline = grid.get("baseline", {})
    if baseline.get("rgu") != {WORKER: "1", COMPANY: "1"}:
        raise SensitivityInputError("Unexpected baseline RGU.")
    if baseline.get("kvptn") != {PTN_ID: "1"}:
        raise SensitivityInputError("Unexpected baseline KVPTN.")


def compute_ptn(
    factors: dict[str, dict[str, Fraction]],
    r_worker: Fraction,
    r_company: Fraction,
    q: Fraction,
) -> dict[str, Any]:
    if r_worker < 0 or r_company < 0 or q < 0:
        raise SensitivityInputError("Weights must be nonnegative.")
    if r_worker > 10 or r_company > 10 or q > 10:
        raise SensitivityInputError("Weights must be within 0..10.")

    rows = (
        (WORKER, factors[WORKER], r_worker),
        (COMPANY, factors[COMPANY], r_company),
    )
    W = Fraction(0)
    positive = Fraction(0)
    negative = Fraction(0)
    traces = []
    for actor_id, row, rgu in rows:
        x, c = row["POS"], row["KVS"]
        w = rgu * c
        p = 10 * w * max(x, 0)
        n = 10 * w * max(-x, 0)
        W += w
        positive += p
        negative += n
        traces.append({
            "actor_id": actor_id,
            "POS": _rounded(x),
            "KVS": _rounded(c),
            "RGU": _rounded(rgu),
            "effective_weight": _rounded(w),
        })

    if not W:
        return {
            "ptn_status": "NOT_COMPUTABLE",
            "W": "0.00000000",
            "P": None,
            "N": None,
            "A": None,
            "B": None,
            "Pol": None,
            "single_ptn_uno_field": None,
            "q": _rounded(q),
            "trace": traces,
        }

    P = positive / W
    N = negative / W
    Pol = 2 * min(P, N)
    uno = None if not q else Pol
    return {
        "ptn_status": "COMPLETE",
        "W": _rounded(W),
        "P": _rounded(P),
        "N": _rounded(N),
        "A": _rounded(P + N),
        "B": _rounded(P - N),
        "Pol": _rounded(Pol),
        "single_ptn_uno_field": None if uno is None else _rounded(uno),
        "q": _rounded(q),
        "trace": traces,
    }


def _scenario_result(
    scenario_id: str,
    factors: dict[str, dict[str, Fraction]],
    r_worker: object,
    r_company: object,
    q: object,
    family: str,
) -> dict[str, Any]:
    rw, rc, qf = _fraction(r_worker), _fraction(r_company), _fraction(q)
    return {
        "scenario_id": scenario_id,
        "family": family,
        "weights": {
            "RGU": {WORKER: str(r_worker), COMPANY: str(r_company)},
            "KVPTN": {PTN_ID: str(q)},
        },
        "result": compute_ptn(factors, rw, rc, qf),
    }


def run(factor_payload: dict[str, Any], grid: dict[str, Any]) -> dict[str, Any]:
    _validate_grid(grid)
    try:
        factors = _validate_factor_record(factor_payload)
    except SensitivityInputError as exc:
        return {
            "episode_id": EPISODE_ID,
            "ptn_id": PTN_ID,
            "state": "NOT_COMPUTABLE",
            "reason": str(exc),
            "baseline": None,
            "main_positive_scenarios": [],
            "positive_q_invariance": None,
            "zero_weight_stress": [],
            "claims": {
                "historical_area_UNO": "NOT_COMPUTED",
                "human_validation": "NOT_PERFORMED",
                "weight_values": "EXOGENOUS_ANALYTIC_DESIGN",
            },
        }

    baseline = _scenario_result(
        "BASELINE_EQUAL_POSITIVE",
        factors,
        "1",
        "1",
        "1",
        "BASELINE",
    )

    main = []
    for row in grid["rgu_relative_scenarios"]:
        main.append(_scenario_result(
            row["scenario_id"],
            factors,
            row["r_worker"],
            row["r_company"],
            "1",
            "RGU_ONLY",
        ))

    q_checks = []
    for q in grid["positive_q_scale_checks"]:
        q_checks.append(_scenario_result(
            f"Q_SCALE_{str(q).replace('.', '_')}",
            factors,
            "1",
            "1",
            q,
            "KVPTN_POSITIVE_SCALE_INVARIANCE",
        ))
    q_pols = {row["result"]["Pol"] for row in q_checks}
    q_invariance = {
        "passed": len(q_pols) == 1,
        "values_checked": [str(q) for q in grid["positive_q_scale_checks"]],
        "observed_Pol_values": sorted(q_pols),
        "interpretation": (
            "Expected algebraic invariance for a one-PTN topology; "
            "not substantive KVPTN sensitivity."
        ),
    }

    stress = []
    for row in grid["zero_weight_stress"]:
        stress.append(_scenario_result(
            row["scenario_id"],
            factors,
            row["r_worker"],
            row["r_company"],
            row["q"],
            "ZERO_WEIGHT_COVERAGE_STRESS",
        ))

    computed_pols = [
        Decimal(row["result"]["Pol"])
        for row in main
        if row["result"]["Pol"] is not None
    ]
    envelope = {
        "main_positive_scenarios": len(main),
        "Pol_min": f"{min(computed_pols):.8f}" if computed_pols else None,
        "Pol_max": f"{max(computed_pols):.8f}" if computed_pols else None,
        "baseline_Pol": baseline["result"]["Pol"],
        "robustness_label": "NOT_ASSIGNED_BY_PROTOCOL",
    }

    return {
        "episode_id": EPISODE_ID,
        "ptn_id": PTN_ID,
        "state": "COMPUTED_RESEARCH_SCENARIOS",
        "baseline": baseline,
        "main_positive_scenarios": main,
        "positive_q_invariance": q_invariance,
        "zero_weight_stress": stress,
        "envelope": envelope,
        "claims": {
            "historical_area_UNO": "NOT_COMPUTED",
            "single_ptn_uno_field": (
                "Numerically equal to Pol when q>0, but not reported as an "
                "area-level historical UNO."
            ),
            "human_validation": "NOT_PERFORMED",
            "human_reliability": "NOT_PERFORMED",
            "weight_values": "EXOGENOUS_ANALYTIC_DESIGN",
            "strict_v1_overwritten": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--factors", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    factor_payload = json.loads(args.factors.read_text(encoding="utf-8-sig"))
    grid = json.loads(args.grid.read_text(encoding="utf-8-sig"))
    result = run(factor_payload, grid)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
