from __future__ import annotations

import ast
import os
import re
import tomllib
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase


APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
ENTRY_TEMPLATE = APP_ROOT / "templates" / "production_studio" / "entry.html"
DEFINITION_TEMPLATE = APP_ROOT / "templates" / "production_studio" / "definition.html"
CSS_PATH = APP_ROOT / "static" / "production_studio" / "studio.css"
JS_PATH = APP_ROOT / "static" / "production_studio" / "studio.js"


class _HiddenAncestorParser(HTMLParser):
    """Record whether selected elements are nested below a hidden boundary."""

    _VOID_ELEMENTS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self, targets: set[str]) -> None:
        super().__init__()
        self.targets = targets
        self.hidden_by_id: dict[str, bool] = {}
        self._stack: list[tuple[str, bool]] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        hidden = (self._stack[-1][1] if self._stack else False) or (
            "hidden" in attributes
        )
        identifier = attributes.get("id")
        if identifier in self.targets:
            self.hidden_by_id[identifier] = hidden
        if tag not in self._VOID_ELEMENTS:
            self._stack.append((tag, hidden))

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in self._VOID_ELEMENTS:
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                return


class ProductionStudioReadOnlyStaticContractTests(SimpleTestCase):
    maxDiff = None

    def test_production_python_has_no_domain_or_database_authority(self):
        production_python = sorted(
            path
            for path in APP_ROOT.rglob("*.py")
            if "tests" not in path.parts and "browser_tests" not in path.parts
        )
        self.assertTrue(production_python)
        for path in production_python:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
                elif isinstance(node, ast.Attribute):
                    self.assertNotEqual(
                        node.attr,
                        "objects",
                        f"direct ORM manager in {path.relative_to(PROJECT_ROOT)}",
                    )
            for module in imported:
                self.assertFalse(
                    module == "domain" or module.startswith("domain."),
                    f"Foundation internals imported by {path.relative_to(PROJECT_ROOT)}",
                )
                self.assertFalse(
                    module == "django.db" or module.startswith("django.db."),
                    f"database authority imported by {path.relative_to(PROJECT_ROOT)}",
                )

    def test_forbidden_studio_authority_files_do_not_exist(self):
        forbidden = (
            APP_ROOT / "models.py",
            APP_ROOT / "migrations",
            APP_ROOT / "session.py",
            APP_ROOT / "package.py",
            APP_ROOT / "validation.py",
            APP_ROOT / "evidence.py",
        )
        for path in forbidden:
            self.assertFalse(path.exists(), str(path.relative_to(PROJECT_ROOT)))

    def test_templates_have_permanent_spoken_and_visual_boundaries(self):
        entry = ENTRY_TEMPLATE.read_text(encoding="utf-8")
        definition = DEFINITION_TEMPLATE.read_text(encoding="utf-8")
        for name, source in (("entry", entry), ("definition", definition)):
            with self.subTest(template=name):
                self.assertIn('<html lang="ru">', source)
                self.assertIn('id="studio-boundary-banner"', source)
                self.assertIn('id="studio-limitations"', source)
                self.assertIn("<noscript>", source)
                self.assertIn("claim_statements", source)
                self.assertIn("claim_sha256", source)
                self.assertNotRegex(source.lower(), r'type\s*=\s*["\']password')
                self.assertNotIn("{% csrf_token %}", source)
                self.assertNotRegex(source.lower(), r'action\s*=\s*["\'][^"\']*(?:login|logout)')

        for fragment in (
            "overview",
            "project",
            "actors",
            "analytical-elements",
            "status-export",
            "limitations",
        ):
            self.assertIn(f'id="{fragment}"', definition)
        self.assertIn('data-state="DOCUMENT_UNAVAILABLE"', definition)
        self.assertIn('data-explicit-unavailable="true"', definition)
        self.assertIn('data-state="CHAT_UNAVAILABLE"', definition)
        self.assertRegex(
            definition,
            r'<button[^>]+disabled[^>]*>[^<]*</button>',
        )
        self.assertGreaterEqual(
            definition.count("UNKNOWN_NOT_EXPOSED_BY_FOUNDATION"),
            4,
        )
        self.assertIn('id="help-state"', definition)
        self.assertIn('id="help-topic"', definition)
        self.assertIn('id="help-content"', definition)
        self.assertIn('sandbox=""', definition)
        self.assertIn(
            'pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"',
            entry,
        )

        visibility = _HiddenAncestorParser(
            {"studio-boundary-banner", "definition-content", "studio-limitations"}
        )
        visibility.feed(definition)
        self.assertEqual(
            visibility.hidden_by_id,
            {
                "studio-boundary-banner": False,
                "definition-content": True,
                "studio-limitations": False,
            },
        )

    def test_static_client_is_get_only_bounded_and_has_no_hidden_authority(self):
        javascript = JS_PATH.read_text(encoding="utf-8")
        css = CSS_PATH.read_text(encoding="utf-8")
        combined = javascript + "\n" + css
        self.assertIn("conflict-analysis-studio:read-only-layout:v1", javascript)
        self.assertIn("STUDIO_READ_ONLY_LAYOUT_V1", javascript)
        self.assertIn(
            "const UUID_PATTERN = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;",
            javascript,
        )
        self.assertIn("parseLosslessJSON(raw).value", javascript)
        self.assertIn("firstExactHelpBinding", javascript)
        for literal in ("272", "360", "220", "420", "300", "500", "256", "100"):
            self.assertIn(literal, javascript)
        self.assertNotRegex(javascript, r"(?i)sessionStorage|indexedDB|serviceWorker|caches\s*\.")
        self.assertNotRegex(javascript, r"(?i)localStorage\s*\.\s*(?:project|definition|manifest|evidence)")
        self.assertNotIn("/api/studio", combined)
        self.assertNotRegex(javascript, r"(?i)method\s*:\s*[`\"'](?:POST|PUT|PATCH|DELETE|HEAD)")
        self.assertNotRegex(javascript, r"(?i)XMLHttpRequest|sendBeacon|WebSocket|EventSource")
        self.assertNotRegex(
            combined,
            r"(?i)(?:actor[-_ ]?element[-_ ]?matrix|heatmap[-_ ]?(?:cell|grid)|rank[-_ ]?(?:row|score)|total[-_ ]?row|average[-_ ]?row|power[-_ ]?badge|risk[-_ ]?badge)",
        )
        self.assertNotRegex(javascript, r"(?i)(?:validate|predict|recommend|calculate)\s*\(")

    def test_static_assets_are_resolvable_and_packaging_declarations_are_exact(self):
        self.assertIsNotNone(finders.find("production_studio/studio.css"))
        self.assertIsNotNone(finders.find("production_studio/studio.js"))
        pyproject = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        includes = pyproject["tool"]["setuptools"]["packages"]["find"]["include"]
        self.assertIn("production_studio*", includes)
        package_data = pyproject["tool"]["setuptools"]["package-data"][
            "production_studio"
        ]
        self.assertEqual(
            set(package_data),
            {
                "contracts/*.json",
                "contracts/*.sha256",
                "templates/production_studio/*.html",
                "static/production_studio/*.css",
                "static/production_studio/*.js",
            },
        )

    def test_built_wheel_contains_runtime_assets_and_no_studio_authority(self):
        wheel_value = os.environ.get("STUDIO_C0_WHEEL")
        if not wheel_value:
            self.skipTest("STUDIO_C0_WHEEL is set by the wheel acceptance job")
        wheel = Path(wheel_value).resolve()
        self.assertTrue(wheel.is_file(), wheel)
        with zipfile.ZipFile(wheel) as archive:
            names = set(archive.namelist())
        required = {
            "production_studio/__init__.py",
            "production_studio/apps.py",
            "production_studio/claim_boundaries.py",
            "production_studio/urls.py",
            "production_studio/views.py",
            "production_studio/contracts/read_only_claim_boundaries_v1.ru.json",
            "production_studio/contracts/read_only_claim_boundaries_v1.ru.json.sha256",
            "production_studio/templates/production_studio/entry.html",
            "production_studio/templates/production_studio/definition.html",
            "production_studio/static/production_studio/studio.css",
            "production_studio/static/production_studio/studio.js",
        }
        self.assertTrue(required <= names, sorted(required - names))
        forbidden = {
            "production_studio/models.py",
            "production_studio/session.py",
            "production_studio/package.py",
            "production_studio/validation.py",
            "production_studio/evidence.py",
        }
        self.assertFalse(forbidden & names)
        self.assertFalse(
            any(name.startswith("production_studio/migrations/") for name in names)
        )

    def test_hosted_and_windows_browser_roles_are_documented(self):
        runtime_doc = (
            PROJECT_ROOT / "docs" / "production-studio-c-read-only-runtime.md"
        ).read_text(encoding="utf-8")
        for required in (
            "CPython 3.12",
            "Django 5.2",
            "Gunicorn 23",
            "PostgreSQL 18",
            "HTTPS",
            "reverse proxy",
            "Windows",
            "Chromium",
            "SQLite",
        ):
            self.assertIn(required.casefold(), runtime_doc.casefold())
