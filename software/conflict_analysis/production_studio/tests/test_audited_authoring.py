from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import re
import subprocess
import zlib
from pathlib import Path
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name
from domain.enums import HelpApplicationScope, PublicationStatus
from domain.models import AuditEvent, HelpTopic, Project, ProjectDefinitionVersion, UIHelpBinding
from domain.policies import StudioPrincipal, StudioRole
from domain.services.project_definitions import create_project_definition_draft
from production_studio.authoring_claim_boundaries import (
    AUTHORING_CLAIM_BOUNDARY_CONTRACT_BYTES,
    AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID,
    AUTHORING_CLAIM_BOUNDARY_CONTRACT_PATH,
    AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256,
    AUTHORING_CLAIM_BOUNDARY_EXPECTED_SIDECAR,
    AUTHORING_CLAIM_BOUNDARY_SIDECAR_PATH,
    load_authoring_claim_boundaries,
)
from production_studio.tests import database_fingerprint, foundation_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORING_SCRIPT = (
    PROJECT_ROOT
    / "production_studio"
    / "static"
    / "production_studio"
    / "audited_draft.js"
)
AUTHORING_STYLE = AUTHORING_SCRIPT.with_suffix(".css")
BROWSER_SCRIPT = (
    PROJECT_ROOT
    / "production_studio"
    / "browser_tests"
    / "audited_authoring.mjs"
)
AUTHORING_CLAIM_CODES = (
    "STATUS",
    "AUTHORITY",
    "ATTRIBUTION",
    "DRAFT_MEMORY",
    "RECONCILIATION",
    "VALIDATION",
    "TRACEABILITY",
    "UNAVAILABLE_FUNCTIONS",
    "DISTINCT_VALUES",
    "LOCAL_STORAGE",
    "BASELINE_SEPARATION",
)
AUTHORING_LAYOUT_KEY = "conflict-analysis-studio:audited-draft-layout:v1"


