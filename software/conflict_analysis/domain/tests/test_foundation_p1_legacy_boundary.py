from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from django.contrib import admin as django_admin
from django.db import transaction
from django.test import SimpleTestCase, TestCase

from domain.models import (
    AssessmentSet,
    AuditEvent,
    Document,
    DocumentContent,
    DocumentVersion,
    EvidenceLink,
    EvidenceSource,
    Fact,
    GroupTensionRelation,
    LegacyCompatibilityReceipt,
    ParameterDefinition,
    ParameterValue,
    Project,
    ProjectWorkspace,
    Scenario,
    ScenarioOverride,
    Source,
    TextFragment,
    TimeSlice,
)
from domain.enums import EvidenceRelation, TargetType, ValueStatus
from domain.services.foundation_packages import export_foundation_package
from domain.services.project_packages import (
    CANONICAL_CAPTURED_CONTENT_MODEL,
    CANONICAL_EVIDENCE_CHAIN,
    LEGACY_COMPATIBILITY_ONLY,
    V1_HISTORICAL_SCENARIO_RESIDUE,
    V1_SECTION_AUTHORITY,
    export_project_package,
    import_project_package,
)
from domain.services.seed import seed_zhanaozen_demo


class FoundationP1LegacyBoundaryStaticTests(SimpleTestCase):
    def test_v1_sections_are_executable_compatibility_markers_and_hidden(self):
        self.assertEqual(
            V1_SECTION_AUTHORITY,
            {
                "evidence_sources": LEGACY_COMPATIBILITY_ONLY,
                "evidence_links": LEGACY_COMPATIBILITY_ONLY,
                "scenarios": LEGACY_COMPATIBILITY_ONLY,
                "scenario_overrides": LEGACY_COMPATIBILITY_ONLY,
            },
        )
        self.assertEqual(
            V1_HISTORICAL_SCENARIO_RESIDUE,
            {"scenarios", "scenario_overrides"},
        )
        self.assertEqual(
            CANONICAL_EVIDENCE_CHAIN,
            (
                "Source",
                "Document",
                "DocumentVersion",
                "TextFragment",
                "Fact",
                "Assessment/ParameterValue",
            ),
        )
        self.assertEqual(CANONICAL_CAPTURED_CONTENT_MODEL, "DocumentContent")

        from domain.admin import HiddenLegacyCompatibilityAdmin

        for legacy_model in (
            EvidenceSource,
            EvidenceLink,
            Scenario,
            ScenarioOverride,
        ):
            registered = django_admin.site._registry[legacy_model]
            self.assertIsInstance(registered, HiddenLegacyCompatibilityAdmin)
            self.assertFalse(registered.has_module_permission(None))

    def test_v2_schema_and_docs_keep_legacy_evidence_outside_canonical_authority(self):
        domain_root = Path(__file__).resolve().parents[1]
        schema = json.loads(
            (
                domain_root
                / "services"
                / "schemas"
                / "foundation-package-2.0.0.schema.json"
            ).read_text(encoding="utf-8")
        )
        public_sections = set(schema["properties"])
        self.assertTrue(
            {"sources", "documents", "document_versions", "text_fragments", "facts"}
            .issubset(public_sections)
        )
        self.assertTrue(
            {"evidence_sources", "evidence_links", "scenarios", "scenario_overrides"}
            .isdisjoint(public_sections)
        )

        repository_root = Path(__file__).resolve().parents[2]
        docs = (repository_root / "docs" / "foundation-package-v2.md").read_text(
            encoding="utf-8"
        )
        readme = (repository_root / "README.md").read_text(encoding="utf-8")
        for text in (docs, readme):
            self.assertIn(LEGACY_COMPATIBILITY_ONLY, text)
            self.assertIn("DocumentVersion", text)
            self.assertIn("TextFragment", text)
            self.assertIn("Assessment/ParameterValue", text)
        self.assertIn("never fabricates", docs)
        self.assertIn("does not authorize", docs)


