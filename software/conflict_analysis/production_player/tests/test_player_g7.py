"""Portable Product and real-browser acceptance nodes for the frozen G7 slice."""

from __future__ import annotations

import json
import os
import re
import subprocess
import unittest
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

from django.conf import settings
from django.db import connection
from django.test import Client, TestCase
from django.urls import resolve, reverse
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from domain.enums import PublicationStatus
from domain.models import AuditEvent, ProjectWorkspace, TimeSlice
from domain.services.player_help_catalog import CATALOG_LOCALE, CATALOG_VERSION
from domain.services.player_projection import WORKSPACE_CREATE_CONTRACT
from domain.services.player_workspaces import SLICE_CREATE_CONTRACT
from domain.tests.test_player_foundation import FoundationPlayerFixture
from domain.tests.test_player_help_provisioning import (
    assert_player_help_http_payload,
    assert_player_help_provisioning_contract,
    player_help_snapshot,
)
from production_player.claim_boundaries import (
    CLAIM_BOUNDARY_CONTRACT_ID,
    CLAIM_BOUNDARY_CONTRACT_PATH,
    CLAIM_BOUNDARY_CONTRACT_SHA256,
    load_claim_boundaries,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PLAYER_PACKAGE_ROOT = PROJECT_ROOT / "production_player"
PLAYER_SCRIPT = PLAYER_PACKAGE_ROOT / "static" / "production_player" / "player.js"
PLAYER_STYLE = PLAYER_SCRIPT.with_suffix(".css")
PLAYER_BROWSER = PLAYER_PACKAGE_ROOT / "browser_tests" / "player_g7.mjs"
PLAYER_LAYOUT_KEY = "conflict-analysis-player:layout:v1"
COMMAND_IDS = (
    "CMD-WORKSPACE-CREATE",
    "CMD-WORKSPACE-OPEN",
    "CMD-WORKSPACE-SWITCH",
    "CMD-SLICE-CREATE",
    "CMD-SLICE-OPEN",
    "CMD-SLICE-SWITCH",
    "CMD-SLICE-REFRESH",
)


class ProductionPlayerG7Tests(FoundationPlayerFixture, TestCase):
    """The literal ten portable Product nodes; no Product ORM gateway is used."""

    maxDiff = None

    def setUp(self) -> None:
        self.setUp_player_fixture()
        self.client = Client()
        self.client.force_login(self.player_user)

    def _shell(self, name: str, **kwargs: object):
        response = self.client.get(reverse(name, kwargs=kwargs))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'self'", response["Content-Security-Policy"])
        self.assertIn(settings.CSRF_COOKIE_NAME, self.client.cookies)
        return response

    def _complete_workspace(self):
        workspace, receipt, body, operation_id = self.create_complete_workspace()
        return workspace, receipt, body, operation_id

    def _create_slice(self, workspace):
        body = self.slice_body()
        operation_id = uuid4()
        response = self.csrf_post(
            self.player_client,
            self.time_slice_url(workspace.pk),
            self.canonical_json(body),
            operation_id=operation_id,
            if_match=f'"{workspace.definition_manifest_hash}"',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return body, operation_id, response

    def test_routes_auth_claim_contract_and_separate_player_app_are_exact(self):
        entry_url = reverse("production_player:entry")
        project_url = reverse("production_player:project", kwargs={"project_id": self.project.pk})
        workspace_url = reverse(
            "production_player:workspace",
            kwargs={"workspace_id": self.default_workspace.pk},
        )
        anonymous = Client()
        for url in (entry_url, project_url, workspace_url):
            with self.subTest(url=url):
                denied = anonymous.get(url)
                self.assertEqual(denied.status_code, 401)
                self.assertEqual(set(denied.cookies), {settings.CSRF_COOKIE_NAME})
                self.assertEqual(anonymous.post(url).status_code, 405)

        contract = load_claim_boundaries()
        self.assertEqual(contract.contract, CLAIM_BOUNDARY_CONTRACT_ID)
        self.assertEqual(contract.sha256, CLAIM_BOUNDARY_CONTRACT_SHA256)
        self.assertIn(CLAIM_BOUNDARY_CONTRACT_SHA256, self._shell("production_player:entry").content.decode("utf-8"))
        self._shell("production_player:project", project_id=self.project.pk)
        self._shell("production_player:workspace", workspace_id=self.default_workspace.pk)
        self.assertEqual(resolve(entry_url).namespace, "production_player")
        self.assertEqual(resolve(project_url).namespace, "production_player")
        self.assertEqual(resolve(workspace_url).namespace, "production_player")
        views = (PLAYER_PACKAGE_ROOT / "views.py").read_text(encoding="utf-8")
        self.assertNotIn("domain.models", views)
        self.assertNotIn(".objects.", views)

    def test_onboarding_and_context_help_use_full_terms_while_dense_workspace_has_no_persistent_explanatory_prose(self):
        entry = self._shell("production_player:entry").content.decode("utf-8")
        for term in (
            "Опубликованное определение проекта",
            "Рабочее пространство",
            "Временной срез",
            "Foundation",
        ):
            self.assertIn(term, entry)
        self.assertNotIn("Работает бета-версия методики", entry)
        self.assertIn('id="local-help"', entry)
        workspace = self._shell(
            "production_player:workspace", workspace_id=self.default_workspace.pk
        ).content.decode("utf-8")
        self.assertIn('id="workspace-content"', workspace)
        self.assertIn('id="help-content" sandbox=""', workspace)
        self.assertNotIn("tutorial", workspace.lower())
        script = PLAYER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(PLAYER_LAYOUT_KEY, script)
        self.assertNotIn("sessionStorage.setItem", script)
        self.assertNotIn("indexedDB.open", script)
        self.assertNotIn("serviceWorker.register", script)

    def test_project_page_opens_only_foundation_published_definition_truth(self):
        project_shell = self._shell(
            "production_player:project", project_id=self.project.pk
        ).content.decode("utf-8")
        self.assertIn(str(self.project.pk), project_shell)
        payload = self.assert_canonical_get(
            self.player_client.get(self.definition_list_url(self.project.pk)),
            keys={"project", "definitions"},
        )
        self.assertEqual(payload["project"]["id"], str(self.project.pk))
        self.assertTrue(payload["definitions"])
        self.assertTrue(
            all(item["publication_status"] == PublicationStatus.PUBLISHED for item in payload["definitions"])
        )
        script = PLAYER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('const API = "/api/foundation/player/"', script)
        self.assertIn("${API}projects/${projectId}/definitions/", script)
        self.assertNotIn("/api/studio", script)
        self.assertNotIn("latest", script.lower())

    def test_workspace_create_and_reopen_use_only_foundation_receipt_and_pin(self):
        before = self.database_fingerprint()
        workspace, fresh, body, operation_id = self._complete_workspace()
        self.assertEqual(fresh.status_code, 201, fresh.content)
        self.assertEqual(fresh.json()["contract"], "FOUNDATION_PLAYER_WORKSPACE_CREATE_V1")
        self.assertEqual(fresh.json()["workspace_id"], body["id"])
        replay = self.csrf_post(
            self.player_client,
            self.workspace_list_url(self.project.pk),
            self.canonical_json(body),
            operation_id=operation_id,
            if_match=f'"{self.definition.manifest_hash}"',
        )
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.content, fresh.content)
        manifest = self.definition.manifest
        self.assertEqual(self.database_fingerprint(), (
            before[0] + 1,
            before[1],
            before[2] + 1,
            before[3] + len(manifest["actors"]),
            before[4] + len(manifest["analytical_elements"]),
            before[5] + len(manifest["actor_element_roles"]),
            before[6] + 8,
            before[7],
        ))
        opened = self.assert_canonical_get(
            self.player_client.get(self.workspace_url(workspace.pk)),
            keys={"project", "workspace", "definition"},
        )
        self.assertEqual(opened["workspace"]["id"], str(workspace.pk))
        self.assertEqual(opened["workspace"]["assessment_projection_status"], "COMPLETE")
        self.assertEqual(opened["workspace"]["definition_manifest_hash"], self.definition.manifest_hash)
        shell = self._shell("production_player:workspace", workspace_id=workspace.pk)
        self.assertIn(str(workspace.pk).encode("ascii"), shell.content)

    def test_time_slice_create_reopen_and_persisted_immutability_are_truthful(self):
        workspace, _, _, _ = self._complete_workspace()
        body, operation_id, fresh = self._create_slice(workspace)
        self.assertEqual(fresh.status_code, 201, fresh.content)
        self.assertEqual(fresh.json()["contract"], "FOUNDATION_PLAYER_TIME_SLICE_CREATE_V1")
        self.assertEqual(fresh.json()["created_slice"]["cutoff_date"], body["cutoff_date"])
        replay = self.csrf_post(
            self.player_client,
            self.time_slice_url(workspace.pk),
            self.canonical_json(body),
            operation_id=operation_id,
            if_match=f'"{workspace.definition_manifest_hash}"',
        )
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.content, fresh.content)
        listed = self.assert_canonical_get(
            self.player_client.get(self.time_slice_url(workspace.pk)),
            keys={"workspace_id", "time_slices"},
        )
        self.assertEqual(len(listed["time_slices"]), 1)
        self.assertEqual(listed["time_slices"][0]["cutoff_date"], "2026-01-15")
        persisted = TimeSlice.objects.get(pk=body["id"])
        self.assertEqual(persisted.cutoff_date, date(2026, 1, 15))
        self.assertEqual(
            self.player_client.patch(self.time_slice_url(workspace.pk), {}).status_code,
            405,
        )

    def test_structure_tree_is_arbitrary_cardinality_read_only_and_dom_bounded(self):
        payload = self.assert_canonical_get(
            self.player_client.get(self.definition_url(self.definition.pk)),
            keys={"project", "definition"},
        )
        definition = payload["definition"]
        self.assertEqual(definition["id"], str(self.definition.pk))
        self.assertIn("manifest", definition)
        manifest = definition["manifest"]
        self.assertGreaterEqual(len(manifest["actors"]), 2)
        self.assertGreaterEqual(len(manifest["analytical_elements"]), 2)
        entry = (PLAYER_PACKAGE_ROOT / "templates" / "production_player" / "entry.html").read_text(encoding="utf-8")
        script = PLAYER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('id="structure-tree"', entry)
        self.assertIn("100", script)
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotRegex(script, r"(?i)(?:patch|put|delete)\s*\(")
        self.assertNotIn("data-command-id", entry.split('id="structure-tree"', 1)[1].split("</aside>", 1)[0])

    def test_general_dynamic_experiment_plus_tabs_have_no_values_or_aggregation(self):
        workspace, _, _, _ = self._complete_workspace()
        payload = self.assert_canonical_get(
            self.player_client.get(self.experiments_url(workspace.pk)),
            keys={"workspace_id", "experiments"},
        )
        allowed = {
            "id", "name", "status", "order", "color", "expert_profile", "assessment_set",
        }
        self.assertTrue(all(set(item) <= allowed for item in payload["experiments"]))
        template = (PLAYER_PACKAGE_ROOT / "templates" / "production_player" / "workspace.html").read_text(encoding="utf-8")
        self.assertIn('id="experiment-general"', template)
        self.assertIn('id="experiment-plus"', template)
        self.assertIn("Доступно после этапа экспериментов", template)
        for forbidden in ("value", "average", "winner", "ranking", "chart", "modeling"):
            self.assertNotIn(forbidden, template.lower())

    def test_focus_aware_icon_toolbar_has_no_in_panel_commands_and_exposes_exact_disabled_boundaries(self):
        entry = (PLAYER_PACKAGE_ROOT / "templates" / "production_player" / "entry.html").read_text(encoding="utf-8")
        observed = tuple(re.findall(r'data-command-id="([^"]+)"', entry))
        self.assertEqual(observed, COMMAND_IDS)
        self.assertEqual(len(set(observed)), 7)
        self.assertIn("Доступно после этапа доказательств", entry)
        self.assertIn("Доступно после этапа чата", entry)
        workspace_template = (
            PLAYER_PACKAGE_ROOT / "templates" / "production_player" / "workspace.html"
        ).read_text(encoding="utf-8")
        self.assertIn("Доступно после этапа экспериментов", workspace_template)
        toolbar = entry.split('id="player-toolbar"', 1)[1].split("</nav>", 1)[0]
        self.assertLessEqual(toolbar.count('class="primary"'), 3)
        workspace_panel = entry.split('id="center-panel"', 1)[1].split('id="right-divider"', 1)[0]
        self.assertNotIn("data-command-id", workspace_panel)
        script = PLAYER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("F6", script)
        self.assertIn("aria-disabled", script)
        self.assertNotIn("Ctrl+R", script)

    def test_mouse_keyboard_splitters_bounded_layout_and_narrow_status_bar_are_exact(self):
        entry = (PLAYER_PACKAGE_ROOT / "templates" / "production_player" / "entry.html").read_text(encoding="utf-8")
        style = PLAYER_STYLE.read_text(encoding="utf-8")
        script = PLAYER_SCRIPT.read_text(encoding="utf-8")
        for selector in ("left-divider", "right-divider", "left-panel", "center-panel", "right-panel", "player-status-bar"):
            self.assertIn(f'id="{selector}"', entry)
        self.assertIn("aria-valuemin", entry)
        self.assertIn("aria-valuemax", entry)
        self.assertIn("pointerdown", script)
        self.assertIn("keydown", script)
        self.assertIn('event.key !== "F6"', script)
        self.assertIn("event.shiftKey ? 2 : 1", script)
        self.assertIn(PLAYER_LAYOUT_KEY, script)
        self.assertIn("220", script)
        self.assertIn("480", script)
        self.assertIn("status-bar", style)
        storage_keys = set(re.findall(r"conflict-analysis-player:[a-z0-9:-]+", script))
        self.assertEqual(storage_keys, {PLAYER_LAYOUT_KEY})

    def test_help_and_method_state_are_exact_no_beta_claim_without_strategy_and_no_domain_persistence(self):
        workspace, _, _, _ = self._complete_workspace()
        before = self.database_fingerprint()
        response = self.player_client.get(
            self.help_url(
                workspace.pk,
                "player.workspace",
                locale=CATALOG_LOCALE,
                version=CATALOG_VERSION,
            )
        )
        payload = self.assert_canonical_get(
            response,
            keys={"workspace_id", "ui_key", "locale", "help_topic"},
        )
        assert_player_help_http_payload(self, payload, ui_key="player.workspace")
        self.assertEqual(len(player_help_snapshot(workspace)), 8)
        self.assertEqual(self.database_fingerprint(), before)
        entry = (PLAYER_PACKAGE_ROOT / "templates" / "production_player" / "entry.html").read_text(encoding="utf-8")
        script = PLAYER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('id="help-content" sandbox=""', entry)
        self.assertIn("Методика не подключена", entry)
        self.assertNotIn("Работает бета-версия методики", entry)
        self.assertIn("/workspaces/", script)
        self.assertIn("/help/", script)
        self.assertNotIn("domain.models", script)
        self.assertEqual(CLAIM_BOUNDARY_CONTRACT_PATH.read_bytes()[-1:], b"\n")


