from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
BASE = "c29a245ac8b29783aeeaecdc86477836096a2a3a"
BASE_TREE = "777a1d08b6caf60fe3bd2d57927f0f918902eb36"
PREFIX = "docs/scientific/pilots/ZHANAOZEN_2011_EXACT_EDITION_CONSOLIDATION_V1/"
FILES = {
    "CONSOLIDATED_ATTEMPT_LEDGER.json",
    "DOCUMENT_VERSION_RESIDUAL_GAP_MATRIX.json",
    "FREEZE_MANIFEST.json",
    "CONSOLIDATION_SUMMARY.md",
    "VALIDATION_RECEIPT.json",
    "validate_exact_edition_consolidation.py",
}
A_PREFIX = "docs/scientific/pilots/ZHANAOZEN_2011_EXACT_EDITION_RECOVERY_TRANCHE_A_V1/"
B_PREFIX = "docs/scientific/pilots/ZHANAOZEN_2011_EXACT_EDITION_RECOVERY_TRANCHE_B_V1/"
PLAN = "docs/scientific/pilots/ZHANAOZEN_2011_RECOVERY_PROTOCOL_V1/RECOVERY_PLAN.json"
MAPPING = "docs/scientific/pilots/ZHANAOZEN_2011_MAPPING_ADMISSION_V1/MAPPING_ADMISSION_MATRIX.json"
QUEUE = "docs/scientific/pilots/ZHANAOZEN_2011_MAPPING_ADMISSION_V1/SOURCE_CONTEXT_RECOVERY_QUEUE.json"
PR18_VALIDATOR = B_PREFIX + "validate_exact_edition_tranche.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def local(relative: str) -> Path:
    return ROOT / relative


def read_json(relative: str) -> dict:
    return json.loads(local(relative).read_text(encoding="utf-8-sig"))


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
        require(local(path).is_file(), f"Missing base file: {path}")
        require(git_blob(local(path).read_bytes()) == object_id.decode(), f"Base blob changed: {path}")
        count += 1
    return count


