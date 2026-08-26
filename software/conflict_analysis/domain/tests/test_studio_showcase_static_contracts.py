from __future__ import annotations

import ast
import re
from pathlib import Path

from django.test import SimpleTestCase


APP_ROOT = Path(__file__).resolve().parents[2]
SHOWCASE_ROOT = APP_ROOT / "studio_showcase"
SHARED_UI_ROOT = APP_ROOT / "shared_ui"
TEMPLATE_PATH = SHOWCASE_ROOT / "templates" / "studio_showcase" / "index.html"
JAVASCRIPT_PATH = SHOWCASE_ROOT / "static" / "studio_showcase" / "studio.js"
STYLESHEET_PATH = SHOWCASE_ROOT / "static" / "studio_showcase" / "studio.css"
TOKENS_PATH = SHARED_UI_ROOT / "static" / "shared_ui" / "tokens.css"

PROTOTYPE_BANNER = (
    "Исследовательский прототип — публикация и научная валидация ещё не завершены"
)
NEGATIVE_DECISION_DISCLAIMER = (
    "Прототип не прогнозирует конфликт, не ранжирует людей и не принимает "
    "решения за пользователя."
)
PARTNER_OPENING_LABEL = (
    "Исследовательский прототип. Демонстрируются архитектура, доказательная "
    "трассировка и рабочий процесс. Научная валидность Power-профиля, "
    "превосходство над сильным экспертным baseline, прогнозирование и "
    "production readiness пока не заявляются."
)


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"Required showcase asset is missing: {path}")
    return path.read_text(encoding="utf-8")


def _hex_token(css: str, token: str) -> str:
    match = re.search(rf"{re.escape(token)}\s*:\s*(#[0-9a-fA-F]{{6}})\s*;", css)
    if not match:
        raise AssertionError(f"Missing six-digit color token {token}")
    return match.group(1)


def _relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        channel / 12.92
        if channel <= 0.04045
        else ((channel + 0.055) / 1.055) ** 2.4
        for channel in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (light + 0.05) / (dark + 0.05)


