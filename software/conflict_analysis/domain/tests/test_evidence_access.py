from __future__ import annotations

import base64
import hashlib
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from domain.enums import (
    AnchorStatus,
    AssessmentEvidenceRole,
    DocumentLineageKind,
    DocumentVersionStatus,
    EvidenceTemporalStatus,
    FactCategoryAssignmentStatus,
    FactDirectness,
    FactEvidenceRelation,
    FactOrigin,
    FactType,
    SourceIndependenceStatus,
    Visibility,
)
from domain.models import (
    AssessmentEvidence,
    AuditEvent,
    Document,
    DocumentContent,
    DocumentVersion,
    Fact,
    FactCategory,
    FactCategoryAssignment,
    FactEvidence,
    ParameterValueEvidence,
    Source,
    TextFragment,
)
from domain.services.document_lineage import (
    AlignmentComponentSpec,
    ContentVariantSpec,
    DocumentSpec,
    FragmentSpec,
    SentenceSpec,
    TranslationProvenanceSpec,
    create_exact_project_primary_fragment,
    ingest_initial_synchronized_document,
)
from domain.services.evidence_access import assessment_facts, parameter_value_facts
from domain.tests.test_player_experiments import PlayerExperimentsFixture
from domain.tests.test_v4_foundation_contracts import clean_save


