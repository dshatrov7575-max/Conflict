"""Read-only repository validation. No network, historical assessment or coding."""
import calendar
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import date, datetime, timezone

from jsonschema import Draft202012Validator, FormatChecker

BASE = "cb77ddbbc5cae3115f90a1512494d09be12c54d4"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PREFIX = HERE.relative_to(ROOT).as_posix() + "/"
SCI = "docs/scientific/"
PILOT = SCI + "pilots/ZHANAOZEN_2011_V4_PILOT_V1/"
HUMAN = SCI + "pilots/ZHANAOZEN_2011_HUMAN_CODING_PILOT_V1/"
REC = SCI + "admission/ZHANAOZEN_2011_HISTORICAL_AVAILABILITY_RECOVERY_V1/"
FILES = {"CASE_IDENTITY_AND_EPISODE_SCOPE.json", "FACTOR_MAPPING_PREPARATION.json",
         "SCOPE_AND_MAPPING_CHECKS.json", "FREEZE_MANIFEST.json", "README.md", "validate_scope.py"}
CUTOFF = "2011-12-15T23:59:59Z"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def git(*args):
    env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.check_output(["git", *args], cwd=ROOT, env=env)


def local(path):
    p = (ROOT / path).resolve()
    require(p.is_relative_to(ROOT) and p.is_file(), "Missing/outside repository: " + path)
    return p


def no_duplicate_keys(pairs):
    result = {}
    for k, v in pairs:
        require(k not in result, "Duplicate JSON key: " + k)
        result[k] = v
    return result


def read(path):
    return json.loads(local(path).read_text(encoding="utf-8-sig"), object_pairs_hook=no_duplicate_keys)


