from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import TestCase
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse

from domain.enums import (
    AssessmentEvidenceRole,
    EvidenceTemporalStatus,
    FactDirectness,
    FactOrigin,
    FactType,
    Visibility,
)
from domain.models import Fact, ParameterValueEvidence
from domain.models import AssessmentEvidence, Source, TextFragment
from domain.api.studio_definitions import project_access_group_name
from domain.enums import SourceIndependenceStatus
from domain.services.document_lineage import (
    AlignmentComponentSpec,
    ContentVariantSpec,
    DocumentSpec,
    FragmentSpec,
    SentenceSpec,
    create_exact_project_primary_fragment,
    ingest_initial_synchronized_document,
)
from domain.services import zhanaozen_typed_manifest as typed
from domain.services.player_experiments import G8_REQUIRED_PERMISSIONS
from domain.services.seed import seed_zhanaozen_demo
from domain.tests.test_player_experiments import PlayerExperimentsFixture
from domain.tests.test_v4_foundation_contracts import clean_save
from production_player.claim_boundaries import (
    EVIDENCE_CLAIM_CONTRACT_ID,
    EVIDENCE_CLAIM_CONTRACT_SHA256,
    load_evidence_claim_boundaries,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "static" / "production_player" / "evidence.js"
STYLE = ROOT / "static" / "production_player" / "evidence.css"
TEMPLATE = ROOT / "templates" / "production_player" / "workspace.html"
VIEWS = ROOT / "views.py"
SERVICE = ROOT.parent / "domain" / "services" / "evidence_access.py"
BROWSER = ROOT / "browser_tests" / "player_g9_evidence.mjs"


class ProductionPlayerG9EvidenceTests(PlayerExperimentsFixture, TestCase):
    """The exact six-node portable G9 Product registry."""

    def setUp(self) -> None:
        self.client.force_login(self.user)

    def _workspace_html(self) -> str:
        response = self.client.get(reverse(
            "production_player:workspace", kwargs={"workspace_id": self.workspace.pk},
        ))
        self.assertEqual(response.status_code, 200)
        return response.content.decode("utf-8")

    def _focus_fixture(self):
        _, experiment, _ = self.aggregate(kind="HUMAN")
        value = self.create_value(experiment, value=7)
        return experiment, value, value.actor_element_assessment

    def test_g9_product_uses_only_foundation_reads_and_has_no_orm_or_evidence_store(self):
        source = SCRIPT.read_text(encoding="utf-8")
        views = VIEWS.read_text(encoding="utf-8")
        self.assertIn('const API = "/api/foundation/"', source)
        self.assertNotIn("domain.models", source + views)
        self.assertNotIn(".objects.", views)
        self.assertNotIn("indexedDB", source)
        self.assertNotIn("caches.", source)
        self.assertNotIn("serviceWorker", source)
        self.assertNotIn("WebSocket", source)
        self.assertIn("Fact visibility in the\ndatabase", SERVICE.read_text(encoding="utf-8"))

    def test_g9_focus_and_command_surface_are_exact_no_in_row_actions_or_implicit_mutation(self):
        _, value, assessment = self._focus_fixture()
        self.assertNotEqual(value.pk, assessment.pk)
        source = SCRIPT.read_text(encoding="utf-8")
        html = self._workspace_html()
        for token in (
            "data-ca-project-id", "data-ca-workspace-id", "data-ca-focus-kind", "data-ca-focus-id",
            "parameter-value", "actor-element-assessment", "g9-related", "g9-open-fact",
            "g9-open-fragment", "g9-open-document",
        ):
            self.assertIn(token, source + html)
        self.assertIn("Выбор значения или оценки сам по себе не загружает", load_evidence_claim_boundaries().statements[1]["text"])
        self.assertNotIn("fetch(API + path", source[source.index("function selectEntry"):source.index("async function related")])
        self.assertNotIn("button", source[source.index("function option("):source.index("function metadata(")])
        self.assertIn("document.addEventListener(\"click\"", source)

    def test_g9_fact_and_evidence_rendering_preserves_roles_category_memory_and_no_truth_claims(self):
        _, value, _ = self._focus_fixture()
        fact = clean_save(Fact(
            workspace=self.workspace, code=f"G9-PRODUCT-FACT-{uuid4().hex[:8]}", version="1.0.0",
            fact_type=FactType.EXPERT_INTERPRETATION, statement="Память эксперта без документа.",
            origin=FactOrigin.HUMAN_EXPERT_ASSERTION, directness=FactDirectness.INDIRECT,
            visibility=Visibility.WORKSPACE_SHARED, temporal_status=EvidenceTemporalStatus.UNKNOWN,
            coder_identifier=f"django-user:{self.user.pk}",
        ))
        for role in (AssessmentEvidenceRole.PRIMARY_SUPPORT, AssessmentEvidenceRole.COUNTEREVIDENCE):
            clean_save(ParameterValueEvidence(
                workspace=self.workspace, parameter_value=value, fact=fact,
                code=f"G9-PRODUCT-LINK-{role}-{uuid4().hex[:8]}", version="1.0.0",
                role=role, temporal_status=EvidenceTemporalStatus.UNKNOWN,
            ))
        response = self.client.get(reverse("foundation-parameter-value-facts", kwargs={
            "project_id": self.project.pk, "workspace_id": self.workspace.pk,
            "parameter_value_id": value.pk,
        }))
        payload = response.json()["facts"][0]
        self.assertEqual(payload["fact_type"], FactType.EXPERT_INTERPRETATION)
        self.assertEqual(payload["category"]["classification_status"], "UNCLASSIFIED")
        self.assertEqual([item["role"] for item in payload["entry_evidence"]], [
            AssessmentEvidenceRole.COUNTEREVIDENCE, AssessmentEvidenceRole.PRIMARY_SUPPORT,
        ])
        detail = self.client.get(reverse("foundation-fact-evidence-drilldown", kwargs={
            "project_id": self.project.pk, "workspace_id": self.workspace.pk, "fact_id": fact.pk,
        })).json()
        self.assertEqual((detail["code"], detail["evidence"]), ("NO_DOCUMENT_EVIDENCE", []))
        contract = load_evidence_claim_boundaries()
        self.assertEqual((contract.contract, contract.sha256), (EVIDENCE_CLAIM_CONTRACT_ID, EVIDENCE_CLAIM_CONTRACT_SHA256))
        self.assertIn("не подтверждает истинность", next(item["text"] for item in contract.statements if item["code"] == "NO_TRUTH_CLAIM"))

    def test_g9_exact_fragment_original_disabled_and_multi_sentence_alignment_rendering_are_honest(self):
        source = SCRIPT.read_text(encoding="utf-8")
        html = self._workspace_html()
        self.assertIn("source?.exact_text", source)
        self.assertIn("source?.excerpt", source)
        self.assertIn("crypto.subtle.digest", source)
        self.assertIn("new TextEncoder().encode(value)", source)
        self.assertIn("Array.from(text).length !== end - start", source)
        self.assertIn('source.anchor_status !== "EXACT"', source)
        self.assertIn('"SHA-256 точного текста"', source)
        self.assertNotIn(".normalize(", source)
        self.assertNotIn(".trim(", source)
        self.assertNotIn("substring(", source)
        self.assertNotIn("slice(source", source)
        self.assertIn("Точное соответствие оригиналу не подтверждено", source + html)
        self.assertIn("alignment_set_id", source)
        self.assertIn("alignment_sha256", source)
        self.assertIn("white-space: pre-wrap", STYLE.read_text(encoding="utf-8"))

    def test_g9_async_errors_history_and_permission_changes_clear_stale_confidential_state(self):
        source = SCRIPT.read_text(encoding="utf-8")
        for token in (
            "AbortController", "requestToken", "sameIdentity", "clearConfidential",
            "popstate", "restoreHistory", "MutationObserver", "data-authenticated",
            "data-ca-workspace-id", "document.contains(state.focusNode)",
        ):
            self.assertIn(token, source)
        self.assertLess(source.index("clearConfidential(\"Связанные факты недоступны."), source.index("async function openFact"))
        self.assertIn("await related(false)", source)
        self.assertIn("await openFact(false)", source)
        self.assertNotIn("latest", source.lower())

    def test_g9_storage_active_content_external_urls_and_accessibility_are_bounded(self):
        source = SCRIPT.read_text(encoding="utf-8")
        html = self._workspace_html()
        for forbidden in (
            "localStorage", "sessionStorage", "indexedDB", "serviceWorker", "innerHTML",
            "insertAdjacentHTML", "eval(", "new Function", "javascript:", "data:", "file:",
        ):
            self.assertNotIn(forbidden, source)
        for required in (
            "textContent", 'node.dir = "auto"', '"http:", "https:"', '"noopener,noreferrer"',
            "window.confirm", "target.opener = null", 'role="listbox"', 'role="status"',
            'aria-live="polite"', 'aria-label="Команды доказательств"',
        ):
            self.assertIn(required, source + html)
        self.assertEqual(source.count("history.pushState"), 1)


@unittest.skipUnless(connection.vendor == "postgresql", "G9 Chromium nodes require PostgreSQL")
class ProductionPlayerG9ChromiumTests(PlayerExperimentsFixture, StaticLiveServerTestCase):
    host = "localhost"

    def setUp(self) -> None:
        self.project = seed_zhanaozen_demo()
        self.workspace = self.project.workspaces.get(pk=typed.WORKSPACE_ID)
        self.user = get_user_model().objects.create_user(username=f"g9-browser-{uuid4()}")
        permissions = Permission.objects.filter(
            content_type__app_label="domain",
            codename__in=[item.removeprefix("domain.") for item in G8_REQUIRED_PERMISSIONS],
        )
        self.user.user_permissions.add(*permissions)
        group, _ = Group.objects.get_or_create(name=project_access_group_name(self.project.pk))
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def _fact(self, suffix: str, *, statement: str, visibility=Visibility.WORKSPACE_SHARED, coder=None, experiment=None):
        return clean_save(Fact(
            workspace=self.workspace, experiment=experiment,
            code=f"G9-BROWSER-FACT-{suffix}-{uuid4().hex[:8]}", version="1.0.0",
            fact_type=FactType.OBSERVED_EVENT, statement=statement,
            origin=FactOrigin.DOCUMENT_DERIVED, directness=FactDirectness.DIRECT,
            visibility=visibility, temporal_status=EvidenceTemporalStatus.UNKNOWN,
            coder_identifier=coder or f"django-user:{self.user.pk}",
        ))

    def _fragment(self) -> TextFragment:
        source = clean_save(Source(
            workspace=self.workspace, code=f"G9-BROWSER-SOURCE-{uuid4().hex[:8]}", version="1.0.0",
            name="Источник <img src=x onerror=alert(1)>", publisher="Издатель \u202eтест",
            independence_group="G9-BROWSER", independence_status=SourceIndependenceStatus.UNKNOWN,
        ))
        text = "Строка 😀\u200d🔬 e\u0301.\r\nПовтор. Повтор. \u202eabc"
        document_code = f"G9-BROWSER-DOC-{uuid4().hex[:8]}"
        variant = ContentVariantSpec(
            code=f"G9-BROWSER-VARIANT-{uuid4().hex[:8]}", language_tag="ru",
            normalized_text=text, segmentation_version="g9-browser-v1",
        )
        sentence = SentenceSpec(
            code=f"G9-BROWSER-SENTENCE-{uuid4().hex[:8]}", text=text,
            start_offset=0, end_offset=len(text), sentence_number=1,
        )
        result = ingest_initial_synchronized_document(
            workspace=self.workspace, source=source,
            document=DocumentSpec(
                code=document_code, title="Документ",
                canonical_url="https://example.test/g9", capture_url="https://example.test/g9",
            ),
            original=variant, project_primary=variant,
            original_sentences=(sentence,), project_primary_sentences=(sentence,),
            alignment_components=(AlignmentComponentSpec((1,), (1,)),),
        )
        return create_exact_project_primary_fragment(
            document_version=result.document_version,
            content_variant=result.primary_variant,
            fragment=FragmentSpec(
                code=f"G9-BROWSER-FRAGMENT-{uuid4().hex[:8]}",
                start_offset=0, end_offset=len(text),
                selector={"type": "TextPositionSelector", "start": 0, "end": len(text)},
            ),
        )

    def run_browser(self, scenario: str) -> dict[str, object]:
        _, visible_experiment, _ = self.aggregate(kind="AI")
        visible_value = self.create_value(visible_experiment, value=4)
        _, hidden_experiment, _ = self.aggregate(kind="HUMAN")
        hidden_value = self.create_value(hidden_experiment, value=4)
        visible_fact = self._fact(
            "VISIBLE", statement="Точный <script>не код</script> 😀\u200d🔬 e\u0301 \u202eabc",
        )
        hidden_fact = self._fact(
            "HIDDEN", statement="Скрытое утверждение", visibility=Visibility.OWNER_ONLY,
            coder="django-user:another", experiment=hidden_experiment,
        )
        for value, fact, role in (
            (visible_value, visible_fact, AssessmentEvidenceRole.PRIMARY_SUPPORT),
            (hidden_value, hidden_fact, AssessmentEvidenceRole.COUNTEREVIDENCE),
        ):
            clean_save(ParameterValueEvidence(
                workspace=self.workspace, parameter_value=value, fact=fact,
                code=f"G9-BROWSER-VALUE-LINK-{uuid4().hex[:8]}", version="1.0.0",
                role=role, temporal_status=EvidenceTemporalStatus.UNKNOWN,
            ))
        clean_save(AssessmentEvidence(
            workspace=self.workspace, assessment=visible_value.actor_element_assessment,
            fact=visible_fact, code=f"G9-BROWSER-ASSESS-LINK-{uuid4().hex[:8]}", version="1.0.0",
            role=AssessmentEvidenceRole.CONTEXT, temporal_status=EvidenceTemporalStatus.UNKNOWN,
        ))
        fragment = self._fragment()
        from domain.models import FactEvidence
        from domain.enums import FactEvidenceRelation
        clean_save(FactEvidence(
            workspace=self.workspace, fact=visible_fact, fragment=fragment,
            code=f"G9-BROWSER-DOC-LINK-{uuid4().hex[:8]}", version="1.0.0",
            relation=FactEvidenceRelation.REFUTES, temporal_status=EvidenceTemporalStatus.UNKNOWN,
        ))
        env = os.environ.copy()
        env.update(
            PLAYER_BASE_URL=self.live_server_url,
            PLAYER_WORKSPACE_ID=str(self.workspace.pk),
            PLAYER_SESSION_COOKIE_NAME=settings.SESSION_COOKIE_NAME,
            PLAYER_SESSION_COOKIE_VALUE=self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            PLAYER_G9_SCENARIO=scenario,
            PLAYER_VISIBLE_EXPERIMENT_ID=str(visible_experiment.pk),
            PLAYER_VISIBLE_VALUE_ID=str(visible_value.pk),
            PLAYER_VISIBLE_ASSESSMENT_ID=str(visible_value.actor_element_assessment_id),
            PLAYER_VISIBLE_FACT_ID=str(visible_fact.pk),
            PLAYER_HIDDEN_EXPERIMENT_ID=str(hidden_experiment.pk),
            PLAYER_HIDDEN_VALUE_ID=str(hidden_value.pk),
            PLAYER_HIDDEN_FACT_ID=str(hidden_fact.pk),
            PLAYER_FRAGMENT_ID=str(fragment.pk),
            PLAYER_EXPECTED_G9_CLAIM_SHA256=EVIDENCE_CLAIM_CONTRACT_SHA256,
            PLAYER_CDP_TIMEOUT_MS=env.get("PLAYER_CDP_TIMEOUT_MS", "90000"),
        )
        result = subprocess.run(
            [env.get("NODE_BIN", "node"), str(BROWSER)], cwd=ROOT.parent, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", timeout=240,
        )
        self.assertEqual(result.returncode, 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}")
        payload = json.loads([line for line in result.stdout.splitlines() if line][-1])
        self.assertEqual(payload["browser_result"], "PASS")
        return payload

    def test_chromium_g9_parameter_and_assessment_to_fact_evidence_exact_navigation(self):
        payload = self.run_browser("navigation")
        self.assertEqual(payload["fact_id"], payload["expected_fact_id"])
        self.assertTrue(payload["parameter_and_assessment"])
        self.assertTrue(payload["exact_fragment"])

    def test_chromium_g9_private_hidden_revoked_and_network_race_non_fingerprinting(self):
        payload = self.run_browser("privacy")
        self.assertTrue(payload["hidden_neutral"])
        self.assertTrue(payload["late_response_cleared"])
        self.assertTrue(payload["revoked_cleared"])

    def test_chromium_g9_keyboard_history_storage_xss_bidi_and_external_url_policy(self):
        payload = self.run_browser("security")
        self.assertTrue(payload["keyboard"])
        self.assertTrue(payload["history_reauthorized"])
        self.assertTrue(payload["xss_inert"])
        self.assertTrue(payload["unicode_exact"])
        self.assertEqual(payload["unicode_range_cases"], 24)
        self.assertTrue(payload["fragment_mismatch_closed"])
        self.assertLessEqual(set(payload["storage"]), {"conflict-analysis-player:layout:v1"})
