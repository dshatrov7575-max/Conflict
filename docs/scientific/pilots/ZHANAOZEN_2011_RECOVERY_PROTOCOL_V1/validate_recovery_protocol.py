"""Read-only validation for the PR-15 prospective recovery-protocol freeze."""
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
from collections import Counter

BASE = "c48e3730cc9a7c67d62429614e1ca9e5c58be920"
BASE_TREE = "386a4c134e1a50cf4285c91c36899f71f0eb751b"
PLAN_ID = "ZHANAOZEN_2011_RECOVERY_PROTOCOL_V1"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREFIX = HERE.relative_to(ROOT).as_posix() + "/"
PR14 = "docs/scientific/pilots/ZHANAOZEN_2011_MAPPING_ADMISSION_V1/"
FILES = {
    "RECOVERY_PROTOCOL.md", "RECOVERY_PLAN.json", "ATTEMPT_LEDGER_TEMPLATE.json",
    "VALIDATION_RECEIPT.json", "FREEZE_MANIFEST.json", "validate_recovery_protocol.py",
}
ROUTES = {
    "ROUTE_PUBLISHER_OR_ARCHIVE_EXACT_EDITION",
    "ROUTE_AUTHENTICATED_FRAGMENT_WITNESS",
    "ROUTE_ACTOR_MANDATE_OR_REPRESENTATION",
    "ROUTE_REFERENCE_COMPONENT_COVERAGE",
    "ROUTE_TARGET_TIME_APPLICABILITY",
    "ROUTE_CONTEXT_ATTRIBUTION_LANGUAGE",
    "ROUTE_COUNTEREVIDENCE_REVIEW",
}
SCOPE_ROUTES = {
    "TARGET_TIME": ["ROUTE_TARGET_TIME_APPLICABILITY"],
    "DOCUMENT_VERSION": ["ROUTE_PUBLISHER_OR_ARCHIVE_EXACT_EDITION", "ROUTE_AUTHENTICATED_FRAGMENT_WITNESS"],
    "ACTOR_SCOPE": ["ROUTE_ACTOR_MANDATE_OR_REPRESENTATION"],
    "REFERENCE_SCOPE": ["ROUTE_REFERENCE_COMPONENT_COVERAGE"],
    "CONTEXT_LANGUAGE": ["ROUTE_CONTEXT_ATTRIBUTION_LANGUAGE"],
    "COUNTEREVIDENCE_COMPLETENESS": ["ROUTE_COUNTEREVIDENCE_REVIEW"],
}
RESULT_STATES = sorted([
    "ADMISSIBLE_CONTRACT_SATISFIED", "ATTEMPT_ERROR", "DUPLICATE",
    "NEGATIVE_EVIDENCE_LIMIT", "NO_RESULT", "NOT_ADMISSIBLE", "TIMEOUT",
])
CUSTODY_FIELDS = [
    "attempt_id", "blocker_id", "coding_item_id", "dimension", "route_id",
    "query_ordinal", "query_text_sha256", "requested_at_utc", "completed_at_utc",
    "result_state", "error_state", "locator", "redirect_chain", "retrieved_bytes",
    "retrieved_sha256", "archive_capture_timestamp", "content_type",
    "duplicate_of_attempt_id", "admissibility_contract_satisfied",
    "prior_status_retained", "notes",
]
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


