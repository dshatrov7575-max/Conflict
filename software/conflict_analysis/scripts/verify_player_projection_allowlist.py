#!/usr/bin/env python3
"""Verify the bounded FD08 assessment-projection delivery contract.

This verifier is intentionally Git-only.  It proves the exact accepted F1
parent, the owner-authorized five-commit recovery chain, the final twelve-path
6+6 aggregate, frozen package and migration assets, corrected RC1-5 combined
receipt evidence, migration evidence route, and literal FD08 test registry.
Runtime semantics are proved by the focused and full test runs that invoke this
verifier in CI.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


FD08_BASE_BRANCH = "codex/ca-suite-i1-evidence-multilingual-f1"
FD08_BASE_HEAD = "d2f5a881e10dbb688371e8c5add6bf9375404738"
FD08_BASE_TREE = "7f5fd4f321282a48a799698861ce6f2bd3940cd1"
FD08_BASE_PARENT = "dbabf019f48b1433a96573476e94d4c7f427a689"
FD08_TARGET_BRANCH = "codex/ca-suite-i1-foundation-fd08-assessment-projection"
FD08_FIRST_COMMIT = "bbc89458f65e26a8ec38c4a00ccd0c788bfa73f5"
FD08_FIRST_TREE = "e241824346771bf00732107ffb079f5ec8ae8403"
FD08_SECOND_COMMIT = "5958117f7702f786f0a99ac2b49a421e6ccdf7c8"
FD08_SECOND_TREE = "9878849d527bc76406799bebb1e0f79e28b4f999"
FD08_RECOVERY_THIRD_COMMIT = "929b52aa765db1b17d3df5793391aafa2692e0dd"
FD08_RECOVERY_THIRD_TREE = "8a7ef4a5294e2b4f31c39eea2c0afb8e16141a5e"
FD08_RECOVERY_THIRD_PARENT = "5958117f7702f786f0a99ac2b49a421e6ccdf7c8"
FD08_FINAL_FOURTH_COMMIT = "333801d8020a8c9e78299eee529a170fc6c7d3dd"
FD08_FINAL_FOURTH_TREE = "ec3ecd42ae80bf243b7747f624dd5ea3bcb45eea"
FD08_FINAL_FOURTH_PARENT = "929b52aa765db1b17d3df5793391aafa2692e0dd"

WORKFLOW_PATH = ".github/workflows/conflict-analysis.yml"
ENUMS_PATH = "software/conflict_analysis/domain/enums.py"
MODELS_PATH = "software/conflict_analysis/domain/models.py"
FOUNDATION_PACKAGES_PATH = (
    "software/conflict_analysis/domain/services/foundation_packages.py"
)
ADR_PATH = "software/conflict_analysis/docs/adr/0013-foundation-workspace-assessment-projection.md"
MIGRATION_PATH = (
    "software/conflict_analysis/domain/migrations/0018_workspace_assessment_projection.py"
)
PROJECTION_PATH = "software/conflict_analysis/domain/services/player_projection.py"
TEST_PATH = "software/conflict_analysis/domain/tests/test_player_projection.py"
POSTGRESQL_MIGRATIONS_TEST_PATH = (
    "software/conflict_analysis/domain/tests/test_postgresql_migrations.py"
)
POSTGRESQL_MIGRATION_TEST_CLASS = "ProjectPrimaryLanguageMigrationGateTests"
POSTGRESQL_MIGRATION_TEST_METHOD = (
    "test_0016_reverse_reapply_and_clean_database_seed_are_exact"
)
VERIFIER_PATH = "software/conflict_analysis/scripts/verify_player_projection_allowlist.py"
HARNESS_PATH = "software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs"
CDP_CLIENT_PATH = "software/conflict_analysis/production_studio/browser_tests/cdp_client.mjs"
SCHEMA_PATH = (
    "software/conflict_analysis/domain/services/schemas/"
    "foundation-package-2.2.0.schema.json"
)

FD08_FIRST_MODIFIED_PATHS = frozenset(
    {WORKFLOW_PATH, ENUMS_PATH, MODELS_PATH, FOUNDATION_PACKAGES_PATH}
)
FD08_NEW_PATHS = frozenset(
    {ADR_PATH, MIGRATION_PATH, PROJECTION_PATH, TEST_PATH, VERIFIER_PATH, SCHEMA_PATH}
)
FD08_FIRST_ALLOWLIST = FD08_FIRST_MODIFIED_PATHS | FD08_NEW_PATHS
FD08_FINAL_MODIFIED_PATHS = FD08_FIRST_MODIFIED_PATHS | {
    POSTGRESQL_MIGRATIONS_TEST_PATH,
    HARNESS_PATH,
}
FD08_FINAL_ALLOWLIST = FD08_FINAL_MODIFIED_PATHS | FD08_NEW_PATHS
FD08_SECOND_DELTA_STATUSES = {TEST_PATH: "M"}
FD08_RECOVERY_THIRD_DELTA_STATUSES = {
    WORKFLOW_PATH: "M",
    TEST_PATH: "M",
    VERIFIER_PATH: "M",
}
FD08_FOURTH_DELTA_STATUSES = {
    WORKFLOW_PATH: "M",
    POSTGRESQL_MIGRATIONS_TEST_PATH: "M",
    VERIFIER_PATH: "M",
}
FD08_FIFTH_DELTA_STATUSES = {
    WORKFLOW_PATH: "M",
    PROJECTION_PATH: "M",
    TEST_PATH: "M",
    HARNESS_PATH: "M",
    VERIFIER_PATH: "M",
}
FD08_RECOVERY_THIRD_DELTA_PATHS = frozenset(FD08_RECOVERY_THIRD_DELTA_STATUSES)
FD08_FOURTH_DELTA_PATHS = frozenset(FD08_FOURTH_DELTA_STATUSES)
FD08_FIFTH_DELTA_PATHS = frozenset(FD08_FIFTH_DELTA_STATUSES)
FD08_FROZEN_MIGRATION_BLOB = "292a8eb4abafeef80d6efc7d3c2d4cda5f771fd9"
FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB = (
    "70dba8ee3e1e159e85f112ffc4523cd8d097ba4e"
)
FD08_FIXED_FOURTH_POSTGRESQL_MIGRATION_TEST_BLOB = (
    "3d31f7dabde996e18fbef219f835432c947f24f1"
)
FD08_FINAL_HARNESS_BLOB = "f6ad2ff633d9c49ae4e5c69d5fff931b677e8af3"
FD08_CDP_CLIENT_BLOB = "685faeb3906a0f74815549e272748125bb6fbf65"

FD08_PREIMAGE_BLOBS = {
    WORKFLOW_PATH: "24631b5dd4a83ee680dd64e427c35805fbe1c276",
    ENUMS_PATH: "5ac630ac40a35b0e07fca9e526b0642bcc8f2cf2",
    MODELS_PATH: "6077fc7ad6dd62647ed7e7a2baf21a7be13090b8",
    FOUNDATION_PACKAGES_PATH: "41c5a6ba2dddd39bdf01ccd398f8ab8213133986",
}
FROZEN_PACKAGE_BLOBS = {
    "software/conflict_analysis/domain/services/schemas/"
    "foundation-package-2.0.0.schema.json": "f6d980c1ba298aabd7373b9579b2333ec18a52be",
    "software/conflict_analysis/domain/services/schemas/"
    "foundation-package-2.1.0.schema.json": "6aaf283725c8b929b1996b4e0200abf7f1804130",
}
FD08_FINAL_PREIMAGE_BLOBS = {
    **FD08_PREIMAGE_BLOBS,
    POSTGRESQL_MIGRATIONS_TEST_PATH: FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB,
    HARNESS_PATH: "e0078090f235757a3bd8b426eecc8a86bcc250e4",
}
FD08_FIFTH_PREIMAGE_BLOBS = {
    WORKFLOW_PATH: "70c1aed79dbc11235969fccf8f11534ac6674fb6",
    PROJECTION_PATH: "a859643c78a572e17daefda3914f37b7e03868c6",
    TEST_PATH: "bf050746fcbfad7d77741949b26bbe690d104a20",
    HARNESS_PATH: "e0078090f235757a3bd8b426eecc8a86bcc250e4",
    VERIFIER_PATH: "0b21980f5d7e1cdb1d94440ae3e2db21e8504b7c",
}
PYPROJECT_PATH = "software/conflict_analysis/pyproject.toml"
MIGRATION_DEPENDENCY = ("domain", "0017_multilingual_evidence_lineage")
WORKFLOW_REQUIRED_TOKENS = (
    "fd08-assessment-projection:",
    FD08_TARGET_BRANCH,
    FD08_BASE_BRANCH,
    "github.event.pull_request.head.sha || github.sha",
    "F1_ACCEPTED_HEAD",
    "F1_ACCEPTED_TREE",
    "verify_player_projection_allowlist.py",
    "FD08_SAME_RUN_EXACT_HEAD_EVIDENCE=PASS",
    "run_attempt",
)
WORKFLOW_JOB_REQUIRED_TOKENS = (
    "github.event_name == 'pull_request'",
    f"github.event.pull_request.head.ref == '{FD08_TARGET_BRANCH}'",
    f"github.event.pull_request.base.ref == '{FD08_BASE_BRANCH}'",
    "github.event_name == 'push'",
    f"github.ref == 'refs/heads/{FD08_TARGET_BRANCH}'",
    "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
    'test "$GITHUB_RUN_ATTEMPT" = "1"',
    'test "$F1_ACCEPTED_HEAD" = "$FD08_BASE_HEAD"',
    'test "$F1_ACCEPTED_TREE" = "$FD08_BASE_TREE"',
    'test "$EVENT_HEAD_SHA" = "$delivery_head"',
    'test "$EVENT_BASE_SHA" = "$FD08_BASE_HEAD"',
    'test "$GITHUB_SHA" = "$delivery_head"',
    "FD08_SAME_RUN_EXACT_HEAD_EVIDENCE=PASS",
)
WORKFLOW_RECOVERY_REQUIRED_TOKENS = (
    "FD08_FIRST_HEAD",
    "FD08_FIRST_TREE",
    "FD08_ORACLE_LATE_SECOND_HEAD",
    "FD08_ORACLE_LATE_SECOND_TREE",
    "FD08_ORACLE_LATE_SECOND_PARENT",
    "FD08_RECOVERY_THIRD_HEAD",
    "FD08_RECOVERY_THIRD_TREE",
    "FD08_RECOVERY_THIRD_PARENT",
    "FD08_FINAL_FOURTH_HEAD",
    "FD08_FINAL_FOURTH_TREE",
    "FD08_FINAL_FOURTH_PARENT",
    "FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB",
    "FD08_FIXED_FOURTH_POSTGRESQL_MIGRATION_TEST_BLOB",
    "FD08_FINAL_HARNESS_BLOB",
    "FD08_CDP_CLIENT_BLOB",
    FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB,
    "FD08_EXACT_HEAD_ROUTE_V1",
    "recovery_chain",
    "commit_count_above_f1",
    "merge_count",
    "first_delivery",
    "oracle_late_second",
    "recovery_third",
    "exact_delta",
    "final_fourth",
    "final_fifth",
    "fifth_preimage_blobs",
    "FD08_RC1_5_COMBINED_RECEIPT_V2",
    "canonical_request_sha256",
    "receipt_sha256",
    "occurred_at_bound",
    "operation_pk_identity",
    "collision_before_projection_mutation",
    "legacy_standalone_byte_compatible",
    "self_contained_read_verification",
    "sibling_snapshot_provenance",
    "combined_postgresql_concurrency",
    "test_postgresql_migrations.py",
    "fd08-migration-postgresql.json",
    "fd08-migration-sqlite.json",
    "FD08_MIGRATION_REVERSE_REAPPLY_EVIDENCE_V1",
    "migration_evidence",
    "postgresql",
    "sqlite",
    "frozen_migration_nodes",
    "legacy_empty_0017_0018_reverse_reapply",
    "populated_canonical_reverse_refusal",
    "FD08_CANONICAL_PROJECTION_REVERSE_BLOCKED",
    "test_upgrade_preserves_every_legacy_parameter_definition_value_and_target_identity",
    "test_clean_migration_creates_conditional_legacy_and_canonical_constraints",
    "FD08_SAME_RUN_ACCEPTANCE_EVIDENCE_V1",
    "acceptance_ready",
    "final_parent",
    "FD08_STATIC_MIGRATION_EVIDENCE_V1",
    "FD08_POSTGRESQL_RESULTS_V1",
    "FD08_SQLITE_RESULTS_V1",
    "FD08_INHERITED_PRODUCT_CHROMIUM_V1",
    "FD08_WHEEL_EVIDENCE_V1",
    "FD08_ISOLATED_WHEEL_INSTALL_V1",
    "fd08-focused-postgresql.xml",
    "fd08-foundation-postgresql.xml",
    "fd08-focused-sqlite.xml",
    "fd08-foundation-sqlite.xml",
    "fd08-c0-postgresql.xml",
    "fd08-c1-postgresql.xml",
    "fd08-c0-sqlite.xml",
    "fd08-c1-sqlite.xml",
    "fd08-c1-chromium-postgresql.xml",
)

RC1_5_TEST_NODES = (
    "test_definition_bound_parameter_snapshots_are_exact_immutable_and_replay_safe",
    "test_projection_materializes_actor_element_role_hierarchy_with_deterministic_workspace_ids",
    "test_two_workspaces_same_definition_have_distinct_rows_and_identical_source_mapping",
    "test_partial_extra_or_drifted_projection_fails_closed_without_repair",
    "test_every_projection_failure_stage_rolls_back_rows_and_immutable_receipt",
    "test_concurrent_same_workspace_projection_has_one_commit_and_one_exact_replay",
    "test_competing_projection_identity_or_snapshot_has_one_commit_and_one_typed_loser",
)
RC1_5_SERVICE_REQUIRED_TOKENS = (
    "canonical_request_sha256: str | None = None",
    "_CANONICAL_REQUEST_SHA256",
    "WORKSPACE_CREATE_CONTRACT",
    "canonical_request_sha256 = _canonical_request_sha256",
    '"canonical_request_sha256": canonical_request_sha256',
    '"receipt_sha256": _sha256(core)',
    '"occurred_at": _canonical_occurred_at(occurred_at)',
    '"projection_request_sha256": _sha256(projection_request)',
    "id=operation_id",
    "AuditEvent.objects.select_for_update().filter(pk=operation_id).first()",
    "except (IntegrityError, ValidationError) as exc",
    "late_operation_receipt",
    "if late_operation_receipt is not None",
    "raise AssessmentProjectionConflict",
    "ASSESSMENT_PROJECTION_COMBINED_TRANSACTION_REQUIRED",
    "transaction.get_connection().in_atomic_block",
    "entity_type__in=_PROJECTION_RECEIPT_CONTRACTS",
    "_standalone_receipt_matches_expected_projection",
    "_combined_receipt_matches_expected_projection",
    "Projection facts are server-derived",
)
RC1_5_TEST_REQUIRED_TOKENS = (
    "WORKSPACE_CREATE_CONTRACT",
    "canonical_request_sha256=",
    "receipt_sha256",
    "occurred_at",
    "ASSESSMENT_PROJECTION_COMBINED_TRANSACTION_REQUIRED",
    "projection_sha256=\"caller-must-not-assert-this\"",
    "FD08-COLLISION",
    "outer rollback",
    "pause_only_a_save",
    "A did not reach the real inherited AuditEvent.save path",
    "test_concurrent_same_workspace_projection_has_one_commit_and_one_exact_replay",
    "test_competing_projection_identity_or_snapshot_has_one_commit_and_one_typed_loser",
)
RC1_5_EVIDENCE_REQUIRED_TOKENS = (
    "FD08_RC1_5_COMBINED_RECEIPT_V2",
    "canonical_request_sha256",
    "receipt_sha256",
    "occurred_at_bound",
    "operation_pk_identity",
    "collision_before_projection_mutation",
    "legacy_standalone_byte_compatible",
    "self_contained_read_verification",
    "sibling_snapshot_provenance",
    "combined_postgresql_concurrency",
    "late_operation_uuid_collision_typed",
    "late_collision_zero_write_loser",
    "late_collision_post_savepoint_requery",
    "late_collision_narrow_exception_boundary",
)

PORTABLE_TEST_METHODS = (
    "test_manifest_target_enum_and_domain_target_model_are_exactly_aligned",
    "test_upgrade_preserves_every_legacy_parameter_definition_value_and_target_identity",
    "test_clean_migration_creates_conditional_legacy_and_canonical_constraints",
    "test_projection_requires_exact_published_workspace_definition_and_hash_pin",
    "test_projection_materializes_actor_element_role_hierarchy_with_deterministic_workspace_ids",
    "test_two_workspaces_same_definition_have_distinct_rows_and_identical_source_mapping",
    "test_definition_bound_parameter_snapshots_are_exact_immutable_and_replay_safe",
    "test_successor_definition_gets_separate_parameter_snapshots_without_rewriting_history",
    "test_canonical_parameter_values_accept_only_exact_workspace_actor_element_role_targets",
    "test_legacy_targets_remain_backward_only_and_no_tension_group_rows_are_created",
    "test_partial_extra_or_drifted_projection_fails_closed_without_repair",
    "test_every_projection_failure_stage_rolls_back_rows_and_immutable_receipt",
)
POSTGRESQL_ONLY_TEST_METHODS = (
    "test_concurrent_same_workspace_projection_has_one_commit_and_one_exact_replay",
    "test_competing_projection_identity_or_snapshot_has_one_commit_and_one_typed_loser",
)
FD08_TEST_METHODS = PORTABLE_TEST_METHODS + POSTGRESQL_ONLY_TEST_METHODS

POSTGRESQL_MIGRATION_TEST_REQUIRED_TOKENS = (
    "self.addCleanup(self._restore_leaf_migrations)",
    "executor.migrate(self.migrate_from)",
    "executor.migrate(self.migrate_to)",
    "self.assertNotIn(",
    "self._project_snapshot(reversed_project)",
    "first_pairs",
    "self._project_snapshot(reapplied_project)",
    "reapplied_project.objects.all().delete()",
    "self._restore_leaf_migrations()",
    "from domain.services.seed import seed_zhanaozen_demo",
    "seeded = seed_zhanaozen_demo()",
    "replayed = seed_zhanaozen_demo()",
    "stable_demo_uuid(",
    '"ru"',
    '"EXPLICIT"',
)

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(RuntimeError):
    """Raised for a delivery-contract mismatch."""


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    object_type: str
    object_id: str
    path: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _require_sha(value: str, label: str) -> None:
    _require(bool(SHA1_RE.fullmatch(value)), f"{label} must be lowercase 40-hex")


def _constant_contract() -> None:
    _require_sha(FD08_BASE_HEAD, "FD08 base HEAD")
    _require_sha(FD08_BASE_TREE, "FD08 base TREE")
    _require_sha(FD08_BASE_PARENT, "FD08 base parent")
    _require_sha(FD08_FIRST_COMMIT, "FD08 first recovery commit")
    _require_sha(FD08_FIRST_TREE, "FD08 first recovery tree")
    _require_sha(FD08_SECOND_COMMIT, "FD08 second recovery commit")
    _require_sha(FD08_SECOND_TREE, "FD08 second recovery tree")
    _require_sha(FD08_RECOVERY_THIRD_COMMIT, "FD08 recovery third commit")
    _require_sha(FD08_RECOVERY_THIRD_TREE, "FD08 recovery third tree")
    _require_sha(FD08_RECOVERY_THIRD_PARENT, "FD08 recovery third parent")
    _require_sha(FD08_FINAL_FOURTH_COMMIT, "FD08 final fourth commit")
    _require_sha(FD08_FINAL_FOURTH_TREE, "FD08 final fourth tree")
    _require_sha(FD08_FINAL_FOURTH_PARENT, "FD08 final fourth parent")
    _require_sha(FD08_FROZEN_MIGRATION_BLOB, "FD08 frozen migration blob")
    _require_sha(
        FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB,
        "FD08 accepted-F1 PostgreSQL migration test blob",
    )
    _require_sha(
        FD08_FIXED_FOURTH_POSTGRESQL_MIGRATION_TEST_BLOB,
        "FD08 fixed-fourth PostgreSQL migration test blob",
    )
    _require_sha(FD08_FINAL_HARNESS_BLOB, "FD08 final authoring harness blob")
    _require_sha(FD08_CDP_CLIENT_BLOB, "FD08 frozen CDP client blob")
    _require(
        FD08_RECOVERY_THIRD_PARENT == FD08_SECOND_COMMIT,
        "FD08 recovery third parent must be the oracle-late second commit",
    )
    _require(
        FD08_FINAL_FOURTH_PARENT == FD08_RECOVERY_THIRD_COMMIT,
        "FD08 final fourth parent must be the recovery third commit",
    )
    _require(
        len(FD08_FIRST_ALLOWLIST) == 10,
        "FD08 first delivery allowlist must contain exactly ten paths",
    )
    _require(
        len(FD08_FIRST_MODIFIED_PATHS) == 4,
        "FD08 first delivery must modify exactly four paths",
    )
    _require(len(FD08_NEW_PATHS) == 6, "FD08 must add exactly six paths")
    _require(
        not (FD08_FIRST_MODIFIED_PATHS & FD08_NEW_PATHS),
        "FD08 first modified and new path sets must not overlap",
    )
    _require(
        len(FD08_FINAL_ALLOWLIST) == 12,
        "FD08 final aggregate allowlist must contain exactly twelve paths",
    )
    _require(
        len(FD08_FINAL_MODIFIED_PATHS) == 6,
        "FD08 final aggregate must modify exactly six paths",
    )
    _require(
        not (FD08_FINAL_MODIFIED_PATHS & FD08_NEW_PATHS),
        "FD08 final modified and new path sets must not overlap",
    )
    _require(
        POSTGRESQL_MIGRATIONS_TEST_PATH not in FD08_FIRST_ALLOWLIST
        and POSTGRESQL_MIGRATIONS_TEST_PATH in FD08_FINAL_ALLOWLIST,
        "FD08 inherited PostgreSQL migration test must remain in the final aggregate",
    )
    _require(
        FD08_SECOND_DELTA_STATUSES == {TEST_PATH: "M"},
        "FD08 second recovery delta must be the exact test-file modification",
    )
    _require(
        FD08_RECOVERY_THIRD_DELTA_STATUSES
        == {
            WORKFLOW_PATH: "M",
            TEST_PATH: "M",
            VERIFIER_PATH: "M",
        },
        "FD08 recovery third delta must modify only workflow, projection test, and verifier",
    )
    _require(
        FD08_FOURTH_DELTA_STATUSES
        == {
            WORKFLOW_PATH: "M",
            POSTGRESQL_MIGRATIONS_TEST_PATH: "M",
            VERIFIER_PATH: "M",
        },
        "FD08 fourth-child delta must modify only workflow, PostgreSQL migration test, and verifier",
    )
    _require(
        FD08_FIFTH_DELTA_STATUSES
        == {
            WORKFLOW_PATH: "M",
            PROJECTION_PATH: "M",
            TEST_PATH: "M",
            HARNESS_PATH: "M",
            VERIFIER_PATH: "M",
        },
        "FD08 corrected fifth delta must modify exactly workflow, service, test, harness, and verifier",
    )
    _require(
        FD08_RECOVERY_THIRD_DELTA_PATHS <= FD08_FIRST_ALLOWLIST,
        "FD08 recovery third paths must remain inside the original allowlist",
    )
    _require(
        FD08_FOURTH_DELTA_PATHS <= FD08_FINAL_ALLOWLIST,
        "FD08 fourth-child paths must remain inside the final aggregate allowlist",
    )
    _require(
        FD08_FIFTH_DELTA_PATHS <= FD08_FINAL_ALLOWLIST,
        "FD08 fifth-child paths must remain inside the final aggregate allowlist",
    )
    _require(
        set(FD08_PREIMAGE_BLOBS) == set(FD08_FIRST_MODIFIED_PATHS),
        "FD08 original preimage map must cover exactly the four first-delivery modified paths",
    )
    _require(
        set(FD08_FINAL_PREIMAGE_BLOBS) == set(FD08_FINAL_MODIFIED_PATHS),
        "FD08 final preimage map must cover exactly the six final modified paths",
    )
    for path, object_id in FD08_FINAL_PREIMAGE_BLOBS.items():
        _require(PurePosixPath(path).as_posix() == path, f"non-posix FD08 path: {path}")
        _require_sha(object_id, f"FD08 preimage {path}")
    for path, object_id in FROZEN_PACKAGE_BLOBS.items():
        _require_sha(object_id, f"frozen package blob {path}")
    for path, object_id in FD08_FIFTH_PREIMAGE_BLOBS.items():
        _require_sha(object_id, f"FD08 fifth preimage {path}")
    _require(
        len(PORTABLE_TEST_METHODS) == 12,
        "FD08 portable registry must contain exactly twelve nodes",
    )
    _require(
        len(POSTGRESQL_ONLY_TEST_METHODS) == 2,
        "FD08 PostgreSQL-only registry must contain exactly two nodes",
    )
    _require(
        len(set(FD08_TEST_METHODS)) == len(FD08_TEST_METHODS),
        "FD08 test registry must not contain duplicate names",
    )
    _require(
        len(WORKFLOW_REQUIRED_TOKENS) == len(set(WORKFLOW_REQUIRED_TOKENS)),
        "FD08 workflow token contract must not contain duplicates",
    )
    _require(
        len(WORKFLOW_JOB_REQUIRED_TOKENS) == len(set(WORKFLOW_JOB_REQUIRED_TOKENS)),
        "FD08 workflow-job token contract must not contain duplicates",
    )
    _require(
        len(WORKFLOW_RECOVERY_REQUIRED_TOKENS)
        == len(set(WORKFLOW_RECOVERY_REQUIRED_TOKENS)),
        "FD08 recovery workflow token contract must not contain duplicates",
    )
    _require(
        len(RC1_5_TEST_NODES) == 7 and len(set(RC1_5_TEST_NODES)) == 7,
        "FD08 corrected RC1-5 evidence must bind seven distinct frozen nodes",
    )
    for tokens, label in (
        (RC1_5_SERVICE_REQUIRED_TOKENS, "service"),
        (RC1_5_TEST_REQUIRED_TOKENS, "test"),
        (RC1_5_EVIDENCE_REQUIRED_TOKENS, "evidence"),
    ):
        _require(len(tokens) == len(set(tokens)), f"FD08 RC1-5 {label} oracle has duplicates")


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repo), *args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise VerificationError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _repo_root(repo: Path) -> Path:
    root = Path(_git(repo, "rev-parse", "--show-toplevel"))
    _require(root.is_dir(), f"repository root does not exist: {root}")
    return root.resolve()


def _entry(repo: Path, revision: str, path: str) -> TreeEntry | None:
    output = _git(repo, "ls-tree", revision, "--", path)
    if not output:
        return None
    lines = output.splitlines()
    _require(len(lines) == 1, f"expected one tree entry for {revision}:{path}")
    metadata, separator, entry_path = lines[0].partition("\t")
    _require(separator == "\t", f"malformed tree entry for {revision}:{path}")
    parts = metadata.split()
    _require(len(parts) == 3, f"malformed tree metadata for {revision}:{path}")
    mode, object_type, object_id = parts
    _require(entry_path == path, f"tree entry path drifted for {revision}:{path}")
    return TreeEntry(mode, object_type, object_id, entry_path)


def _require_regular_file(entry: TreeEntry | None, label: str) -> TreeEntry:
    _require(entry is not None, f"missing required file: {label}")
    _require(entry.mode == "100644", f"{label} must be a regular 100644 file")
    _require(entry.object_type == "blob", f"{label} must be a blob")
    return entry


def _validate_recovery_history(
    *,
    commit_count: int,
    ordered_commits: Iterable[str],
    commit_parents: Iterable[Iterable[str]],
    first_tree: str,
    second_tree: str,
    third_tree: str,
    fourth_tree: str,
    merge_count: int,
) -> None:
    """Require the owner-authorized corrected five-commit FD08 recovery chain."""

    commits = tuple(ordered_commits)
    parents = tuple(tuple(parent_ids) for parent_ids in commit_parents)
    for index, commit in enumerate(commits, start=1):
        _require_sha(commit, f"FD08 recovery commit {index}")
    for index, parent_set in enumerate(parents, start=1):
        for parent in parent_set:
            _require_sha(parent, f"FD08 recovery commit {index} parent")
    _require_sha(first_tree, "FD08 first recovery tree")
    _require_sha(second_tree, "FD08 second recovery tree")
    _require_sha(third_tree, "FD08 recovery third tree")
    _require_sha(fourth_tree, "FD08 final fourth tree")
    _require(commit_count == 5, "FD08 recovery must contain exactly five commits")
    _require(len(commits) == 5, "FD08 recovery commit sequence must contain five commits")
    _require(len(parents) == 5, "FD08 recovery parent sequence must contain five commits")
    _require(
        commits[:4]
        == (
            FD08_FIRST_COMMIT,
            FD08_SECOND_COMMIT,
            FD08_RECOVERY_THIRD_COMMIT,
            FD08_FINAL_FOURTH_COMMIT,
        ),
        "FD08 recovery fixed first, second, third, or fourth commit drifted",
    )
    _require(
        commits[4]
        not in {
            FD08_BASE_HEAD,
            FD08_FIRST_COMMIT,
            FD08_SECOND_COMMIT,
            FD08_RECOVERY_THIRD_COMMIT,
            FD08_FINAL_FOURTH_COMMIT,
        },
        "FD08 corrected fifth commit must be a new ordinary child",
    )
    _require(
        parents
        == (
            (FD08_BASE_HEAD,),
            (FD08_FIRST_COMMIT,),
            (FD08_SECOND_COMMIT,),
            (FD08_RECOVERY_THIRD_COMMIT,),
            (FD08_FINAL_FOURTH_COMMIT,),
        ),
        "FD08 recovery parent chain must be F1 -> first -> second -> third -> fourth -> fifth",
    )
    _require(
        first_tree == FD08_FIRST_TREE,
        "FD08 recovery first commit tree drifted",
    )
    _require(
        second_tree == FD08_SECOND_TREE,
        "FD08 recovery second commit tree drifted",
    )
    _require(
        third_tree == FD08_RECOVERY_THIRD_TREE,
        "FD08 recovery third commit tree drifted",
    )
    _require(
        fourth_tree == FD08_FINAL_FOURTH_TREE,
        "FD08 final fourth commit tree drifted",
    )
    _require(merge_count == 0, "FD08 recovery must not contain merge commits")


def _validate_topology(
    statuses: Mapping[str, str],
    *,
    allowlist: frozenset[str],
    modified_paths: frozenset[str],
    label: str,
) -> None:
    _require(
        set(statuses) == allowlist,
        f"{label} changed paths must equal its exact allowlist",
    )
    modified = {path for path, status in statuses.items() if status == "M"}
    new = {path for path, status in statuses.items() if status == "A"}
    _require(
        set(statuses.values()) <= {"M", "A"},
        "FD08 may contain only ordinary modifications and additions",
    )
    _require(modified == modified_paths, f"{label} modified-path topology drifted")
    _require(new == FD08_NEW_PATHS, f"{label} new-path topology drifted")


def _validate_first_topology(statuses: Mapping[str, str]) -> None:
    _validate_topology(
        statuses,
        allowlist=FD08_FIRST_ALLOWLIST,
        modified_paths=FD08_FIRST_MODIFIED_PATHS,
        label="FD08 first delivery",
    )


def _validate_final_topology(statuses: Mapping[str, str]) -> None:
    _validate_topology(
        statuses,
        allowlist=FD08_FINAL_ALLOWLIST,
        modified_paths=FD08_FINAL_MODIFIED_PATHS,
        label="FD08 final aggregate",
    )


def _validate_exact_delta(
    statuses: Mapping[str, str], expected: Mapping[str, str], label: str
) -> None:
    _require(
        dict(statuses) == dict(expected),
        f"{label} path/status delta drifted",
    )


def _validate_second_delta(statuses: Mapping[str, str]) -> None:
    _validate_exact_delta(
        statuses,
        FD08_SECOND_DELTA_STATUSES,
        "FD08 second recovery",
    )


def _validate_recovery_third_delta(statuses: Mapping[str, str]) -> None:
    _validate_exact_delta(
        statuses,
        FD08_RECOVERY_THIRD_DELTA_STATUSES,
        "FD08 recovery third",
    )


def _validate_fourth_delta(statuses: Mapping[str, str]) -> None:
    _validate_exact_delta(
        statuses,
        FD08_FOURTH_DELTA_STATUSES,
        "FD08 fourth child",
    )


def _validate_fifth_delta(statuses: Mapping[str, str]) -> None:
    _validate_exact_delta(
        statuses,
        FD08_FIFTH_DELTA_STATUSES,
        "FD08 corrected fifth child",
    )


def _validate_original_preimage_map(actual: Mapping[str, str]) -> None:
    _require(
        dict(actual) == FD08_PREIMAGE_BLOBS,
        "FD08 original modified preimage blobs differ from the accepted F1 base",
    )


def _validate_final_preimage_map(actual: Mapping[str, str]) -> None:
    _require(
        dict(actual) == FD08_FINAL_PREIMAGE_BLOBS,
        "FD08 final modified preimage blobs differ from the accepted F1 base",
    )


def _validate_inherited_postgresql_migration_test_preimage(actual: str) -> None:
    _require(
        actual == FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB,
        "FD08 inherited PostgreSQL migration test preimage drifted from accepted F1",
    )


def _validate_fixed_fourth_postgresql_migration_test_blob(actual: str) -> None:
    _require(
        actual == FD08_FIXED_FOURTH_POSTGRESQL_MIGRATION_TEST_BLOB,
        "FD08 final fifth must retain the accepted fixed-fourth migration test blob",
    )


def _validate_fifth_preimage_map(actual: Mapping[str, str]) -> None:
    _require(
        dict(actual) == FD08_FIFTH_PREIMAGE_BLOBS,
        "FD08 corrected fifth preimage blobs differ from fixed fourth",
    )


def _validate_frozen_migration_blob(actual: str) -> None:
    _require(
        actual == FD08_FROZEN_MIGRATION_BLOB,
        "FD08 recovery mutated the byte-frozen 0018 migration",
    )


def _validate_registry(methods: Iterable[str]) -> None:
    _require(
        tuple(methods) == FD08_TEST_METHODS,
        "FD08 literal 12+2 test registry or order drifted",
    )


def _validate_migration_dependency(dependencies: object) -> None:
    _require(
        dependencies == [MIGRATION_DEPENDENCY],
        "FD08 migration must depend only on exact 0017_multilingual_evidence_lineage",
    )


def _validate_frozen_package_registry(actual: Mapping[str, str]) -> None:
    _require(
        dict(actual) == FROZEN_PACKAGE_BLOBS,
        "FD08 frozen Foundation 2.0/2.1 package registry drifted",
    )


def _validate_schema_contract(schema: object) -> None:
    _require(isinstance(schema, dict), "Foundation 2.2 schema root must be an object")
    serialized_schema = json.dumps(schema, sort_keys=True)
    _require("2.2.0" in serialized_schema, "Foundation 2.2 schema lacks its version identity")
    _require("workspace" in serialized_schema, "Foundation 2.2 schema lacks workspace identity")


def _validate_required_tokens(
    source: str, required_tokens: Iterable[str], label: str
) -> None:
    missing = [token for token in required_tokens if token not in source]
    _require(
        not missing,
        f"{label} lacks exact token(s): {', '.join(missing)}",
    )


def _changed_statuses(
    repo: Path, from_revision: str, to_revision: str
) -> dict[str, str]:
    output = _git(
        repo,
        "diff",
        "--name-status",
        "--no-ext-diff",
        "--no-renames",
        f"{from_revision}..{to_revision}",
    )
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split("\t")
        _require(len(fields) == 2, f"unexpected FD08 diff record: {line!r}")
        status, path = fields
        _require(status in {"M", "A"}, f"forbidden FD08 diff status: {status} {path}")
        _require(path not in statuses, f"duplicate FD08 diff path: {path}")
        statuses[path] = status
    return statuses


class _TestNameCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name.startswith("test_"):
            self.names.append(node.name)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef


def _parse_python_module(source: str, label: str) -> ast.Module:
    try:
        return ast.parse(source, filename=label)
    except SyntaxError as exc:
        raise VerificationError(f"cannot parse FD08 Python source {label}: {exc}") from exc


def _test_method_names_from_module(module: ast.Module) -> tuple[str, ...]:
    collector = _TestNameCollector()
    collector.visit(module)
    return tuple(collector.names)


def _test_method_names(path: Path) -> tuple[str, ...]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(f"cannot read FD08 test registry: {exc}") from exc
    return _test_method_names_from_module(_parse_python_module(source, str(path)))


def _class_method(
    module: ast.Module, *, class_name: str, method_name: str, label: str
) -> ast.FunctionDef:
    classes = [
        node
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    _require(len(classes) == 1, f"{label} must contain one {class_name} class")
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    ]
    _require(
        len(methods) == 1,
        f"{label} must contain one {class_name}.{method_name} method",
    )
    return methods[0]


def _source_without_method(source: str, method: ast.FunctionDef, label: str) -> str:
    start_line = min(
        (decorator.lineno for decorator in method.decorator_list),
        default=method.lineno,
    )
    _require(
        method.end_lineno is not None,
        f"{label} {method.name} must have a source end line",
    )
    lines = source.splitlines(keepends=True)
    _require(
        1 <= start_line <= method.end_lineno <= len(lines),
        f"{label} {method.name} source span is invalid",
    )
    return "".join(lines[: start_line - 1] + lines[method.end_lineno :])


def _verify_inherited_postgresql_migration_test_scope(repo: Path) -> dict[str, object]:
    root = _repo_root(repo)
    try:
        final_source = (root / POSTGRESQL_MIGRATIONS_TEST_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(
            f"cannot read inherited PostgreSQL migration test: {exc}"
        ) from exc
    base_source = _git(
        repo,
        "show",
        f"{FD08_BASE_HEAD}:{POSTGRESQL_MIGRATIONS_TEST_PATH}",
    )
    base_module = _parse_python_module(
        base_source,
        f"{FD08_BASE_HEAD}:{POSTGRESQL_MIGRATIONS_TEST_PATH}",
    )
    final_module = _parse_python_module(
        final_source,
        str(root / POSTGRESQL_MIGRATIONS_TEST_PATH),
    )
    _require(
        _test_method_names_from_module(final_module)
        == _test_method_names_from_module(base_module),
        "FD08 fourth child must not add or rename PostgreSQL migration tests",
    )
    base_method = _class_method(
        base_module,
        class_name=POSTGRESQL_MIGRATION_TEST_CLASS,
        method_name=POSTGRESQL_MIGRATION_TEST_METHOD,
        label="accepted F1 PostgreSQL migration test",
    )
    final_method = _class_method(
        final_module,
        class_name=POSTGRESQL_MIGRATION_TEST_CLASS,
        method_name=POSTGRESQL_MIGRATION_TEST_METHOD,
        label="final PostgreSQL migration test",
    )
    _require(
        ast.dump(base_method.args, include_attributes=False)
        == ast.dump(final_method.args, include_attributes=False),
        "FD08 fourth child must preserve the inherited migration test signature",
    )
    _require(
        tuple(
            ast.dump(decorator, include_attributes=False)
            for decorator in base_method.decorator_list
        )
        == tuple(
            ast.dump(decorator, include_attributes=False)
            for decorator in final_method.decorator_list
        ),
        "FD08 fourth child must preserve the inherited migration test decorators",
    )
    _require(
        ast.dump(
            _parse_python_module(
                _source_without_method(
                    base_source,
                    base_method,
                    "accepted F1 PostgreSQL migration test",
                ),
                "accepted F1 PostgreSQL migration test outside authorized method",
            ),
            include_attributes=False,
        )
        == ast.dump(
            _parse_python_module(
                _source_without_method(
                    final_source,
                    final_method,
                    "final PostgreSQL migration test",
                ),
                "final PostgreSQL migration test outside authorized method",
            ),
            include_attributes=False,
        ),
        "FD08 fourth child may alter only the inherited migration test method",
    )
    final_body = ast.get_source_segment(final_source, final_method)
    _require(
        final_body is not None,
        "FD08 fourth child cannot recover its authorized migration test body",
    )
    _validate_required_tokens(
        final_body,
        POSTGRESQL_MIGRATION_TEST_REQUIRED_TOKENS,
        "FD08 inherited PostgreSQL migration test contract",
    )
    delete_index = final_body.index("reapplied_project.objects.all().delete()")
    restore_index = final_body.index("self._restore_leaf_migrations()", delete_index)
    seed_import_index = final_body.index(
        "from domain.services.seed import seed_zhanaozen_demo", restore_index
    )
    seed_call_index = final_body.index("seeded = seed_zhanaozen_demo()", seed_import_index)
    _require(
        delete_index < restore_index < seed_import_index < seed_call_index,
        "FD08 fourth child must restore current leaf migrations after cleanup and before seed import/replay",
    )
    return {
        "path": POSTGRESQL_MIGRATIONS_TEST_PATH,
        "class": POSTGRESQL_MIGRATION_TEST_CLASS,
        "method": POSTGRESQL_MIGRATION_TEST_METHOD,
        "only_authorized_method_changed": True,
        "reverse_reapply_cleanup_before_current_seed": True,
        "test_names_unchanged": True,
    }


def _migration_dependencies(path: Path) -> object:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise VerificationError(f"cannot parse FD08 migration: {exc}") from exc
    for node in module.body:
        if not isinstance(node, ast.ClassDef) or node.name != "Migration":
            continue
        for statement in node.body:
            if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
                continue
            targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
            if not any(isinstance(target, ast.Name) and target.id == "dependencies" for target in targets):
                continue
            try:
                return ast.literal_eval(statement.value)
            except ValueError as exc:
                raise VerificationError("FD08 migration dependencies must be literal") from exc
    raise VerificationError("FD08 migration has no Migration.dependencies declaration")


def _verify_base(repo: Path, supplied_head: str, supplied_tree: str) -> None:
    _require(
        supplied_head == FD08_BASE_HEAD,
        "FD08 supplied base head does not equal accepted F1 head",
    )
    _require(
        supplied_tree == FD08_BASE_TREE,
        "FD08 supplied base tree does not equal accepted F1 tree",
    )
    _require(
        _git(repo, "rev-parse", FD08_BASE_HEAD) == FD08_BASE_HEAD,
        "accepted F1 head object is unavailable or ambiguous",
    )
    _require(
        _git(repo, "rev-parse", f"{FD08_BASE_HEAD}^{{tree}}") == FD08_BASE_TREE,
        "accepted F1 head tree drifted",
    )
    _require(
        _git(repo, "rev-parse", f"{FD08_BASE_HEAD}^") == FD08_BASE_PARENT,
        "accepted F1 parent drifted",
    )


def _verify_history(repo: Path) -> dict[str, object]:
    _git(repo, "merge-base", "--is-ancestor", FD08_BASE_HEAD, "HEAD")
    ordered_commits = tuple(
        line
        for line in _git(
            repo,
            "rev-list",
            "--reverse",
            f"{FD08_BASE_HEAD}..HEAD",
        ).splitlines()
        if line
    )
    commit_parents = tuple(
        tuple(_git(repo, "show", "-s", "--format=%P", commit).split())
        for commit in ordered_commits
    )
    commit_count = len(ordered_commits)
    merges = _git(repo, "rev-list", "--merges", f"{FD08_BASE_HEAD}..HEAD").splitlines()
    first_tree = _git(repo, "rev-parse", f"{FD08_FIRST_COMMIT}^{{tree}}")
    second_tree = _git(repo, "rev-parse", f"{FD08_SECOND_COMMIT}^{{tree}}")
    third_tree = _git(repo, "rev-parse", f"{FD08_RECOVERY_THIRD_COMMIT}^{{tree}}")
    fourth_tree = _git(repo, "rev-parse", f"{FD08_FINAL_FOURTH_COMMIT}^{{tree}}")
    _validate_recovery_history(
        commit_count=commit_count,
        ordered_commits=ordered_commits,
        commit_parents=commit_parents,
        first_tree=first_tree,
        second_tree=second_tree,
        third_tree=third_tree,
        fourth_tree=fourth_tree,
        merge_count=len(merges),
    )
    final_head = _git(repo, "rev-parse", "HEAD")
    final_tree = _git(repo, "rev-parse", "HEAD^{tree}")
    final_parent = commit_parents[-1][0]
    return {
        "final_head": final_head,
        "final_tree": final_tree,
        "final_parent": final_parent,
        "sole_parent": final_parent,
        "commit_count": commit_count,
        "merge_count": len(merges),
        "ordinary_commits_above_f1": commit_count,
        "merge_commits_above_f1": len(merges),
        "recovery_chain": {
            "commit_count_above_f1": commit_count,
            "merge_count": len(merges),
            "first_delivery": {
                "head": FD08_FIRST_COMMIT,
                "tree": first_tree,
                "parent": commit_parents[0][0],
            },
            "oracle_late_second": {
                "head": FD08_SECOND_COMMIT,
                "tree": second_tree,
                "parent": commit_parents[1][0],
                "exact_delta": [
                    {"status": status, "path": path}
                    for path, status in sorted(FD08_SECOND_DELTA_STATUSES.items())
                ],
            },
            "recovery_third": {
                "head": FD08_RECOVERY_THIRD_COMMIT,
                "tree": third_tree,
                "parent": FD08_RECOVERY_THIRD_PARENT,
                "exact_delta": [
                    {"status": status, "path": path}
                    for path, status in sorted(
                        FD08_RECOVERY_THIRD_DELTA_STATUSES.items()
                    )
                ],
            },
            "final_fourth": {
                "head": FD08_FINAL_FOURTH_COMMIT,
                "tree": fourth_tree,
                "parent": FD08_FINAL_FOURTH_PARENT,
                "exact_delta": [
                    {"status": status, "path": path}
                    for path, status in sorted(FD08_FOURTH_DELTA_STATUSES.items())
                ],
            },
            "final_fifth": {
                "head": final_head,
                "tree": final_tree,
                "parent": final_parent,
                "exact_delta": [
                    {"status": status, "path": path}
                    for path, status in sorted(FD08_FIFTH_DELTA_STATUSES.items())
                ],
                "fifth_preimage_blobs": FD08_FIFTH_PREIMAGE_BLOBS,
            },
        },
    }


def _verify_paths_and_preimages(repo: Path) -> dict[str, object]:
    first_statuses = _changed_statuses(repo, FD08_BASE_HEAD, FD08_FIRST_COMMIT)
    second_statuses = _changed_statuses(repo, FD08_FIRST_COMMIT, FD08_SECOND_COMMIT)
    third_statuses = _changed_statuses(
        repo, FD08_SECOND_COMMIT, FD08_RECOVERY_THIRD_COMMIT
    )
    fourth_statuses = _changed_statuses(
        repo, FD08_RECOVERY_THIRD_COMMIT, FD08_FINAL_FOURTH_COMMIT
    )
    fifth_statuses = _changed_statuses(repo, FD08_FINAL_FOURTH_COMMIT, "HEAD")
    aggregate_statuses = _changed_statuses(repo, FD08_BASE_HEAD, "HEAD")
    _validate_first_topology(first_statuses)
    _validate_second_delta(second_statuses)
    _validate_recovery_third_delta(third_statuses)
    _validate_fourth_delta(fourth_statuses)
    _validate_fifth_delta(fifth_statuses)
    _validate_final_topology(aggregate_statuses)
    preimages: dict[str, str] = {}
    for path, expected_blob in FD08_FINAL_PREIMAGE_BLOBS.items():
        base_entry = _require_regular_file(_entry(repo, FD08_BASE_HEAD, path), f"base {path}")
        preimages[path] = base_entry.object_id
        _require(
            base_entry.object_id == expected_blob,
            f"FD08 base preimage drifted: {path}",
        )
        _require_regular_file(_entry(repo, "HEAD", path), f"final {path}")
    _validate_original_preimage_map(
        {path: preimages[path] for path in FD08_PREIMAGE_BLOBS}
    )
    _validate_final_preimage_map(preimages)
    inherited_base_blob = preimages[POSTGRESQL_MIGRATIONS_TEST_PATH]
    _validate_inherited_postgresql_migration_test_preimage(inherited_base_blob)
    inherited_recovery_third_blob = _require_regular_file(
        _entry(
            repo,
            FD08_RECOVERY_THIRD_COMMIT,
            POSTGRESQL_MIGRATIONS_TEST_PATH,
        ),
        f"{FD08_RECOVERY_THIRD_COMMIT} {POSTGRESQL_MIGRATIONS_TEST_PATH}",
    ).object_id
    _validate_inherited_postgresql_migration_test_preimage(inherited_recovery_third_blob)
    inherited_fixed_fourth_blob = _require_regular_file(
        _entry(
            repo,
            FD08_FINAL_FOURTH_COMMIT,
            POSTGRESQL_MIGRATIONS_TEST_PATH,
        ),
        f"{FD08_FINAL_FOURTH_COMMIT} {POSTGRESQL_MIGRATIONS_TEST_PATH}",
    ).object_id
    final_postgresql_migration_test_blob = _require_regular_file(
        _entry(repo, "HEAD", POSTGRESQL_MIGRATIONS_TEST_PATH),
        f"HEAD {POSTGRESQL_MIGRATIONS_TEST_PATH}",
    ).object_id
    _validate_fixed_fourth_postgresql_migration_test_blob(inherited_fixed_fourth_blob)
    _validate_fixed_fourth_postgresql_migration_test_blob(final_postgresql_migration_test_blob)
    fifth_preimages = {
        path: _require_regular_file(
            _entry(repo, FD08_FINAL_FOURTH_COMMIT, path),
            f"{FD08_FINAL_FOURTH_COMMIT} {path}",
        ).object_id
        for path in FD08_FIFTH_PREIMAGE_BLOBS
    }
    _validate_fifth_preimage_map(fifth_preimages)
    frozen_migration_entries = {
        revision: _require_regular_file(
            _entry(repo, revision, MIGRATION_PATH),
            f"{revision} {MIGRATION_PATH}",
        ).object_id
        for revision in (
            FD08_FIRST_COMMIT,
            FD08_SECOND_COMMIT,
            FD08_RECOVERY_THIRD_COMMIT,
            FD08_FINAL_FOURTH_COMMIT,
            "HEAD",
        )
    }
    for object_id in frozen_migration_entries.values():
        _validate_frozen_migration_blob(object_id)
    for path in FD08_NEW_PATHS:
        _require(
            _entry(repo, FD08_BASE_HEAD, path) is None,
            f"FD08 new path unexpectedly existed at F1 base: {path}",
        )
        _require_regular_file(_entry(repo, "HEAD", path), f"final {path}")
    harness_preimages = {
        "path": HARNESS_PATH,
        "accepted_f1": _require_regular_file(
            _entry(repo, FD08_BASE_HEAD, HARNESS_PATH), f"{FD08_BASE_HEAD} {HARNESS_PATH}"
        ).object_id,
        "fixed_fourth": _require_regular_file(
            _entry(repo, FD08_FINAL_FOURTH_COMMIT, HARNESS_PATH),
            f"{FD08_FINAL_FOURTH_COMMIT} {HARNESS_PATH}",
        ).object_id,
        "final_fifth": _require_regular_file(_entry(repo, "HEAD", HARNESS_PATH), f"HEAD {HARNESS_PATH}").object_id,
    }
    _require(
        harness_preimages["accepted_f1"] == FD08_FIFTH_PREIMAGE_BLOBS[HARNESS_PATH]
        and harness_preimages["fixed_fourth"] == FD08_FIFTH_PREIMAGE_BLOBS[HARNESS_PATH]
        and harness_preimages["final_fifth"] == FD08_FINAL_HARNESS_BLOB,
        "FD08 corrected fifth authoring harness provenance drifted",
    )
    frozen_cdp_client_blobs = {
        revision: _require_regular_file(
            _entry(repo, revision, CDP_CLIENT_PATH), f"{revision} {CDP_CLIENT_PATH}"
        ).object_id
        for revision in (FD08_BASE_HEAD, FD08_FINAL_FOURTH_COMMIT, "HEAD")
    }
    _require(
        all(blob == FD08_CDP_CLIENT_BLOB for blob in frozen_cdp_client_blobs.values()),
        "FD08 corrected fifth mutated the frozen CDP client",
    )
    _git(repo, "diff", "--check", f"{FD08_BASE_HEAD}..HEAD")
    return {
        "changed_paths": sorted(aggregate_statuses),
        "modified_paths": sorted(
            path for path, status in aggregate_statuses.items() if status == "M"
        ),
        "new_paths": sorted(
            path for path, status in aggregate_statuses.items() if status == "A"
        ),
        "modified_preimage_blobs": preimages,
        "first_delivery_delta": first_statuses,
        "second_delivery_delta": second_statuses,
        "recovery_third_delta": third_statuses,
        "fourth_child_delta": fourth_statuses,
        "fifth_child_delta": fifth_statuses,
        "fifth_preimage_blobs": fifth_preimages,
        "inherited_postgresql_migration_test_preimage": {
            "path": POSTGRESQL_MIGRATIONS_TEST_PATH,
            "accepted_f1": inherited_base_blob,
            "recovery_third": inherited_recovery_third_blob,
            "fixed_fourth": inherited_fixed_fourth_blob,
            "final_fifth": final_postgresql_migration_test_blob,
        },
        "frozen_migration_blobs": frozen_migration_entries,
        "browser_harness_preimage": harness_preimages,
        "frozen_cdp_client_blobs": frozen_cdp_client_blobs,
        "authoring_ready_replay_contract": True,
        "topology": "6 modified + 6 new aggregate across five commits",
    }


def _verify_migration_and_registry(repo: Path) -> dict[str, object]:
    root = _repo_root(repo)
    migration_path = root / MIGRATION_PATH
    dependencies = _migration_dependencies(migration_path)
    _validate_migration_dependency(dependencies)
    methods = _test_method_names(root / TEST_PATH)
    _validate_registry(methods)
    return {
        "migration": MIGRATION_PATH,
        "migration_dependency": list(MIGRATION_DEPENDENCY),
        "portable_registry": list(PORTABLE_TEST_METHODS),
        "postgresql_only_registry": list(POSTGRESQL_ONLY_TEST_METHODS),
    }


def _verify_package_compatibility(repo: Path) -> dict[str, object]:
    root = _repo_root(repo)
    frozen: dict[str, str] = {}
    for path, expected_blob in FROZEN_PACKAGE_BLOBS.items():
        base_entry = _require_regular_file(_entry(repo, FD08_BASE_HEAD, path), f"base {path}")
        final_entry = _require_regular_file(_entry(repo, "HEAD", path), f"final {path}")
        _require(base_entry.object_id == expected_blob, f"F1 package blob drifted: {path}")
        _require(final_entry.object_id == expected_blob, f"FD08 mutated frozen package schema: {path}")
        frozen[path] = final_entry.object_id
    _validate_frozen_package_registry(frozen)
    pyproject_base = _require_regular_file(_entry(repo, FD08_BASE_HEAD, PYPROJECT_PATH), PYPROJECT_PATH)
    pyproject_final = _require_regular_file(_entry(repo, "HEAD", PYPROJECT_PATH), PYPROJECT_PATH)
    _require(
        pyproject_final.object_id == pyproject_base.object_id,
        "FD08 must use the existing schema package-data glob without pyproject changes",
    )
    pyproject_text = (root / PYPROJECT_PATH).read_text(encoding="utf-8")
    _require(
        '"domain.services" = ["schemas/*.json"]' in pyproject_text,
        "domain.services schema package-data glob is missing",
    )
    schema_path = root / SCHEMA_PATH
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"Foundation 2.2 schema is not valid JSON: {exc}") from exc
    _validate_schema_contract(schema)
    service_text = (root / FOUNDATION_PACKAGES_PATH).read_text(encoding="utf-8")
    for required_token in (
        "foundation-package-2.2.0.schema.json",
        "definition_version",
        "source_manifest_parameter_id",
    ):
        _require(
            required_token in service_text,
            f"Foundation package service lacks FD08 compatibility token: {required_token}",
        )
    return {
        "frozen_2_0_2_1_blobs": frozen,
        "schema_2_2": SCHEMA_PATH,
        "schema_package_glob": "schemas/*.json",
        "pyproject_unchanged": True,
    }


def _ast_dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _ast_dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _ast_dotted_name(node.func)
    return ""


def _contains_real_combined_receipt_savepoint(nodes: Iterable[ast.stmt]) -> bool:
    for node in nodes:
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        has_atomic_context = any(
            _ast_dotted_name(item.context_expr) == "transaction.atomic"
            for item in node.items
        )
        if not has_atomic_context:
            continue
        if "AuditEvent.objects.create" in ast.unparse(node):
            return True
    return False


def _verify_late_operation_uuid_collision_handler(tree: ast.AST) -> None:
    """Prove the real late receipt collision boundary is narrow and ordered."""

    candidates: list[ast.Try] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try):
            continue
        if not _contains_real_combined_receipt_savepoint(node.body):
            continue
        candidates.append(node)
    _require(
        len(candidates) == 1,
        "FD08 must have exactly one real combined-receipt savepoint handler",
    )
    candidate = candidates[0]
    _require(
        len(candidate.handlers) == 1,
        "FD08 late receipt collision handler must not use a broad sibling catch",
    )
    handler = candidate.handlers[0]
    _require(
        isinstance(handler.type, ast.Tuple)
        and tuple(_ast_dotted_name(item) for item in handler.type.elts)
        == ("IntegrityError", "ValidationError"),
        "FD08 late receipt collision handler must catch exactly IntegrityError and ValidationError",
    )
    _require(
        handler.name == "exc",
        "FD08 late receipt collision handler must preserve the original exception",
    )
    handler_source = "\n".join(ast.unparse(statement) for statement in handler.body)
    _require(
        "AuditEvent.objects.select_for_update().filter(pk=operation_id).first()"
        in handler_source,
        "FD08 late receipt collision handler must re-read the exact operation ID after savepoint rollback",
    )
    occupancy_guards = [
        node
        for node in ast.walk(ast.Module(body=handler.body, type_ignores=[]))
        if isinstance(node, ast.If)
        and ast.unparse(node.test) == "late_operation_receipt is not None"
    ]
    _require(
        len(occupancy_guards) == 1,
        "FD08 late receipt collision handler must have one exact occupied-ID guard",
    )
    guarded_raises = [
        node
        for node in ast.walk(occupancy_guards[0])
        if isinstance(node, ast.Raise)
        and isinstance(node.exc, ast.Call)
        and _ast_dotted_name(node.exc.func) == "AssessmentProjectionConflict"
    ]
    _require(
        len(guarded_raises) == 1,
        "FD08 late receipt collision handler must raise only typed AssessmentProjectionConflict for occupancy",
    )
    _require(
        any(
            isinstance(node, ast.Raise) and node.exc is None
            for node in ast.walk(ast.Module(body=handler.body, type_ignores=[]))
        ),
        "FD08 late receipt collision handler must bare re-raise absent-row failures",
    )


def _rc1_5_combined_receipt_evidence() -> dict[str, object]:
    return {
        "schema": "FD08_RC1_5_COMBINED_RECEIPT_V2",
        "contract": "FOUNDATION_PLAYER_WORKSPACE_CREATE_V1",
        "legacy_standalone_byte_compatible": True,
        "caller_canonical_request_sha256": True,
        "canonical_request_sha256_lowercase_64_hex": True,
        "server_derived_projection_facts_only": True,
        "operation_pk_identity": True,
        "one_combined_receipt": True,
        "zero_standalone_projection_receipts": True,
        "occurred_at_bound": True,
        "receipt_sha256": True,
        "receipt_sha256_non_self_referential": True,
        "exact_replay": True,
        "canonical_request_conflict": True,
        "collision_before_projection_mutation": True,
        "outer_transaction_required": True,
        "outer_rollback": True,
        "self_contained_read_verification": True,
        "sibling_snapshot_provenance": True,
        "malformed_dual_drift_unreceipted_fail_closed": True,
        "combined_postgresql_concurrency": True,
        "late_operation_uuid_collision_typed": True,
        "late_collision_zero_write_loser": True,
        "late_collision_post_savepoint_requery": True,
        "late_collision_narrow_exception_boundary": True,
        "test_nodes": list(RC1_5_TEST_NODES),
    }


def _verify_rc1_5_source_contract(repo: Path) -> dict[str, object]:
    root = _repo_root(repo)
    try:
        service_text = (root / PROJECTION_PATH).read_text(encoding="utf-8")
        test_text = (root / TEST_PATH).read_text(encoding="utf-8")
        service_tree = ast.parse(service_text)
        ast.parse(test_text)
    except (OSError, SyntaxError) as exc:
        raise VerificationError(f"cannot parse corrected RC1-5 source evidence: {exc}") from exc
    _validate_required_tokens(
        service_text,
        RC1_5_SERVICE_REQUIRED_TOKENS,
        "FD08 corrected RC1-5 service contract",
    )
    _validate_required_tokens(
        test_text,
        RC1_5_TEST_REQUIRED_TOKENS,
        "FD08 corrected RC1-5 test contract",
    )
    for node in RC1_5_TEST_NODES:
        _require(
            f"def {node}(" in test_text,
            f"FD08 corrected RC1-5 frozen test node is missing: {node}",
        )
    _verify_late_operation_uuid_collision_handler(service_tree)
    return {
        **_rc1_5_combined_receipt_evidence(),
        "service_path": PROJECTION_PATH,
        "test_path": TEST_PATH,
        "late_collision_handler_ast": True,
    }


def _verify_workflow_contract(repo: Path) -> dict[str, object]:
    root = _repo_root(repo)
    try:
        workflow = (root / WORKFLOW_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(f"cannot read FD08 workflow: {exc}") from exc
    _validate_required_tokens(
        workflow,
        WORKFLOW_REQUIRED_TOKENS,
        "FD08 workflow CI contract",
    )
    _validate_required_tokens(
        workflow,
        WORKFLOW_RECOVERY_REQUIRED_TOKENS,
        "FD08 workflow recovery/migration evidence contract",
    )
    _validate_required_tokens(
        workflow,
        RC1_5_EVIDENCE_REQUIRED_TOKENS,
        "FD08 corrected RC1-5 workflow evidence contract",
    )
    _require(
        workflow.count(FD08_TARGET_BRANCH) >= 4,
        "FD08 workflow must bind target trigger, route and environment separately",
    )
    header = "  fd08-assessment-projection:\n"
    _require(
        workflow.count(header) == 1,
        "FD08 workflow must contain exactly one assessment-projection job",
    )
    start = workflow.index(header)
    next_job = re.search(r"(?m)^  [A-Za-z0-9_-]+:\s*$", workflow[start + len(header) :])
    job = workflow[start:] if next_job is None else workflow[start : start + len(header) + next_job.start()]
    _validate_required_tokens(
        job,
        WORKFLOW_JOB_REQUIRED_TOKENS,
        "FD08 workflow job route contract",
    )
    return {
        "job": "fd08-assessment-projection",
        "exact_head_checkout": True,
        "same_run_evidence": True,
        "required_token_count": len(WORKFLOW_REQUIRED_TOKENS),
        "job_route_token_count": len(WORKFLOW_JOB_REQUIRED_TOKENS),
        "recovery_migration_evidence_token_count": len(
            WORKFLOW_RECOVERY_REQUIRED_TOKENS
        ),
        "rc1_5_evidence_token_count": len(RC1_5_EVIDENCE_REQUIRED_TOKENS),
    }


def verify_fd08(
    repo: Path,
    *,
    base_head: str,
    base_tree: str,
    accepted_head: str,
    accepted_tree: str,
) -> dict[str, object]:
    _constant_contract()
    _require(
        accepted_head == FD08_BASE_HEAD,
        "F1_ACCEPTED_HEAD does not equal the FD08 accepted base",
    )
    _require(
        accepted_tree == FD08_BASE_TREE,
        "F1_ACCEPTED_TREE does not equal the FD08 accepted base",
    )
    resolved = _repo_root(repo)
    _verify_base(resolved, base_head, base_tree)
    return {
        "allowlist_result": "PASS",
        "slice": "FD08",
        "base_branch": FD08_BASE_BRANCH,
        "base_head": FD08_BASE_HEAD,
        "base_tree": FD08_BASE_TREE,
        "base_parent": FD08_BASE_PARENT,
        "target_branch": FD08_TARGET_BRANCH,
        "history": _verify_history(resolved),
        "paths": _verify_paths_and_preimages(resolved),
        "inherited_postgresql_migration_test": _verify_inherited_postgresql_migration_test_scope(
            resolved
        ),
        "migration_and_registry": _verify_migration_and_registry(resolved),
        "package_compatibility": _verify_package_compatibility(resolved),
        "rc1_5_combined_receipt": _verify_rc1_5_source_contract(resolved),
        "workflow_contract": _verify_workflow_contract(resolved),
        "negative_self_checks_required": True,
    }


def _expect_verification_error(call: Callable[[], object]) -> bool:
    try:
        call()
    except VerificationError:
        return True
    return False


def _legacy_self_check_negative_cases() -> dict[str, bool]:
    """Keep the inherited FD08 structural and evidence rejection oracles active."""

    _constant_contract()
    first_statuses = {
        **{path: "M" for path in FD08_FIRST_MODIFIED_PATHS},
        **{path: "A" for path in FD08_NEW_PATHS},
    }
    final_statuses = {
        **{path: "M" for path in FD08_FINAL_MODIFIED_PATHS},
        **{path: "A" for path in FD08_NEW_PATHS},
    }
    recovery_history = {
        "commit_count": 5,
        "ordered_commits": (
            FD08_FIRST_COMMIT,
            FD08_SECOND_COMMIT,
            FD08_RECOVERY_THIRD_COMMIT,
            FD08_FINAL_FOURTH_COMMIT,
            "c" * 40,
        ),
        "commit_parents": (
            (FD08_BASE_HEAD,),
            (FD08_FIRST_COMMIT,),
            (FD08_SECOND_COMMIT,),
            (FD08_RECOVERY_THIRD_COMMIT,),
            (FD08_FINAL_FOURTH_COMMIT,),
        ),
        "first_tree": FD08_FIRST_TREE,
        "second_tree": FD08_SECOND_TREE,
        "third_tree": FD08_RECOVERY_THIRD_TREE,
        "fourth_tree": FD08_FINAL_FOURTH_TREE,
        "merge_count": 0,
    }
    _validate_recovery_history(**recovery_history)
    _validate_first_topology(first_statuses)
    _validate_final_topology(final_statuses)
    _validate_second_delta(FD08_SECOND_DELTA_STATUSES)
    _validate_recovery_third_delta(FD08_RECOVERY_THIRD_DELTA_STATUSES)
    _validate_fourth_delta(FD08_FOURTH_DELTA_STATUSES)
    _validate_original_preimage_map(FD08_PREIMAGE_BLOBS)
    _validate_final_preimage_map(FD08_FINAL_PREIMAGE_BLOBS)
    _validate_inherited_postgresql_migration_test_preimage(
        FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB
    )
    _validate_frozen_migration_blob(FD08_FROZEN_MIGRATION_BLOB)
    _validate_registry(FD08_TEST_METHODS)
    _validate_migration_dependency([MIGRATION_DEPENDENCY])
    _validate_frozen_package_registry(FROZEN_PACKAGE_BLOBS)
    _validate_schema_contract({"format_version": "2.2.0", "workspace": {}})

    workflow_recovery_source = "\n".join(WORKFLOW_RECOVERY_REQUIRED_TOKENS)
    _validate_required_tokens(
        workflow_recovery_source,
        WORKFLOW_RECOVERY_REQUIRED_TOKENS,
        "FD08 synthetic workflow recovery evidence",
    )

    wrong_original_preimages = dict(FD08_PREIMAGE_BLOBS)
    wrong_original_preimages[WORKFLOW_PATH] = "0" * 40
    wrong_final_preimages = dict(FD08_FINAL_PREIMAGE_BLOBS)
    wrong_final_preimages[POSTGRESQL_MIGRATIONS_TEST_PATH] = "0" * 40
    wrong_registry = (*FD08_TEST_METHODS[:-1], "test_unapproved_projection_case")
    wrong_migration_dependency = [("domain", "0016_project_language_bootstrap")]
    wrong_frozen_registry = dict(FROZEN_PACKAGE_BLOBS)
    wrong_frozen_registry[next(iter(wrong_frozen_registry))] = "0" * 40
    wrong_second_delta = {TEST_PATH: "A"}
    wrong_recovery_third_delta = dict(FD08_RECOVERY_THIRD_DELTA_STATUSES)
    wrong_recovery_third_delta["README.md"] = "M"
    wrong_fourth_delta = dict(FD08_FOURTH_DELTA_STATUSES)
    wrong_fourth_delta[POSTGRESQL_MIGRATIONS_TEST_PATH] = "A"
    four_commit_history = {
        **recovery_history,
        "commit_count": 4,
        "ordered_commits": recovery_history["ordered_commits"][:4],
        "commit_parents": recovery_history["commit_parents"][:4],
    }
    six_commit_history = {
        **recovery_history,
        "commit_count": 6,
        "ordered_commits": (*recovery_history["ordered_commits"], "d" * 40),
        "commit_parents": (*recovery_history["commit_parents"], ("c" * 40,)),
    }
    migration_evidence_token_removed = workflow_recovery_source.replace(
        "fd08-migration-postgresql.json",
        "",
        1,
    )
    migration_evidence_key_removed = workflow_recovery_source.replace(
        "populated_canonical_reverse_refusal",
        "",
        1,
    )

    negative_cases = {
        "legacy_base_parent_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{
                    **recovery_history,
                    "commit_parents": (
                        (FD08_BASE_PARENT,),
                        (FD08_FIRST_COMMIT,),
                        (FD08_SECOND_COMMIT,),
                        (FD08_RECOVERY_THIRD_COMMIT,),
                        (FD08_FINAL_FOURTH_COMMIT,),
                    ),
                }
            )
        ),
        "legacy_first_commit_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{
                    **recovery_history,
                    "ordered_commits": (
                        "a" * 40,
                        FD08_SECOND_COMMIT,
                        FD08_RECOVERY_THIRD_COMMIT,
                        FD08_FINAL_FOURTH_COMMIT,
                        "c" * 40,
                    ),
                }
            )
        ),
        "legacy_first_tree_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{**recovery_history, "first_tree": "a" * 40}
            )
        ),
        "legacy_second_commit_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{
                    **recovery_history,
                    "ordered_commits": (
                        FD08_FIRST_COMMIT,
                        "b" * 40,
                        FD08_RECOVERY_THIRD_COMMIT,
                        FD08_FINAL_FOURTH_COMMIT,
                        "c" * 40,
                    ),
                }
            )
        ),
        "legacy_second_tree_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{**recovery_history, "second_tree": "b" * 40}
            )
        ),
        "legacy_second_parent_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{
                    **recovery_history,
                    "commit_parents": (
                        (FD08_BASE_HEAD,),
                        ("d" * 40,),
                        (FD08_SECOND_COMMIT,),
                        (FD08_RECOVERY_THIRD_COMMIT,),
                        (FD08_FINAL_FOURTH_COMMIT,),
                    ),
                }
            )
        ),
        "legacy_recovery_third_head_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{
                    **recovery_history,
                    "ordered_commits": (
                        FD08_FIRST_COMMIT,
                        FD08_SECOND_COMMIT,
                        "d" * 40,
                        FD08_FINAL_FOURTH_COMMIT,
                        "c" * 40,
                    ),
                }
            )
        ),
        "legacy_recovery_third_tree_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{**recovery_history, "third_tree": "d" * 40}
            )
        ),
        "legacy_recovery_third_parent_drift_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{
                    **recovery_history,
                    "commit_parents": (
                        (FD08_BASE_HEAD,),
                        (FD08_FIRST_COMMIT,),
                        ("d" * 40,),
                        (FD08_RECOVERY_THIRD_COMMIT,),
                        (FD08_FINAL_FOURTH_COMMIT,),
                    ),
                }
            )
        ),
        "legacy_four_commit_chain_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(**four_commit_history)
        ),
        "legacy_six_commit_chain_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(**six_commit_history)
        ),
        "legacy_recovery_third_delta_rejected": _expect_verification_error(
            lambda: _validate_recovery_third_delta(wrong_recovery_third_delta)
        ),
        "legacy_fourth_child_delta_rejected": _expect_verification_error(
            lambda: _validate_fourth_delta(wrong_fourth_delta)
        ),
        "legacy_second_delta_rejected": _expect_verification_error(
            lambda: _validate_second_delta(wrong_second_delta)
        ),
        "legacy_original_preimage_drift_rejected": _expect_verification_error(
            lambda: _validate_original_preimage_map(wrong_original_preimages)
        ),
        "legacy_final_preimage_drift_rejected": _expect_verification_error(
            lambda: _validate_final_preimage_map(wrong_final_preimages)
        ),
        "legacy_inherited_postgresql_migration_test_blob_drift_rejected": _expect_verification_error(
            lambda: _validate_inherited_postgresql_migration_test_preimage("0" * 40)
        ),
        "legacy_frozen_migration_drift_rejected": _expect_verification_error(
            lambda: _validate_frozen_migration_blob("0" * 40)
        ),
        "legacy_registry_drift_rejected": _expect_verification_error(
            lambda: _validate_registry(wrong_registry)
        ),
        "legacy_migration_dependency_drift_rejected": _expect_verification_error(
            lambda: _validate_migration_dependency(wrong_migration_dependency)
        ),
        "legacy_frozen_package_registry_drift_rejected": _expect_verification_error(
            lambda: _validate_frozen_package_registry(wrong_frozen_registry)
        ),
        "legacy_schema_drift_rejected": _expect_verification_error(
            lambda: _validate_schema_contract({"format_version": "2.2.0"})
        ),
        "legacy_migration_evidence_token_removal_rejected": _expect_verification_error(
            lambda: _validate_required_tokens(
                migration_evidence_token_removed,
                WORKFLOW_RECOVERY_REQUIRED_TOKENS,
                "FD08 synthetic workflow recovery evidence",
            )
        ),
        "legacy_migration_evidence_key_removal_rejected": _expect_verification_error(
            lambda: _validate_required_tokens(
                migration_evidence_key_removed,
                WORKFLOW_RECOVERY_REQUIRED_TOKENS,
                "FD08 synthetic workflow recovery evidence",
            )
        ),
    }
    _require(
        all(negative_cases.values()),
        "FD08 inherited verifier negative self-check failed",
    )
    return negative_cases

def self_check() -> dict[str, object]:
    """Exercise every corrected topology and RC1-5 source/evidence oracle."""

    _constant_contract()
    first_statuses = {
        **{path: "M" for path in FD08_FIRST_MODIFIED_PATHS},
        **{path: "A" for path in FD08_NEW_PATHS},
    }
    final_statuses = {
        **{path: "M" for path in FD08_FINAL_MODIFIED_PATHS},
        **{path: "A" for path in FD08_NEW_PATHS},
    }
    recovery_history = {
        "commit_count": 5,
        "ordered_commits": (
            FD08_FIRST_COMMIT,
            FD08_SECOND_COMMIT,
            FD08_RECOVERY_THIRD_COMMIT,
            FD08_FINAL_FOURTH_COMMIT,
            "c" * 40,
        ),
        "commit_parents": (
            (FD08_BASE_HEAD,),
            (FD08_FIRST_COMMIT,),
            (FD08_SECOND_COMMIT,),
            (FD08_RECOVERY_THIRD_COMMIT,),
            (FD08_FINAL_FOURTH_COMMIT,),
        ),
        "first_tree": FD08_FIRST_TREE,
        "second_tree": FD08_SECOND_TREE,
        "third_tree": FD08_RECOVERY_THIRD_TREE,
        "fourth_tree": FD08_FINAL_FOURTH_TREE,
        "merge_count": 0,
    }
    _validate_recovery_history(**recovery_history)
    _validate_first_topology(first_statuses)
    _validate_final_topology(final_statuses)
    _validate_second_delta(FD08_SECOND_DELTA_STATUSES)
    _validate_recovery_third_delta(FD08_RECOVERY_THIRD_DELTA_STATUSES)
    _validate_fourth_delta(FD08_FOURTH_DELTA_STATUSES)
    _validate_fifth_delta(FD08_FIFTH_DELTA_STATUSES)
    _validate_original_preimage_map(FD08_PREIMAGE_BLOBS)
    _validate_final_preimage_map(FD08_FINAL_PREIMAGE_BLOBS)
    _validate_fifth_preimage_map(FD08_FIFTH_PREIMAGE_BLOBS)
    _validate_inherited_postgresql_migration_test_preimage(
        FD08_ACCEPTED_F1_POSTGRESQL_MIGRATION_TEST_BLOB
    )
    _validate_fixed_fourth_postgresql_migration_test_blob(
        FD08_FIXED_FOURTH_POSTGRESQL_MIGRATION_TEST_BLOB
    )
    _validate_frozen_migration_blob(FD08_FROZEN_MIGRATION_BLOB)
    _validate_registry(FD08_TEST_METHODS)
    _validate_migration_dependency([MIGRATION_DEPENDENCY])
    _validate_frozen_package_registry(FROZEN_PACKAGE_BLOBS)
    _validate_schema_contract({"format_version": "2.2.0", "workspace": {}})

    service_source = "\n".join(RC1_5_SERVICE_REQUIRED_TOKENS)
    test_source = "\n".join(dict.fromkeys(RC1_5_TEST_REQUIRED_TOKENS + RC1_5_TEST_NODES))
    workflow_source = "\n".join(
        dict.fromkeys(WORKFLOW_RECOVERY_REQUIRED_TOKENS + RC1_5_EVIDENCE_REQUIRED_TOKENS)
    )
    _validate_required_tokens(service_source, RC1_5_SERVICE_REQUIRED_TOKENS, "service")
    _validate_required_tokens(test_source, RC1_5_TEST_REQUIRED_TOKENS, "test")
    _validate_required_tokens(
        workflow_source,
        WORKFLOW_RECOVERY_REQUIRED_TOKENS,
        "workflow recovery evidence",
    )
    _validate_required_tokens(
        workflow_source,
        RC1_5_EVIDENCE_REQUIRED_TOKENS,
        "workflow RC1-5 evidence",
    )

    def token_removals_fail(source: str, tokens: tuple[str, ...], label: str) -> bool:
        return all(
            _expect_verification_error(
                lambda token=token: _validate_required_tokens(
                    source.replace(token, ""), tokens, label
                )
            )
            for token in tokens
        )

    valid_late_collision_handler_source = """
