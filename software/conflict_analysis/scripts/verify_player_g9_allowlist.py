from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROJECT = ROOT / "software" / "conflict_analysis"
F1_HEAD = "d2f5a881e10dbb688371e8c5add6bf9375404738"
FD08_HEAD = "68b14882a06b2e90710ebd06e584dc5300fdfe7e"
G7_HEAD = "319450a64cb381df2e392027c64de157e2ed830c"
G8_HEAD = "df537ee138088a1fc691cc89a257259817db4644"
G8_TREE = "67739a84d7bcc9406cbb830d9a58656b05eee06a"
MODIFIED = {
    ".github/workflows/conflict-analysis.yml": "b2b7fdbd3ff4411dc7c294b507b7471a378b67e0",
    "software/conflict_analysis/domain/api/evidence.py": "ca9ff9ada30996a52f5981254e1d368b4035c783",
    "software/conflict_analysis/domain/urls.py": "b7841b82bcc9b52d0810b3a4cb853d94af8153c1",
    "software/conflict_analysis/production_player/claim_boundaries.py": "5cd1a2ada3adaca0d1d25ae98baf32b19f4da673",
    "software/conflict_analysis/production_player/templates/production_player/workspace.html": "b8e99aecb823ed240b2019e0bee96a56c6a83424",
}
ADDED = {f"software/conflict_analysis/{path}" for path in (
    "domain/services/evidence_access.py",
    "domain/tests/test_evidence_access.py",
    "docs/adr/0016-production-player-g9-evidence-ui.md",
    "production_player/contracts/player_g9_evidence_claim_boundaries_v1.ru.json",
    "production_player/contracts/player_g9_evidence_claim_boundaries_v1.ru.json.sha256",
    "production_player/static/production_player/evidence.css",
    "production_player/static/production_player/evidence.js",
    "production_player/tests/test_player_g9_evidence.py",
    "production_player/browser_tests/player_g9_evidence.mjs",
    "scripts/verify_player_g9_allowlist.py",
)}
FOUNDATION = [
    "test_parameter_value_fact_list_filters_before_projection_and_neutralizes_zero_vs_hidden",
    "test_assessment_fact_list_reuses_exact_visibility_and_lane_scope",
    "test_entry_list_project_workspace_entry_and_spoofing_fail_uniformly_before_fact_queries",
    "test_entry_list_owner_private_unspecified_and_revocation_semantics_match_fact_drilldown",
    "test_entry_list_get_boundary_is_zero_write_no_cookie_no_rehash_no_store_and_method_strict",
    "test_entry_list_dto_is_deterministic_minimal_and_keeps_fact_type_category_and_classification_separate",
    "test_entry_to_fact_to_evidence_preserves_multiple_contradictory_roles_and_memory_zero_links",
    "test_fact_drilldown_keeps_exact_fragment_version_and_stored_alignment_only_without_latest_or_guess",
]
PRODUCT = [
    "test_g9_product_uses_only_foundation_reads_and_has_no_orm_or_evidence_store",
    "test_g9_focus_and_command_surface_are_exact_no_in_row_actions_or_implicit_mutation",
    "test_g9_fact_and_evidence_rendering_preserves_roles_category_memory_and_no_truth_claims",
    "test_g9_exact_fragment_original_disabled_and_multi_sentence_alignment_rendering_are_honest",
    "test_g9_async_errors_history_and_permission_changes_clear_stale_confidential_state",
    "test_g9_storage_active_content_external_urls_and_accessibility_are_bounded",
]
CHROMIUM = [
    "test_chromium_g9_parameter_and_assessment_to_fact_evidence_exact_navigation",
    "test_chromium_g9_private_hidden_revoked_and_network_race_non_fingerprinting",
    "test_chromium_g9_keyboard_history_storage_xss_bidi_and_external_url_policy",
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def class_tests(path: Path, name: str) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == name)
    return [item.name for item in node.body if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test_")]


def main() -> None:
    assert git("rev-parse", f"{G8_HEAD}^{{tree}}") == G8_TREE
    for ancestor in (F1_HEAD, FD08_HEAD, G7_HEAD):
        subprocess.check_call(["git", "merge-base", "--is-ancestor", ancestor, G8_HEAD], cwd=ROOT)
    assert git("rev-list", "--merges", f"{F1_HEAD}..{G8_HEAD}") == ""
    for path, blob in MODIFIED.items():
        assert git("rev-parse", f"{G8_HEAD}:{path}") == blob, path
    for path in ADDED:
        process = subprocess.run(["git", "cat-file", "-e", f"{G8_HEAD}:{path}"], cwd=ROOT)
        assert process.returncode != 0, path
    head = git("rev-parse", "HEAD")
    assert head != G8_HEAD, "delivery must be committed before verification"
    assert git("rev-list", "--count", f"{G8_HEAD}..{head}") == "1"
    assert git("rev-list", "--parents", "-n", "1", head) == f"{head} {G8_HEAD}"
    assert git("rev-list", "--merges", f"{G8_HEAD}..{head}") == ""
    expected = {f"M\t{path}" for path in MODIFIED} | {f"A\t{path}" for path in ADDED}
    actual = set(git("diff", "--no-renames", "--name-status", G8_HEAD, head).splitlines())
    assert actual == expected, (sorted(actual), sorted(expected))
    assert git("status", "--porcelain") == ""
    migrations = sorted((PROJECT / "domain" / "migrations").glob("[0-9][0-9][0-9][0-9]_*.py"))
    assert migrations[-1].name == "0018_workspace_assessment_projection.py"
    assert not any(path.name.startswith("0019_") for path in migrations)
    assert class_tests(PROJECT / "domain" / "tests" / "test_evidence_access.py", "EvidenceAccessTests") == FOUNDATION
    product_path = PROJECT / "production_player" / "tests" / "test_player_g9_evidence.py"
    assert class_tests(product_path, "ProductionPlayerG9EvidenceTests") == PRODUCT
    assert class_tests(product_path, "ProductionPlayerG9ChromiumTests") == CHROMIUM
    contract = PROJECT / "production_player" / "contracts" / "player_g9_evidence_claim_boundaries_v1.ru.json"
    raw = contract.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = contract.with_suffix(".json.sha256").read_text(encoding="ascii")
    assert sidecar == f"{digest}  {contract.name}\n"
    claims = json.loads(raw)
    assert claims["contract"] == "PLAYER_G9_EVIDENCE_CLAIM_BOUNDARIES_V1" and len(claims["statements"]) == 14
    pyproject = (PROJECT / "pyproject.toml").read_text(encoding="utf-8")
    for glob in ("contracts/*.json", "contracts/*.sha256", "templates/production_player/*.html", "static/production_player/*.css", "static/production_player/*.js"):
        assert glob in pyproject
    urls = (PROJECT / "domain" / "urls.py").read_text(encoding="utf-8")
    assert urls.count("parameter-values/<uuid:parameter_value_id>/facts/") == 1
    assert urls.count("assessments/<uuid:assessment_id>/facts/") == 1
    js = (PROJECT / "production_player" / "static" / "production_player" / "evidence.js").read_text(encoding="utf-8")
    for forbidden in ("localStorage", "sessionStorage", "indexedDB", "serviceWorker", "innerHTML"):
        assert forbidden not in js
    workflow = (ROOT / ".github" / "workflows" / "conflict-analysis.yml").read_text(encoding="utf-8")
    assert "player-g9-evidence-ui" in workflow and "codex/ca-suite-i1-player-g9-evidence-ui" in workflow
    assert os.getenv("G8_ACCEPTED_HEAD", G8_HEAD) == G8_HEAD
    assert os.getenv("G8_ACCEPTED_TREE", G8_TREE) == G8_TREE
    print(json.dumps({
        "G9_ALLOWLIST": "PASS", "scope": "15 = 5 M + 10 A",
        "foundation_portable": 8, "postgresql_only": 0,
        "product_portable": 6, "chromium": 3,
        "g8_head": G8_HEAD, "g8_tree": G8_TREE,
        "claim_bytes": len(raw), "claim_sha256": digest, "delivery_head": head,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
