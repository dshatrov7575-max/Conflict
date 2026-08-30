#!/usr/bin/env python3
"""Verify the exact Production Studio and Foundation slice boundaries."""

from __future__ import annotations

import argparse
import ast
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
PINNED_C1_START_HEAD = "bd6e88c2a5f6552e057ea5b49fc63a1eb77ef4c6"
PINNED_C1_START_TREE = "e1124839da8571408c258517c8afdf24622f1655"
PINNED_FD02_BASE_HEAD = "bbe852d2f30f1be042e9cd8c35a52fd120d65ae4"
PINNED_FD02_BASE_TREE = "838364d0f10a9517160a6bb0a81b547f121e2447"
PINNED_FD02_DOMAIN_TREE = "51279fb4d656ed42e5da3b18d7922380dce3800d"
PINNED_FD03_BASE_HEAD = "6b7d8977f9798fa21b9ccc3d12f9410a5165d6b5"
PINNED_FD03_BASE_TREE = "09f9a2f93b0e63f7d90863131ffbe799b17475bf"
PINNED_FD03_BASE_DOMAIN_TREE = "e47f058218efb79e04b52d4434f9e72f9f91a901"
PINNED_FD03_RC2_START_HEAD = "bee7335d441c0b5d6d3501481fb14fb62a5de7a8"
PINNED_FD03_RC2_START_TREE = "a94e9c08bdc67d3f6b2e04952de44ac3f8339f99"
PINNED_FD06_BASE_HEAD = "feefd3899b5a168e650ddb3094881f48830acb96"
PINNED_FD06_BASE_TREE = "0dad3448608b3bbab28c7f1bfc7399c30382a343"
PINNED_FD06_BASE_DOMAIN_TREE = "8fd38b8d56177527473ac652978594593773c973"
PINNED_FD06_PRODUCTION_STUDIO_TREE = "31ba7273cfe4a6ae3c57054518de2e2ba98113ff"
PINNED_FD06_RC4_INTERMEDIATE_HEAD = "0dd4ae788c765a0a0c24ac4d61582870d73e29e2"
PINNED_FD06_RC4_INTERMEDIATE_TREE = "b59baccfa73ba6b9cce6e89419cb540005564b64"
FD06_BASE_BRANCH = "codex/ca-suite-i1-foundation-fd03-lifecycle-read-result"
FD06_TARGET_BRANCH = (
    "codex/ca-suite-i1-foundation-fd06-publication-reconciliation"
)
FD06_EXACT_PATH_COUNT = 10
FD06_POSTGRESQL_TOTAL = 227
FD06_POSTGRESQL_SKIPPED = 0
FD06_SQLITE_PASSED = 212
FD06_SQLITE_SKIPPED = 15
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

# Sealed exact 16-path delta against the accepted R0 authorization point;
# additions are not accepted through directory-prefix matching.
ACTIVE_C1_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/README.md",
        "software/conflict_analysis/docs/adr/0008-production-studio-c-audited-draft.md",
        "software/conflict_analysis/docs/production-studio-c-read-only-runtime.md",
        "software/conflict_analysis/production_studio/authoring_claim_boundaries.py",
        "software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs",
        "software/conflict_analysis/production_studio/contracts/audited_draft_claim_boundaries_v1.ru.json",
        "software/conflict_analysis/production_studio/contracts/audited_draft_claim_boundaries_v1.ru.json.sha256",
        "software/conflict_analysis/production_studio/static/production_studio/audited_draft.css",
        "software/conflict_analysis/production_studio/static/production_studio/audited_draft.js",
        "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_definition.html",
        "software/conflict_analysis/production_studio/templates/production_studio/audited_draft_entry.html",
        "software/conflict_analysis/production_studio/tests/test_audited_authoring.py",
        "software/conflict_analysis/production_studio/urls.py",
        "software/conflict_analysis/production_studio/views.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

C1_FROZEN_PATHS = (
    "software/conflict_analysis/domain",
    "software/conflict_analysis/domain/migrations",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/enums.py",
    "software/conflict_analysis/domain/policies.py",
    "software/conflict_analysis/domain/services/foundation_packages.py",
    "software/conflict_analysis/domain/services/project_definitions.py",
    "software/conflict_analysis/domain/services/schemas",
    "software/conflict_analysis/production_studio/__init__.py",
    "software/conflict_analysis/production_studio/apps.py",
    "software/conflict_analysis/production_studio/browser_tests/cdp_client.mjs",
    "software/conflict_analysis/production_studio/claim_boundaries.py",
    "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json",
    "software/conflict_analysis/production_studio/contracts/read_only_claim_boundaries_v1.ru.json.sha256",
    "software/conflict_analysis/production_studio/static/production_studio/studio.css",
    "software/conflict_analysis/production_studio/static/production_studio/studio.js",
    "software/conflict_analysis/production_studio/templates/production_studio/definition.html",
    "software/conflict_analysis/production_studio/templates/production_studio/entry.html",
    "software/conflict_analysis/production_studio/browser_tests/read_only_smoke.mjs",
    "software/conflict_analysis/production_studio/tests/__init__.py",
    "software/conflict_analysis/production_studio/tests/test_browser_contract.py",
    "software/conflict_analysis/production_studio/tests/test_claim_boundaries.py",
    "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
    "software/conflict_analysis/production_studio/tests/test_read_only_static_contracts.py",
)

ACTIVE_FD02_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/domain/content/studio_help_ru_v1.json",
        "software/conflict_analysis/domain/management/commands/provision_studio_help.py",
        "software/conflict_analysis/domain/services/studio_help_catalog.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_help_provisioning.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

ACTIVE_FD03_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/domain/urls.py",
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
        "software/conflict_analysis/production_studio/tests/test_read_only_http.py",
    }
)

ACTIVE_FD06_ALLOWLIST = frozenset(
    {
        ".github/workflows/conflict-analysis.yml",
        "software/conflict_analysis/docs/adr/0006-foundation-studio-application-gateways.md",
        "software/conflict_analysis/domain/api/studio_definitions.py",
        "software/conflict_analysis/domain/policies.py",
        "software/conflict_analysis/domain/services/project_definitions.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_bootstrap.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_http.py",
        "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py",
        "software/conflict_analysis/domain/urls.py",
        "software/conflict_analysis/scripts/verify_production_studio_c_allowlist.py",
    }
)

FD06_PORTABLE_CLASS = "FoundationStudioPublicationReconciliationTests"
FD06_PORTABLE_METHODS = (
    "test_initial_and_successor_require_exact_key_if_match_envelope_and_prebody_method_gate",
    "test_initial_fresh_result_persists_hash_bound_project_operation_and_exact_receipt",
    "test_successor_fresh_result_preserves_predecessor_and_exact_receipt",
    "test_same_key_same_request_replays_before_lifecycle_rejection_and_after_workspace_or_lifecycle_change",
    "test_same_uuid_key_is_independent_across_projects_and_foreign_operation_is_hidden",
    "test_same_key_different_request_actor_or_target_is_typed_conflict",
    "test_response_loss_recovers_immutable_receipt_and_fd03_current_state_remains_separate",
    "test_already_published_stale_noncurrent_and_cross_scope_failures_are_typed",
    "test_every_initial_failure_stage_rolls_back_definition_workspace_help_publication_and_audits",
    "test_every_successor_failure_stage_rolls_back_currentness_publication_and_audits",
    "test_auth_csrf_basic_cookie_and_nonpost_paths_are_bounded_and_write_free_before_admission",
)
FD06_CONCURRENCY_CLASS = "FoundationStudioPublicationReconciliationConcurrencyTests"
FD06_CONCURRENCY_METHODS = (
    "test_concurrent_initial_same_key_has_one_fresh_and_one_replay",
    "test_concurrent_initial_different_keys_has_one_commit_and_one_typed_loser",
    "test_concurrent_successor_same_key_has_one_fresh_and_one_replay",
    "test_concurrent_successor_different_keys_has_one_current_winner_and_one_typed_loser",
)