class EvidenceAccessTests(PlayerExperimentsFixture, TestCase):
    """The exact eight-node portable G9 Foundation registry."""

    def setUp(self) -> None:
        _, self.experiment, _ = self.aggregate(kind="HUMAN")
        self.value = self.create_value(self.experiment, value=0)
        self.assessment = self.value.actor_element_assessment
        self.client.force_login(self.user)

    def _fact(
        self,
        suffix: str,
        *,
        visibility: str = Visibility.WORKSPACE_SHARED,
        coder: str | None = None,
        origin: str = FactOrigin.HUMAN_EXPERT_ASSERTION,
        experiment=None,
    ) -> Fact:
        return clean_save(Fact(
            workspace=self.workspace,
            experiment=experiment,
            code=f"G9-FACT-{suffix}-{uuid4().hex[:8]}",
            version="1.0.0",
            fact_type=FactType.OBSERVED_EVENT,
            statement=f"Сохранённое утверждение {suffix}.",
            origin=origin,
            directness=FactDirectness.DIRECT,
            visibility=visibility,
            temporal_status=EvidenceTemporalStatus.UNKNOWN,
            coder_identifier=coder or f"django-user:{self.user.pk}",
        ))

    def _value_link(self, fact: Fact, role: str = AssessmentEvidenceRole.PRIMARY_SUPPORT):
        return clean_save(ParameterValueEvidence(
            workspace=self.workspace,
            parameter_value=self.value,
            fact=fact,
            code=f"G9-PV-LINK-{uuid4().hex[:10]}",
            version="1.0.0",
            role=role,
            temporal_status=EvidenceTemporalStatus.UNKNOWN,
        ))

    def _assessment_link(self, fact: Fact, role: str = AssessmentEvidenceRole.PRIMARY_SUPPORT):
        return clean_save(AssessmentEvidence(
            workspace=self.workspace,
            assessment=self.assessment,
            fact=fact,
            code=f"G9-AEA-LINK-{uuid4().hex[:10]}",
            version="1.0.0",
            role=role,
            temporal_status=EvidenceTemporalStatus.UNKNOWN,
        ))

    def _value_url(self, *, project=None, workspace=None, entry=None):
        return reverse("foundation-parameter-value-facts", kwargs={
            "project_id": project or self.project.pk,
            "workspace_id": workspace or self.workspace.pk,
            "parameter_value_id": entry or self.value.pk,
        })

    def _assessment_url(self, *, project=None, workspace=None, entry=None):
        return reverse("foundation-assessment-facts", kwargs={
            "project_id": project or self.project.pk,
            "workspace_id": workspace or self.workspace.pk,
            "assessment_id": entry or self.assessment.pk,
        })

    def _drilldown_url(self, fact: Fact):
        return reverse("foundation-fact-evidence-drilldown", kwargs={
            "project_id": self.project.pk,
            "workspace_id": self.workspace.pk,
            "fact_id": fact.pk,
        })

    def _legacy_fragment(self, suffix: str) -> TextFragment:
        source = clean_save(Source(
            workspace=self.workspace,
            code=f"G9-SOURCE-{suffix}-{uuid4().hex[:8]}", version="1.0.0",
            name=f"Source {suffix}", publisher="G9 publisher",
            independence_group=f"G9-{suffix}",
            independence_status=SourceIndependenceStatus.INDEPENDENT,
        ))
        text = "Exact retained fragment."
        digest = hashlib.sha256(text.encode()).hexdigest()
        document = clean_save(Document(
            workspace=self.workspace, source=source,
            code=f"G9-DOC-{suffix}-{uuid4().hex[:8]}", version="1.0.0",
            title=f"Document {suffix}", canonical_url="https://example.test/document",
            lineage_kind=DocumentLineageKind.LEGACY_CAPTURE,
            translation_synchronized=False,
        ))
        version = clean_save(DocumentVersion(
            workspace=self.workspace, document=document,
            code=f"G9-DOC-VERSION-{suffix}-{uuid4().hex[:8]}", version="1.0.0",
            status=DocumentVersionStatus.CONTENT_CAPTURED,
            capture_url=document.canonical_url, content_sha256=digest, media_type="text/plain",
        ))
        clean_save(DocumentContent(
            workspace=self.workspace, document_version=version,
            code=f"G9-CONTENT-{suffix}-{uuid4().hex[:8]}", version="1.0.0",
            normalized_text=text, original_bytes=text.encode(), encoding="utf-8",
            normalization_version="g9-test-v1", content_sha256=digest,
        ))
        return clean_save(TextFragment(
            workspace=self.workspace, document_version=version,
            code=f"G9-FRAGMENT-{suffix}-{uuid4().hex[:8]}", version="1.0.0",
            anchor_status=AnchorStatus.EXACT, start_offset=0, end_offset=len(text),
            selector={"type": "TextPositionSelector", "start": 0, "end": len(text)},
            exact_text=text, text_sha256=digest,
        ))

    def test_parameter_value_fact_list_filters_before_projection_and_neutralizes_zero_vs_hidden(self):
        zero = self.client.get(self._value_url())
        hidden = self._fact("hidden", visibility=Visibility.OWNER_ONLY, coder="django-user:other")
        self._value_link(hidden)
        hidden_only = self.client.get(self._value_url())
        self.assertEqual(zero.content, hidden_only.content)
        self.assertEqual(zero.json(), {
            "code": "NO_ACCESSIBLE_FACT_EVIDENCE",
            "entry": {"kind": "parameter-value", "id": str(self.value.pk)},
            "facts": [],
        })
        visible = self._fact("visible")
        self._value_link(visible)
        payload = self.client.get(self._value_url()).json()
        self.assertEqual([item["id"] for item in payload["facts"]], [str(visible.pk)])
        self.assertNotIn(str(hidden.pk), repr(payload))

    def test_assessment_fact_list_reuses_exact_visibility_and_lane_scope(self):
        public = self._fact("assessment-public")
        private = self._fact(
            "assessment-private", visibility=Visibility.EXPERIMENT_PRIVATE,
            experiment=self.experiment,
        )
        _, other_experiment, _ = self.aggregate(kind="HUMAN")
        wrong_lane = self._fact(
            "assessment-wrong-lane", visibility=Visibility.EXPERIMENT_PRIVATE,
            experiment=other_experiment,
        )
        for fact in (public, private, wrong_lane): self._assessment_link(fact)
        direct = assessment_facts(
            user=self.user, project_id=self.project.pk,
            workspace_id=self.workspace.pk, entry_id=self.assessment.pk,
        ).as_dict()
        http = self.client.get(self._assessment_url()).json()
        self.assertEqual(direct, http)
        self.assertEqual({item["id"] for item in http["facts"]}, {str(public.pk), str(private.pk)})

    def test_entry_list_project_workspace_entry_and_spoofing_fail_uniformly_before_fact_queries(self):
        with patch("domain.services.evidence_access._list_links") as links:
            denial = None
            for url in (
                self._value_url(project=uuid4()),
                self._value_url(workspace=uuid4()),
                self._value_url(entry=uuid4()),
                self._assessment_url(entry=uuid4()),
            ):
                response = self.client.get(url, HTTP_X_PROJECT_ID=str(self.project.pk), HTTP_X_WORKSPACE_ID=str(self.workspace.pk))
                self.assertEqual(response.status_code, 404)
                denial = response.content if denial is None else denial
                self.assertEqual(response.content, denial)
            links.assert_not_called()

    def test_entry_list_owner_private_unspecified_and_revocation_semantics_match_fact_drilldown(self):
        owned = self._fact("owned", visibility=Visibility.OWNER_ONLY)
        unspecified = self._fact("unspecified", visibility=Visibility.OWNER_ONLY, coder="UNSPECIFIED")
        self._value_link(owned); self._value_link(unspecified)
        listed = self.client.get(self._value_url()).json()["facts"]
        self.assertEqual([item["id"] for item in listed], [str(owned.pk)])
        self.assertEqual(self.client.get(self._drilldown_url(owned)).status_code, 200)
        self.assertEqual(self.client.get(self._drilldown_url(unspecified)).status_code, 404)
        self.user.groups.clear()
        self.assertEqual(self.client.get(self._value_url()).status_code, 404)
        self.assertEqual(self.client.get(self._drilldown_url(owned)).status_code, 404)

    def test_entry_list_get_boundary_is_zero_write_no_cookie_no_rehash_no_store_and_method_strict(self):
        password_before = get_user_model().objects.get(pk=self.user.pk).password
        audit_before = AuditEvent.objects.count()
        response = self.client.get(self._value_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Vary"], "Cookie, Authorization")
        self.assertFalse(response.cookies)
        self.assertNotIn("Set-Cookie", response.headers)
        self.assertEqual(AuditEvent.objects.count(), audit_before)
        self.assertEqual(get_user_model().objects.get(pk=self.user.pk).password, password_before)
        for method in (self.client.post, self.client.put, self.client.patch, self.client.delete):
            denied = method(self._value_url(), data=b'{"ignored":true}', content_type="application/json")
            self.assertEqual((denied.status_code, denied.content, denied.headers["Allow"]), (405, b"", "GET"))
        token = base64.b64encode(b"missing-user:wrong-password").decode("ascii")
        denied = self.client.get(self._value_url(), HTTP_AUTHORIZATION=f"Basic {token}")
        self.assertIn(denied.status_code, (401, 404))

    def test_entry_list_dto_is_deterministic_minimal_and_keeps_fact_type_category_and_classification_separate(self):
        root = clean_save(FactCategory(
            project=self.project, code=f"G9-CAT-ROOT-{uuid4().hex[:8]}", version="1.0.0", name="Root",
        ))
        child = clean_save(FactCategory(
            project=self.project, parent=root, code=f"G9-CAT-CHILD-{uuid4().hex[:8]}", version="1.0.0", name="Child",
        ))
        fact = self._fact("classified")
        assignment = clean_save(FactCategoryAssignment(
            workspace=self.workspace, fact=fact, category=child,
            code=f"G9-ASSIGN-{uuid4().hex[:8]}", version="1.0.0",
            classification_status=FactCategoryAssignmentStatus.DISPUTED,
        ))
        self._value_link(fact, AssessmentEvidenceRole.COUNTEREVIDENCE)
        first = self.client.get(self._value_url())
        second = self.client.get(self._value_url())
        self.assertEqual(first.content, second.content)
        dto = first.json()["facts"][0]
        self.assertEqual(set(dto), {
            "id", "code", "version", "fact_type", "statement", "origin", "directness",
            "status", "temporal_status", "category", "entry_evidence",
        })
        self.assertEqual(dto["fact_type"], FactType.OBSERVED_EVENT)
        self.assertEqual(dto["category"]["classification_status"], FactCategoryAssignmentStatus.DISPUTED)
        self.assertEqual(dto["category"]["assignment_id"], str(assignment.pk))
        self.assertEqual([item["code"] for item in dto["category"]["ancestor_path"]], [root.code, child.code])

    def test_entry_to_fact_to_evidence_preserves_multiple_contradictory_roles_and_memory_zero_links(self):
        memory = self._fact("memory")
        self._value_link(memory, AssessmentEvidenceRole.PRIMARY_SUPPORT)
        memory_drilldown = self.client.get(self._drilldown_url(memory)).json()
        self.assertEqual(memory_drilldown["code"], "NO_DOCUMENT_EVIDENCE")
        self.assertEqual(memory_drilldown["evidence"], [])

        fragment = self._legacy_fragment("contradictory")
        documented = self._fact("documented", origin=FactOrigin.DOCUMENT_DERIVED)
        self._value_link(documented, AssessmentEvidenceRole.COUNTEREVIDENCE)
        for relation in (FactEvidenceRelation.SUPPORTS, FactEvidenceRelation.REFUTES, FactEvidenceRelation.CONTEXTUALIZES):
            clean_save(FactEvidence(
                workspace=self.workspace, fact=documented, fragment=fragment,
                code=f"G9-FACT-LINK-{relation}-{uuid4().hex[:8]}", version="1.0.0",
                relation=relation, temporal_status=EvidenceTemporalStatus.UNKNOWN,
            ))
        listed = self.client.get(self._value_url()).json()["facts"]
        self.assertEqual({item["id"] for item in listed}, {str(memory.pk), str(documented.pk)})
        drilldown = self.client.get(self._drilldown_url(documented)).json()
        self.assertEqual([item["relation"] for item in drilldown["evidence"]], [
            FactEvidenceRelation.CONTEXTUALIZES, FactEvidenceRelation.REFUTES, FactEvidenceRelation.SUPPORTS,
        ])

    def test_fact_drilldown_keeps_exact_fragment_version_and_stored_alignment_only_without_latest_or_guess(self):
        source = clean_save(Source(
            workspace=self.workspace, code=f"G9-ALIGNED-SOURCE-{uuid4().hex[:8]}", version="1.0.0",
            name="Aligned source", publisher="Publisher", independence_group="G9-ALIGN",
            independence_status=SourceIndependenceStatus.INDEPENDENT,
        ))
        original_text = "Original one. Original two."
        primary_text = "Первое. Второе."
        original = ContentVariantSpec(
            code="G9-ORIGINAL", language_tag="en", normalized_text=original_text,
            segmentation_version="g9-sentences-v1",
        )
        primary = ContentVariantSpec(
            code="G9-PRIMARY", language_tag="ru", normalized_text=primary_text,
            segmentation_version="g9-sentences-v1",
        )
        result = ingest_initial_synchronized_document(
            workspace=self.workspace, source=source,
            document=DocumentSpec(
                code=f"G9-ALIGNED-DOC-{uuid4().hex[:8]}", title="Aligned document",
                canonical_url="https://example.test/aligned", capture_url="https://example.test/aligned",
                accessed_on=date(2026, 9, 10),
            ),
            original=original, project_primary=primary,
            original_sentences=(
                SentenceSpec(code="G9-O-S1", text="Original one.", start_offset=0, end_offset=13, sentence_number=1),
                SentenceSpec(code="G9-O-S2", text="Original two.", start_offset=14, end_offset=27, sentence_number=2),
            ),
            project_primary_sentences=(
                SentenceSpec(code="G9-P-S1", text="Первое.", start_offset=0, end_offset=7, sentence_number=1),
                SentenceSpec(code="G9-P-S2", text="Второе.", start_offset=8, end_offset=15, sentence_number=2),
            ),
            alignment_components=(AlignmentComponentSpec((1,), (1,)), AlignmentComponentSpec((2,), (2,))),
            translation_provenance=TranslationProvenanceSpec(
                code=f"G9-TRANSLATION-{uuid4().hex[:8]}", translation_id="g9-translation",
                translation_version="1.0.0", translated_at=timezone.now(), actor_type="AI",
                actor_identifier="translator:g9", provider="test", model="test",
                method_version="g9-v1", knowledge="KNOWN",
            ),
        )
        fragment = create_exact_project_primary_fragment(
            document_version=result.document_version, content_variant=result.primary_variant,
            fragment=FragmentSpec(
                code=f"G9-EXACT-FRAGMENT-{uuid4().hex[:8]}", start_offset=0, end_offset=15,
                selector={"type": "TextPositionSelector", "start": 0, "end": 15},
            ),
        )
        fact = self._fact("aligned", origin=FactOrigin.DOCUMENT_DERIVED)
        self._value_link(fact)
        clean_save(FactEvidence(
            workspace=self.workspace, fact=fact, fragment=fragment,
            code=f"G9-ALIGNED-LINK-{uuid4().hex[:8]}", version="1.0.0",
            relation=FactEvidenceRelation.SUPPORTS, temporal_status=EvidenceTemporalStatus.UNKNOWN,
        ))
        payload = self.client.get(self._drilldown_url(fact)).json()
        evidence = payload["evidence"][0]
        self.assertEqual(payload["code"], "DOCUMENT_EVIDENCE")
        self.assertEqual(evidence["document_version"]["id"], str(result.document_version.pk))
        self.assertEqual(evidence["project_primary"]["fragment_id"], str(fragment.pk))
        self.assertEqual(evidence["project_primary"]["exact_text"], primary_text)
        self.assertEqual(evidence["original_excerpt"], "Original one.\nOriginal two.")
        self.assertEqual(evidence["alignment_sha256"], result.alignment_set.alignment_sha256)
        self.assertNotIn("latest", repr(payload).lower())

        unicode_oracle = (
            ("U01", "АБВ", 3, 3, 6, 1, 2, 1, 2, "Б", "c78364c5d0f27706fe002726c70be55fa7ceeb2537db621cfe54f73e9047c389"),
            ("U02", "А😀БВ", 4, 5, 10, 2, 3, 3, 4, "Б", "c78364c5d0f27706fe002726c70be55fa7ceeb2537db621cfe54f73e9047c389"),
            ("U03", "А😀Б", 3, 4, 8, 1, 2, 1, 3, "😀", "f0443a342c5ef54783a111b51ba56c938e474c32324d90c3a60c9c8e3a37e2d9"),
            ("U04", "Ae\u0301Б", 4, 4, 6, 1, 3, 1, 3, "e\u0301", "bf12767b0f2a56b2190075bae8169f656e3ce8d6357d4aff184bc6c7ea48f9f6"),
            ("U05", "А👩\u200d💻Б", 5, 7, 15, 1, 4, 1, 6, "👩\u200d💻", "427274538f1f24ef137872891551ffb4263f6edd90c80c533534578e8a5a9893"),
            ("U06", "А\r\nБ", 4, 4, 6, 3, 4, 3, 4, "Б", "c78364c5d0f27706fe002726c70be55fa7ceeb2537db621cfe54f73e9047c389"),
            ("U07", "А\u2067אב\u2069Б", 6, 6, 14, 2, 4, 2, 4, "אב", "cf7ad5d93148f62ef46ce18b42b7c2303579d6b508b54f75e1ac445e1d9a9e1b"),
            ("U08", "😀 факт; факт", 12, 13, 23, 8, 12, 9, 13, "факт", "a5b27a7349d8d0a202e78c5b3c65005665973aa7ea5aeb7bc3179cea064ecdf6"),
        )
        for (case, text, cp_len, u16_len, byte_len, cp_start, cp_end,
             u16_start, u16_end, quote, quote_sha256) in unicode_oracle:
            with self.subTest(case=case):
                self.assertEqual(len(text), cp_len)
                self.assertEqual(len(text.encode("utf-16-le")) // 2, u16_len)
                self.assertEqual(len(text.encode("utf-8")), byte_len)
                self.assertEqual(text[cp_start:cp_end], quote)
                self.assertEqual(len(text[:cp_start].encode("utf-16-le")) // 2, u16_start)
                self.assertEqual(len(text[:cp_end].encode("utf-16-le")) // 2, u16_end)
                self.assertEqual(hashlib.sha256(quote.encode("utf-8")).hexdigest(), quote_sha256)
