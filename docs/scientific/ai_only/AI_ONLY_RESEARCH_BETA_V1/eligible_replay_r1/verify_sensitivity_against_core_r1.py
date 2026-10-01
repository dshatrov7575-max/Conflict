#!/usr/bin/env python3
"""Read-only parity check between frozen sensitivity output and pinned Calculation Core.

This utility does not select factors, repair primary outputs, tune weights, or create a
historical snapshot. It reconstructs each already-frozen scenario as an immutable
CalculationSnapshot, executes POLARIZATION_V1_BETA/1.0.0, JSON-replays the snapshot,
and compares the Core PTN metrics with the frozen sensitivity runner output.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any

Q8 = Decimal("0.00000001")


def load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def q8(value: object | None) -> str | None:
    if value is None:
        return None
    return format(Decimal(str(value)).quantize(Q8, rounding=ROUND_HALF_EVEN), "f")


def fail(message: str) -> None:
    raise ValueError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensitivity", required=True)
    parser.add_argument("--grid", required=True)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    sys.path.insert(0, str(repo_root / "software" / "conflict_analysis"))

    from calculation import (  # type: ignore
        ActorInput,
        CalculationSnapshot,
        InputValue,
        PtnInput,
        STRATEGY_ID,
        STRATEGY_VERSION,
        calculate,
    )

    sensitivity = load(args.sensitivity)
    grid = load(args.grid)

    if sensitivity.get("state") != "COMPUTED_READ_ONLY_RESEARCH_SCENARIOS":
        fail("sensitivity output is not computable")
    if sensitivity.get("calculation_release") is not True:
        fail("sensitivity calculation_release is not true")
    if sensitivity.get("historical_snapshot") != "NOT_ESTABLISHED":
        fail("historical snapshot boundary changed")
    if sensitivity.get("historical_area_UNO") != "NOT_COMPUTED":
        fail("historical area UNO boundary changed")

    route_id = sensitivity["route_id"]
    input_sha256 = sensitivity["input_sha256"]
    binding = sensitivity["actor_binding"]
    factor_record = sensitivity["factor_record"]
    actor_a = binding["actor_a"]
    actor_b = binding["actor_b"]
    ptn_id = binding["ptn_id"]

    if set(factor_record) != {actor_a, actor_b}:
        fail("factor actor set mismatch")

    def confirmed(value: object, source_id: str) -> InputValue:
        return InputValue(
            status="CONFIRMED",
            value=str(value),
            source_id=source_id,
            source_version="AI_ONLY_RESEARCH_BETA_V1",
        )

    def snapshot_for(scenario_id: str, ra: object, rb: object, q: object) -> CalculationSnapshot:
        actors = []
        for actor_id, rgu in ((actor_a, ra), (actor_b, rb)):
            row = factor_record[actor_id]
            actors.append(ActorInput(
                actor_id=actor_id,
                relation_id=f"{route_id}:{ptn_id}:{actor_id}:relation",
                assessment_id=f"{route_id}:{scenario_id}:{actor_id}:assessment",
                attitude=confirmed(row["POS_AO2"], f"{route_id}:CONSENSUS_POS"),
                kvs=confirmed(row["KVS_AO2"], f"{route_id}:CONSENSUS_KVS"),
                rgu=confirmed(rgu, f"AI_ONLY_COMMON_EXOGENOUS_WEIGHT_DESIGN_V2:{scenario_id}:RGU"),
            ))
        return CalculationSnapshot(
            experiment_id=f"AI_ONLY_READ_ONLY_SCENARIO:{route_id}:{scenario_id}",
            assessment_set_id=f"AI_ONLY_MANUAL_DUAL_MODEL_R1:{route_id}",
            project_id="CONFLICT_ANALYSIS_MVP7",
            time_slice_id=f"NON_HISTORICAL_SCENARIO_OBJECT:{route_id}",
            workspace_id="AI_ONLY_RESEARCH_BETA_V1",
            definition_version_id=f"{STRATEGY_ID}:{STRATEGY_VERSION}",
            definition_hash=input_sha256,
            time_slice_version="READ_ONLY_SCENARIO_R1",
            cutoff_date="NOT_A_HISTORICAL_SNAPSHOT",
            ptns=(PtnInput(
                ptn_id=ptn_id,
                kvptn=confirmed(q, f"AI_ONLY_COMMON_EXOGENOUS_WEIGHT_DESIGN_V2:{scenario_id}:KVPTN"),
                actors=tuple(actors),
            ),),
        )

    def core_metrics(snapshot: CalculationSnapshot) -> tuple[dict[str, Any], dict[str, Any]]:
        run = calculate(snapshot)
        replayed_snapshot = CalculationSnapshot.from_json(snapshot.to_json())
        replayed_run = calculate(replayed_snapshot)
        if run.to_json() != replayed_run.to_json():
            fail("Core JSON replay mismatch")
        if run.result_digest != replayed_run.result_digest:
            fail("Core result digest mismatch after replay")
        if len(run.ptns) != 1:
            fail("expected exactly one PTN")
        row = run.ptns[0]
        metrics = {
            "status": row.status,
            "W": q8(row.W),
            "P": q8(row.P),
            "N": q8(row.N),
            "A": q8(row.A),
            "B": q8(row.B),
            "Pol": q8(row.Pol),
            "single_ptn_uno_field": q8(run.UNO),
        }
        provenance = {
            "snapshot_id": snapshot.id,
            "snapshot_input_digest": snapshot.input_digest,
            "core_result_digest": run.result_digest,
            "core_run_status": run.status,
            "core_warnings": list(run.warnings),
        }
        return metrics, provenance

    checks: list[dict[str, Any]] = []

    def check_returned_scenario(container_name: str, scenario: dict[str, Any]) -> None:
        sid = scenario["scenario_id"]
        weights = scenario["weights"]
        ra = weights["RGU"][actor_a]
        rb = weights["RGU"][actor_b]
        q = weights["KVPTN"][ptn_id]
        snapshot = snapshot_for(sid, ra, rb, q)
        core, provenance = core_metrics(snapshot)
        runner = scenario["result"]
        compared_fields = ("status", "W", "P", "N", "A", "B", "Pol", "single_ptn_uno_field")
        mismatches = {
            field: {"runner": runner.get(field), "core": core.get(field)}
            for field in compared_fields if runner.get(field) != core.get(field)
        }
        if mismatches:
            fail(f"Core parity mismatch for {sid}: {mismatches}")
        checks.append({
            "scenario_id": sid,
            "family": container_name,
            "weights": weights,
            "metrics": core,
            **provenance,
            "parity": "PASS",
            "snapshot_json_replay": "PASS",
        })

    check_returned_scenario("BASELINE", sensitivity["baseline"])
    for scenario in sensitivity["positive_RGU_scenarios"]:
        check_returned_scenario("RGU_ONLY", scenario)
    for scenario in sensitivity["zero_weight_stress"]:
        check_returned_scenario("ZERO_WEIGHT_COVERAGE_STRESS", scenario)

    q_pols: list[str | None] = []
    q_checks: list[dict[str, Any]] = []
    for q in grid["positive_q_scale_checks"]:
        sid = "Q_SCALE_" + str(q).replace(".", "_")
        snapshot = snapshot_for(sid, "1", "1", q)
        metrics, provenance = core_metrics(snapshot)
        q_pols.append(metrics["Pol"])
        q_checks.append({
            "scenario_id": sid,
            "q": q8(q),
            "metrics": metrics,
            **provenance,
            "snapshot_json_replay": "PASS",
        })

    q_summary = sensitivity["positive_q_invariance"]
    observed = sorted({value for value in q_pols if value is not None})
    if q_summary.get("passed") is not True:
        fail("runner q-invariance did not pass")
    if q_summary.get("values_checked") != grid["positive_q_scale_checks"]:
        fail("q-invariance values_checked mismatch")
    if q_summary.get("observed_Pol_values") != observed:
        fail("q-invariance Core/runner Pol set mismatch")

    receipt = {
        "schema": "AI_ONLY_ELIGIBLE_LANE_CORE_REPLAY_RECEIPT_R1",
        "route_id": route_id,
        "input_sha256": input_sha256,
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "state": "PASS_CORE_PARITY",
        "scenario_count": len(checks) + len(q_checks),
        "returned_scenario_checks": checks,
        "positive_q_scale_core_checks": q_checks,
        "positive_q_invariance": {
            "passed": True,
            "observed_Pol_values": observed,
        },
        "all_snapshot_json_replays": "PASS",
        "all_core_result_digests_stable": True,
        "factor_or_weight_mutation": False,
        "coordinator_substitution": "FORBIDDEN",
        "historical_snapshot": "NOT_ESTABLISHED",
        "historical_area_UNO": "NOT_COMPUTED",
        "human_validation": "NOT_PERFORMED",
        "predictive_validation": "NOT_CLAIMED",
    }
    Path(args.out).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "route_id": route_id,
        "state": receipt["state"],
        "scenario_count": receipt["scenario_count"],
    }))


if __name__ == "__main__":
    main()
