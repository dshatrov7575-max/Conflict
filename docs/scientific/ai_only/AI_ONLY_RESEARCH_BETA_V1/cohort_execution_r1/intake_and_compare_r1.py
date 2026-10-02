#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

COHORT_ID = "AI_ONLY_REPLICATION_COHORT_R1_20260930"

LANES = {
    "KBM_E02": {
        "route_id": "AI_ONLY_DYAD_KBM_E02_V100",
        "input_sha256": "d0fb1f4a87f1cf64380f99167d77ecd63fd37b2827c48d044679b6abf027bf42",
        "ai1": "KBM_E02_V100_AI1_COMPLETED.json",
        "ai2": "KBM_E02_V100_AI2_COMPLETED.json",
        "comparator": "docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/engineering/KBM_E02_V100/compare_primary.py",
        "aggregate_flag": "--kbm-e02",
        "expected_decisions": 2,
    },
    "OMG_NOV24": {
        "route_id": "AI_ONLY_DYAD_OMG_NOV24_V100",
        "input_sha256": "72b061d6999b596052adc34df493cd2f9687979589ddd17a83ae21f375a0a9a4",
        "ai1": "OMG_NOV24_V100_AI1_COMPLETED.json",
        "ai2": "OMG_NOV24_V100_AI2_COMPLETED.json",
        "comparator": "docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/engineering/OMG_NOV24_V100/compare_primary.py",
        "aggregate_flag": "--omg-nov24",
        "expected_decisions": 4,
    },
    "KBM_E05": {
        "route_id": "AI_ONLY_PAIR_KBM_E05_V100",
        "input_sha256": "51f1a805986f7550828d8b05e0a1aa7aa2c80d43410540cd0f72a82448660f95",
        "ai1": "KBM_E05_V100_AI1_COMPLETED.json",
        "ai2": "KBM_E05_V100_AI2_COMPLETED.json",
        "comparator": "docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/engineering/KBM_E05_V100/compare_primary.py",
        "aggregate_flag": "--kbm-e05",
        "expected_decisions": 2,
    },
    "D25_E02": {
        "route_id": "AI_ONLY_DYAD_D25_E02_V100",
        "input_sha256": "aa256f3c1822eea2494b4267a15f5b65707a86896b457531762b2066387872aa",
        "ai1": "D25_E02_V100_AI1_COMPLETED.json",
        "ai2": "D25_E02_V100_AI2_COMPLETED.json",
        "comparator": "docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/episode_input_v1/engineering/D25_E02_V100/compare_primary.py",
        "aggregate_flag": "--d25-e02",
        "expected_decisions": 4,
    },
}

AGGREGATOR = "docs/scientific/ai_only/AI_ONLY_RESEARCH_BETA_V1/cohort_analysis_r1/aggregate_cohort_r1.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def invalid_comparison(spec: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "route_id": spec["route_id"],
        "input_sha256": spec["input_sha256"],
        "state": "REJECT_INVALID_PRIMARY_RUN",
        "reason": reason,
        "calculation_release": False,
        "historical_snapshot": "NOT_ESTABLISHED",
        "historical_area_UNO": "NOT_COMPUTED",
        "human_validation": "NOT_PERFORMED",
    }


def run_comparator(
    repo_root: Path,
    input_dir: Path,
    out_dir: Path,
    lane_key: str,
    spec: dict[str, Any],
) -> dict[str, Any]:
    ai1 = input_dir / spec["ai1"]
    ai2 = input_dir / spec["ai2"]
    present = {"ai1": ai1.is_file(), "ai2": ai2.is_file()}

    record: dict[str, Any] = {
        "lane_key": lane_key,
        "route_id": spec["route_id"],
        "expected_files": [spec["ai1"], spec["ai2"]],
        "present": present,
        "comparison_state": None,
        "comparison_path": None,
    }

    if not all(present.values()):
        missing = [spec[k] for k in ("ai1", "ai2") if not present[k]]
        record["comparison_state"] = "MISSING_PRIMARY_PAIR"
        record["missing"] = missing
        return record

    comparator = repo_root / spec["comparator"]
    if not comparator.is_file():
        record["comparison_state"] = "REJECT_INVALID_PRIMARY_RUN"
        record["reason"] = "frozen comparator file missing"
        return record

    comparison_path = out_dir / f"{lane_key}_PRIMARY_COMPARISON.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(comparator),
            "--ai1", str(ai1),
            "--ai2", str(ai2),
            "--out", str(comparison_path),
        ],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )

    if proc.returncode != 0:
        reason = (proc.stderr or proc.stdout or "comparator failed").strip()
        payload = invalid_comparison(spec, reason)
        write_json(comparison_path, payload)
        record["comparison_state"] = "REJECT_INVALID_PRIMARY_RUN"
        record["comparison_path"] = str(comparison_path)
        record["reason"] = reason
        return record

    payload = json.loads(comparison_path.read_text(encoding="utf-8-sig"))
    if payload.get("route_id") != spec["route_id"]:
        payload = invalid_comparison(spec, "comparator output route mismatch")
        write_json(comparison_path, payload)

    record["comparison_state"] = payload.get("state")
    record["comparison_path"] = str(comparison_path)
    return record


