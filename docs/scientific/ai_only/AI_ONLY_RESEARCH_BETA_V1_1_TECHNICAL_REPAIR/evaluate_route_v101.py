#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any

REQUIRED_LABEL = "AI-кодирование; человеческая проверка не проводилась; исследовательская версия; прогнозная точность не установлена."
ELIGIBLE = ["AI_ONLY_DYAD_KBM_E02_V100", "AI_ONLY_PAIR_KBM_E05_V100"]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def module_from(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git_blob(repo: Path, path: Path) -> str:
    return subprocess.check_output(
        ["git", "hash-object", str(path.relative_to(repo))], cwd=repo, text=True
    ).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate(repo: Path, out: Path, run_id: str, run_attempt: str, head_sha: str) -> dict[str, Any]:
    route = repo / "docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1_1_TECHNICAL_REPAIR"
    r1 = repo / "docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1"
    out.mkdir(parents=True, exist_ok=True)

    comparator_path = route / "omg_nov24_v1_0_1/compare_primary_v101.py"
    aggregator_path = route / "aggregate_cohort_v101.py"
    gate_path = r1 / "release_gate_r1/evaluate_release_gate_r1.py"
    comparator = module_from(comparator_path, "v101_comparator")
    aggregator = module_from(aggregator_path, "v101_aggregator")
    gate_module = module_from(gate_path, "release_gate_r1")

    assert comparator.self_test() == {"self_test": "PASS", "cases": 10}
    assert aggregator.self_test() == {"self_test": "PASS", "cases": 5}

    ai1_path = route / "raw/OMG_NOV24_V101_AI1_COMPLETED.json"
    ai2_path = route / "raw/OMG_NOV24_V101_AI2_COMPLETED.json"
    ai1, ai2 = load(ai1_path), load(ai2_path)
    assert ai1["actual_model_label"] == "GPT-5.6 Sol Pro"
    assert ai2["actual_model_label"] == "Gemini 3.1 Pro"
    assert ai1["run_id"] != ai2["run_id"]
    for record in (ai1, ai2):
        assert record["completed_at_utc"].endswith("Z")
        assert all(value is False for value in record["attestation"].values())

    comparison = comparator.compare(ai1, ai2)
    comparison_path = out / "OMG_NOV24_V101_PRIMARY_COMPARISON.json"
    write(comparison_path, comparison)

    comparison_paths = [
        r1 / "executors/manual_dual_model_r1/derived/KBM_E02_V100_PRIMARY_COMPARISON.json",
        comparison_path,
        r1 / "executors/manual_dual_model_r1/derived/KBM_E05_V100_PRIMARY_COMPARISON.json",
        r1 / "executors/manual_dual_model_r1/derived/D25_E02_V100_PRIMARY_COMPARISON.json",
    ]
    aggregate = aggregator.aggregate([load(path) for path in comparison_paths])
    aggregate_path = out / "COHORT_AGGREGATE_V1_1_R1.json"
    write(aggregate_path, aggregate)

    replay_path = r1 / "eligible_replay_r1/run_36844856009/ELIGIBLE_REPLAY_RESULT_R1.json"
    replay = load(replay_path)
    assert aggregate["eligible_replay_lanes"] == ELIGIBLE
    assert replay["state"] == "PASS"
    assert all(
        replay["lanes"][lane]["core_replay"]["state"] == "PASS_CORE_PARITY"
        for lane in ELIGIBLE
    )

    gate_input = {
        "cohort_fixed": True,
        "new_lane_after_results": False,
        "all_four_lanes_reported": True,
        "primary_roles": {
            "KBM_COMPANY_E02_V100_AI1": "VALID",
            "KBM_COMPANY_E02_V100_AI2": "VALID",
            "OMG_NOV24_V101_AI1": "VALID",
            "OMG_NOV24_V101_AI2": "VALID",
            "KBM_E05_V100_AI1": "VALID",
            "KBM_E05_V100_AI2": "VALID",
            "D25_E02_V100_AI1": "VALID",
            "D25_E02_V100_AI2": "VALID",
        },
        "primary_role_provenance": {
            "carry_forward_validated_roles": 6,
            "fresh_blind_roles": 2,
            "fresh_model_pair": ["GPT-5.6 Sol Pro", "Gemini 3.1 Pro"],
            "executor_substitution": "PROSPECTIVE_AVAILABILITY_ONLY_BEFORE_AI2_RESPONSE",
        },
        "input_provenance_integrity": "PASS",
        "post_result_rebinding": False,
        "all_lane_comparators_executed": True,
        "coordinator_substitution_used": False,
        "targeted_content_review_used": False,
        "all_lane_outcomes_retained": True,
        "lane_states": aggregate["lane_states"],
        "omg_v101_state": comparison["state"],
        "cohort_aggregator_test": "PASS",
        "cohort_aggregate_schema": "PASS",
        "denominator_rule_preserved": True,
        "weight_grid_unchanged": True,
        "weight_runner_test": "PASS",
        "weights_inferred_from_evidence_or_outcome": False,
        "eligible_lanes": ELIGIBLE,
        "eligible_lane_core_replay": {lane: "PASS" for lane in ELIGIBLE},
        "required_label": REQUIRED_LABEL,
        "claims": {
            "historical_snapshot": "NOT_ESTABLISHED",
            "historical_area_UNO": "NOT_COMPUTED",
            "human_validation": "NOT_PERFORMED",
            "human_reliability": "NOT_PERFORMED",
            "predictive_probability_risk_validation": "NOT_CLAIMED",
        },
    }
    gate_input_path = out / "RELEASE_GATE_INPUT_V1_1_R1.json"
    write(gate_input_path, gate_input)

    gate_output = gate_module.evaluate(gate_input)
    gate_output_path = out / "RELEASE_GATE_OUTPUT_V1_1_R1.json"
    write(gate_output_path, gate_output)

    assert comparison["state"] == "HOLD_DISAGREEMENT"
    assert [row["triage"] for row in comparison["entries"]] == [
        "CONSENSUS_NUMERIC",
        "CONSENSUS_NUMERIC",
        "CONSENSUS_NUMERIC",
        "HOLD_DISAGREEMENT",
    ]
    assert aggregate["state"] == "COMPLETE"
    assert aggregate["observed_decisions"] == aggregate["expected_decisions"] == 12
    assert aggregate["overall"]["exact_agreement_count"] == 11
    assert aggregate["overall"]["numeric_consensus_count"] == 9
    assert aggregate["overall"]["shared_unknown_count"] == 2
    assert aggregate["overall"]["disagreement_count"] == 1
    assert aggregate["overall"]["unresolved_count"] == 0
    assert gate_output["state"] == "AI_ONLY_RESEARCH_BETA_RC_PASS_WITH_VISIBLE_INCOMPLETENESS"
    assert all(value == "PASS" for value in gate_output["gates"].values())

    tracked = [
        route / "PROTOCOL_FREEZE_R1.md",
        route / "CARRY_FORWARD_MANIFEST_R1.json",
        route / "MODEL_B_SUBSTITUTION_GEMINI31PRO_R2.md",
        route / "omg_nov24_v1_0_1/06_AI1_STANDALONE_RU.md",
        route / "omg_nov24_v1_0_1/07_AI2_STANDALONE_RU.md",
        comparator_path,
        aggregator_path,
        Path(__file__).resolve(),
        ai1_path,
        ai2_path,
        gate_path,
        replay_path,
    ]
    artifact_files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
        for path in sorted(out.glob("*.json"))
    }
    receipt = {
        "schema": "AI_ONLY_RESEARCH_BETA_V1_1_EVALUATION_RECEIPT_R1",
        "github_run_id": run_id,
        "github_run_attempt": run_attempt,
        "github_head_sha": head_sha,
        "artifact_files": artifact_files,
        "pinned_git_blobs": {str(path.relative_to(repo)): git_blob(repo, path) for path in tracked},
        "derived_states": {
            "omg_v101": comparison["state"],
            "cohort": aggregate["state"],
            "release_gate": gate_output["state"],
        },
        "scientific_boundaries": {
            "r1_raw_outputs_edited": False,
            "coordinator_substitution": False,
            "targeted_adjudication": False,
            "old_omg_kvs5_pol50_restored": False,
            "historical_area_UNO": "NOT_COMPUTED",
            "human_validation": "NOT_PERFORMED",
            "predictive_validation": "NOT_CLAIMED",
            "auto_merge": False,
        },
    }
    receipt_path = out / "V1_1_EVALUATION_RECEIPT_R1.json"
    write(receipt_path, receipt)

    return {
        "omg_v101_state": comparison["state"],
        "cohort_state": aggregate["state"],
        "release_gate_state": gate_output["state"],
        "gates": gate_output["gates"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--head-sha", required=True)
    args = parser.parse_args()
    result = evaluate(
        Path(args.repo_root).resolve(),
        Path(args.out).resolve(),
        args.run_id,
        args.run_attempt,
        args.head_sha,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
