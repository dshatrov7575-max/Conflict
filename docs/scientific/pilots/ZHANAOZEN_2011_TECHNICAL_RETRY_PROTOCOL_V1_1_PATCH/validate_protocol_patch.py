from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "8150ce7c7d001f6e75c0c03cdc93aa0b8c5e4db1"
BASE_TREE = "c2e6c4ec21609507689c5c62302a0fc00c0ad6a2"
PREFIX = "docs/scientific/pilots/ZHANAOZEN_2011_TECHNICAL_RETRY_PROTOCOL_V1_1_PATCH/"
FILES = {"PROTOCOL_PATCH.json", "PROTOCOL_PATCH.md", "VALIDATION_RECEIPT.json", "FREEZE_MANIFEST.json", "validate_protocol_patch.py"}


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
    patch = read_json(PREFIX + "PROTOCOL_PATCH.json")
    receipt = read_json(PREFIX + "VALIDATION_RECEIPT.json")
    manifest = read_json(PREFIX + "FREEZE_MANIFEST.json")
    v1 = read_json("docs/scientific/pilots/ZHANAOZEN_2011_TECHNICAL_RETRY_PROTOCOL_V1/TECHNICAL_RETRY_PLAN.json")
    require(v1["future_retry_budget"]["authorized_attempts"] == 4, "V1 logical units")
    require(v1["future_retry_budget"]["maximum_executions_per_failed_source_attempt"] == 1, "V1 per-unit budget")
    require(v1["future_retry_budget"]["total_maximum_future_http_attempts"] == 4, "V1 ambiguous field missing")
    require(len(v1["retry_units"]) == 4, "V1 unit count")
    require(sum(u["failure_class"] == "INITIAL_ARCHIVE_QUERY_FAILURE" for u in v1["retry_units"]) == 2, "Initial count")
    require(sum(u["failure_class"] == "REPLAY_AFTER_CANDIDATE_FAILURE" for u in v1["retry_units"]) == 2, "Replay count")
    budget = patch["authoritative_v1_1_budget"]
    require(budget == {"logical_retry_execution_units": 4, "maximum_executions_per_retry_attempt_id": 1, "initial_failure_units": 2, "maximum_http_subrequests_per_initial_failure_unit": 2, "replay_failure_units": 2, "maximum_http_subrequests_per_replay_failure_unit": 1, "maximum_total_http_subrequests": 6, "automatic_library_retries": 0, "extra_http_subrequests_beyond_frozen_stage": 0}, "Patched budget")
    require(patch["interpretation_rule"]["all_other_v1_protocol_fields"] == "UNCHANGED_AND_STILL_AUTHORITATIVE", "Overbroad patch")
    require(patch["execution_state"] == "NOT_EXECUTED_PROTOCOL_PATCH_ONLY", "Patch executed")
    require(patch["network_access_executed_by_pr20a"] is False and patch["retrieval_executed_by_pr20a"] is False and patch["retry_execution_authorized_by_pr20a"] is False, "Execution flags")
    require(patch["scientific_state_changed_by_pr20a"] is False, "Scientific state")
    require(receipt["status"] == "PASS_TECHNICAL_ONLY" and receipt["counts"]["maximum_total_http_subrequests"] == 6, "Receipt")
    for p in manifest["inputs"]:
        verify(p, base=True)
    for p in manifest["outputs"]:
        verify(p)
    changed = git("diff", "--name-only", BASE, "--").decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    scope = sorted(set(changed + untracked))
    require(len(scope) == 5 and all(x.startswith(PREFIX) and Path(x).name in FILES for x in scope), "Scope")
    subprocess.check_call(["git", "diff", "--check", BASE, "--"], cwd=ROOT)
    for name in FILES:
        path = ROOT / (PREFIX + name)
        require(path.read_bytes().endswith(b"\n"), f"Newline {name}")
        require(all(line == line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()), f"Whitespace {name}")
    print(json.dumps({"status": "PASS_TECHNICAL_ONLY", "patch_id": patch["patch_id"], "logical_retry_units": 4, "maximum_total_http_subrequests": 6, "output_pins": "PASS", "release_state": receipt["release_state"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