def _raw_json(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


class _AuditedAuthoringFixture:
    password = "c1-audited-authoring-password"

    @classmethod
    def make_authoring_fixture(cls, *, high_cardinality: bool = False) -> None:
        cls.help_html = "<p>Точная справка Foundation для C1.</p>"
        cls.help_sha256 = hashlib.sha256(cls.help_html.encode("utf-8")).hexdigest()
        now = timezone.now()
        topic = HelpTopic(
            code=f"C1-HELP-{uuid4().hex}",
            version="1.0.0",
            stable_key="studio.welcome",
            title="Точная справка Foundation C1",
            application_scope=HelpApplicationScope.STUDIO,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="ru",
            sanitized_html=cls.help_html,
            content_sha256=cls.help_sha256,
            publication_status=PublicationStatus.PUBLISHED,
            published_at=now,
        )
        topic.save(force_insert=True)
        UIHelpBinding(
            code=f"C1-HELP-BINDING-{uuid4().hex}",
            version="1.0.0",
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            ui_key="studio.welcome",
            locale="ru",
            help_topic=topic,
        ).save(force_insert=True)

        cls.manifest = foundation_manifest()
        identity = cls.manifest["project"]
        identity.update(
            default_locale="ru",
            metadata={
                "studio_contract": AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID,
                "fixture": "audited-authoring",
                "точное_большое_целое": 9007199254740993,
                "точная_экспонента": 1e-7,
            },
        )
        binding = cls.manifest["help_bindings"][0]
        binding.update(
            application_scope="STUDIO",
            ui_key="studio.welcome",
            locale="ru",
            topic_stable_key="studio.welcome",
            topic_version="1.0.0",
            version="1.0.0",
            topic_sha256=cls.help_sha256,
        )
        if high_cardinality:
            for index in range(len(cls.manifest["actors"]), 520):
                cls.manifest["actors"].append(
                    {
                        "id": f"21000000-0000-4000-8000-{index:012d}",
                        "code": f"C1-ACTOR-{index:04d}",
                        "version": "1.0.0",
                        "label": f"Актор {index}",
                        "description": f"Описание актора {index}.",
                        "actor_type": "GROUP",
                        "order": index,
                        "parent_id": None,
                    }
                )
            for index in range(len(cls.manifest["analytical_elements"]), 520):
                cls.manifest["analytical_elements"].append(
                    {
                        "id": f"22000000-0000-4000-8000-{index:012d}",
                        "code": f"C1-ELEMENT-{index:04d}",
                        "version": "1.0.0",
                        "label": f"Аналитический элемент {index}",
                        "description": f"Описание элемента {index}.",
                        "element_type": "CONFLICT_ISSUE",
                        "reference_statement": f"Reference statement {index}.",
                        "order": index,
                        "parent_id": None,
                    }
                )

        cls.project = Project.objects.create(
            id=identity["id"],
            code=identity["code"],
            version=identity["version"],
            name=identity["name"],
            description=identity["description"],
            metadata=identity["metadata"],
        )
        fixture_principal = StudioPrincipal.for_role(
            actor_identifier=f"c1-fixture:{uuid4()}",
            role=StudioRole.STUDIO_EDITOR,
        )
        cls.definition = create_project_definition_draft(
            project=cls.project,
            definition_id=uuid4(),
            code=f"C1-AUTHORING-{uuid4().hex}",
            version="1.0.0",
            manifest=cls.manifest,
            principal=fixture_principal,
        )

        user_model = get_user_model()
        cls.editor = user_model.objects.create_user(
            username=f"c1-editor-{uuid4().hex}",
            password=cls.password,
        )
        cls.viewer = user_model.objects.create_user(
            username=f"c1-viewer-{uuid4().hex}",
            password=cls.password,
        )
        cls.out_of_scope_editor = user_model.objects.create_user(
            username=f"c1-out-of-scope-{uuid4().hex}",
            password=cls.password,
        )
        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
            )
        }
        editor_permissions = (
            permissions["studio_read_definition"],
            permissions["studio_create_definition_draft"],
            permissions["studio_clone_definition_draft"],
            permissions["studio_save_definition_draft"],
        )
        cls.editor.user_permissions.add(*editor_permissions)
        cls.out_of_scope_editor.user_permissions.add(*editor_permissions)
        cls.viewer.user_permissions.add(permissions["studio_read_definition"])
        scope = Group.objects.create(name=project_access_group_name(cls.project.pk))
        scope.user_set.add(cls.editor, cls.viewer)
        cls.editor = user_model.objects.get(pk=cls.editor.pk)
        cls.viewer = user_model.objects.get(pk=cls.viewer.pk)
        cls.out_of_scope_editor = user_model.objects.get(
            pk=cls.out_of_scope_editor.pk
        )

    def session_api(self, user: object | None = None) -> tuple[APIClient, str]:
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user or self.editor)
        opened = client.get(
            f"/api/foundation/definitions/{self.definition.pk}/"
        )
        self.assertEqual(opened.status_code, 200, getattr(opened, "data", None))
        return client, client.cookies["csrftoken"].value

    def bootstrap_payload(self) -> tuple[dict[str, object], UUID, UUID]:
        project_id = uuid4()
        definition_id = uuid4()
        project = {
            "id": str(project_id),
            "code": f"C1-BOOTSTRAP-{project_id.hex}",
            "version": "1.0.0",
            "name": "Первый проект C1",
            "description": "Первый DRAFT создаётся только Foundation.",
            "metadata": {
                "studio_contract": AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID,
            },
        }
        manifest = foundation_manifest()
        manifest["project"] = {
            **project,
            "default_locale": "ru",
        }
        for collection in (
            "actors",
            "analytical_elements",
            "actor_element_roles",
            "parameter_definitions",
            "help_bindings",
        ):
            manifest[collection] = []
        payload: dict[str, object] = {
            "project": project,
            "definition": {
                "id": str(definition_id),
                "code": f"C1-DRAFT-{definition_id.hex}",
                "version": "1.0.0",
                "manifest": manifest,
                "semantic_version": "1.0.0",
                "construct_version": "1.0.0",
            },
        }
        return payload, project_id, definition_id