def run_prior_validator() -> dict:
    temp_path = Path(tempfile.gettempdir()) / f"conflict-pr18-validate-{uuid.uuid4().hex}"
    try:
        subprocess.check_call(
            ["git", "worktree", "add", "--detach", str(temp_path), BASE],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        output = subprocess.check_output(
            [sys.executable, "-B", str(temp_path / PR18_VALIDATOR)],
            cwd=temp_path,
            text=True,
            encoding="utf-8",
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0"),
        )
        return json.loads(output)
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(temp_path)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.rmtree(temp_path, ignore_errors=True)


def classify(response_status: str) -> str:
    if response_status == "FINITE_NO_RESULT":
        return "FINITE_NO_RESULT_PRIOR_STATE_RETAINED"
    if response_status.startswith("TECHNICAL_FAILURE") or response_status == "PARSER_FAILURE":
        return "TECHNICAL_FAILURE_PRIOR_STATE_RETAINED"
    return "COMPLETED_NONADMISSIBLE"


def check_no_results(value) -> None:
    forbidden_keys = {
        "factor_value",
        "assessment_value",
        "numeric_anchor",
        "anchor",
        "score",
        "weight",
        "weights",
        "outcome",
        "outcome_class",
        "calculated_result",
        "probability",
        "risk",
        "country_score",
        "validation_record",
        "uno",
        "historical_assessment",
        "human_response",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            require(key.lower() not in forbidden_keys, f"Forbidden result field: {key}")
            check_no_results(child)
    elif isinstance(value, list):
        for child in value:
            check_no_results(child)
    elif isinstance(value, str):
        require(
            not re.search(r"\b(?:POS|KVS|RGU|KVPTN|UNO|Pol)\s*[:=]\s*[+-]?\d", value, re.I),
            "Encoded numeric factor or output result",
        )


def expected_queries(plan: dict) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for unit in plan["blocker_units"]:
        version_ids = unit.get("affected_ids", {}).get("document_version_ids", [])
        if unit.get("scope") != "DOCUMENT_VERSION" or len(version_ids) != 1:
            continue
        for query in unit.get("planned_queries", []):
            if query.get("route_id") != "ROUTE_PUBLISHER_OR_ARCHIVE_EXACT_EDITION":
                continue
            query_id = query["query_id"]
            require(query_id not in rows, f"Duplicate frozen query in plan: {query_id}")
            rows[query_id] = {
                "blocker_id": unit["blocker_id"],
                "document_version_id": version_ids[0],
                "query_template_id": query["query_template_id"],
                "query_ordinal": query["query_ordinal"],
                "query_text_sha256": query["query_text_sha256"],
            }
    return rows


def source_attempts() -> tuple[list[dict], list[dict], dict, dict]:
    a_ledger = read_json(A_PREFIX + "EXECUTED_ATTEMPT_LEDGER.json")
    b_ledger = read_json(B_PREFIX + "EXECUTED_ATTEMPT_LEDGER.json")
    a_decisions = read_json(A_PREFIX + "EXACT_EDITION_DECISIONS.json")
    b_decisions = read_json(B_PREFIX + "EXACT_EDITION_DECISIONS.json")
    attempts: list[dict] = []
    for tranche_id, path, ledger in (
        (a_ledger["tranche_id"], A_PREFIX + "EXECUTED_ATTEMPT_LEDGER.json", a_ledger),
        (b_ledger["tranche_id"], B_PREFIX + "EXECUTED_ATTEMPT_LEDGER.json", b_ledger),
    ):
        for row in ledger["attempts"]:
            attempts.append({"source_tranche_id": tranche_id, "source_ledger_path": path, "row": row})
    return attempts, a_decisions["document_versions"] + b_decisions["document_versions"], a_ledger, b_ledger


def main() -> dict:
    head = git("rev-parse", "HEAD").decode().strip()
    require(head != BASE, "Validator must run on committed PR-19 HEAD")
    require(git("rev-parse", "HEAD^").decode().strip() == BASE, "PR-19 parent is not exact PR-18 HEAD")
    require(int(git("rev-list", "--count", f"{BASE}..HEAD").decode().strip()) == 1, "PR-19 must contain one commit")
    require(git("rev-parse", f"{BASE}^{{tree}}").decode().strip() == BASE_TREE, "Base tree mismatch")
    require(not git("status", "--porcelain").decode().strip(), "Worktree is not clean")

    actual_entries = list(local(PREFIX).iterdir())
    require(all(path.is_file() for path in actual_entries), "Unexpected subdirectory in PR-19 output")
    require({path.name for path in actual_entries} == FILES, "Unexpected PR-19 file set")

    manifest = read_json(PREFIX + "FREEZE_MANIFEST.json")
    receipt = read_json(PREFIX + "VALIDATION_RECEIPT.json")
    consolidated = read_json(PREFIX + "CONSOLIDATED_ATTEMPT_LEDGER.json")
    gap_matrix = read_json(PREFIX + "DOCUMENT_VERSION_RESIDUAL_GAP_MATRIX.json")
    plan = read_json(PLAN)
    mapping = read_json(MAPPING)
    queue = read_json(QUEUE)

    require(manifest["base_commit"] == BASE and manifest["base_tree"] == BASE_TREE, "Manifest base mismatch")
    require(manifest["network_access_authorized"] is False, "Manifest authorizes network access")
    require(manifest["new_retrieval_authorized"] is False, "Manifest authorizes retrieval")
    require(manifest["source_tranche_ledgers_immutable"] is True, "Source ledgers not frozen")
    require(len(manifest["inputs"]) == 9, "Unexpected input pin count")
    require(len(manifest["outputs"]) == 5, "Unexpected output pin count")
    for pin in manifest["inputs"]:
        verify_pin(pin, bind_to_base=True)
    for pin in manifest["outputs"]:
        verify_pin(pin)

    base_blob_count = verify_base_blobs()
    prior_result = run_prior_validator()
    require(prior_result["status"] == "PASS_TECHNICAL_ONLY", "PR-18 validator did not pass")
    require(prior_result["output_pins"] == "PASS", "PR-18 output pins did not pass")

    expected = expected_queries(plan)
    require(len(expected) == 54, f"Expected 54 frozen exact-edition queries, found {len(expected)}")
    require(len({row["document_version_id"] for row in expected.values()}) == 27, "Expected 27 DocumentVersions")

    source_rows, source_decisions, a_ledger, b_ledger = source_attempts()
    require(len(a_ledger["attempts"]) == 22 and len(b_ledger["attempts"]) == 32, "Source tranche sizes changed")
    require(len(source_rows) == 54, "Source attempt count mismatch")
    source_by_query: dict[str, dict] = {}
    for wrapper in source_rows:
        row = wrapper["row"]
        query_id = row["planned_query_id"]
        require(query_id not in source_by_query, f"Duplicate source query execution: {query_id}")
        require(query_id in expected, f"Unexpected source query: {query_id}")
        exp = expected[query_id]
        for field in ("blocker_id", "document_version_id", "query_template_id", "query_ordinal", "query_text_sha256"):
            require(row[field] == exp[field], f"Source query binding mismatch: {query_id} / {field}")
        require(row["route_id"] == "ROUTE_PUBLISHER_OR_ARCHIVE_EXACT_EDITION", "Unexpected source route")
        require(row["admission_decision"] == "RETAIN_NOT_PROVEN", "Source admission changed")
        require(row["prior_status_retained"] == "NOT_PROVEN", "Source prior state changed")
        require(row["admissibility_gates"]["exact_edition_contract_satisfied"] is False, "Source contract promoted")
        require(row["admissibility_gates"]["exact_document_version_full_edition_binding"] is False, "Source binding promoted")
        require(row["rerun_performed"] is False, "Source rerun recorded")
        state_field = "scientific_state_changed_by_pr17" if "scientific_state_changed_by_pr17" in row else "scientific_state_changed_by_pr18"
        require(row[state_field] is False, "Source scientific state changed")
        source_by_query[query_id] = wrapper
    require(set(source_by_query) == set(expected), "Source query union does not match frozen plan")

    source_response_counts = Counter(wrapper["row"]["response_status"] for wrapper in source_rows)
    source_status_counts = Counter(classify(wrapper["row"]["response_status"]) for wrapper in source_rows)
    require(
        source_status_counts
        == Counter(
            {
                "COMPLETED_NONADMISSIBLE": 35,
                "FINITE_NO_RESULT_PRIOR_STATE_RETAINED": 15,
                "TECHNICAL_FAILURE_PRIOR_STATE_RETAINED": 4,
            }
        ),
        "Unexpected consolidated source status counts",
    )
    publisher_attempts = [wrapper["row"] for wrapper in source_rows if wrapper["row"]["query_template_id"] == "EDITION-PUBLISHER-HISTORY"]
    archive_attempts = [wrapper["row"] for wrapper in source_rows if wrapper["row"]["query_template_id"] == "EDITION-ARCHIVE-CAPTURE"]
    require(len(publisher_attempts) == 27 and len(archive_attempts) == 27, "Expected 27 publisher and 27 archive attempts")
    archive_payloads = sum(
        row["response_status"] == "PRE_CUTOFF_CAPTURE_RETRIEVED"
        and row["admissibility_gates"].get("complete_payload_retrieved") is True
        for row in archive_attempts
    )
    archive_digests = sum(row["admissibility_gates"].get("archive_digest_verified") is True for row in archive_attempts)
    require(archive_payloads == 8 and archive_digests == 8, "Archive payload/digest count mismatch")

    require(consolidated["base_commit"] == BASE and consolidated["base_tree"] == BASE_TREE, "Consolidated ledger base mismatch")
    require(consolidated["network_access_executed_by_pr19"] is False, "PR-19 network access recorded")
    require(consolidated["new_retrieval_executed_by_pr19"] is False, "PR-19 retrieval recorded")
    require(consolidated["repository_only_consolidation"] is True, "Repository-only flag missing")
    rows = consolidated["attempts"]
    require(len(rows) == 54, "Consolidated attempt count mismatch")
    require([row["consolidation_ordinal"] for row in rows] == list(range(1, 55)), "Consolidation ordinals are not exact")
    consolidated_by_query: dict[str, dict] = {}
    for row in rows:
        query_id = row["planned_query_id"]
        require(query_id not in consolidated_by_query, f"Duplicate consolidated query: {query_id}")
        require(query_id in source_by_query, f"Unknown consolidated query: {query_id}")
        source = source_by_query[query_id]
        original = source["row"]
        require(row["source_tranche_id"] == source["source_tranche_id"], "Tranche binding mismatch")
        require(row["source_ledger_path"] == source["source_ledger_path"], "Ledger binding mismatch")
        require(row["source_attempt_id"] == original["attempt_id"], "Attempt binding mismatch")
        for field in (
            "blocker_id",
            "document_version_id",
            "document_id",
            "source_id",
            "label",
            "route_id",
            "query_template_id",
            "query_ordinal",
            "query_text_sha256",
        ):
            require(row[field] == original[field], f"Consolidated field mismatch: {query_id} / {field}")
        require(row["source_response_status"] == original["response_status"], "Response status changed")
        require(row["source_result_state"] == original["result_state"], "Result state changed")
        require(row["source_admission_decision"] == original["admission_decision"], "Admission changed")
        require(row["consolidation_status"] == classify(original["response_status"]), "Wrong consolidation classification")
        require(row["prior_full_edition_status"] == "NOT_PROVEN", "Prior full-edition status changed")
        require(row["full_edition_status_after_consolidation"] == "NOT_PROVEN", "Full-edition status promoted")
        require(row["exact_edition_contract_satisfied"] is False, "Consolidation promoted exact-edition contract")
        require(row["mapping_admission_changed"] is False, "Consolidation changed Mapping")
        require(row["no_absence_inference_permitted"] is True, "Absence inference not blocked")
        require(row["scientific_state_changed_by_pr19"] is False, "PR-19 scientific state changed")
        consolidated_by_query[query_id] = row
    require(set(consolidated_by_query) == set(expected), "Consolidated query union does not match frozen plan")
    require(Counter(row["consolidation_status"] for row in rows) == source_status_counts, "Consolidated status counts mismatch")

    require(len(source_decisions) == 27, "Source decision union does not contain 27 versions")
    source_decision_by_version = {row["document_version_id"]: row for row in source_decisions}
    require(len(source_decision_by_version) == 27, "Duplicate source DocumentVersion decision")
    source_attempts_by_version: dict[str, list[dict]] = {}
    for wrapper in source_rows:
        source_attempts_by_version.setdefault(wrapper["row"]["document_version_id"], []).append(wrapper["row"])

    require(gap_matrix["base_commit"] == BASE and gap_matrix["base_tree"] == BASE_TREE, "Gap matrix base mismatch")
    version_rows = gap_matrix["document_versions"]
    require(len(version_rows) == 27, "Gap matrix does not contain 27 versions")
    require(len({row["document_version_id"] for row in version_rows}) == 27, "Duplicate gap-matrix version")
    common_gaps = {
        "CURRENT_PUBLISHER_OR_REDIRECT_CONTENT_NOT_HISTORICAL_EXACT_EDITION_PROOF",
        "MISSING_FROZEN_COMPLETE_EDITION_BYTE_IDENTITY",
        "MISSING_EXACT_DOCUMENT_VERSION_TO_COMPLETE_EDITION_BINDING",
    }
    for row in version_rows:
        version_id = row["document_version_id"]
        require(version_id in source_decision_by_version, f"Unknown gap-matrix version: {version_id}")
        decision = source_decision_by_version[version_id]
        attempts = source_attempts_by_version[version_id]
        require(len(attempts) == 2, f"Expected two source attempts for {version_id}")
        publisher = next(item for item in attempts if item["query_template_id"] == "EDITION-PUBLISHER-HISTORY")
        archive = next(item for item in attempts if item["query_template_id"] == "EDITION-ARCHIVE-CAPTURE")
        for field in ("document_id", "source_id", "label", "frozen_source_url"):
            require(row[field] == decision[field], f"Gap-matrix identity mismatch: {version_id} / {field}")
        require(row["publisher_attempt_id"] == publisher["attempt_id"], "Publisher attempt ID mismatch")
        require(row["archive_attempt_id"] == archive["attempt_id"], "Archive attempt ID mismatch")
        require(row["publisher_response_status"] == publisher["response_status"], "Publisher status mismatch")
        require(row["archive_response_status"] == archive["response_status"], "Archive status mismatch")
        require(row["publisher_consolidation_status"] == classify(publisher["response_status"]), "Publisher classification mismatch")
        require(row["archive_consolidation_status"] == classify(archive["response_status"]), "Archive classification mismatch")
        require(row["archive_candidate_count"] == decision["archive_candidate_count"], "Archive candidate count mismatch")
        retrieved = archive["response_status"] == "PRE_CUTOFF_CAPTURE_RETRIEVED" and archive["admissibility_gates"].get("complete_payload_retrieved") is True
        require(row["pre_cutoff_archive_payload_retrieved"] is retrieved, "Archive retrieval flag mismatch")
        require(row["archive_digest_verified"] is (archive["admissibility_gates"].get("archive_digest_verified") is True), "Archive digest flag mismatch")
        require(row["full_edition_status_before"] == "NOT_PROVEN", "Prior version state changed")
        require(row["full_edition_status_after"] == "NOT_PROVEN", "Version state promoted")
        require(row["decision"] == "RETAIN_NOT_PROVEN", "Version decision changed")
        require(row["exact_edition_contract_satisfied"] is False, "Version exact-edition contract promoted")
        require(row["mapping_admission_changed"] is False, "Version Mapping changed")
        require(row["target_time_applicability"] == "UNKNOWN", "Target-time applicability changed")
        require(row["automatic_carry_forward"] is False, "Automatic carry-forward enabled")
        require(common_gaps.issubset(set(row["residual_proof_gaps"])), "Common residual proof gap missing")
        if archive["response_status"] == "FINITE_NO_RESULT":
            require("FROZEN_ARCHIVE_QUERY_RETURNED_NO_PRE_CUTOFF_CAPTURE" in row["residual_proof_gaps"], "Finite no-result gap missing")
            require(row["negative_evidence_limit"] == "FINITE_NO_RESULT_IS_NOT_PROOF_OF_ABSENCE", "Finite no-result limit missing")
            require(row["residual_technical_gaps"] == [], "Finite no-result mislabeled as technical failure")
        elif archive["response_status"].startswith("TECHNICAL_FAILURE") or archive["response_status"] == "PARSER_FAILURE":
            require("ARCHIVE_QUERY_OR_REPLAY_NOT_TECHNICALLY_COMPLETED" in row["residual_proof_gaps"], "Technical proof gap missing")
            require(row["negative_evidence_limit"] == "TECHNICAL_FAILURE_IS_NOT_PROOF_OF_ABSENCE", "Technical failure limit missing")
            require("UNRESOLVED_TECHNICAL_FAILURE_IN_FROZEN_ARCHIVE_ROUTE" in row["residual_technical_gaps"], "Technical gap missing")
        elif retrieved:
            require(
                "PRE_CUTOFF_ARCHIVE_PAYLOAD_RETRIEVED_BUT_NOT_BOUND_TO_EXACT_DOCUMENT_VERSION"
                in row["residual_proof_gaps"],
                "Retrieved-payload binding gap missing",
            )
            require(row["negative_evidence_limit"] == "NO_ABSENCE_INFERENCE_PERMITTED", "Retrieved-payload limit missing")
            require(row["residual_technical_gaps"] == [], "Retrieved payload mislabeled as technical failure")
        else:
            require(
                "ARCHIVE_ROUTE_COMPLETED_WITHOUT_ADMISSIBLE_EXACT_EDITION_PROOF" in row["residual_proof_gaps"],
                "Completed archive proof gap missing",
            )
            require(row["negative_evidence_limit"] == "NO_ABSENCE_INFERENCE_PERMITTED", "Completed-route limit missing")

    preservation = gap_matrix["scientific_state_preservation"]
    require(mapping["automatic_carry_forward"] is False, "Source Mapping enables carry-forward")
    require(mapping["counts"]["mapping_admitted_items"] == 0, "Source Mapping contains an admission")
    require(preservation["mapping_matrix_unchanged"] is True, "Mapping preservation flag missing")
    require(preservation["mapping_admitted_items"] == 0, "Mapping admission count changed")
    require(preservation["target_time_applicability"] == "UNKNOWN", "Global target-time state changed")
    require(preservation["automatic_carry_forward"] is False, "Global carry-forward changed")
    require(preservation["disputed_facts"]["count"] == mapping["counts"]["disputed_facts"] == 3, "DISPUTED fact count changed")
    require(preservation["disputed_facts"]["preserved_without_change"] is True, "DISPUTED facts not preserved")
    require(preservation["unlinked_facts"]["count"] == mapping["counts"]["unlinked_facts"] == 14, "Unlinked fact count changed")
    require(preservation["unlinked_facts"]["preserved_without_change"] is True, "Unlinked facts not preserved")
    require(queue["release_state"] == "HOLD_BEFORE_HUMAN_CODING", "Source recovery queue release state changed")

    check_no_results(consolidated)
    check_no_results(gap_matrix)
    check_no_results(receipt)

    expected_receipt = {
        "artifact_kind": "EXACT_EDITION_CONSOLIDATION_VALIDATION_RECEIPT",
        "assessor_type": "AI_PREPARATION",
        "status": "PASS_TECHNICAL_ONLY",
        "base_commit": BASE,
        "base_tree": BASE_TREE,
        "checks": [
            "one_commit_stacked_on_exact_pr18_head",
            "exact_base_blobs_and_immutable_source_ledgers",
            "pr18_validator_chain_and_output_pins",
            "strict_json_and_manifest_pins",
            "twenty_seven_versions_and_fifty_four_frozen_queries_exactly_once",
            "repository_only_no_network_no_new_retrieval",
            "three_way_nonadmissible_status_classification",
            "eight_verified_archive_payloads_and_zero_exact_edition_admissions",
            "per_version_residual_proof_and_technical_gaps",
            "mapping_target_time_disputed_and_unlinked_state_preservation",
            "no_factor_human_historical_uno_predictive_or_rating_outputs",
            "six_file_scope_clean_tree_and_git_diff_check",
        ],
        "counts": {
            "base_blobs_verified": base_blob_count,
            "manifest_input_pins": len(manifest["inputs"]),
            "manifest_output_pins": len(manifest["outputs"]),
            "source_tranches": 2,
            "document_versions": len(version_rows),
            "frozen_queries_consolidated": len(rows),
            "publisher_attempts": len(publisher_attempts),
            "archive_attempts": len(archive_attempts),
            "completed_nonadmissible": source_status_counts["COMPLETED_NONADMISSIBLE"],
            "finite_no_result_prior_state_retained": source_status_counts["FINITE_NO_RESULT_PRIOR_STATE_RETAINED"],
            "technical_failure_prior_state_retained": source_status_counts["TECHNICAL_FAILURE_PRIOR_STATE_RETAINED"],
            "pre_cutoff_archive_payloads_retrieved": archive_payloads,
            "archive_digests_verified": archive_digests,
            "exact_edition_contracts_satisfied": 0,
            "full_edition_not_proven": len(version_rows),
            "mapping_admission_changes": 0,
            "scientific_state_changes": 0,
            "disputed_facts_preserved": mapping["counts"]["disputed_facts"],
            "unlinked_facts_preserved": mapping["counts"]["unlinked_facts"],
        },
        "source_response_status_counts": dict(sorted(source_response_counts.items())),
        "consolidation_status_counts": dict(sorted(source_status_counts.items())),
        "prior_validator": {
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
        "release_state": "EXACT_EDITION_CONSOLIDATED_NO_NEW_ADMISSION",
    }
    require(receipt == expected_receipt, "Stored validation receipt is not reproducible")

    summary = local(PREFIX + "CONSOLIDATION_SUMMARY.md").read_text(encoding="utf-8")
    for required_text in (
        "Repository-only consolidation; no network access or new retrieval",
        "27/27",
        "54/54",
        "35",
        "15",
        "4",
        "8",
        "Exact-edition contracts satisfied: **0**",
        "27 × `NOT_PROVEN`",
        "Target-time applicability remains `UNKNOWN`",
        "3 DISPUTED facts",
        "14 unlinked facts",
        "HUMAN validation/coding/adjudication remains `NOT_PERFORMED`",
        "Historical area UNO remains `NOT_COMPUTED / BLOCKED`",
    ):
        require(required_text in summary, f"Summary boundary missing: {required_text}")

    changed = git("diff", "--name-only", BASE, "HEAD", "--").decode().splitlines()
    require(set(changed) == {PREFIX + name for name in FILES}, "Changes outside exact PR-19 file set")
    subprocess.check_call(["git", "diff", "--check", BASE, "HEAD", "--"], cwd=ROOT)
    for name in FILES:
        text = local(PREFIX + name).read_text(encoding="utf-8")
        require(text.endswith("\n"), f"Missing final newline: {name}")
        require(all(line == line.rstrip() for line in text.splitlines()), f"Trailing whitespace: {name}")

    return {
        "status": "PASS_TECHNICAL_ONLY",
        "counts": expected_receipt["counts"],
        "source_response_status_counts": expected_receipt["source_response_status_counts"],
        "consolidation_status_counts": expected_receipt["consolidation_status_counts"],
        "output_pins": "PASS",
        "prior_validator": "PASS_TECHNICAL_ONLY",
        "release_state": expected_receipt["release_state"],
    }


if __name__ == "__main__":
    try:
        print(json.dumps(main(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
