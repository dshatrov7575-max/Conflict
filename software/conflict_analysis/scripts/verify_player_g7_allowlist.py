#!/usr/bin/env python3
"""Verify the bounded G7 Professional Player delivery contract.

The verifier is deliberately Git- and source-oriented.  It does not claim a
runtime or cloud-CI result; the workflow supplies those independently.  Its
job is to reject an incorrect parent, topology, frozen-parent drift, package
scope drift, and the security boundary regressions that can be checked without
executing an HTTP request.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import sys
import tomllib
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory


FD08_ACCEPTED_HEAD = "68b14882a06b2e90710ebd06e584dc5300fdfe7e"
FD08_ACCEPTED_TREE = "5969ee705ae935bf305a1b2531bc3bc77ade03cb"
F1_ACCEPTED_HEAD = "d2f5a881e10dbb688371e8c5add6bf9375404738"
F1_ACCEPTED_TREE = "7f5fd4f321282a48a799698861ce6f2bd3940cd1"
FD08_BASE_BRANCH = "codex/ca-suite-i1-foundation-fd08-assessment-projection"
G7_TARGET_BRANCH = "codex/ca-suite-i1-player-g7-professional-shell"

WORKFLOW_PATH = ".github/workflows/conflict-analysis.yml"
README_PATH = "software/conflict_analysis/README.md"
PYPROJECT_PATH = "software/conflict_analysis/pyproject.toml"
SETTINGS_PATH = "software/conflict_analysis/conflict_analysis/settings.py"
ROOT_URLS_PATH = "software/conflict_analysis/conflict_analysis/urls.py"
DOMAIN_URLS_PATH = "software/conflict_analysis/domain/urls.py"
ADR_PATH = "software/conflict_analysis/docs/adr/0014-production-player-g7.md"
RUNTIME_DOC_PATH = "software/conflict_analysis/docs/production-player-g7-runtime.md"
PLAYER_API_PATH = "software/conflict_analysis/domain/api/player.py"
PLAYER_WORKSPACES_PATH = "software/conflict_analysis/domain/services/player_workspaces.py"
PLAYER_HELP_CATALOG_PATH = "software/conflict_analysis/domain/services/player_help_catalog.py"
PLAYER_HELP_COMMAND_PATH = "software/conflict_analysis/domain/management/commands/provision_player_help.py"
FOUNDATION_TEST_PATH = "software/conflict_analysis/domain/tests/test_player_foundation.py"
HELP_TEST_PATH = "software/conflict_analysis/domain/tests/test_player_help_provisioning.py"
PLAYER_PACKAGE = "software/conflict_analysis/production_player"
PLAYER_TEST_PATH = f"{PLAYER_PACKAGE}/tests/test_player_g7.py"
PLAYER_BROWSER_PATH = f"{PLAYER_PACKAGE}/browser_tests/player_g7.mjs"
VERIFIER_PATH = "software/conflict_analysis/scripts/verify_player_g7_allowlist.py"

MODIFIED_PATHS = frozenset(
    {
        WORKFLOW_PATH,
        README_PATH,
        PYPROJECT_PATH,
        SETTINGS_PATH,
        ROOT_URLS_PATH,
        DOMAIN_URLS_PATH,
    }
)
NEW_PATHS = frozenset(
    {
        ADR_PATH,
        RUNTIME_DOC_PATH,
        PLAYER_API_PATH,
        PLAYER_WORKSPACES_PATH,
        PLAYER_HELP_CATALOG_PATH,
        PLAYER_HELP_COMMAND_PATH,
        FOUNDATION_TEST_PATH,
        HELP_TEST_PATH,
        f"{PLAYER_PACKAGE}/__init__.py",
        f"{PLAYER_PACKAGE}/apps.py",
        f"{PLAYER_PACKAGE}/claim_boundaries.py",
        f"{PLAYER_PACKAGE}/contracts/player_g7_claim_boundaries_v1.ru.json",
        f"{PLAYER_PACKAGE}/contracts/player_g7_claim_boundaries_v1.ru.json.sha256",
        f"{PLAYER_PACKAGE}/static/production_player/player.css",
        f"{PLAYER_PACKAGE}/static/production_player/player.js",
        f"{PLAYER_PACKAGE}/templates/production_player/entry.html",
        f"{PLAYER_PACKAGE}/templates/production_player/project.html",
        f"{PLAYER_PACKAGE}/templates/production_player/workspace.html",
        PLAYER_TEST_PATH,
        PLAYER_BROWSER_PATH,
        f"{PLAYER_PACKAGE}/urls.py",
        f"{PLAYER_PACKAGE}/views.py",
        VERIFIER_PATH,
    }
)
ALLOWLIST = MODIFIED_PATHS | NEW_PATHS

PREIMAGE_BLOBS = {
    WORKFLOW_PATH: "95c0c590c7e2e84b2d54750649dc0b3d05c75d22",
    README_PATH: "9b7cc61e3776b9dd0c82a3cc2d665300918feb67",
    PYPROJECT_PATH: "3a4705d5b016aaabbfc66899db852a77eed30b9e",
    SETTINGS_PATH: "2fb106c3802d306556ff4f7d18b805b90fd1fcc6",
    ROOT_URLS_PATH: "52377cfd6eae7447602e702e3827ef89dc0da267",
    DOMAIN_URLS_PATH: "6a2429ef06848e52ecc71b208c53139549e0be1d",
}
FROZEN_PARENT_BLOBS = {
    "software/conflict_analysis/domain/services/foundation_packages.py": "799b849f998396ca5a9a9b1ec1d1035d6926c7f5",
    "software/conflict_analysis/domain/services/schemas/foundation-package-2.2.0.schema.json": "fa5f8ca3db4c0c2d8867d88610df9a7ff07626a7",
    "software/conflict_analysis/domain/api/evidence.py": "ca9ff9ada30996a52f5981254e1d368b4035c783",
    "software/conflict_analysis/domain/services/evidence_drilldown.py": "b7f4345d154858b00b9983904762abb371f00311",
    "software/conflict_analysis/domain/migrations/0018_workspace_assessment_projection.py": "292a8eb4abafeef80d6efc7d3c2d4cda5f771fd9",
    "software/conflict_analysis/production_studio/browser_tests/audited_authoring.mjs": "f6ad2ff633d9c49ae4e5c69d5fff931b677e8af3",
    "software/conflict_analysis/production_studio/browser_tests/cdp_client.mjs": "685faeb3906a0f74815549e272748125bb6fbf65",
    "software/conflict_analysis/domain/models.py": "f92d07d187e03cd51ba9405c067029df12d7189e",
    "software/conflict_analysis/domain/enums.py": "dd50f597199711bfa66d37fc40e8908f9ea9879b",
    "software/conflict_analysis/domain/migrations": "19a5680696d79074c3c41e49a6732c01ec3314ac",
    "software/conflict_analysis/domain/services/player_projection.py": "1455939048c784fb75ec7a1ed2e16a6025bf4fbc",
    "software/conflict_analysis/domain/services/help_topics.py": "268a6d5eac0aa7f42ca3039a223877388f70dd3d",
    "software/conflict_analysis/production_studio": "3292e89b30c0b9f01029b897b18fe25e24a4feda",
}

FOUNDATION_PORTABLE_NODES = (
    "test_player_permission_family_session_scope_and_no_studio_mixing_are_exact",
    "test_definition_list_returns_only_scoped_published_current_and_noncurrent_versions",
    "test_definition_open_hides_draft_validated_foreign_and_absent_with_zero_writes",
    "test_workspace_list_open_and_manifest_pin_truth_are_exact",
    "test_workspace_create_requires_exact_key_if_match_body_nondefault_and_published_definition",
    "test_workspace_fresh_replay_key_reuse_identity_conflict_and_rollback_are_exact",
    "test_workspace_pin_and_default_workspace_cannot_be_reassigned_or_mutated",
    "test_time_slice_list_and_create_require_exact_workspace_project_and_pin",
    "test_time_slice_fresh_replay_key_reuse_date_code_conflict_and_rollback_are_exact",
    "test_persisted_time_slice_has_no_update_delete_or_metadata_hiding_path",
    "test_experiment_list_is_dynamic_read_only_and_modeling_is_never_an_action",
    "test_player_help_is_exact_versioned_sanitized_and_scope_hidden",
)
POSTGRESQL_ONLY_NODES = (
    "test_concurrent_workspace_same_key_and_competing_identity_have_one_graph_and_typed_loser",
    "test_concurrent_time_slice_same_key_and_competing_date_have_one_slice_and_typed_loser",
)
PRODUCT_NODES = (
    "test_routes_auth_claim_contract_and_separate_player_app_are_exact",
    "test_onboarding_and_context_help_use_full_terms_while_dense_workspace_has_no_persistent_explanatory_prose",
    "test_project_page_opens_only_foundation_published_definition_truth",
    "test_workspace_create_and_reopen_use_only_foundation_receipt_and_pin",
    "test_time_slice_create_reopen_and_persisted_immutability_are_truthful",
    "test_structure_tree_is_arbitrary_cardinality_read_only_and_dom_bounded",
    "test_general_dynamic_experiment_plus_tabs_have_no_values_or_aggregation",
    "test_focus_aware_icon_toolbar_has_no_in_panel_commands_and_exposes_exact_disabled_boundaries",
    "test_mouse_keyboard_splitters_bounded_layout_and_narrow_status_bar_are_exact",
    "test_help_and_method_state_are_exact_no_beta_claim_without_strategy_and_no_domain_persistence",
)
CHROMIUM_NODES = (
    "test_chromium_player_open_published_create_workspace_slice_reload_and_role_negative_matrix",
    "test_chromium_player_professional_toolbar_splitters_dynamic_tabs_help_storage_and_no_structure_mutation",
)

SHA1_RE = re.compile(r"^[0-9a-f]{40}$")


class VerificationError(RuntimeError):
    """Raised for a bounded-G7 delivery mismatch."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def require_sha(value: str, label: str) -> None:
    require(bool(SHA1_RE.fullmatch(value)), f"{label} must be lowercase 40-hex")


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode:
        raise VerificationError(
            f"git {' '.join(args)} failed: {completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout.strip()


def source(repo: Path, path: str) -> str:
    candidate = repo / PurePosixPath(path)
    require(candidate.is_file(), f"required source file is missing: {path}")
    return candidate.read_text(encoding="utf-8")


def source_tokens(repo: Path, path: str, tokens: Iterable[str]) -> None:
    text = source(repo, path)
    missing = [token for token in tokens if token not in text]
    require(not missing, f"{path} is missing required contract tokens: {', '.join(missing)}")


def parse_name_status(output: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in filter(None, output.splitlines()):
        status, path = line.split("\t", 1)
        require(status in {"A", "M"}, f"unsupported path status {status!r} for {path}")
        require(path not in result, f"duplicate changed path: {path}")
        result[path] = status
    return result


def definition_method_names(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            names.append(node.name)
    return tuple(names)


def assert_test_registry_names(
    *, foundation: tuple[str, ...], product: tuple[str, ...], help_source: str
) -> None:
    require(
        foundation == FOUNDATION_PORTABLE_NODES + POSTGRESQL_ONLY_NODES,
        "Foundation G7 test registry must be the literal ordered 12+2 node set",
    )
    require(product == PRODUCT_NODES + CHROMIUM_NODES, "Product G7 registry must be the literal ordered 10+2 node set")
    help_tree = ast.parse(help_source, filename=HELP_TEST_PATH)
    require(
        any(
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "__test__" for target in node.targets)
            and isinstance(node.value, ast.Constant)
            and node.value.value is False
            for node in help_tree.body
        ),
        "G7 Help provisioning helper must be explicitly non-collected",
    )


def assert_exact_test_registry(repo: Path) -> None:
    help_test = repo / HELP_TEST_PATH
    require(help_test.is_file(), "G7 Help provisioning helper must exist")
    assert_test_registry_names(
        foundation=definition_method_names(repo / FOUNDATION_TEST_PATH),
        product=definition_method_names(repo / PLAYER_TEST_PATH),
        help_source=help_test.read_text(encoding="utf-8"),
    )


def assert_topology_statuses(statuses: Mapping[str, str]) -> None:
    require(set(statuses) == ALLOWLIST, "G7 changed paths must be exactly the frozen 29-path allowlist")
    require(
        {path for path, status in statuses.items() if status == "M"} == MODIFIED_PATHS,
        "G7 must modify exactly the frozen six parent paths",
    )
    require(
        {path for path, status in statuses.items() if status == "A"} == NEW_PATHS,
        "G7 must add exactly the frozen 23 paths",
    )
    require(
        len(statuses) == 29 and len(MODIFIED_PATHS) == 6 and len(NEW_PATHS) == 23,
        "G7 topology must remain 6 modified + 23 new",
    )


def assert_allowed_topology(repo: Path, *, base_head: str) -> dict[str, str]:
    statuses = parse_name_status(git(repo, "diff", "--name-status", "--no-renames", base_head, "HEAD"))
    assert_topology_statuses(statuses)
    return statuses


def assert_parent(repo: Path, *, base_head: str, base_tree: str, git_reader=None) -> tuple[str, str, str]:
    read = git_reader or (lambda *args: git(repo, *args))
    require(base_head == FD08_ACCEPTED_HEAD, "G7 base HEAD must be the accepted FD08 head")
    require(base_tree == FD08_ACCEPTED_TREE, "G7 base TREE must be the accepted FD08 tree")
    require(read("rev-parse", f"{base_head}^{{tree}}") == base_tree, "accepted FD08 base tree does not resolve")
    require(read("rev-parse", f"{F1_ACCEPTED_HEAD}^{{tree}}") == F1_ACCEPTED_TREE, "accepted F1 tree drift")
    read("merge-base", "--is-ancestor", F1_ACCEPTED_HEAD, base_head)
    require(not read("status", "--porcelain=v1", "-uall"), "delivery verification requires a clean worktree")
    head = read("rev-parse", "HEAD")
    tree = read("rev-parse", "HEAD^{tree}")
    parents = read("show", "-s", "--format=%P", "HEAD").split()
    require(parents == [base_head], "G7 delivery must be one ordinary commit with accepted FD08 as sole parent")
    require(read("rev-list", "--count", f"{base_head}..HEAD") == "1", "G7 must be exactly one commit above FD08")
    require(not read("rev-list", "--merges", f"{base_head}..HEAD"), "G7 history must contain zero merges")
    return head, tree, parents[0]


def assert_frozen_parent_blobs(resolve_blob) -> None:
    for path, expected in PREIMAGE_BLOBS.items():
        require(resolve_blob(path) == expected, f"G7 modified preimage drift: {path}")
    for path, expected in FROZEN_PARENT_BLOBS.items():
        require(resolve_blob(path) == expected, f"G7 frozen parent drift: {path}")


def assert_frozen_parent(repo: Path, *, base_head: str, git_reader=None) -> None:
    read = git_reader or (lambda *args: git(repo, *args))
    assert_frozen_parent_blobs(lambda path: read("rev-parse", f"{base_head}:{path}"))
    for path, expected in FROZEN_PARENT_BLOBS.items():
        require(read("rev-parse", f"HEAD:{path}") == expected, f"frozen delivery anchor drift: {path}")


def assert_help_route_contract(*, api_source: str, urls_source: str) -> None:
    require(
        "def help_topic(request, workspace_id, ui_key)" in api_source,
        "Player Help must receive the exact workspace path identity",
    )
    require(
        'path("player/workspaces/<uuid:workspace_id>/help/<str:ui_key>/", player.help_topic' in urls_source,
        "Player Help route must bind exact workspace and UI-key identities",
    )
    require(
        'path("player/help/<str:ui_key>/", player.help_topic' not in urls_source,
        "Player Help must reject the obsolete unscoped route",
    )


def assert_service_write_boundary(workspaces: str) -> None:
    tree = ast.parse(workspaces)
    forbidden = {
        "bulk_create", "abulk_create", "bulk_update", "abulk_update", "update", "aupdate",
        "delete", "adelete", "asave", "raw", "execute", "executemany",
        "get_or_create", "aget_or_create", "update_or_create", "aupdate_or_create",
        "save_base", "_save_table", "_save_parents", "_do_insert", "_do_update",
        "_insert", "_update", "_raw_delete",
    }
    save_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            require(node.func.attr not in forbidden, f"G7 persisted write bypass: {node.func.attr}")
            if node.func.attr == "save":
                save_calls.append(node)
    proven = set()
    for block in ast.walk(tree):
        statements = getattr(block, "body", None)
        if not isinstance(statements, list):
            continue
        for previous, statement in zip(statements, statements[1:]):
            if not isinstance(statement, ast.Expr) or statement.value not in save_calls:
                continue
            call = statement.value
            require(isinstance(previous, ast.Assign) and len(previous.targets) == 1,
                    "save must immediately follow a new unsaved instance assignment")
            require(isinstance(previous.targets[0], ast.Name) and isinstance(call.func.value, ast.Name)
                    and previous.targets[0].id == call.func.value.id, "save receiver must be the new instance")
            constructor = previous.value
            require(isinstance(constructor, ast.Call) and isinstance(constructor.func, ast.Name)
                    and constructor.func.id in {"TimeSlice", "ProjectWorkspace"},
                    "save of an already persisted row is forbidden")
            require(not call.args and len(call.keywords) == 1 and call.keywords[0].arg == "force_insert"
                    and isinstance(call.keywords[0].value, ast.Constant)
                    and call.keywords[0].value.value is True, "instance save must be force_insert=True")
            proven.add(id(call))
    require({id(node) for node in save_calls} == proven, "every instance save must be proven fresh-only")


def assert_no_ctrl_r_intercept(player_js: str) -> None:
    require("Ctrl+R" not in player_js, "Player must not advertise a Ctrl+R interception")
    key = r"(?:['\"](?:r|keyr)['\"])"
    patterns = (
        re.compile(rf"ctrlkey.{{0,96}}{key}", re.IGNORECASE | re.DOTALL),
        re.compile(rf"{key}.{{0,96}}ctrlkey", re.IGNORECASE | re.DOTALL),
    )
    require(
        not any(pattern.search(player_js) for pattern in patterns),
        "Player must not intercept Ctrl+R",
    )


def assert_sources(repo: Path) -> None:
    for path in sorted(NEW_PATHS):
        require((repo / PurePosixPath(path)).is_file(), f"new G7 path is absent: {path}")
        require(not (repo / PurePosixPath(path)).is_symlink(), f"G7 symlink is forbidden: {path}")
    for path in sorted(MODIFIED_PATHS):
        require((repo / PurePosixPath(path)).is_file(), f"modified G7 path is absent: {path}")
        require(not (repo / PurePosixPath(path)).is_symlink(), f"G7 symlink is forbidden: {path}")

    assert_exact_test_registry(repo)
    source_tokens(
        repo,
        PLAYER_WORKSPACES_PATH,
        (
            "transaction.atomic",
            "select_for_update",
            "verify_workspace_assessment_projection",
            "require_complete_workspace_assessment_projection",
            "WORKSPACE_CREATE_CONTRACT",
            "FOUNDATION_PLAYER_TIME_SLICE_CREATE_V1",
            "canonical",
            "receipt",
        ),
    )
    workspaces = source(repo, PLAYER_WORKSPACES_PATH)
    require(
        "from domain.services.player_projection import" in workspaces
        and "WORKSPACE_CREATE_CONTRACT," in workspaces
        and "receipt_contract=WORKSPACE_CREATE_CONTRACT" in workspaces,
        "G7 Workspace service must import and pass the frozen FD08 receipt contract",
    )
    assert_service_write_boundary(workspaces)
    source_tokens(
        repo,
        PLAYER_API_PATH,
        (
            "_PlayerSessionAuthentication",
            "SessionAuthentication().enforce_csrf",
            "HTTP_IDEMPOTENCY_KEY",
            "HTTP_IF_MATCH",
            "create_player_workspace",
            "create_player_time_slice",
        ),
    )
    assert_help_route_contract(
        api_source=source(repo, PLAYER_API_PATH),
        urls_source=source(repo, DOMAIN_URLS_PATH),
    )
    source_tokens(
        repo,
        PLAYER_HELP_CATALOG_PATH,
        ("PLAYER", "locale", "version", "sha256", "UIHelpBinding"),
    )
    catalog = source(repo, PLAYER_HELP_CATALOG_PATH).lower()
    require("latest" not in catalog and "nearest" not in catalog, "G7 Help catalog must not select latest or nearest version")

    product_paths = sorted((repo / PLAYER_PACKAGE).rglob("*.py"))
    require(product_paths, "Production Player source package is missing")
    for path in product_paths:
        relative = path.relative_to(repo).as_posix()
        if "/tests/" in relative:
            continue
        text = path.read_text(encoding="utf-8")
        require("from domain.models import" not in text and "import domain.models" not in text, f"Product may not use ORM models directly: {relative}")
        require(".objects." not in text, f"Product may not issue direct ORM queries: {relative}")
    claim_source = source(repo, f"{PLAYER_PACKAGE}/contracts/player_g7_claim_boundaries_v1.ru.json")
    require("PLAYER_PRODUCT_SLICE_DELIVERED" in claim_source, "Product claims must identify G7 as a delivered slice")
    require("OWNER_PLAYER_PACKAGE_READY" not in claim_source and "COMPLETE_SUITE_ALPHA" not in claim_source, "Product must not claim a complete owner package")
    raw_claim = (repo / PLAYER_PACKAGE / "contracts/player_g7_claim_boundaries_v1.ru.json").read_bytes()
    constants = {
        node.target.id: node.value.value
        for node in ast.parse(source(repo, f"{PLAYER_PACKAGE}/claim_boundaries.py")).body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        and isinstance(node.value, ast.Constant)
    }
    claim_sha = hashlib.sha256(raw_claim).hexdigest()
    require(claim_sha == constants.get("CLAIM_BOUNDARY_CONTRACT_SHA256")
            and len(raw_claim) == constants.get("CLAIM_BOUNDARY_CONTRACT_BYTES"), "claim bytes/constants drift")
    require((repo / PLAYER_PACKAGE / "contracts/player_g7_claim_boundaries_v1.ru.json.sha256").read_bytes()
            == f"{claim_sha}  player_g7_claim_boundaries_v1.ru.json\n".encode("ascii"), "claim sidecar drift")
    player_js = source(repo, f"{PLAYER_PACKAGE}/static/production_player/player.js")
    require("conflict-analysis-player:layout:v1" in player_js, "Player must use the single bounded layout key")
    for forbidden in ("sessionStorage.setItem", "indexedDB.open", "caches.open", "serviceWorker.register"):
        require(forbidden not in player_js, f"Player browser persistence boundary violated: {forbidden}")
    assert_no_ctrl_r_intercept(player_js)


PLAYER_PACKAGE_DATA = (
    "contracts/*.json", "contracts/*.sha256", "templates/production_player/*.html",
    "static/production_player/*.css", "static/production_player/*.js",
)


def assert_packaging_configuration(configuration: dict, baseline: dict) -> None:
    expected = copy.deepcopy(baseline)
    expected["tool"]["setuptools"]["packages"]["find"]["include"].append("production_player*")
    expected["tool"]["setuptools"]["package-data"]["production_player"] = list(PLAYER_PACKAGE_DATA)
    require(configuration == expected, "pyproject delta must be only exact Player discovery/package-data")


def assert_packaging(repo: Path) -> None:
    configuration = tomllib.loads(source(repo, PYPROJECT_PATH))
    baseline = tomllib.loads(git(repo, "show", f"{FD08_ACCEPTED_HEAD}:{PYPROJECT_PATH}"))
    assert_packaging_configuration(configuration, baseline)
    find = configuration.get("tool", {}).get("setuptools", {}).get("packages", {}).get("find", {})
    include = tuple(find.get("include", ()))
    require("production_player*" in include, "pyproject must discover the Production Player package")
    package_data = configuration.get("tool", {}).get("setuptools", {}).get("package-data", {})
    data = tuple(package_data.get("production_player", ()))
    required = {
        "contracts/*.json",
        "contracts/*.sha256",
        "templates/production_player/*.html",
        "static/production_player/*.css",
        "static/production_player/*.js",
    }
    require(required == set(data), "production_player package-data must contain exact runtime assets only")
    serialized = source(repo, PYPROJECT_PATH)
    require("data-files" not in serialized.lower(), "G7 must not install documentation as data-files")
    require("0014-production-player-g7" not in serialized and "production-player-g7-runtime" not in serialized, "G7 source docs must not be wheel payload declarations")
    require((repo / ADR_PATH).is_file() and (repo / RUNTIME_DOC_PATH).is_file(), "G7 source documents must be repository artifacts")


def assert_legacy_workflow_preserved(workflow: str, baseline: str) -> None:
    marker = "  player-g7-professional-shell:\n"
    require(workflow.count(marker) == 1, "exactly one dedicated G7 job is required")
    prior, _ = workflow.split(marker, 1)
    branch_line = f"      - {G7_TARGET_BRANCH}\n"
    require(prior.count(branch_line) == 1, "G7 must be added to exactly one push branch list")
    restored = prior.replace(branch_line, "", 1)
    pull_prefix, push_suffix = restored.split("  push:\n", 1)
    base_line = f"      - {FD08_BASE_BRANCH}\n"
    require(pull_prefix.count(base_line) == 1, "G7 PR trigger must add the exact accepted FD08 base")
    restored = pull_prefix.replace(base_line, "", 1) + "  push:\n" + push_suffix
    for property_name, prefix in (("github.event.pull_request.head.ref", ""), ("github.ref", "refs/heads/")):
        previous = f"{property_name} != '{prefix}{FD08_BASE_BRANCH}'"
        appended = previous + f" &&\n       {property_name} != '{prefix}{G7_TARGET_BRANCH}'"
        require(restored.count(appended) == 1, "legacy job must exclude G7 for both push and PR")
        restored = restored.replace(appended, previous, 1)
    require(restored.rstrip() == baseline.rstrip(), "legacy workflow changes exceed the four G7 route additions")


def assert_workflow(repo: Path) -> None:
    workflow = source(repo, WORKFLOW_PATH)
    baseline = git(repo, "show", f"{FD08_ACCEPTED_HEAD}:{WORKFLOW_PATH}")
    assert_legacy_workflow_preserved(workflow, baseline)
    g7_body = workflow.split("  player-g7-professional-shell:\n", 1)[1]
    required = (
        G7_TARGET_BRANCH,
        FD08_BASE_BRANCH,
        "github.event.pull_request.head.sha || github.sha",
        "FD08_ACCEPTED_HEAD",
        "FD08_ACCEPTED_TREE",
        "verify_player_g7_allowlist.py",
        "G7_SAME_RUN_EXACT_HEAD_EVIDENCE=PASS",
        "github.run_attempt",
        'test "$GITHUB_RUN_ATTEMPT" = "1"',
        "test \"$FD08_ACCEPTED_HEAD\" = \"$G7_BASE_HEAD\"",
        "test \"$FD08_ACCEPTED_TREE\" = \"$G7_BASE_TREE\"",
        "test \"$EVENT_HEAD_SHA\" = \"$delivery_head\"",
        "test \"$EVENT_BASE_SHA\" = \"$G7_BASE_HEAD\"",
        "test \"$GITHUB_SHA\" = \"$delivery_head\"",
        "test_player_foundation.py",
        "test_player_g7.py",
        "player_g7.mjs",
        "G7_WHEEL_EVIDENCE_V1",
        "G7_ISOLATED_WHEEL_INSTALL_V1",
    )
    missing = [token for token in required if token not in g7_body]
    require(not missing, f"G7 workflow is missing required exact-head evidence tokens: {', '.join(missing)}")
    legacy_start = workflow.find("  foundation-contract:")
    g7_start = workflow.find("  player-g7-professional-shell:")
    require(legacy_start >= 0 and g7_start >= 0, "workflow must contain legacy and dedicated G7 jobs")
    legacy_condition = workflow[legacy_start:workflow.index("    runs-on:", legacy_start)]
    require(f"github.event.pull_request.head.ref != '{G7_TARGET_BRANCH}'" in legacy_condition,
            "legacy Foundation PR job must exclude G7")
    require(f"github.ref != 'refs/heads/{G7_TARGET_BRANCH}'" in legacy_condition,
            "legacy Foundation push job must exclude G7")


WHEEL_RUNTIME_MEMBERS = frozenset({
    "conflict_analysis/settings.py",
    "conflict_analysis/urls.py",
    "domain/urls.py",
    "domain/api/player.py",
    "domain/services/player_workspaces.py",
    "domain/services/player_help_catalog.py",
    "domain/management/commands/provision_player_help.py",
    "production_player/__init__.py",
    "production_player/apps.py",
    "production_player/claim_boundaries.py",
    "production_player/urls.py",
    "production_player/views.py",
    "production_player/contracts/player_g7_claim_boundaries_v1.ru.json",
    "production_player/contracts/player_g7_claim_boundaries_v1.ru.json.sha256",
    "production_player/static/production_player/player.css",
    "production_player/static/production_player/player.js",
    "production_player/templates/production_player/entry.html",
    "production_player/templates/production_player/project.html",
    "production_player/templates/production_player/workspace.html",
})


def inspect_wheel(wheel: Path, *, repo: Path | None = None) -> dict[str, object]:
    require(wheel.is_file(), f"wheel does not exist: {wheel}")
    with zipfile.ZipFile(wheel) as archive:
        names = frozenset(archive.namelist())
        require(len(names) == len(archive.namelist()), "duplicate wheel members are forbidden")
        asset_hashes = {}
        if repo is not None:
            for member in WHEEL_RUNTIME_MEMBERS:
                require(member in names, f"required wheel member is absent: {member}")
                raw = archive.read(member)
                require(raw == (repo / "software/conflict_analysis" / member).read_bytes(),
                        f"wheel/source runtime byte drift: {member}")
                asset_hashes[member] = hashlib.sha256(raw).hexdigest()
    required = WHEEL_RUNTIME_MEMBERS
    require(required <= names, "wheel lacks one or more required Production Player runtime assets")
    forbidden = [name for name in names if "0014-production-player-g7" in name or "production-player-g7-runtime" in name]
    require(not forbidden, "G7 source docs must not be installed in the wheel")
    return {"filename": wheel.name, "bytes": wheel.stat().st_size,
            "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
            "member_count": len(names), "runtime_assets": sorted(required),
            "runtime_asset_sha256": asset_hashes}


def verify(repo: Path, *, base_head: str, base_tree: str, wheel: Path | None = None) -> dict[str, object]:
    require(repo.is_dir(), f"repository does not exist: {repo}")
    require_sha(base_head, "G7 base HEAD")
    require_sha(base_tree, "G7 base TREE")
    head, tree, parent = assert_parent(repo, base_head=base_head, base_tree=base_tree)
    statuses = assert_allowed_topology(repo, base_head=base_head)
    assert_frozen_parent(repo, base_head=base_head)
    assert_sources(repo)
    assert_packaging(repo)
    assert_workflow(repo)
    result: dict[str, object] = {
        "allowlist_result": "PASS",
        "schema": "G7_ALLOWLIST_EVIDENCE_V1",
        "base": {"branch": FD08_BASE_BRANCH, "head": base_head, "tree": base_tree},
        "accepted_f1_ancestor": {"head": F1_ACCEPTED_HEAD, "tree": F1_ACCEPTED_TREE},
        "delivery": {"head": head, "tree": tree, "parent": parent},
        "history": {"ordinary_commits_above_fd08": 1, "merge_commits": 0},
        "paths": {"modified": sorted(MODIFIED_PATHS), "new": sorted(NEW_PATHS), "statuses": dict(sorted(statuses.items()))},
        "counts": {"modified": 6, "new": 23, "total": 29},
        "preimage_blobs": PREIMAGE_BLOBS,
        "frozen_parent_blobs": FROZEN_PARENT_BLOBS,
        "registry": {"foundation_portable": list(FOUNDATION_PORTABLE_NODES), "postgresql_only": list(POSTGRESQL_ONLY_NODES), "product_portable": list(PRODUCT_NODES), "chromium": list(CHROMIUM_NODES)},
        "source_docs_repository_only": [ADR_PATH, RUNTIME_DOC_PATH],
        "workflow": {"same_run_exact_head": True, "legacy_foundation_excludes_g7": True},
    }
    if wheel is not None:
        result["wheel"] = inspect_wheel(wheel, repo=repo)
    return result


def expect_error(callback: object) -> bool:
    try:
        callback()  # type: ignore[operator]
    except VerificationError:
        return True
    return False


def self_check() -> dict[str, object]:
    require(len(MODIFIED_PATHS) == 6 and len(NEW_PATHS) == 23 and len(ALLOWLIST) == 29, "frozen G7 path count drift")
    require(not (MODIFIED_PATHS & NEW_PATHS), "modified/new G7 paths must not overlap")
    for path, blob in {**PREIMAGE_BLOBS, **FROZEN_PARENT_BLOBS}.items():
        require(PurePosixPath(path).as_posix() == path, f"non-posix frozen path: {path}")
        require_sha(blob, f"frozen blob {path}")
    require(len(FOUNDATION_PORTABLE_NODES) == 12, "Foundation portable registry drift")
    require(len(POSTGRESQL_ONLY_NODES) == 2, "PostgreSQL-only registry drift")
    require(len(PRODUCT_NODES) == 10, "Product registry drift")
    require(len(CHROMIUM_NODES) == 2, "Chromium registry drift")
    all_nodes = FOUNDATION_PORTABLE_NODES + POSTGRESQL_ONLY_NODES + PRODUCT_NODES + CHROMIUM_NODES
    require(len(all_nodes) == len(set(all_nodes)), "G7 registry contains duplicate nodes")

    topology = {
        **{path: "M" for path in MODIFIED_PATHS},
        **{path: "A" for path in NEW_PATHS},
    }
    assert_topology_statuses(topology)
    bad_status = {**topology, "README.md": "A"}

    helper_source = "__test__ = False\n"
    assert_test_registry_names(
        foundation=FOUNDATION_PORTABLE_NODES + POSTGRESQL_ONLY_NODES,
        product=PRODUCT_NODES + CHROMIUM_NODES,
        help_source=helper_source,
    )
    bad_registry = FOUNDATION_PORTABLE_NODES[:-1] + ("test_unapproved_node",)
    frozen_blobs = {**PREIMAGE_BLOBS, **FROZEN_PARENT_BLOBS}
    assert_frozen_parent_blobs(frozen_blobs.__getitem__)
    bad_blobs = dict(frozen_blobs)
    bad_blobs[WORKFLOW_PATH] = "0" * 40

    help_api = "def help_topic(request, workspace_id, ui_key):\n    return None\n"
    help_urls = (
        'path("player/workspaces/<uuid:workspace_id>/help/<str:ui_key>/", '
        "player.help_topic, name=\"foundation-player-help\"),\n"
    )
    assert_help_route_contract(api_source=help_api, urls_source=help_urls)
    unscoped_urls = 'path("player/help/<str:ui_key>/", player.help_topic),\n'

    valid_write = (
        "def create_one():\n    with transaction.atomic():\n"
        "        row = TimeSlice(id=identity)\n        row.save(force_insert=True)\n"
    )
    assert_service_write_boundary(valid_write)
    forbidden_write = "TimeSlice.objects.bulk_create(rows)\n"
    persisted_save = valid_write.replace("TimeSlice(id=identity)", "TimeSlice.objects.get(pk=identity)")
    non_insert_save = valid_write.replace("force_insert=True", "force_insert=False")
    baseline_packaging = {"tool": {"setuptools": {"packages": {"find": {"include": ["domain*"]}}, "package-data": {}}}}
    good_packaging = copy.deepcopy(baseline_packaging)
    good_packaging["tool"]["setuptools"]["packages"]["find"]["include"].append("production_player*")
    good_packaging["tool"]["setuptools"]["package-data"]["production_player"] = list(PLAYER_PACKAGE_DATA)
    assert_packaging_configuration(good_packaging, baseline_packaging)
    extra_packaging = copy.deepcopy(good_packaging)
    extra_packaging["tool"]["setuptools"]["package-data"]["production_player"].append("docs/*")

    history = {
        ("rev-parse", f"{FD08_ACCEPTED_HEAD}^{{tree}}"): FD08_ACCEPTED_TREE,
        ("rev-parse", f"{F1_ACCEPTED_HEAD}^{{tree}}"): F1_ACCEPTED_TREE,
        ("merge-base", "--is-ancestor", F1_ACCEPTED_HEAD, FD08_ACCEPTED_HEAD): "",
        ("status", "--porcelain=v1", "-uall"): "",
        ("rev-parse", "HEAD"): "1" * 40,
        ("rev-parse", "HEAD^{tree}"): "2" * 40,
        ("show", "-s", "--format=%P", "HEAD"): FD08_ACCEPTED_HEAD,
        ("rev-list", "--count", f"{FD08_ACCEPTED_HEAD}..HEAD"): "1",
        ("rev-list", "--merges", f"{FD08_ACCEPTED_HEAD}..HEAD"): "",
    }
    def check_history(overrides=None):
        facts = {**history, **(overrides or {})}
        def read(*args):
            value = facts[args]
            if isinstance(value, VerificationError):
                raise value
            return value
        return assert_parent(Path("."), base_head=FD08_ACCEPTED_HEAD,
                             base_tree=FD08_ACCEPTED_TREE, git_reader=read)
    check_history()
    all_anchors = {
        **{("rev-parse", f"{FD08_ACCEPTED_HEAD}:{path}"): blob for path, blob in frozen_blobs.items()},
        **{("rev-parse", f"HEAD:{path}"): blob for path, blob in FROZEN_PARENT_BLOBS.items()},
    }
    assert_frozen_parent(Path("."), base_head=FD08_ACCEPTED_HEAD,
                         git_reader=lambda *args: all_anchors[args])
    bad_delivery_anchor = dict(all_anchors)
    bad_delivery_anchor[("rev-parse", "HEAD:software/conflict_analysis/domain/models.py")] = "0" * 40

    old_workflow = (
        "on:\n  pull_request:\n    branches:\n      - preserved-pr\n  push:\n"
        "    branches:\n      - preserved-push\njobs:\n  foundation-contract:\n    if: >-\n"
        f"       github.event.pull_request.head.ref != '{FD08_BASE_BRANCH}') ||\n"
        f"       github.ref != 'refs/heads/{FD08_BASE_BRANCH}')\n    runs-on: ubuntu-latest\n"
    )
    new_workflow = old_workflow.replace("      - preserved-pr\n", f"      - preserved-pr\n      - {FD08_BASE_BRANCH}\n")
    new_workflow = new_workflow.replace("      - preserved-push\n", f"      - preserved-push\n      - {G7_TARGET_BRANCH}\n")
    for property_name, prefix in (("github.event.pull_request.head.ref", ""), ("github.ref", "refs/heads/")):
        previous = f"{property_name} != '{prefix}{FD08_BASE_BRANCH}'"
        new_workflow = new_workflow.replace(previous, previous + f" &&\n       {property_name} != '{prefix}{G7_TARGET_BRANCH}'")
    new_workflow += "\n  player-g7-professional-shell:\n    runs-on: ubuntu-latest\n"
    assert_legacy_workflow_preserved(new_workflow, old_workflow)

    with TemporaryDirectory(prefix="g7-verifier-self-check-") as temporary:
        fixture_wheel = Path(temporary) / "fixture.whl"
        with zipfile.ZipFile(fixture_wheel, "w") as archive:
            for member in WHEEL_RUNTIME_MEMBERS:
                archive.writestr(member, b"fixture")
        inspect_wheel(fixture_wheel)
        forbidden_wheel = Path(temporary) / "fixture-with-docs.whl"
        with zipfile.ZipFile(forbidden_wheel, "w") as archive:
            for member in WHEEL_RUNTIME_MEMBERS:
                archive.writestr(member, b"fixture")
            archive.writestr("docs/0014-production-player-g7.md", b"must remain source-only")
        wheel_docs_rejected = expect_error(lambda: inspect_wheel(forbidden_wheel))

    negatives = {
        "30th_path_rejected": expect_error(lambda: assert_topology_statuses(bad_status)),
        "registry_drift_rejected": expect_error(
            lambda: assert_test_registry_names(
                foundation=bad_registry + POSTGRESQL_ONLY_NODES,
                product=PRODUCT_NODES + CHROMIUM_NODES,
                help_source=helper_source,
            )
        ),
        "preimage_drift_rejected": expect_error(lambda: assert_frozen_parent_blobs(bad_blobs.__getitem__)),
        "unscoped_help_route_rejected": expect_error(
            lambda: assert_help_route_contract(api_source=help_api, urls_source=unscoped_urls)
        ),
        "wheel_docs_rejected": wheel_docs_rejected,
        "bulk_insert_rejected": expect_error(lambda: assert_service_write_boundary(forbidden_write)),
        "persisted_instance_save_rejected": expect_error(lambda: assert_service_write_boundary(persisted_save)),
        "non_insert_instance_save_rejected": expect_error(lambda: assert_service_write_boundary(non_insert_save)),
        "persisted_delete_rejected": expect_error(lambda: assert_service_write_boundary("row.delete()\n")),
        "persisted_update_rejected": expect_error(lambda: assert_service_write_boundary("TimeSlice.objects.filter(pk=identity).update(name='changed')\n")),
        "save_base_bypass_rejected": expect_error(lambda: assert_service_write_boundary("row = TimeSlice.objects.get(pk=identity)\nrow.save_base()\n")),
        "extra_package_glob_rejected": expect_error(lambda: assert_packaging_configuration(extra_packaging, baseline_packaging)),
        "ctrl_r_interception_rejected": expect_error(lambda: assert_no_ctrl_r_intercept("if (event.ctrlKey && event.key === 'r') event.preventDefault();")),
        "second_parent_rejected": expect_error(lambda: check_history({("show", "-s", "--format=%P", "HEAD"): FD08_ACCEPTED_HEAD + " " + "3" * 40})),
        "f1_tree_drift_rejected": expect_error(lambda: check_history({("rev-parse", f"{F1_ACCEPTED_HEAD}^{{tree}}"): "0" * 40})),
        "missing_f1_ancestry_rejected": expect_error(lambda: check_history({("merge-base", "--is-ancestor", F1_ACCEPTED_HEAD, FD08_ACCEPTED_HEAD): VerificationError("git ancestry check failed")})),
        "dirty_delivery_rejected": expect_error(lambda: check_history({("status", "--porcelain=v1", "-uall"): " M changed.py"})),
        "extra_commit_rejected": expect_error(lambda: check_history({("rev-list", "--count", f"{FD08_ACCEPTED_HEAD}..HEAD"): "2"})),
        "merge_commit_rejected": expect_error(lambda: check_history({("rev-list", "--merges", f"{FD08_ACCEPTED_HEAD}..HEAD"): "3" * 40})),
        "delivery_anchor_drift_rejected": expect_error(lambda: assert_frozen_parent(Path("."), base_head=FD08_ACCEPTED_HEAD, git_reader=lambda *args: bad_delivery_anchor[args])),
        "legacy_workflow_mutation_rejected": expect_error(lambda: assert_legacy_workflow_preserved(new_workflow.replace("preserved-pr", "changed-pr"), old_workflow)),
    }
    require(all(negatives.values()), "G7 verifier negative self-check failed")
    return {
        "contract_self_check": "PASS",
        "marker": "G7_ALLOWLIST_VERIFIER_SELF_CHECK=PASS",
        "counts": {"modified": 6, "new": 23, "total": 29},
        "registry_counts": {"foundation_portable": 12, "postgresql_only": 2, "product_portable": 10, "chromium": 2},
        "negative_cases": negatives,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument("--base-head", default=FD08_ACCEPTED_HEAD)
    parser.add_argument("--base-tree", default=FD08_ACCEPTED_TREE)
    parser.add_argument("--wheel", type=Path)
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = self_check() if args.self_check else verify(args.repo, base_head=args.base_head, base_tree=args.base_tree, wheel=args.wheel)
    except VerificationError as error:
        key = "contract_self_check" if args.self_check else "allowlist_result"
        print(json.dumps({key: "FAIL", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
