from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
PROJECT=ROOT/"software"/"conflict_analysis"
R2_HEAD="f2255b6d76cf8efa46b5bea5756e09af4273b46a"
R2_TREE="249b5e826511072c6fbcb0ea3cb7441d83c25faf"
G7_HEAD="319450a64cb381df2e392027c64de157e2ed830c"
G7_TREE="95a8a2a5a7248dd3ec030963c3b25709d49364b0"
MODIFIED={
 ".github/workflows/conflict-analysis.yml":"4cfd1914779a1cb5d68354e7f60f6f3b7afc3027",
 "software/conflict_analysis/README.md":"633d7166857f01492f3421904da234c46a54022d",
 "software/conflict_analysis/pyproject.toml":"377b5ba4b44981e0cdbe0067bd41295b7b35eee0",
 "software/conflict_analysis/domain/services/xlsx_adapter.py":"f9f5a03d6148ea694e64ba5fe5dbe12ccf0f531d",
 "software/conflict_analysis/domain/models.py":"f92d07d187e03cd51ba9405c067029df12d7189e",
 "software/conflict_analysis/domain/urls.py":"78e8ad794250b6723f6031a2c1e026815bfb95df",
 "software/conflict_analysis/production_player/templates/production_player/workspace.html":"a19c6e827ba20e6272e94fa6f55826eb65616ba7",
 "software/conflict_analysis/production_player/urls.py":"e4aa5df45e423cc4ab529e0ff85b70aaf5dd36d5",
 "software/conflict_analysis/production_player/views.py":"dfa8022a7178eee6cf4efd46fb4c77ffe6ae930a",
}
ADDED={f"software/conflict_analysis/{path}" for path in (
 "docs/adr/0015-production-player-g8-experiments-xlsx.md","docs/production-player-g8-import-profile.md",
 "domain/api/player_experiments.py","domain/services/player_experiments.py","domain/services/xlsx_import_profiles.py",
 "domain/import_profiles/kz_zhanaozen_expert_v2_a5_v0_1.json","domain/import_profiles/kz_zhanaozen_expert_v2_a5_v0_1.json.sha256",
 "domain/tests/test_player_experiments.py","domain/tests/test_player_xlsx_import.py","production_player/experiment_claim_boundaries.py",
 "production_player/contracts/player_g8_claim_boundaries_v1.ru.json","production_player/contracts/player_g8_claim_boundaries_v1.ru.json.sha256",
 "production_player/static/production_player/experiments.css","production_player/static/production_player/experiments.js",
 "production_player/templates/production_player/experiment.html","production_player/tests/test_player_g8.py",
 "production_player/browser_tests/player_g8.mjs","scripts/verify_player_g8_allowlist.py")}
FOUNDATION=[
"test_assessment_author_permission_family_scope_hiding_and_no_studio_mixing_are_exact","test_expert_profile_assessment_set_experiment_create_replay_and_receipt_are_atomic","test_human_and_ai_experiments_keep_independent_values_without_overwrite","test_used_expert_profile_and_frozen_archived_experiment_guards_fail_closed","test_manual_first_value_and_successor_correction_preserve_immutable_history","test_frozen_computed_and_a5_blocked_targets_deny_value_writes","test_general_comparison_returns_raw_values_without_aggregation_or_fill_across","test_import_candidates_are_experiment_scoped_and_general_does_not_leak_them","test_a3_a4_a5_profile_hashes_lineage_and_330_classification_are_exact","test_xlsx_bounds_repeated_headers_formula_and_cached_values_fail_closed","test_row_order_independent_stable_id_mapping_uses_exact_projection_and_applicability","test_unknown_blank_zero_and_per_value_categorical_confidence_are_not_collapsed","test_a5_288_transfer_review_flags_and_18_24_exclusions_never_create_values","test_missing_rows_warn_while_unknown_duplicate_range_and_type_errors_block_commit","test_missing_rationale_uses_factual_source_provenance_without_invented_justification","test_preview_is_deterministic_zero_write_and_hash_bound","test_import_ticket_acknowledgement_same_bytes_reparse_key_and_if_match_are_sealed","test_atomic_import_replay_recovery_after_freeze_and_import_run_receipt_are_exact","test_nonempty_experiment_and_competing_imports_are_rejected_without_partial_writes","test_legacy_xlsx_adapter_and_foundation_package_regressions_remain_unchanged"]
POSTGRES=["test_concurrent_experiment_same_key_creates_one_aggregate_and_one_exact_replay","test_concurrent_import_same_key_creates_one_graph_and_one_exact_replay","test_competing_import_keys_into_one_empty_experiment_have_one_commit_and_one_typed_loser","test_concurrent_manual_corrections_have_one_successor_and_one_stale_loser"]
PRODUCT=["test_g8_routes_permission_family_csrf_object_scope_and_nonfingerprinting_are_exact","test_only_projection_complete_workspaces_and_draft_assessment_experiments_enable_g8_actions","test_expert_profile_creation_freeze_on_first_use_and_historical_display_are_truthful","test_experiment_create_edit_freeze_archive_replay_and_modeling_disabled_states_are_exact","test_ai_and_human_tabs_select_distinct_columns_and_never_overwrite_lanes","test_xlsx_preview_renders_source_lineage_330_classification_and_zero_write_truth","test_retained_ticket_acknowledgement_commit_recovery_and_key_reuse_ui_are_exact","test_unknown_blank_zero_confidence_review_flags_and_blocked42_render_distinctly","test_manual_value_successor_history_and_frozen_target_disabled_reasons_are_exact","test_general_comparison_shows_only_raw_series_without_mean_rank_consensus_or_fill","test_import_candidates_and_receipts_are_experiment_scoped_non_html_and_not_evidence","test_claim_contract_browser_storage_off_origin_formula_and_product_orm_boundaries_are_exact"]
CHROMIUM=["test_chromium_ai_and_human_experiments_import_distinct_columns_compare_raw_series_and_reopen","test_chromium_unknown_duplicate_blocked42_freeze_role_scope_and_no_persistent_state"]

