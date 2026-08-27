#!/usr/bin/env python3
"""Verify exact FD01/FD05 prerequisite path sets and accepted C0 freeze anchors."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath


FD01_BASE_HEAD = "c0b773573c8d37faf7b1b71e910f7a8d356000f4"
FD01_BASE_TREE = "914e3b0895e404cf699d651c8148da875528b4e7"
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


def _object(repo: Path, spec: str) -> str:
    return _git(repo, "rev-parse", spec)


def verify_fd01(repo: Path, *, base_head: str, base_tree: str) -> dict[str, object]:
    if base_head != FD01_BASE_HEAD or base_tree != FD01_BASE_TREE:
        raise VerificationError("FD01 accepts only the MAIN-authorized C0 HEAD/TREE")
    if _object(repo, f"{base_head}^{{tree}}") != base_tree:
        raise VerificationError("FD01 base tree does not match the pinned C0 tree")
    if _git(repo, "merge-base", base_head, "HEAD") != base_head:
        raise VerificationError("HEAD is not a descendant of the exact FD01 base")
    merge_commits = _git(repo, "rev-list", "--merges", f"{base_head}..HEAD")
    if merge_commits:
        raise VerificationError("merge commits are forbidden inside the FD01 slice")

    changed = _changed_paths(repo, base_head)
    outside = sorted(changed - FD01_ALLOWLIST)
    if outside:
        raise VerificationError("FD01 changed path(s) outside exact allowlist: " + ", ".join(outside))

    freeze_specs = {
        "production_studio_tree": (
            f"{base_head}:software/conflict_analysis/production_studio",
            PINNED_PRODUCTION_STUDIO_TREE,
        ),
        "models_blob": (
            f"{base_head}:software/conflict_analysis/domain/models.py",
            PINNED_MODELS_BLOB,
        ),
        "enums_blob": (
            f"{base_head}:software/conflict_analysis/domain/enums.py",
            PINNED_ENUMS_BLOB,
        ),
        "migrations_tree": (
            f"{base_head}:software/conflict_analysis/domain/migrations",
            PINNED_MIGRATIONS_TREE,
        ),
        "project_definitions_blob": (
            f"{base_head}:software/conflict_analysis/domain/services/project_definitions.py",
            PINNED_PROJECT_DEFINITIONS_BLOB,
        ),
    }
    resolved: dict[str, str] = {}
    for label, (spec, expected) in freeze_specs.items():
        value = _object(repo, spec)
        if value != expected:
            raise VerificationError(f"pinned {label} mismatch: expected {expected}, got {value}")
        resolved[label] = value

    forbidden_roots = (
        "software/conflict_analysis/production_studio",
        "software/conflict_analysis/domain/models.py",
        "software/conflict_analysis/domain/enums.py",
        "software/conflict_analysis/domain/migrations",
        "software/conflict_analysis/domain/services/project_definitions.py",
        "software/conflict_analysis/studio_showcase",
        "software/conflict_analysis/shared_ui",
    )
    for root in forbidden_roots:
        if _git(repo, "diff", "--name-only", base_head, "--", root):
            raise VerificationError(f"FD01 frozen path changed: {root}")

    migrations = tuple(
        line
        for line in _git(repo, "ls-files", "software/conflict_analysis/domain/migrations").splitlines()
        if line
    )
    if migrations != PINNED_MIGRATIONS:
        raise VerificationError(
            "migration filename set changed: "
            + json.dumps({"expected": PINNED_MIGRATIONS, "actual": migrations})
        )

    return {
        "allowlist_result": "PASS",
        "slice": "FD01",
        "base_head": base_head,
        "base_tree": base_tree,
        "changed_paths": sorted(changed),
        "freeze": resolved,
        "migration_filenames_unchanged": True,
        "fd05_path_contract_predeclared": sorted(FD05_ALLOWLIST),
        "fd05_exact_base_pin": "EXTERNAL_MAIN_ORACLE_REQUIRED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", choices=("FD01",), default="FD01")
    parser.add_argument("--base-head", default=FD01_BASE_HEAD)
    parser.add_argument("--base-tree", default=FD01_BASE_TREE)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = verify_fd01(
            _repo_root(args.repo.resolve()),
            base_head=args.base_head,
            base_tree=args.base_tree,
        )
    except VerificationError as exc:
        print(json.dumps({"allowlist_result": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
