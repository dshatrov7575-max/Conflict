from __future__ import annotations

import base64
import hashlib
import json
from datetime import date
from unittest.mock import patch
from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
import pytest
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name
from domain.enums import (
    AnchorStatus,
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
    Document,
    DocumentContent,
    DocumentContentRoleBinding,
    DocumentContentVariant,
    DocumentSentence,
    DocumentVersion,
    Fact,
    FactCategory,
    FactCategoryAssignment,
    FactEvidence,
    Project,
    ProjectWorkspace,
    SentenceAlignmentEdge,
    SentenceAlignmentSet,
    Source,
    TextFragment,
    TranslationProvenance,
)
from domain.services.document_lineage import (
    AlignmentComponentSpec,
    ContentVariantSpec,
    DocumentLineageError,
    DocumentSpec,
    FragmentSpec,
    SentenceSpec,
    TranslationProvenanceSpec,
    create_complete_realignment_derivative,
    create_exact_project_primary_fragment,
    create_translation_edit_derivative,
    ingest_initial_synchronized_document,
)
from domain.services.evidence_drilldown import (
    EvidenceDrilldownCode,
    build_evidence_drilldown,
)
from domain.tests.test_v4_foundation_contracts import (
    FoundationFactoryMixin,
    clean_save,
)


pytest_plugins = (__name__,)


