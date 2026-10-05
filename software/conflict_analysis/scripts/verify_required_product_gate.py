#!/usr/bin/env python3
"""Fail-closed verification helpers for the required Conflict Analysis product gate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from zipfile import ZipFile

WORKFLOW_PATH = Path(".github/workflows/conflict-analysis-required.yml")
PROJECT_PATH = Path("software/conflict_analysis")
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"
SETUP_PYTHON_SHA = "a26af69be951a213d495a4c3e4e4022e16d87065"
SETUP_NODE_SHA = "49933ea5288caeca8642d1e84afbd3f7d6820020"
UPLOAD_ARTIFACT_SHA = "ea165f8d65b6e75b540449e92b4886f43607fa02"
POSTGRES_DIGEST = "sha256:77f585114c32fbca283dc835b0596f4e52b51b4c6662d7810b2f4084f60a1873"

PRODUCT_TEST_PATHS = (
    "conflict_analysis/tests",
    "calculation/tests",
    "domain/tests",
    "production_studio/tests",
    "production_player/tests",
    "player_integration/tests",
    "scenario_modeling/tests",
)

REQUIRED_WHEEL_MEMBERS = (
    "player_integration/__init__.py",
    "player_integration/apps.py",
    "player_integration/inputs.py",
    "player_integration/project_urls.py",
    "player_integration/quality.py",
    "player_integration/receipts.py",
    "player_integration/services.py",
    "player_integration/settings.py",
    "player_integration/urls.py",
    "player_integration/views.py",
    "player_integration/static/player_integration/result.css",
    "player_integration/templates/player_integration/base.html",
    "player_integration/templates/player_integration/experiment.html",
    "player_integration/templates/player_integration/inputs.html",
    "player_integration/templates/player_integration/result.html",
    "player_integration/templates/player_integration/start.html",
    "player_integration/tests/__init__.py",
    "player_integration/tests/test_browser.py",
    "player_integration/tests/test_e2e.py",
    "player_integration/tests/test_quality.py",
    "player_integration/tests/test_receipts.py",
    "scenario_modeling/__init__.py",
    "scenario_modeling/adapter.py",
    "scenario_modeling/apps.py",
    "scenario_modeling/model.py",
    "scenario_modeling/session.py",
    "scenario_modeling/urls.py",
    "scenario_modeling/views.py",
    "scenario_modeling/static/scenario_modeling/scenario.css",
    "scenario_modeling/static/scenario_modeling/scenario.js",
    "scenario_modeling/templates/scenario_modeling/result.html",
    "scenario_modeling/tests/__init__.py",
    "scenario_modeling/tests/test_browser.py",
    "scenario_modeling/tests/test_http.py",
    "scenario_modeling/tests/test_model.py",
)

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def _json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def verify_workflow(repo_root: Path) -> None:
    repo_root = repo_root.resolve(strict=True)
    workflow = (repo_root / WORKFLOW_PATH).read_text(encoding="utf-8")
    pytest_config = (repo_root / PROJECT_PATH / "pytest.ini").read_text(encoding="utf-8")

    expected_trigger = """on:\n  pull_request:\n  push:\n    branches:\n      - main\n      - review/ai-only-research-beta-v1\n  workflow_dispatch:\n"""
    _require(expected_trigger in workflow, "required workflow must run on every pull request")
    _require("permissions:\n  contents: read\n" in workflow, "workflow permissions are not read-only")
    _require("name: Required product gate" in workflow, "stable aggregate job name is absent")
    _require("if: ${{ always() }}" in workflow, "aggregate job must execute after failures")
    _require("secrets." not in workflow, "required product gate must not consume repository secrets")

    pins = {
        "checkout": CHECKOUT_SHA,
        "setup-python": SETUP_PYTHON_SHA,
        "setup-node": SETUP_NODE_SHA,
        "upload-artifact": UPLOAD_ARTIFACT_SHA,
    }
    for action, sha in pins.items():
        _require(
            f"actions/{action}@{sha}" in workflow,
            f"actions/{action} is not pinned to the frozen commit",
        )
    _require(
        re.search(r"uses:\s*actions/[^@\s]+@v\d", workflow) is None,
        "mutable major action tag is forbidden in the required gate",
    )
    _require(
        f"postgres:18-alpine@{POSTGRES_DIGEST}" in workflow,
        "PostgreSQL service image is not digest-pinned",
    )

    for token in (
        "PLAYER_INTEGRATION_BROWSER: \"1\"",
        "SCENARIO_BROWSER: \"1\"",
        "python -m pytest -q -p no:cacheprovider",
        "python manage.py migrate --noinput",
        "python manage.py makemigrations --check --dry-run",
        "installed-smoke",
        "inspect-wheel",
    ):
        _require(token in workflow, f"required gate contract is missing: {token}")

    for test_path in PRODUCT_TEST_PATHS:
        _require(test_path in pytest_config, f"default pytest omits {test_path}")
    _require(
        pytest_config.count("DJANGO_SETTINGS_MODULE = conflict_analysis.settings") == 1,
        "default pytest must use the single root settings graph",
    )

    for marker in (
        'HTTP_PROXY: "http://127.0.0.1:9"',
        'HTTPS_PROXY: "http://127.0.0.1:9"',
        'OPENAI_API_KEY: ""',
        'HF_HUB_OFFLINE: "1"',
        'TRANSFORMERS_OFFLINE: "1"',
    ):
        _require(
            workflow.count(marker) == 2,
            f"offline test marker missing from both gates: {marker}",
        )

    lowered = workflow.lower()
    for forbidden in (
        "anthropic_api_key",
        "gemini_api_key",
        "grok_api_key",
        "model_executor",
        "workflow_call",
    ):
        _require(forbidden not in lowered, f"external-model capability leaked into gate: {forbidden}")

    _json(
        {
            "status": "PASS",
            "workflow": str(WORKFLOW_PATH),
            "read_only_permissions": True,
            "all_pull_requests": True,
            "pinned_actions": pins,
            "postgres_digest": POSTGRES_DIGEST,
            "product_test_paths": list(PRODUCT_TEST_PATHS),
        }
    )


def inspect_wheel(wheel_path: Path) -> None:
    wheel_path = wheel_path.resolve(strict=True)
    _require(wheel_path.suffix == ".whl", "expected one wheel file")
    with ZipFile(wheel_path) as archive:
        names = archive.namelist()
    name_set = set(names)
    missing = sorted(set(REQUIRED_WHEEL_MEMBERS) - name_set)
    duplicates = sorted(name for name in REQUIRED_WHEEL_MEMBERS if names.count(name) != 1)
    forbidden = sorted(
        name for name in names
        if "__pycache__" in name
        or name.endswith((".pyc", ".pyo", ".sqlite3"))
        or "/.artifacts/" in name
    )
    _require(not missing, f"wheel misses required members: {missing}")
    _require(not duplicates, f"wheel members are not unique: {duplicates}")
    _require(not forbidden, f"wheel contains forbidden build/runtime residue: {forbidden}")
    _json(
        {
            "status": "PASS",
            "wheel": wheel_path.name,
            "bytes": wheel_path.stat().st_size,
            "entries": len(names),
            "required_members": len(REQUIRED_WHEEL_MEMBERS),
            "missing": missing,
            "duplicates": duplicates,
            "forbidden": forbidden,
        }
    )


def installed_smoke(target: Path, static_root: Path, sqlite_path: Path) -> None:
    target = target.resolve(strict=True)
    static_root = static_root.resolve()
    sqlite_path = sqlite_path.resolve()
    _require(target.is_dir(), "installed wheel target is absent")

    os.chdir(target.parent)
    sys.path.insert(0, str(target))
    os.environ["DJANGO_SETTINGS_MODULE"] = "conflict_analysis.settings"
    os.environ["DJANGO_SECRET_KEY"] = "ci-installed-wheel-smoke-only"
    os.environ["DJANGO_DEBUG"] = "false"
    os.environ["USE_SQLITE"] = "true"
    os.environ["SQLITE_PATH"] = str(sqlite_path)

    import calculation
    import conflict_analysis
    import domain
    import player_integration
    import production_player
    import production_studio
    import scenario_modeling

    modules = {
        "calculation": Path(calculation.__file__).resolve(),
        "conflict_analysis": Path(conflict_analysis.__file__).resolve(),
        "domain": Path(domain.__file__).resolve(),
        "player_integration": Path(player_integration.__file__).resolve(),
        "production_player": Path(production_player.__file__).resolve(),
        "production_studio": Path(production_studio.__file__).resolve(),
        "scenario_modeling": Path(scenario_modeling.__file__).resolve(),
    }
    for name, module_path in modules.items():
        _require(target in module_path.parents, f"{name} imported outside installed wheel target")

    import django

    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.template.loader import get_template
    from django.urls import resolve

    settings.STATIC_ROOT = static_root
    call_command("check", verbosity=0)
    call_command("migrate", interactive=False, verbosity=0)
    call_command("collectstatic", interactive=False, verbosity=0, clear=True)

    route_expectations = {
        "/player/calculations/": ("player_integration", "start"),
        "/player/calculations/scenarios/": ("scenario_modeling", "update"),
    }
    for path, expected in route_expectations.items():
        match = resolve(path)
        _require((match.namespace, match.url_name) == expected, f"route mismatch for {path}")

    templates = (
        "player_integration/start.html",
        "player_integration/result.html",
        "scenario_modeling/result.html",
    )
    for template in templates:
        get_template(template)

    static_assets = (
        "player_integration/result.css",
        "scenario_modeling/scenario.css",
        "scenario_modeling/scenario.js",
    )
    for relative in static_assets:
        _require((static_root / relative).is_file(), f"collectstatic omitted {relative}")

    _json(
        {
            "status": "PASS",
            "installed_target": str(target),
            "module_paths": {key: str(value) for key, value in modules.items()},
            "routes": sorted(route_expectations),
            "templates": list(templates),
            "static_assets": list(static_assets),
            "static_file_count": sum(1 for path in static_root.rglob("*") if path.is_file()),
        }
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    workflow = commands.add_parser("workflow")
    workflow.add_argument("--repo-root", type=Path, required=True)

    wheel = commands.add_parser("inspect-wheel")
    wheel.add_argument("--wheel", type=Path, required=True)

    smoke = commands.add_parser("installed-smoke")
    smoke.add_argument("--target", type=Path, required=True)
    smoke.add_argument("--static-root", type=Path, required=True)
    smoke.add_argument("--sqlite-path", type=Path, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "workflow":
        verify_workflow(args.repo_root)
    elif args.command == "inspect-wheel":
        inspect_wheel(args.wheel)
    elif args.command == "installed-smoke":
        installed_smoke(args.target, args.static_root, args.sqlite_path)
    else:  # pragma: no cover
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
