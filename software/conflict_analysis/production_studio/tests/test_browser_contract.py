from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.utils import timezone

from domain.api.studio_definitions import project_access_group_name
from domain.enums import HelpApplicationScope, PublicationStatus
from domain.models import HelpTopic, Project, UIHelpBinding
from domain.policies import StudioPrincipal, StudioRole
from domain.services.project_definitions import create_project_definition_draft
from production_studio.claim_boundaries import CLAIM_BOUNDARY_CONTRACT_SHA256
from production_studio.tests import database_fingerprint, foundation_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BROWSER_SCRIPT = (
    PROJECT_ROOT
    / "production_studio"
    / "browser_tests"
    / "read_only_smoke.mjs"
)


class ProductionStudioReadOnlyBrowserContractTests(StaticLiveServerTestCase):
    host = "localhost"

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.manifest = foundation_manifest()
        identity = cls.manifest["project"]
        identity["metadata"].update(
            {
                "canonical_float_scientific": 1e-7,
                "canonical_float_integral": 1.0,
                "canonical_integer_beyond_js_safe_range": 900719925474099312345678901234567890,
                "\u2028line_separator_key": "line\u2028separator\u2029value",
                "\ue000": "unicode-private-use-key",
                "\U0001f600": "unicode-supplementary-plane-key",
            }
        )
        cls.project = Project.objects.create(
            id=identity["id"],
            code=identity["code"],
            version=identity["version"],
            name=identity["name"],
            primary_language_tag="en",
            primary_language_assignment="EXPLICIT",
        )

        help_html = "<p>Точная русская справка C0.</p>"
        help_sha256 = hashlib.sha256(help_html.encode("utf-8")).hexdigest()
        topic = HelpTopic(
            code="C0-BROWSER-HELP",
            version="1.0.0",
            stable_key="studio.welcome",
            title="Точная справка C0",
            application_scope=HelpApplicationScope.STUDIO,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="ru",
            sanitized_html=help_html,
            content_sha256=help_sha256,
            publication_status=PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        topic.save(force_insert=True)
        UIHelpBinding(
            code="C0-BROWSER-HELP-BINDING",
            version="1.0.0",
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            ui_key="studio.welcome",
            locale="ru",
            help_topic=topic,
        ).save(force_insert=True)
        binding = cls.manifest["help_bindings"][0]
        binding.update(
            application_scope="STUDIO",
            ui_key="studio.welcome",
            locale="ru",
            topic_stable_key="studio.welcome",
            topic_version="1.0.0",
            version="1.0.0",
            topic_sha256=help_sha256,
        )
        for index in range(2_500):
            cls.manifest["help_bindings"].append(
                {
                    "id": str(uuid5(NAMESPACE_URL, f"studio-c0-browser-help-{index}")),
                    "code": f"C0-HELP-DECOY-{index:04d}",
                    "version": "1.0.0",
                    "application_scope": "STUDIO",
                    "ui_key": f"studio.decoy.{index:04d}",
                    "locale": "ru",
                    "topic_stable_key": "studio.welcome",
                    "topic_version": "1.0.0",
                    "topic_sha256": help_sha256,
                }
            )

        actors = cls.manifest["actors"]
        for index in range(len(actors), 520):
            actors.append(
                {
                    "id": str(uuid5(NAMESPACE_URL, f"studio-c0-browser-actor-{index}")),
                    "code": f"C0-ACTOR-{index:04d}",
                    "version": "1.0.0",
                    "label": f"Актор {index}",
                    "description": f"Авторская запись актора {index}.",
                    "actor_type": "GROUP",
                    "order": index,
                    "parent_id": None,
                }
            )
        elements = cls.manifest["analytical_elements"]
        for index in range(len(elements), 520):
            elements.append(
                {
                    "id": str(uuid5(NAMESPACE_URL, f"studio-c0-browser-element-{index}")),
                    "code": f"C0-ELEMENT-{index:04d}",
                    "version": "1.0.0",
                    "label": f"Аналитический элемент {index}",
                    "description": f"Авторская запись элемента {index}.",
                    "element_type": "CONFLICT_ISSUE",
                    "reference_statement": f"Reference statement {index}.",
                    "order": index,
                    "parent_id": None,
                }
            )

        principal = StudioPrincipal.for_role(
            actor_identifier="c0-browser-fixture",
            role=StudioRole.STUDIO_EDITOR,
        )
        cls.definition = create_project_definition_draft(
            project=cls.project,
            code="C0-BROWSER-DRAFT",
            version="1.0.0",
            manifest=cls.manifest,
            principal=principal,
        )
        user_model = get_user_model()
        cls.reader = user_model.objects.create_user(
            username="c0-browser-reader",
            password="session-issued-outside-measurement",
        )
        cls.reader.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
                codename="studio_read_definition",
            )
        )
        group = Group.objects.create(name=project_access_group_name(cls.project.pk))
        cls.reader.groups.add(group)

    def test_preissued_session_browser_flow_is_get_only_bounded_and_zero_write(self):
        canonical_manifest = json.dumps(
            self.manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertIn('"canonical_float_scientific":1e-07', canonical_manifest)
        self.assertIn('"canonical_float_integral":1.0', canonical_manifest)
        self.assertIn(
            '"canonical_integer_beyond_js_safe_range":900719925474099312345678901234567890',
            canonical_manifest,
        )
        self.assertLess(
            canonical_manifest.index('"\ue000"'),
            canonical_manifest.index('"\U0001f600"'),
        )
        self.assertEqual(len(self.manifest["help_bindings"]), 2_501)
        self.client.force_login(self.reader)
        session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        before = database_fingerprint()
        expected_project_metadata = json.dumps(
            self.manifest["project"]["metadata"],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        environment = os.environ.copy()
        environment.update(
            STUDIO_BASE_URL=self.live_server_url,
            STUDIO_DEFINITION_ID=str(self.definition.pk),
            STUDIO_SESSION_COOKIE_NAME=settings.SESSION_COOKIE_NAME,
            STUDIO_SESSION_COOKIE_VALUE=session_cookie,
            STUDIO_EXPECTED_CLAIM_SHA256=CLAIM_BOUNDARY_CONTRACT_SHA256,
            STUDIO_EXPECTED_MANIFEST_SHA256=self.definition.manifest_hash,
            STUDIO_EXPECTED_PROJECT_METADATA=expected_project_metadata,
            STUDIO_CDP_TIMEOUT_MS=environment.get("STUDIO_CDP_TIMEOUT_MS", "45000"),
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
            timeout=240,
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
        self.assertEqual(result["methods"], ["GET"])
        self.assertEqual(result["claim_contract_sha256"], CLAIM_BOUNDARY_CONTRACT_SHA256)
        self.assertEqual(result["storage_key"], "conflict-analysis-studio:read-only-layout:v1")
        self.assertGreater(result["observed_actor_count"], 500)
        self.assertGreater(result["observed_element_count"], 500)
        self.assertEqual(result["observed_help_binding_options"], 1)
        self.assertEqual(database_fingerprint(), before)
