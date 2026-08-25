from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


APP_ROOT = Path(__file__).resolve().parents[2]
BROWSER_TEST_ROOT = APP_ROOT / "studio_showcase" / "browser_tests"
CDP_CLIENT = BROWSER_TEST_ROOT / "cdp_client.mjs"
PHASE1_SCRIPT = BROWSER_TEST_ROOT / "phase1_import_export.mjs"


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"Required browser gate is missing: {path}")
    return path.read_text(encoding="utf-8")


class ShowcaseBrowserHarnessContractTests(SimpleTestCase):
    def test_phase1_is_a_dependency_free_real_browser_file_round_trip(self):
        client = _read(CDP_CLIENT)
        phase1 = _read(PHASE1_SCRIPT)
        combined = f"{client}\n{phase1}"

        for required_contract in (
            'new File([text], filename',
            "new DataTransfer()",
            'new Event("change", { bubbles: true })',
            "input.files = transfer.files",
            "__ownerTestLastDownload",
            "download.blob.arrayBuffer()",
            "terminalNewline",
            'crypto.subtle.digest("SHA-256"',
            "beforeCanonicalSha256",
            "afterCanonicalSha256",
            "nonMutating",
            "equalsExportedSession",
        ):
            with self.subTest(contract=required_contract):
                self.assertIn(required_contract, combined)

        self.assertIn('document.querySelector(\'[data-command="export"]\').click()', phase1)
        self.assertIn('"showcase-session-v1-export.json"', phase1)
        self.assertIn('"SHOWCASE_SESSION_V1"', phase1)
        for forbidden_dependency in (
            "playwright",
            "puppeteer",
            "selenium",
            "webdriver",
            "node_modules",
        ):
            self.assertNotIn(forbidden_dependency, combined.casefold())

    def test_browser_gate_scripts_pass_node_syntax_check(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is not available for the browser harness syntax gate.")

        for script in (CDP_CLIENT, PHASE1_SCRIPT):
            with self.subTest(script=script.name):
                result = subprocess.run(
                    [node, "--check", str(script)],
                    cwd=APP_ROOT,
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
