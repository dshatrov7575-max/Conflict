"""Read-only validation for PR-18 exact-edition recovery tranche B."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

BASE = "ae5770467f93efdf4a3bf988b4339e1ef4577998"
BASE_TREE = "19ccc23a96ccbe2cd3cd1422879aac9059e37cf2"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREFIX = HERE.relative_to(ROOT).as_posix() + "/"
PR15 = "docs/scientific/pilots/ZHANAOZEN_2011_RECOVERY_PROTOCOL_V1/"
PR17 = "docs/scientific/pilots/ZHANAOZEN_2011_EXACT_EDITION_RECOVERY_TRANCHE_A_V1/"
FILES = {
    "EXECUTED_ATTEMPT_LEDGER.json",
    "EXACT_EDITION_DECISIONS.json",
    "RECOVERY_TRANCHE_SUMMARY.md",
    "VALIDATION_RECEIPT.json",
    "FREEZE_MANIFEST.json",
    "validate_exact_edition_tranche.py",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def local(path: str) -> Path:
    candidate = (ROOT / path).resolve()
    require(candidate.is_relative_to(ROOT) and candidate.is_file(), f"Missing/outside repository: {path}")
    return candidate


def read_json(path: str):
    return json.loads(local(path).read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicate_keys)


def git(*args: str) -> bytes:
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(["git", *args], cwd=ROOT, env=env)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def verify_pin(pin: dict, *, bind_to_base: bool = False) -> None:
    raw = local(pin["path"]).read_bytes()
    require(len(raw) == pin["bytes"], f"Size mismatch: {pin['path']}")
    require(sha256(raw) == pin["sha256"], f"SHA mismatch: {pin['path']}")
    require(git_blob(raw) == pin["git_blob_sha1"], f"Blob mismatch: {pin['path']}")
    if bind_to_base:
        recorded = git("rev-parse", f"{BASE}:{pin['path']}").decode().strip()
        require(recorded == pin["git_blob_sha1"], f"Base pin mismatch: {pin['path']}")


def verify_base_blobs() -> int:
    count = 0
    for entry in git("ls-tree", "-rz", "-r", BASE).split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        _mode, kind, object_id = metadata.split()
        require(kind == b"blob", "Unexpected non-blob base object")
        path = raw_name.decode("utf-8")
        require(git_blob(local(path).read_bytes()) == object_id.decode(), f"Base blob changed: {path}")
        count += 1
    return count


def run_prior_validator() -> dict:
    temp_path = Path(tempfile.gettempdir()) / f"conflict-pr17-validate-{uuid.uuid4().hex}"
    try:
        subprocess.check_call(["git", "worktree", "add", "--detach", str(temp_path), BASE], cwd=ROOT,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        output = subprocess.check_output([sys.executable, "-B", str(temp_path / PR17 / "validate_exact_edition_tranche.py")],
                                         cwd=temp_path, text=True, encoding="utf-8")
        return json.loads(output)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(temp_path)], cwd=ROOT,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shutil.rmtree(temp_path, ignore_errors=True)


def check_no_results(value) -> None:
    forbidden_keys = {
        "factor_value", "assessment_value", "numeric_anchor", "anchor", "score",
        "weight", "weights", "outcome", "outcome_class", "calculated_result",
        "probability", "risk", "country_score", "validation_record", "uno",
        "historical_assessment", "payload_body", "full_text", "article_text",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            require(key.lower() not in forbidden_keys, f"Forbidden field: {key}")
            check_no_results(child)
    elif isinstance(value, list):
        for child in value:
            check_no_results(child)
    elif isinstance(value, str):
        require(not re.search(r"\b(?:POS|KVS|RGU|KVPTN|UNO|Pol)\s*[:=]\s*[+-]?\d", value, re.I),
                "Encoded numeric factor result")


def planned_exact_queries(plan: dict, version_ids: set[str]) -> dict[str, dict]:
    result = {}
    for unit in plan["blocker_units"]:
        ids = unit.get("affected_ids", {}).get("document_version_ids", [])
        if unit["scope"] != "DOCUMENT_VERSION" or len(ids) != 1 or ids[0] not in version_ids:
            continue
        for query in unit["planned_queries"]:
            if query["route_id"] == "ROUTE_PUBLISHER_OR_ARCHIVE_EXACT_EDITION":
                result[query["query_id"]] = {"unit": unit, "query": query}
    return result


def validate() -> dict:
    require(git("rev-parse", f"{BASE}^{{tree}}").decode().strip() == BASE_TREE, "Base tree mismatch")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT)
    actual_files = {path.name for path in HERE.iterdir() if path.is_file()}
    require(actual_files == FILES, f"Expected six files, found {sorted(actual_files)}")
    require(not any(path.is_dir() for path in HERE.iterdir()), "Unexpected subdirectory")

    manifest = read_json(PREFIX + "FREEZE_MANIFEST.json")
    ledger = read_json(PREFIX + "EXECUTED_ATTEMPT_LEDGER.json")
    decisions = read_json(PREFIX + "EXACT_EDITION_DECISIONS.json")
    receipt = read_json(PREFIX + "VALIDATION_RECEIPT.json")
    plan = read_json(PR15 + "RECOVERY_PLAN.json")
    pr17_ledger = read_json(PR17 + "EXECUTED_ATTEMPT_LEDGER.json")

    require(manifest["base_commit"] == BASE and manifest["base_tree"] == BASE_TREE, "Manifest base mismatch")
    require(len({pin["path"] for pin in manifest["inputs"]}) == len(manifest["inputs"]), "Duplicate input pin")
    require(len({pin["path"] for pin in manifest["outputs"]}) == len(manifest["outputs"]), "Duplicate output pin")
    for pin in manifest["inputs"]:
        verify_pin(pin, bind_to_base=True)
    expected_outputs = {PREFIX + name for name in FILES if name != "FREEZE_MANIFEST.json"}
    require({pin["path"] for pin in manifest["outputs"]} == expected_outputs, "Output pin coverage mismatch")
    for pin in manifest["outputs"]:
        verify_pin(pin)

    prior_result = run_prior_validator()
    require(prior_result["status"] == "PASS_TECHNICAL_ONLY" and prior_result["output_pins"] == "PASS",
            "PR-16 validator failed")
    base_blob_count = verify_base_blobs()
    check_no_results(ledger)
    check_no_results(decisions)
    check_no_results(receipt)
    require(ledger["artifact_kind"] == "EXACT_EDITION_RECOVERY_EXECUTION_LEDGER", "Wrong ledger kind")
    require(ledger["assessor_type"] == "AI_PREPARATION", "Wrong assessor type")
    require(ledger["base_commit"] == BASE and ledger["base_tree"] == BASE_TREE, "Ledger base mismatch")
    require(ledger["network_search_executed_by_pr18"] is True, "Network execution not recorded")
    require(ledger["substantive_review_executed_by_pr18"] is True, "Substantive review not recorded")
    require(ledger["live_query_budget_consumed"] == 32, "Wrong live query budget")
    require(ledger["legacy_fragment_replay_budget_consumed"] == 0, "Fragment-route budget consumed")

    attempts = ledger["attempts"]
    decision_rows = decisions["document_versions"]
    require(len(attempts) == 32, "Expected 32 attempts")
    require(len(decision_rows) == 16, "Expected 16 DocumentVersion decisions")
    require(len({row["attempt_id"] for row in attempts}) == 32, "Duplicate attempt ID")
    require(len({row["planned_query_id"] for row in attempts}) == 32, "Duplicate planned query execution")
    require(len({row["document_version_id"] for row in decision_rows}) == 16, "Duplicate DocumentVersion decision")

    version_ids = {row["document_version_id"] for row in decision_rows}
    planned = planned_exact_queries(plan, version_ids)
    require(len(planned) == 32, "Frozen plan does not expose exactly 32 scoped exact-edition queries")
    require({row["planned_query_id"] for row in attempts} == set(planned), "Attempt/query set mismatch")
    require(all(row["route_id"] == "ROUTE_PUBLISHER_OR_ARCHIVE_EXACT_EDITION" for row in attempts),
            "Out-of-scope route executed")
    require(all(row["query_template_id"] in {"EDITION-PUBLISHER-HISTORY", "EDITION-ARCHIVE-CAPTURE"} for row in attempts),
            "Out-of-scope query template executed")
    by_version: dict[str, list[dict]] = {}
    for attempt in attempts:
        frozen = planned[attempt["planned_query_id"]]
        query = frozen["query"]
        unit = frozen["unit"]
        require(attempt["blocker_id"] == unit["blocker_id"], "Blocker rebinding")
        require(attempt["document_version_id"] == unit["affected_ids"]["document_version_ids"][0], "Version rebinding")
        require(attempt["query_template_id"] == query["query_template_id"], "Template changed")
        require(attempt["query_ordinal"] == query["query_ordinal"], "Query ordinal changed")
        require(attempt["query_text_sha256"] == query["query_text_sha256"], "Query text hash changed")
        require(attempt["query_budget_effect"] == "CONSUMED_ONE_FROZEN_QUERY", "Budget effect changed")
        require(attempt["rerun_performed"] is False, "Rerun recorded")
        require(attempt["admission_decision"] == "RETAIN_NOT_PROVEN", "Unexpected admission decision")
        require(attempt["prior_status_retained"] == "NOT_PROVEN", "Prior status not retained")
        require(attempt["scientific_state_changed_by_pr18"] is False, "Scientific state changed")
        gates = attempt["admissibility_gates"]
        require(gates["exact_document_version_full_edition_binding"] is False, "Edition binding promoted")
        require(gates["exact_edition_contract_satisfied"] is False, "Exact-edition contract promoted")
        require(attempt["requested_at_utc"] and attempt["completed_at_utc"], "Missing timestamps")
        require(attempt["request_locator"], "Missing request locator")
        require(isinstance(attempt["subrequests"], list), "Missing subrequest ledger")
        by_version.setdefault(attempt["document_version_id"], []).append(attempt)

    for version_id, rows in by_version.items():
        require(len(rows) == 2, f"Expected two attempts for {version_id}")
        require({row["query_template_id"] for row in rows} == {"EDITION-PUBLISHER-HISTORY", "EDITION-ARCHIVE-CAPTURE"},
                f"Template coverage incomplete for {version_id}")
    require(pr17_ledger["live_query_budget_consumed"] == 22, "PR-17 exact-edition budget changed")
    require(pr17_ledger["legacy_fragment_replay_budget_consumed"] == 0, "PR-17 fragment-route budget changed")
    require({row["document_version_id"] for row in decision_rows} == set(by_version), "Decision/version coverage mismatch")
    for decision in decision_rows:
        version_id = decision["document_version_id"]
        ids = {row["attempt_id"] for row in by_version[version_id]}
        require({decision["publisher_attempt_id"], decision["archive_attempt_id"]} == ids, "Decision attempt linkage mismatch")
        require(decision["prior_full_edition_status"] == "NOT_PROVEN", "Prior edition status changed")
        require(decision["exact_document_version_full_edition_binding"] is False, "Decision edition binding promoted")
        require(decision["exact_edition_contract_satisfied"] is False, "Decision contract promoted")
        require(decision["decision"] == "RETAIN_NOT_PROVEN", "Decision promoted")
        require(decision["mapping_admission_changed"] is False, "Mapping admission changed")
        require(decision["target_time_status"] == "UNKNOWN_UNCHANGED", "Target-time status changed")
        require(decision["scientific_state_changed_by_pr18"] is False, "Decision changed scientific state")

    publisher_attempts = [row for row in attempts if row["query_template_id"] == "EDITION-PUBLISHER-HISTORY"]
    archive_attempts = [row for row in attempts if row["query_template_id"] == "EDITION-ARCHIVE-CAPTURE"]
    require(len(publisher_attempts) == len(archive_attempts) == 16, "Attempt type count mismatch")
    require(all(row["admissibility_gates"]["pre_cutoff_historical_capture"] is False for row in publisher_attempts),
            "Current publisher content treated as pre-cutoff proof")
    require(all(row["admission_decision"] == "RETAIN_NOT_PROVEN" for row in archive_attempts),
            "Archive attempt changed edition status")
    for row in archive_attempts:
        if row["admissibility_gates"]["archive_digest_verified"]:
            require(row["chosen_capture"]["digest_match"] is True, "Digest gate without digest match")
            require(row["admissibility_gates"]["complete_payload_retrieved"] is True, "Digest gate without payload")
        if row["response_status"].startswith("TECHNICAL_FAILURE") or row["response_status"] == "PARSER_FAILURE":
            require(row["technical_error"], "Technical failure lacks error")
            require(row["scientific_state_changed_by_pr18"] is False, "Technical failure changed state")
    archive_payloads = sum(row["admissibility_gates"]["complete_payload_retrieved"] for row in archive_attempts)
    digest_verified = sum(row["admissibility_gates"]["archive_digest_verified"] for row in archive_attempts)
    technical_failures = sum(
        row["response_status"].startswith("TECHNICAL_FAILURE") or row["response_status"] == "PARSER_FAILURE"
        for row in attempts
    )
    response_counts = {}
    result_counts = {}
    for row in attempts:
        response_counts[row["response_status"]] = response_counts.get(row["response_status"], 0) + 1
        result_counts[row["result_state"]] = result_counts.get(row["result_state"], 0) + 1

    expected_receipt = {
        "artifact_kind": "EXACT_EDITION_TRANCHE_VALIDATION_RECEIPT",
        "assessor_type": "AI_PREPARATION",
        "status": "PASS_TECHNICAL_ONLY",
        "base_commit": BASE,
        "base_tree": BASE_TREE,
        "checks": [
            "exact_base_and_prior_blobs",
            "pr17_validator_and_output_pins",
            "strict_json_and_manifest_pins",
            "sixteen_versions_and_thirty_two_frozen_queries",
            "one_execution_per_frozen_query_and_no_reruns",
            "publisher_and_archive_query_pair_per_version",
            "technical_failure_retains_prior_state",
            "current_content_and_fragment_proof_not_promoted",
            "no_exact_edition_contract_satisfied",
            "no_mapping_or_target_time_state_change",
            "six_file_scope_and_git_diff_check",
        ],
        "counts": {
            "base_blobs_verified": base_blob_count,
            "manifest_input_pins": len(manifest["inputs"]),
            "manifest_output_pins": len(manifest["outputs"]),
            "document_versions": len(decision_rows),
            "frozen_queries_executed": len(attempts),
            "publisher_attempts": len(publisher_attempts),
            "archive_attempts": len(archive_attempts),
            "archive_payloads_retrieved": archive_payloads,
            "archive_digests_verified": digest_verified,
            "technical_or_parser_failures": technical_failures,
            "exact_edition_contracts_satisfied": 0,
            "scientific_state_changes": 0,
            "fragment_route_live_budget_consumed": 0,
        },
        "response_status_counts": dict(sorted(response_counts.items())),
        "result_state_counts": dict(sorted(result_counts.items())),
        "pr17_validator": {
            "status": prior_result["status"],
            "output_pins": prior_result["output_pins"],
        },
        "scientific_boundaries": {
            "human_validation_reliability": "NOT_PERFORMED",
            "human_coding_adjudication": "NOT_PERFORMED",
            "historical_snapshot": "NOT_ESTABLISHED",
            "historical_area_UNO": "NOT_COMPUTED_BLOCKED",
            "predictive_probability_risk_validation": "NOT_CLAIMED",
            "publication_release_deployment": "NOT_EXECUTED",
        },
    }
    require(receipt == expected_receipt, "Stored validation receipt is not reproducible")

    summary = local(PREFIX + "RECOVERY_TRANCHE_SUMMARY.md").read_text(encoding="utf-8")
    for required_text in (
        "AI preparation only",
        "32/32",
        "16/16",
        "Exact-edition contracts satisfied: **0**",
        "16 × NOT_PROVEN",
        "Live fragment-route budget consumed: **0**",
        "Target-time state remains **UNKNOWN**",
        "HUMAN validation/coding is **NOT_PERFORMED**",
        "Historical area UNO is **NOT_COMPUTED / BLOCKED**",
    ):
        require(required_text in summary, f"Summary boundary missing: {required_text}")

    changed = git("diff", "--name-only", BASE, "--").decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    require(all(path.startswith(PREFIX) and Path(path).name in FILES for path in changed + untracked),
            "Changes outside PR-18 scope")
    subprocess.check_call(["git", "diff", "--check", BASE, "--"], cwd=ROOT)
    for name in FILES:
        text = local(PREFIX + name).read_text(encoding="utf-8")
        require(text.endswith("\n"), f"Missing final newline: {name}")
        require(all(line == line.rstrip() for line in text.splitlines()), f"Trailing whitespace: {name}")
    return {
        "status": "PASS_TECHNICAL_ONLY",
        "counts": expected_receipt["counts"],
        "response_status_counts": expected_receipt["response_status_counts"],
        "result_state_counts": expected_receipt["result_state_counts"],
        "output_pins": "PASS",
        "pr17_validator": "PASS_TECHNICAL_ONLY",
        "release_state": "EXACT_EDITION_TRANCHE_B_COMPLETE_NO_NEW_ADMISSION",
    }


if __name__ == "__main__":
    try:
        require(sys.argv[1:] == [], "This validator accepts no arguments")
        print(json.dumps(validate(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
