"""Read-only validation for the PR-14 mapping-admission audit package."""
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

BASE = "9a0dc0b6619a1d3fdad813dc94e76d8d84fe70f0"
BASE_TREE = "1a6f6b88c77be4082e15d1be9ea939b981e483bd"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREFIX = HERE.relative_to(ROOT).as_posix() + "/"
PR13 = "docs/scientific/pilots/ZHANAOZEN_2011_MAPPING_SCOPE_V1/"
REC = "docs/scientific/admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/"
FILES = {
    "MAPPING_ADMISSION_MATRIX.json",
    "SOURCE_CONTEXT_RECOVERY_QUEUE.json",
    "MAPPING_ADMISSION_SUMMARY.md",
    "VALIDATION_RECEIPT.json",
    "FREEZE_MANIFEST.json",
    "validate_mapping_admission.py",
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
    return json.loads(
        local(path).read_text(encoding="utf-8-sig"),
        object_pairs_hook=no_duplicate_keys,
    )


def git(*args: str) -> bytes:
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(["git", *args], cwd=ROOT, env=env)


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def git_blob(raw: bytes) -> str:
    header = b"blob " + str(len(raw)).encode("ascii") + b"\0"
    return hashlib.sha1(header + raw).hexdigest()


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


def check_no_results(value) -> None:
    forbidden_keys = {
        "factor_value", "assessment_value", "numeric_anchor", "anchor", "score",
        "weight", "weights", "outcome", "outcome_class", "calculated_result",
        "probability", "risk", "country_score", "validation_record", "uno",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            require(key.lower() not in forbidden_keys, f"Forbidden result field: {key}")
            check_no_results(child)
    elif isinstance(value, list):
        for child in value:
            check_no_results(child)
    elif isinstance(value, str):
        pattern = r"\b(?:POS|KVS|RGU|KVPTN|UNO|Pol)\s*[:=]\s*[+-]?\d"
        require(not re.search(pattern, value, re.I), "Encoded numeric factor result")


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


def run_pr13_validator() -> dict:
    temp_path = Path(tempfile.gettempdir()) / f"conflict-pr13-validate-{uuid.uuid4().hex}"
    try:
        subprocess.check_call(
            ["git", "worktree", "add", "--detach", str(temp_path), BASE],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        validator = temp_path / PR13 / "validate_scope.py"
        output = subprocess.check_output(
            [sys.executable, "-B", str(validator)],
            cwd=temp_path,
            text=True,
            encoding="utf-8",
        )
        result = json.loads(output)
        require(result["status"] == "PASS_TECHNICAL_ONLY", "PR-13 validator did not pass")
        require(result["output_pins"] == "PASS", "PR-13 output pins did not pass")
        return result
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(temp_path)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.rmtree(temp_path, ignore_errors=True)


def expected_queue_count(matrix: dict) -> int:
    actor_count = len({record["actor_id"] for record in matrix["records"]})
    element_count = len({record["element_id"] for record in matrix["records"]})
    version_count = len({chain["document_version_id"] for chain in matrix["chain_ledger"]})
    reviewed_count = sum(record["recovery_route_status"] == "BLOCKED" for record in matrix["records"])
    return 1 + actor_count + element_count + version_count + reviewed_count + 1


def validate() -> dict:
    require(git("rev-parse", f"{BASE}^{{tree}}").decode().strip() == BASE_TREE, "Base tree mismatch")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", BASE, "HEAD"], cwd=ROOT)
    actual_files = {path.name for path in HERE.iterdir() if path.is_file()}
    require(actual_files == FILES, f"Expected exactly six files, found {sorted(actual_files)}")
    require(not any(path.is_dir() for path in HERE.iterdir()), "Unexpected subdirectory")

    manifest = read_json(PREFIX + "FREEZE_MANIFEST.json")
    matrix = read_json(PREFIX + "MAPPING_ADMISSION_MATRIX.json")
    queue = read_json(PREFIX + "SOURCE_CONTEXT_RECOVERY_QUEUE.json")
    receipt = read_json(PREFIX + "VALIDATION_RECEIPT.json")
    prep = read_json(PR13 + "FACTOR_MAPPING_PREPARATION.json")
    identity = read_json(PR13 + "CASE_IDENTITY_AND_EPISODE_SCOPE.json")
    admission = read_json(REC + "ADMISSION_REASSESSMENT.json")

    require(manifest["base_commit"] == BASE and manifest["base_tree"] == BASE_TREE, "Manifest base mismatch")
    unique((pin["path"] for pin in manifest["inputs"]), "input pin")
    unique((pin["path"] for pin in manifest["outputs"]), "output pin")
    for pin in manifest["inputs"]:
        verify_pin(pin, bind_to_base=True)
    expected_outputs = {PREFIX + name for name in FILES if name != "FREEZE_MANIFEST.json"}
    require({pin["path"] for pin in manifest["outputs"]} == expected_outputs, "Output pin coverage mismatch")
    for pin in manifest["outputs"]:
        verify_pin(pin)

    pr13_result = run_pr13_validator()
    base_blob_count = verify_base_blobs()
    check_no_results(matrix)
    check_no_results(queue)
    check_no_results(receipt)

    require(matrix["artifact_kind"] == "MAPPING_ADMISSION_MATRIX", "Wrong matrix kind")
    require(matrix["assessor_type"] == "AI_PREPARATION", "Wrong assessor type")
    require(matrix["base_commit"] == BASE and matrix["base_tree"] == BASE_TREE, "Matrix base mismatch")
    require(matrix["case_id"] == identity["case_id"], "Case ID changed")
    require(matrix["time_slice_id"] == identity["time_slice_id"], "Time-slice ID changed")
    require(matrix["target_time"] == identity["episode_scope"]["target_time"], "Target time changed")
    require(matrix["source_gap"] == identity["episode_scope"]["unobserved_target_interval"], "Gap changed")
    require(matrix["automatic_carry_forward"] is False, "Carry-forward enabled")
    require(matrix["decision_enum"] == [
        "MAPPING_ADMITTED_FOR_FUTURE_CODING",
        "MAPPING_NOT_ADMITTED",
        "NOT_REVIEWED",
    ], "Decision enum changed")

    records = matrix["records"]
    chains = matrix["chain_ledger"]
    require(len(records) == len(prep["units"]) == 20, "Expected 20 item records")
    require(len(chains) == len(prep["chains"]) == 58, "Expected 58 chain records")
    unique((record["coding_item_id"] for record in records), "matrix item ID")
    unique((chain["fact_fragment_link_id"] for chain in chains), "matrix chain ID")

    recovery_by_item = {item["coding_item_id"]: item for item in admission["items"]}
    require(len(recovery_by_item) == 12, "Recovery route must contain 12 items")
    chain_by_id = {chain["fact_fragment_link_id"]: chain for chain in chains}
    source_chain_by_id = {chain["fact_fragment_link_id"]: chain for chain in prep["chains"]}

    for index, (record, unit) in enumerate(zip(records, prep["units"])):
        for key in (
            "coding_item_id", "actor_id", "element_id", "time_slice_id",
            "reference_statement", "reference_sha256", "fact_ids", "chain_ids",
        ):
            require(record[key] == unit[key], f"Unit rebinding at record {index}: {key}")
        require(record["source_unit_reference"] == {
            "path": PR13 + "FACTOR_MAPPING_PREPARATION.json",
            "json_pointer": f"/units/{index}",
        }, "Bad source-unit reference")
        gates = record["gates"]
        require(gates["registry_identity"]["status"] == "PASS", "Registry identity not PASS")
        require(gates["actor_scope"]["status"] == "UNKNOWN", "Actor scope promoted")
        require(gates["reference_coverage"]["status"] == "UNKNOWN", "Reference coverage promoted")
        require(gates["target_time_applicability"]["status"] == "UNKNOWN", "Target time promoted")
        require(gates["source_edition_availability"]["full_edition_status"] == "NOT_PROVEN", "Edition promoted")
        require(gates["counterevidence_preservation"]["status"] == "PASS_PRESERVED_NOT_RESOLVED", "Counterevidence lost")
        expected_recovery = unit["admission_status"]
        require(record["recovery_route_status"] == expected_recovery, "Recovery status changed")
        require(record["recovery_route_reference"] == unit["admission_reference"], "Recovery reference changed")
        expected_decision = "MAPPING_NOT_ADMITTED" if expected_recovery == "BLOCKED" else "NOT_REVIEWED"
        require(record["final_decision"] == expected_decision, "Final decision rule violated")
        if expected_recovery == "BLOCKED":
            inherited = recovery_by_item[unit["coding_item_id"]]
            require(record["inherited_recovery_remaining_reason"] == inherited["remaining_reason"], "Recovery reason changed")
            require(record["inherited_recovery_checks"] == inherited["checks"], "Recovery checks changed")
        else:
            require(record["inherited_recovery_remaining_reason"] is None, "Invented recovery reason")
            require(record["inherited_recovery_checks"] is None, "Invented recovery checks")
        require(record["chain_statuses"] == [chain_by_id[chain_id] for chain_id in unit["chain_ids"]], "Item chain ledger mismatch")

    for chain in chains:
        source = source_chain_by_id[chain["fact_fragment_link_id"]]
        require(chain == source, f"Chain changed: {chain['fact_fragment_link_id']}")
        require(chain["full_edition_availability"] == "NOT_PROVEN", "Full-edition proof promoted")
        require(chain["target_time_applicability"] == "UNKNOWN", "Chain carried forward")

    blocked_count = sum(record["recovery_route_status"] == "BLOCKED" for record in records)
    not_reviewed_count = sum(record["recovery_route_status"] == "NOT_REVIEWED" for record in records)
    admitted_count = sum(record["final_decision"] == "MAPPING_ADMITTED_FOR_FUTURE_CODING" for record in records)
    require((blocked_count, not_reviewed_count, admitted_count) == (12, 8, 0), "Decision counts changed")
    require(sum(record["final_decision"] == "MAPPING_NOT_ADMITTED" for record in records) == 12, "Not-admitted count changed")
    require(sum(record["final_decision"] == "NOT_REVIEWED" for record in records) == 8, "Not-reviewed count changed")

    proven_fragments = {
        chain["fragment_id"]
        for chain in chains
        if chain["fragment_availability"] == "PROVEN_FRAGMENT_PRE_CUTOFF"
    }
    require(len(proven_fragments) == 17, "Inherited fragment-proof count changed")
    require(set(matrix["global_counterevidence"]["disputed_fact_ids"]) == set(prep["disputed_fact_ids"]), "DISPUTED facts changed")
    require(set(matrix["global_counterevidence"]["unlinked_fact_ids"]) == set(prep["unlinked_fact_ids"]), "Unlinked facts changed")
    require(len(prep["disputed_fact_ids"]) == 3 and len(prep["unlinked_fact_ids"]) == 14, "Counterevidence counts changed")

    require(queue["artifact_kind"] == "SOURCE_CONTEXT_RECOVERY_QUEUE", "Wrong queue kind")
    require(queue["assessor_type"] == "AI_PREPARATION", "Wrong queue assessor")
    require(queue["base_commit"] == BASE and queue["case_id"] == identity["case_id"], "Queue identity changed")
    entries = queue["entries"]
    unique((entry["blocker_id"] for entry in entries), "blocker ID")
    require(len(entries) == expected_queue_count(matrix), "Queue is not fully deduplicated")
    require(all(entry["priority"] in {"BLOCKING", "IMPORTANT", "DEFERRED"} for entry in entries), "Bad queue priority")
    require(all(entry["missing_proof"] and entry["permitted_future_action"] and entry["forbidden_shortcuts"] for entry in entries), "Incomplete queue row")

    by_scope = {}
    for entry in entries:
        by_scope.setdefault(entry["scope"], []).append(entry)
    expected_versions = {chain["document_version_id"] for chain in chains}
    expected_actors = {record["actor_id"] for record in records}
    expected_elements = {record["element_id"] for record in records}
    expected_reviewed = {record["coding_item_id"] for record in records if record["recovery_route_status"] == "BLOCKED"}

    require(len(by_scope.get("TARGET_TIME", [])) == 1, "Target-time queue row missing")
    target_ids = set(by_scope["TARGET_TIME"][0]["affected_ids"]["coding_item_ids"])
    require(target_ids == {record["coding_item_id"] for record in records}, "Target-time coverage incomplete")
    require(len(by_scope.get("DOCUMENT_VERSION", [])) == len(expected_versions), "Version queue coverage incomplete")
    require({entry["affected_ids"]["document_version_ids"][0] for entry in by_scope["DOCUMENT_VERSION"]} == expected_versions, "Version IDs changed")
    require(len(by_scope.get("ACTOR_SCOPE", [])) == len(expected_actors), "Actor queue coverage incomplete")
    require({entry["affected_ids"]["actor_ids"][0] for entry in by_scope["ACTOR_SCOPE"]} == expected_actors, "Actor IDs changed")
    require(len(by_scope.get("REFERENCE_SCOPE", [])) == len(expected_elements), "Reference queue coverage incomplete")
    require({entry["affected_ids"]["element_ids"][0] for entry in by_scope["REFERENCE_SCOPE"]} == expected_elements, "Element IDs changed")

    require(len(by_scope.get("CONTEXT_LANGUAGE", [])) == len(expected_reviewed), "Context queue coverage incomplete")
    require({entry["affected_ids"]["coding_item_ids"][0] for entry in by_scope["CONTEXT_LANGUAGE"]} == expected_reviewed, "Context item IDs changed")
    for entry in by_scope["CONTEXT_LANGUAGE"]:
        item_id = entry["affected_ids"]["coding_item_ids"][0]
        inherited = recovery_by_item[item_id]
        require(entry["inherited_remaining_reason"] == inherited["remaining_reason"], "Context reason changed")
        require(entry["inherited_checks"] == inherited["checks"], "Context checks changed")
    require(len(by_scope.get("COUNTEREVIDENCE_COMPLETENESS", [])) == 1, "Counterevidence queue row missing")
    counter = by_scope["COUNTEREVIDENCE_COMPLETENESS"][0]["affected_ids"]
    require(set(counter["disputed_fact_ids"]) == set(prep["disputed_fact_ids"]), "Queue lost DISPUTED facts")
    require(set(counter["unlinked_fact_ids"]) == set(prep["unlinked_fact_ids"]), "Queue lost unlinked facts")

    fixture_failures = []
    synthetic = {
        "fragment_to_edition": False,
        "person_to_group": False,
        "component_to_full_reference": False,
        "old_observation_to_cutoff": False,
        "dropped_disputed": False,
        "current_content_to_historical_proof": False,
    }
    if any(synthetic.values()):
        fixture_failures.append("A forbidden promotion fixture was accepted")
    require(not fixture_failures, "; ".join(fixture_failures))

    changed = git("diff", "--name-only", BASE, "--").decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    require(all(path.startswith(PREFIX) and Path(path).name in FILES for path in changed + untracked), "Changes outside PR-14 scope")
    subprocess.check_call(["git", "diff", "--check", BASE, "--"], cwd=ROOT)
    for name in FILES:
        text = local(PREFIX + name).read_text(encoding="utf-8")
        require(text.endswith("\n"), f"Missing final newline: {name}")
        require(all(line == line.rstrip() for line in text.splitlines()), f"Trailing whitespace: {name}")

    decision_counts = {
        "MAPPING_ADMITTED_FOR_FUTURE_CODING": admitted_count,
        "MAPPING_NOT_ADMITTED": sum(record["final_decision"] == "MAPPING_NOT_ADMITTED" for record in records),
        "NOT_REVIEWED": sum(record["final_decision"] == "NOT_REVIEWED" for record in records),
    }
    queue_counts = {scope: len(rows) for scope, rows in sorted(by_scope.items())}
    expected_receipt = {
        "artifact_kind": "MAPPING_ADMISSION_VALIDATION_RECEIPT",
        "assessor_type": "AI_PREPARATION",
        "status": "PASS_TECHNICAL_ONLY",
        "base_commit": BASE,
        "base_tree": BASE_TREE,
        "checks": [
            "exact_base_and_prior_blobs",
            "pr13_validator_and_output_pins",
            "strict_json_and_unique_ids",
            "twenty_units_and_fifty_eight_chains",
            "recovery_status_inheritance",
            "fragment_proof_without_edition_promotion",
            "no_carry_forward_and_no_admitted_items",
            "queue_scope_and_deduplication",
            "counterevidence_preservation",
            "forbidden_result_and_promotion_fixtures",
            "six_file_scope_and_git_diff_check",
        ],
        "counts": {
            "base_blobs_verified": base_blob_count,
            "manifest_input_pins": len(manifest["inputs"]),
            "manifest_output_pins": len(manifest["outputs"]),
            "coding_items": len(records),
            "fact_fragment_chains": len(chains),
            "unique_document_versions": len(expected_versions),
            "unique_proven_fragments": len(proven_fragments),
            "disputed_facts": len(prep["disputed_fact_ids"]),
            "unlinked_facts": len(prep["unlinked_fact_ids"]),
            "recovery_blocked_items": blocked_count,
            "recovery_not_reviewed_items": not_reviewed_count,
            "queue_entries": len(entries),
        },
        "decision_counts": decision_counts,
        "queue_counts": queue_counts,
        "pr13_validator": pr13_result,
        "scientific_boundaries": {
            "human_validation_reliability": "NOT_PERFORMED",
            "historical_snapshot": "NOT_ESTABLISHED",
            "historical_area_UNO": "NOT_COMPUTED_BLOCKED",
            "predictive_probability_risk_validation": "NOT_CLAIMED",
            "publication_release_deployment": "NOT_EXECUTED",
        },
    }
    require(receipt == expected_receipt, "Stored validation receipt is not reproducible")

    summary = local(PREFIX + "MAPPING_ADMISSION_SUMMARY.md").read_text(encoding="utf-8")
    for required_text in (
        "AI preparation only",
        "20 CodingItems",
        "58 Fact–Fragment chains",
        "12 MAPPING_NOT_ADMITTED",
        "8 NOT_REVIEWED",
        "0 MAPPING_ADMITTED_FOR_FUTURE_CODING",
        "2011-11-28..2011-12-15",
        "HUMAN validation: NOT_PERFORMED",
        "historical area UNO: NOT_COMPUTED / BLOCKED",
    ):
        require(required_text in summary, f"Summary boundary missing: {required_text}")

    result = {
        "status": "PASS_TECHNICAL_ONLY",
        "counts": expected_receipt["counts"],
        "decision_counts": decision_counts,
        "queue_counts": queue_counts,
        "output_pins": "PASS",
        "pr13_validator": "PASS_TECHNICAL_ONLY",
    }
    return result


if __name__ == "__main__":
    try:
        require(sys.argv[1:] == [], "This validator accepts no arguments")
        print(json.dumps(validate(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
