#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

COHORT_ID = "AI_ONLY_REPLICATION_COHORT_V1_1_20261001"
ROUTES = (
    "AI_ONLY_DYAD_KBM_E02_V100",
    "AI_ONLY_DYAD_OMG_NOV24_V101",
    "AI_ONLY_PAIR_KBM_E05_V100",
    "AI_ONLY_DYAD_D25_E02_V100",
)
FACTOR_EXPECTED = {"POS_AO2": 6, "KVS_AO2": 6}
VALID_TRIAGE = {
    "CONSENSUS_NUMERIC",
    "SHARED_UNKNOWN",
    "SHARED_DISPUTED",
    "HOLD_DISAGREEMENT",
}
PARENT_AGGREGATOR_BLOB = "47b3fc0fc3828066b8cb68450114d4f7f8b69790"


def load(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def extract_rows(doc):
    if isinstance(doc.get("entries"), list):
        return doc["entries"]
    if isinstance(doc.get("company_entries"), list):
        return [
            {"actor_id": "COMPANY", "factor": row["factor"], "triage": row["triage"]}
            for row in doc["company_entries"]
        ]
    return []


def classify(row):
    triage = row.get("triage")
    return triage if triage in VALID_TRIAGE else "UNRESOLVED"


def aggregate(docs):
    by_route = {doc.get("route_id"): doc for doc in docs}
    if len(by_route) != len(docs):
        raise ValueError("duplicate route")
    missing = [route for route in ROUTES if route not in by_route]
    if missing:
        raise ValueError(f"missing routes: {missing}")

    by_factor = {
        factor: {
            "expected": expected,
            "exact_agreement_count": 0,
            "numeric_consensus_count": 0,
            "shared_unknown_count": 0,
            "shared_disputed_count": 0,
            "disagreement_count": 0,
            "unresolved_count": 0,
        }
        for factor, expected in FACTOR_EXPECTED.items()
    }
    overall = {
        key: 0
        for key in (
            "exact_agreement_count",
            "numeric_consensus_count",
            "shared_unknown_count",
            "shared_disputed_count",
            "disagreement_count",
            "unresolved_count",
        )
    }
    lane_states = {}
    observed = 0

    for route in ROUTES:
        doc = by_route[route]
        lane_states[route] = doc.get("state", "UNKNOWN")
        for row in extract_rows(doc):
            factor = row.get("factor")
            if factor not in by_factor:
                continue
            observed += 1
            triage = classify(row)
            counts = by_factor[factor]
            if triage == "CONSENSUS_NUMERIC":
                counts["exact_agreement_count"] += 1
                counts["numeric_consensus_count"] += 1
                overall["exact_agreement_count"] += 1
                overall["numeric_consensus_count"] += 1
            elif triage == "SHARED_UNKNOWN":
                counts["exact_agreement_count"] += 1
                counts["shared_unknown_count"] += 1
                overall["exact_agreement_count"] += 1
                overall["shared_unknown_count"] += 1
            elif triage == "SHARED_DISPUTED":
                counts["exact_agreement_count"] += 1
                counts["shared_disputed_count"] += 1
                overall["exact_agreement_count"] += 1
                overall["shared_disputed_count"] += 1
            elif triage == "HOLD_DISAGREEMENT":
                counts["disagreement_count"] += 1
                overall["disagreement_count"] += 1
            else:
                counts["unresolved_count"] += 1
                overall["unresolved_count"] += 1

    expected = sum(FACTOR_EXPECTED.values())

    def fraction(number, denominator=expected):
        return f"{number / denominator:.8f}"

    for counts in by_factor.values():
        for key in (
            "exact_agreement_count",
            "numeric_consensus_count",
            "shared_unknown_count",
            "shared_disputed_count",
            "disagreement_count",
            "unresolved_count",
        ):
            counts[key.replace("_count", "_fraction")] = fraction(counts[key], counts["expected"])

    return {
        "cohort_id": COHORT_ID,
        "state": "COMPLETE" if observed == expected else "PARTIAL",
        "expected_lanes": len(ROUTES),
        "expected_decisions": expected,
        "observed_decisions": observed,
        "overall": {
            **overall,
            "exact_agreement_fraction_expected_denominator": fraction(overall["exact_agreement_count"]),
            "numeric_consensus_fraction_expected_denominator": fraction(overall["numeric_consensus_count"]),
            "shared_unknown_fraction_expected_denominator": fraction(overall["shared_unknown_count"]),
            "shared_disputed_fraction_expected_denominator": fraction(overall["shared_disputed_count"]),
            "disagreement_fraction_expected_denominator": fraction(overall["disagreement_count"]),
            "unresolved_fraction_expected_denominator": fraction(overall["unresolved_count"]),
        },
        "by_factor": by_factor,
        "lane_states": lane_states,
        "eligible_replay_lanes": [
            route
            for route, state in lane_states.items()
            if state
            in {
                "ELIGIBLE_FOR_READ_ONLY_DYAD_SCENARIO_REPLAY",
                "ELIGIBLE_FOR_READ_ONLY_PAIR_SCENARIO_REPLAY",
            }
        ],
        "claims": {
            "representative_sample": False,
            "population_inference": False,
            "human_validation": "NOT_PERFORMED",
            "historical_area_UNO": "NOT_COMPUTED",
            "fraction_denominator": "FROZEN_EXPECTED_DECISIONS",
        },
        "tooling_provenance": {
            "parent_aggregator_blob": PARENT_AGGREGATOR_BLOB,
            "adaptation": "ROUTE_IDENTITY_ONLY_V100_TO_V101; COUNTING_ALGORITHM_AND_DENOMINATORS_UNCHANGED",
        },
    }


def sample(route, values):
    return {
        "route_id": route,
        "state": "X",
        "entries": [{"factor": factor, "triage": triage} for factor, triage in values],
    }


def self_test():
    docs = [
        sample(ROUTES[0], [("POS_AO2", "CONSENSUS_NUMERIC"), ("KVS_AO2", "CONSENSUS_NUMERIC")]),
        sample(ROUTES[1], [("POS_AO2", "CONSENSUS_NUMERIC"), ("KVS_AO2", "HOLD_DISAGREEMENT")]),
        sample(ROUTES[2], [("POS_AO2", "CONSENSUS_NUMERIC"), ("KVS_AO2", "SHARED_DISPUTED")]),
        sample(ROUTES[3], [("POS_AO2", "CONSENSUS_NUMERIC"), ("KVS_AO2", "SHARED_UNKNOWN")]),
    ]
    result = aggregate(docs)
    assert result["state"] == "PARTIAL" and result["observed_decisions"] == 8
    cases = 1

    try:
        aggregate(docs[:-1])
    except ValueError:
        cases += 1
    else:
        raise AssertionError("missing route accepted")

    bad = [dict(doc) for doc in docs]
    bad[0] = {"route_id": ROUTES[0], "state": "X", "entries": [{"factor": "POS_AO2", "triage": "BAD"}]}
    unresolved = aggregate(bad)
    assert unresolved["overall"]["unresolved_count"] == 1
    cases += 1

    company_rows = [dict(doc) for doc in docs]
    company_rows[0] = {
        "route_id": ROUTES[0],
        "state": "X",
        "company_entries": [{"factor": "POS_AO2", "triage": "CONSENSUS_NUMERIC"}],
    }
    result2 = aggregate(company_rows)
    assert result2["observed_decisions"] == 7
    cases += 1

    assert set(result["by_factor"]) == {"POS_AO2", "KVS_AO2"}
    cases += 1
    return {"self_test": "PASS", "cases": cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--comparisons", nargs="*")
    parser.add_argument("--out")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test()))
        return
    if not args.comparisons or not args.out:
        parser.error("--comparisons ... --out required")
    result = aggregate([load(path) for path in args.comparisons])
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": result["state"], "observed": result["observed_decisions"]}))


if __name__ == "__main__":
    main()
