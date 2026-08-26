from __future__ import annotations

from pathlib import Path
import re

from django.test import SimpleTestCase


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "conflict-analysis.yml"


class StudioShowcaseCiContractTests(SimpleTestCase):
    def test_final_head_postgresql_browser_and_sqlite_gates_are_explicit(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        for required in (
            "codex/ca-suite-i1-studio-showcase",
            "ref: ${{ github.event.pull_request.head.sha || github.sha }}",
            "postgres:18-alpine",
            'node-version: "24"',
            "domain/tests/test_studio_showcase_*.py",
            "phase1_import_export.mjs",
            "phase3_dom_safety.mjs",
            "python -m pytest domain/tests -q",
            "USE_SQLITE: \"true\"",
            "makemigrations --check --dry-run",
            "python -m pip wheel . --no-deps --no-build-isolation",
            "git diff --check",
        ):
            self.assertIn(required, workflow)

        secret_match = re.search(r"DJANGO_SECRET_KEY:\s*([^\r\n]+)", workflow)
        self.assertIsNotNone(secret_match)
        self.assertGreaterEqual(len(secret_match.group(1).strip().strip('"')), 32)

    def test_windows_artifact_is_exact_head_reproducible_and_clean_room_tested(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        for required in (
            "runs-on: windows-latest",
            "requirements-owner-test.txt",
            "build_owner_test_package.ps1",
            "$FirstHash -cne $SecondHash",
            "run_clean_room_gate.ps1",
            '$ManifestHashRecord = "$($FirstZip.FullName).manifest.sha256"',
            "-ManifestSha256RecordPath $ManifestHashRecord",
            "$EvidencePath = Join-Path $env:RUNNER_TEMP 'clean-room-evidence.json'",
            "-EvidencePath $EvidencePath",
            "stop_no_orphan",
            "actions/upload-artifact@v4",
            "ConflictAnalysis-Studio-OWNER-TEST-${{ steps.owner_package.outputs.head }}",
            "if-no-files-found: error",
        ):
            self.assertIn(required, workflow)

        self.assertEqual(workflow.count("build_owner_test_package.ps1"), 2)
        self.assertNotIn("Select-Object -Single", workflow)
        self.assertNotIn("artifact_dir=$First", workflow)
        self.assertNotIn("path: ${{ steps.owner_package.outputs.artifact_dir }}", workflow)
        self.assertIn(
            """path: |
            ${{ steps.owner_package.outputs.zip_path }}
            ${{ steps.owner_package.outputs.zip_sha256_path }}
            ${{ steps.owner_package.outputs.manifest_sha256_path }}
          if-no-files-found: error""",
            workflow,
        )