class FoundationP1LegacyBoundaryRuntimeTests(TestCase):
    def test_v1_direct_evidence_stays_unresolved_and_v2_export_is_canonical(self):
        fixture_savepoint = transaction.savepoint()
        project = seed_zhanaozen_demo()
        value = ParameterValue(
            project=project,
            workspace=ProjectWorkspace.objects.get(project=project, is_default=True),
            code="LEGACY-VALUE-P1",
            version="1.0.0",
            time_slice=TimeSlice.objects.get(project=project, code="2011-12-15"),
            assessment_set=AssessmentSet.objects.get(
                project=project,
                code="HUMAN_DRAFT",
            ),
            parameter_definition=ParameterDefinition.objects.get(
                project=project,
                code="UOS",
            ),
            target_type=TargetType.GROUP_TENSION_RELATION,
            target_id=GroupTensionRelation.objects.filter(project=project).first().pk,
            status=ValueStatus.PROVISIONAL,
            value=2,
            confidence=Decimal("0.7500"),
            rationale="Legacy compatibility test value.",
        )
        value.full_clean()
        value.save(force_insert=True)
        legacy_source = EvidenceSource(
            project=project,
            code="LEGACY-SOURCE-P1",
            version="1.0.0",
            title="Legacy URL-only evidence",
            url="https://example.test/legacy-source",
        )
        legacy_source.full_clean()
        legacy_source.save(force_insert=True)
        legacy_link = EvidenceLink(
            project=project,
            code="LEGACY-LINK-P1",
            version="1.0.0",
            parameter_value=value,
            source=legacy_source,
            relation=EvidenceRelation.SUPPORTS,
            rationale="Legacy direct value-to-URL evidence.",
        )
        legacy_link.full_clean()
        legacy_link.save(force_insert=True)
        v1_package = export_project_package(project)
        transaction.savepoint_rollback(fixture_savepoint)

        imported = import_project_package(v1_package)
        workspace = ProjectWorkspace.objects.get(project=imported, is_default=True)
        for legacy_model, legacy_code in (
            ("EvidenceSource", "LEGACY-SOURCE-P1"),
            ("EvidenceLink", "LEGACY-LINK-P1"),
        ):
            receipt = LegacyCompatibilityReceipt.objects.get(
                workspace=workspace,
                legacy_model=legacy_model,
                legacy_code=legacy_code,
            )
            self.assertEqual(receipt.status, "UNRESOLVED")
            self.assertIsNone(receipt.canonical_id)
            self.assertEqual(receipt.canonical_model, "")
            self.assertIn(LEGACY_COMPATIBILITY_ONLY, receipt.reason)

        self.assertTrue(EvidenceSource.objects.filter(project=imported).exists())
        self.assertTrue(EvidenceLink.objects.filter(project=imported).exists())
        for canonical_model in (
            Source,
            Document,
            DocumentVersion,
            DocumentContent,
            TextFragment,
            Fact,
        ):
            self.assertFalse(canonical_model.objects.filter(workspace=workspace).exists())

        v2_package = export_foundation_package(workspace)
        self.assertTrue(
            {"sources", "documents", "document_versions", "text_fragments", "facts"}
            .issubset(v2_package)
        )
        self.assertTrue(
            {"evidence_sources", "evidence_links", "scenarios", "scenario_overrides"}
            .isdisjoint(v2_package)
        )
        self.assertEqual(v2_package["sources"], [])
        self.assertEqual(v2_package["documents"], [])
        self.assertEqual(v2_package["document_versions"], [])
        self.assertEqual(v2_package["text_fragments"], [])
        self.assertEqual(v2_package["facts"], [])
        self.assertEqual(len(v2_package["compatibility_receipts"]), 2)
        self.assertEqual(
            {item["status"] for item in v2_package["compatibility_receipts"]},
            {"UNRESOLVED"},
        )
