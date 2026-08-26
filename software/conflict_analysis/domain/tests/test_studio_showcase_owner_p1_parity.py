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
CORPUS_PATH = (
    APP_ROOT / "studio_showcase" / "contracts" / "validation_vectors_v1.json"
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
NODE_CORPUS_VALIDATOR = r"""
const crypto = require("node:crypto");
const { validateSession } = require(process.argv[1]);
function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    const entries = Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`);
    return `{${entries.join(",")}}`;
  }
  return JSON.stringify(value);
}
function hash(value) {
  return crypto.createHash("sha256").update(canonical(value), "utf8").digest("hex");
}
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => { input += chunk; });
process.stdin.on("end", () => {
  const payload = JSON.parse(input);
  const beforeHash = hash(payload);
  const diagnostics = validateSession(payload);
  process.stdout.write(JSON.stringify({
    beforeHash,
    afterHash: hash(payload),
    diagnosticsJson: JSON.stringify(diagnostics),
  }));
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


def _diagnostics_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _set_path(payload: Any, path: list[str | int], value: Any) -> None:
    target = payload
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = copy.deepcopy(value)


def _build_corpus_payload(case: dict[str, Any]) -> Any:
    source = case["source"]
    if "fixture" in source:
        payload = build_fixture(*source["fixture"])
    else:
        payload = copy.deepcopy(source["literal"])
    for mutation in case.get("set", []):
        _set_path(payload, mutation["path"], mutation["value"])
    return payload


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


class OwnerTestSharedValidationCorpusTests(SimpleTestCase):
    maxDiff = None

    def test_versioned_corpus_has_exact_ordered_parity_and_deep_nonmutation(self):
        corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(corpus["format"], "SHOWCASE_VALIDATION_VECTORS_V1")
        self.assertEqual(corpus["version"], "1.0.0")

        cases = {case["name"]: case for case in corpus["cases"]}
        self.assertTrue(
            {
                "valid_6x8",
                "valid_3x4",
                "valid_empty",
                "valid_ordinary_custom",
                "session_not_object",
                "wrong_format_and_version",
                "blank_project_name",
                "collections_not_arrays",
                "rows_not_objects",
                "blank_duplicate_and_required_fields",
                "within_collection_parent_missing",
                "cross_collection_duplicate_id_and_parent",
                "supported_ascii_cyrillic_case_normalization",
                "supported_lowercase_not_compatibility_casefold",
                "numeric_ids_1_and_1_point_0_are_type_errors_not_duplicates",
                "boolean_null_container_and_parent_types",
                "explicit_unicode_whitespace_and_case_edges",
                "collection_exactly_500",
                "collection_501",
                "preview_exactly_10000",
                "preview_10001",
                "under_2mb_500x500",
            }.issubset(cases)
        )

        for name, case in cases.items():
            with self.subTest(case=name):
                payload = _build_corpus_payload(case)
                expected_json = _diagnostics_json(case["expectedDiagnostics"])
                before = copy.deepcopy(payload)
                before_hash = _canonical_hash(payload)

                python_diagnostics = validate_session(payload)
                self.assertEqual(_diagnostics_json(python_diagnostics), expected_json)
                self.assertEqual(payload, before)
                self.assertEqual(_canonical_hash(payload), before_hash)

                completed = subprocess.run(
                    ["node", "-e", NODE_CORPUS_VALIDATOR, str(JAVASCRIPT_PATH)],
                    input=_diagnostics_json(payload),
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                javascript_result = json.loads(completed.stdout)
                self.assertEqual(javascript_result["diagnosticsJson"], expected_json)
                self.assertEqual(
                    javascript_result["diagnosticsJson"],
                    _diagnostics_json(python_diagnostics),
                )
                self.assertEqual(
                    javascript_result["afterHash"],
                    javascript_result["beforeHash"],
                )

                byte_limit = case.get("assertSerializedBytesBelow")
                if byte_limit is not None:
                    self.assertLess(
                        len(_canonical_json(payload).encode("utf-8")),
                        byte_limit,
                    )
