"""Cross-screen presentation contracts, plus real Chromium keyboard/layout checks.

The browser fixtures render real templates with synthetic data. Existing live-server
tests separately exercise Foundation writes, lifecycle recovery and calculations.
"""
import json
import os
from dataclasses import replace
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import tempfile

from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase, override_settings

from calculation import calculate
from calculation.examples import example_snapshot
from player_integration.inputs import ExperimentForm, WeightForm
from scenario_modeling.adapter import result_view
from scenario_modeling.model import ScenarioModel, parameters
from scenario_modeling.views import OverrideForm


ROOT = Path(__file__).resolve().parents[2]
APPS = list(settings.INSTALLED_APPS)
for app in ("player_integration", "scenario_modeling"):
    if not any(item.startswith(app) for item in APPS):
        APPS.append(app)
SCREENS = [
    "production_studio/entry.html", "production_studio/definition.html",
    "production_studio/audited_draft_entry.html", "production_studio/audited_draft_definition.html",
    "production_studio/lifecycle_publication_definition.html",
    "production_player/entry.html", "production_player/project.html",
    "production_player/workspace.html", "production_player/experiment.html",
    "player_integration/start.html", "player_integration/experiment.html",
    "player_integration/inputs.html", "player_integration/result.html",
    "scenario_modeling/result.html",
]
UUID = "11111111-1111-4111-8111-111111111111"


class Markup(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.nodes = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.nodes.append((tag, dict(attrs)))


def fixtures():
    snapshot = replace(example_snapshot([10, -10, None]), experiment_id=UUID, time_slice_id=UUID)
    run = json.loads(calculate(snapshot).to_json())
    weights = WeightForm(snapshot)
    model = ScenarioModel(UUID, snapshot).with_override(parameters(snapshot)[0].key, "5")
    context = {
        "studio_authenticated": True, "player_authenticated": True,
        "definition_id": UUID, "project_id": UUID, "workspace_id": UUID,
        "experiment_id": UUID, "g8_shell": True,
        "experiment": {"pk": UUID, "name": "Эксперимент " + "ОченьДлинноеЗначение" * 10,
                       "assessment_set": {"kind": "HUMAN"}, "status": "DRAFT",
                       "expert_profile": {"display_name": "Эксперт"}},
        "slices": [{"pk": UUID, "name": "Срез", "version": "1.0.0"}],
        "snapshot": json.loads(snapshot.to_json()), "run": run,
        "lane": {"experiment_id": UUID, "experiment_name": "Расчёт", "assessment_kind": "HUMAN"},
        "snapshot_json": snapshot.to_json(), "run_json": json.dumps(run),
        "scenario_token": "synthetic-rendering-only", "claim_sha256": "0" * 64,
        "claim_contract": "STUDIO_READ_ONLY_CLAIM_BOUNDARIES_V1",
        "claim_statements": [{"code": "TRACEABILITY", "text": "Прослеживаемость не подтверждает истинность."}],
    }
    result = {}
    for screen in SCREENS:
        local = dict(context)
        if screen == "player_integration/start.html":
            local["form"] = ExperimentForm()
        elif screen == "player_integration/inputs.html":
            local.update(form=weights, rows=weights.rows())
        elif screen == "scenario_modeling/result.html":
            local.update(result_view(model), model=model, form=OverrideForm(model), has_parameters=True,
                         choices=[{"key": row.key, "label": row.label, "min": row.minimum,
                                   "max": row.maximum, "value": str(row.baseline.value),
                                   "status": row.baseline.status}
                                  for row in parameters(snapshot) if row.baseline.known])
        result[screen] = render_to_string(screen, local)
    return result


@override_settings(ROOT_URLCONF="player_integration.project_urls", INSTALLED_APPS=APPS)
class PanelUIContractTests(SimpleTestCase):
    def test_every_work_screen_resolves_help_anchors_and_unique_ids(self):
        for screen, html in fixtures().items():
            with self.subTest(screen=screen):
                nodes = Markup(html).nodes
                ids = [attrs["id"] for _, attrs in nodes if "id" in attrs]
                self.assertEqual(len(ids), len(set(ids)), f"duplicate DOM IDs in {screen}")
                topics = {attrs["data-help-topic"] for _, attrs in nodes if "data-help-topic" in attrs}
                panels = [attrs["data-panel-help"] for _, attrs in nodes if "data-panel-help" in attrs]
                self.assertTrue(panels, screen)
                self.assertTrue(set(panels) <= topics, set(panels) - topics)
                self.assertEqual(ids.count("ui-help-dialog"), 1)
                self.assertIn("production_studio/panel_ui.js", html)

    def test_actions_are_declared_and_old_helper_copy_is_only_in_help(self):
        for screen, html in fixtures().items():
            with self.subTest(screen=screen):
                work = html.split('<dialog id="ui-help-dialog"')[0]
                for tag, attrs in Markup(work).nodes:
                    if tag != "button" or attrs.get("role") == "tab":
                        continue
                    if any(key in attrs for key in ("data-dataset", "data-authoring-section")):
                        continue  # Selection controls retain their visible choices.
                    self.assertIn(attrs.get("data-ui-kind"), {"primary", "utility"}, attrs)
                    self.assertTrue(attrs.get("data-ui-icon"), attrs)
                for phrase in (
                    "Для известного веса укажите", "Сервер не ведёт историю запусков",
                    "Для каждого изменения показан отдельный расчёт", "Начните с проекта",
                    "UUID попадёт только в адрес страницы", "Ползунок имеет шаг 0,1",
                ):
                    self.assertNotIn(phrase, work)
                self.assertIn("UNKNOWN/HOLD", html)
                self.assertIn("data-help-topic=\"warnings\"", html)

    def test_moved_details_remain_available_without_a_foundation_help_binding(self):
        help_html = render_to_string("production_studio/ui_help.html", {})
        for phrase in (
            "RGU — вес участника", "0…10", "UNKNOWN", "не заменяется нулём",
            "Эти delta не складываются", "8 часов", "не ведёт историю запусков",
            "18 METHOD_BLOCKED", "24 RECODING_REQUIRED", "побайтный повтор FD05",
            "без слепого POST", "Хеш не подтверждает достоверность",
        ):
            self.assertIn(phrase, help_html)

    def test_real_chromium_panel_help_actions_keyboard_and_responsive_layout(self):
        with tempfile.TemporaryDirectory(prefix="conflict-panel-ui-") as folder:
            fixture_file = Path(folder) / "screens.json"
            fixture_file.write_text(json.dumps(fixtures(), ensure_ascii=False), encoding="utf-8")
            completed = subprocess.run(
                [os.getenv("NODE_BIN", "node"), str(ROOT / "production_studio/browser_tests/panel_ui.mjs"), str(fixture_file)],
                cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True,
                encoding="utf-8", timeout=240,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            report = json.loads(completed.stdout.strip().splitlines()[-1])
            self.assertEqual(report["screens"], len(SCREENS))
            self.assertEqual(report["viewports"], [360, 768, 1280, 1440])
            self.assertGreater(report["panel_help_checks"], 80)
            self.assertTrue(report["keyboard_and_accessibility"])