FD06_EXACT_FROZEN_OBJECTS = {
    "software/conflict_analysis/domain/models.py": (
        "c6c5c2419989e7b0cf40bd1242ab65d37cc2e162"
    ),
    "software/conflict_analysis/domain/enums.py": (
        "a701c3c83511b7d1706519d40fab4580d0a0d63e"
    ),
    "software/conflict_analysis/domain/migrations": (
        "b0cc214cd63086172c9d3801338a5a2302a7ce0f"
    ),
    "software/conflict_analysis/production_studio": (
        PINNED_FD06_PRODUCTION_STUDIO_TREE
    ),
}
FD06_REOPENED_BASE_BLOBS = {
    "software/conflict_analysis/domain/api/studio_definitions.py": (
        "bf6cdf29c49878025c73e2a984f61a1e326b0c8e"
    ),
    "software/conflict_analysis/domain/policies.py": (
        "697c72a91fe6fbe00ae54ec249ea89583d47ca93"
    ),
    "software/conflict_analysis/domain/services/project_definitions.py": (
        "9bb454a25a9621507662d5aa12e35ccd8a91dd1d"
    ),
    "software/conflict_analysis/domain/urls.py": (
        "127bde69d539844d59b53b74f81aa3483f865e66"
    ),
}
FD06_HTTP_BOUNDED_CLASS = "FoundationStudioApplicationGatewayHttpTests"
FD06_HTTP_BOUNDED_METHOD = (
    "test_successor_http_201_etag_pin_preservation_and_stable_retry_409"
)
FD06_BOOTSTRAP_BOUNDED_CLASS = "FoundationStudioHttpAuthorizationTests"
FD06_BOOTSTRAP_BOUNDED_METHOD = (
    "test_editor_viewer_publisher_matrix_and_exact_routes"
)

FD03_AGGREGATE_ALLOWLIST = ACTIVE_FD02_ALLOWLIST | ACTIVE_FD03_ALLOWLIST

FD03_TEST_CLASS = "FoundationStudioLifecycleReadResultHttpTests"
FD03_TEST_METHODS = (
    "test_fd03_open_definition_returns_exact_persisted_lifecycle_values",
    "test_fd03_open_definition_distinguishes_current_successor_and_published_predecessor",
    "test_fd03_initial_publication_result_recovers_exact_workspace_pin",
    "test_fd03_successor_publication_result_has_exact_null_workspace_fields",
    "test_fd03_publication_result_scope_identity_and_get_only_boundary_are_indistinguishable",
    "test_fd03_reads_are_repeat_stable_and_non_mutating",
)

FD03_C0_CLASS = "ProductionStudioReadOnlyHttpTests"
FD03_C0_METHOD = (
    "test_open_all_literal_lifecycle_states_has_exact_hash_etag_and_zero_writes"
)

FD02_FROZEN_PATHS = (
    "software/conflict_analysis/conflict_analysis",
    "software/conflict_analysis/domain/api/studio_definitions.py",
    "software/conflict_analysis/domain/enums.py",
    "software/conflict_analysis/domain/migrations",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/policies.py",
    "software/conflict_analysis/domain/services/foundation_packages.py",
    "software/conflict_analysis/domain/services/help_topics.py",
    "software/conflict_analysis/domain/services/project_definitions.py",
    "software/conflict_analysis/domain/services/schemas",
    "software/conflict_analysis/domain/urls.py",
    "software/conflict_analysis/production_studio",
    "software/conflict_analysis/pyproject.toml",
)

FD03_FROZEN_PATHS = (
    "software/conflict_analysis/conflict_analysis",
    "software/conflict_analysis/domain/content/studio_help_ru_v1.json",
    "software/conflict_analysis/domain/management/commands/provision_studio_help.py",
    "software/conflict_analysis/domain/models.py",
    "software/conflict_analysis/domain/enums.py",
    "software/conflict_analysis/domain/migrations",
    "software/conflict_analysis/domain/policies.py",
    "software/conflict_analysis/domain/services",
    "software/conflict_analysis/domain/tests/test_foundation_studio_help_provisioning.py",
    "software/conflict_analysis/production_studio/browser_tests",
    "software/conflict_analysis/production_studio/contracts",
    "software/conflict_analysis/production_studio/static",
    "software/conflict_analysis/production_studio/templates",
    "software/conflict_analysis/production_studio/urls.py",
    "software/conflict_analysis/production_studio/views.py",
    "software/conflict_analysis/pyproject.toml",
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
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_C0",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_C0",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_C0",
        }
    if active_slice == "FD02":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("FD02 does not accept FD05 external pin arguments")
        if base_head != PINNED_FD02_BASE_HEAD or base_tree != PINNED_FD02_BASE_TREE:
            raise VerificationError("FD02 accepts only the exact accepted C1 HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_FD02_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_FD02_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_FD02",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_FD02",
            "c1_base_pin": "PIN_VERIFIED_AUTHORIZATION",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_FD02",
        }
    if active_slice == "FD03":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("FD03 does not accept FD05 external pin arguments")
        if base_head != PINNED_FD03_BASE_HEAD or base_tree != PINNED_FD03_BASE_TREE:
            raise VerificationError("FD03 accepts only the exact accepted FD02 HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_FD03_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_FD03_BASE_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_FD03",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_FD03",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_FD03",
            "fd02_base_pin": "PIN_VERIFIED_AUTHORIZATION",
        }
    if active_slice == "FD06":
        if fd05_accepted_head is not None or fd05_accepted_tree is not None:
            raise VerificationError("FD06 does not accept external pin arguments")
        if base_head != PINNED_FD06_BASE_HEAD or base_tree != PINNED_FD06_BASE_TREE:
            raise VerificationError("FD06 accepts only the exact accepted FD03 HEAD/TREE")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_FD06_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_FD06_BASE_DOMAIN_TREE,
            "fd05_base_pin": "NOT_APPLICABLE_CURRENT_FD06",
            "fd05_accepted_head": None,
            "fd05_accepted_tree": None,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_FD06",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_FD06",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_FD06",
        }
    if active_slice not in {"R0", "C1"}:
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
    if active_slice == "R0":
        if base_head != accepted_head or base_tree != accepted_tree:
            raise VerificationError("R0 base HEAD/TREE does not match the external FD05 pin")
        return {
            "active_slice": active_slice,
            "allowlist": ACTIVE_R0_ALLOWLIST,
            "exact_changed_paths": True,
            "domain_tree": PINNED_R0_DOMAIN_TREE,
            "fd05_base_pin": "PIN_VERIFIED_EXTERNAL",
            "fd05_accepted_head": accepted_head,
            "fd05_accepted_tree": accepted_tree,
            "r0_start_pin": "NOT_APPLICABLE_CURRENT_R0",
            "c1_base_pin": "NOT_APPLICABLE_CURRENT_R0",
            "fd02_base_pin": "NOT_APPLICABLE_CURRENT_R0",
        }

    if base_head != PINNED_C1_START_HEAD or base_tree != PINNED_C1_START_TREE:
        raise VerificationError("C1 accepts only the exact authorized R0 START HEAD/TREE")
    return {
        "active_slice": active_slice,
        "allowlist": ACTIVE_C1_ALLOWLIST,
        "exact_changed_paths": True,
        "domain_tree": PINNED_R0_DOMAIN_TREE,
        "fd05_base_pin": "PIN_VERIFIED_EXTERNAL",
        "fd05_accepted_head": accepted_head,
        "fd05_accepted_tree": accepted_tree,
        "r0_start_pin": "PIN_VERIFIED_AUTHORIZATION",
        "c1_base_pin": "NOT_APPLICABLE_CURRENT_C1",
        "fd02_base_pin": "NOT_APPLICABLE_CURRENT_C1",
    }