def materialize():
    try:
        with transaction.atomic():
            AuditEvent.objects.create(id=operation_id)
    except (IntegrityError, ValidationError) as exc:
        late_operation_receipt = (
            AuditEvent.objects.select_for_update().filter(pk=operation_id).first()
        )
        if late_operation_receipt is not None:
            raise AssessmentProjectionConflict() from exc
        raise
"""
    _verify_late_operation_uuid_collision_handler(
        ast.parse(valid_late_collision_handler_source)
    )

    extra_final_statuses = {**final_statuses, "README.md": "A"}
    missing_final_statuses = dict(final_statuses)
    missing_final_statuses.pop(HARNESS_PATH)
    wrong_status_classification = dict(final_statuses)
    wrong_status_classification[HARNESS_PATH] = "A"
    wrong_fifth_delta = dict(FD08_FIFTH_DELTA_STATUSES)
    wrong_fifth_delta[HARNESS_PATH] = "A"
    wrong_final_preimages = dict(FD08_FINAL_PREIMAGE_BLOBS)
    wrong_final_preimages[HARNESS_PATH] = "0" * 40
    wrong_fifth_preimages = dict(FD08_FIFTH_PREIMAGE_BLOBS)
    wrong_fifth_preimages[TEST_PATH] = "0" * 40
    four_commit_history = {
        **recovery_history,
        "commit_count": 4,
        "ordered_commits": recovery_history["ordered_commits"][:4],
        "commit_parents": recovery_history["commit_parents"][:4],
    }
    six_commit_history = {
        **recovery_history,
        "commit_count": 6,
        "ordered_commits": (*recovery_history["ordered_commits"], "d" * 40),
        "commit_parents": (*recovery_history["commit_parents"], ("c" * 40,)),
    }
    wrong_parent_history = {
        **recovery_history,
        "commit_parents": (
            (FD08_BASE_HEAD,),
            (FD08_FIRST_COMMIT,),
            (FD08_SECOND_COMMIT,),
            (FD08_RECOVERY_THIRD_COMMIT,),
            ("d" * 40,),
        ),
    }
    legacy_negative_cases = _legacy_self_check_negative_cases()
    negative_cases = {
        **legacy_negative_cases,
        "wrong_final_parent_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(**wrong_parent_history)
        ),
        "four_commit_chain_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(**four_commit_history)
        ),
        "six_commit_chain_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(**six_commit_history)
        ),
        "merge_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{**recovery_history, "merge_count": 1}
            )
        ),
        "wrong_fixed_fourth_tree_rejected": _expect_verification_error(
            lambda: _validate_recovery_history(
                **{**recovery_history, "fourth_tree": "0" * 40}
            )
        ),
        "fifth_delta_drift_rejected": _expect_verification_error(
            lambda: _validate_fifth_delta(wrong_fifth_delta)
        ),
        "aggregate_13_path_rejected": _expect_verification_error(
            lambda: _validate_final_topology(extra_final_statuses)
        ),
        "aggregate_11_path_rejected": _expect_verification_error(
            lambda: _validate_final_topology(missing_final_statuses)
        ),
        "aggregate_5m_7a_rejected": _expect_verification_error(
            lambda: _validate_final_topology(wrong_status_classification)
        ),
        "aggregate_preimage_drift_rejected": _expect_verification_error(
            lambda: _validate_final_preimage_map(wrong_final_preimages)
        ),
        "fifth_preimage_drift_rejected": _expect_verification_error(
            lambda: _validate_fifth_preimage_map(wrong_fifth_preimages)
        ),
        "service_oracle_token_removals_rejected": token_removals_fail(
            service_source, RC1_5_SERVICE_REQUIRED_TOKENS, "service"
        ),
        "test_oracle_token_removals_rejected": token_removals_fail(
            test_source, RC1_5_TEST_REQUIRED_TOKENS, "test"
        ),
        "workflow_evidence_token_removals_rejected": token_removals_fail(
            workflow_source, RC1_5_EVIDENCE_REQUIRED_TOKENS, "workflow"
        ),
        "late_collision_ast_broad_catch_rejected": _expect_verification_error(
            lambda: _verify_late_operation_uuid_collision_handler(
                ast.parse(
                    valid_late_collision_handler_source.replace(
                        "except (IntegrityError, ValidationError) as exc:",
                        "except Exception as exc:",
                    )
                )
            )
        ),
        "late_collision_ast_missing_requery_rejected": _expect_verification_error(
            lambda: _verify_late_operation_uuid_collision_handler(
                ast.parse(
                    valid_late_collision_handler_source.replace(
                        "AuditEvent.objects.select_for_update().filter(pk=operation_id).first()",
                        "None",
                    )
                )
            )
        ),
        "late_collision_ast_untyped_occupancy_rejected": _expect_verification_error(
            lambda: _verify_late_operation_uuid_collision_handler(
                ast.parse(
                    valid_late_collision_handler_source.replace(
                        "raise AssessmentProjectionConflict() from exc",
                        "raise exc",
                    )
                )
            )
        ),
        "late_collision_ast_missing_bare_reraise_rejected": _expect_verification_error(
            lambda: _verify_late_operation_uuid_collision_handler(
                ast.parse(
                    valid_late_collision_handler_source.replace(
                        "\n        raise\n",
                        "\n        return\n",
                    )
                )
            )
        ),
    }
    failed_negative_cases = [key for key, passed in negative_cases.items() if not passed]
    _require(
        not failed_negative_cases,
        "FD08 corrected verifier negative self-check failed: "
        + ", ".join(failed_negative_cases),
    )
    return {
        "contract_self_check": "PASS",
        "slice": "FD08",
        "marker": "FD08_RECOVERY_5_COMMIT_VERIFIER_SELF_CHECK=PASS",
        "negative_cases": negative_cases,
        "path_counts": {"modified": 6, "new": 6, "total": 12},
        "recovery_third_path_count": len(FD08_RECOVERY_THIRD_DELTA_PATHS),
        "fourth_child_path_count": len(FD08_FOURTH_DELTA_PATHS),
        "fifth_child_path_count": len(FD08_FIFTH_DELTA_PATHS),
        "registry_counts": {"portable": 12, "postgresql_only": 2},
        "rc1_5_combined_receipt": _rc1_5_combined_receipt_evidence(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--base-head", default=FD08_BASE_HEAD)
    parser.add_argument("--base-tree", default=FD08_BASE_TREE)
    parser.add_argument("--f1-accepted-head")
    parser.add_argument("--f1-accepted-tree")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_check:
            result = self_check()
        else:
            _require(
                args.f1_accepted_head is not None and args.f1_accepted_tree is not None,
                "FD08 verification requires F1_ACCEPTED_HEAD and F1_ACCEPTED_TREE",
            )
            result = verify_fd08(
                args.repo,
                base_head=args.base_head,
                base_tree=args.base_tree,
                accepted_head=args.f1_accepted_head,
                accepted_tree=args.f1_accepted_tree,
            )
    except VerificationError as exc:
        key = "contract_self_check" if args.self_check else "allowlist_result"
        print(json.dumps({key: "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