def git(*args): return subprocess.check_output(["git",*args],cwd=ROOT,text=True).strip()
def functions(path): return [node.name for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith("test_")]
def main():
 assert git("rev-parse",f"{R2_HEAD}^{{tree}}") == R2_TREE
 assert git("rev-list","--parents","-n","1",R2_HEAD) == f"{R2_HEAD} {G7_HEAD}"
 assert git("rev-parse",f"{G7_HEAD}^{{tree}}") == G7_TREE
 for path,blob in MODIFIED.items(): assert git("rev-parse",f"{R2_HEAD}:{path}")==blob,(path,blob)
 expected={f"M\t{path}" for path in MODIFIED}|{f"A\t{path}" for path in ADDED}
 if git("rev-parse","HEAD") != R2_HEAD:
  delta=set(git("diff","--no-renames","--name-status",R2_HEAD,"HEAD").splitlines()); assert delta==expected,(sorted(delta),sorted(expected))
 assert not (PROJECT/"domain"/"migrations"/"0019_player_experiments.py").exists()
 migrations=sorted((PROJECT/"domain"/"migrations").glob("[0-9][0-9][0-9][0-9]_*.py")); assert migrations[-1].name=="0018_workspace_assessment_projection.py"
 assert functions(PROJECT/"domain"/"tests"/"test_player_experiments.py")==FOUNDATION[:8]+POSTGRES
 assert functions(PROJECT/"domain"/"tests"/"test_player_xlsx_import.py")==FOUNDATION[8:]
 assert functions(PROJECT/"production_player"/"tests"/"test_player_g8.py")==PRODUCT+CHROMIUM
 source_paths={ROOT/path for path in git("ls-files").splitlines()}|{ROOT/path for path in ADDED}
 text="\n".join(path.read_text(encoding="utf-8") for path in source_paths if path.is_file() and path.suffix in {".py",".js",".html",".json",".md"})
 assert text.count("G8-"+"G9-FOCUS-R1")==4
 profile=json.loads((PROJECT/"domain"/"import_profiles"/"kz_zhanaozen_expert_v2_a5_v0_1.json").read_text(encoding="utf-8")); assert len(profile["records"])==330
 assert {row["migration_status"] for row in profile["records"]}=={"TRANSFER_WITH_REVIEW","METHOD_BLOCKED","RECODING_REQUIRED"}
 assert os.getenv("G7_ACCEPTED_HEAD",G7_HEAD)==G7_HEAD and os.getenv("G7_ACCEPTED_TREE",G7_TREE)==G7_TREE
 print(json.dumps({"G8_ALLOWLIST":"PASS","scope":"27 = 9 M + 18 A","foundation_portable":20,"postgresql_only":4,"product_portable":12,"chromium":2,"r2_head":R2_HEAD,"r2_tree":R2_TREE,"g7_head":G7_HEAD,"g7_tree":G7_TREE},sort_keys=True))
if __name__=="__main__": main()