class MultilingualEvidenceLineageTests(FoundationFactoryMixin, TestCase):
    """Frozen portable oracle for F1 multilingual evidence semantics."""

    def setUp(self) -> None:
        self.make_foundation(suffix="F1")
        self.source = self._make_source("F1", "F1-PUBLISHER")

    def _make_source(self, suffix: str, group: str) -> Source:
        return clean_save(
            Source(
                workspace=self.workspace,
                code=f"SOURCE-{suffix}",
                version="1.0.0",
                name=f"Source {suffix}",
                publisher=f"Publisher {group}",
                independence_group=group,
                independence_status=SourceIndependenceStatus.INDEPENDENT,
                homepage_url=f"https://{suffix.lower()}.example.test",
            )
        )

    @staticmethod
    def _role(
        *,
        language_tag: str,
        sentences: tuple[str, ...],
        code: str,
    ) -> tuple[ContentVariantSpec, tuple[SentenceSpec, ...]]:
        text = " ".join(sentences)
        offset = 0
        sentence_specs: list[SentenceSpec] = []
        for number, sentence in enumerate(sentences, start=1):
            end = offset + len(sentence)
            sentence_specs.append(
                SentenceSpec(
                    code=f"{code}-S{number}",
                    text=sentence,
                    start_offset=offset,
                    end_offset=end,
                    sentence_number=number,
                )
            )
            offset = end + 1
        return (
            ContentVariantSpec(
                code=f"{code}-VARIANT",
                language_tag=language_tag,
                normalized_text=text,
                segmentation_version="f1-sentence-v1",
            ),
            tuple(sentence_specs),
        )

    @staticmethod
    def _known_provenance(suffix: str) -> TranslationProvenanceSpec:
        return TranslationProvenanceSpec(
            code=f"TRANSLATION-{suffix}",
            translation_id=f"translation:{suffix}",
            translation_version="2026.09",
            translated_at=timezone.now(),
            actor_type="AI",
            actor_identifier="translator:f1",
            provider="OpenAI",
            model="translation-model-f1",
            method_version="prompt-v1",
            knowledge="KNOWN",
        )

    @staticmethod
    def _unknown_provenance(suffix: str) -> TranslationProvenanceSpec:
        return TranslationProvenanceSpec(
            code=f"TRANSLATION-{suffix}",
            translation_id=f"unknown:{suffix}",
            translation_version="UNKNOWN",
            translated_at=timezone.now(),
            actor_type="UNKNOWN",
            knowledge="UNKNOWN",
        )

    def _ingest(
        self,
        suffix: str,
        *,
        original_sentences: tuple[str, ...] = ("Исходное предложение.",),
        primary_sentences: tuple[str, ...] = ("Primary sentence.",),
        original_language: str = "ru",
        primary_language: str = "en",
        components: tuple[AlignmentComponentSpec, ...] | None = None,
        provenance: TranslationProvenanceSpec | None = None,
        source: Source | None = None,
    ):
        original, stored_original_sentences = self._role(
            language_tag=original_language,
            sentences=original_sentences,
            code=f"DOC-{suffix}-ORIGINAL",
        )
        primary, stored_primary_sentences = self._role(
            language_tag=primary_language,
            sentences=primary_sentences,
            code=f"DOC-{suffix}-PRIMARY",
        )
        if components is None:
            components = tuple(
                AlignmentComponentSpec((number,), (number,))
                for number in range(1, len(original_sentences) + 1)
            )
        if provenance is None and (
            original_language != primary_language
            or original.normalized_text != primary.normalized_text
            or original.segmentation_version != primary.segmentation_version
        ):
            provenance = self._unknown_provenance(suffix)
        return ingest_initial_synchronized_document(
            workspace=self.workspace,
            source=source or self.source,
            document=DocumentSpec(
                code=f"DOC-{suffix}",
                title=f"Multilingual document {suffix}",
                canonical_url=f"https://documents.example.test/{suffix.lower()}",
                capture_url=f"https://capture.example.test/{suffix.lower()}",
                accessed_on=date(2026, 9, 4),
            ),
            original=original,
            project_primary=primary,
            original_sentences=stored_original_sentences,
            project_primary_sentences=stored_primary_sentences,
            alignment_components=components,
            translation_provenance=provenance,
        )

    def _fact(
        self,
        suffix: str,
        *,
        origin: str = FactOrigin.DOCUMENT_DERIVED,
        visibility: str = Visibility.WORKSPACE_SHARED,
        coder_identifier: str = "django-user:fixture",
        workspace: ProjectWorkspace | None = None,
    ) -> Fact:
        return clean_save(
            Fact(
                workspace=workspace or self.workspace,
                code=f"FACT-{suffix}",
                version="1.0.0",
                fact_type=FactType.OBSERVED_EVENT,
                statement=f"F1 immutable fact {suffix}.",
                origin=origin,
                directness=FactDirectness.DIRECT,
                visibility=visibility,
                temporal_status=EvidenceTemporalStatus.UNKNOWN,
                coder_identifier=coder_identifier,
            )
        )

    def _evidence_link(self, suffix: str, *, fact: Fact, fragment: TextFragment) -> FactEvidence:
        return clean_save(
            FactEvidence(
                workspace=fact.workspace,
                fact=fact,
                fragment=fragment,
                code=f"LINK-{suffix}",
                version="1.0.0",
                relation=FactEvidenceRelation.SUPPORTS,
                temporal_status=EvidenceTemporalStatus.UNKNOWN,
            )
        )

    @staticmethod
    def _primary_fragment(result, suffix: str) -> TextFragment:
        primary_text = result.primary_variant.normalized_text
        return create_exact_project_primary_fragment(
            document_version=result.document_version,
            content_variant=result.primary_variant,
            fragment=FragmentSpec(
                code=f"FRAGMENT-{suffix}",
                start_offset=0,
                end_offset=len(primary_text),
                selector={
                    "type": "TextPositionSelector",
                    "start": 0,
                    "end": len(primary_text),
                },
            ),
        )

    def _category(
        self,
        suffix: str,
        *,
        parent: FactCategory | None = None,
        project: Project | None = None,
    ) -> FactCategory:
        return clean_save(
            FactCategory(
                project=project or self.project,
                parent=parent,
                code=f"CATEGORY-{suffix}",
                version="1.0.0",
                name=f"Category {suffix}",
            )
        )

    @staticmethod
    def _assignment(
        suffix: str,
        *,
        fact: Fact,
        category: FactCategory,
        status: str = FactCategoryAssignmentStatus.PROVISIONAL,
    ) -> FactCategoryAssignment:
        return clean_save(
            FactCategoryAssignment(
                workspace=fact.workspace,
                fact=fact,
                category=category,
                code=f"ASSIGNMENT-{suffix}",
                version="1.0.0",
                classification_status=status,
            )
        )

    def _legacy_document_evidence(self, suffix: str):
        """Make an explicit legacy capture without F1 role/alignment claims."""

        text = "Legacy exact captured evidence."
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document = clean_save(
            Document(
                workspace=self.workspace,
                source=self.source,
                code=f"LEGACY-DOC-{suffix}",
                version="1.0.0",
                title=f"Legacy document {suffix}",
                canonical_url=f"https://legacy.example.test/{suffix.lower()}",
                lineage_kind=DocumentLineageKind.LEGACY_CAPTURE,
                translation_synchronized=False,
            )
        )
        version = clean_save(
            DocumentVersion(
                workspace=self.workspace,
                document=document,
                code=f"LEGACY-VERSION-{suffix}",
                version="1.0.0",
                status=DocumentVersionStatus.CONTENT_CAPTURED,
                capture_url=document.canonical_url,
                content_sha256=checksum,
                media_type="text/plain",
            )
        )
        content = clean_save(
            DocumentContent(
                workspace=self.workspace,
                document_version=version,
                code=f"LEGACY-CONTENT-{suffix}",
                version="1.0.0",
                normalized_text=text,
                original_bytes=text.encode("utf-8"),
                encoding="utf-8",
                normalization_version="legacy-v1",
                content_sha256=checksum,
            )
        )
        fragment = clean_save(
            TextFragment(
                workspace=self.workspace,
                document_version=version,
                content_variant=None,
                code=f"LEGACY-FRAGMENT-{suffix}",
                version="1.0.0",
                anchor_status=AnchorStatus.EXACT,
                start_offset=0,
                end_offset=len(text),
                selector={"type": "TextPositionSelector", "start": 0, "end": len(text)},
                exact_text=text,
                text_sha256=checksum,
            )
        )
        return document, version, content, fragment

    @staticmethod
    def _database_fingerprint() -> str:
        snapshot: dict[str, object] = {}
        with connection.cursor() as cursor:
            for table in sorted(connection.introspection.table_names(cursor)):
                cursor.execute(f"SELECT * FROM {connection.ops.quote_name(table)}")
                columns = [item[0] for item in cursor.description or ()]
                rows = sorted(repr(tuple(row)) for row in cursor.fetchall())
                snapshot[table] = {"columns": columns, "rows": rows}
        return hashlib.sha256(
            json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _basic_authorization(username: str, password: str = "test-password") -> str:
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8"))
        return "Basic " + encoded.decode("ascii")

    def _assert_no_response_cookie_mutation(self, response) -> None:
        self.assertFalse(response.cookies)
        self.assertEqual(response.cookies.output(), "")
        self.assertNotIn("Set-Cookie", response.headers)
        self.assertFalse(response.wsgi_request.META.get("CSRF_COOKIE_NEEDS_UPDATE", False))

    def test_fact_category_is_project_scoped_versioned_and_path_is_deterministic(self):
        root = self._category("ROOT")
        child = self._category("CHILD", parent=root)
        grandchild = self._category("GRANDCHILD", parent=child)
        second_workspace = self.make_workspace(code="WORKSPACE-F1-SECOND")
        second_fact = self._fact("SECOND", workspace=second_workspace)
        assignment = self._assignment(
            "SECOND",
            fact=second_fact,
            category=grandchild,
        )

        self.assertEqual(root.project_id, self.project.pk)
        self.assertEqual(
            grandchild.full_path,
            ("CATEGORY-ROOT", "CATEGORY-CHILD", "CATEGORY-GRANDCHILD"),
        )
        self.assertEqual(
            build_evidence_drilldown(second_fact).as_dict()["category"],
            {
                "assignment_id": str(assignment.pk),
                "classification_status": FactCategoryAssignmentStatus.PROVISIONAL,
                "category": {
                    "id": str(grandchild.pk),
                    "code": grandchild.code,
                    "version": grandchild.version,
                },
                "ancestor_path": [
                    {"id": str(root.pk), "code": root.code, "version": root.version},
                    {"id": str(child.pk), "code": child.code, "version": child.version},
                    {
                        "id": str(grandchild.pk),
                        "code": grandchild.code,
                        "version": grandchild.version,
                    },
                ],
                "full_path": "/".join(grandchild.full_path),
            },
        )

    def test_category_self_cycle_cross_project_reparent_and_delete_fail_closed(self):
        root = self._category("ROOT")
        child = self._category("CHILD", parent=root)
        other_project = clean_save(
            Project(
                code="PROJECT-F1-OTHER",
                version="1.0.0",
                name="Other F1 project",
                primary_language_tag="en",
                primary_language_assignment="EXPLICIT",
            )
        )
        foreign = self._category("FOREIGN", project=other_project)

        child.parent = child
        with self.assertRaises(ValidationError):
            child.save()
        child.parent = foreign
        with self.assertRaises(ValidationError):
            child.save()
        child.parent = None
        with self.assertRaises(ValidationError):
            child.save()
        with self.assertRaises(ValidationError):
            root.delete()
        self.assertEqual(FactCategory.objects.get(pk=child.pk).parent_id, root.pk)

    def test_fact_classification_status_is_assignment_state_and_fact_type_remains_separate(self):
        category = self._category("DISPUTED")
        fact = self._fact("CLASSIFICATION")
        assignment = self._assignment(
            "DISPUTED",
            fact=fact,
            category=category,
            status=FactCategoryAssignmentStatus.DISPUTED,
        )

        fact.refresh_from_db()
        self.assertEqual(fact.fact_type, FactType.OBSERVED_EVENT)
        self.assertEqual(assignment.classification_status, FactCategoryAssignmentStatus.DISPUTED)
        self.assertFalse(hasattr(category, "classification_status"))
        self.assertEqual(
            build_evidence_drilldown(fact).as_dict()["category"]["classification_status"],
            FactCategoryAssignmentStatus.DISPUTED,
        )

    def test_legacy_facts_remain_unclassified_without_identity_or_evidence_drift(self):
        document, version, content, fragment = self._legacy_document_evidence("FACT")
        fact = self._fact("LEGACY")
        link = self._evidence_link("LEGACY", fact=fact, fragment=fragment)
        before = {
            "document": (document.pk, document.code, document.root_document_id),
            "version": (version.pk, version.code, version.content_sha256),
            "content": (content.pk, content.normalized_text, content.content_sha256),
            "fragment": (fragment.pk, fragment.exact_text, fragment.content_variant_id),
            "fact": (fact.pk, fact.fact_type, fact.statement),
            "link": (link.pk, link.fact_id, link.fragment_id, link.relation),
        }

        drilldown = build_evidence_drilldown(fact).as_dict()

        self.assertEqual(drilldown["category"]["classification_status"], "UNCLASSIFIED")
        self.assertIsNone(drilldown["category"]["category"])
        self.assertEqual(drilldown["code"], EvidenceDrilldownCode.ALIGNMENT_NOT_GUARANTEED)
        self.assertFalse(FactCategoryAssignment.objects.filter(fact=fact).exists())
        self.assertFalse(DocumentContentRoleBinding.objects.filter(document_version=version).exists())
        self.assertFalse(DocumentSentence.objects.filter(content_variant__document_version=version).exists())
        self.assertFalse(SentenceAlignmentSet.objects.filter(document_version=version).exists())
        self.assertFalse(TranslationProvenance.objects.filter(document_version=version).exists())
        document.refresh_from_db()
        version.refresh_from_db()
        content.refresh_from_db()
        fragment.refresh_from_db()
        fact.refresh_from_db()
        link.refresh_from_db()
        self.assertEqual(
            {
                "document": (document.pk, document.code, document.root_document_id),
                "version": (version.pk, version.code, version.content_sha256),
                "content": (content.pk, content.normalized_text, content.content_sha256),
                "fragment": (fragment.pk, fragment.exact_text, fragment.content_variant_id),
                "fact": (fact.pk, fact.fact_type, fact.statement),
                "link": (link.pk, link.fact_id, link.fragment_id, link.relation),
            },
            before,
        )

    def test_monolingual_content_is_synchronized_without_fabricated_translation_provenance(self):
        result = self._ingest(
            "MONOLINGUAL",
            original_sentences=("Один текст.",),
            primary_sentences=("Один текст.",),
            original_language="ru",
            primary_language="ru",
            provenance=None,
        )

        self.assertTrue(result.document.translation_synchronized)
        self.assertEqual(result.original_variant.pk, result.primary_variant.pk)
        self.assertEqual(result.translation_provenance, None)
        self.assertEqual(
            DocumentContentVariant.objects.filter(document_version=result.document_version).count(),
            1,
        )
        self.assertEqual(
            set(
                DocumentContentRoleBinding.objects.filter(
                    document_version=result.document_version
                ).values_list("role", flat=True)
            ),
            {"ORIGINAL", "PROJECT_PRIMARY"},
        )

    def test_complete_one_to_one_one_to_many_and_many_to_one_alignment_is_checksum_bound(self):
        one_to_one = self._ingest("ONE-ONE")
        one_to_many = self._ingest(
            "ONE-MANY",
            original_sentences=("Исходное предложение.",),
            primary_sentences=("First translated sentence.", "Second translated sentence."),
            components=(AlignmentComponentSpec((1,), (1, 2)),),
        )
        many_to_one = self._ingest(
            "MANY-ONE",
            original_sentences=("Первое исходное предложение.", "Второе исходное предложение."),
            primary_sentences=("One translated sentence.",),
            components=(AlignmentComponentSpec((1, 2), (1,)),),
        )

        cases = (
            (one_to_one, {"ONE_TO_ONE"}, 1),
            (one_to_many, {"ONE_TO_MANY"}, 2),
            (many_to_one, {"MANY_TO_ONE"}, 2),
        )
        for result, cardinalities, expected_edges in cases:
            with self.subTest(document=result.document.code):
                self.assertTrue(result.document.translation_synchronized)
                self.assertIsNotNone(result.alignment_set)
                self.assertEqual(len(result.alignment_set.alignment_sha256), 64)
                self.assertEqual(len(result.alignment_edges), expected_edges)
                self.assertEqual(
                    {edge.cardinality for edge in result.alignment_edges}, cardinalities
                )
                self.assertEqual(
                    SentenceAlignmentEdge.objects.filter(
                        alignment_set=result.alignment_set
                    ).count(),
                    expected_edges,
                )

    def test_partial_positional_contradictory_or_many_to_many_alignment_is_never_synchronized(self):
        baseline = Document.objects.count()
        invalid_components = (
            ("partial", (AlignmentComponentSpec((1,), (1,)),)),
            ("positional", ()),
            ("duplicate", (AlignmentComponentSpec((1, 1), (1,)),)),
            (
                "contradictory",
                (
                    AlignmentComponentSpec((1,), (1,)),
                    AlignmentComponentSpec((1,), (2,)),
                ),
            ),
            ("many-to-many", (AlignmentComponentSpec((1, 2), (1, 2)),)),
        )
        for suffix, components in invalid_components:
            with self.subTest(case=suffix):
                with self.assertRaises(DocumentLineageError):
                    self._ingest(
                        f"INVALID-{suffix}",
                        original_sentences=("Первое.", "Второе."),
                        primary_sentences=("First.", "Second."),
                        components=components,
                    )
        self.assertEqual(Document.objects.count(), baseline)
        self.assertFalse(Document.objects.filter(translation_synchronized=True).exists())

    def test_translation_provenance_preserves_exact_known_fields_and_explicit_unknowns(self):
        known = self._ingest(
            "KNOWN-PROVENANCE",
            provenance=self._known_provenance("KNOWN-PROVENANCE"),
        )
        unknown = self._ingest(
            "UNKNOWN-PROVENANCE",
            provenance=self._unknown_provenance("UNKNOWN-PROVENANCE"),
        )

        self.assertEqual(
            (
                known.translation_provenance.translation_id,
                known.translation_provenance.translation_version,
                known.translation_provenance.provider,
                known.translation_provenance.model,
                known.translation_provenance.method_version,
                known.translation_provenance.knowledge,
            ),
            (
                "translation:KNOWN-PROVENANCE",
                "2026.09",
                "OpenAI",
                "translation-model-f1",
                "prompt-v1",
                "KNOWN",
            ),
        )
        self.assertEqual(
            (
                unknown.translation_provenance.provider,
                unknown.translation_provenance.model,
                unknown.translation_provenance.method_version,
                unknown.translation_provenance.knowledge,
            ),
            ("", "", "", "UNKNOWN"),
        )
        identical_text_different_language = self._ingest(
            "IDENTICAL-TEXT-DIFFERENT-LANGUAGE",
            original_sentences=("Unchanged token.",),
            primary_sentences=("Unchanged token.",),
            original_language="ru",
            primary_language="en",
        )
        self.assertNotEqual(
            identical_text_different_language.original_variant.pk,
            identical_text_different_language.primary_variant.pk,
        )
        self.assertEqual(
            identical_text_different_language.original_variant.content_sha256,
            identical_text_different_language.primary_variant.content_sha256,
        )
        self.assertNotEqual(known.translation_provenance.pk, unknown.translation_provenance.pk)

    def test_any_primary_translation_edit_creates_unsynchronized_derivative_and_preserves_history(self):
        initial = self._ingest("EDIT-INITIAL")
        initial_fragment = self._primary_fragment(initial, "EDIT-INITIAL")
        fact = self._fact("EDIT")
        link = self._evidence_link("EDIT", fact=fact, fragment=initial_fragment)
        original, original_sentences = self._role(
            language_tag="ru",
            sentences=("Исходное предложение.",),
            code="DOC-EDIT-DERIVATIVE-ORIGINAL",
        )
        primary, primary_sentences = self._role(
            language_tag="en",
            sentences=("Primary sentence!",),
            code="DOC-EDIT-DERIVATIVE-PRIMARY",
        )

        edited = create_translation_edit_derivative(
            predecessor_document=initial.document,
            document=DocumentSpec(code="DOC-EDIT-DERIVATIVE", title="Edited translation"),
            original=original,
            project_primary=primary,
            original_sentences=original_sentences,
            project_primary_sentences=primary_sentences,
            translation_provenance=self._unknown_provenance("EDIT-DERIVATIVE"),
        )

        self.assertNotEqual(edited.document.pk, initial.document.pk)
        self.assertEqual(edited.document.predecessor_document_id, initial.document.pk)
        self.assertEqual(edited.document.root_document_id, initial.document.root_document_id)
        self.assertFalse(edited.document.translation_synchronized)
        self.assertIsNone(edited.alignment_set)
        self.assertFalse(
            SentenceAlignmentSet.objects.filter(document_version=edited.document_version).exists()
        )
        link.refresh_from_db()
        initial_fragment.refresh_from_db()
        self.assertEqual(link.fragment_id, initial_fragment.pk)
        self.assertEqual(initial_fragment.content_variant_id, initial.primary_variant.pk)
        self.assertEqual(initial.primary_variant.normalized_text, "Primary sentence.")
        self.assertEqual(edited.primary_variant.normalized_text, "Primary sentence!")

    def test_explicit_complete_realign_creates_new_synchronized_derivative_without_mutation(self):
        initial = self._ingest("REALIGN-INITIAL")
        edited_original, edited_original_sentences = self._role(
            language_tag="ru",
            sentences=("Исходное предложение.",),
            code="DOC-REALIGN-EDIT-ORIGINAL",
        )
        edited_primary, edited_primary_sentences = self._role(
            language_tag="en",
            sentences=("Primary sentence!",),
            code="DOC-REALIGN-EDIT-PRIMARY",
        )
        edited = create_translation_edit_derivative(
            predecessor_document=initial.document,
            document=DocumentSpec(code="DOC-REALIGN-EDIT", title="Edited translation"),
            original=edited_original,
            project_primary=edited_primary,
            original_sentences=edited_original_sentences,
            project_primary_sentences=edited_primary_sentences,
            translation_provenance=self._unknown_provenance("REALIGN-EDIT"),
        )
        realigned = create_complete_realignment_derivative(
            predecessor_document=edited.document,
            document=DocumentSpec(code="DOC-REALIGN-COMPLETE", title="Realigned translation"),
            original=edited_original,
            project_primary=edited_primary,
            original_sentences=edited_original_sentences,
            project_primary_sentences=edited_primary_sentences,
            alignment_components=(AlignmentComponentSpec((1,), (1,)),),
            translation_provenance=self._unknown_provenance("REALIGN-COMPLETE"),
        )

        self.assertNotEqual(realigned.document.pk, edited.document.pk)
        self.assertEqual(realigned.document.predecessor_document_id, edited.document.pk)
        self.assertEqual(realigned.document.root_document_id, initial.document.root_document_id)
        self.assertTrue(realigned.document.translation_synchronized)
        self.assertIsNotNone(realigned.alignment_set)
        edited.document.refresh_from_db()
        self.assertFalse(edited.document.translation_synchronized)
        self.assertIsNone(
            SentenceAlignmentSet.objects.filter(document_version=edited.document_version).first()
        )

    def test_memory_origin_fact_returns_typed_no_document_evidence(self):
        fact = self._fact("MEMORY", origin=FactOrigin.HUMAN_EXPERT_ASSERTION)

        result = build_evidence_drilldown(fact).as_dict()

        self.assertEqual(result["code"], EvidenceDrilldownCode.NO_DOCUMENT_EVIDENCE)
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["fact_id"], str(fact.pk))

    def test_multiple_document_evidence_is_deterministic_without_truth_or_independence_inference(self):
        first = self._ingest("MULTI-FIRST")
        second_source = self._make_source("F1-SECOND", "F1-SECOND-PUBLISHER")
        second = self._ingest("MULTI-SECOND", source=second_source)
        fact = self._fact("MULTI")
        self._evidence_link(
            "Z-MULTI",
            fact=fact,
            fragment=self._primary_fragment(first, "MULTI-FIRST"),
        )
        self._evidence_link(
            "A-MULTI",
            fact=fact,
            fragment=self._primary_fragment(second, "MULTI-SECOND"),
        )

        first_read = build_evidence_drilldown(fact).as_dict()
        second_read = build_evidence_drilldown(fact).as_dict()

        self.assertEqual(first_read, second_read)
        self.assertEqual(first_read["code"], EvidenceDrilldownCode.DOCUMENT_EVIDENCE)
        self.assertEqual(
            [entry["fact_evidence_code"] for entry in first_read["evidence"]],
            ["LINK-A-MULTI", "LINK-Z-MULTI"],
        )
        self.assertTrue(
            all(
                key not in first_read
                for key in ("truth", "truth_value", "source_count", "independence_inferred")
            )
        )
        self.assertTrue(
            all(
                "independence_inferred" not in entry and "truth" not in entry
                for entry in first_read["evidence"]
            )
        )

    def test_synchronized_drilldown_resolves_exact_primary_and_original_fragments(self):
        result = self._ingest(
            "SYNC-DRILLDOWN",
            original_sentences=("Длинное исходное предложение.",),
            primary_sentences=("Short primary.",),
        )
        fragment = self._primary_fragment(result, "SYNC-DRILLDOWN")
        fact = self._fact("SYNC-DRILLDOWN")
        self._evidence_link("SYNC-DRILLDOWN", fact=fact, fragment=fragment)

        payload = build_evidence_drilldown(fact).as_dict()
        evidence = payload["evidence"][0]

        self.assertEqual(payload["code"], EvidenceDrilldownCode.DOCUMENT_EVIDENCE)
        self.assertEqual(
            evidence["project_primary"]["content_variant_id"], str(result.primary_variant.pk)
        )
        self.assertEqual(evidence["project_primary"]["exact_text"], "Short primary.")
        self.assertEqual(evidence["original"]["variant_id"], str(result.original_variant.pk))
        self.assertEqual(evidence["original"]["excerpt"], "Длинное исходное предложение.")
        self.assertEqual(evidence["original_excerpt"], "Длинное исходное предложение.")

    def test_unsynchronized_drilldown_returns_alignment_not_guaranteed_without_guessed_original(self):
        initial = self._ingest("UNSYNC-INITIAL")
        original, original_sentences = self._role(
            language_tag="ru",
            sentences=("Исходное предложение.",),
            code="DOC-UNSYNC-EDIT-ORIGINAL",
        )
        primary, primary_sentences = self._role(
            language_tag="en",
            sentences=("Changed primary sentence.",),
            code="DOC-UNSYNC-EDIT-PRIMARY",
        )
        edited = create_translation_edit_derivative(
            predecessor_document=initial.document,
            document=DocumentSpec(code="DOC-UNSYNC-EDIT", title="Unsynchronized edit"),
            original=original,
            project_primary=primary,
            original_sentences=original_sentences,
            project_primary_sentences=primary_sentences,
            translation_provenance=self._unknown_provenance("UNSYNC-EDIT"),
        )
        fact = self._fact("UNSYNC")
        self._evidence_link(
            "UNSYNC",
            fact=fact,
            fragment=self._primary_fragment(edited, "UNSYNC"),
        )

        payload = build_evidence_drilldown(fact).as_dict()
        evidence = payload["evidence"][0]

        self.assertEqual(payload["code"], EvidenceDrilldownCode.ALIGNMENT_NOT_GUARANTEED)
        self.assertNotIn("original", evidence)
        self.assertNotIn("original_excerpt", evidence)
        self.assertEqual(
            evidence["project_primary"]["content_variant_id"], str(edited.primary_variant.pk)
        )

    def test_drilldown_authorizes_before_disclosure_and_performs_zero_writes(self):
        User = get_user_model()
        owner = User.objects.create_user(username="f1-owner", password="test-password")
        reader = User.objects.create_user(username="f1-reader", password="test-password")
        group = Group.objects.create(name=project_access_group_name(self.project.pk))
        owner.groups.add(group)
        reader.groups.add(group)
        fact = self._fact(
            "PRIVATE",
            visibility=Visibility.OWNER_ONLY,
            coder_identifier=f"django-user:{owner.pk}",
        )
        url = (
            f"/api/foundation/projects/{self.project.pk}/workspaces/{self.workspace.pk}"
            f"/facts/{fact.pk}/evidence/"
        )
        denied_client = APIClient()
        denied_client.force_authenticate(reader)
        with patch(
            "domain.api.evidence.build_evidence_drilldown",
            side_effect=AssertionError("authorization must precede evidence disclosure"),
        ) as read_builder:
            denied = denied_client.get(url)
        read_builder.assert_not_called()
        self.assertEqual(denied.status_code, 404)
        self._assert_no_response_cookie_mutation(denied)
        missing = denied_client.get(
            (
                f"/api/foundation/projects/{self.project.pk}/workspaces/{self.workspace.pk}"
                f"/facts/{uuid4()}/evidence/"
            )
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(denied.content, missing.content)

        password_hasher = PBKDF2PasswordHasher()
        weak_password = password_hasher.encode(
            "test-password", password_hasher.salt(), iterations=1
        )
        self.assertTrue(password_hasher.must_update(weak_password))
        User.objects.filter(pk=owner.pk).update(password=weak_password)
        baseline = self._database_fingerprint()
        owner_client = APIClient()
        response = owner_client.get(
            url,
            HTTP_AUTHORIZATION=self._basic_authorization(owner.username),
        )

        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(response.data["fact_id"], str(fact.pk))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Vary"], "Cookie, Authorization")
        self._assert_no_response_cookie_mutation(response)
        self.assertEqual(User.objects.get(pk=owner.pk).password, weak_password)
        self.assertEqual(self._database_fingerprint(), baseline)

    def test_noncanonical_in_place_or_bypass_mutations_fail_closed(self):
        result = self._ingest("BYPASS")
        result.primary_variant.normalized_text = "rewritten in place"
        with self.assertRaises(ValidationError):
            result.primary_variant.save()
        result.alignment_set.alignment_sha256 = "0" * 64
        with self.assertRaises(ValidationError):
            result.alignment_set.save()
        with self.assertRaises(ValidationError):
            DocumentContentVariant.objects.filter(pk=result.primary_variant.pk).update(
                normalized_text="queryset bypass"
            )
        with self.assertRaises(ValidationError):
            SentenceAlignmentSet.objects.filter(pk=result.alignment_set.pk).update(
                alignment_sha256="f" * 64
            )
        with self.assertRaises(ValidationError):
            clean_save(
                DocumentContentVariant(
                    workspace=self.workspace,
                    document_version=result.document_version,
                    document_content=result.captured_content,
                    code="BYPASS-VARIANT",
                    version="1.0.0",
                    language_tag="ru",
                    normalized_text="Direct bypass.",
                    content_sha256=hashlib.sha256(b"Direct bypass.").hexdigest(),
                    segmentation_version="f1-sentence-v1",
                    variant_kind="DECLARED",
                )
            )


class MultilingualEvidenceLineageMigrationTests(TransactionTestCase):
    """The two non-portable historical migration gates frozen for F1."""

    migrate_from = [("domain", "0016_project_primary_language")]
    migrate_to = [("domain", "0017_multilingual_evidence_lineage")]

    def _require_postgresql(self) -> None:
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only multilingual evidence migration gate")

    def _restore_leaf_migrations(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    @staticmethod
    def _legacy_snapshot(apps, ids: dict[str, UUID]) -> dict[str, object]:
        return {
            "project": apps.get_model("domain", "Project").objects.values(
                "id",
                "code",
                "version",
                "name",
                "primary_language_tag",
                "primary_language_assignment",
            ).get(pk=ids["project"]),
            "workspace": apps.get_model("domain", "ProjectWorkspace").objects.values(
                "id", "project_id", "definition_version_id", "definition_manifest_hash", "code"
            ).get(pk=ids["workspace"]),
            "document": apps.get_model("domain", "Document").objects.values(
                "id", "workspace_id", "source_id", "code", "version", "title", "canonical_url"
            ).get(pk=ids["document"]),
            "document_version": apps.get_model("domain", "DocumentVersion").objects.values(
                "id", "workspace_id", "document_id", "code", "version", "content_sha256"
            ).get(pk=ids["document_version"]),
            "content": apps.get_model("domain", "DocumentContent").objects.values(
                "id", "workspace_id", "document_version_id", "code", "normalized_text", "original_bytes", "content_sha256"
            ).get(pk=ids["content"]),
            "fragment": apps.get_model("domain", "TextFragment").objects.values(
                "id", "workspace_id", "document_version_id", "code", "start_offset", "end_offset", "exact_text", "text_sha256"
            ).get(pk=ids["fragment"]),
            "empty_document": apps.get_model("domain", "Document").objects.values(
                "id", "workspace_id", "source_id", "code", "version", "title", "canonical_url"
            ).get(pk=ids["empty_document"]),
            "empty_document_version": apps.get_model("domain", "DocumentVersion").objects.values(
                "id", "workspace_id", "document_id", "code", "version", "content_sha256"
            ).get(pk=ids["empty_document_version"]),
            "empty_content": apps.get_model("domain", "DocumentContent").objects.values(
                "id", "workspace_id", "document_version_id", "code", "normalized_text", "original_bytes", "content_sha256"
            ).get(pk=ids["empty_content"]),
            "fact": apps.get_model("domain", "Fact").objects.values(
                "id", "workspace_id", "code", "fact_type", "statement", "origin"
            ).get(pk=ids["fact"]),
            "link": apps.get_model("domain", "FactEvidence").objects.values(
                "id", "workspace_id", "fact_id", "fragment_id", "code", "relation"
            ).get(pk=ids["link"]),
        }

    @staticmethod
    def _seed_0016_legacy_evidence(apps) -> dict[str, UUID]:
        Project = apps.get_model("domain", "Project")
        ProjectDefinitionVersion = apps.get_model("domain", "ProjectDefinitionVersion")
        ProjectWorkspace = apps.get_model("domain", "ProjectWorkspace")
        Source = apps.get_model("domain", "Source")
        Document = apps.get_model("domain", "Document")
        DocumentVersion = apps.get_model("domain", "DocumentVersion")
        DocumentContent = apps.get_model("domain", "DocumentContent")
        TextFragment = apps.get_model("domain", "TextFragment")
        Fact = apps.get_model("domain", "Fact")
        FactEvidence = apps.get_model("domain", "FactEvidence")
        ids = {
            name: UUID(value)
            for name, value in {
                "project": "84000000-0000-4000-8000-000000000001",
                "definition": "84000000-0000-4000-8000-000000000002",
                "workspace": "84000000-0000-4000-8000-000000000003",
                "source": "84000000-0000-4000-8000-000000000004",
                "document": "84000000-0000-4000-8000-000000000005",
                "document_version": "84000000-0000-4000-8000-000000000006",
                "content": "84000000-0000-4000-8000-000000000007",
                "fragment": "84000000-0000-4000-8000-000000000008",
                "fact": "84000000-0000-4000-8000-000000000009",
                "link": "84000000-0000-4000-8000-000000000010",
                "empty_document": "84000000-0000-4000-8000-000000000011",
                "empty_document_version": "84000000-0000-4000-8000-000000000012",
                "empty_content": "84000000-0000-4000-8000-000000000013",
            }.items()
        }
        text = "Legacy migration exact evidence."
        content_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        empty_content_sha256 = hashlib.sha256(b"").hexdigest()
        definition_manifest = {"fixture": "f1-0016"}
        definition_hash = hashlib.sha256(
            json.dumps(
                definition_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        project = Project.objects.create(
            id=ids["project"],
            code="F1-MIGRATION-PROJECT",
            version="1.0.0",
            name="F1 migration project",
            primary_language_tag="ru",
            primary_language_assignment="EXPLICIT",
        )
        definition = ProjectDefinitionVersion.objects.create(
            id=ids["definition"],
            project=project,
            code="F1-MIGRATION-DEFINITION",
            version="1.0.0",
            is_current=True,
            publication_status="PUBLISHED",
            manifest=definition_manifest,
            manifest_hash=definition_hash,
            validated_at=timezone.now(),
            validated_by="migration-fixture",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="migration-fixture",
        )
        workspace = ProjectWorkspace.objects.create(
            id=ids["workspace"],
            project=project,
            definition_version=definition,
            definition_manifest_hash=definition_hash,
            code="F1-MIGRATION-WORKSPACE",
            version="1.0.0",
            name="F1 migration workspace",
            is_default=True,
        )
        source = Source.objects.create(
            id=ids["source"],
            workspace=workspace,
            code="F1-MIGRATION-SOURCE",
            version="1.0.0",
            name="F1 migration source",
            publisher="Migration publisher",
            independence_group="migration-publisher",
            independence_status="INDEPENDENT",
            homepage_url="https://migration.example.test",
        )
        document = Document.objects.create(
            id=ids["document"],
            workspace=workspace,
            source=source,
            code="F1-MIGRATION-DOCUMENT",
            version="1.0.0",
            title="F1 legacy document",
            canonical_url="https://migration.example.test/document",
        )
        document_version = DocumentVersion.objects.create(
            id=ids["document_version"],
            workspace=workspace,
            document=document,
            code="F1-MIGRATION-DOCUMENT-VERSION",
            version="1.0.0",
            status="CONTENT_CAPTURED",
            capture_url=document.canonical_url,
            content_sha256=content_sha256,
            media_type="text/plain",
        )
        content = DocumentContent.objects.create(
            id=ids["content"],
            workspace=workspace,
            document_version=document_version,
            code="F1-MIGRATION-CONTENT",
            version="1.0.0",
            normalized_text=text,
            original_bytes=text.encode("utf-8"),
            encoding="utf-8",
            normalization_version="legacy-v1",
            content_sha256=content_sha256,
        )
        empty_document = Document.objects.create(
            id=ids["empty_document"],
            workspace=workspace,
            source=source,
            code="F1-MIGRATION-EMPTY-DOCUMENT",
            version="1.0.0",
            title="F1 zero-byte legacy document",
            canonical_url="https://migration.example.test/empty-document",
        )
        empty_document_version = DocumentVersion.objects.create(
            id=ids["empty_document_version"],
            workspace=workspace,
            document=empty_document,
            code="F1-MIGRATION-EMPTY-DOCUMENT-VERSION",
            version="1.0.0",
            status="CONTENT_CAPTURED",
            capture_url=empty_document.canonical_url,
            content_sha256=empty_content_sha256,
            media_type="text/plain",
        )
        DocumentContent.objects.create(
            id=ids["empty_content"],
            workspace=workspace,
            document_version=empty_document_version,
            code="F1-MIGRATION-EMPTY-CONTENT",
            version="1.0.0",
            normalized_text="",
            original_bytes=b"",
            encoding="utf-8",
            normalization_version="legacy-v1",
            content_sha256=empty_content_sha256,
        )
        fragment = TextFragment.objects.create(
            id=ids["fragment"],
            workspace=workspace,
            document_version=document_version,
            code="F1-MIGRATION-FRAGMENT",
            version="1.0.0",
            anchor_status="EXACT",
            start_offset=0,
            end_offset=len(text),
            selector={"type": "TextPositionSelector", "start": 0, "end": len(text)},
            exact_text=text,
            text_sha256=content_sha256,
        )
        fact = Fact.objects.create(
            id=ids["fact"],
            workspace=workspace,
            code="F1-MIGRATION-FACT",
            version="1.0.0",
            fact_type="OBSERVED_EVENT",
            statement="Legacy fact identity must survive.",
            origin="DOCUMENT_DERIVED",
            directness="DIRECT",
            visibility="WORKSPACE_SHARED",
            temporal_status="UNKNOWN",
            coder_identifier="migration-fixture",
        )
        FactEvidence.objects.create(
            id=ids["link"],
            workspace=workspace,
            fact=fact,
            fragment=fragment,
            code="F1-MIGRATION-LINK",
            version="1.0.0",
            relation="SUPPORTS",
            temporal_status="UNKNOWN",
        )
        return ids

    def _clear_0016_fixture(self, apps) -> None:
        for model_name in (
            "FactEvidence",
            "Fact",
            "TextFragment",
            "DocumentContent",
            "DocumentVersion",
            "Document",
            "Source",
            "ProjectWorkspace",
            "ProjectDefinitionVersion",
            "Project",
        ):
            apps.get_model("domain", model_name).objects.all().delete()

    def test_0016_to_0017_preserves_project_language_and_all_legacy_evidence_identities(self):
        self._require_postgresql()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self._restore_leaf_migrations)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        ids = self._seed_0016_legacy_evidence(old_apps)
        before = self._legacy_snapshot(old_apps, ids)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        after = self._legacy_snapshot(apps, ids)
        Document = apps.get_model("domain", "Document")
        TextFragment = apps.get_model("domain", "TextFragment")
        DocumentContentVariant = apps.get_model("domain", "DocumentContentVariant")
        DocumentContentRoleBinding = apps.get_model("domain", "DocumentContentRoleBinding")
        DocumentSentence = apps.get_model("domain", "DocumentSentence")
        SentenceAlignmentSet = apps.get_model("domain", "SentenceAlignmentSet")
        SentenceAlignmentEdge = apps.get_model("domain", "SentenceAlignmentEdge")
        TranslationProvenance = apps.get_model("domain", "TranslationProvenance")
        FactCategory = apps.get_model("domain", "FactCategory")
        FactCategoryAssignment = apps.get_model("domain", "FactCategoryAssignment")

        self.assertEqual(after, before)
        document = Document.objects.get(pk=ids["document"])
        self.assertEqual(document.root_document_id, document.pk)
        self.assertIsNone(document.predecessor_document_id)
        self.assertEqual(document.lineage_kind, "LEGACY_CAPTURE")
        self.assertFalse(document.translation_synchronized)
        variant = DocumentContentVariant.objects.get(document_content_id=ids["content"])
        self.assertEqual(
            (
                variant.document_version_id,
                variant.language_tag,
                variant.variant_kind,
                variant.normalized_text,
                variant.content_sha256,
                variant.metadata["legacy_capture_sha256"],
            ),
            (
                ids["document_version"],
                "und",
                "LEGACY_UNSPECIFIED",
                before["content"]["normalized_text"],
                hashlib.sha256(
                    before["content"]["normalized_text"].encode("utf-8")
                ).hexdigest(),
                before["content"]["content_sha256"],
            ),
        )
        empty_variant = DocumentContentVariant.objects.get(
            document_content_id=ids["empty_content"]
        )
        self.assertEqual(
            (
                empty_variant.document_version_id,
                empty_variant.language_tag,
                empty_variant.variant_kind,
                empty_variant.normalized_text,
                empty_variant.content_sha256,
                empty_variant.metadata["legacy_capture_sha256"],
            ),
            (
                ids["empty_document_version"],
                "und",
                "LEGACY_UNSPECIFIED",
                "",
                hashlib.sha256(b"").hexdigest(),
                hashlib.sha256(b"").hexdigest(),
            ),
        )
        fragment = TextFragment.objects.get(pk=ids["fragment"])
        self.assertEqual(fragment.content_variant_id, variant.pk)
        self.assertFalse(DocumentContentRoleBinding.objects.filter(document_version_id=ids["document_version"]).exists())
        self.assertFalse(DocumentSentence.objects.filter(content_variant=variant).exists())
        self.assertFalse(SentenceAlignmentSet.objects.filter(document_version_id=ids["document_version"]).exists())
        self.assertFalse(SentenceAlignmentEdge.objects.exists())
        self.assertFalse(TranslationProvenance.objects.filter(document_version_id=ids["document_version"]).exists())
        self.assertFalse(FactCategory.objects.exists())
        self.assertFalse(FactCategoryAssignment.objects.exists())

    def test_0017_reverse_reapply_and_empty_database_are_deterministic(self):
        self._require_postgresql()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self._restore_leaf_migrations)
        apps_0016 = executor.loader.project_state(self.migrate_from).apps
        ids = self._seed_0016_legacy_evidence(apps_0016)
        before = self._legacy_snapshot(apps_0016, ids)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps_0017 = executor.loader.project_state(self.migrate_to).apps
        first_successor_rows = {
            "document": apps_0017.get_model("domain", "Document").objects.values(
                "id", "root_document_id", "predecessor_document_id", "lineage_kind", "translation_synchronized"
            ).get(pk=ids["document"]),
            "variant": apps_0017.get_model("domain", "DocumentContentVariant").objects.values(
                "document_content_id", "document_version_id", "language_tag", "variant_kind", "normalized_text", "content_sha256", "metadata"
            ).get(document_content_id=ids["content"]),
            "empty_variant": apps_0017.get_model("domain", "DocumentContentVariant").objects.values(
                "document_content_id", "document_version_id", "language_tag", "variant_kind", "normalized_text", "content_sha256", "metadata"
            ).get(document_content_id=ids["empty_content"]),
            "fragment": apps_0017.get_model("domain", "TextFragment").objects.values(
                "id", "exact_text", "text_sha256"
            ).get(pk=ids["fragment"]),
        }

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        reversed_apps = executor.loader.project_state(self.migrate_from).apps
        self.assertEqual(self._legacy_snapshot(reversed_apps, ids), before)
        self.assertNotIn(
            "content_variant",
            {field.name for field in reversed_apps.get_model("domain", "TextFragment")._meta.get_fields()},
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        reapplied_apps = executor.loader.project_state(self.migrate_to).apps
        reapplied_successor_rows = {
            "document": reapplied_apps.get_model("domain", "Document").objects.values(
                "id", "root_document_id", "predecessor_document_id", "lineage_kind", "translation_synchronized"
            ).get(pk=ids["document"]),
            "variant": reapplied_apps.get_model("domain", "DocumentContentVariant").objects.values(
                "document_content_id", "document_version_id", "language_tag", "variant_kind", "normalized_text", "content_sha256", "metadata"
            ).get(document_content_id=ids["content"]),
            "empty_variant": reapplied_apps.get_model("domain", "DocumentContentVariant").objects.values(
                "document_content_id", "document_version_id", "language_tag", "variant_kind", "normalized_text", "content_sha256", "metadata"
            ).get(document_content_id=ids["empty_content"]),
            "fragment": reapplied_apps.get_model("domain", "TextFragment").objects.values(
                "id", "exact_text", "text_sha256"
            ).get(pk=ids["fragment"]),
        }
        self.assertEqual(reapplied_successor_rows, first_successor_rows)
        self.assertEqual(self._legacy_snapshot(reapplied_apps, ids), before)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        empty_0016 = executor.loader.project_state(self.migrate_from).apps
        self._clear_0016_fixture(empty_0016)
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        empty_0017 = executor.loader.project_state(self.migrate_to).apps
        for model_name in (
            "DocumentContentVariant",
            "DocumentContentRoleBinding",
            "DocumentSentence",
            "SentenceAlignmentSet",
            "SentenceAlignmentEdge",
            "TranslationProvenance",
            "FactCategory",
            "FactCategoryAssignment",
        ):
            self.assertFalse(empty_0017.get_model("domain", model_name).objects.exists())


_F1_JUNIT_ORDER = {
    MultilingualEvidenceLineageTests: (
        "test_fact_category_is_project_scoped_versioned_and_path_is_deterministic",
        "test_category_self_cycle_cross_project_reparent_and_delete_fail_closed",
        "test_fact_classification_status_is_assignment_state_and_fact_type_remains_separate",
        "test_legacy_facts_remain_unclassified_without_identity_or_evidence_drift",
        "test_monolingual_content_is_synchronized_without_fabricated_translation_provenance",
        "test_complete_one_to_one_one_to_many_and_many_to_one_alignment_is_checksum_bound",
        "test_partial_positional_contradictory_or_many_to_many_alignment_is_never_synchronized",
        "test_translation_provenance_preserves_exact_known_fields_and_explicit_unknowns",
        "test_any_primary_translation_edit_creates_unsynchronized_derivative_and_preserves_history",
        "test_explicit_complete_realign_creates_new_synchronized_derivative_without_mutation",
        "test_memory_origin_fact_returns_typed_no_document_evidence",
        "test_multiple_document_evidence_is_deterministic_without_truth_or_independence_inference",
        "test_synchronized_drilldown_resolves_exact_primary_and_original_fragments",
        "test_unsynchronized_drilldown_returns_alignment_not_guaranteed_without_guessed_original",
        "test_drilldown_authorizes_before_disclosure_and_performs_zero_writes",
        "test_noncanonical_in_place_or_bypass_mutations_fail_closed",
    ),
    MultilingualEvidenceLineageMigrationTests: (
        "test_0016_to_0017_preserves_project_language_and_all_legacy_evidence_identities",
        "test_0017_reverse_reapply_and_empty_database_are_deterministic",
    ),
}
_F1_JUNIT_RANK = {
    test_class: {method_name: position for position, method_name in enumerate(method_names)}
    for test_class, method_names in _F1_JUNIT_ORDER.items()
}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(items):
    """Emit the frozen F1 unittest registry in the acceptance-defined order."""
    ordered_by_class = {}
    for test_class, expected_names in _F1_JUNIT_ORDER.items():
        class_items = [item for item in items if item.cls is test_class]
        if not class_items:
            continue
        actual_names = {item.name for item in class_items}
        if actual_names != set(expected_names) or len(class_items) != len(expected_names):
            raise RuntimeError("F1 frozen JUnit registry drifted")
        ordered_by_class[test_class] = iter(
            sorted(class_items, key=lambda item: _F1_JUNIT_RANK[test_class][item.name])
        )
    items[:] = [
        next(ordered_by_class[item.cls]) if item.cls in ordered_by_class else item
        for item in items
    ]
