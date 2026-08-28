#!/usr/bin/env python3
"""Verify exact FD01/FD05 prerequisite path sets and accepted C0 freeze anchors."""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PurePosixPath


FD01_BASE_HEAD = "c0b773573c8d37faf7b1b71e910f7a8d356000f4"
FD01_BASE_TREE = "914e3b0895e404cf699d651c8148da875528b4e7"
FD01_RC1_START_HEAD = "1e2fd10878236ee8f0a01a62773894dd9c0d5c40"
FD01_RC1_START_TREE = "671c0777cee1d4542ebe4eeb1128c0e0fecac4b3"
FD01_RC2_START_HEAD = "2bf40798dc2c4ba0ea3c742bf86b88fda4bde8d0"
FD01_RC2_START_TREE = "23161d6d2ba575d1ca92149f468e086ce43df129"
FD01_RC3_START_HEAD = "6b502c985094799050e0970a7c40d5a4f9cd0724"
FD01_RC3_START_TREE = "d527e34b8e9d3d67802be0118ac4928821cfd60b"
PINNED_PRODUCTION_STUDIO_TREE = "87d8e93ec09a18b87ae016977f0fb5fbf67d4104"
PINNED_MODELS_BLOB = "c6c5c2419989e7b0cf40bd1242ab65d37cc2e162"
PINNED_ENUMS_BLOB = "a701c3c83511b7d1706519d40fab4580d0a0d63e"
PINNED_MIGRATIONS_TREE = "b0cc214cd63086172c9d3801338a5a2302a7ce0f"
PINNED_PROJECT_DEFINITIONS_BLOB = "de4a4f69d3627d83766ef3b0f6bbd44c885af14d"

FD01_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/domain/urls.py",
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/policies.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/scripts/verify_foundation_c1_prerequisites_allowlist.py",
    }
)

FD01_RC2_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/scripts/verify_foundation_c1_prerequisites_allowlist.py",
    }
)

# RC3 is another gate-only correction over the same two inherited gate files.
FD01_RC3_ALLOWLIST = FD01_RC2_ALLOWLIST

C0_BRANCH = "codex/ca-suite-i1-production-studio-c0-read-only"
FD01_BRANCH = "codex/ca-suite-i1-foundation-fd01-validation-preview"
FD05_BRANCH = "codex/ca-suite-i1-foundation-fd05-audited-write-reconciliation"
ROUTE_MATRIX = {
    ("pull_request", FD01_BRANCH, C0_BRANCH): "FD01",
    ("pull_request", FD05_BRANCH, FD01_BRANCH): "FD05",
    ("push", FD01_BRANCH, ""): "FD01",
    ("push", FD05_BRANCH, ""): "FD05",
}

FD01_TEST_CLASS = "FoundationStudioValidationPreviewHttpTests"
FD01_TEST_METHODS = (
    "test_validation_preview_valid_and_invalid_candidates_return_exact_contract",
    "test_validation_preview_matches_validate_policy_help_resolution_and_order",
    "test_validation_preview_bounds_projection_and_hashes_complete_diagnostics",
    "test_validation_preview_retry_is_byte_identical_and_changes_no_row",
    "test_validation_preview_auth_scope_and_capability_precede_capture",
    "test_validation_preview_session_csrf_precedes_capture_and_basic_matches_contract",
    "test_validation_preview_reuses_all_raw_json_ingress_vectors",
    "test_validation_preview_rejects_nonexact_envelope_query_headers_and_non_draft",
)
FD01_TEST_MODULE = Path(
    "software/conflict_analysis/domain/tests/test_foundation_studio_http.py"
)

# This is a path/test contract only.  It deliberately contains no future FD01 H1/T1
# identity; MAIN must pin that exact accepted HEAD/TREE before FD05 authorization.
FD05_ALLOWLIST = frozenset(
    {
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/policies.py",
        "software/conflict_analysis/domain/services/foundation_packages.py",
        "software/conflict_analysis/domain/services/project_definitions.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_bootstrap.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_write_reconciliation.py",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
    }
)

FD05_TEST_MODULE = Path(
    "software/conflict_analysis/domain/tests/"
    "test_foundation_studio_write_reconciliation.py"
)
FD05_PORTABLE_TEST_CLASS = "FoundationStudioWriteReconciliationTests"
FD05_PORTABLE_TEST_METHODS = (
    "test_all_five_operations_emit_exact_immutable_human_receipts",
    "test_operation_key_is_required_and_validated_before_body_capture",
    "test_create_clone_envelopes_and_preselected_ids_are_exact",
    "test_clone_save_validate_require_exact_strong_if_match",
    "test_exact_retry_reconciles_before_stale_lifecycle_or_duplicate_checks",
    "test_operation_key_reuse_changed_actor_route_target_body_or_token_is_typed",
    "test_create_clone_identity_conflicts_have_stable_precedence",
    "test_save_and_validate_stale_or_non_draft_outcomes_are_typed",
    "test_validate_uses_fd01_policy_report_and_replay_is_immutable",
    "test_replay_uses_audit_snapshot_after_later_definition_change",
    "test_auth_scope_capability_csrf_and_spoof_order_remains_fail_closed",
    "test_fault_injection_rolls_back_definition_scope_membership_and_audit_without_orphans",
)
FD05_POSTGRESQL_TEST_CLASS = "FoundationStudioWriteReconciliationConcurrencyTests"
FD05_POSTGRESQL_TEST_METHODS = (
    "test_postgresql_concurrent_bootstrap_same_key_has_one_graph_one_audit_one_reconcile",
    "test_postgresql_concurrent_create_same_key_has_one_commit_one_reconcile",
    "test_postgresql_different_keys_same_create_or_clone_identity_have_one_typed_loser",
    "test_postgresql_concurrent_stale_saves_have_one_commit_one_draft_stale",
    "test_postgresql_save_validate_race_obeys_project_first_lock_order",
)