class ProductionStudioAuditedAuthoringContractTests(
    _AuditedAuthoringFixture,
    TestCase,
):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.make_authoring_fixture()

    def test_authoring_claim_contract_is_exact_immutable_and_persistent(self):
        claim_before = database_fingerprint()
        response = Client().get(
            "/studio/claim-boundaries/audited-draft/v1/"
        )
        payload = AUTHORING_CLAIM_BOUNDARY_CONTRACT_PATH.read_bytes()
        sidecar = AUTHORING_CLAIM_BOUNDARY_SIDECAR_PATH.read_bytes()
        verified = load_authoring_claim_boundaries()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, payload)
        self.assertEqual(len(payload), AUTHORING_CLAIM_BOUNDARY_CONTRACT_BYTES)
        self.assertEqual(
            hashlib.sha256(payload).hexdigest(),
            AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256,
        )
        self.assertEqual(sidecar, AUTHORING_CLAIM_BOUNDARY_EXPECTED_SIDECAR)
        self.assertEqual(response["Content-Length"], str(len(payload)))
        self.assertEqual(
            response["ETag"], f'"{AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256}"'
        )
        self.assertEqual(
            response["Cache-Control"],
            "public, max-age=31536000, immutable, no-transform",
        )
        self.assertFalse(response.cookies)
        self.assertEqual(
            tuple(item["code"] for item in verified.statements),
            AUTHORING_CLAIM_CODES,
        )
        self.assertEqual(verified.contract, AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID)
        combined = " ".join(item["text"] for item in verified.statements)
        for required in (
            "Foundation",
            "If-Match",
            "Чат",
            "прогноз",
            "рекомендац",
        ):
            self.assertIn(required, combined)
        self.assertEqual(database_fingerprint(), claim_before)

    def test_draft_routes_require_preissued_session_and_render_no_credentials(self):
        entry_url = "/studio/drafts/"
        definition_url = f"/studio/drafts/definitions/{self.definition.pk}/"
        anonymous = Client()
        anonymous_before = database_fingerprint()
        for url in (entry_url, definition_url):
            with self.subTest(url=url):
                response = anonymous.get(url)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn("Location", response)
                self.assertFalse(response.cookies)
                html = response.content.decode("utf-8").lower()
                self.assertNotIn('type="password"', html)
                self.assertNotIn("/login", html)
                self.assertNotIn("/logout", html)
                self.assertNotIn("/signup", html)
                self.assertContains(
                    response,
                    AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID,
                    status_code=401,
                )
                for method in ("post", "put", "patch", "delete"):
                    denied = getattr(anonymous, method)(url)
                    self.assertEqual(denied.status_code, 405)

        self.assertEqual(database_fingerprint(), anonymous_before)

        authenticated = Client()
        authenticated.force_login(self.editor)
        session_id = authenticated.cookies[settings.SESSION_COOKIE_NAME].value
        authenticated_before = database_fingerprint()
        entry = authenticated.get(entry_url)
        shell = authenticated.get(definition_url)
        self.assertEqual(entry.status_code, 200)
        self.assertEqual(shell.status_code, 200)
        self.assertEqual(
            authenticated.cookies[settings.SESSION_COOKIE_NAME].value,
            session_id,
        )
        self.assertFalse(entry.cookies.get(settings.SESSION_COOKIE_NAME))
        self.assertFalse(shell.cookies.get(settings.SESSION_COOKIE_NAME))
        self.assertIn(settings.CSRF_COOKIE_NAME, authenticated.cookies)
        self.assertTrue(
            entry.cookies.get(settings.CSRF_COOKIE_NAME)
            or shell.cookies.get(settings.CSRF_COOKIE_NAME)
        )
        self.assertEqual(entry["Cache-Control"], "no-store")
        self.assertEqual(shell["Cache-Control"], "no-store")
        self.assertEqual(database_fingerprint(), authenticated_before)

    def test_shell_bootstrap_and_exact_open_use_only_foundation_gateways(self):
        client = Client()
        client.force_login(self.editor)
        entry = client.get("/studio/drafts/")
        shell = client.get(
            f"/studio/drafts/definitions/{self.definition.pk}/"
        )
        self.assertEqual(entry.status_code, 200)
        self.assertEqual(shell.status_code, 200)
        entry_html = entry.content.decode("utf-8")
        shell_html = shell.content.decode("utf-8")

        self.assertIn("/api/foundation/projects/bootstrap-first-draft/", entry_html)
        self.assertIn("/studio/drafts/definitions/", entry_html)
        for selector in (
            "audited-draft-entry",
            "bootstrap-project-id",
            "bootstrap-project-code",
            "bootstrap-project-version",
            "bootstrap-project-name",
            "bootstrap-project-description",
            "bootstrap-definition-id",
            "bootstrap-definition-code",
            "bootstrap-definition-version",
            "bootstrap-semantic-version",
            "bootstrap-construct-version",
            "bootstrap-operation-key",
            "bootstrap-draft",
            "bootstrap-manual-reconcile",
            "existing-definition-id",
            "open-existing-draft",
            "entry-state-code",
            "entry-state-message",
        ):
            self.assertIn(f'id="{selector}"', entry_html)

        definition_id = str(self.definition.pk)
        self.assertIn(
            f"/api/foundation/definitions/{definition_id}/", shell_html
        )
        self.assertIn(
            f"/api/foundation/definitions/{definition_id}/draft/", shell_html
        )
        self.assertIn(
            f"/api/foundation/definitions/{definition_id}/validation-preview/",
            shell_html,
        )
        self.assertIn("/api/foundation/help/", shell_html)
        self.assertIn("/studio/claim-boundaries/audited-draft/v1/", shell_html)
        self.assertNotIn("/api/studio", entry_html + shell_html)
        script = AUTHORING_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("studio_contract", script)
        self.assertIn(AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID, script)
        self.assertNotIn("/api/studio", script)

    def test_bootstrap_envelope_csrf_raw_ingress_and_scope_are_fail_closed(self):
        url = "/api/foundation/projects/bootstrap-first-draft/"
        payload, project_id, definition_id = self.bootstrap_payload()
        raw = _raw_json(payload)

        missing_csrf = APIClient(enforce_csrf_checks=True)
        missing_csrf.force_login(self.editor)
        response = missing_csrf.post(
            url,
            data=raw,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Project.objects.filter(pk=project_id).exists())
        self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=definition_id).exists())

        api, csrf = self.session_api()
        malformed = api.post(
            url,
            data=raw + b"{}",
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(malformed.status_code, 400, malformed.data)
        self.assertEqual(malformed.data["code"], "RAW_JSON_TRAILING_DOCUMENT")
        self.assertFalse(Project.objects.filter(pk=project_id).exists())

        operation_id = uuid4()
        created = api.post(
            url,
            data=raw,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
        )
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["project"]["id"], str(project_id))
        self.assertEqual(created.data["definition"]["id"], str(definition_id))
        self.assertEqual(
            created.data["write_receipt"]["operation_id"], str(operation_id)
        )
        self.assertEqual(created["X-Foundation-Operation-Replayed"], "false")
        self.assertTrue(
            get_user_model().objects.get(pk=self.editor.pk).groups.filter(
                name=created.data["object_scope_group"]
            ).exists()
        )

        out_of_scope = APIClient(enforce_csrf_checks=True)
        out_of_scope.force_login(self.out_of_scope_editor)
        inaccessible = out_of_scope.get(
            f"/api/foundation/definitions/{self.definition.pk}/"
        )
        absent = out_of_scope.get(f"/api/foundation/definitions/{uuid4()}/")
        self.assertEqual(inaccessible.status_code, 404)
        self.assertEqual(inaccessible.data, absent.data)

        no_capability = APIClient(enforce_csrf_checks=True)
        no_capability.force_login(self.viewer)
        readable = no_capability.get(
            f"/api/foundation/definitions/{self.definition.pk}/"
        )
        self.assertEqual(readable.status_code, 200, readable.data)
        viewer_csrf = no_capability.cookies[settings.CSRF_COOKIE_NAME].value
        denied = no_capability.put(
            f"/api/foundation/definitions/{self.definition.pk}/draft/",
            {"manifest": copy.deepcopy(self.manifest)},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_IF_MATCH=f'"{self.definition.manifest_hash}"',
            HTTP_X_CSRFTOKEN=viewer_csrf,
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["code"], "STUDIO_CAPABILITY_DENIED")

    def test_save_uses_strong_etag_receipt_and_typed_stale_conflict(self):
        api, csrf = self.session_api()
        url = f"/api/foundation/definitions/{self.definition.pk}/draft/"
        before_hash = self.definition.manifest_hash
        candidate = copy.deepcopy(self.manifest)
        candidate["project"]["description"] = "Сохранённый Foundation DRAFT."
        raw = _raw_json({"manifest": candidate})

        missing_token = api.put(
            url,
            data=raw,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(missing_token.status_code, 400, missing_token.data)
        self.assertEqual(missing_token.data["code"], "IF_MATCH_REQUIRED")

        operation_id = uuid4()
        audit_before = AuditEvent.objects.count()
        saved = api.put(
            url,
            data=raw,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{before_hash}"',
        )
        self.assertEqual(saved.status_code, 200, saved.data)
        self.assertEqual(saved["X-Foundation-Operation-Replayed"], "false")
        self.assertEqual(saved.data["write_receipt"]["operation_id"], str(operation_id))
        self.assertEqual(saved["ETag"], f'"{saved.data["manifest_hash"]}"')
        self.assertEqual(AuditEvent.objects.count(), audit_before + 1)

        replay = api.put(
            url,
            data=raw,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{before_hash}"',
        )
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data["code"], "WRITE_OPERATION_RECONCILED")
        self.assertEqual(replay["X-Foundation-Operation-Replayed"], "true")
        self.assertEqual(replay.data["write_receipt"], saved.data["write_receipt"])
        self.assertEqual(AuditEvent.objects.count(), audit_before + 1)

        stale = api.put(
            url,
            data=raw,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_IF_MATCH=f'"{before_hash}"',
        )
        self.assertEqual(stale.status_code, 409, stale.data)
        self.assertEqual(stale.data["code"], "DRAFT_STALE")
        self.assertEqual(AuditEvent.objects.count(), audit_before + 1)

    def test_validation_preview_is_canonical_non_mutating_and_exact_help_is_foundation_owned(self):
        api, csrf = self.session_api()
        preview_url = (
            f"/api/foundation/definitions/{self.definition.pk}/validation-preview/"
        )
        candidate = copy.deepcopy(self.manifest)
        candidate["actors"][0]["label"] = "Предложенное имя актора"
        before = database_fingerprint()
        preview = api.post(
            preview_url,
            data=_raw_json({"manifest": candidate}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertEqual(preview["Cache-Control"], "no-store")
        self.assertEqual(preview["X-Content-Type-Options"], "nosniff")
        self.assertTrue(preview.content.endswith(b"\n"))
        self.assertEqual(
            preview["ETag"],
            f'"{hashlib.sha256(preview.content).hexdigest()}"',
        )
        report = json.loads(preview.content)
        self.assertEqual(report["definition_id"], str(self.definition.pk))
        self.assertEqual(report["project_id"], str(self.project.pk))
        self.assertTrue(report["valid"])
        self.assertEqual(database_fingerprint(), before)

        help_response = api.get(
            "/api/foundation/help/studio.welcome/"
            "?application=STUDIO&locale=ru&version=1.0.0"
        )
        self.assertEqual(help_response.status_code, 200, help_response.data)
        self.assertEqual(
            help_response.data,
            {
                "stable_key": "studio.welcome",
                "version": "1.0.0",
                "locale": "ru",
                "title": "Точная справка Foundation C1",
                "sanitized_html": self.help_html,
                "content_sha256": self.help_sha256,
            },
        )
        self.assertEqual(database_fingerprint(), before)

    def test_authoring_static_contract_is_bounded_and_disables_unavailable_controls(self):
        client = Client()
        client.force_login(self.editor)
        response = client.get(
            f"/studio/drafts/definitions/{self.definition.pk}/"
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        for selector in (
            "audited-draft-app",
            "audited-draft-boundary-banner",
            "save-draft",
            "preview-validation",
            "manual-reconcile",
            "authoring-operation-key",
            "authoring-state-code",
            "authoring-state-message",
            "project-name",
            "project-description",
            "authoring-actors",
            "authoring-elements",
            "add-actor",
            "add-element",
            "authoring-window-prev",
            "authoring-window-next",
            "help-binding-select",
            "load-help",
            "help-frame",
        ):
            self.assertIn(f'id="{selector}"', html)
        for selector in (
            "document-control",
            "chat-control",
            "scientific-control",
            "prediction-control",
            "recommendation-control",
        ):
            self.assertRegex(
                html,
                rf'<[^>]+id="{re.escape(selector)}"[^>]+disabled',
            )
        self.assertIn(AUTHORING_CLAIM_BOUNDARY_CONTRACT_ID, html)

        script = AUTHORING_SCRIPT.read_text(encoding="utf-8")
        style = AUTHORING_STYLE.read_text(encoding="utf-8")
        for event_name in (
            "studio:authoring-ready",
            "studio:save-complete",
            "studio:preview-complete",
            "studio:typed-conflict",
        ):
            self.assertIn(event_name, script)
        self.assertIn("100", script)
        self.assertIn("data-authoring-row", script)
        self.assertIn("data-field", script)
        for action in ("rename", "delete", "move-up", "move-down"):
            self.assertIn(action, script)
        self.assertNotIn("actor_element_matrix", script.lower())
        self.assertNotIn("/api/studio", script)
        self.assertIn("audited-draft", style)

    def test_browser_storage_contract_allows_only_bounded_layout_not_draft_state(self):
        script = AUTHORING_SCRIPT.read_text(encoding="utf-8")
        self.assertIn(AUTHORING_LAYOUT_KEY, script)
        self.assertIn("AUDITED_DRAFT_LAYOUT_V1", script)
        self.assertIn("256", script)
        storage_keys = set(
            re.findall(r"conflict-analysis-studio:[a-z0-9:-]+", script)
        )
        self.assertEqual(storage_keys, {AUTHORING_LAYOUT_KEY})
        self.assertNotRegex(script, r"sessionStorage\s*\.\s*setItem")
        self.assertNotRegex(script, r"indexedDB\s*\.\s*open")
        self.assertNotRegex(script, r"caches\s*\.\s*open")
        self.assertNotRegex(script, r"serviceWorker\s*\.\s*register")
        set_item_calls = re.findall(
            r"localStorage\s*\.\s*setItem\s*\(([^,\n]+)", script
        )
        self.assertTrue(set_item_calls)
        self.assertEqual({item.strip() for item in set_item_calls}, {"STORAGE_KEY"})
        for forbidden in (
            "manifest-cache",
            "draft-cache",
            "receipt-cache",
            "operation-key-cache",
        ):
            self.assertNotIn(forbidden, script.lower())


class ProductionStudioAuditedAuthoringBrowserTests(
    _AuditedAuthoringFixture,
    StaticLiveServerTestCase,
):
    host = "localhost"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.make_authoring_fixture(high_cardinality=True)

    def test_authenticated_edit_save_reload_is_bounded_foundation_only_and_receipted(self):
        self.assertGreater(len(self.manifest["actors"]), 500)
        self.assertGreater(len(self.manifest["analytical_elements"]), 500)
        self.client.force_login(self.editor)
        session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        before = database_fingerprint()
        audit_before = AuditEvent.objects.count()
        environment = os.environ.copy()
        remote_manifest = copy.deepcopy(self.manifest)
        remote_manifest["project"]["description"] = (
            "Параллельное изменение Foundation"
        )
        remote_save_body = _raw_json({"manifest": remote_manifest})
        remote_save_text = remote_save_body.decode("utf-8")
        exponent_match = re.search(
            r'"точная_экспонента":([^,}]+)',
            remote_save_text,
        )
        self.assertIsNotNone(exponent_match)
        self.assertIn('"точное_большое_целое":9007199254740993', remote_save_text)
        environment.update(
            STUDIO_BASE_URL=self.live_server_url,
            STUDIO_DEFINITION_ID=str(self.definition.pk),
            STUDIO_SESSION_COOKIE_NAME=settings.SESSION_COOKIE_NAME,
            STUDIO_SESSION_COOKIE_VALUE=session_cookie,
            STUDIO_EXPECTED_CLAIM_SHA256=AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256,
            STUDIO_EXPECTED_MANIFEST_SHA256=self.definition.manifest_hash,
            STUDIO_EXPECTED_HELP_SHA256=self.help_sha256,
            STUDIO_REMOTE_SAVE_BODY_ZLIB_B64=base64.b64encode(
                zlib.compress(remote_save_body, level=9)
            ).decode("ascii"),
            STUDIO_LOSSLESS_BIGINT_KEY="точное_большое_целое",
            STUDIO_LOSSLESS_EXPONENT_KEY="точная_экспонента",
            STUDIO_LOSSLESS_EXPONENT_TOKEN=exponent_match.group(1),
            STUDIO_CDP_TIMEOUT_MS=environment.get("STUDIO_CDP_TIMEOUT_MS", "60000"),
        )
        completed = subprocess.run(
            ["node", str(BROWSER_SCRIPT)],
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
        output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertTrue(output_lines, completed.stderr)
        result = json.loads(output_lines[-1])
        self.assertEqual(result["browser_result"], "PASS")
        self.assertEqual(result["definition_id"], str(self.definition.pk))
        self.assertEqual(
            result["claim_contract_sha256"],
            AUTHORING_CLAIM_BOUNDARY_CONTRACT_SHA256,
        )
        self.assertEqual(result["storage_key"], AUTHORING_LAYOUT_KEY)
        self.assertGreater(result["observed_actor_count"], 500)
        self.assertGreater(result["observed_element_count"], 500)
        self.assertLessEqual(result["max_active_rows"], 100)
        self.assertEqual(result["typed_conflict"], "DRAFT_STALE")
        self.assertRegex(result["receipt_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(AuditEvent.objects.count(), audit_before + 2)

        after = database_fingerprint()
        allowed_changes = {
            "domain_auditevent",
            "domain_projectdefinitionversion",
        }
        for table, digest in before.items():
            if table not in allowed_changes:
                self.assertEqual(after[table], digest, table)
        self.definition.refresh_from_db()
        self.assertEqual(self.definition.manifest_hash, result["final_manifest_sha256"])
        self.assertEqual(
            self.definition.manifest["project"]["name"],
            "Проект C1 после сохранения",
        )
