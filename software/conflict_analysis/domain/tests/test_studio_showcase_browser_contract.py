from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase


APP_ROOT = Path(__file__).resolve().parents[2]
BROWSER_TEST_ROOT = APP_ROOT / "studio_showcase" / "browser_tests"
CDP_CLIENT = BROWSER_TEST_ROOT / "cdp_client.mjs"
PHASE1_SCRIPT = BROWSER_TEST_ROOT / "phase1_import_export.mjs"
PHASE3_SCRIPT = BROWSER_TEST_ROOT / "phase3_dom_safety.mjs"


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

        for script in (CDP_CLIENT, PHASE1_SCRIPT, PHASE3_SCRIPT):
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

    def test_phase3_is_a_real_dom_safety_and_interaction_matrix(self):
        phase3 = _read(PHASE3_SCRIPT)

        for required_contract in (
            'window.StudioShowcase.fixture("6x8")',
            'window.StudioShowcase.fixture("3x4")',
            'new KeyboardEvent("keydown"',
            'key: "ArrowDown"',
            "altKey: true",
            "focusPreservedOnMovedStableId",
            'document.getElementById("tab-chat")',
            "provider/RAG gate",
            "HELP_LOCAL_V1",
            '[...document.querySelectorAll(".evidence-trace .trace-kind")]',
            "new File([text], filename",
            "new DataTransfer()",
            "__ownerTestXssExecuted",
            "executableNodesInEditors",
            "localStorage.getItem",
            "window.StudioShowcase.resetLayout()",
            "await page.goto(options.baseUrl)",
            "new MutationObserver",
            'String(name).toLowerCase() === "td"',
            "matrixCellAllocations === 0",
            "matrixCellMutations === 0",
            "PREVIEW_CELL_BUDGET_EXCEEDED",
            "payloadBytes < 2 * 1024 * 1024",
            "prospectiveCells === 10_100",
        ):
            with self.subTest(contract=required_contract):
                self.assertIn(required_contract, phase3)

        for forbidden_dependency in (
            "playwright",
            "puppeteer",
            "selenium",
            "webdriver",
            "node_modules",
        ):
            self.assertNotIn(forbidden_dependency, phase3.casefold())