BASELINE_SQLITE_SKIPS = (
    (
        "domain.tests.test_foundation_studio_bootstrap."
        "FoundationStudioBootstrapConcurrencyTests",
        "test_postgresql_concurrent_bootstrap_has_one_winner_and_one_explicit_conflict",
    ),
    (
        "domain.tests.test_foundation_studio_bootstrap."
        "FoundationStudioSuccessorConcurrencyTests",
        "test_postgresql_competing_successors_have_one_winner_and_preserve_old_pin",
    ),
    (
        "domain.tests.test_foundation_studio_bootstrap."
        "FoundationStudioApplicationSuccessorConcurrencyTests",
        "test_postgresql_application_wrapper_has_one_success_and_one_typed_conflict",
    ),
    (
        "domain.tests.test_foundation_studio_bootstrap."
        "FoundationStudioFirstProjectApplicationConcurrencyTests",
        "test_postgresql_application_bootstrap_has_one_complete_winner_and_no_orphans",
    ),
    (
        "domain.tests.test_foundation_studio_package."
        "FoundationStudioCrossPathLockOrderTests",
        "test_postgresql_import_initial_and_successor_paths_share_one_lock_order",
    ),
    (
        "domain.tests.test_postgresql_migrations.PostgreSQLMigrationGateTests",
        "test_clean_test_database_is_at_every_migration_leaf",
    ),
)
FD05_SQLITE_SKIPS = BASELINE_SQLITE_SKIPS + tuple(
    (
        "domain.tests.test_foundation_studio_write_reconciliation."
        + FD05_POSTGRESQL_TEST_CLASS,
        method,
    )
    for method in FD05_POSTGRESQL_TEST_METHODS
)

SLICE_TOTALS = {
    "FD01": {
        "postgresql_collected": 183,
        "postgresql_passed": 183,
        "postgresql_skipped": 0,
        "sqlite_collected": 183,
        "sqlite_passed": 177,
        "sqlite_skipped": 6,
        "c0_postgresql_passed": 19,
        "c0_sqlite_passed": 19,
    },
    "FD05": {
        "postgresql_collected": 200,
        "postgresql_passed": 200,
        "postgresql_skipped": 0,
        "sqlite_collected": 200,
        "sqlite_passed": 189,
        "sqlite_skipped": 11,
        "c0_postgresql_passed": 19,
        "c0_sqlite_passed": 19,
    },
}

LOWERCASE_SHA1 = re.compile(r"[0-9a-f]{40}\Z")

WORKFLOW_PATH = ".github/workflows/conflict-analysis.yml"
VERIFIER_PATH = (
    "software/conflict_analysis/scripts/"
    "verify_foundation_c1_prerequisites_allowlist.py"
)
COMMON_FROZEN_PATHS = (
    "software/conflict_analysis/production_studio",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/enums.py",
    "software/conflict_analysis/domain/migrations",
    "software/conflict_analysis/studio_showcase",
    "software/conflict_analysis/shared_ui",
)

PINNED_MIGRATIONS = (
    "software/conflict_analysis/domain/migrations/0001_initial.py",
    "software/conflict_analysis/domain/migrations/0002_foundation_v4_schema.py",
    "software/conflict_analysis/domain/migrations/0003_foundation_v4_workspace_required.py",
    "software/conflict_analysis/domain/migrations/0004_power_metadata_state.py",
    "software/conflict_analysis/domain/migrations/0005_foundation_contract_completion.py",
    "software/conflict_analysis/domain/migrations/0006_definition_lifecycle_enforcement.py",
    "software/conflict_analysis/domain/migrations/0007_assessment_header_confidence.py",
    "software/conflict_analysis/domain/migrations/0008_evidence_relation_contract.py",
    "software/conflict_analysis/domain/migrations/0009_append_only_provenance_restrict.py",
    "software/conflict_analysis/domain/migrations/0010_import_receipt_contract.py",
    "software/conflict_analysis/domain/migrations/0011_chat_citation_target_modes.py",
    "software/conflict_analysis/domain/migrations/0012_xlsx_metadata_contract.py",
    "software/conflict_analysis/domain/migrations/0013_foundation_studio_contract_fields.py",
    "software/conflict_analysis/domain/migrations/0014_foundation_studio_contract_backfill.py",
    "software/conflict_analysis/domain/migrations/0015_foundation_studio_contract_constraints.py",
    "software/conflict_analysis/domain/migrations/__init__.py",
)


class VerificationError(RuntimeError):
    """A deterministic prerequisite-boundary verification failure."""


def _git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if check and completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _repo_root(start: Path) -> Path:
    return Path(_git(start, "rev-parse", "--show-toplevel")).resolve()