class ShowcasePresentationContractTests(SimpleTestCase):
    def test_template_has_visible_prototype_boundary_and_plain_language_onboarding(self):
        html = _read(TEMPLATE_PATH)

        self.assertIn('<html lang="ru">', html)
        self.assertIn(PROTOTYPE_BANNER, html)
        self.assertIn(NEGATIVE_DECISION_DISCLAIMER, html)
        self.assertIn(PARTNER_OPENING_LABEL, html)
        for visible_copy in (
            "Проблемные темы",
            "Группы людей и организаций",
            "Версия структуры отделена от доказательств",
            "Доказательства ≠ оценки",
            "Только эта сессия",
            "SHOWCASE_SESSION_V1",
        ):
            self.assertIn(visible_copy, html)

        self.assertIn('class="skip-link"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('role="status"', html)

    def test_toolbar_tree_panels_and_right_tabs_are_complete_and_accessible(self):
        html = _read(TEMPLATE_PATH)

        commands = {
            "new": "Новый",
            "open": "Открыть",
            "clone": "Клонировать",
            "save": "Сохранить",
            "validate": "Проверить",
            "import": "Импорт",
            "export": "Экспорт",
            "publish": "Опубликовать",
        }
        for command, label in commands.items():
            self.assertRegex(html, rf'data-command="{command}"')
            self.assertIn(label, html)
        self.assertRegex(
            html,
            r'data-command="publish"[\s\S]{0,240}aria-disabled="true"',
        )

        for tree_label in (
            "Проект",
            "Проблемные темы",
            "Группы людей и организаций",
            "Параметры",
            "Публикации",
            "Справка",
        ):
            self.assertIn(tree_label, html)

        panels = re.findall(r'class="[^"]*\bstudio-panel\b[^"]*"', html)
        splitters = re.findall(r'class="[^"]*\bsplitter\b[^"]*"', html)
        self.assertEqual(len(panels), 3)
        self.assertEqual(len(splitters), 2)
        self.assertEqual(html.count('role="separator"'), 2)
        self.assertEqual(html.count('aria-orientation="vertical"'), 2)
        self.assertGreaterEqual(html.count('tabindex="0"'), 3)

        for tab in ("document", "chat", "help"):
            self.assertRegex(
                html,
                rf'role="tab"[^>]+data-right-tab="{tab}"',
            )
            self.assertRegex(
                html,
                rf'role="tabpanel"[^>]+data-right-panel="{tab}"',
            )
        self.assertIn("Документ", html)
        self.assertIn("Чат", html)
        self.assertIn("Справка", html)
        self.assertIn(
            "Будет подключён после отдельного provider/RAG gate",
            html,
        )
        self.assertRegex(html, r'<button[^>]+disabled[^>]*>[^<]*Начать разговор')

    def test_versioned_help_topics_have_explicit_question_mark_buttons(self):
        html = _read(TEMPLATE_PATH)
        javascript = _read(JAVASCRIPT_PATH)

        self.assertIn("HELP_LOCAL_V1", html)
        for topic in (
            "welcome",
            "project",
            "actors",
            "analytical-elements",
            "validation",
            "preview",
            "publication-limitation",
        ):
            with self.subTest(topic=topic):
                self.assertIn(f'data-help-topic="{topic}"', html)
                self.assertRegex(
                    html,
                    rf'data-help-topic="{re.escape(topic)}"[^>]*>\?</button>',
                )
                self.assertRegex(
                    javascript.replace('"', "").replace("'", ""),
                    rf"(?m)^\s*{re.escape(topic)}\s*:",
                )

    def test_evidence_trace_is_exact_and_contains_no_numeric_claim(self):
        html = _read(TEMPLATE_PATH)
        trace_match = re.search(
            r'<ol class="evidence-trace"[^>]*>([\s\S]*?)</ol>',
            html,
        )
        self.assertIsNotNone(trace_match)
        trace = trace_match.group(1)

        kinds = re.findall(r'<span class="trace-kind">([^<]+)</span>', trace)
        self.assertEqual(
            kinds,
            ["Assessment", "Fact", "Fragment", "DocumentVersion", "Source"],
        )
        self.assertNotRegex(trace, r"\b\d+(?:[.,]\d+)?\b")

    def test_visible_copy_has_no_positive_production_or_prediction_claim(self):
        html = _read(TEMPLATE_PATH).casefold()
        javascript = _read(JAVASCRIPT_PATH).casefold()

        # Mandatory negative disclosures intentionally name forbidden
        # capabilities. Remove only those exact disclosures before scanning
        # both server-rendered and runtime-generated authored copy.
        claims = f"{html}\n{javascript}"
        for allowed_negative_disclosure in (
            PROTOTYPE_BANNER,
            NEGATIVE_DECISION_DISCLAIMER,
            PARTNER_OPENING_LABEL,
        ):
            claims = claims.replace(allowed_negative_disclosure.casefold(), "")

        self.assertNotRegex(claims, r"\bpower\b|\bpow\b|\brisk[\s_-]*score\b")
        self.assertNotRegex(claims, r"\bpos\b|\bsal\b|формул")
        for forbidden in (
            r"production[\s_-]*ready",
            r"валидированн\w*\s+(?:power|pow)",
            r"(?:прототип|studio|система)\s+(?:успешно\s+)?прогнозир",
            r"(?:публикация|научная валидация)\s+(?:успешно\s+)?завершен",
            r"(?:решение|рекомендаци\w*)\s+(?:автоматически\s+)?сформирован",
        ):
            self.assertNotRegex(claims, forbidden)


class ShowcaseInteractionContractTests(SimpleTestCase):
    def test_splitters_use_pointer_events_and_versioned_layout_storage(self):
        html = _read(TEMPLATE_PATH)
        javascript = _read(JAVASCRIPT_PATH)

        self.assertEqual(html.count('data-splitter="'), 2)
        for event_name in ("pointerdown", "pointermove", "pointerup"):
            self.assertIn(event_name, javascript)
        self.assertIn("setPointerCapture", javascript)
        self.assertIn("gridTemplateColumns", javascript)

        self.assertIn("conflict-analysis-studio:layout:v1", javascript)
        self.assertIn("localStorage.getItem", javascript)
        self.assertIn("localStorage.setItem", javascript)
        self.assertIn("localStorage.removeItem", javascript)
        self.assertIn("Number.isFinite", javascript)
        self.assertIn("resetLayout", javascript)
        self.assertIn("data-reset-layout", html)

        stored_keys = {
            argument.strip()
            for argument in re.findall(r"safeStorageSet\(([^,]+),", javascript)
            if argument.strip() != "key"
        }
        self.assertEqual(stored_keys, {"LAYOUT_KEY"})

    def test_splitter_html_and_runtime_aria_values_share_one_layout_contract(self):
        html = _read(TEMPLATE_PATH)
        javascript = _read(JAVASCRIPT_PATH)

        defaults_match = re.search(
            r"DEFAULT_LAYOUT\s*=\s*Object\.freeze\(\{\s*left:\s*(\d+),\s*"
            r"right:\s*(\d+),",
            javascript,
        )
        limits_match = re.search(
            r"WIDTH_LIMITS\s*=\s*Object\.freeze\(\{\s*left:\s*\[(\d+),\s*(\d+)\],\s*"
            r"right:\s*\[(\d+),\s*(\d+)\]",
            javascript,
        )
        self.assertIsNotNone(defaults_match)
        self.assertIsNotNone(limits_match)
        defaults = {
            "left": int(defaults_match.group(1)),
            "right": int(defaults_match.group(2)),
        }
        limits = {
            "left": (int(limits_match.group(1)), int(limits_match.group(2))),
            "right": (int(limits_match.group(3)), int(limits_match.group(4))),
        }

        for side in ("left", "right"):
            tag_match = re.search(
                rf'<div\s+[^>]*data-splitter="{side}"[^>]*>',
                html,
            )
            self.assertIsNotNone(tag_match)
            tag = tag_match.group(0)

            def aria_integer(name: str) -> int:
                match = re.search(rf'{name}="(\d+)"', tag)
                if not match:
                    self.fail(f"{side} splitter is missing {name}")
                return int(match.group(1))

            self.assertEqual(aria_integer("aria-valuemin"), limits[side][0])
            self.assertEqual(aria_integer("aria-valuemax"), limits[side][1])
            self.assertEqual(aria_integer("aria-valuenow"), defaults[side])

        self.assertIn('setAttribute("aria-valuenow"', javascript)

    def test_keyboard_navigation_covers_tabs_splitters_and_row_reorder(self):
        javascript = _read(JAVASCRIPT_PATH)

        self.assertIn('addEventListener("keydown"', javascript)
        for key in ("ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"):
            self.assertIn(key, javascript)
        self.assertIn("aria-selected", javascript)
        self.assertIn("aria-valuenow", javascript)
        self.assertIn("moveRow", javascript)

    def test_session_editor_and_public_test_api_are_real_interactions(self):
        html = _read(TEMPLATE_PATH)
        javascript = _read(JAVASCRIPT_PATH)

        for hook in (
            "data-add-row",
            "data-fixture",
            "data-command",
            "diagnostics",
            "structure-preview",
            "project-name",
        ):
            self.assertIn(hook, html)
        for interaction in (
            "dragstart",
            "dragover",
            "drop",
            "deleteRow",
            "exportSession",
            "loadSession",
            "validateSession",
            "updateRowFromInput",
            "nextAvailableCode",
            "rowFocusSelector",
            "restoreRowFocus",
        ):
            self.assertIn(interaction, javascript)

        for dynamic_cardinality_contract in (
            "session.analyticalElements.length",
            "session.actors.length",
            "themes.forEach",
            "actors.forEach",
        ):
            self.assertIn(dynamic_cardinality_contract, javascript)

        self.assertIn("window.StudioShowcase", javascript)
        for public_method in (
            "getSession",
            "loadSession",
            "validate",
            "getLayout",
            "resetLayout",
            "fixture",
            "exportSession",
        ):
            self.assertRegex(javascript, rf"\b{public_method}\b")

        self.assertIn("SHOWCASE_SESSION_V1", javascript)
        self.assertNotRegex(
            javascript,
            r"localStorage\.setItem\([^,]*(?:session|project|fixture)",
        )

    def test_add_and_reorder_contracts_preserve_uniqueness_and_keyboard_focus(self):
        javascript = _read(JAVASCRIPT_PATH)

        self.assertRegex(
            javascript,
            r"function nextAvailableCode\([^)]+\)[\s\S]+?\.toLocaleLowerCase\(",
        )
        self.assertRegex(
            javascript,
            r"nextAvailableCode\(collection,\s*\"CI\"\)",
        )
        self.assertRegex(
            javascript,
            r"nextAvailableCode\(collection,\s*\"ACT\"\)",
        )
        self.assertRegex(
            javascript,
            r"function moveRow\([^)]*focusControl[^)]*\)[\s\S]+?restoreRowFocus",
        )
        self.assertIn("?.focus({ preventScroll: true })", javascript)
        self.assertIn("heading.tabIndex = -1", javascript)


class ShowcaseArchitectureBoundaryTests(SimpleTestCase):
    def test_showcase_and_shared_ui_have_no_models_or_migrations(self):
        for package_root in (SHOWCASE_ROOT, SHARED_UI_ROOT):
            self.assertFalse((package_root / "models.py").exists())
            self.assertFalse((package_root / "migrations").exists())

    def test_showcase_python_does_not_import_or_call_the_orm(self):
        forbidden_modules = {
            "django.db",
            "domain.models",
            "domain.migrations",
            "studio_showcase.models",
        }
        python_paths = sorted(
            [*SHOWCASE_ROOT.rglob("*.py"), *SHARED_UI_ROOT.rglob("*.py")]
        )
        self.assertTrue(python_paths)

        violations: list[str] = []
        for path in python_paths:
            tree = ast.parse(_read(path), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    modules = []
                for module in modules:
                    if any(
                        module == forbidden
                        or module.startswith(f"{forbidden}.")
                        or module.endswith(".models")
                        or module.endswith(".migrations")
                        for forbidden in forbidden_modules
                    ):
                        violations.append(f"{path.relative_to(APP_ROOT)}:{node.lineno} {module}")
                if isinstance(node, ast.Attribute) and node.attr == "objects":
                    violations.append(
                        f"{path.relative_to(APP_ROOT)}:{node.lineno} .objects"
                    )

        self.assertEqual(violations, [])

    def test_presentation_tokens_meet_basic_text_contrast_and_focus_smoke(self):
        tokens = _read(TOKENS_PATH)
        studio_css = _read(STYLESHEET_PATH)
        white = _hex_token(tokens, "--ca-surface")

        for token in (
            "--ca-navy-900",
            "--ca-teal-700",
            "--ca-amber-700",
            "--ca-red-700",
            "--ca-ink",
        ):
            with self.subTest(token=token):
                self.assertGreaterEqual(
                    _contrast_ratio(_hex_token(tokens, token), white),
                    4.5,
                )

        self.assertIn(":focus-visible", tokens)
        self.assertIn("@media (forced-colors: active)", tokens)
        self.assertIn("prefers-reduced-motion", studio_css)
        self.assertNotIn("outline: none", f"{tokens}\n{studio_css}".casefold())
