"""Read-only validation for the PR-16 inherited witness provenance replay."""
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
from collections import Counter, defaultdict
from datetime import datetime, timezone

BASE = "7bb97104a0f70c9b2d331b955eba440e1bee35ee"
BASE_TREE = "a92cdb777038c5901ed7bc4283b62b6f35fe97c3"
REPLAY_ID = "ZHANAOZEN_2011_INHERITED_WITNESS_REPLAY_V1"
REPLAY_NAMESPACE = uuid.UUID("c278e8cf-478f-54e8-82b5-e72d472556af")
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREFIX = HERE.relative_to(ROOT).as_posix() + "/"
PR15 = "docs/scientific/pilots/ZHANAOZEN_2011_RECOVERY_PROTOCOL_V1/"
REC = "docs/scientific/admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/"
FILES = {
    "EXECUTED_ATTEMPT_LEDGER.json", "WITNESS_QUERY_BINDING.json",
    "REPLAY_VALIDATION_RECEIPT.json", "FREEZE_MANIFEST.json",
    "README.md", "validate_witness_replay.py",
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
    require(candidate.is_relative_to(ROOT), f"Outside repository: {path}")
    require(candidate.is_file(), f"Missing file: {path}")
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
def canonical_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(raw)


def unique(values, label: str) -> None:
    values = list(values)
    require(len(values) == len(set(values)), f"Duplicate {label}")


def resolve_pointer(data, pointer: str):
    require(pointer == "" or pointer.startswith("/"), "Bad JSON pointer")
    current = data
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def verify_pin(pin: dict, *, bind_to_base: bool = False) -> None:
    raw = local(pin["path"]).read_bytes()
    require(len(raw) == pin["bytes"], f"Byte count mismatch: {pin['path']}")
    require(sha256(raw) == pin["sha256"], f"SHA-256 mismatch: {pin['path']}")
    require(git_blob(raw) == pin["git_blob_sha1"], f"Blob mismatch: {pin['path']}")
    if bind_to_base:
        recorded = git("rev-parse", f"{BASE}:{pin['path']}").decode().strip()
        require(recorded == pin["git_blob_sha1"], f"Base binding mismatch: {pin['path']}")


def verify_base_blobs() -> int:
    count = 0
    for entry in git("ls-tree", "-rz", "-r", BASE).split(b"\0"):
        if not entry:
            continue
        metadata, raw_name = entry.split(b"\t", 1)
        _mode, kind, object_id = metadata.split()
        require(kind == b"blob", "Unexpected non-blob in base tree")
        path = raw_name.decode("utf-8")
        require(git_blob(local(path).read_bytes()) == object_id.decode(), f"Base blob changed: {path}")
        count += 1
    return count


def check_no_results(value) -> None:
    forbidden = {
        "factor_value", "assessment_value", "numeric_anchor", "anchor", "score",
        "weight", "weights", "outcome", "outcome_class", "calculated_result",
        "probability", "risk", "country_score", "validation_record", "uno",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            require(key.lower() not in forbidden, f"Forbidden result field: {key}")
            check_no_results(child)
    elif isinstance(value, list):
        for child in value:
            check_no_results(child)
    elif isinstance(value, str):
        pattern = r"\b(?:POS|KVS|RGU|KVPTN|UNO|Pol)\s*[:=]\s*[+-]?\d"
        require(not re.search(pattern, value, re.I), "Encoded numeric factor result")


def run_pr15_validator() -> dict:
    temp_path = Path(tempfile.gettempdir()) / f"conflict-pr15-validate-{uuid.uuid4().hex}"
    try:
        subprocess.check_call(
            ["git", "worktree", "add", "--detach", str(temp_path), BASE], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        validator = temp_path / PR15 / "validate_recovery_protocol.py"
        output = subprocess.check_output(
            [sys.executable, "-B", str(validator)], cwd=temp_path, text=True, encoding="utf-8",
        )
        result = json.loads(output)
        require(result["status"] == "PASS_TECHNICAL_ONLY", "PR-15 validator did not pass")
        require(result["output_pins"] == "PASS", "PR-15 output pins did not pass")
        return result
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(temp_path)], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        shutil.rmtree(temp_path, ignore_errors=True)


def validate() -> dict:
    require(git("rev-parse", f"{BASE}^{{tree}}").decode().strip() == BASE_TREE, "Base tree mismatch")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT)
    actual_files = {path.name for path in HERE.iterdir() if path.is_file()}
    require(actual_files == FILES, f"Expected exactly six files, found {sorted(actual_files)}")
    require(not any(path.is_dir() for path in HERE.iterdir()), "Unexpected subdirectory")

    manifest = read_json(PREFIX + "FREEZE_MANIFEST.json")
    ledger = read_json(PREFIX + "EXECUTED_ATTEMPT_LEDGER.json")
    binding = read_json(PREFIX + "WITNESS_QUERY_BINDING.json")
    receipt = read_json(PREFIX + "REPLAY_VALIDATION_RECEIPT.json")
    plan = read_json(PR15 + "RECOVERY_PLAN.json")
    source = read_json(REC + "AVAILABILITY_WITNESSES.json")

    require(manifest["base_commit"] == BASE and manifest["base_tree"] == BASE_TREE, "Manifest base mismatch")
    unique((pin["path"] for pin in manifest["inputs"]), "input pin")
    unique((pin["path"] for pin in manifest["outputs"]), "output pin")
    for pin in manifest["inputs"]:
        verify_pin(pin, bind_to_base=True)
    expected_outputs = {PREFIX + name for name in FILES if name != "FREEZE_MANIFEST.json"}
    require({pin["path"] for pin in manifest["outputs"]} == expected_outputs, "Output pin coverage mismatch")
    for pin in manifest["outputs"]:
        verify_pin(pin)

    pr15_result = run_pr15_validator()
    base_blob_count = verify_base_blobs()
    require(base_blob_count == 771, "Unexpected base blob count")
    for value in (ledger, binding, receipt):
        check_no_results(value)
    require(ledger["artifact_kind"] == "INHERITED_WITNESS_EXECUTION_LEDGER", "Wrong ledger kind")
    require(ledger["assessor_type"] == "AI_PREPARATION", "Wrong ledger assessor")
    require(ledger["replay_id"] == REPLAY_ID, "Wrong replay ID")
    require(ledger["base_commit"] == BASE and ledger["base_tree"] == BASE_TREE, "Ledger base mismatch")
    require(ledger["plan_id"] == plan["plan_id"] and ledger["case_id"] == plan["case_id"], "Ledger plan identity changed")
    require(ledger["execution_mode"] == "INHERITED_PRE_PROTOCOL_WITNESS_REPLAY_ONLY", "Replay mode changed")
    require(ledger["network_search_executed_by_pr16"] is False, "PR-16 network search reported")
    require(ledger["substantive_review_executed_by_pr16"] is False, "PR-16 substantive review reported")
    require(ledger["live_query_budget_consumed"] == 0, "Live query budget consumed")
    require(ledger["append_only"] is True, "Ledger not append-only")
    require(ledger["source_status"] == "INHERITED_REPLAY_NOT_LIVE_EXECUTION", "Replay misclassified as live execution")

    attempts = ledger["attempts"]
    bindings = binding["bindings"]
    witnesses = source["witnesses"]
    require(len(attempts) == len(bindings) == len(witnesses) == 18, "Expected 18 replay records")
    unique((attempt["attempt_id"] for attempt in attempts), "replay attempt ID")
    unique((attempt["planned_query_id"] for attempt in attempts), "planned query binding")
    unique((row["witness_id"] for row in bindings), "bound witness ID")
    unique((row["planned_query_id"] for row in bindings), "binding query ID")

    witness_by_id = {witness["witness_id"]: witness for witness in witnesses}
    attempt_by_id = {attempt["attempt_id"]: attempt for attempt in attempts}
    plan_blocker_by_id = {unit["blocker_id"]: unit for unit in plan["blocker_units"]}
    binding_by_witness = {row["witness_id"]: row for row in bindings}
    unique_fragments = set()
    version_ids = set()
    cutoff = datetime.fromisoformat(plan["target_time"].replace("Z", "+00:00"))
    for source_index, witness in enumerate(witnesses):
        row = binding_by_witness[witness["witness_id"]]
        require(row["source_witness_reference"] == {
            "path": REC + "AVAILABILITY_WITNESSES.json",
            "json_pointer": f"/witnesses/{source_index}",
        }, "Witness source pointer changed")
        require(row["source_witness_sha256"] == canonical_hash(witness), "Witness source hash mismatch")
        require(row["document_version_id"] == witness["document_version_id"], "DocumentVersion binding changed")
        unit = plan_blocker_by_id[row["blocker_id"]]
        require(unit["scope"] == "DOCUMENT_VERSION", "Witness bound outside DocumentVersion blocker")
        require(unit["affected_ids"]["document_version_ids"] == [witness["document_version_id"]], "Blocker version mismatch")
        resolved_unit = resolve_pointer(plan, row["plan_blocker_reference"]["json_pointer"])
        resolved_query = resolve_pointer(plan, row["plan_query_reference"]["json_pointer"])
        require(resolved_unit == unit, "Plan blocker pointer mismatch")
        require(resolved_query["query_id"] == row["planned_query_id"], "Plan query pointer mismatch")
        require(resolved_query["route_id"] == "ROUTE_AUTHENTICATED_FRAGMENT_WITNESS", "Wrong replay route")
        require(resolved_query["execution_state"] == "NOT_EXECUTED", "PR-15 query state mutated")
        require(row["planned_query_template_id"] == resolved_query["query_template_id"], "Template binding mismatch")
        require(row["planned_query_ordinal"] == resolved_query["query_ordinal"], "Query ordinal mismatch")
        require(row["binding_mode"] == "REFERENCE_ONLY_INHERITED_REPLAY", "Replay overclaimed")
        require(row["query_budget_effect"] == "NONE_LEGACY_REPLAY", "Replay consumed query budget")

        replay_id = str(uuid.uuid5(REPLAY_NAMESPACE, f"{REPLAY_ID}|{witness['witness_id']}|{resolved_query['query_id']}"))
        require(row["replay_attempt_id"] == replay_id, "Replay attempt ID not deterministic")
        attempt = attempt_by_id[replay_id]
        require(attempt["witness_id"] == witness["witness_id"], "Attempt witness mismatch")
        require(attempt["planned_query_id"] == resolved_query["query_id"], "Attempt query mismatch")
        require(attempt["blocker_id"] == unit["blocker_id"], "Attempt blocker mismatch")
        require(attempt["route_id"] == "ROUTE_AUTHENTICATED_FRAGMENT_WITNESS", "Attempt route mismatch")
        require(attempt["query_ordinal"] == resolved_query["query_ordinal"], "Attempt ordinal mismatch")
        require(attempt["query_text_sha256"] == resolved_query["query_text_sha256"], "Attempt query hash mismatch")
        require(attempt["attempt_class"] == "INHERITED_PRE_PROTOCOL_WITNESS_REPLAY", "Attempt class changed")
        require(attempt["result_state"] == "NOT_ADMISSIBLE", "Replay became a new admission result")
        require(attempt["error_state"] == "NONE", "Inherited witness marked as error")
        require(attempt["admissibility_contract_satisfied"] is False, "PR-15 live contract falsely satisfied")
        require(attempt["prior_status_retained"] == "PROVEN_FRAGMENT_PRE_CUTOFF", "Inherited fragment status not retained")
        require(attempt["query_budget_effect"] == "NONE_LEGACY_REPLAY", "Replay budget effect changed")
        require(attempt["network_used_by_pr16"] is False, "PR-16 network use claimed")
        require(attempt["substantive_review_by_pr16"] is False, "PR-16 review claimed")
        require(attempt["scientific_state_changed_by_pr16"] is False, "Scientific state changed")
        require(attempt["requested_at_utc"] is None and attempt["content_type"] is None, "Missing inherited fields invented")
        require(attempt["completed_at_utc"] == witness["retrieved_at_utc"], "Retrieval timestamp changed")
        require(attempt["locator"] == witness["archive_replay_url"], "Witness locator changed")
        require(attempt["retrieved_bytes"] == witness["payload_bytes"], "Witness byte count changed")
        require(attempt["retrieved_sha256"] == witness["retrieved_payload_sha256"], "Witness SHA-256 changed")
        require(attempt["archive_capture_timestamp"] == witness["archive_capture_timestamp"], "Capture timestamp changed")
        require(attempt["archive_digest_sha1_base32"] == witness["archive_digest_sha1_base32"], "Archive SHA-1 changed")
        require(attempt["retrieved_payload_sha1_base32"] == witness["retrieved_payload_sha1_base32"], "Payload SHA-1 changed")
        require(witness["archive_digest_sha1_base32"] == witness["retrieved_payload_sha1_base32"], "Inherited CDX/payload digest mismatch")
        capture = datetime.strptime(witness["archive_capture_timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        require(capture <= cutoff, "Inherited witness capture is after cutoff")
        require(attempt["proof_scope"] == "FRAGMENT_TEXT_AND_THIS_ARCHIVED_CONTEXT_ONLY_NOT_LATE_CP3_EDITION_IDENTITY", "Proof scope promoted")
        require(attempt["publication_date_used_as_proof"] is False, "Publication date used as proof")
        require(attempt["frozen_chain_rebound"] is False, "Frozen chain rebound")
        require(attempt["matched_fragments"] == witness["matched_fragments"], "Matched fragments changed")
        for fragment in witness["matched_fragments"]:
            require(fragment["literal_in_extracted_text"] is True, "Inherited fragment not literal")
            require(sha256(fragment["exact_frozen_fragment"].encode("utf-8")) == fragment["fragment_sha256"], "Fragment hash mismatch")
            unique_fragments.add(fragment["fragment_id"])
        version_ids.add(witness["document_version_id"])
    require(len(version_ids) == 11, "Expected 11 DocumentVersion blockers")
    require(len(unique_fragments) == 17, "Expected 17 unique proven fragments")
    require(binding["coverage"] == {
        "witnesses": 18,
        "document_versions": 11,
        "unique_fragments": 17,
        "unique_query_bindings": 18,
        "live_query_budget_consumed": 0,
    }, "Binding coverage changed")
    require(binding["boundaries"] == {
        "network_search_executed_by_pr16": False,
        "substantive_review_executed_by_pr16": False,
        "full_edition_promotion": False,
        "scientific_state_change": False,
    }, "Binding boundaries changed")

    source_by_version = defaultdict(list)
    binding_by_version = defaultdict(list)
    for witness in witnesses:
        source_by_version[witness["document_version_id"]].append(witness)
    for row in bindings:
        binding_by_version[row["document_version_id"]].append(row)
    for version_id in version_ids:
        source_rows = sorted(source_by_version[version_id], key=lambda row: (row["archive_capture_timestamp"], row["witness_id"]))
        bound_rows = sorted(binding_by_version[version_id], key=lambda row: row["planned_query_ordinal"])
        require([row["witness_id"] for row in bound_rows] == [row["witness_id"] for row in source_rows], "Chronological binding changed")
        require(len(bound_rows) <= 2, "More inherited witnesses than frozen fragment slots")

    summaries = {row["document_version_id"]: row for row in binding["document_version_summary"]}
    require(set(summaries) == version_ids, "Version summary coverage changed")
    for version_id, summary in summaries.items():
        require(summary["full_edition_status"] == "NOT_PROVEN_UNCHANGED", "Edition status promoted")
        require(summary["query_budget_effect"] == "NONE_LEGACY_REPLAY", "Summary budget effect changed")
        require(summary["witness_count"] == len(source_by_version[version_id]), "Witness summary count changed")
        require(set(summary["fragment_ids"]) == {fragment["fragment_id"] for witness in source_by_version[version_id] for fragment in witness["matched_fragments"]}, "Fragment summary changed")

    scientific = ledger["scientific_state"]
    require(scientific["full_edition_status"] == "NOT_PROVEN_UNCHANGED", "Full edition promoted")
    require(scientific["mapping_admission"] == "UNCHANGED", "Mapping admission changed")
    require(scientific["target_time"] == "UNKNOWN_UNCHANGED", "Target time changed")
    require(scientific["historical_area_UNO"] == "NOT_COMPUTED_BLOCKED", "UNO boundary changed")
    changed = git("diff", "--name-only", BASE, "--").decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    require(all(path.startswith(PREFIX) and Path(path).name in FILES for path in changed + untracked), "Changes outside PR-16 scope")
    subprocess.check_call(["git", "diff", "--check", BASE, "--"], cwd=ROOT)
    for name in FILES:
        text = local(PREFIX + name).read_text(encoding="utf-8")
        require(text.endswith("\n"), f"Missing final newline: {name}")
        require(all(line == line.rstrip() for line in text.splitlines()), f"Trailing whitespace: {name}")

    expected_receipt = {
        "artifact_kind": "INHERITED_WITNESS_REPLAY_VALIDATION_RECEIPT",
        "assessor_type": "AI_PREPARATION",
        "status": "PASS_TECHNICAL_ONLY",
        "base_commit": BASE,
        "base_tree": BASE_TREE,
        "checks": [
            "exact_base_and_prior_blobs", "pr15_validator_and_output_pins",
            "strict_json_and_unique_ids", "eighteen_witnesses_byte_and_digest_bound",
            "eleven_document_version_blockers", "seventeen_unique_fragments",
            "deterministic_one_to_one_query_binding", "no_live_query_budget_consumed",
            "fragment_only_proof_scope", "no_full_edition_promotion",
            "no_new_network_or_substantive_review", "no_scientific_state_change",
            "six_file_scope_and_git_diff_check",
        ],
        "counts": {
            "base_blobs_verified": base_blob_count,
            "manifest_input_pins": len(manifest["inputs"]),
            "manifest_output_pins": len(manifest["outputs"]),
            "source_witnesses": len(witnesses),
            "replay_records": len(attempts),
            "document_version_blockers": len(version_ids),
            "unique_proven_fragments": len(unique_fragments),
            "planned_query_bindings": len(bindings),
            "live_query_budget_consumed": ledger["live_query_budget_consumed"],
            "missing_content_type_retained_null": sum(attempt["content_type"] is None for attempt in attempts),
            "missing_requested_at_retained_null": sum(attempt["requested_at_utc"] is None for attempt in attempts),
        },
        "pr15_validator": pr15_result,
        "scientific_boundaries": {
            "full_edition_status": "NOT_PROVEN_UNCHANGED",
            "fragment_status": "INHERITED_PROVEN_FRAGMENT_PRE_CUTOFF_RETAINED",
            "mapping_admission": "UNCHANGED",
            "target_time": "UNKNOWN_UNCHANGED",
            "human_validation_reliability": "NOT_PERFORMED",
            "historical_snapshot": "NOT_ESTABLISHED",
            "historical_area_UNO": "NOT_COMPUTED_BLOCKED",
            "predictive_probability_risk_validation": "NOT_CLAIMED",
            "publication_release_deployment": "NOT_EXECUTED",
            "network_and_substantive_review_by_pr16": "NOT_EXECUTED",
        },
    }
    require(receipt == expected_receipt, "Stored replay receipt is not reproducible")
    require(manifest["scope"] == {
        "allowed_directory": PREFIX.rstrip("/"),
        "file_count": 6,
        "existing_files_modified": False,
        "network_search_executed_by_pr16": False,
        "substantive_review_executed_by_pr16": False,
        "live_query_budget_consumed": 0,
        "scientific_state_changed": False,
        "human_coding": "NOT_PERFORMED",
        "historical_area_UNO": "NOT_COMPUTED_BLOCKED",
        "publication_release_deployment": "NOT_EXECUTED",
    }, "Manifest scope changed")

    readme = local(PREFIX + "README.md").read_text(encoding="utf-8")
    for text in (
        "AI preparation only", "18 already preserved archive witnesses",
        "11 DocumentVersion blockers", "17 unique fragments",
        "Network search by PR-16: NOT_EXECUTED",
        "result_state=NOT_ADMISSIBLE", "query_budget_effect=NONE_LEGACY_REPLAY",
        "Fragment proof remains fragment-only", "historical UNO",
    ):
        require(text.lower() in readme.lower(), f"README boundary missing: {text}")

    fixture_results = {
        "no_query_reuse": len({attempt["planned_query_id"] for attempt in attempts}) == 18,
        "no_live_budget_consumption": ledger["live_query_budget_consumed"] == 0,
        "no_full_edition_promotion": scientific["full_edition_status"] == "NOT_PROVEN_UNCHANGED",
        "no_new_admission": all(attempt["admissibility_contract_satisfied"] is False for attempt in attempts),
        "missing_fields_not_invented": all(attempt["content_type"] is None and attempt["requested_at_utc"] is None for attempt in attempts),
        "no_pr16_network": ledger["network_search_executed_by_pr16"] is False,
    }
    require(all(fixture_results.values()), "A replay fail-closed fixture failed")
    return {
        "status": "PASS_TECHNICAL_ONLY",
        "counts": expected_receipt["counts"],
        "fixture_results": fixture_results,
        "output_pins": "PASS",
        "pr15_validator": "PASS_TECHNICAL_ONLY",
        "replay_disposition": "PROVENANCE_BOUND_NO_NEW_ADMISSION",
    }


if __name__ == "__main__":
    try:
        require(sys.argv[1:] == [], "This validator accepts no arguments")
        print(json.dumps(validate(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
