from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "127f682beba758be36d07ce6ee8a7e8166ecd72d"
BASE_TREE = "7aa4d2a022e99496ae64ee6a7941a00d52e8386c"
PREFIX = "docs/scientific/pilots/ZHANAOZEN_2011_TECHNICAL_RETRY_PROTOCOL_V1/"
FILES = {
    "TECHNICAL_RETRY_PLAN.json",
    "TECHNICAL_RETRY_ATTEMPT_TEMPLATE.json",
    "TECHNICAL_RETRY_PROTOCOL.md",
    "VALIDATION_RECEIPT.json",
    "FREEZE_MANIFEST.json",
    "validate_technical_retry_protocol.py",
}


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8-sig"))


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def canonical_hash(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw)


def git(*args):
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(["git", *args], cwd=ROOT, env=env)


def verify_pin(pin, base=False):
    raw = (ROOT / pin["path"]).read_bytes()
    require(len(raw) == pin["bytes"], f"Size mismatch {pin['path']}")
    require(sha256(raw) == pin["sha256"], f"SHA mismatch {pin['path']}")
    require(blob(raw) == pin["git_blob_sha1"], f"Blob mismatch {pin['path']}")
    if base:
        require(git("rev-parse", f"{BASE}:{pin['path']}").decode().strip() == pin["git_blob_sha1"], f"Base pin mismatch {pin['path']}")