def _normalize(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    if normalized.startswith("../") or normalized == "..":
        raise VerificationError(f"changed path escapes repository: {path!r}")
    return normalized


def _changed_paths(repo: Path, base_head: str) -> set[str]:
    groups = (
        _git(repo, "diff", "--name-only", f"{base_head}...HEAD", "--"),
        _git(repo, "diff", "--name-only", "HEAD", "--"),
        _git(repo, "diff", "--cached", "--name-only", "HEAD", "--"),
        _git(repo, "ls-files", "--others", "--exclude-standard"),
    )
    return {
        _normalize(path)
        for group in groups
        for path in group.splitlines()
        if path
    }


def _committed_changed_paths(repo: Path, base_head: str, target_head: str) -> set[str]:
    return {
        _normalize(path)
        for path in _git(
            repo,
            "diff",
            "--name-only",
            f"{base_head}...{target_head}",
            "--",
        ).splitlines()
        if path
    }


def _object(repo: Path, spec: str) -> str:
    return _git(repo, "rev-parse", spec)


def _validate_external_sha(value: str, *, label: str) -> None:
    if LOWERCASE_SHA1.fullmatch(value) is None:
        raise VerificationError(f"{label} must be an exact lowercase 40-hex object id")


def _select_slice_from_refs(
    *,
    event_name: str,
    head_ref: str,
    base_ref: str,
) -> str:
    try:
        return ROUTE_MATRIX[(event_name, head_ref, base_ref)]
    except KeyError as exc:
        raise VerificationError(
            "unsupported prerequisite route: "
            f"{event_name}|{head_ref}|{base_ref}"
        ) from exc


def _verify_external_fd01_pin(
    *,
    slice_name: str,
    base_head: str,
    base_tree: str,
    accepted_head: str | None,
    accepted_tree: str | None,
) -> str:
    """Validate the external MAIN pin separately from the event/live base."""

    if slice_name == "FD01":
        return "NOT_APPLICABLE"
    if slice_name != "FD05":
        raise VerificationError(f"unsupported prerequisite slice: {slice_name}")

    missing = [
        label
        for label, value in (
            ("--fd01-accepted-head", accepted_head),
            ("--fd01-accepted-tree", accepted_tree),
        )
        if not value
    ]
    if missing:
        raise VerificationError(
            "FD05 requires externally supplied " + " and ".join(missing)
        )

    _validate_external_sha(base_head, label="FD05 --base-head")
    _validate_external_sha(base_tree, label="FD05 --base-tree")
    _validate_external_sha(
        accepted_head,
        label="FD05 --fd01-accepted-head",
    )
    _validate_external_sha(
        accepted_tree,
        label="FD05 --fd01-accepted-tree",
    )
    if base_head != accepted_head:
        raise VerificationError(
            "FD05 event/live base HEAD does not match external FD01 accepted HEAD"
        )
    if base_tree != accepted_tree:
        raise VerificationError(
            "FD05 event/live base TREE does not match external FD01 accepted TREE"
        )
    return "PIN_VERIFIED_EXTERNAL"


def _expect_verification_error(operation: Callable[[], object]) -> bool:
    try:
        operation()
    except VerificationError:
        return True
    return False


def _parse_module(repo: Path, module_path: Path, *, label: str) -> ast.Module:
    test_path = repo / module_path
    try:
        return ast.parse(
            test_path.read_text(encoding="utf-8"),
            filename=str(test_path),
        )
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise VerificationError(f"cannot parse {label}: {exc}") from exc


def _verify_exact_test_class(
    module: ast.Module,
    *,
    class_name: str,
    expected_methods: tuple[str, ...],
    label: str,
) -> tuple[str, ...]:
    classes = [
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise VerificationError(f"expected exactly one {class_name} class, got {len(classes)}")
    actual = tuple(
        node.name
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )
    if actual != expected_methods:
        raise VerificationError(
            f"{label} test-node topology changed: "
            + json.dumps(
                {"expected": expected_methods, "actual": actual},
                ensure_ascii=False,
            )
        )
    return actual


def _verify_fd01_test_nodes(repo: Path) -> tuple[str, ...]:
    module = _parse_module(repo, FD01_TEST_MODULE, label="FD01 test module")
    return _verify_exact_test_class(
        module,
        class_name=FD01_TEST_CLASS,
        expected_methods=FD01_TEST_METHODS,
        label="FD01",
    )


def _verify_fd05_test_nodes(
    repo: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    module = _parse_module(repo, FD05_TEST_MODULE, label="FD05 test module")
    portable = _verify_exact_test_class(
        module,
        class_name=FD05_PORTABLE_TEST_CLASS,
        expected_methods=FD05_PORTABLE_TEST_METHODS,
        label="FD05 portable",
    )
    postgresql = _verify_exact_test_class(
        module,
        class_name=FD05_POSTGRESQL_TEST_CLASS,
        expected_methods=FD05_POSTGRESQL_TEST_METHODS,
        label="FD05 PostgreSQL-only",
    )
    return portable, postgresql


def _verify_exact_paths(
    *,
    actual: set[str],
    expected: frozenset[str],
    label: str,
) -> None:
    if actual != expected:
        raise VerificationError(
            f"{label} changed paths are not the exact allowlist: "
            + json.dumps(
                {
                    "missing": sorted(expected - actual),
                    "extra": sorted(actual - expected),
                },
                ensure_ascii=False,
            )
        )


def _verify_bounded_paths(
    *,
    actual: set[str],
    required: frozenset[str],
    allowed: frozenset[str],
    label: str,
) -> None:
    missing = required - actual
    extra = actual - allowed
    if missing or extra:
        raise VerificationError(
            f"{label} changed paths violate required/allowed bounds: "
            + json.dumps(
                {
                    "missing_required": sorted(missing),
                    "outside_allowlist": sorted(extra),
                },
                ensure_ascii=False,
            )
        )


def _verify_pinned_start(
    repo: Path,
    *,
    head: str,
    tree: str,
    label: str,
) -> None:
    if _object(repo, f"{head}^{{tree}}") != tree:
        raise VerificationError(f"{label} tree does not match its pinned HEAD")


def _verify_ancestor(repo: Path, ancestor: str, descendant: str, *, label: str) -> None:
    if _git(repo, "merge-base", ancestor, descendant) != ancestor:
        raise VerificationError(f"{label} is not a fast-forward ancestry relation")


def _verify_no_merges(repo: Path, base_head: str, target_head: str, *, label: str) -> None:
    if _git(repo, "rev-list", "--merges", f"{base_head}..{target_head}"):
        raise VerificationError(f"merge commits are forbidden inside {label}")


def _verify_migration_filenames(repo: Path) -> None:
    migrations = tuple(
        line
        for line in _git(
            repo,
            "ls-files",
            "software/conflict_analysis/domain/migrations",
        ).splitlines()
        if line
    )
    if migrations != PINNED_MIGRATIONS:
        raise VerificationError(
            "migration filename set changed: "
            + json.dumps({"expected": PINNED_MIGRATIONS, "actual": migrations})
        )


def _verify_frozen_paths(
    repo: Path,
    *,
    base_head: str,
    paths: tuple[str, ...],
    slice_name: str,
) -> None:
    for path in paths:
        if _git(repo, "diff", "--name-only", base_head, "--", path):
            raise VerificationError(f"{slice_name} frozen path changed: {path}")


def _verify_common_freezes(repo: Path, *, base_head: str) -> dict[str, str]:
    freeze_specs = {
        "production_studio_tree": (
            "software/conflict_analysis/production_studio",
            PINNED_PRODUCTION_STUDIO_TREE,
        ),
        "models_blob": (
            "software/conflict_analysis/domain/models.py",
            PINNED_MODELS_BLOB,
        ),
        "enums_blob": (
            "software/conflict_analysis/domain/enums.py",
            PINNED_ENUMS_BLOB,
        ),
        "migrations_tree": (
            "software/conflict_analysis/domain/migrations",
            PINNED_MIGRATIONS_TREE,
        ),
    }
    resolved: dict[str, str] = {}
    for label, (path, expected) in freeze_specs.items():
        for ref_label, ref in (("base", base_head), ("HEAD", "HEAD")):
            value = _object(repo, f"{ref}:{path}")
            if value != expected:
                raise VerificationError(
                    f"pinned {label} mismatch at {ref_label}: "
                    f"expected {expected}, got {value}"
                )
        resolved[label] = expected
    _verify_migration_filenames(repo)
    return resolved


def _contract_self_check() -> dict[str, object]:
    pin_head = "a" * 40
    pin_tree = "b" * 40
    other_object = "c" * 40
    relaxed_allowed_path = "software/conflict_analysis/domain/urls.py"
    fd01_totals = SLICE_TOTALS["FD01"]
    fd05_totals = SLICE_TOTALS["FD05"]
    fd05_added_nodes = len(FD05_PORTABLE_TEST_METHODS) + len(
        FD05_POSTGRESQL_TEST_METHODS
    )

    checks = {
        "fd01_allowlist_count": len(FD01_ALLOWLIST) == 7,
        "fd01_rc2_allowlist_count": len(FD01_RC2_ALLOWLIST) == 2,
        "fd01_rc2_is_fd01_subset": FD01_RC2_ALLOWLIST < FD01_ALLOWLIST,
        "fd05_allowlist_count": len(FD05_ALLOWLIST) == 8,
        "fd05_freezes_gate_files": not (
            {WORKFLOW_PATH, VERIFIER_PATH} & FD05_ALLOWLIST
        ),
        "fd05_test_module_is_allowed": FD05_TEST_MODULE.as_posix()
        in FD05_ALLOWLIST,
        "fd01_test_nodes_exact_unique_eight": len(FD01_TEST_METHODS) == 8
        and len(set(FD01_TEST_METHODS)) == 8,
        "fd05_portable_nodes_exact_unique_twelve": len(
            FD05_PORTABLE_TEST_METHODS
        )
        == 12
        and len(set(FD05_PORTABLE_TEST_METHODS)) == 12,
        "fd05_postgresql_nodes_exact_unique_five": len(
            FD05_POSTGRESQL_TEST_METHODS
        )
        == 5
        and len(set(FD05_POSTGRESQL_TEST_METHODS)) == 5,
        "fd05_test_node_sets_disjoint": not (
            set(FD05_PORTABLE_TEST_METHODS) & set(FD05_POSTGRESQL_TEST_METHODS)
        ),
        "fd01_sqlite_skips_exact_six": len(BASELINE_SQLITE_SKIPS) == 6
        and len(set(BASELINE_SQLITE_SKIPS)) == 6,
        "fd05_sqlite_skips_exact_eleven": len(FD05_SQLITE_SKIPS) == 11
        and len(set(FD05_SQLITE_SKIPS)) == 11,
        "fd01_postgresql_total_partition_is_consistent": (
            fd01_totals["postgresql_collected"]
            == fd01_totals["postgresql_passed"]
            + fd01_totals["postgresql_skipped"]
            and fd01_totals["postgresql_skipped"] == 0
        ),
        "fd01_sqlite_total_partition_is_consistent": (
            fd01_totals["sqlite_collected"]
            == fd01_totals["sqlite_passed"] + fd01_totals["sqlite_skipped"]
            and fd01_totals["sqlite_skipped"] == len(BASELINE_SQLITE_SKIPS)
            and fd01_totals["sqlite_collected"]
            == fd01_totals["postgresql_collected"]
        ),
        "fd01_totals_derive_from_pre_preview_baseline": (
            fd01_totals["postgresql_collected"]
            == 175 + len(FD01_TEST_METHODS)
            and fd01_totals["postgresql_passed"]
            == 175 + len(FD01_TEST_METHODS)
            and fd01_totals["sqlite_passed"]
            == 169 + len(FD01_TEST_METHODS)
        ),
        "fd05_postgresql_totals_derive_from_fd01_nodes": (
            fd05_totals["postgresql_collected"]
            == fd01_totals["postgresql_collected"] + fd05_added_nodes
            and fd05_totals["postgresql_passed"]
            == fd01_totals["postgresql_passed"] + fd05_added_nodes
            and fd05_totals["postgresql_skipped"]
            == fd01_totals["postgresql_skipped"]
        ),
        "fd05_sqlite_totals_derive_from_fd01_nodes": (
            fd05_totals["sqlite_collected"]
            == fd01_totals["sqlite_collected"] + fd05_added_nodes
            and fd05_totals["sqlite_passed"]
            == fd01_totals["sqlite_passed"]
            + len(FD05_PORTABLE_TEST_METHODS)
            and fd05_totals["sqlite_skipped"]
            == fd01_totals["sqlite_skipped"]
            + len(FD05_POSTGRESQL_TEST_METHODS)
        ),
        "c0_totals_are_cross_slice_and_cross_backend_invariant": (
            fd01_totals["c0_postgresql_passed"]
            == fd01_totals["c0_sqlite_passed"]
            == fd05_totals["c0_postgresql_passed"]
            == fd05_totals["c0_sqlite_passed"]
            == 19
        ),
        "routing_matrix_has_exact_four_entries": len(ROUTE_MATRIX) == 4,
        "route_fd01_pull_request": _select_slice_from_refs(
            event_name="pull_request",
            head_ref=FD01_BRANCH,
            base_ref=C0_BRANCH,
        )
        == "FD01",
        "route_fd05_pull_request": _select_slice_from_refs(
            event_name="pull_request",
            head_ref=FD05_BRANCH,
            base_ref=FD01_BRANCH,
        )
        == "FD05",
        "route_fd01_push": _select_slice_from_refs(
            event_name="push",
            head_ref=FD01_BRANCH,
            base_ref="",
        )
        == "FD01",
        "route_fd05_push": _select_slice_from_refs(
            event_name="push",
            head_ref=FD05_BRANCH,
            base_ref="",
        )
        == "FD05",
        "route_rejects_main_push": _expect_verification_error(
            lambda: _select_slice_from_refs(
                event_name="push",
                head_ref="main",
                base_ref="",
            )
        ),
        "route_rejects_fd05_to_c0_pull_request": _expect_verification_error(
            lambda: _select_slice_from_refs(
                event_name="pull_request",
                head_ref=FD05_BRANCH,
                base_ref=C0_BRANCH,
            )
        ),
        "route_rejects_unrelated_pull_request": _expect_verification_error(
            lambda: _select_slice_from_refs(
                event_name="pull_request",
                head_ref="unrelated",
                base_ref=FD01_BRANCH,
            )
        ),
        "route_rejects_unsupported_event": _expect_verification_error(
            lambda: _select_slice_from_refs(
                event_name="workflow_dispatch",
                head_ref=FD01_BRANCH,
                base_ref=C0_BRANCH,
            )
        ),
        "fd01_external_pin_is_not_applicable": _verify_external_fd01_pin(
            slice_name="FD01",
            base_head="",
            base_tree="",
            accepted_head=None,
            accepted_tree=None,
        )
        == "NOT_APPLICABLE",
        "fd05_exact_external_pin_is_accepted": _verify_external_fd01_pin(
            slice_name="FD05",
            base_head=pin_head,
            base_tree=pin_tree,
            accepted_head=pin_head,
            accepted_tree=pin_tree,
        )
        == "PIN_VERIFIED_EXTERNAL",
        "fd05_missing_external_head_is_rejected": _expect_verification_error(
            lambda: _verify_external_fd01_pin(
                slice_name="FD05",
                base_head=pin_head,
                base_tree=pin_tree,
                accepted_head=None,
                accepted_tree=pin_tree,
            )
        ),
        "fd05_missing_external_pair_is_rejected": _expect_verification_error(
            lambda: _verify_external_fd01_pin(
                slice_name="FD05",
                base_head=pin_head,
                base_tree=pin_tree,
                accepted_head=None,
                accepted_tree=None,
            )
        ),
        "fd05_missing_external_tree_is_rejected": _expect_verification_error(
            lambda: _verify_external_fd01_pin(
                slice_name="FD05",
                base_head=pin_head,
                base_tree=pin_tree,
                accepted_head=pin_head,
                accepted_tree=None,
            )
        ),
        "fd05_malformed_external_head_is_rejected": _expect_verification_error(
            lambda: _verify_external_fd01_pin(
                slice_name="FD05",
                base_head=pin_head,
                base_tree=pin_tree,
                accepted_head="A" * 40,
                accepted_tree=pin_tree,
            )
        ),
        "fd05_malformed_external_tree_is_rejected": _expect_verification_error(
            lambda: _verify_external_fd01_pin(
                slice_name="FD05",
                base_head=pin_head,
                base_tree=pin_tree,
                accepted_head=pin_head,
                accepted_tree="z" * 40,
            )
        ),
        "fd05_external_head_mismatch_is_rejected": _expect_verification_error(
            lambda: _verify_external_fd01_pin(
                slice_name="FD05",
                base_head=pin_head,
                base_tree=pin_tree,
                accepted_head=other_object,
                accepted_tree=pin_tree,
            )
        ),
        "fd05_external_tree_mismatch_is_rejected": _expect_verification_error(
            lambda: _verify_external_fd01_pin(
                slice_name="FD05",
                base_head=pin_head,
                base_tree=pin_tree,
                accepted_head=pin_head,
                accepted_tree=other_object,
            )
        ),
        "future_h1_exact_required_paths_are_accepted": not _expect_verification_error(
            lambda: _verify_bounded_paths(
                actual=set(FD01_RC2_ALLOWLIST),
                required=FD01_RC2_ALLOWLIST,
                allowed=FD01_ALLOWLIST,
                label="self-check future H1",
            )
        ),
        "future_h1_relaxed_allowed_superset_is_accepted": not _expect_verification_error(
            lambda: _verify_bounded_paths(
                actual=set(FD01_RC2_ALLOWLIST) | {relaxed_allowed_path},
                required=FD01_RC2_ALLOWLIST,
                allowed=FD01_ALLOWLIST,
                label="self-check future H1",
            )
        ),
        "future_h1_full_fd01_allowlist_is_accepted": not _expect_verification_error(
            lambda: _verify_bounded_paths(
                actual=set(FD01_ALLOWLIST),
                required=FD01_RC2_ALLOWLIST,
                allowed=FD01_ALLOWLIST,
                label="self-check future H1",
            )
        ),
        "future_h1_missing_required_path_is_rejected": _expect_verification_error(
            lambda: _verify_bounded_paths(
                actual={WORKFLOW_PATH},
                required=FD01_RC2_ALLOWLIST,
                allowed=FD01_ALLOWLIST,
                label="self-check future H1",
            )
        ),
        "future_h1_outside_allowlist_path_is_rejected": _expect_verification_error(
            lambda: _verify_bounded_paths(
                actual=set(FD01_RC2_ALLOWLIST) | {"README.md"},
                required=FD01_RC2_ALLOWLIST,
                allowed=FD01_ALLOWLIST,
                label="self-check future H1",
            )
        ),
    }
    failed = sorted(label for label, passed in checks.items() if not passed)
    if failed:
        raise VerificationError(
            "slice contract self-check failed: "
            + json.dumps(failed, ensure_ascii=False)
        )
    return {
        "contract_self_check_only": "PASS",
        "repository_access": "NOT_USED",
        "network_access": "NOT_USED",
        "future_fd01_accepted_pin": "EXTERNAL_MAIN_ORACLE_REQUIRED",
        "checks": checks,
        "slices": {
            "FD01": {
                "allowlist": sorted(FD01_ALLOWLIST),
                "rc2_incremental_allowlist": sorted(FD01_RC2_ALLOWLIST),
                "rc3_incremental_allowlist": sorted(FD01_RC3_ALLOWLIST),
                "test_class": FD01_TEST_CLASS,
                "test_nodes": list(FD01_TEST_METHODS),
                "totals": SLICE_TOTALS["FD01"],
                "sqlite_skips": [list(item) for item in BASELINE_SQLITE_SKIPS],
            },
            "FD05": {
                "path_contract_status": "PREDECLARED_NOT_IMPLEMENTED",
                "test_node_contract_status": "PREDECLARED_NOT_IMPLEMENTED",
                "totals_status": "PREDECLARED_NOT_IMPLEMENTED",
                "allowlist": sorted(FD05_ALLOWLIST),
                "base_pin": "EXTERNAL_MAIN_ORACLE_REQUIRED",
                "portable_test_class": FD05_PORTABLE_TEST_CLASS,
                "portable_test_nodes": list(FD05_PORTABLE_TEST_METHODS),
                "postgresql_test_class": FD05_POSTGRESQL_TEST_CLASS,
                "postgresql_test_nodes": list(FD05_POSTGRESQL_TEST_METHODS),
                "totals": SLICE_TOTALS["FD05"],
                "sqlite_skips": [list(item) for item in FD05_SQLITE_SKIPS],
            },
        },
    }


def verify_fd01(repo: Path, *, base_head: str, base_tree: str) -> dict[str, object]:
    if base_head != FD01_BASE_HEAD or base_tree != FD01_BASE_TREE:
        raise VerificationError("FD01 accepts only the MAIN-authorized C0 HEAD/TREE")
    if _object(repo, f"{base_head}^{{tree}}") != base_tree:
        raise VerificationError("FD01 base tree does not match the pinned C0 tree")
    _verify_pinned_start(
        repo,
        head=FD01_RC1_START_HEAD,
        tree=FD01_RC1_START_TREE,
        label="FD01 RC1 start",
    )
    _verify_pinned_start(
        repo,
        head=FD01_RC2_START_HEAD,
        tree=FD01_RC2_START_TREE,
        label="FD01 RC2 start",
    )
    _verify_pinned_start(
        repo,
        head=FD01_RC3_START_HEAD,
        tree=FD01_RC3_START_TREE,
        label="FD01 RC3 start",
    )
    _verify_ancestor(repo, base_head, "HEAD", label="FD01 base -> HEAD")
    _verify_ancestor(
        repo,
        FD01_RC1_START_HEAD,
        "HEAD",
        label="FD01 RC1 start -> HEAD",
    )
    _verify_ancestor(
        repo,
        FD01_RC2_START_HEAD,
        "HEAD",
        label="FD01 RC2 start -> HEAD",
    )
    _verify_ancestor(
        repo,
        FD01_RC3_START_HEAD,
        "HEAD",
        label="FD01 RC3 start -> HEAD",
    )
    _verify_no_merges(repo, base_head, "HEAD", label="the FD01 slice")

    changed = _changed_paths(repo, base_head)
    _verify_exact_paths(
        actual=changed,
        expected=FD01_ALLOWLIST,
        label="FD01 aggregate",
    )
    rc2_changed = _changed_paths(repo, FD01_RC2_START_HEAD)
    _verify_exact_paths(
        actual=rc2_changed,
        expected=FD01_RC2_ALLOWLIST,
        label="FD01 RC2 incremental",
    )
    rc3_changed = _changed_paths(repo, FD01_RC3_START_HEAD)
    _verify_exact_paths(
        actual=rc3_changed,
        expected=FD01_RC3_ALLOWLIST,
        label="FD01 RC3 incremental",
    )

    test_nodes = _verify_fd01_test_nodes(repo)
    resolved = _verify_common_freezes(repo, base_head=base_head)
    for ref_label, ref in (("base", base_head), ("HEAD", "HEAD")):
        value = _object(
            repo,
            f"{ref}:software/conflict_analysis/domain/services/project_definitions.py",
        )
        if value != PINNED_PROJECT_DEFINITIONS_BLOB:
            raise VerificationError(
                "pinned project_definitions_blob mismatch at "
                f"{ref_label}: expected {PINNED_PROJECT_DEFINITIONS_BLOB}, got {value}"
            )
    resolved["project_definitions_blob"] = PINNED_PROJECT_DEFINITIONS_BLOB
    _verify_frozen_paths(
        repo,
        base_head=base_head,
        paths=COMMON_FROZEN_PATHS
        + ("software/conflict_analysis/domain/services/project_definitions.py",),
        slice_name="FD01",
    )

    return {
        "allowlist_result": "PASS",
        "slice": "FD01",
        "base_head": base_head,
        "base_tree": base_tree,
        "rc1_start_head": FD01_RC1_START_HEAD,
        "rc1_start_tree": FD01_RC1_START_TREE,
        "rc1_start_is_ancestor": True,
        "rc2_start_head": FD01_RC2_START_HEAD,
        "rc2_start_tree": FD01_RC2_START_TREE,
        "rc2_start_is_ancestor": True,
        "rc3_start_head": FD01_RC3_START_HEAD,
        "rc3_start_tree": FD01_RC3_START_TREE,
        "rc3_start_is_ancestor": True,
        "changed_paths": sorted(changed),
        "rc2_incremental_changed_paths": sorted(rc2_changed),
        "rc3_incremental_changed_paths": sorted(rc3_changed),
        "test_class": FD01_TEST_CLASS,
        "test_nodes": list(test_nodes),
        "test_node_count": len(test_nodes),
        "freeze": resolved,
        "migration_filenames_unchanged": True,
        "totals": SLICE_TOTALS["FD01"],
        "sqlite_skips": [list(item) for item in BASELINE_SQLITE_SKIPS],
        "fd05_path_contract_predeclared": sorted(FD05_ALLOWLIST),
        "fd05_exact_base_pin": "EXTERNAL_MAIN_ORACLE_REQUIRED",
    }


def verify_fd05(
    repo: Path,
    *,
    base_head: str,
    base_tree: str,
    accepted_head: str,
    accepted_tree: str,
) -> dict[str, object]:
    pin_status = _verify_external_fd01_pin(
        slice_name="FD05",
        base_head=base_head,
        base_tree=base_tree,
        accepted_head=accepted_head,
        accepted_tree=accepted_tree,
    )
    resolved_accepted = _git(
        repo,
        "rev-parse",
        "--verify",
        f"{accepted_head}^{{commit}}",
    )
    if resolved_accepted != accepted_head:
        raise VerificationError(
            "FD05 external accepted HEAD does not resolve to the exact commit"
        )
    if _object(repo, f"{accepted_head}^{{tree}}") != accepted_tree:
        raise VerificationError(
            "FD05 external accepted TREE does not match its accepted HEAD"
        )
    if _object(repo, f"{FD01_BASE_HEAD}^{{tree}}") != FD01_BASE_TREE:
        raise VerificationError("accepted C0 tree does not match its pinned HEAD")
    _verify_pinned_start(
        repo,
        head=FD01_RC2_START_HEAD,
        tree=FD01_RC2_START_TREE,
        label="FD01 RC2 start",
    )
    _verify_pinned_start(
        repo,
        head=FD01_RC3_START_HEAD,
        tree=FD01_RC3_START_TREE,
        label="FD01 RC3 start",
    )
    _verify_ancestor(
        repo,
        FD01_BASE_HEAD,
        base_head,
        label="accepted C0 -> external FD01 base",
    )
    _verify_ancestor(
        repo,
        FD01_RC2_START_HEAD,
        base_head,
        label="FD01 RC2 start -> external FD01 base",
    )
    _verify_ancestor(
        repo,
        FD01_RC3_START_HEAD,
        base_head,
        label="FD01 RC3 start -> external FD01 base",
    )
    _verify_ancestor(repo, base_head, "HEAD", label="external FD01 base -> FD05 HEAD")
    _verify_no_merges(
        repo,
        FD01_BASE_HEAD,
        base_head,
        label="the accepted FD01 lineage",
    )
    _verify_no_merges(repo, base_head, "HEAD", label="the FD05 slice")

    base_aggregate_changed = _committed_changed_paths(
        repo,
        FD01_BASE_HEAD,
        base_head,
    )
    _verify_exact_paths(
        actual=base_aggregate_changed,
        expected=FD01_ALLOWLIST,
        label="external FD01 base aggregate",
    )
    base_post_rc2_changed = _committed_changed_paths(
        repo,
        FD01_RC2_START_HEAD,
        base_head,
    )
    _verify_bounded_paths(
        actual=base_post_rc2_changed,
        required=FD01_RC2_ALLOWLIST,
        allowed=FD01_ALLOWLIST,
        label="external FD01 base post-RC2",
    )
    changed = _changed_paths(repo, base_head)
    _verify_exact_paths(
        actual=changed,
        expected=FD05_ALLOWLIST,
        label="FD05",
    )
    base_project_definitions_blob = _object(
        repo,
        f"{base_head}:software/conflict_analysis/domain/services/project_definitions.py",
    )
    if base_project_definitions_blob != PINNED_PROJECT_DEFINITIONS_BLOB:
        raise VerificationError(
            "FD05 external base project_definitions blob does not retain the FD01 pin"
        )
    if _git(
        repo,
        "ls-tree",
        "--name-only",
        base_head,
        "--",
        FD05_TEST_MODULE.as_posix(),
    ):
        raise VerificationError(
            "FD05 write-reconciliation test module must be absent at the external base"
        )

    fd01_test_nodes = _verify_fd01_test_nodes(repo)
    portable_nodes, postgresql_nodes = _verify_fd05_test_nodes(repo)
    resolved = _verify_common_freezes(repo, base_head=base_head)
    fd05_frozen_paths = COMMON_FROZEN_PATHS + (WORKFLOW_PATH, VERIFIER_PATH)
    _verify_frozen_paths(
        repo,
        base_head=base_head,
        paths=fd05_frozen_paths,
        slice_name="FD05",
    )
    for path in (WORKFLOW_PATH, VERIFIER_PATH):
        if _object(repo, f"{base_head}:{path}") != _object(repo, f"HEAD:{path}"):
            raise VerificationError(f"FD05 inherited gate changed: {path}")

    return {
        "allowlist_result": "PASS",
        "slice": "FD05",
        "base_head": base_head,
        "base_tree": base_tree,
        "fd01_accepted_head": accepted_head,
        "fd01_accepted_tree": accepted_tree,
        "FD05_BASE_PIN": pin_status,
        "base_head_tree_relation": "PASS",
        "base_is_descendant_of_rc2_start": True,
        "base_is_descendant_of_rc3_start": True,
        "base_aggregate_changed_paths": sorted(base_aggregate_changed),
        "base_post_rc2_changed_paths": sorted(base_post_rc2_changed),
        "base_post_rc2_path_bounds": "PASS",
        "base_project_definitions_blob": base_project_definitions_blob,
        "write_reconciliation_test_module_absent_at_base": True,
        "changed_paths": sorted(changed),
        "retained_fd01_test_class": FD01_TEST_CLASS,
        "retained_fd01_test_nodes": list(fd01_test_nodes),
        "retained_fd01_test_node_count": len(fd01_test_nodes),
        "portable_test_class": FD05_PORTABLE_TEST_CLASS,
        "portable_test_nodes": list(portable_nodes),
        "portable_test_node_count": len(portable_nodes),
        "postgresql_test_class": FD05_POSTGRESQL_TEST_CLASS,
        "postgresql_test_nodes": list(postgresql_nodes),
        "postgresql_test_node_count": len(postgresql_nodes),
        "freeze": resolved,
        "inherited_workflow_verifier_frozen": True,
        "migration_filenames_unchanged": True,
        "totals": SLICE_TOTALS["FD05"],
        "sqlite_skips": [list(item) for item in FD05_SQLITE_SKIPS],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", choices=("FD01", "FD05"), default="FD01")
    parser.add_argument("--base-head")
    parser.add_argument("--base-tree")
    parser.add_argument("--fd01-accepted-head")
    parser.add_argument("--fd01-accepted-tree")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--self-check",
        "--self-check-contracts",
        dest="self_check_contracts",
        action="store_true",
        help="verify both predeclared slice contracts without repository or network access",
    )
    args = parser.parse_args(argv)
    try:
        if args.self_check_contracts:
            result = _contract_self_check()
        else:
            if args.slice == "FD05":
                if not args.base_head or not args.base_tree:
                    raise VerificationError(
                        "FD05 requires event/live --base-head and --base-tree"
                    )
                _verify_external_fd01_pin(
                    slice_name="FD05",
                    base_head=args.base_head,
                    base_tree=args.base_tree,
                    accepted_head=args.fd01_accepted_head,
                    accepted_tree=args.fd01_accepted_tree,
                )
            repo = _repo_root(args.repo.resolve())
            if args.slice == "FD01":
                result = verify_fd01(
                    repo,
                    base_head=args.base_head or FD01_BASE_HEAD,
                    base_tree=args.base_tree or FD01_BASE_TREE,
                )
            else:
                result = verify_fd05(
                    repo,
                    base_head=args.base_head,
                    base_tree=args.base_tree,
                    accepted_head=args.fd01_accepted_head,
                    accepted_tree=args.fd01_accepted_tree,
                )
    except VerificationError as exc:
        result_key = (
            "contract_self_check_only"
            if args.self_check_contracts
            else "allowlist_result"
        )
        print(json.dumps({result_key: "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
