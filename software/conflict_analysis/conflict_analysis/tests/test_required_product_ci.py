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