def _require_changed_path_contract(
    *,
    active_slice: str,
    changed: frozenset[str] | set[str],
    allowlist: frozenset[str],
    exact_changed_paths: bool,
) -> None:
    outside = sorted(changed - allowlist)
    if outside:
        raise VerificationError(
            f"changed path(s) outside ACTIVE {active_slice} EXACT ALLOWLIST: "
            + ", ".join(outside)
        )
    if exact_changed_paths and changed != allowlist:
        missing = sorted(allowlist - changed)
        raise VerificationError(
            f"{active_slice} changed paths must equal the exact delivered allowlist; "
            "missing: "
            + ", ".join(missing)
        )


def _require_merge_free(active_slice: str, merge_commits: tuple[str, ...]) -> None:
    if merge_commits:
        raise VerificationError(
            f"merge commits are forbidden after the exact {active_slice} base: "
            + ", ".join(merge_commits)
        )


def _require_single_fast_forward_commit(
    *,
    active_slice: str,
    commit_count: int,
    delivery_parent: str,
    base_head: str,
) -> None:
    if commit_count != 1 or delivery_parent != base_head:
        raise VerificationError(
            f"{active_slice} delivery must be exactly one fast-forward commit "
            f"whose sole parent is the exact base; count={commit_count}, "
            f"parent={delivery_parent}, base={base_head}"
        )


def _require_fd06_rc5_public_history(
    *,
    commit_count: int,
    delivery_head: str,
    delivery_parent: str,
    intermediate_parent: str,
    intermediate_tree: str,
    ordered_commits: tuple[str, ...],
) -> None:
    delivery_head = _require_exact_object_id("FD06 RC5 delivery HEAD", delivery_head)
    delivery_parent = _require_exact_object_id(
        "FD06 RC5 delivery parent", delivery_parent
    )
    intermediate_parent = _require_exact_object_id(
        "FD06 RC4 intermediate parent", intermediate_parent
    )
    intermediate_tree = _require_exact_object_id(
        "FD06 RC4 intermediate TREE", intermediate_tree
    )
    expected_order = (PINNED_FD06_RC4_INTERMEDIATE_HEAD, delivery_head)
    if (
        commit_count != 2
        or delivery_head == PINNED_FD06_RC4_INTERMEDIATE_HEAD
        or delivery_parent != PINNED_FD06_RC4_INTERMEDIATE_HEAD
        or intermediate_parent != PINNED_FD06_BASE_HEAD
        or intermediate_tree != PINNED_FD06_RC4_INTERMEDIATE_TREE
        or ordered_commits != expected_order
    ):
        raise VerificationError(
            "FD06 RC5 public history must preserve the exact RC4 intermediate "
            "and add exactly one child commit; "
            f"count={commit_count}, delivery={delivery_head}, "
            f"delivery_parent={delivery_parent}, "
            f"intermediate_parent={intermediate_parent}, "
            f"intermediate_tree={intermediate_tree}, "
            f"ordered_commits={ordered_commits}"
        )


def _require_fd03_rc2_fast_forward(
    *,
    commit_count: int,
    delivery_parent: str,
) -> None:
    if commit_count != 2 or delivery_parent != PINNED_FD03_RC2_START_HEAD:
        raise VerificationError(
            "FD03 RC2 delivery must be exactly two fast-forward commits from "
            "the accepted FD02 base, with the final commit whose sole parent "
            "is the exact RC2 start; "
            f"count={commit_count}, parent={delivery_parent}, "
            f"rc2_start={PINNED_FD03_RC2_START_HEAD}"
        )


def _resolve_fd06_route(
    *,
    event_name: str,
    event_ref: str = "",
    head_ref: str = "",
    base_ref: str = "",
) -> str:
    if event_name == "push" and event_ref == f"refs/heads/{FD06_TARGET_BRANCH}":
        return "PINNED_FD03"
    if (
        event_name == "pull_request"
        and head_ref == FD06_TARGET_BRANCH
        and base_ref == FD06_BASE_BRANCH
    ):
        return "EVENT_FD03"
    raise VerificationError(
        "FD06 routing accepts only its exact push ref or its exact stacked "
        "pull-request ref pair"
    )


def _require_fd06_static_contract(
    *,
    exact_path_count: int,
    portable_count: int,
    concurrency_count: int,
    postgresql_total: int,
    postgresql_skipped: int,
    sqlite_passed: int,
    sqlite_skipped: int,
) -> None:
    actual = (
        exact_path_count,
        portable_count,
        concurrency_count,
        postgresql_total,
        postgresql_skipped,
        sqlite_passed,
        sqlite_skipped,
    )
    expected = (
        FD06_EXACT_PATH_COUNT,
        11,
        4,
        FD06_POSTGRESQL_TOTAL,
        FD06_POSTGRESQL_SKIPPED,
        FD06_SQLITE_PASSED,
        FD06_SQLITE_SKIPPED,
    )
    if actual != expected:
        raise VerificationError(
            "FD06 static path/test total contract drifted: "
            + json.dumps({"expected": expected, "actual": actual})
        )


def _require_fd06_frozen_contract(
    *,
    exact_frozen_objects: dict[str, str],
    reopened_base_blobs: dict[str, str],
) -> None:
    if exact_frozen_objects != FD06_EXACT_FROZEN_OBJECTS:
        raise VerificationError("FD06 exact frozen-object contract drifted")
    if reopened_base_blobs != FD06_REOPENED_BASE_BLOBS:
        raise VerificationError("FD06 reopened base-blob contract drifted")


def _require_synthetic_merge_contract(
    *,
    expected_base_head: str,
    expected_delivery_head: str,
    actual_parents: tuple[str, ...],
    delivery_tree: str,
    synthetic_tree: str,
    independent_tree: str,
) -> None:
    expected_base_head = _require_exact_object_id(
        "synthetic expected base HEAD", expected_base_head
    )
    expected_delivery_head = _require_exact_object_id(
        "synthetic expected delivery HEAD", expected_delivery_head
    )
    delivery_tree = _require_exact_object_id("delivery TREE", delivery_tree)
    synthetic_tree = _require_exact_object_id("synthetic merge TREE", synthetic_tree)
    independent_tree = _require_exact_object_id(
        "independent merge-tree TREE", independent_tree
    )
    if actual_parents != (expected_base_head, expected_delivery_head):
        raise VerificationError(
            "synthetic merge parents must be [exact base HEAD, exact delivery HEAD]"
        )
    if synthetic_tree != delivery_tree or independent_tree != delivery_tree:
        raise VerificationError(
            "synthetic merge, delivery and independent merge-tree trees must be equal"
        )


def _require_exact_test_topology(
    *,
    source: str,
    class_name: str,
    expected_methods: tuple[str, ...],
) -> None:
    tree = ast.parse(source)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise VerificationError(
            f"expected exactly one {class_name} class, found {len(classes)}"
        )
    actual = tuple(
        node.name
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )
    if actual != expected_methods:
        raise VerificationError(
            f"{class_name} test topology mismatch: "
            + json.dumps({"expected": expected_methods, "actual": actual})
        )