def csv_rows(path):
    with local(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def blob(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def pointer(data, ptr):
    require(ptr == "" or bool(re.fullmatch(r"(?:/(?:[^~/]|~[01])*)+", ptr)), "Invalid JSON Pointer")
    for token in ptr.split("/")[1:]:
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(data, list):
            require(bool(re.fullmatch(r"0|[1-9][0-9]*", key)), "Invalid array index")
            data = data[int(key)]
        else:
            data = data[key]
    return data


def resolve(ref):
    if "json_pointer" in ref:
        return pointer(read(ref["path"]), ref["json_pointer"])
    if "csv_record" in ref:
        require(ref["csv_record"] >= 2, "Header is not an evidence record")
        return csv_rows(ref["path"])[ref["csv_record"] - 2]
    return local(ref["path"]).read_text(encoding="utf-8-sig")


def refs(value):
    if isinstance(value, dict):
        if "path" in value and ("json_pointer" in value or "csv_record" in value):
            yield value
        for v in value.values():
            yield from refs(v)
    elif isinstance(value, list):
        for v in value:
            yield from refs(v)


def unique(rows, key):
    values = [row[key] for row in rows]
    require(len(values) == len(set(values)), "Duplicate IDs: " + key)


def publication_interval(recorded, precision):
    d = date.fromisoformat(recorded)
    if precision == "MONTH":
        return [d.replace(day=1).isoformat(), d.replace(day=calendar.monthrange(d.year, d.month)[1]).isoformat()]
    require(precision == "DAY", "Unsupported precision")
    return [recorded, recorded]


def temporal_gate(candidate):
    """Logical admission guard, not a proof generator. Fixtures are synthetic."""
    end = datetime.fromisoformat(CUTOFF.replace("Z", "+00:00"))
    witness = candidate.get("witness_at")
    if candidate.get("proof_kind") != "ARCHIVED_EXACT_FRAGMENT" or not witness:
        return "NOT_PROVEN"
    try:
        stamp = datetime.fromisoformat(witness.replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp > end:
            return "NOT_PROVEN"
        lower, upper = [date.fromisoformat(v) for v in candidate["publication_interval"]]
        if lower > upper or upper > end.date():
            return "NOT_PROVEN"
    except (ValueError, KeyError, TypeError):
        return "NOT_PROVEN"
    if not candidate.get("literal_match"):
        return "NOT_PROVEN"
    if candidate.get("claim_scope") != "FRAGMENT":
        return "NOT_PROVEN"
    if candidate.get("subject_scope") != candidate.get("represented_scope"):
        return "UNKNOWN"
    if candidate.get("observation_time") != candidate.get("target_time"):
        return "UNKNOWN"
    return "ELIGIBLE_FOR_REVIEW_ONLY"


def check_fixtures():
    base = dict(proof_kind="ARCHIVED_EXACT_FRAGMENT", witness_at="2011-11-27T12:00:00Z",
                publication_interval=["2011-11-27", "2011-11-27"], literal_match=True,
                claim_scope="FRAGMENT", subject_scope="SYNTHETIC_PERSON",
                represented_scope="SYNTHETIC_PERSON", observation_time="2011-11-27",
                target_time="2011-11-27")
    require(temporal_gate(base) == "ELIGIBLE_FOR_REVIEW_ONLY", "Positive temporal control")
    cases = {
        "publication_date_only": ({"proof_kind": "PUBLICATION_DATE"}, "NOT_PROVEN"),
        "current_url_only": ({"proof_kind": "CURRENT_URL"}, "NOT_PROVEN"),
        "pdf_metadata_only": ({"proof_kind": "PDF_METADATA"}, "NOT_PROVEN"),
        "late_snapshot": ({"witness_at": "2012-01-26T00:00:00Z"}, "NOT_PROVEN"),
        "after_cutoff_same_window": ({"witness_at": "2011-12-16T00:00:00Z"}, "NOT_PROVEN"),
        "fragment_to_edition": ({"claim_scope": "FULL_EDITION"}, "NOT_PROVEN"),
        "no_literal_match": ({"literal_match": False}, "NOT_PROVEN"),
        "month_crosses_cutoff": ({"publication_interval": publication_interval("2011-12-01", "MONTH")}, "NOT_PROVEN"),
        "reversed_interval": ({"publication_interval": ["2011-11-28", "2011-11-27"]}, "NOT_PROVEN"),
        "person_to_group": ({"represented_scope": "SYNTHETIC_GROUP"}, "UNKNOWN"),
        "company_to_employer_group": ({"subject_scope": "SYNTHETIC_COMPANY", "represented_scope": "SYNTHETIC_GROUP"}, "UNKNOWN"),
        "no_timezone": ({"witness_at": "2011-11-27T12:00:00"}, "NOT_PROVEN"),
    }
    for target in ("2011-11-28", "2011-12-15"):
        cases["no_carry_forward_to_" + target] = ({"target_time": target}, "UNKNOWN")
    for name, (patch, expected) in cases.items():
        require(temporal_gate(dict(base, **patch)) == expected, "Negative fixture: " + name)
    require(publication_interval("2011-10-01", "MONTH") == ["2011-10-01", "2011-10-31"], "MONTH precision")
    return sorted(cases)


def check_no_results(value):
    forbidden = {"assessment_value", "factor_value", "numeric_anchor", "anchor", "score",
                 "weight", "weights", "pos", "kvs", "rgu", "kvptn", "uno", "outcome",
                 "outcome_class", "calculated_result", "probability", "risk", "validation_record"}
    if isinstance(value, dict):
        for k, v in value.items():
            require(k.lower() not in forbidden, "Forbidden result field: " + k)
            check_no_results(v)
    elif isinstance(value, list):
        for v in value:
            check_no_results(v)
    elif isinstance(value, str):
        require(not re.search(r"\b(?:POS|KVS|RGU|KVPTN|UNO|Pol)\s*[:=]\s*[+-]?\d", value, re.I), "Encoded result")
        require(value not in {"NO_ESCALATION", "VIOLENT_ESCALATION", "REGIME_CHANGE", "ARMED_CONFLICT"}, "Historical classification")


def verify_pin(pin, base=False):
    raw = local(pin["path"]).read_bytes()
    require(sha(raw) == pin["sha256"] and blob(raw) == pin["git_blob_sha1"], "Pin mismatch: " + pin["path"])
    require(len(raw) == pin["bytes"], "Byte size mismatch")
    if base:
        require(git("rev-parse", BASE + ":" + pin["path"]).decode().strip() == pin["git_blob_sha1"], "Base binding mismatch")


def validate(emit=False):
    m = read(PREFIX + "FREEZE_MANIFEST.json")
    identity = read(PREFIX + "CASE_IDENTITY_AND_EPISODE_SCOPE.json")
    prep = read(PREFIX + "FACTOR_MAPPING_PREPARATION.json")
    require(m["base_commit"] == BASE, "Wrong base")
    require(git("rev-parse", BASE + "^{tree}").decode().strip() == m["base_tree"], "Wrong tree")
    require({p.name for p in HERE.iterdir() if p.is_file()} == FILES, "Six-file boundary")
    require(not any(p.is_dir() for p in HERE.iterdir()), "Unexpected subdirectory")
    unique(m["inputs"], "path")
    for pin in m["inputs"]:
        verify_pin(pin, base=True)
    input_paths = {p["path"] for p in m["inputs"]}
    for obj in (identity, prep):
        check_no_results(obj)
        require(obj["assessor_type"] == "AI_PREPARATION", "Assessor boundary")
        for ref in refs(obj):
            require(ref["path"] in input_paths or ref["path"].startswith(PREFIX), "Unpinned reference")
            resolve(ref)
    if not emit:
        unique(m["outputs"], "path")
        require({x["path"] for x in m["outputs"]} == {PREFIX + f for f in FILES if f != "FREEZE_MANIFEST.json"}, "Output pin coverage")
        for pin in m["outputs"]:
            verify_pin(pin)

    source_pins = 0
    for path in (SCI + "MVP7_METHODOLOGY_RUBRIC_FREEZE_MANIFEST.json", HUMAN + "FREEZE_MANIFEST.json", REC + "FREEZE_MANIFEST.json"):
        source_manifest = read(path)
        for pin in source_manifest["files"] + source_manifest.get("previous_artifacts", []):
            require(sha(local(pin["path"]).read_bytes()) == pin["sha256"], "Inherited manifest mismatch")
            source_pins += 1
    original = read(PILOT + "INPUT_MANIFEST.json")
    for path, expected in original["files"].items():
        require(sha(local(path).read_bytes()) == expected, "Pilot input pin")
    subset = read(HUMAN + "coordinator/EVIDENCE_SUBSET.json")
    require(subset["source_packet_sha256"] == original["sources"]["sources/ZHANAOZEN_V4_2011_SEALED_EVIDENCE_PACKET_CP3.json"], "CP3 rebinding")
    recovery_manifest = read(REC + "FREEZE_MANIFEST.json")
    require(sha(local(HUMAN + "FREEZE_MANIFEST.json").read_bytes()) == recovery_manifest["original_pilot_outer_manifest_sha256"], "Human freeze rebinding")

    audit = read(PILOT + "PACKET_AUDIT.json")
    plan = read(HUMAN + "coordinator/STUDY_PLAN.json")
    require(identity["case_id"] == audit["case_id"] == prep["case_id"], "Case identity mismatch")
    require(identity["time_slice_id"] == audit["time_slice_id"], "TimeSlice identity mismatch")
    scope = identity["episode_scope"]
    require(scope["information_cutoff"] == scope["target_time"] == CUTOFF == plan["information_cutoff"] == plan["target_time"], "Cutoff mismatch")
    require(scope["message_review_window"] == {"start_date": plan["source_window_start"], "end_date": CUTOFF[:10]}, "Window mismatch")
    require(scope["registered_message_dates"] == audit["fact_date_range"], "Date range mismatch")
    require(scope["natural_conflict_start"] is None and scope["natural_conflict_end"] is None, "Invented conflict boundary")
    require(scope["gap_state"] == "UNKNOWN" and scope["automatic_carry_forward"] is False, "Carry-forward enabled")
    require(scope["unobserved_target_interval"] == ["2011-11-28", "2011-12-15"], "Gap mismatch")
    require(prep["element_to_model_ptn"] == "UNKNOWN", "PTN silently promoted")
    require(identity["country"] == "Kazakhstan" and resolve(identity["country_basis"])["geography"] == "Kazakhstan", "Country unsupported")

    traces = csv_rows(PILOT + "EVIDENCE_TRACE_INDEX.csv")
    coverage = csv_rows(PILOT + "CODING_ITEM_COVERAGE.csv")
    witnesses = read(REC + "AVAILABILITY_WITNESSES.json")
    admission = read(REC + "ADMISSION_REASSESSMENT.json")
    versions = {v["document_version_id"]: v for v in witnesses["versions"]}
    admitted = {x["coding_item_id"]: x for x in admission["items"]}
    require(admission["overall_gate"] == "BLOCKED" and all(x["status"] == "BLOCKED" for x in admitted.values()), "Admission changed")
    unique(traces, "fact_fragment_link_id")
    unique(coverage, "coding_item_id")
    unique(prep["chains"], "fact_fragment_link_id")
    unique(prep["units"], "coding_item_id")
    require(len(prep["chains"]) == len(traces) == 58, "Dropped chains")
    require(len(prep["units"]) == len(coverage) == 20, "Changed frame")
    ids = {}
    for chain, row in zip(prep["chains"], traces):
        require(resolve(chain["trace_reference"]) == row, "Trace locator")
        for key in ("fact_id", "fragment_id", "document_version_id", "document_id", "source_id", "fact_fragment_link_id", "fact_status", "relation", "fragment_hash", "content_hash"):
            require(chain[key] == row[key], "Trace rebinding: " + key)
        require(sha(row["exact_text"].encode("utf-8")) == row["fragment_hash"], "Fragment hash")
        interval = publication_interval(row["publication_date"], row["publication_date_precision"])
        require(chain["publication_interval"] == interval, "Date precision changed")
        require(chain["registered_fact_interval"] == [row["fact_time_start"], row["fact_time_end"]], "Fact date changed")
        version = versions.get(row["document_version_id"])
        expected = "PROVEN_FRAGMENT_PRE_CUTOFF" if version and row["fragment_id"] in version["proven_fragment_ids"] else "NOT_PROVEN"
        require(chain["fragment_availability"] == expected, "Fragment proof promoted/dropped")
        require(chain["full_edition_availability"] == "NOT_PROVEN", "Edition proof promoted")
        require(chain["target_time_applicability"] == "UNKNOWN", "Observation carried forward")
        if version:
            require(resolve(chain["recovery_version_reference"]) == version, "Recovery reference")
            require(chain["recovery_version_status"] == version["status"], "Version status changed")
            require(version["late_capture_content_hash"] == row["content_hash"], "Version content hash changed")
        else:
            require(chain["recovery_version_reference"] is None and chain["recovery_version_status"] == "NOT_REVIEWED", "Invented recovery")
        for key in ("fact_id", "fragment_id", "document_version_id", "document_id", "source_id"):
            ids.setdefault(key, set()).add(row[key])
    for unit, row in zip(prep["units"], coverage):
        require(resolve(unit["coverage_reference"]) == row, "Coverage locator")
        for k in ("coding_item_id", "actor_id", "element_id", "time_slice_id", "reference_statement"):
            require(unit[k] == row[k], "Unit rebinding: " + k)
        require(unit["reference_sha256"] == sha(row["reference_statement"].encode()), "Reference hash")
        require(unit["fact_ids"] == row["fact_ids"].split(";"), "ItemFact links changed")
        expected_links = [t["fact_fragment_link_id"] for t in traces if t["fact_id"] in unit["fact_ids"]]
        require(unit["chain_ids"] == expected_links, "Chain dropped from unit")
        require(unit["mapping_status"] == "UNKNOWN" and unit["target_time_applicability"] == "UNKNOWN", "Premature mapping")
        if row["coding_item_id"] in admitted:
            old = admitted[row["coding_item_id"]]
            require(resolve(unit["admission_reference"]) == old and unit["admission_status"] == old["status"], "Admission rebinding")
        else:
            require(unit["admission_reference"] is None and unit["admission_status"] == "NOT_REVIEWED", "Unaudited admission")
    disputed = {t["fact_id"] for t in traces if t["fact_status"] == "DISPUTED"}
    require(set(prep["disputed_fact_ids"]) == disputed and len(disputed) == 3, "DISPUTED not preserved")
    require(set(prep["unlinked_fact_ids"]) == set(audit["unlinked_fact_ids"]), "Unlinked facts dropped")
    require(set(prep["unlinked_fact_ids"]) <= ids["fact_id"], "Unresolved unlinked fact")
    require(set(prep["possible_counterevidence_fact_ids"]) <= ids["fact_id"], "Unresolved counterevidence")
    require({x["factor_id"] for x in prep["factor_routes"]} == {"POS", "KVS", "RGU", "KVPTN"}, "Factor routes")
    for route in prep["factor_routes"]:
        if route["factor_id"] in ("RGU", "KVPTN"):
            require(route["role"] == "IDENTITY_CONTEXT_ONLY" and route["evidence_derivation_permitted"] is False, "Evidence-derived design input")
    # Exact original subset joins, independently of prepared routes.
    tables = {k: {row[key]: row for row in subset[k]} for k, key in (
        ("facts", "fact_id"), ("text_fragments", "fragment_id"),
        ("document_versions", "document_version_id"), ("documents", "document_id"),
        ("sources", "source_id"), ("coding_items", "coding_item_id"))}
    for k, key in (("facts", "fact_id"), ("text_fragments", "fragment_id"), ("document_versions", "document_version_id"), ("documents", "document_id"), ("sources", "source_id"), ("coding_items", "coding_item_id")):
        unique(subset[k], key)
    by_link = {t["fact_fragment_link_id"]: t for t in traces}
    for link in subset["fact_fragment_links"]:
        row = by_link[link["link_id"]]
        fact = tables["facts"][link["fact_id"]]
        fragment = tables["text_fragments"][link["fragment_id"]]
        version = tables["document_versions"][fragment["document_version_id"]]
        document = tables["documents"][version["document_id"]]
        source = tables["sources"][document["source_id"]]
        require((row["fact_id"], row["fragment_id"], row["document_version_id"], row["document_id"], row["source_id"]) ==
                (fact["fact_id"], fragment["fragment_id"], version["document_version_id"], document["document_id"], source["source_id"]), "Subset chain mismatch")
        require(fragment["fragment_hash"] == row["fragment_hash"] and fact["statement"] == row["fact_statement"], "Subset content mismatch")
    for witness in witnesses["witnesses"]:
        stamp = datetime.strptime(witness["archive_capture_timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        require(stamp <= datetime.fromisoformat(CUTOFF.replace("Z", "+00:00")), "Late inherited witness")
        require(witness["archive_digest_sha1_base32"] == witness["retrieved_payload_sha1_base32"], "Recorded witness digest mismatch")
        for f in witness["matched_fragments"]:
            require(sha(f["exact_frozen_fragment"].encode()) == f["fragment_sha256"] and f["literal_in_extracted_text"], "Witness fragment mismatch")

    schemas = [("CASE_MAPPING_SCHEMA.json", "ZHANAOZEN_2011_EXAMPLE.json"),
               ("EMPIRICAL_VALIDATION_SCHEMA.json", "ZHANAOZEN_2011_VALIDATION_TEMPLATE.json"),
               ("HISTORICAL_ASSESSMENT_SCHEMA.json", "ZHANAOZEN_2011_ASSESSMENT_TEMPLATE.json")]
    for schema_name, template in schemas:
        schema = read(SCI + schema_name)
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(read(SCI + template))
    historical = read(SCI + "HISTORICAL_ASSESSMENT_SCHEMA.json")
    fake = copy.deepcopy(read(SCI + "ZHANAOZEN_2011_ASSESSMENT_TEMPLATE.json"))
    fake["document_kind"] = "HISTORICAL_ASSESSMENT"
    for a in fake["assessments"]:
        a["assessment_id"] = "SYNTHETIC_" + a["factor_id"]
        a["assessor_type"] = "AI_PREPARATION"
    require(not Draft202012Validator(historical).is_valid(fake), "Historical schema accepted AI preparation")
    for synthetic in ({"factor_value": 1}, {"anchor": "1"}, {"score": 1}, {"weights": []}, {"outcome_class": "SYNTHETIC"}):
        try:
            check_no_results(synthetic)
        except ValueError:
            pass
        else:
            raise ValueError("Forbidden-result fixture accepted")
    negatives = check_fixtures()

    base_count = 0
    for entry in git("ls-tree", "-rz", BASE).split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, oid = metadata.split()
        require(kind == b"blob", "Unexpected base object")
        require(blob(local(name.decode()).read_bytes()) == oid.decode(), "Base bytes changed: " + name.decode())
        base_count += 1
    changed = git("diff", "--name-only", BASE).decode().splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").decode().splitlines()
    require(all(p.startswith(PREFIX) and Path(p).name in FILES for p in changed + untracked), "Changes outside allowed directory")
    git("diff", "--check", BASE)
    for name in FILES:
        text = local(PREFIX + name).read_text(encoding="utf-8")
        require(text.endswith("\n") and all(line == line.rstrip() for line in text.splitlines()), "Output whitespace")
    report = {
        "artifact_kind": "TECHNICAL_SCOPE_CHECKS", "assessor_type": "AI_PREPARATION",
        "status": "PASS_TECHNICAL_ONLY", "base_commit": BASE,
        "checks": ["strict_json_parse", "input_git_blob_and_sha256", "existing_manifest_pins",
                   "all_local_references_and_json_pointers", "typed_ids_and_original_links",
                   "reference_text_hashes", "fragment_hashes", "admission_status_preservation",
                   "fragment_proof_not_edition_proof", "disputed_and_unlinked_facts_retained",
                   "no_results_in_audit_data", "three_existing_schemas_and_templates",
                   "historical_schema_rejects_ai_preparation", "negative_result_field_fixtures",
                   "temporal_and_representation_fixtures", "all_existing_files_byte_identical",
                   "six_new_files_only", "git_diff_check"],
        "counts": {"base_blobs_verified": base_count, "input_pins": len(m["inputs"]),
                   "inherited_manifest_file_pins": source_pins, "coding_items": len(coverage),
                   "fact_fragment_links": len(traces), "facts": len(ids["fact_id"]),
                   "fragments": len(ids["fragment_id"]), "document_versions": len(ids["document_version_id"]),
                   "disputed_facts": len(disputed), "recovery_blocked_items": len(admitted),
                   "recorded_archive_witnesses": len(witnesses["witnesses"]),
                   "unique_proven_fragments": len({x["fragment_id"] for x in prep["chains"] if x["fragment_availability"] == "PROVEN_FRAGMENT_PRE_CUTOFF"})},
        "negative_temporal_fixtures": negatives,
        "limits": ["External CP3 and full archive payload bytes are not in Git and were not retrieved.",
                   "Inherited witness records verified locally; no new historical authentication.",
                   "Audit artifacts are outside existing assessment/pilot schemas; those schemas remain unchanged.",
                   "Technical PASS does not change scientific admission or establish empirical validity."],
    }
    if not emit:
        receipt = read(PREFIX + "SCOPE_AND_MAPPING_CHECKS.json")
        require(receipt == report, "Stored checks differ from reproduced checks")
        check_no_results(receipt)
        print(json.dumps({"status": report["status"], "counts": report["counts"], "output_pins": "PASS"}, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        require(sys.argv[1:] in ([], ["--emit-checks"]), "Use no arguments for acceptance")
        validate(emit=sys.argv[1:] == ["--emit-checks"])
    except Exception as exc:
        print("FAIL: " + str(exc), file=sys.stderr)
        sys.exit(1)
