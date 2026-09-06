#!/usr/bin/env python3
"""Verify the bounded FD08 assessment-projection delivery contract.

This verifier is intentionally Git-only.  It proves the exact accepted F1
parent, the one-child linear delivery, the ten-path 4+6 delta, frozen package
assets, migration edge, and literal FD08 test registry.  Runtime semantics are
proved by the focused and full test runs that invoke this verifier in CI.
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
VERIFIER_PATH = "software/conflict_analysis/scripts/verify_player_projection_allowlist.py"
SCHEMA_PATH = (
    "software/conflict_analysis/domain/services/schemas/"
    "foundation-package-2.2.0.schema.json"
)

FD08_MODIFIED_PATHS = frozenset(
    {WORKFLOW_PATH, ENUMS_PATH, MODELS_PATH, FOUNDATION_PACKAGES_PATH}
)
FD08_NEW_PATHS = frozenset(
    {ADR_PATH, MIGRATION_PATH, PROJECTION_PATH, TEST_PATH, VERIFIER_PATH, SCHEMA_PATH}
)
FD08_ALLOWLIST = FD08_MODIFIED_PATHS | FD08_NEW_PATHS

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
    _require(len(FD08_ALLOWLIST) == 10, "FD08 allowlist must contain exactly ten paths")
    _require(len(FD08_MODIFIED_PATHS) == 4, "FD08 must modify exactly four paths")
    _require(len(FD08_NEW_PATHS) == 6, "FD08 must add exactly six paths")
    _require(
        not (FD08_MODIFIED_PATHS & FD08_NEW_PATHS),
        "FD08 modified and new path sets must not overlap",
    )
    _require(
        set(FD08_PREIMAGE_BLOBS) == set(FD08_MODIFIED_PATHS),
        "FD08 preimage map must cover exactly the four modified paths",
    )
    for path, object_id in FD08_PREIMAGE_BLOBS.items():
        _require(PurePosixPath(path).as_posix() == path, f"non-posix FD08 path: {path}")
        _require_sha(object_id, f"FD08 preimage {path}")
    for path, object_id in FROZEN_PACKAGE_BLOBS.items():
        _require_sha(object_id, f"frozen package blob {path}")
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


def _validate_history(
    *, parent_ids: Iterable[str], expected_parent: str, commit_count: int, merge_count: int
) -> None:
    parents = tuple(parent_ids)
    _require(len(parents) == 1, "FD08 final commit must have exactly one parent")
    _require(parents[0] == expected_parent, "FD08 final commit parent differs from accepted F1")
    _require(commit_count == 1, "FD08 delivery must be exactly one ordinary child of F1")
    _require(merge_count == 0, "FD08 delivery must not contain merge commits")


def _validate_topology(statuses: Mapping[str, str]) -> None:
    _require(
        set(statuses) == FD08_ALLOWLIST,
        "FD08 changed paths must equal the exact ten-path allowlist",
    )
    modified = {path for path, status in statuses.items() if status == "M"}
    new = {path for path, status in statuses.items() if status == "A"}
    _require(
        set(statuses.values()) <= {"M", "A"},
        "FD08 may contain only ordinary modifications and additions",
    )
    _require(modified == FD08_MODIFIED_PATHS, "FD08 modified-path topology drifted")
    _require(new == FD08_NEW_PATHS, "FD08 new-path topology drifted")


def _validate_preimage_map(actual: Mapping[str, str]) -> None:
    _require(
        dict(actual) == FD08_PREIMAGE_BLOBS,
        "FD08 modified preimage blobs differ from the accepted F1 base",
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


def _changed_statuses(repo: Path, base_head: str) -> dict[str, str]:
    output = _git(
        repo,
        "diff",
        "--name-status",
        "--no-ext-diff",
        "--no-renames",
        f"{base_head}..HEAD",
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


def _test_method_names(path: Path) -> tuple[str, ...]:
    try:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise VerificationError(f"cannot parse FD08 test registry: {exc}") from exc
    collector = _TestNameCollector()
    collector.visit(module)
    return tuple(collector.names)


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
    parent_ids = _git(repo, "show", "-s", "--format=%P", "HEAD").split()
    commit_count = int(_git(repo, "rev-list", "--count", f"{FD08_BASE_HEAD}..HEAD"))
    merges = _git(repo, "rev-list", "--merges", f"{FD08_BASE_HEAD}..HEAD").splitlines()
    _validate_history(
        parent_ids=parent_ids,
        expected_parent=FD08_BASE_HEAD,
        commit_count=commit_count,
        merge_count=len(merges),
    )
    return {
        "final_head": _git(repo, "rev-parse", "HEAD"),
        "final_tree": _git(repo, "rev-parse", "HEAD^{tree}"),
        "sole_parent": parent_ids[0],
        "ordinary_commits_above_f1": commit_count,
        "merge_commits_above_f1": len(merges),
    }


def _verify_paths_and_preimages(repo: Path) -> dict[str, object]:
    statuses = _changed_statuses(repo, FD08_BASE_HEAD)
    _validate_topology(statuses)
    preimages: dict[str, str] = {}
    for path, expected_blob in FD08_PREIMAGE_BLOBS.items():
        base_entry = _require_regular_file(_entry(repo, FD08_BASE_HEAD, path), f"base {path}")
        preimages[path] = base_entry.object_id
        _require(
            base_entry.object_id == expected_blob,
            f"FD08 base preimage drifted: {path}",
        )
        _require_regular_file(_entry(repo, "HEAD", path), f"final {path}")
    _validate_preimage_map(preimages)
    for path in FD08_NEW_PATHS:
        _require(
            _entry(repo, FD08_BASE_HEAD, path) is None,
            f"FD08 new path unexpectedly existed at F1 base: {path}",
        )
        _require_regular_file(_entry(repo, "HEAD", path), f"final {path}")
    _git(repo, "diff", "--check", f"{FD08_BASE_HEAD}..HEAD")
    return {
        "changed_paths": sorted(statuses),
        "modified_paths": sorted(path for path, status in statuses.items() if status == "M"),
        "new_paths": sorted(path for path, status in statuses.items() if status == "A"),
        "modified_preimage_blobs": preimages,
        "topology": "4 modified + 6 new",
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
    _require(isinstance(schema, dict), "Foundation 2.2 schema root must be an object")
    serialized_schema = json.dumps(schema, sort_keys=True)
    _require("2.2.0" in serialized_schema, "Foundation 2.2 schema lacks its version identity")
    _require("workspace" in serialized_schema, "Foundation 2.2 schema lacks workspace identity")
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


def _verify_workflow_contract(repo: Path) -> dict[str, object]:
    root = _repo_root(repo)
    try:
        workflow = (root / WORKFLOW_PATH).read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(f"cannot read FD08 workflow: {exc}") from exc
    missing = [token for token in WORKFLOW_REQUIRED_TOKENS if token not in workflow]
    _require(
        not missing,
        f"FD08 workflow lacks exact CI contract token(s): {', '.join(missing)}",
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
    missing_job_tokens = [
        token for token in WORKFLOW_JOB_REQUIRED_TOKENS if token not in job
    ]
    _require(
        not missing_job_tokens,
        "FD08 workflow job lacks exact route token(s): "
        + ", ".join(missing_job_tokens),
    )
    return {
        "job": "fd08-assessment-projection",
        "exact_head_checkout": True,
        "same_run_evidence": True,
        "required_token_count": len(WORKFLOW_REQUIRED_TOKENS),
        "job_route_token_count": len(WORKFLOW_JOB_REQUIRED_TOKENS),
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
        "migration_and_registry": _verify_migration_and_registry(resolved),
        "package_compatibility": _verify_package_compatibility(resolved),
        "workflow_contract": _verify_workflow_contract(resolved),
        "negative_self_checks_required": True,
    }


def _expect_verification_error(call: Callable[[], object]) -> bool:
    try:
        call()
    except VerificationError:
        return True
    return False


def self_check() -> dict[str, object]:
    _constant_contract()
    expected_statuses = {
        **{path: "M" for path in FD08_MODIFIED_PATHS},
        **{path: "A" for path in FD08_NEW_PATHS},
    }
    _validate_history(
        parent_ids=(FD08_BASE_HEAD,),
        expected_parent=FD08_BASE_HEAD,
        commit_count=1,
        merge_count=0,
    )
    _validate_topology(expected_statuses)
    _validate_preimage_map(FD08_PREIMAGE_BLOBS)
    _validate_registry(FD08_TEST_METHODS)
    _validate_migration_dependency([MIGRATION_DEPENDENCY])
    _validate_frozen_package_registry(FROZEN_PACKAGE_BLOBS)

    wrong_statuses = dict(expected_statuses)
    wrong_statuses["README.md"] = "A"
    missing_statuses = dict(expected_statuses)
    missing_statuses.pop(VERIFIER_PATH)
    swapped_statuses = dict(expected_statuses)
    swapped_statuses[WORKFLOW_PATH] = "A"
    wrong_preimages = dict(FD08_PREIMAGE_BLOBS)
    wrong_preimages[WORKFLOW_PATH] = "0" * 40
    wrong_registry = (*FD08_TEST_METHODS[:-1], "test_unapproved_projection_case")
    wrong_migration_dependency = [("domain", "0016_project_language_bootstrap")]
    wrong_frozen_registry = dict(FROZEN_PACKAGE_BLOBS)
    wrong_frozen_registry[next(iter(wrong_frozen_registry))] = "0" * 40
    negative_cases = {
        "wrong_parent_rejected": _expect_verification_error(
            lambda: _validate_history(
                parent_ids=(FD08_BASE_PARENT,),
                expected_parent=FD08_BASE_HEAD,
                commit_count=1,
                merge_count=0,
            )
        ),
        "merge_rejected": _expect_verification_error(
            lambda: _validate_history(
                parent_ids=(FD08_BASE_HEAD, FD08_BASE_PARENT),
                expected_parent=FD08_BASE_HEAD,
                commit_count=1,
                merge_count=1,
            )
        ),
        "extra_path_rejected": _expect_verification_error(
            lambda: _validate_topology(wrong_statuses)
        ),
        "missing_path_rejected": _expect_verification_error(
            lambda: _validate_topology(missing_statuses)
        ),
        "wrong_4_plus_6_classification_rejected": _expect_verification_error(
            lambda: _validate_topology(swapped_statuses)
        ),
        "preimage_drift_rejected": _expect_verification_error(
            lambda: _validate_preimage_map(wrong_preimages)
        ),
        "registry_drift_rejected": _expect_verification_error(
            lambda: _validate_registry(wrong_registry)
        ),
        "migration_dependency_drift_rejected": _expect_verification_error(
            lambda: _validate_migration_dependency(wrong_migration_dependency)
        ),
        "frozen_package_registry_drift_rejected": _expect_verification_error(
            lambda: _validate_frozen_package_registry(wrong_frozen_registry)
        ),
    }
    _require(all(negative_cases.values()), "FD08 verifier negative self-check failed")
    return {
        "contract_self_check": "PASS",
        "slice": "FD08",
        "marker": "FD08_EXACT_10_PATH_VERIFIER_SELF_CHECK=PASS",
        "negative_cases": negative_cases,
        "path_counts": {"modified": 4, "new": 6, "total": 10},
        "registry_counts": {"portable": 12, "postgresql_only": 2},
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