def main():
    head = git("rev-parse", "HEAD").decode().strip()
    if head == BASE:
        pass  # pre-commit validation
    else:
        require(git("rev-parse", "HEAD^").decode().strip() == BASE, "Not one commit over base")
    require(git("rev-parse", f"{BASE}^{{tree}}").decode().strip() == BASE_TREE, "Base tree mismatch")
    plan = read_json(PREFIX + "TECHNICAL_RETRY_PLAN.json")
    template = read_json(PREFIX + "TECHNICAL_RETRY_ATTEMPT_TEMPLATE.json")
    receipt = read_json(PREFIX + "VALIDATION_RECEIPT.json")
    manifest = read_json(PREFIX + "FREEZE_MANIFEST.json")
    consolidated = read_json("docs/scientific/pilots/ZHANAOZEN_2011_EXACT_EDITION_CONSOLIDATION_V1/CONSOLIDATED_ATTEMPT_LEDGER.json")
    recovery = read_json("docs/scientific/pilots/ZHANAOZEN_2011_RECOVERY_PROTOCOL_V1/RECOVERY_PLAN.json")
    source_ledgers = {}
    for rel in [
        "docs/scientific/pilots/ZHANAOZEN_2011_EXACT_EDITION_RECOVERY_TRANCHE_A_V1/EXECUTED_ATTEMPT_LEDGER.json",
        "docs/scientific/pilots/ZHANAOZEN_2011_EXACT_EDITION_RECOVERY_TRANCHE_B_V1/EXECUTED_ATTEMPT_LEDGER.json",
    ]:
        ledger = read_json(rel)
        for index, row in enumerate(ledger["attempts"]):
            source_ledgers[row["attempt_id"]] = (rel, index, row)
    queries = {}
    for unit in recovery["blocker_units"]:
        for query in unit["planned_queries"]:
            queries[query["query_id"]] = query

    failures = [row for row in consolidated["attempts"] if row["consolidation_status"] == "TECHNICAL_FAILURE_PRIOR_STATE_RETAINED"]
    prohibited = [row for row in consolidated["attempts"] if row["consolidation_status"] != "TECHNICAL_FAILURE_PRIOR_STATE_RETAINED"]
    require(len(failures) == 4, "Expected four failures")
    require(Counter(row["consolidation_status"] for row in prohibited) == Counter({"COMPLETED_NONADMISSIBLE": 35, "FINITE_NO_RESULT_PRIOR_STATE_RETAINED": 15}), "Prohibited population mismatch")
    require(plan["execution_state"] == "NOT_EXECUTED_PROTOCOL_FREEZE_ONLY", "Protocol executed")
    require(plan["network_access_executed_by_pr20"] is False and plan["retrieval_executed_by_pr20"] is False, "Network/retrieval flag")
    require(len(plan["retry_units"]) == 4, "Retry unit count")
    require(len({row["retry_attempt_id"] for row in plan["retry_units"]}) == 4, "Retry IDs not unique")
    require(len({row["linked_failed_source_attempt_id"] for row in plan["retry_units"]}) == 4, "Source attempt duplication")
    require({row["linked_failed_source_attempt_id"] for row in plan["retry_units"]} == {row["source_attempt_id"] for row in failures}, "Failure coverage mismatch")
    require(Counter(row["failure_class"] for row in plan["retry_units"]) == Counter({"INITIAL_ARCHIVE_QUERY_FAILURE": 2, "REPLAY_AFTER_CANDIDATE_FAILURE": 2}), "Failure classes")

    for unit in plan["retry_units"]:
        rel, index, source = source_ledgers[unit["linked_failed_source_attempt_id"]]
        require(unit["source_attempt_reference"] == {"path": rel, "json_pointer": f"/attempts/{index}"}, "Source reference")
        require(unit["source_attempt_canonical_sha256"] == canonical_hash(source), "Source attempt hash")
        query = queries[source["planned_query_id"]]
        require(unit["frozen_rendered_query"] == query["rendered_query"], "Query text")
        require(unit["query_text_sha256"] == query["query_text_sha256"] == source["query_text_sha256"], "Query hash")
        require(unit["original_request_locator"] == source["request_locator"], "Locator drift")
        require(unit["information_cutoff"] == recovery["target_time"], "Cutoff drift")
        contract = unit["future_retry_contract"]
        require(contract["maximum_future_executions"] == 1 and contract["authorization_state"] == "AUTHORIZED_NOT_EXECUTED", "Retry budget")
        require(not any(contract[key] for key in ["query_expansion_permitted", "mirror_search_permitted", "publisher_rerun_permitted", "alternate_candidate_permitted", "substantive_search_permitted"]), "Expansion permitted")
        require(unit["state_after_pr20"] == {"full_edition_status": "NOT_PROVEN", "mapping_admission_changed": False, "target_time_applicability": "UNKNOWN", "automatic_carry_forward": False, "scientific_state_changed_by_pr20": False}, "State changed")
        if unit["failure_class"] == "INITIAL_ARCHIVE_QUERY_FAILURE":
            require(source["response_status"] == "TECHNICAL_FAILURE" and not source.get("archive_candidates") and not source.get("subrequests"), "Initial failure shape")
            require(contract["exact_target_locator"] == source["request_locator"], "Initial retry target")
            require(unit["candidate_state"]["selected_candidate"] is None, "Unexpected candidate")
        else:
            candidates = source["archive_candidates"]
            require(source["response_status"] == "TECHNICAL_FAILURE_AFTER_CANDIDATE" and candidates, "Replay failure shape")
            chosen = candidates[-1]
            expected_url = f"https://web.archive.org/web/{chosen['timestamp']}id_/{chosen['original']}"
            require(contract["exact_target_locator"] == expected_url, "Replay target")
            require(unit["candidate_state"]["selected_candidate"] == chosen, "Selected candidate drift")
            require(unit["candidate_state"]["successful_cdx_subrequest_reused_without_rerun"] is True, "CDX reuse")

    require(plan["future_retry_budget"] == {"authorized_attempts": 4, "maximum_executions_per_failed_source_attempt": 1, "total_maximum_future_http_attempts": 4, "execution_requires_separate_explicit_task": True, "execution_authorized_by_pr20": False}, "Budget contract")
    require(plan["prohibited_retry_population"]["total_prohibited_attempts"] == 50 and plan["prohibited_retry_population"]["retry_permitted"] is False, "Prohibited retry contract")
    require(plan["transport_contract"]["automatic_library_retries"] == 0, "Automatic retries")
    require(plan["transport_contract"]["connect_timeout_seconds"] == 15 and plan["transport_contract"]["read_timeout_seconds"] == 45, "Timeouts")
    require(plan["custody_and_logging_contract"]["store_payload_body_in_repository"] is False, "Payload storage")
    require(len(plan["stop_rules"]) >= 5, "Stop rules")
    require(template["execution_authorized"] is False, "Template authorizes execution")
    require(receipt["status"] == "PASS_TECHNICAL_ONLY" and receipt["counts"]["executions_by_pr20"] == 0, "Receipt")

    for pin in manifest["inputs"]:
        verify_pin(pin, base=True)
    for pin in manifest["outputs"]:
        verify_pin(pin, base=False)
    require(manifest["network_access_executed_by_pr20"] is False and manifest["retry_execution_executed_by_pr20"] is False, "Manifest execution flags")

    text = "\n".join((ROOT / (PREFIX + name)).read_text(encoding="utf-8") for name in FILES)
    for pattern in [r'"factor_value"\s*:', r'"numeric_anchor"\s*:', r'"human_response"\s*:', r'"historical_assessment"\s*:', r'"validation_record"\s*:', r'"outcome_classification"\s*:', r'"uno"\s*:', r'"probability"\s*:', r'"risk"\s*:', r'"country_rating"\s*:']:
        require(not re.search(pattern, text, re.I), f"Forbidden output field {pattern}")
    validator_text = (ROOT / (PREFIX + "validate_technical_retry_protocol.py")).read_text(encoding="utf-8")
    parsed = ast.parse(validator_text)
    imported = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    require(not imported.intersection({"requests", "urllib.request", "socket", "http.client"}), "Validator has network imports")

    changed = git("diff", "--name-only", BASE, "--").decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    scope_paths = sorted(set(changed + untracked))
    require(len(scope_paths) == 6 and all(path.startswith(PREFIX) and Path(path).name in FILES for path in scope_paths), "Scope mismatch")
    subprocess.check_call(["git", "diff", "--check", BASE, "--"], cwd=ROOT)
    for name in FILES:
        path = ROOT / (PREFIX + name)
        require(path.read_bytes().endswith(b"\n"), f"Missing newline {name}")
        require(all(line == line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()), f"Trailing whitespace {name}")
    result = {
        "status": "PASS_TECHNICAL_ONLY",
        "counts": receipt["counts"],
        "protocol_id": plan["protocol_id"],
        "output_pins": "PASS",
        "release_state": receipt["release_state"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