def _normalized_authorized_method_body(
    source: str,
    *,
    class_name: str,
    method_name: str,
) -> str:
    tree = ast.parse(source)
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    ]
    if len(classes) != 1:
        raise VerificationError(
            f"expected exactly one frozen {class_name} class, found {len(classes)}"
        )
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    ]
    if len(methods) != 1 or not methods[0].body:
        raise VerificationError(
            f"expected exactly one non-empty frozen {class_name}.{method_name}"
        )
    method = methods[0]
    lines = source.splitlines(keepends=True)
    start = method.body[0].lineno - 1
    end = method.end_lineno
    indent = " " * (method.col_offset + 4)
    lines[start:end] = [f"{indent}<AUTHORIZED_FD03_RC2_ASSERTION_BODY>\n"]
    return "".join(lines).rstrip("\n")


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
    c1 = _resolve_slice_contract(
        active_slice="C1",
        base_head=PINNED_C1_START_HEAD,
        base_tree=PINNED_C1_START_TREE,
        fd05_accepted_head=PINNED_R0_BASE_HEAD,
        fd05_accepted_tree=PINNED_R0_BASE_TREE,
    )
    fd02 = _resolve_slice_contract(
        active_slice="FD02",
        base_head=PINNED_FD02_BASE_HEAD,
        base_tree=PINNED_FD02_BASE_TREE,
        fd05_accepted_head=None,
        fd05_accepted_tree=None,
    )
    fd03 = _resolve_slice_contract(
        active_slice="FD03",
        base_head=PINNED_FD03_BASE_HEAD,
        base_tree=PINNED_FD03_BASE_TREE,
        fd05_accepted_head=None,
        fd05_accepted_tree=None,
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

    valid_c1 = {
        "active_slice": "C1",
        "base_head": PINNED_C1_START_HEAD,
        "base_tree": PINNED_C1_START_TREE,
        "fd05_accepted_head": PINNED_R0_BASE_HEAD,
        "fd05_accepted_tree": PINNED_R0_BASE_TREE,
    }
    invalid_c1_contracts = (
        (
            "C1 H2 substituted for R0 start",
            {"base_head": PINNED_R0_BASE_HEAD, "base_tree": PINNED_R0_BASE_TREE},
            "exact authorized R0 START HEAD/TREE",
        ),
        (
            "C1 mismatched R0 start head",
            {"base_head": other_head},
            "exact authorized R0 START HEAD/TREE",
        ),
        (
            "C1 mismatched R0 start tree",
            {"base_tree": other_tree},
            "exact authorized R0 START HEAD/TREE",
        ),
        (
            "C1 missing H2 head pin",
            {"fd05_accepted_head": None},
            "FD05_ACCEPTED_HEAD",
        ),
        (
            "C1 mismatched H2 tree pin",
            {"fd05_accepted_tree": other_tree},
            "authorized H2/T2",
        ),
    )
    for label, overrides, expected_error in invalid_c1_contracts:
        candidate = {**valid_c1, **overrides}
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

    _require_changed_path_contract(
        active_slice="C1",
        changed=ACTIVE_C1_ALLOWLIST,
        allowlist=ACTIVE_C1_ALLOWLIST,
        exact_changed_paths=True,
    )
    _require_merge_free("C1", ())
    path_negative_cases = 0
    for label, changed, expected_error in (
        (
            "C1 path outside allowlist",
            ACTIVE_C1_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            "outside ACTIVE C1 EXACT ALLOWLIST",
        ),
        (
            "C1 missing delivered path",
            ACTIVE_C1_ALLOWLIST
            - {"software/conflict_analysis/production_studio/views.py"},
            "C1 changed paths must equal",
        ),
    ):
        path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice="C1",
                changed=frozenset(changed),
                allowlist=ACTIVE_C1_ALLOWLIST,
                exact_changed_paths=True,
            )
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
        _require_merge_free("C1", ("synthetic-merge-object",))
    except VerificationError as exc:
        if "merge commits are forbidden after the exact C1 base" not in str(exc):
            raise VerificationError(
                "offline C1 merge-topology self-check failed for the wrong reason"
            ) from exc
    else:
        raise VerificationError(
            "offline self-check unexpectedly accepted a C1 merge commit"
        )

    valid_fd02 = {
        "active_slice": "FD02",
        "base_head": PINNED_FD02_BASE_HEAD,
        "base_tree": PINNED_FD02_BASE_TREE,
        "fd05_accepted_head": None,
        "fd05_accepted_tree": None,
    }
    invalid_fd02_contracts = (
        (
            "FD02 mismatched accepted C1 head",
            {"base_head": other_head},
            "exact accepted C1 HEAD/TREE",
        ),
        (
            "FD02 mismatched accepted C1 tree",
            {"base_tree": other_tree},
            "exact accepted C1 HEAD/TREE",
        ),
        (
            "FD02 uppercase accepted C1 head",
            {"base_head": PINNED_FD02_BASE_HEAD.upper()},
            "base HEAD",
        ),
        (
            "FD02 unexpected external pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD},
            "does not accept FD05 external pin arguments",
        ),
    )
    for label, overrides, expected_error in invalid_fd02_contracts:
        candidate = {**valid_fd02, **overrides}
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

    _require_changed_path_contract(
        active_slice="FD02",
        changed=ACTIVE_FD02_ALLOWLIST,
        allowlist=ACTIVE_FD02_ALLOWLIST,
        exact_changed_paths=True,
    )
    fd02_path_negative_cases = 0
    for label, changed, expected_error in (
        (
            "FD02 path outside allowlist",
            ACTIVE_FD02_ALLOWLIST | {"software/conflict_analysis/pyproject.toml"},
            "outside ACTIVE FD02 EXACT ALLOWLIST",
        ),
        (
            "FD02 missing delivered path",
            ACTIVE_FD02_ALLOWLIST
            - {"software/conflict_analysis/domain/content/studio_help_ru_v1.json"},
            "FD02 changed paths must equal",
        ),
    ):
        fd02_path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice="FD02",
                changed=frozenset(changed),
                allowlist=ACTIVE_FD02_ALLOWLIST,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )
    _require_merge_free("FD02", ())
    _require_single_fast_forward_commit(
        active_slice="FD02",
        commit_count=1,
        delivery_parent=PINNED_FD02_BASE_HEAD,
        base_head=PINNED_FD02_BASE_HEAD,
    )
    try:
        _require_merge_free("FD02", ("synthetic-merge-object",))
    except VerificationError as exc:
        if "merge commits are forbidden after the exact FD02 base" not in str(exc):
            raise VerificationError(
                "offline FD02 merge-topology self-check failed for the wrong reason"
            ) from exc
    else:
        raise VerificationError(
            "offline self-check unexpectedly accepted an FD02 merge commit"
        )
    for label, commit_count, parent in (
        ("FD02 extra commit", 2, PINNED_FD02_BASE_HEAD),
        ("FD02 wrong parent", 1, other_head),
    ):
        try:
            _require_single_fast_forward_commit(
                active_slice="FD02",
                commit_count=commit_count,
                delivery_parent=parent,
                base_head=PINNED_FD02_BASE_HEAD,
            )
        except VerificationError as exc:
            if "exactly one fast-forward commit" not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    valid_fd03 = {
        "active_slice": "FD03",
        "base_head": PINNED_FD03_BASE_HEAD,
        "base_tree": PINNED_FD03_BASE_TREE,
        "fd05_accepted_head": None,
        "fd05_accepted_tree": None,
    }
    invalid_fd03_contracts = (
        (
            "FD03 mismatched accepted FD02 head",
            {"base_head": other_head},
            "exact accepted FD02 HEAD/TREE",
        ),
        (
            "FD03 mismatched accepted FD02 tree",
            {"base_tree": other_tree},
            "exact accepted FD02 HEAD/TREE",
        ),
        (
            "FD03 uppercase accepted FD02 head",
            {"base_head": PINNED_FD03_BASE_HEAD.upper()},
            "base HEAD",
        ),
        (
            "FD03 unexpected external pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD},
            "does not accept FD05 external pin arguments",
        ),
    )
    for label, overrides, expected_error in invalid_fd03_contracts:
        candidate = {**valid_fd03, **overrides}
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

    _require_changed_path_contract(
        active_slice="FD03",
        changed=ACTIVE_FD03_ALLOWLIST,
        allowlist=ACTIVE_FD03_ALLOWLIST,
        exact_changed_paths=True,
    )
    _require_changed_path_contract(
        active_slice="FD03_AGGREGATE",
        changed=FD03_AGGREGATE_ALLOWLIST,
        allowlist=FD03_AGGREGATE_ALLOWLIST,
        exact_changed_paths=True,
    )
    fd03_path_negative_cases = 0
    for label, changed, allowlist, expected_error in (
        (
            "FD03 eighth path",
            ACTIVE_FD03_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            ACTIVE_FD03_ALLOWLIST,
            "outside ACTIVE FD03 EXACT ALLOWLIST",
        ),
        (
            "FD03 missing bounded C0 node path",
            ACTIVE_FD03_ALLOWLIST
            - {"software/conflict_analysis/production_studio/tests/test_read_only_http.py"},
            ACTIVE_FD03_ALLOWLIST,
            "FD03 changed paths must equal",
        ),
        (
            "FD03 twelfth aggregate path",
            FD03_AGGREGATE_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            FD03_AGGREGATE_ALLOWLIST,
            "outside ACTIVE FD03_AGGREGATE EXACT ALLOWLIST",
        ),
        (
            "FD03 missing aggregate FD02 catalog",
            FD03_AGGREGATE_ALLOWLIST
            - {"software/conflict_analysis/domain/content/studio_help_ru_v1.json"},
            FD03_AGGREGATE_ALLOWLIST,
            "FD03_AGGREGATE changed paths must equal",
        ),
    ):
        fd03_path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice=(
                    "FD03_AGGREGATE"
                    if allowlist is FD03_AGGREGATE_ALLOWLIST
                    else "FD03"
                ),
                changed=frozenset(changed),
                allowlist=allowlist,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )
    _require_merge_free("FD03", ())
    _require_fd03_rc2_fast_forward(
        commit_count=2,
        delivery_parent=PINNED_FD03_RC2_START_HEAD,
    )
    for label, commit_count, parent in (
        ("FD03 missing RC2 commit", 1, PINNED_FD03_RC2_START_HEAD),
        ("FD03 extra commit", 3, PINNED_FD03_RC2_START_HEAD),
        ("FD03 wrong RC2 parent", 2, other_head),
    ):
        try:
            _require_fd03_rc2_fast_forward(
                commit_count=commit_count,
                delivery_parent=parent,
            )
        except VerificationError as exc:
            if "exactly two fast-forward commits" not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason"
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

    valid_fd06 = {
        "active_slice": "FD06",
        "base_head": PINNED_FD06_BASE_HEAD,
        "base_tree": PINNED_FD06_BASE_TREE,
        "fd05_accepted_head": None,
        "fd05_accepted_tree": None,
    }
    fd06 = _resolve_slice_contract(**valid_fd06)
    invalid_fd06_contracts = (
        (
            "FD06 mismatched accepted FD03 head",
            {"base_head": other_head},
            "exact accepted FD03 HEAD/TREE",
        ),
        (
            "FD06 mismatched accepted FD03 tree",
            {"base_tree": other_tree},
            "exact accepted FD03 HEAD/TREE",
        ),
        (
            "FD06 uppercase accepted FD03 head",
            {"base_head": PINNED_FD06_BASE_HEAD.upper()},
            "base HEAD",
        ),
        (
            "FD06 unexpected external pin",
            {"fd05_accepted_head": PINNED_R0_BASE_HEAD},
            "does not accept external pin arguments",
        ),
    )
    for label, overrides, expected_error in invalid_fd06_contracts:
        candidate = {**valid_fd06, **overrides}
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

    if len(ACTIVE_FD06_ALLOWLIST) != FD06_EXACT_PATH_COUNT:
        raise VerificationError("FD06 exact allowlist constant is not ten paths")
    _require_changed_path_contract(
        active_slice="FD06",
        changed=ACTIVE_FD06_ALLOWLIST,
        allowlist=ACTIVE_FD06_ALLOWLIST,
        exact_changed_paths=True,
    )
    fd06_path_negative_cases = 0
    for label, changed, expected_error in (
        (
            "FD06 eleventh path",
            ACTIVE_FD06_ALLOWLIST | {"software/conflict_analysis/domain/models.py"},
            "outside ACTIVE FD06 EXACT ALLOWLIST",
        ),
        (
            "FD06 missing bootstrap reconciliation",
            ACTIVE_FD06_ALLOWLIST
            - {
                "software/conflict_analysis/domain/tests/"
                "test_foundation_studio_bootstrap.py"
            },
            "FD06 changed paths must equal",
        ),
    ):
        fd06_path_negative_cases += 1
        try:
            _require_changed_path_contract(
                active_slice="FD06",
                changed=changed,
                allowlist=ACTIVE_FD06_ALLOWLIST,
                exact_changed_paths=True,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason: {exc}"
                ) from exc
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    _resolve_fd06_route(
        event_name="push",
        event_ref=f"refs/heads/{FD06_TARGET_BRANCH}",
    )
    _resolve_fd06_route(
        event_name="pull_request",
        head_ref=FD06_TARGET_BRANCH,
        base_ref=FD06_BASE_BRANCH,
    )
    fd06_route_negative_cases = 0
    for route in (
        {"event_name": "push", "event_ref": f"refs/heads/{FD06_BASE_BRANCH}"},
        {
            "event_name": "pull_request",
            "head_ref": FD06_TARGET_BRANCH,
            "base_ref": "main",
        },
        {
            "event_name": "pull_request",
            "head_ref": FD06_BASE_BRANCH,
            "base_ref": FD06_BASE_BRANCH,
        },
        {"event_name": "workflow_dispatch"},
    ):
        fd06_route_negative_cases += 1
        try:
            _resolve_fd06_route(**route)
        except VerificationError as exc:
            if "FD06 routing accepts only" not in str(exc):
                raise VerificationError(
                    "offline FD06 routing self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                "offline FD06 routing self-check accepted an invalid route"
            )

    _require_fd06_static_contract(
        exact_path_count=len(ACTIVE_FD06_ALLOWLIST),
        portable_count=len(FD06_PORTABLE_METHODS),
        concurrency_count=len(FD06_CONCURRENCY_METHODS),
        postgresql_total=FD06_POSTGRESQL_TOTAL,
        postgresql_skipped=FD06_POSTGRESQL_SKIPPED,
        sqlite_passed=FD06_SQLITE_PASSED,
        sqlite_skipped=FD06_SQLITE_SKIPPED,
    )
    fd06_static_negative_cases = 0
    valid_fd06_static = {
        "exact_path_count": FD06_EXACT_PATH_COUNT,
        "portable_count": 11,
        "concurrency_count": 4,
        "postgresql_total": FD06_POSTGRESQL_TOTAL,
        "postgresql_skipped": FD06_POSTGRESQL_SKIPPED,
        "sqlite_passed": FD06_SQLITE_PASSED,
        "sqlite_skipped": FD06_SQLITE_SKIPPED,
    }
    for field, invalid_value in (
        ("exact_path_count", 9),
        ("portable_count", 12),
        ("concurrency_count", 3),
        ("postgresql_total", 226),
        ("postgresql_skipped", 1),
        ("sqlite_passed", 211),
        ("sqlite_skipped", 14),
    ):
        fd06_static_negative_cases += 1
        try:
            _require_fd06_static_contract(
                **{**valid_fd06_static, field: invalid_value}
            )
        except VerificationError as exc:
            if "FD06 static path/test total contract drifted" not in str(exc):
                raise VerificationError(
                    f"offline FD06 {field} self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD06 {field} self-check accepted drift"
            )

    _require_fd06_frozen_contract(
        exact_frozen_objects=dict(FD06_EXACT_FROZEN_OBJECTS),
        reopened_base_blobs=dict(FD06_REOPENED_BASE_BLOBS),
    )
    fd06_frozen_negative_cases = 0
    for label, frozen, reopened, expected_error in (
        (
            "frozen model blob",
            {
                **FD06_EXACT_FROZEN_OBJECTS,
                "software/conflict_analysis/domain/models.py": other_head,
            },
            dict(FD06_REOPENED_BASE_BLOBS),
            "exact frozen-object contract drifted",
        ),
        (
            "reopened URL base blob",
            dict(FD06_EXACT_FROZEN_OBJECTS),
            {
                **FD06_REOPENED_BASE_BLOBS,
                "software/conflict_analysis/domain/urls.py": other_head,
            },
            "reopened base-blob contract drifted",
        ),
    ):
        fd06_frozen_negative_cases += 1
        try:
            _require_fd06_frozen_contract(
                exact_frozen_objects=frozen,
                reopened_base_blobs=reopened,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline FD06 {label} self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD06 {label} self-check accepted drift"
            )

    def render_test_class(class_name: str, methods: tuple[str, ...]) -> str:
        method_source = "".join(
            f"    def {method}(self):\n        pass\n" for method in methods
        )
        return f"class {class_name}:\n{method_source}"

    _require_exact_test_topology(
        source=render_test_class(FD06_PORTABLE_CLASS, FD06_PORTABLE_METHODS),
        class_name=FD06_PORTABLE_CLASS,
        expected_methods=FD06_PORTABLE_METHODS,
    )
    _require_exact_test_topology(
        source=render_test_class(FD06_CONCURRENCY_CLASS, FD06_CONCURRENCY_METHODS),
        class_name=FD06_CONCURRENCY_CLASS,
        expected_methods=FD06_CONCURRENCY_METHODS,
    )
    fd06_topology_negative_cases = 0
    for class_name, actual_methods, expected_methods in (
        (
            FD06_PORTABLE_CLASS,
            FD06_PORTABLE_METHODS[:-1],
            FD06_PORTABLE_METHODS,
        ),
        (
            FD06_CONCURRENCY_CLASS,
            tuple(reversed(FD06_CONCURRENCY_METHODS)),
            FD06_CONCURRENCY_METHODS,
        ),
    ):
        fd06_topology_negative_cases += 1
        try:
            _require_exact_test_topology(
                source=render_test_class(class_name, actual_methods),
                class_name=class_name,
                expected_methods=expected_methods,
            )
        except VerificationError as exc:
            if "test topology mismatch" not in str(exc):
                raise VerificationError(
                    "offline FD06 topology self-check failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                "offline FD06 topology self-check accepted registry drift"
            )

    delivery_head = "e" * 40
    _require_merge_free("FD06", ())
    valid_fd06_history = {
        "commit_count": 2,
        "delivery_head": delivery_head,
        "delivery_parent": PINNED_FD06_RC4_INTERMEDIATE_HEAD,
        "intermediate_parent": PINNED_FD06_BASE_HEAD,
        "intermediate_tree": PINNED_FD06_RC4_INTERMEDIATE_TREE,
        "ordered_commits": (PINNED_FD06_RC4_INTERMEDIATE_HEAD, delivery_head),
    }
    _require_fd06_rc5_public_history(**valid_fd06_history)
    fd06_history_negative_cases = 0
    try:
        _require_merge_free("FD06", ("synthetic-merge-object",))
    except VerificationError as exc:
        if "merge commits are forbidden after the exact FD06 base" not in str(exc):
            raise VerificationError(
                "offline FD06 merge-topology self-check failed for the wrong reason"
            ) from exc
        fd06_history_negative_cases += 1
    else:
        raise VerificationError("offline self-check accepted an FD06 merge commit")
    for label, overrides in (
        ("FD06 squashed history", {"commit_count": 1}),
        ("FD06 extra commit", {"commit_count": 3}),
        ("FD06 wrong delivery parent", {"delivery_parent": other_head}),
        ("FD06 wrong intermediate parent", {"intermediate_parent": other_head}),
        ("FD06 wrong intermediate tree", {"intermediate_tree": other_tree}),
        (
            "FD06 replaced intermediate",
            {"ordered_commits": (other_head, delivery_head)},
        ),
        (
            "FD06 wrong ordered delivery",
            {
                "ordered_commits": (
                    PINNED_FD06_RC4_INTERMEDIATE_HEAD,
                    other_head,
                )
            },
        ),
    ):
        try:
            _require_fd06_rc5_public_history(
                **{**valid_fd06_history, **overrides}  # type: ignore[arg-type]
            )
        except VerificationError as exc:
            if "FD06 RC5 public history must preserve" not in str(exc):
                raise VerificationError(
                    f"offline self-check {label!r} failed for the wrong reason"
                ) from exc
            fd06_history_negative_cases += 1
        else:
            raise VerificationError(
                f"offline self-check unexpectedly accepted {label!r}"
            )

    delivery_tree = "f" * 40
    _require_synthetic_merge_contract(
        expected_base_head=PINNED_FD06_BASE_HEAD,
        expected_delivery_head=delivery_head,
        actual_parents=(PINNED_FD06_BASE_HEAD, delivery_head),
        delivery_tree=delivery_tree,
        synthetic_tree=delivery_tree,
        independent_tree=delivery_tree,
    )
    fd06_synthetic_negative_cases = 0
    for label, parents, synthetic_tree, independent_tree, expected_error in (
        (
            "reversed parents",
            (delivery_head, PINNED_FD06_BASE_HEAD),
            delivery_tree,
            delivery_tree,
            "synthetic merge parents",
        ),
        (
            "synthetic tree drift",
            (PINNED_FD06_BASE_HEAD, delivery_head),
            other_tree,
            delivery_tree,
            "trees must be equal",
        ),
        (
            "independent merge-tree drift",
            (PINNED_FD06_BASE_HEAD, delivery_head),
            delivery_tree,
            other_tree,
            "trees must be equal",
        ),
    ):
        fd06_synthetic_negative_cases += 1
        try:
            _require_synthetic_merge_contract(
                expected_base_head=PINNED_FD06_BASE_HEAD,
                expected_delivery_head=delivery_head,
                actual_parents=parents,
                delivery_tree=delivery_tree,
                synthetic_tree=synthetic_tree,
                independent_tree=independent_tree,
            )
        except VerificationError as exc:
            if expected_error not in str(exc):
                raise VerificationError(
                    f"offline FD06 synthetic {label} failed for the wrong reason"
                ) from exc
        else:
            raise VerificationError(
                f"offline FD06 synthetic {label} was unexpectedly accepted"
            )

    return {
        "marker": "PRODUCTION_STUDIO_R0_VERIFIER_SELF_CHECK=PASS",
        "c1_marker": "PRODUCTION_STUDIO_C1_VERIFIER_SELF_CHECK=PASS",
        "fd02_marker": "FOUNDATION_FD02_VERIFIER_SELF_CHECK=PASS",
        "fd03_marker": "FOUNDATION_FD03_RC2_VERIFIER_SELF_CHECK=PASS",
        "fd06_marker": "FOUNDATION_FD06_VERIFIER_SELF_CHECK=PASS",
        "network_access": False,
        "repository_access": False,
        "positive_slices": [
            c0["active_slice"],
            r0["active_slice"],
            c1["active_slice"],
            fd02["active_slice"],
            fd03["active_slice"],
            fd06["active_slice"],
        ],
        "negative_cases": (
            len(invalid_contracts)
            + len(invalid_c1_contracts)
            + path_negative_cases
            + 2
            + len(invalid_fd02_contracts)
            + fd02_path_negative_cases
            + 3
            + len(invalid_fd06_contracts)
            + fd06_path_negative_cases
            + fd06_route_negative_cases
            + fd06_static_negative_cases
            + fd06_frozen_negative_cases
            + fd06_topology_negative_cases
            + fd06_history_negative_cases
            + fd06_synthetic_negative_cases
            + len(invalid_fd03_contracts)
            + fd03_path_negative_cases
            + 3
        ),
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

    if active_slice == "C1":
        accepted_head = contract["fd05_accepted_head"]
        accepted_tree = contract["fd05_accepted_tree"]
        if not isinstance(accepted_head, str) or not isinstance(accepted_tree, str):
            raise VerificationError("internal C1 FD05 accepted-pin contract is invalid")
        resolved_accepted_tree = _git(
            repo,
            "rev-parse",
            f"{accepted_head}^{{tree}}",
        )
        if resolved_accepted_tree != accepted_tree:
            raise VerificationError(
                "FD05 accepted tree mismatch: "
                f"expected {accepted_tree}, resolved {resolved_accepted_tree}"
            )
        if _git(repo, "merge-base", accepted_head, base_head) != accepted_head:
            raise VerificationError(
                "the exact C1 R0 START is not a descendant of accepted FD05 H2"
            )
        accepted_to_start_merges = tuple(
            item
            for item in _git(
                repo,
                "rev-list",
                "--merges",
                f"{accepted_head}..{base_head}",
            ).splitlines()
            if item
        )
        _require_merge_free("C1 accepted H2-to-R0 START", accepted_to_start_merges)

    if active_slice in {"R0", "C1", "FD02", "FD03", "FD06"}:
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
        _require_merge_free(active_slice, merge_commits)

    delivery_commit_count: int | None = None
    delivery_parent: str | None = None
    fd06_intermediate_parent: str | None = None
    fd06_intermediate_tree: str | None = None
    fd06_ordered_commits: tuple[str, ...] | None = None
    if active_slice in {"FD02", "FD03", "FD06"}:
        delivery_commit_count = int(
            _git(repo, "rev-list", "--count", f"{base_head}..HEAD")
        )
        delivery_parent = _git(repo, "rev-parse", "HEAD^")
        if active_slice == "FD02":
            _require_single_fast_forward_commit(
                active_slice=active_slice,
                commit_count=delivery_commit_count,
                delivery_parent=delivery_parent,
                base_head=base_head,
            )
        elif active_slice == "FD06":
            fd06_intermediate_parent = _git(
                repo,
                "rev-parse",
                f"{PINNED_FD06_RC4_INTERMEDIATE_HEAD}^",
            )
            fd06_intermediate_tree = _git(
                repo,
                "rev-parse",
                f"{PINNED_FD06_RC4_INTERMEDIATE_HEAD}^{{tree}}",
            )
            fd06_ordered_commits = tuple(
                item
                for item in _git(
                    repo,
                    "rev-list",
                    "--reverse",
                    f"{base_head}..HEAD",
                ).splitlines()
                if item
            )
            if (
                _git(repo, "merge-base", PINNED_FD06_RC4_INTERMEDIATE_HEAD, "HEAD")
                != PINNED_FD06_RC4_INTERMEDIATE_HEAD
            ):
                raise VerificationError(
                    "FD06 RC5 HEAD is not a descendant of the exact RC4 intermediate"
                )
            _require_fd06_rc5_public_history(
                commit_count=delivery_commit_count,
                delivery_head=_git(repo, "rev-parse", "HEAD"),
                delivery_parent=delivery_parent,
                intermediate_parent=fd06_intermediate_parent,
                intermediate_tree=fd06_intermediate_tree,
                ordered_commits=fd06_ordered_commits,
            )
        else:
            if (
                _git(repo, "rev-parse", f"{PINNED_FD03_RC2_START_HEAD}^{{tree}}")
                != PINNED_FD03_RC2_START_TREE
                or _git(repo, "rev-parse", f"{PINNED_FD03_RC2_START_HEAD}^")
                != base_head
                or _git(repo, "merge-base", PINNED_FD03_RC2_START_HEAD, "HEAD")
                != PINNED_FD03_RC2_START_HEAD
            ):
                raise VerificationError(
                    "FD03 RC2 start HEAD/TREE/parent/ancestry drifted from authorization"
                )
            _require_fd03_rc2_fast_forward(
                commit_count=delivery_commit_count,
                delivery_parent=delivery_parent,
            )

    changed = _changed_paths(repo, base_head)
    allowlist = contract["allowlist"]
    if not isinstance(allowlist, frozenset):
        raise VerificationError("internal slice allowlist contract is invalid")
    exact_changed_paths = contract["exact_changed_paths"]
    if not isinstance(exact_changed_paths, bool):
        raise VerificationError("internal exact changed-path contract is invalid")
    _require_changed_path_contract(
        active_slice=active_slice,
        changed=changed,
        allowlist=allowlist,
        exact_changed_paths=exact_changed_paths,
    )
    aggregate_changed: set[str] | None = None
    if active_slice == "FD03":
        aggregate_changed = _changed_paths(repo, PINNED_FD02_BASE_HEAD)
        _require_changed_path_contract(
            active_slice="FD03_AGGREGATE",
            changed=aggregate_changed,
            allowlist=FD03_AGGREGATE_ALLOWLIST,
            exact_changed_paths=True,
        )

    domain_prefix = "software/conflict_analysis/domain/"
    changed_domain = sorted(path for path in changed if path.startswith(domain_prefix))
    if active_slice not in {"FD02", "FD03", "FD06"} and changed_domain:
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
    if active_slice not in {"FD02", "FD03", "FD06"} and _git(
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
    elif active_slice == "C1":
        for path in C1_FROZEN_PATHS:
            start_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if head_object != start_object:
                raise VerificationError(
                    f"C1 frozen object drift at {path}: "
                    f"R0 start {start_object}, HEAD {head_object}"
                )
            frozen_objects[path] = start_object
    elif active_slice == "FD02":
        for path in FD02_FROZEN_PATHS:
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if head_object != base_object:
                raise VerificationError(
                    f"FD02 frozen object drift at {path}: "
                    f"accepted C1 {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = base_object
    elif active_slice == "FD03":
        for path in FD03_FROZEN_PATHS:
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if head_object != base_object:
                raise VerificationError(
                    f"FD03 frozen object drift at {path}: "
                    f"accepted FD02 {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = base_object

        domain_test_path = (
            "software/conflict_analysis/domain/tests/test_foundation_studio_http.py"
        )
        _require_exact_test_topology(
            source=(repo / domain_test_path).read_text(encoding="utf-8"),
            class_name=FD03_TEST_CLASS,
            expected_methods=FD03_TEST_METHODS,
        )

        c0_test_path = (
            "software/conflict_analysis/production_studio/tests/test_read_only_http.py"
        )
        base_c0_source = _git(repo, "show", f"{base_head}:{c0_test_path}")
        head_c0_source = (repo / c0_test_path).read_text(encoding="utf-8")
        if base_c0_source == head_c0_source:
            raise VerificationError("FD03 bounded C0 assertion node was not updated")
        if _normalized_authorized_method_body(
            base_c0_source,
            class_name=FD03_C0_CLASS,
            method_name=FD03_C0_METHOD,
        ) != _normalized_authorized_method_body(
            head_c0_source,
            class_name=FD03_C0_CLASS,
            method_name=FD03_C0_METHOD,
        ):
            raise VerificationError(
                "FD03 changed production_studio test bytes outside the one authorized C0 node body"
            )
    elif active_slice == "FD06":
        _require_fd06_static_contract(
            exact_path_count=len(ACTIVE_FD06_ALLOWLIST),
            portable_count=len(FD06_PORTABLE_METHODS),
            concurrency_count=len(FD06_CONCURRENCY_METHODS),
            postgresql_total=FD06_POSTGRESQL_TOTAL,
            postgresql_skipped=FD06_POSTGRESQL_SKIPPED,
            sqlite_passed=FD06_SQLITE_PASSED,
            sqlite_skipped=FD06_SQLITE_SKIPPED,
        )
        _require_fd06_frozen_contract(
            exact_frozen_objects=dict(FD06_EXACT_FROZEN_OBJECTS),
            reopened_base_blobs=dict(FD06_REOPENED_BASE_BLOBS),
        )
        for path, expected_object in FD06_EXACT_FROZEN_OBJECTS.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            head_object = _git(repo, "rev-parse", f"HEAD:{path}")
            if base_object != expected_object or head_object != expected_object:
                raise VerificationError(
                    f"FD06 frozen object drift at {path}: expected "
                    f"{expected_object}, base {base_object}, HEAD {head_object}"
                )
            frozen_objects[path] = expected_object
        for path, expected_object in FD06_REOPENED_BASE_BLOBS.items():
            base_object = _git(repo, "rev-parse", f"{base_head}:{path}")
            if base_object != expected_object:
                raise VerificationError(
                    f"FD06 reopened base blob drift at {path}: expected "
                    f"{expected_object}, got {base_object}"
                )
        test_source = (
            repo / "software/conflict_analysis/domain/tests/test_foundation_studio_publication_reconciliation.py"
        ).read_text(encoding="utf-8")
        _require_exact_test_topology(
            source=test_source,
            class_name=FD06_PORTABLE_CLASS,
            expected_methods=FD06_PORTABLE_METHODS,
        )
        _require_exact_test_topology(
            source=test_source,
            class_name=FD06_CONCURRENCY_CLASS,
            expected_methods=FD06_CONCURRENCY_METHODS,
        )

        for path, class_name, method_name in (
            (
                "software/conflict_analysis/domain/tests/"
                "test_foundation_studio_http.py",
                FD06_HTTP_BOUNDED_CLASS,
                FD06_HTTP_BOUNDED_METHOD,
            ),
            (
                "software/conflict_analysis/domain/tests/"
                "test_foundation_studio_bootstrap.py",
                FD06_BOOTSTRAP_BOUNDED_CLASS,
                FD06_BOOTSTRAP_BOUNDED_METHOD,
            ),
        ):
            base_source = _git(repo, "show", f"{base_head}:{path}")
            head_source = (repo / path).read_text(encoding="utf-8")
            if base_source == head_source:
                raise VerificationError(
                    f"FD06 bounded regression node was not updated at {path}"
                )
            if _normalized_authorized_method_body(
                base_source,
                class_name=class_name,
                method_name=method_name,
            ) != _normalized_authorized_method_body(
                head_source,
                class_name=class_name,
                method_name=method_name,
            ):
                raise VerificationError(
                    f"FD06 changed {path} outside the one authorized method body"
                )

    return {
        "active_slice": active_slice,
        "allowlist_result": "PASS",
        "base_head": base_head,
        "base_tree": base_tree,
        "changed_paths": sorted(changed),
        "aggregate_changed_paths": (
            sorted(aggregate_changed) if aggregate_changed is not None else None
        ),
        "domain_tree": domain_tree,
        "delivery_commit_count": delivery_commit_count,
        "delivery_parent": delivery_parent,
        "fd06_rc4_intermediate_head": (
            PINNED_FD06_RC4_INTERMEDIATE_HEAD if active_slice == "FD06" else None
        ),
        "fd06_rc4_intermediate_parent": fd06_intermediate_parent,
        "fd06_rc4_intermediate_tree": fd06_intermediate_tree,
        "fd06_ordered_delivery_commits": (
            list(fd06_ordered_commits)
            if fd06_ordered_commits is not None
            else None
        ),
        "fd06_public_history_exception": (
            "EXACT_RC4_INTERMEDIATE_PLUS_ONE_CHILD"
            if active_slice == "FD06"
            else None
        ),
        "domain_changed_paths": changed_domain,
        "domain_tree_unchanged": (
            None if active_slice in {"FD02", "FD03", "FD06"} else True
        ),
        "exact_changed_paths": changed == allowlist if exact_changed_paths else None,
        "fd05_base_pin": contract["fd05_base_pin"],
        "fd05_accepted_head": contract["fd05_accepted_head"],
        "fd05_accepted_tree": contract["fd05_accepted_tree"],
        "frozen_objects": frozen_objects,
        "merge_commits_absent": (
            True if active_slice in {"R0", "C1", "FD02", "FD03", "FD06"} else None
        ),
        "migration_filenames_unchanged": True,
        "r0_start_pin": contract["r0_start_pin"],
        "c1_base_pin": contract["c1_base_pin"],
        "fd02_base_pin": contract["fd02_base_pin"],
        "fd03_test_node_count": len(FD03_TEST_METHODS) if active_slice == "FD03" else None,
        "fd03_c0_bounded_node_only": True if active_slice == "FD03" else None,
        "fd06_exact_path_count": (
            len(ACTIVE_FD06_ALLOWLIST) if active_slice == "FD06" else None
        ),
        "fd06_portable_test_node_count": (
            len(FD06_PORTABLE_METHODS) if active_slice == "FD06" else None
        ),
        "fd06_postgresql_only_test_node_count": (
            len(FD06_CONCURRENCY_METHODS) if active_slice == "FD06" else None
        ),
        "fd06_postgresql_expected": (
            {
                "passed": FD06_POSTGRESQL_TOTAL,
                "skipped": FD06_POSTGRESQL_SKIPPED,
            }
            if active_slice == "FD06"
            else None
        ),
        "fd06_sqlite_expected": (
            {"passed": FD06_SQLITE_PASSED, "skipped": FD06_SQLITE_SKIPPED}
            if active_slice == "FD06"
            else None
        ),
        "fd06_synthetic_merge_requirement": (
            {
                "parents": [base_head, "FINAL_FD06_HEAD"],
                "tree": "FINAL_FD06_TREE_EQUALS_INDEPENDENT_MERGE_TREE",
            }
            if active_slice == "FD06"
            else None
        ),
        "aggregate_exact_changed_paths": (
            aggregate_changed == FD03_AGGREGATE_ALLOWLIST
            if aggregate_changed is not None
            else None
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--slice",
        choices=("C0", "R0", "C1", "FD02", "FD03", "FD06"),
        default="C0",
    )
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
        print(result["c1_marker"])
        print(result["fd02_marker"])
        print(result["fd03_marker"])
        print(result["fd06_marker"])
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
