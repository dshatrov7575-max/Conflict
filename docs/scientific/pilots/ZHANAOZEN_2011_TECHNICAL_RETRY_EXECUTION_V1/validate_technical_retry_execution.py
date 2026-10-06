from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "bf22b205b36a4401c15751860fd55e95f0d71459"
BASE_TREE = "b8c87f378715e2f80975479b4bbf21cd87b55675"
PREFIX = "docs/scientific/pilots/ZHANAOZEN_2011_TECHNICAL_RETRY_EXECUTION_V1/"
FILES = {"EXECUTION_CLAIM_JOURNAL.jsonl", "EXECUTED_RETRY_LEDGER.json", "EXECUTION_SUMMARY.md", "VALIDATION_RECEIPT.json", "FREEZE_MANIFEST.json", "validate_technical_retry_execution.py"}


def require(c, m):
    if not c:
        raise AssertionError(m)


def read_json(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8-sig"))


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def git(*args):
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(["git", *args], cwd=ROOT, env=env)


def verify(pin, base=False):
    raw = (ROOT / pin["path"]).read_bytes()
    require(len(raw) == pin["bytes"] and sha256(raw) == pin["sha256"] and blob(raw) == pin["git_blob_sha1"], f"Pin mismatch {pin['path']}")
    if base:
        require(git("rev-parse", f"{BASE}:{pin['path']}").decode().strip() == pin["git_blob_sha1"], f"Base mismatch {pin['path']}")


def main():
    head = git("rev-parse", "HEAD").decode().strip()
    if head != BASE:
        require(git("rev-parse", "HEAD^").decode().strip() == BASE, "Not one commit over base")
    require(git("rev-parse", f"{BASE}^{{tree}}").decode().strip() == BASE_TREE, "Base tree")
    ledger = read_json(PREFIX + "EXECUTED_RETRY_LEDGER.json")
    receipt = read_json(PREFIX + "VALIDATION_RECEIPT.json")
    manifest = read_json(PREFIX + "FREEZE_MANIFEST.json")
    plan = read_json("docs/scientific/pilots/ZHANAOZEN_2011_TECHNICAL_RETRY_PROTOCOL_V1/TECHNICAL_RETRY_PLAN.json")
    patch = read_json("docs/scientific/pilots/ZHANAOZEN_2011_TECHNICAL_RETRY_PROTOCOL_V1_1_PATCH/PROTOCOL_PATCH.json")
    journal_lines = [json.loads(line) for line in (ROOT / (PREFIX + "EXECUTION_CLAIM_JOURNAL.jsonl")).read_text(encoding="utf-8").splitlines() if line]

    require(ledger["base_commit"] == BASE and ledger["base_tree"] == BASE_TREE, "Ledger base")
    require(ledger["protocol_id"] == plan["protocol_id"] and ledger["protocol_patch_id"] == patch["patch_id"], "Protocol identity")
    require(ledger["logical_retry_execution_budget"] == 4 and ledger["maximum_http_subrequest_budget"] == 6, "Budget")
    require(ledger["automatic_library_retries"] == 0, "Automatic retries")
    require(ledger["logical_retry_executions"] == 4 and len(ledger["attempts"]) == 4, "Logical executions")
    require(ledger["http_subrequests_executed"] <= 6, "Subrequest budget")
    require(len({row["retry_attempt_id"] for row in ledger["attempts"]}) == 4, "Duplicate retry")
    require({row["retry_attempt_id"] for row in ledger["attempts"]} == {row["retry_attempt_id"] for row in plan["retry_units"]}, "Retry coverage")
    require(all(row["execution_count_for_retry_attempt_id"] == 1 and row["terminal_for_retry_attempt_id"] is True and row["rerun_performed"] is False for row in ledger["attempts"]), "Execution terminality")
    require(sum(row["http_subrequest_count"] for row in ledger["attempts"]) == ledger["http_subrequests_executed"], "Subrequest count")
    require(ledger["query_expansion_performed"] is False and ledger["mirror_search_performed"] is False and ledger["publisher_rerun_performed"] is False and ledger["alternate_candidate_performed"] is False and ledger["substantive_search_performed"] is False, "Forbidden search")
    require(ledger["payload_bodies_stored"] is False and ledger["source_protocol_files_mutated"] is False, "Storage/mutation")
    require(ledger["exact_edition_contracts_satisfied"] == 0 and ledger["mapping_admission_changes"] == 0 and ledger["scientific_state_changes"] == 0, "Scientific state")

    by_retry = {row["retry_attempt_id"]: row for row in plan["retry_units"]}
    for row in ledger["attempts"]:
        unit = by_retry[row["retry_attempt_id"]]
        require(row["linked_failed_source_attempt_id"] == unit["linked_failed_source_attempt_id"], "Source link")
        require(row["planned_query_id"] == unit["planned_query_id"] and row["query_text_sha256"] == unit["query_text_sha256"], "Query binding")
        require(row["information_cutoff"] == unit["information_cutoff"], "Cutoff")
        require(row["full_edition_status_after_retry"] == "NOT_PROVEN" and row["mapping_admission_changed"] is False and row["target_time_applicability"] == "UNKNOWN" and row["automatic_carry_forward"] is False and row["scientific_state_changed_by_pr21"] is False, "State changed")
        require(row["exact_edition_contract_satisfied"] is False and row["exact_document_version_full_edition_binding"] is False and row["admission_decision"] == "RETAIN_NOT_PROVEN", "Admission")
        if unit["failure_class"] == "INITIAL_ARCHIVE_QUERY_FAILURE":
            require(row["http_subrequest_count"] in (1, 2), "Initial subrequest count")
            require(row["subrequests"][0]["subrequest_role"] == "WAYBACK_CDX_LOOKUP", "Initial role")
            require(row["subrequests"][0]["request_url"] == unit["future_retry_contract"]["exact_target_locator"], "CDX locator")
            if row["http_subrequest_count"] == 2:
                require(row["subrequests"][1]["subrequest_role"] == "WAYBACK_REPLAY_PAYLOAD", "Replay role")
        else:
            require(row["http_subrequest_count"] == 1 and row["subrequests"][0]["subrequest_role"] == "WAYBACK_REPLAY_PAYLOAD", "Replay-only count")
            require(row["subrequests"][0]["request_url"] == unit["future_retry_contract"]["exact_target_locator"], "Replay locator")

    sequences = [line["sequence"] for line in journal_lines]
    require(sequences == list(range(1, len(journal_lines) + 1)), "Journal sequence")
    claims = [line for line in journal_lines if line["event"] == "SUBREQUEST_CLAIM"]
    results = [line for line in journal_lines if line["event"] == "SUBREQUEST_RESULT"]
    require(len(claims) == ledger["http_subrequests_executed"] and len(results) == len(claims), "Journal claim/result count")
    require(len({line["claim_id"] for line in claims}) == len(claims), "Duplicate claim")
    result_by_claim = {line["claim_id"]: line for line in results}
    for claim in claims:
        require(claim["claim_id"] in result_by_claim, "Claim without result")
        require(claim["sequence"] < result_by_claim[claim["claim_id"]]["sequence"], "Result before claim")
        require(claim["automatic_retries"] == 0 and claim["connect_timeout_seconds"] == 15 and claim["read_timeout_seconds"] == 45 and claim["maximum_redirects"] == 5, "Claim transport")
    require(len([line for line in journal_lines if line["event"] == "LOGICAL_RETRY_EXECUTION_START"]) == 4, "Logical starts")
    require(len([line for line in journal_lines if line["event"] == "LOGICAL_RETRY_EXECUTION_END"]) == 4, "Logical ends")
    require(journal_lines[0]["event"] == "EXECUTION_START" and journal_lines[-1]["event"] == "EXECUTION_END", "Journal boundaries")

    require(receipt["status"] == "PASS_TECHNICAL_ONLY" and receipt["counts"]["logical_retry_executions"] == 4 and receipt["counts"]["http_subrequests_executed"] == ledger["http_subrequests_executed"], "Receipt")
    for p in manifest["inputs"]:
        verify(p, base=True)
    for p in manifest["outputs"]:
        verify(p)
    require(manifest["payload_bodies_stored"] is False and manifest["source_files_mutated"] is False, "Manifest boundary")

    changed = git("diff", "--name-only", BASE, "--").decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    scope = sorted(set(changed + untracked))
    require(len(scope) == 6 and all(path.startswith(PREFIX) and Path(path).name in FILES for path in scope), "Scope")
    subprocess.check_call(["git", "diff", "--check", BASE, "--"], cwd=ROOT)
    for name in FILES:
        path = ROOT / (PREFIX + name)
        require(path.read_bytes().endswith(b"\n"), f"Newline {name}")
        require(all(line == line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()), f"Whitespace {name}")
    print(json.dumps({"status": "PASS_TECHNICAL_ONLY", "run_id": ledger["run_id"], "logical_retry_executions": 4, "http_subrequests_executed": ledger["http_subrequests_executed"], "response_status_counts": ledger["response_status_counts"], "result_state_counts": ledger["result_state_counts"], "output_pins": "PASS", "release_state": receipt["release_state"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