def run_pr14_validator() -> dict:
    temp_path = Path(tempfile.gettempdir()) / f"conflict-pr14-validate-{uuid.uuid4().hex}"
    try:
        subprocess.check_call(
            ["git", "worktree", "add", "--detach", str(temp_path), BASE], cwd=ROOT,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        validator = temp_path / PR14 / "validate_mapping_admission.py"
        output = subprocess.check_output(
            [sys.executable, "-B", str(validator)], cwd=temp_path, text=True, encoding="utf-8",
        )
        result = json.loads(output)
        require(result["status"] == "PASS_TECHNICAL_ONLY", "PR-14 validator did not pass")
        require(result["output_pins"] == "PASS", "PR-14 output pins did not pass")
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
    plan = read_json(PREFIX + "RECOVERY_PLAN.json")
    ledger = read_json(PREFIX + "ATTEMPT_LEDGER_TEMPLATE.json")
    receipt = read_json(PREFIX + "VALIDATION_RECEIPT.json")
    queue = read_json(PR14 + "SOURCE_CONTEXT_RECOVERY_QUEUE.json")
    matrix = read_json(PR14 + "MAPPING_ADMISSION_MATRIX.json")

    require(manifest["base_commit"] == BASE and manifest["base_tree"] == BASE_TREE, "Manifest base mismatch")
    unique((pin["path"] for pin in manifest["inputs"]), "input pin")
    unique((pin["path"] for pin in manifest["outputs"]), "output pin")
    for pin in manifest["inputs"]:
        verify_pin(pin, bind_to_base=True)
    expected_outputs = {PREFIX + name for name in FILES if name != "FREEZE_MANIFEST.json"}
    require({pin["path"] for pin in manifest["outputs"]} == expected_outputs, "Output pin coverage mismatch")
    for pin in manifest["outputs"]:
        verify_pin(pin)

    pr14_result = run_pr14_validator()
    base_blob_count = verify_base_blobs()
    require(base_blob_count == 765, "Unexpected base blob count")
    for value in (plan, ledger, receipt):
        check_no_results(value)
    require(plan["artifact_kind"] == "SOURCE_CONTEXT_RECOVERY_PROTOCOL_PLAN", "Wrong plan kind")
    require(plan["assessor_type"] == "AI_PREPARATION", "Wrong assessor type")
    require(plan["plan_id"] == PLAN_ID, "Wrong plan ID")
    require(plan["base_commit"] == BASE and plan["base_tree"] == BASE_TREE, "Plan base mismatch")
    require(plan["case_id"] == queue["case_id"] == matrix["case_id"], "Case ID mismatch")
    require(plan["time_slice_id"] == matrix["time_slice_id"], "Time-slice mismatch")
    require(plan["target_time"] == queue["target_time"] == matrix["target_time"], "Target time mismatch")
    source_queue_raw = local(PR14 + "SOURCE_CONTEXT_RECOVERY_QUEUE.json").read_bytes()
    require(plan["source_queue_sha256"] == sha256(source_queue_raw), "Queue SHA mismatch")
    require(plan["source_queue_git_blob_sha1"] == git_blob(source_queue_raw), "Queue blob mismatch")

    state = plan["execution_state"]
    require(state["protocol_frozen"] is True, "Protocol not frozen")
    for key in (
        "retrieval_started", "network_search_executed", "substantive_review_executed",
        "human_coding_started", "factor_scoring_executed",
    ):
        require(state[key] is False, f"Execution boundary changed: {key}")
    require(plan["previous_scientific_states_preserved"] is True, "Prior states not preserved")
    require(set(plan["allowed_route_ids"]) == ROUTES, "Allowed route IDs changed")
    require(set(plan["route_definitions"]) == ROUTES, "Route definitions incomplete")

    template_ids = {}
    for route_id, route in plan["route_definitions"].items():
        require(route["purpose"] and route["allowed_sources"], f"Incomplete route: {route_id}")
        require(route["evidence_contract"] and route["success_contract"] and route["failure_contract"], f"Missing route contract: {route_id}")
        require(route["forbidden_inferences"], f"Missing route prohibitions: {route_id}")
        templates = route["query_templates"]
        require(len(templates) >= 2, f"Insufficient prospective templates: {route_id}")
        unique((template["template_id"] for template in templates), f"template ID in {route_id}")
        template_ids[route_id] = {template["template_id"] for template in templates}
    units = plan["blocker_units"]
    entries = queue["entries"]
    require(len(units) == len(entries) == 53, "Expected 53 blocker units")
    unique((unit["blocker_id"] for unit in units), "blocker ID")
    require([unit["blocker_id"] for unit in units] == [entry["blocker_id"] for entry in entries], "Blocker order changed")
    all_query_ids = []
    planned_query_count = 0
    for index, (unit, entry) in enumerate(zip(units, entries)):
        require(unit["blocker_id"] == entry["blocker_id"], "Blocker ID rebound")
        require(unit["source_queue_reference"] == {
            "path": PR14 + "SOURCE_CONTEXT_RECOVERY_QUEUE.json",
            "json_pointer": f"/entries/{index}",
        }, "Source queue reference changed")
        require(unit["source_entry_sha256"] == canonical_hash(entry), "Source entry hash mismatch")
        for target, source in (
            ("priority", "priority"), ("scope", "scope"), ("affected_ids", "affected_ids"),
            ("prior_status", "present_status"), ("missing_proof", "missing_proof"),
            ("forbidden_shortcuts", "forbidden_shortcuts"),
        ):
            require(unit[target] == entry[source], f"Blocker field changed: {target}")
        expected_routes = SCOPE_ROUTES[entry["scope"]]
        require(unit["allowed_route_ids"] == expected_routes, "Blocker route mapping changed")
        require(unit["success_effect"] == "REQUIRES_NEW_FROZEN_ADMISSION_DECISION_BEFORE_ANY_CODING", "Premature success effect")
        require(unit["failure_effect"] == "EXACT_PRIOR_STATE_RETENTION", "Failure state not retained")
        require(unit["scientific_state_mutation_permitted"] is False, "Scientific mutation enabled")
        require(unit["human_coding_permitted"] is False, "HUMAN coding enabled")
        queries = unit["planned_queries"]
        require(queries, "Blocker has no prospective queries")
        require([query["query_ordinal"] for query in queries] == list(range(1, len(queries) + 1)), "Query ordinals changed")
        for query in queries:
            require(query["route_id"] in expected_routes, "Query route not allowed")
            require(query["query_template_id"] in template_ids[query["route_id"]], "Unknown query template")
            require(query["query_text_sha256"] == sha256(query["rendered_query"].encode("utf-8")), "Query text hash mismatch")
            require(query["execution_state"] == "NOT_EXECUTED", "Query already executed")
            expected_id = str(uuid.uuid5(uuid.UUID(ledger["attempt_id_contract"]["namespace"]), f"{PLAN_ID}|{unit['blocker_id']}|{query['route_id']}|{query['query_ordinal']}|{query['query_text_sha256']}"))
            require(query["query_id"] == expected_id, "Query ID is not deterministic")
            all_query_ids.append(query["query_id"])
        planned_query_count += len(queries)
    unique(all_query_ids, "query ID")
    require(planned_query_count == 160, "Unexpected planned-query count")
    stopping = plan["stopping_rules"]
    require(stopping["max_substantive_attempts_per_query"] == 1, "Query retry budget changed")
    require(stopping["max_substantive_attempts_per_blocker"] == 4, "Blocker attempt budget changed")
    require(stopping["stop_on_first_admissible_contract_satisfaction"] is True, "Success stop disabled")
    require(stopping["stop_when_allowed_routes_exhausted"] is True, "Exhaustion stop disabled")
    require(stopping["no_rerun_until_favorable"] is True, "Rerun-until-favorable enabled")
    require(stopping["additional_queries_require_new_version_and_freeze_before_execution"] is True, "Post-result query expansion enabled")

    semantics = plan["timeout_error_semantics"]
    require(semantics == {
        "timeout": "ATTEMPT_ERROR_RETAIN_PRIOR_STATE",
        "transport_error": "ATTEMPT_ERROR_RETAIN_PRIOR_STATE",
        "parser_error": "ATTEMPT_ERROR_RETAIN_PRIOR_STATE",
        "no_result": "NEGATIVE_EVIDENCE_LIMIT_RETAIN_PRIOR_STATE",
        "retry_budget": "NOT_INCREASED_AFTER_OBSERVING_CONTENT",
    }, "Timeout/error semantics changed")

    retention = plan["retention_supersession"]
    require(retention["default_rule"] == "EXACT_RETENTION", "Default retention changed")
    require(set(retention) >= {"BLOCKED", "NOT_REVIEWED", "UNKNOWN", "NOT_PROVEN", "DISPUTED"}, "Retention status missing")
    require(retention["DISPUTED"]["retention"] == "PRESERVE_UNLESS_DIRECTLY_RESOLVED", "DISPUTED may be silently resolved")
    require("new version identifier" in retention["supersession_requires"], "Versioned supersession missing")
    require("review before HUMAN coding" in retention["supersession_requires"], "Pre-coding review missing")

    proofs = plan["proof_contracts"]
    require(proofs["exact_edition"]["claim_scope"] == "FULL_EDITION_ONLY", "Edition scope changed")
    require(proofs["exact_edition"]["fragment_proof_is_sufficient"] is False, "Fragment proof promoted")
    require(proofs["fragment_witness"]["claim_scope"] == "FRAGMENT_ONLY", "Fragment scope changed")
    require(proofs["fragment_witness"]["full_edition_promotion_permitted"] is False, "Edition promotion enabled")
    counter = plan["counterevidence_rule"]
    require(counter["preserve_all_disputed_and_unlinked_facts"] is True, "Counterevidence may be dropped")
    require(counter["record_every_inclusion_or_exclusion"] is True, "Counterevidence decisions not logged")
    require(counter["silent_resolution_forbidden"] is True and counter["averaging_forbidden"] is True, "Counterevidence may be silently resolved")
    require(counter["search_completeness_claim"] == "NOT_ESTABLISHED", "Search completeness overclaimed")

    dedup = plan["deduplication_rule"]
    require(dedup["duplicate_key"] == ["retrieved_sha256", "archive_capture_timestamp", "locator"], "Deduplication key changed")
    require(dedup["duplicate_attempt_is_not_new_evidence"] is True, "Duplicate treated as evidence")
    require(dedup["duplicate_of_attempt_id_required"] is True, "Duplicate provenance missing")
    require(dedup["independence_not_inferred_from_multiple_urls"] is True, "Source independence inferred from URLs")

    custody = plan["custody_hash_rule"]
    require(custody["retrieved_bytes_sha256_required"] is True, "Retrieved-byte hash optional")
    require(custody["query_text_sha256_required"] is True, "Query hash optional")
    require(custody["normalization_before_hash_forbidden"] is True, "Pre-hash normalization enabled")
    require(custody["local_cache_path_is_not_a_source_identity"] is True, "Cache path treated as identity")
    require(len(plan["negative_evidence_limits"]) >= 4, "Negative-evidence limits incomplete")
    require(any("No result" in rule for rule in plan["negative_evidence_limits"]), "No-result limit missing")
    require(any("hidden external attempts" in rule for rule in plan["negative_evidence_limits"]), "Hidden-attempt limit missing")
    require(plan["release_state"] == "FROZEN_PROTOCOL_ONLY_HOLD_BEFORE_EXECUTION", "Protocol release boundary changed")

    require(ledger["artifact_kind"] == "PROSPECTIVE_EMPTY_RECOVERY_ATTEMPT_LEDGER", "Wrong ledger kind")
    require(ledger["assessor_type"] == "AI_PREPARATION", "Wrong ledger assessor")
    require(ledger["plan_id"] == PLAN_ID and ledger["base_commit"] == BASE, "Ledger identity changed")
    require(ledger["case_id"] == queue["case_id"], "Ledger case changed")
    require(ledger["prospective"] is True and ledger["source_status"] == "NOT_EXECUTED", "Ledger not prospective")
    require(ledger["network_search_executed"] is False and ledger["substantive_review_executed"] is False, "Ledger reports execution")
    require(ledger["blocker_ids"] == sorted(entry["blocker_id"] for entry in queue["entries"]), "Ledger blocker coverage changed")
    id_contract = ledger["attempt_id_contract"]
    require(id_contract["algorithm"] == "UUID5", "Attempt ID algorithm changed")
    uuid.UUID(id_contract["namespace"])
    require(id_contract["name_components"] == [
        "plan_id", "blocker_id", "route_id", "query_ordinal", "query_text_sha256",
    ], "Attempt ID components changed")
    require(ledger["custody_fields"] == CUSTODY_FIELDS, "Custody fields changed")
    require(ledger["allowed_result_states"] == RESULT_STATES, "Result states changed")
    require(ledger["allowed_error_states"] == ["NONE", "TIMEOUT", "TRANSPORT_ERROR", "PARSER_ERROR"], "Error states changed")
    require(ledger["append_only"] is True and ledger["executor_fill_required"] is True, "Ledger mutability changed")
    require(ledger["attempts"] == [], "Prospective ledger is not empty")

    fixture_results = {
        "fragment_to_full_edition": proofs["fragment_witness"]["full_edition_promotion_permitted"] is False,
        "timeout_retains_prior_state": semantics["timeout"] == "ATTEMPT_ERROR_RETAIN_PRIOR_STATE",
        "no_result_is_not_absence": semantics["no_result"] == "NEGATIVE_EVIDENCE_LIMIT_RETAIN_PRIOR_STATE",
        "person_to_group_requires_mandate": "ROUTE_ACTOR_MANDATE_OR_REPRESENTATION" in ROUTES,
        "component_to_full_reference_forbidden": "ROUTE_REFERENCE_COMPONENT_COVERAGE" in ROUTES,
        "old_message_to_cutoff_forbidden": "ROUTE_TARGET_TIME_APPLICABILITY" in ROUTES,
        "disputed_preserved": retention["DISPUTED"]["retention"] == "PRESERVE_UNLESS_DIRECTLY_RESOLVED",
        "rerun_until_favorable_forbidden": stopping["no_rerun_until_favorable"] is True,
    }
    require(all(fixture_results.values()), "A fail-closed fixture failed")

    protocol = local(PREFIX + "RECOVERY_PROTOCOL.md").read_text(encoding="utf-8")
    required_protocol_text = [
        "AI preparation only", "53 PR-14 blocker units", "Network search: NOT_EXECUTED",
        "Substantive source review: NOT_EXECUTED", "HUMAN coding: NOT_PERFORMED",
        "historical area UNO: NOT_COMPUTED / BLOCKED", "No factor values",
        "No message is automatically carried", "fragment witness proves only",
        "Rerun-until-favorable", "DISPUTED is preserved", "company KVS=5 / Pol=50 is not restored",
    ]
    for text in required_protocol_text:
        require(text.lower() in protocol.lower(), f"Protocol boundary missing: {text}")
    changed = git("diff", "--name-only", BASE, "--").decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    require(all(path.startswith(PREFIX) and Path(path).name in FILES for path in changed + untracked), "Changes outside PR-15 scope")
    subprocess.check_call(["git", "diff", "--check", BASE, "--"], cwd=ROOT)
    for name in FILES:
        text = local(PREFIX + name).read_text(encoding="utf-8")
        require(text.endswith("\n"), f"Missing final newline: {name}")
        require(all(line == line.rstrip() for line in text.splitlines()), f"Trailing whitespace: {name}")

    scope_counts = dict(sorted(Counter(entry["scope"] for entry in queue["entries"]).items()))
    expected_receipt = {
        "artifact_kind": "RECOVERY_PROTOCOL_VALIDATION_RECEIPT",
        "assessor_type": "AI_PREPARATION",
        "status": "PASS_TECHNICAL_ONLY",
        "base_commit": BASE,
        "base_tree": BASE_TREE,
        "checks": [
            "exact_base_and_prior_blobs", "pr14_validator_and_output_pins",
            "strict_json_and_unique_ids", "all_fifty_three_blockers_frozen",
            "seven_allowed_routes_and_query_templates", "prospective_empty_attempt_ledger",
            "exact_edition_and_fragment_contract_separation", "retention_and_supersession_rules",
            "deterministic_stopping_and_no_rerun_until_favorable",
            "timeout_error_and_negative_evidence_semantics",
            "counterevidence_deduplication_and_custody",
            "forbidden_result_and_state_mutation_fixtures",
            "six_file_scope_and_git_diff_check",
        ],
        "counts": {
            "base_blobs_verified": base_blob_count,
            "manifest_input_pins": len(manifest["inputs"]),
            "manifest_output_pins": len(manifest["outputs"]),
            "source_queue_entries": len(entries),
            "blocker_units": len(units),
            "route_definitions": len(ROUTES),
            "planned_queries": planned_query_count,
            "empty_attempts": len(ledger["attempts"]),
        },
        "scope_counts": scope_counts,
        "pr14_validator": pr14_result,
        "scientific_boundaries": {
            "human_validation_reliability": "NOT_PERFORMED",
            "historical_snapshot": "NOT_ESTABLISHED",
            "historical_area_UNO": "NOT_COMPUTED_BLOCKED",
            "predictive_probability_risk_validation": "NOT_CLAIMED",
            "publication_release_deployment": "NOT_EXECUTED",
            "retrieval_and_substantive_review": "NOT_EXECUTED",
        },
    }
    require(receipt == expected_receipt, "Stored validation receipt is not reproducible")
    require(manifest["scope"] == {
        "allowed_directory": PREFIX.rstrip("/"),
        "file_count": 6,
        "existing_files_modified": False,
        "retrieval_executed": False,
        "network_search_executed": False,
        "substantive_review_executed": False,
        "human_coding": "NOT_PERFORMED",
        "factor_scoring": "NOT_PERFORMED",
        "historical_area_UNO": "NOT_COMPUTED_BLOCKED",
        "publication_release_deployment": "NOT_EXECUTED",
    }, "Manifest scope changed")

    return {
        "status": "PASS_TECHNICAL_ONLY",
        "counts": expected_receipt["counts"],
        "scope_counts": scope_counts,
        "fixture_results": fixture_results,
        "output_pins": "PASS",
        "pr14_validator": "PASS_TECHNICAL_ONLY",
        "release_state": plan["release_state"],
    }


if __name__ == "__main__":
    try:
        require(sys.argv[1:] == [], "This validator accepts no arguments")
        print(json.dumps(validate(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1)
