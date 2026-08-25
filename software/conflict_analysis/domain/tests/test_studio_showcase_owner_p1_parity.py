from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from django.test import SimpleTestCase

from studio_showcase.session import (
    MAX_ITEMS_PER_COLLECTION,
    MAX_PREVIEW_CELLS,
    build_fixture,
    validate_session,
)


APP_ROOT = Path(__file__).resolve().parents[2]
JAVASCRIPT_PATH = (
    APP_ROOT / "studio_showcase" / "static" / "studio_showcase" / "studio.js"
)
NODE_VALIDATOR = r"""
const { validateSession } = require(process.argv[1]);
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  process.stdout.write(JSON.stringify(validateSession(JSON.parse(input))));
});
"""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


class OwnerTestValidationParityTests(SimpleTestCase):
    maxDiff = None

    def assert_js_python_parity(self, payload: Any) -> list[dict[str, str]]:
        before = copy.deepcopy(payload)
        before_hash = _canonical_hash(payload)
        python_diagnostics = validate_session(payload)

        completed = subprocess.run(
            ["node", "-e", NODE_VALIDATOR, str(JAVASCRIPT_PATH)],
            input=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        expected_bytes = json.dumps(
            python_diagnostics,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.assertEqual(completed.stdout, expected_bytes)
        self.assertEqual(payload, before)
        self.assertEqual(_canonical_hash(payload), before_hash)
        return python_diagnostics

    def test_cross_collection_duplicate_and_parent_reference_have_exact_parity(self):
        payload = build_fixture(1, 2)
        payload["actors"][0]["id"] = payload["analyticalElements"][0]["id"]
        payload["actors"][1]["parentId"] = payload["analyticalElements"][0]["id"]

        diagnostics = self.assert_js_python_parity(payload)
        self.assertEqual(
            diagnostics,
            [
                {
                    "level": "error",
                    "code": "ID_DUPLICATE",
                    "path": "actors[0].id",
                    "message": (
                        "ID «element-01» уже используется в "
                        "analyticalElements[0]."
                    ),
                },
                {
                    "level": "error",
                    "code": "PARENT_REFERENCE_MISSING",
                    "path": "actors[1].parentId",
                    "message": (
                        "Ссылка на родительскую запись «element-01» не найдена."
                    ),
                },
            ],
        )

    def test_collection_limit_accepts_500_and_rejects_501_without_mutation(self):
        self.assertEqual(MAX_ITEMS_PER_COLLECTION, 500)
        accepted = build_fixture(500, 0)
        self.assertEqual(self.assert_js_python_parity(accepted), [])

        rejected = build_fixture(501, 0)
        diagnostics = self.assert_js_python_parity(rejected)
        self.assertEqual(
            diagnostics,
            [
                {
                    "level": "error",
                    "code": "COLLECTION_TOO_LARGE",
                    "path": "analyticalElements",
                    "message": (
                        "Список «analyticalElements» содержит 501 записей; "
                        "максимум — 500."
                    ),
                }
            ],
        )

    def test_preview_limit_accepts_10000_and_rejects_10001(self):
        self.assertEqual(MAX_PREVIEW_CELLS, 10_000)
        accepted = build_fixture(100, 100)
        self.assertEqual(self.assert_js_python_parity(accepted), [])

        rejected = build_fixture(73, 137)
        diagnostics = self.assert_js_python_parity(rejected)
        self.assertEqual(
            diagnostics,
            [
                {
                    "level": "error",
                    "code": "PREVIEW_CELL_BUDGET_EXCEEDED",
                    "path": "analyticalElements×actors",
                    "message": (
                        "Preview содержит 10001 ячеек; "
                        "безопасный максимум — 10000."
                    ),
                }
            ],
        )

    def test_under_two_megabyte_500x500_payload_is_safely_rejected(self):
        payload = build_fixture(500, 500)
        payload_bytes = _canonical_json(payload).encode("utf-8")
        self.assertLess(len(payload_bytes), 2 * 1024 * 1024)

        diagnostics = self.assert_js_python_parity(payload)
        self.assertEqual(
            [(item["code"], item["path"]) for item in diagnostics],
            [
                (
                    "PREVIEW_CELL_BUDGET_EXCEEDED",
                    "analyticalElements×actors",
                )
            ],
        )

    def test_preview_guard_precedes_any_cross_product_dom_allocation(self):
        javascript = JAVASCRIPT_PATH.read_text(encoding="utf-8")
        start = javascript.index("function showPreview()")
        end = javascript.index("function activateRightTab", start)
        preview_source = javascript[start:end]

        guard = preview_source.index("validateSession(session)")
        refusal = preview_source.index("return false")
        table_allocation = preview_source.index('document.createElement("table")')
        inner_loop = preview_source.index("actors.forEach", table_allocation)
        self.assertLess(guard, refusal)
        self.assertLess(refusal, table_allocation)
        self.assertLess(table_allocation, inner_loop)
