#!/usr/bin/env python3
"""Verify the exact Production Studio C0 path and Foundation-freeze boundary."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath


PINNED_BASE_HEAD = "5f73ebf2fd29a161a34ea047c7eead4fb0c582d4"
PINNED_BASE_TREE = "ea5ff9ab510cb76f0c2b1bfda1c02c1278812aae"
PINNED_DOMAIN_TREE = "8e737658c80fe5f489b8d810f82fd8828c33fb13"

ACTIVE_C0_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/README.md",
        "software/conflict_analysis/conflict_analysis/settings.py",
        "software/conflict_analysis/conflict_analysis/urls.py",
        "software/conflict_analysis/docs/adr/0007-production-studio-c-read-only-first.md",
        "software/conflict_analysis/docs/production-studio-c-read-only-runtime.md",
        "software/conflict_analysis/production_studio/__init__.py",
        "software/conflict_analysis/production_studio/apps.py",
        "software/conflict_analysis/production_studio/browser_tests/cdp_client.mjs",
        "software/conflict_analysis/production_studio/browser_tests/read_only_smoke.mjs",
        "software/conflict_analysis/production_studio/claim_boundaries.py",
        "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json",
        "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json.sha256",
        "software/conflict_analysis/production_studio/static/production_studio/studio.css",
        "software/conflict_analysis/production_studio/static/production_studio/studio.js",
        "software/conflict_analysis/production_studio/templates/production_studio/definition.html",
        "software/conflict_analysis/production_studio/templates/production_studio/entry.html",
        "software/conflict_analysis/production_studio/tests/__init__.py",
        "software/conflict_analysis/production_studio/tests/test_browser_contract.py",
        "software/conflict_analysis/production_studio/tests/test_claim_boundaries.py",
        "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
        "software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py",
        "software/conflict_analysis/production_studio/urls.py",
        "software/conflict_analysis/production_studio/views.py",
        "software/conflict_analysis/pyproject.toml",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
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
    """A deterministic C0 boundary verification failure."""


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
    top = _git(start, "rev-parse", "--show-toplevel")
    return Path(top).resolve()


def _normalize(path: str) -> str:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    if normalized.startswith("../") or normalized == "..":
        raise VerificationError(f"changed path escapes repository: {path!r}")
    return normalized


def _changed_paths(repo: Path, base_head: str) -> set[str]:
    committed = {
        _normalize(path)
        for path in _git(repo, "diff", "--name-only", f"{base_head}...HEAD", "--").splitlines()
        if path
    }
    worktree = {
        _normalize(path)
        for path in _git(repo, "diff", "--name-only", "HEAD", "--").splitlines()
        if path
    }
    staged = {
        _normalize(path)
        for path in _git(repo, "diff", "--cached", "--name-only", "HEAD", "--").splitlines()
        if path
    }
    untracked = {
        _normalize(path)
        for path in _git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
        if path
    }
    return committed | worktree | staged | untracked


def verify(repo: Path, *, base_head: str, base_tree: str) -> dict[str, object]:
    actual_base_tree = _git(repo, "rev-parse", f"{base_head}^{{tree}}")
    if base_head != PINNED_BASE_HEAD or base_tree != PINNED_BASE_TREE:
        raise VerificationError("C0 accepts only the pinned authorization HEAD/TREE")
    if actual_base_tree != base_tree:
        raise VerificationError(
            f"base tree mismatch: expected {base_tree}, resolved {actual_base_tree}"
        )
    if _git(repo, "merge-base", base_head, "HEAD") != base_head:
        raise VerificationError("HEAD is not a descendant of the exact C0 base")

    changed = _changed_paths(repo, base_head)
    outside = sorted(changed - ACTIVE_C0_ALLOWLIST)
    if outside:
        raise VerificationError(
            "changed path(s) outside ACTIVE C0 EXACT ALLOWLIST: " + ", ".join(outside)
        )

    domain_prefix = "software/conflict_analysis/domain/"
    changed_domain = sorted(path for path in changed if path.startswith(domain_prefix))
    if changed_domain:
        raise VerificationError("domain/ is mechanically frozen: " + ", ".join(changed_domain))

    domain_tree = _git(repo, "rev-parse", f"{base_head}:software/conflict_analysis/domain")
    if domain_tree != PINNED_DOMAIN_TREE:
        raise VerificationError(
            f"pinned domain tree mismatch: expected {PINNED_DOMAIN_TREE}, got {domain_tree}"
        )
    if _git(
        repo,
        "diff",
        "--name-only",
        base_head,
        "--",
        "software/conflict_analysis/domain",
    ):
        raise VerificationError("tracked domain/ bytes differ from the pinned base")

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

    return {
        "allowlist_result": "PASS",
        "base_head": base_head,
        "base_tree": base_tree,
        "changed_paths": sorted(changed),
        "domain_tree": domain_tree,
        "domain_tree_unchanged": True,
        "migration_filenames_unchanged": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-head", default=PINNED_BASE_HEAD)
    parser.add_argument("--base-tree", default=PINNED_BASE_TREE)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        result = verify(
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