def run_aggregate(repo_root: Path, out_dir: Path, lane_records: list[dict[str, Any]]) -> Path:
    aggregator = repo_root / AGGREGATOR
    if not aggregator.is_file():
        raise RuntimeError("frozen cohort aggregator missing")

    aggregate_out = out_dir / "COHORT_AGGREGATE_R1.json"
    cmd = [sys.executable, str(aggregator), "--out", str(aggregate_out)]

    by_key = {r["lane_key"]: r for r in lane_records}
    for key, spec in LANES.items():
        record = by_key[key]
        path = record.get("comparison_path")
        if path:
            cmd += [spec["aggregate_flag"], path]

    proc = subprocess.run(cmd, cwd=repo_root, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "aggregator failed").strip())
    return aggregate_out


def orchestrate(repo_root: Path, input_dir: Path, out_dir: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    input_dir = input_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir = out_dir.resolve()

    records = [
        run_comparator(repo_root, input_dir, out_dir, key, spec)
        for key, spec in LANES.items()
    ]
    aggregate_path = run_aggregate(repo_root, out_dir, records)
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8-sig"))

    eligible = aggregate.get("eligible_replay_lanes", [])
    status = {
        "cohort_id": COHORT_ID,
        "state": aggregate.get("state"),
        "input_dir": str(input_dir),
        "lane_records": records,
        "completed_primary_files_observed": sum(
            int(r["present"]["ai1"]) + int(r["present"]["ai2"]) for r in records
        ),
        "expected_primary_files": 8,
        "aggregate_path": str(aggregate_path),
        "eligible_replay_lanes": eligible,
        "next_gate": (
            "CORE_REPLAY_REQUIRED_FOR_ELIGIBLE_LANES"
            if eligible
            else "NO_CORE_REPLAY_UNLESS_A_LANE_BECOMES_ELIGIBLE"
        ),
        "sensitivity_run_triggered": False,
        "core_replay_triggered": False,
        "coordinator_adjudication_used": False,
    }
    status_path = out_dir / "INTAKE_STATUS_R1.json"
    write_json(status_path, status)
    return status


def self_test(repo_root: Path) -> dict[str, Any]:
    cases = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        inp = root / "in"
        out = root / "out"
        inp.mkdir()

        modules = {}
        for key, spec in LANES.items():
            modules[key] = load_module(repo_root / spec["comparator"], f"cmp_{key.lower()}")
            mod = modules[key]
            ai1 = mod.sample(mod.ROLES[0])
            ai2 = mod.sample(mod.ROLES[1])
            write_json(inp / spec["ai1"], ai1)
            write_json(inp / spec["ai2"], ai2)

        status = orchestrate(repo_root, inp, out)
        agg = json.loads((out / "COHORT_AGGREGATE_R1.json").read_text())
        assert status["completed_primary_files_observed"] == 8
        assert agg["state"] == "COMPLETE"
        assert agg["overall"]["numeric_consensus_count"] == 12
        cases += 1

        (inp / LANES["D25_E02"]["ai2"]).unlink()
        out2 = root / "out2"
        status2 = orchestrate(repo_root, inp, out2)
        agg2 = json.loads((out2 / "COHORT_AGGREGATE_R1.json").read_text())
        assert status2["completed_primary_files_observed"] == 7
        assert agg2["state"] == "PARTIAL"
        assert agg2["overall"]["unresolved_count"] == 4
        cases += 1

        mod = modules["D25_E02"]
        write_json(inp / LANES["D25_E02"]["ai2"], mod.sample(mod.ROLES[1]))
        kbm_path = inp / LANES["KBM_E02"]["ai1"]
        bad = json.loads(kbm_path.read_text())
        bad["attestation"]["external_sources_used"] = True
        write_json(kbm_path, bad)
        out3 = root / "out3"
        status3 = orchestrate(repo_root, inp, out3)
        agg3 = json.loads((out3 / "COHORT_AGGREGATE_R1.json").read_text())
        kbm_record = next(x for x in status3["lane_records"] if x["lane_key"] == "KBM_E02")
        assert kbm_record["comparison_state"] == "REJECT_INVALID_PRIMARY_RUN"
        assert agg3["overall"]["unresolved_count"] == 2
        cases += 1

    return {"self_test": "PASS", "cases": cases}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--input-dir")
    p.add_argument("--out-dir")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()

    repo_root = Path(args.repo_root)
    if args.self_test:
        print(json.dumps(self_test(repo_root)))
        return

    if not (args.input_dir and args.out_dir):
        p.error("--input-dir and --out-dir required unless --self-test")

    status = orchestrate(repo_root, Path(args.input_dir), Path(args.out_dir))
    print(json.dumps({
        "state": status["state"],
        "completed_primary_files_observed": status["completed_primary_files_observed"],
        "eligible_replay_lanes": status["eligible_replay_lanes"],
    }))


if __name__ == "__main__":
    main()
