#!/usr/bin/env python3
"""Verify the exact Production Studio C0 or infrastructure-only R0 boundary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


PINNED_BASE_HEAD = "5f73ebf2fd29a161a34ea047c7eead4fb0c582d4"
PINNED_BASE_TREE = "ea5ff9ab510cb76f0c2b1bfda1c02c1278812aae"
PINNED_DOMAIN_TREE = "8e737658c80fe5f489b8d810f82fd8828c33fb13"

PINNED_R0_BASE_HEAD = "ca16f7a99ff044f7fbccb83354d5a9112c99027a"
PINNED_R0_BASE_TREE = "c25848dbbb19aabd5a2d4d642b69c66254879059"
PINNED_R0_DOMAIN_TREE = "51279fb4d656ed42e5da3b18d7922380dce3800d"
PINNED_R0_MIGRATIONS_TREE = "b0cc214cd63086172c9d3801338a5a2302a7ce0f"
PINNED_R0_PRODUCTION_STUDIO_TREE = "87d8e93ec09a18b87ae016977f0fb5fbf67d4104"
PINNED_R0_MODELS_BLOB = "c6c5c2419989e7b0cf40bd1242ab65d37cc2e162"
PINNED_R0_ENUMS_BLOB = "a701c3c83511b7d1706519d40fab4580d0a0d63e"
PINNED_R0_CLAIM_CONTRACTS_TREE = "737ff552664913fd87496bc2dfb0499389cea3c4"
_LOWER_HEX_40 = re.compile(r"[0-9a-f]{40}\Z")

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

ACTIVE_R0_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
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
    """A deterministic Production Studio slice-boundary verification failure."""


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


def _require_exact_object_id(label: str, value: str | None) -> str:
    if value is None or _LOWER_HEX_40.fullmatch(value) is None:
        raise VerificationError(f"{label} must be an exact lowercase 40-hex object id")
    return value


def _resolve_slice_contract(
    *,
    active_slice: str,
    base_head: str,
    base_tree: str,
    fd05_accepted_head: str | None,
    fd05_accepted_tree: str | None,
) -> dict[str, object]:
    base_head = _require_exact_object_id("base HEAD", base_head)
    base_tree = _require_exact_object_id("base TREE", base_tree)
    if active_slice == "C0":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("C0 does not accept FD05 external pin arguments")
        if base_head != PINNED_BASE_HEAD or base_tree != PINNED_BASE_TREE:
            raise VerificationError("C0 accepts only the pinned authorization HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_C0_ALLOWLIST,
            "exact_changed_paths": False,
            "domain_tree": PINNED_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_C0",
        }
    if active_slice != "R0":
        raise VerificationError(f"unsupported Production Studio verifier slice: {active_slice!r}")

    accepted_head = _require_exact_object_id(
        "FD05_ACCEPTED_HEAD",
        fd05_accepted_head,
    )
    accepted_tree = _require_exact_object_id(
        "FD05_ACCEPTED_TREE",
        fd05_accepted_tree,
    )
    if accepted_head != PINNED_R0_BASE_HEAD or accepted_tree != PINNED_R0_BASE_TREE:
        raise VerificationError("external FD05 pin does not match authorized H2/T2")
    if base_head != accepted_head or base_tree != accepted_tree:
        raise VerificationError("R0 base HEAD/TREE does not match the external FD05 pin")
    return {
        "active_slice": active_slice,
        "allowlist": ACTIVE_R0_ALLOWLIST,
        "exact_changed_paths": True,
        "domain_tree": PINNED_R0_DOMAIN_TREE,
        "fd05_base_pin": "PIN_VERIFIED_EXTERNAL",
    }


def self_check() -> dict[str, object]:
    """Exercise only deterministic slice/pin parsing; make no repository claims."""

    c0 = _resolve_slice_contract(
        active_slice="C0",
        base_head=PINNED_BASE_HEAD,
        base_tree=PINNED_BASE_TREE,
        fd05_accepted_head=None,
        fd05_accepted_tree=None,
    )
    r0 = _resolve_slice_contract(
        active_slice="R0",
        base_head=PINNED_R0_BASE_HEAD,
        base_tree=PINNED_R0_BASE_TREE,
        fd05_accepted_head=PINNED_R0_BASE_HEAD,
        fd05_accepted_tree=PINNED_R0_BASE_TREE,
    )
    other_head = "b" * 40
    other_tree = "d" * 40
    valid_r0 = {
        "active_slice": "R0",
        "base_head": PINNED_R0_BASE_HEAD,
        "base_tree": PINNED_R0_BASE_TREE,
        "fd05_accepted_head": PINNED_R0_BASE_HEAD,
        "fd05_accepted_tree": PINNED_R0_BASE_TREE,
    }
    invalid_contracts = (
        ("unsupported slice", {"active_slice": "UNKNOWN"}, "unsupported"),
        (
            "missing pins",
            {"fd05_accepted_head": None, "fd05_accepted_tree": None},
            "FD05_ACCEPTED_HEAD",
        ),
        ("missing tree pin", {"fd05_accepted_tree": None}, "FD05_ACCEPTED_TREE"),
        ("missing head pin", {"fd05_accepted_head": None}, "FD05_ACCEPTED_HEAD"),
        (
            "uppercase head pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD.upper()},
            "FD05_ACCEPTED_HEAD",
        ),
        (
            "uppercase tree pin",
            {"fd05_accepted_tree": PINNED_R0_BASE_TREE.upper()},
            "FD05_ACCEPTED_TREE",
        ),
        (
            "malformed head pin",
            {"fd05_accepted_head": "not-an-object-id"},
            "FD05_ACCEPTED_HEAD",
        ),
        (
            "malformed tree pin",
            {"fd05_accepted_tree": "not-an-object-id"},
            "FD05_ACCEPTED_TREE",
        ),
        (
            "mismatched head pin",
            {"fd05_accepted_head": other_head},
            "does not match authorized H2/T2",
        ),
        (
            "mismatched tree pin",
            {"fd05_accepted_tree": other_tree},
            "does not match authorized H2/T2",
        ),
        (
            "mismatched base head",
            {"base_head": other_head},
            "does not match the external FD05 pin",
        ),
        (
            "mismatched base tree",
            {"base_tree": other_tree},
            "does not match the external FD05 pin",
        ),
        (
            "malformed base head",
            {"base_head": "not-an-object-id"},
            "base HEAD",
        ),
        (
            "malformed base tree",
            {"base_tree": "not-an-object-id"},
            "base TREE",
        ),
    )
    for label, overrides, expected_error in invalid_contracts:
        candidate = {**valid_r0, **overrides}
        try:
            _resolve_slice_contract(**candidate)  # type: ignore[arg-type]
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    try:
        _resolve_slice_contract(
            active_slice="C0",
            base_head=PINNED_BASE_HEAD,
            base_tree=PINNED_BASE_TREE,
            fd05_accepted_head=PINNED_R0_BASE_HEAD,
            fd05_accepted_tree=PINNED_R0_BASE_TREE,
        )
    except VerificationError as exc:
        if "C0 does not accept FD05 external pin arguments" not in str(exc):
            raise VerificationError(
                "offline C0 external-pin self-check failed for the wrong reason"
            ) from exc
    else:
        raise VerificationError("offline self-check let an R0 external pin leak into C0")

    return {
        "marker": "PRODUCTION_STUDIO_R0_VERIFIER_SELF_CHECK=PASS",
        "network_access": False,
        "repository_access": False,
        "positive_slices": [c0["active_slice"], r0["active_slice"]],
        "negative_cases": len(invalid_contracts) + 1,
    }


def verify(
    repo: Path,
    *,
    base_head: str,
    base_tree: str,
    active_slice: str = "C0",
    fd05_accepted_head: str | None = None,
    fd05_accepted_tree: str | None = None,
) -> dict[str, object]:
    contract = _resolve_slice_contract(
        active_slice=active_slice,
        base_head=base_head,
        base_tree=base_tree,
        fd05_accepted_head=fd05_accepted_head,
        fd05_accepted_tree=fd05_accepted_tree,
    )
    actual_base_tree = _git(repo, "rev-parse", f"{base_head}^{{tree}}")
    if actual_base_tree != base_tree:
        raise VerificationError(
            f"base tree mismatch: expected {base_tree}, resolved {actual_base_tree}"
        )
    if _git(repo, "merge-base", base_head, "HEAD") != base_head:
        raise VerificationError(
            f"HEAD is not a descendant of the exact {active_slice} base"
        )

    if active_slice == "R0":
        merge_commits = tuple(
            item
            for item in _git(
                repo,
                "rev-list",
                "--merges",
                f"{base_head}..HEAD",
            ).splitlines()
            if item
        )
        if merge_commits:
            raise VerificationError(
                "merge commits are forbidden after the exact R0 base: "
                + ", ".join(merge_commits)
            )

    changed = _changed_paths(repo, base_head)
    allowlist = contract["allowlist"]
    if not isinstance(allowlist, frozenset):
        raise VerificationError("internal slice allowlist contract is invalid")
    outside = sorted(changed - allowlist)
    if outside:
        raise VerificationError(
            f"changed path(s) outside ACTIVE {active_slice} EXACT ALLOWLIST: "
            + ", ".join(outside)
        )
    if contract["exact_changed_paths"] and changed != allowlist:
        missing = sorted(allowlist - changed)
        raise VerificationError(
            "R0 changed paths must equal the exact two-path allowlist; missing: "
            + ", ".join(missing)
        )

    domain_prefix = "software/conflict_analysis/domain/"
    changed_domain = sorted(path for path in changed if path.startswith(domain_prefix))
    if changed_domain:
        raise VerificationError("domain/ is mechanically frozen: " + ", ".join(changed_domain))

    domain_tree = _git(
        repo,
        "rev-parse",
        f"{base_head}:software/conflict_analysis/domain",
    )
    expected_domain_tree = contract["domain_tree"]
    if not isinstance(expected_domain_tree, str):
        raise VerificationError("internal domain freeze contract is invalid")
    if domain_tree != expected_domain_tree:
        raise VerificationError(
            "pinned domain tree mismatch: "
            f"expected {expected_domain_tree}, got {domain_tree}"
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

    frozen_objects: dict[str, str] = {}
    if active_slice == "R0":
        r0_frozen_objects = {
            "software/conflict_analysis/domain": PINNED_R0_DOMAIN_TREE,
            "software/conflict_analysis/domain/migrations": PINNED_R0_MIGRATIONS_TREE,
            "software/conflict_analysis/domain/models.py": PINNED_R0_MODELS_BLOB,
            "software/conflict_analysis/domain/enums.py": PINNED_R0_ENUMS_BLOB,
            "software/conflict_analysis/production_studio": (
                PINNED_R0_PRODUCTION_STUDIO_TREE
            ),
            "software/conflict_analysis/production_studio/contracts": (
                PINNED_R0_CLAIM_CONTRACTS_TREE
            ),
        }
        for path, expected_object in r0_frozen_objects.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if base_object != expected_object or head_object != expected_object:
                raise VerificationError(
                    f"R0 frozen object drift at {path}: "
                    f"expected {expected_object}, base {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = expected_object

    return {
        "active_slice": active_slice,
        "allowlist_result": "PASS",
        "base_head": base_head,
        "base_tree": base_tree,
        "changed_paths": sorted(changed),
        "domain_tree": domain_tree,
        "domain_tree_unchanged": True,
        "exact_changed_paths": changed == allowlist if active_slice == "R0" else None,
        "fd05_base_pin": contract["fd05_base_pin"],
        "frozen_objects": frozen_objects,
        "merge_commits_absent": True if active_slice == "R0" else None,
        "migration_filenames_unchanged": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice", choices=("C0", "R0"), default="C0")
    parser.add_argument("--base-head", default=PINNED_BASE_HEAD)
    parser.add_argument("--base-tree", default=PINNED_BASE_TREE)
    parser.add_argument("--fd05-accepted-head")
    parser.add_argument("--fd05-accepted-tree")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.self_check:
            result = self_check()
        else:
            result = verify(
                _repo_root(args.repo.resolve()),
                active_slice=args.slice,
                base_head=args.base_head,
                base_tree=args.base_tree,
                fd05_accepted_head=args.fd05_accepted_head,
                fd05_accepted_tree=args.fd05_accepted_tree,
            )
    except VerificationError as exc:
        print(json.dumps({"allowlist_result": "FAIL", "error": str(exc)}, ensure_ascii=False))
        return 1
    if args.self_check:
        print(result["marker"])
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
