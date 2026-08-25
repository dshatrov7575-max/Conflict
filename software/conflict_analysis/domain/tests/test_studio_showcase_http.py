from __future__ import annotations

import json

from django.conf import settings
from django.test import Client, SimpleTestCase, override_settings

from studio_showcase.session import fixture


def _showcase_installed_apps() -> list[str]:
    installed = list(settings.INSTALLED_APPS)
    for app in (
        "shared_ui.apps.SharedUiConfig",
        "studio_showcase.apps.StudioShowcaseConfig",
    ):
        if app not in installed:
            installed.append(app)
    return installed


@override_settings(
    INSTALLED_APPS=_showcase_installed_apps(),
    ROOT_URLCONF="conflict_analysis.studio_showcase_urls",
)
class ShowcaseHttpTests(SimpleTestCase):
    """Exercise the showcase with Django's database access entirely disabled."""

    client: Client

    def test_health_is_explicitly_session_only_and_uses_zero_database_queries(self):
        self.assertEqual(self.databases, frozenset())

        response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "application": "ConflictAnalysis Studio — Прототип",
                "persistence": "session-only",
            },
        )

    def test_index_renders_runnable_shell_with_zero_database_queries(self):
        self.assertEqual(self.databases, frozenset())

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "studio_showcase/index.html")
        self.assertContains(response, "ConflictAnalysis Studio — Прототип")
        self.assertContains(response, "SHOWCASE_SESSION_V1")
        self.assertContains(response, 'id="studio-workspace"', html=False)
        self.assertContains(response, 'class="studio-panel', count=3, html=False)
        self.assertContains(response, 'class="splitter', count=2, html=False)

    def test_both_fixture_apis_return_exact_cardinality_without_database_queries(self):
        self.assertEqual(self.databases, frozenset())

        for name, element_count, actor_count in (("6x8", 6, 8), ("3x4", 3, 4)):
            with self.subTest(name=name):
                response = self.client.get(f"/api/fixtures/{name}/")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["format"], "SHOWCASE_SESSION_V1")
                self.assertEqual(len(payload["analyticalElements"]), element_count)
                self.assertEqual(len(payload["actors"]), actor_count)

        self.assertEqual(self.client.get("/api/fixtures/4x4/").status_code, 404)

    def test_validate_api_accepts_valid_session_without_database_queries(self):
        self.assertEqual(self.databases, frozenset())

        response = self.client.post(
            "/api/validate/",
            data=json.dumps(fixture("6x8"), ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"valid": True, "diagnostics": []})

    def test_validate_api_returns_machine_stable_diagnostics(self):
        payload = fixture("3x4")
        payload["analyticalElements"][1]["code"] = payload["analyticalElements"][0][
            "code"
        ].lower()
        payload["actors"][0]["name"] = ""
        payload["actors"][1]["parentId"] = "missing-actor"

        response = self.client.post(
            "/api/validate/",
            data=json.dumps(payload, ensure_ascii=False),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["valid"])
        self.assertEqual(
            [(item["code"], item["path"]) for item in body["diagnostics"]],
            [
                ("CODE_DUPLICATE", "analyticalElements[1].code"),
                ("NAME_BLANK", "actors[0].name"),
                ("PARENT_REFERENCE_MISSING", "actors[1].parentId"),
            ],
        )

    def test_validate_api_rejects_malformed_or_oversized_json(self):
        malformed = self.client.post(
            "/api/validate/",
            data=b"{not-json",
            content_type="application/json",
        )
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["diagnostics"][0]["code"], "INVALID_JSON")

        oversized = self.client.post(
            "/api/validate/",
            data=b'"' + (b"x" * (2 * 1024 * 1024)) + b'"',
            content_type="application/json",
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(
            oversized.json()["diagnostics"][0]["code"],
            "SESSION_TOO_LARGE",
        )