@unittest.skipUnless(
    connection.vendor == "postgresql",
    "G7 Chromium nodes require PostgreSQL; SQLite runs the literal ten portable Product nodes only.",
)
class ProductionPlayerG7ChromiumTests(FoundationPlayerFixture, StaticLiveServerTestCase):
    """The literal two real-Chromium Product nodes on PostgreSQL."""

    host = "localhost"
    maxDiff = None

    def setUp(self) -> None:
        self.setUp_player_fixture()
        self.client.force_login(self.player_user)
        self.unscoped_player = self.make_player_user(
            project=self.project,
            suffix="browser-unscoped",
            scoped=False,
        )
        self.missing_permission_player = self.make_player_user(
            project=self.project,
            suffix="browser-missing-permission",
            permissions=(),
        )
        self.staff_player = self.make_player_user(
            project=self.project,
            suffix="browser-staff",
            staff=True,
        )

    def _session_cookie_for(self, user) -> str:
        client = Client()
        client.force_login(user)
        return client.cookies[settings.SESSION_COOKIE_NAME].value

    def _activate_high_cardinality_context(self) -> None:
        for index in range(len(self.manifest["actors"]), 128):
            self.manifest["actors"].append(
                {
                    "id": str(uuid4()),
                    "code": f"G7-BROWSER-ACTOR-{index:04d}",
                    "version": "1.0.0",
                    "label": f"Актор Player {index}",
                    "description": f"Проверяемая строка Player {index}.",
                    "actor_type": "GROUP",
                    "order": index,
                    "parent_id": None,
                }
            )
        project, definition, default_workspace = self.make_other_project()
        assert_player_help_provisioning_contract(self, default_workspace)
        player = self.make_player_user(
            project=project,
            suffix="browser-high-cardinality",
        )
        self.project = project
        self.definition = definition
        self.default_workspace = default_workspace
        self.player_user = player
        self.player_client = self.player_session(player, project_id=project.pk)
        self.client = Client()
        self.client.force_login(player)
        self.unscoped_player = self.make_player_user(
            project=project,
            suffix="browser-high-cardinality-unscoped",
            scoped=False,
        )
        self.missing_permission_player = self.make_player_user(
            project=project,
            suffix="browser-high-cardinality-missing-permission",
            permissions=(),
        )
        self.staff_player = self.make_player_user(
            project=project,
            suffix="browser-high-cardinality-staff",
            staff=True,
        )
        self.high_cardinality_actor_count = len(self.manifest["actors"])

    def _run_browser(self, *, scenario: str, workspace_id: object | None = None) -> dict[str, object]:
        session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        environment = os.environ.copy()
        environment.update(
            PLAYER_BASE_URL=self.live_server_url,
            PLAYER_PROJECT_ID=str(self.project.pk),
            PLAYER_DEFINITION_ID=str(self.definition.pk),
            PLAYER_SESSION_COOKIE_NAME=settings.SESSION_COOKIE_NAME,
            PLAYER_SESSION_COOKIE_VALUE=session_cookie,
            PLAYER_UNSCOPED_SESSION_COOKIE_VALUE=self._session_cookie_for(self.unscoped_player),
            PLAYER_MISSING_PERMISSION_SESSION_COOKIE_VALUE=self._session_cookie_for(self.missing_permission_player),
            PLAYER_STAFF_SESSION_COOKIE_VALUE=self._session_cookie_for(self.staff_player),
            PLAYER_EXPECTED_CLAIM_SHA256=CLAIM_BOUNDARY_CONTRACT_SHA256,
            PLAYER_EXPECTED_MANIFEST_SHA256=self.definition.manifest_hash,
            PLAYER_SCENARIO=scenario,
            PLAYER_CDP_TIMEOUT_MS=environment.get("PLAYER_CDP_TIMEOUT_MS", "60000"),
        )
        if workspace_id is not None:
            environment["PLAYER_WORKSPACE_ID"] = str(workspace_id)
        completed = subprocess.run(
            [environment.get("NODE_BIN", "node"), str(PLAYER_BROWSER)],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"browser stdout:\n{completed.stdout}\nbrowser stderr:\n{completed.stderr}",
        )
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertTrue(lines, completed.stderr)
        result = json.loads(lines[-1])
        self.assertEqual(result["browser_result"], "PASS")
        self.assertEqual(result["scenario"], scenario)
        return result

    def test_chromium_player_open_published_create_workspace_slice_reload_and_role_negative_matrix(self):
        before_domain = self.domain_fingerprint()
        before_project = self.project_domain_fingerprint(self.project)
        result = self._run_browser(scenario="owner-journey")
        self.assertEqual(result["project_id"], str(self.project.pk))
        self.assertEqual(result["definition_id"], str(self.definition.pk))
        self.assertEqual(result["claim_sha256"], CLAIM_BOUNDARY_CONTRACT_SHA256)
        self.assertEqual(result["workspace_projection_status"], "COMPLETE")
        self.assertEqual(result["slice_cutoff_date"], "2026-01-15")
        self.assertEqual(result["workspace_receipt_replay_status"], 200)
        self.assertEqual(result["slice_receipt_replay_status"], 200)
        self.assertEqual(result["transport_retry_status"], 201)
        self.assertEqual(
            result["role_negative_statuses"],
            {"anonymous": 401, "unscoped": 404, "missing_permission": 403, "staff": 403},
        )
        self.assertNotEqual(self.domain_fingerprint(), before_domain)
        self.assertNotEqual(self.project_domain_fingerprint(self.project), before_project)
        workspace = ProjectWorkspace.objects.get(
            pk=UUID(result["workspace_id"]), project=self.project
        )
        self.assertFalse(workspace.is_default)
        self.assertEqual(
            ProjectWorkspace.objects.filter(project=self.project, is_default=False).count(),
            1,
        )
        slices = {
            str(row.pk): row
            for row in TimeSlice.objects.filter(project=self.project, workspace=workspace)
        }
        self.assertEqual(set(slices), {result["slice_id"], result["transport_slice_id"]})
        self.assertEqual(slices[result["slice_id"]].cutoff_date, date(2026, 1, 15))
        self.assertEqual(slices[result["transport_slice_id"]].cutoff_date, date(2026, 1, 16))
        receipt_specs = (
            (result["workspace_operation_id"], WORKSPACE_CREATE_CONTRACT, workspace.pk),
            (result["slice_operation_id"], SLICE_CREATE_CONTRACT, UUID(result["slice_id"])),
            (result["transport_operation_id"], SLICE_CREATE_CONTRACT, UUID(result["transport_slice_id"])),
        )
        for operation_id, contract, entity_id in receipt_specs:
            receipt = AuditEvent.objects.get(pk=UUID(operation_id), project=self.project)
            self.assertEqual(receipt.entity_type, contract)
            self.assertEqual(receipt.entity_id, entity_id)
            self.assertEqual(receipt.after["operation_id"], operation_id)
            self.assertEqual(receipt.after["project_id"], str(self.project.pk))
        self.assertEqual(
            AuditEvent.objects.filter(
                pk__in=[UUID(operation_id) for operation_id, _, _ in receipt_specs]
            ).count(),
            3,
        )

    def test_chromium_player_professional_toolbar_splitters_dynamic_tabs_help_storage_and_no_structure_mutation(self):
        self._activate_high_cardinality_context()
        self.assertGreater(self.high_cardinality_actor_count, 100)
        workspace, _, _, _ = self.create_complete_workspace()
        before_domain = self.domain_fingerprint()
        before_project = self.project_domain_fingerprint(self.project)
        result = self._run_browser(
            scenario="shell-contract", workspace_id=workspace.pk
        )
        self.assertEqual(result["command_ids"], list(COMMAND_IDS))
        self.assertEqual(result["max_tree_rows"], 100)
        self.assertGreater(result["tree_total"], 100)
        self.assertEqual(result["storage_key"], PLAYER_LAYOUT_KEY)
        self.assertTrue(result["storage_shape_validated"])
        self.assertTrue(result["splitter_pointer_and_keyboard_validated"])
        self.assertTrue(result["f6_focus_cycle_validated"])
        self.assertTrue(result["document_network_silent"])
        self.assertTrue(result["chat_network_silent"])
        self.assertTrue(result["off_origin_free"])
        self.assertEqual(result["structure_mutation_requests"], 0)
        self.assertEqual(result["help_scope"], "PLAYER")
        self.assertEqual(self.domain_fingerprint(), before_domain)
        self.assertEqual(self.project_domain_fingerprint(self.project), before_project)
