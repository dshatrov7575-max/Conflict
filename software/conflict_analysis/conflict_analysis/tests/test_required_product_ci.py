from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROJECT_ROOT = REPOSITORY_ROOT / "software" / "conflict_analysis"
VERIFIER = PROJECT_ROOT / "scripts" / "verify_required_product_gate.py"
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "conflict-analysis-required.yml"
PYTEST_CONFIG = PROJECT_ROOT / "pytest.ini"


class RequiredProductCIContractTests(SimpleTestCase):
    def test_required_workflow_contract_is_fail_closed(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(VERIFIER),
                "workflow",
                "--repo-root",
                str(REPOSITORY_ROOT),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('"status": "PASS"', completed.stdout)

    def test_default_pytest_surface_is_the_complete_product(self):
        text = PYTEST_CONFIG.read_text(encoding="utf-8")
        for relative in (
            "conflict_analysis/tests",
            "calculation/tests",
            "domain/tests",
            "production_studio/tests",
            "production_player/tests",
            "player_integration/tests",
            "scenario_modeling/tests",
        ):
            self.assertIn(relative, text)
        self.assertEqual(text.count("DJANGO_SETTINGS_MODULE = conflict_analysis.settings"), 1)

    def test_workflow_is_separate_from_historical_branch_specific_gate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:\n  push:", text)
        self.assertNotIn("codex/ca-suite", text)
        self.assertNotIn("secrets.", text)
        self.assertIn("Required product gate", text)
        self.assertIn("postgres:18-alpine@sha256:", text)
        self.assertIn("Production image hardening gate", text)
        self.assertIn("PRODUCTION_IMAGE_RESULT", text)
        self.assertIn("docker build --target production", text)
        self.assertEqual(text.count("scripts/build_reproducible_wheel.py"), 2)
        self.assertEqual(text.count("wheel_sha256: ${{ steps.wheel.outputs.sha256 }}"), 2)
        self.assertIn("WHEEL_SQLITE_SHA256", text)
        self.assertIn("POSTGRESQL_WHEEL_SHA256", text)
        self.assertIn("PRODUCTION_IMAGE_WHEEL_SHA256", text)
        self.assertIn('test "${WHEEL_SQLITE_SHA256}" = "${POSTGRESQL_WHEEL_SHA256}"', text)
        self.assertIn('test "${WHEEL_SQLITE_SHA256}" = "${PRODUCTION_IMAGE_WHEEL_SHA256}"', text)
        self.assertIn("CONFLICT_ANALYSIS_REPRODUCIBLE_WHEEL=PASS", text)
        self.assertEqual(text.count('node-version: "24"'), 2)
        self.assertEqual(text.count("package-manager-cache: false"), 2)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", text)
        self.assertIn("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", text)
        self.assertIn("actions/setup-node@820762786026740c76f36085b0efc47a31fe5020", text)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", text)
