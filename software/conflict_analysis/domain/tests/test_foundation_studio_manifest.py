from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import UUID

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase

from domain.enums import PublicationStatus
from domain.models import Project, ProjectDefinitionVersion
from domain.services.project_definitions import (
    PROJECT_DEFINITION_MANIFEST_FORMAT,
    PROJECT_DEFINITION_MANIFEST_JSON_SCHEMA,
    PROJECT_DEFINITION_MANIFEST_SCHEMA_ID,
    PROJECT_DEFINITION_MANIFEST_VERSION,
    ProjectDefinitionDraftConflict,
    ProjectDefinitionManifestError,
    canonicalize_project_definition_manifest_v1,
    clone_project_definition_draft,
    create_project_definition_draft,
    hash_project_definition_manifest_v1,
    identify_typed_project_definition_manifest,
    open_project_definition_draft,
    parse_project_definition_manifest_v1,
    save_project_definition_draft,
    validate_project_definition_manifest_v1,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "foundation_studio_definition_vectors_v1.json"
)


def load_vectors() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def vector(name: str) -> dict:
    vectors = load_vectors()["vectors"]
    return copy.deepcopy(next(item["manifest"] for item in vectors if item["name"] == name))


def set_path(value: dict, path: list[object], replacement: object) -> None:
    current: object = value
    for part in path[:-1]:
        current = current[part]  # type: ignore[index]
    current[path[-1]] = replacement  # type: ignore[index]


class TypedManifestUnitTests(SimpleTestCase):
    def test_schema_identity_and_cardinality_vectors_are_exact_and_deterministic(self):
        fixtures = load_vectors()
        for item in fixtures["vectors"]:
            manifest = item["manifest"]
            with self.subTest(item["name"]):
                self.assertEqual(manifest["$schema"], PROJECT_DEFINITION_MANIFEST_SCHEMA_ID)
                self.assertEqual(manifest["format"], PROJECT_DEFINITION_MANIFEST_FORMAT)
                self.assertEqual(
                    manifest["format_version"], PROJECT_DEFINITION_MANIFEST_VERSION
                )
                self.assertTrue(identify_typed_project_definition_manifest(manifest))
                report = validate_project_definition_manifest_v1(manifest)
                self.assertTrue(report.valid, report.as_dict())
                self.assertEqual(report.diagnostics, ())
                self.assertEqual(report.manifest_sha256, item["expected_sha256"])
                self.assertEqual(
                    hash_project_definition_manifest_v1(manifest),
                    item["expected_sha256"],
                )
        self.assertEqual(len(vector("valid_3x4")["actors"]), 3)
        self.assertEqual(len(vector("valid_3x4")["analytical_elements"]), 4)
        self.assertEqual(len(vector("valid_6x8")["actors"]), 6)
        self.assertEqual(len(vector("valid_6x8")["analytical_elements"]), 8)

    def test_canonicalization_sorts_object_keys_preserves_arrays_and_input(self):
        manifest = vector("valid_3x4")
        original = copy.deepcopy(manifest)
        reordered = {key: manifest[key] for key in reversed(tuple(manifest))}
        self.assertEqual(
            canonicalize_project_definition_manifest_v1(manifest),
            canonicalize_project_definition_manifest_v1(reordered),
        )
        self.assertEqual(manifest, original)

        reversed_actors = copy.deepcopy(manifest)
        reversed_actors["actors"].reverse()
        self.assertNotEqual(
            hash_project_definition_manifest_v1(manifest),
            hash_project_definition_manifest_v1(reversed_actors),
        )
        canonical = canonicalize_project_definition_manifest_v1(manifest)
        self.assertFalse(canonical.startswith(b"\xef\xbb\xbf"))
        self.assertFalse(canonical.endswith(b"\n"))
        self.assertIn("Studio contract fixture".encode("utf-8"), canonical)

    def test_exact_envelope_dispatch_does_not_reinterpret_legacy_manifest(self):
        legacy = {"actors": [], "analytical_elements": []}
        self.assertFalse(identify_typed_project_definition_manifest(legacy))
        report = validate_project_definition_manifest_v1(legacy)
        self.assertFalse(report.valid)
        self.assertEqual(report.manifest_sha256, "")
        self.assertIn("FORMAT_UNSUPPORTED", {item.code for item in report.diagnostics})
        with self.assertRaises(ProjectDefinitionManifestError):
            hash_project_definition_manifest_v1(legacy)

    def test_new_typed_schema_exposes_only_canonical_v4_target_identities(self):
        target_types = PROJECT_DEFINITION_MANIFEST_JSON_SCHEMA["$defs"][
            "parameter_definition"
        ]["allOf"][1]["properties"]["target_type"]["enum"]
        self.assertTrue(
            {"ACTOR", "ANALYTICAL_ELEMENT", "ACTOR_ELEMENT_ROLE"}.issubset(
                target_types
            )
        )
        self.assertTrue(
            {"TENSION_POINT", "PARTICIPANT_GROUP", "GROUP_TENSION_RELATION"}.isdisjoint(
                target_types
            )
        )

    def test_duplicate_json_keys_bom_and_non_finite_values_fail_closed(self):
        manifest = vector("valid_3x4")
        raw = json.dumps(manifest, ensure_ascii=False)
        duplicate = raw.replace(
            '"format": "conflict-analysis-project-definition",',
            '"format": "conflict-analysis-project-definition", '
            '"format": "conflict-analysis-project-definition",',
            1,
        )
        duplicate_report = validate_project_definition_manifest_v1(duplicate)
        self.assertEqual(
            [item.code for item in duplicate_report.diagnostics],
            ["DUPLICATE_JSON_KEY"],
        )
        bom_report = validate_project_definition_manifest_v1(b"\xef\xbb\xbf" + raw.encode())
        self.assertEqual([item.code for item in bom_report.diagnostics], ["UTF8_BOM_FORBIDDEN"])
        non_finite = copy.deepcopy(manifest)
        non_finite["project"]["metadata"]["bad"] = float("nan")
        finite_report = validate_project_definition_manifest_v1(non_finite)
        self.assertEqual([item.code for item in finite_report.diagnostics], ["FIELD_TYPE_INVALID"])

    def test_fixture_mutations_produce_complete_stable_diagnostics(self):
        fixtures = load_vectors()
        vectors = {
            item["name"]: item["manifest"] for item in fixtures["vectors"]
        }
        identity = fixtures["project"]
        project = mock.Mock(
            pk=UUID(identity["id"]),
            code=identity["code"],
            version=identity["version"],
        )
        for mutation in fixtures["invalid_mutations"]:
            manifest = copy.deepcopy(vectors[mutation["vector"]])
            set_path(manifest, mutation["path"], mutation["value"])
            before = copy.deepcopy(manifest)
            with self.subTest(mutation["name"]):
                first = validate_project_definition_manifest_v1(manifest, project=project)
                second = validate_project_definition_manifest_v1(manifest, project=project)
                self.assertEqual(first.as_dict(), second.as_dict())
                self.assertEqual(manifest, before)
                codes = {diagnostic.code for diagnostic in first.diagnostics}
                self.assertTrue(set(mutation["expected_codes"]).issubset(codes), first.as_dict())

    def test_diagnostics_cover_cycles_orders_forbidden_fields_and_help_version(self):
        manifest = vector("valid_3x4")
        manifest["actors"][0]["parent_id"] = manifest["actors"][1]["id"]
        manifest["actors"][1]["parent_id"] = manifest["actors"][0]["id"]
        manifest["actors"][1]["order"] = manifest["actors"][0]["order"]
        manifest["project"]["metadata"]["formula"] = "forbidden"
        manifest["help_bindings"][0]["topic_version"] = "2.0.0"
        report = validate_project_definition_manifest_v1(manifest)
        codes = {diagnostic.code for diagnostic in report.diagnostics}
        self.assertTrue(
            {
                "HIERARCHY_CYCLE",
                "FORBIDDEN_AGGREGATE_IDENTITY",
                "HELP_TOPIC_VERSION_MISMATCH",
            }.issubset(codes),
            report.as_dict(),
        )

    def test_help_reference_requires_exact_stable_key_not_only_binding_and_hash(self):
        manifest = vector("valid_3x4")
        reference = manifest["help_bindings"][0]
        topic = SimpleNamespace(
            stable_key="studio.different-topic",
            content_sha256=reference["topic_sha256"],
        )
        report = validate_project_definition_manifest_v1(
            manifest,
            help_topic_resolver=lambda _reference: topic,
        )
        self.assertEqual(
            [item.code for item in report.diagnostics],
            ["HELP_TOPIC_STABLE_KEY_MISMATCH"],
        )

    def test_parse_returns_deeply_immutable_dto_with_semantic_diagnostics(self):
        manifest = vector("valid_3x4")
        manifest["actors"][1]["parent_id"] = "11000000-0000-4000-8000-000000000099"
        dto = parse_project_definition_manifest_v1(manifest)
        self.assertFalse(dto.validation.valid)
        self.assertIn(
            "BROKEN_PARENT_REFERENCE",
            {diagnostic.code for diagnostic in dto.validation.diagnostics},
        )
        with self.assertRaises(TypeError):
            dto.manifest["format"] = "changed"  # type: ignore[index]


class TypedManifestDraftServiceTests(TestCase):
    def setUp(self):
        fixture_project = load_vectors()["project"]
        self.project = Project.objects.create(
            id=fixture_project["id"],
            code=fixture_project["code"],
            version=fixture_project["version"],
            name="Persisted project name",
            description="Persisted description",
            metadata={"persisted": True},
        )
        self.principal = object()
        self.authorization = mock.patch(
            "domain.services.project_definitions._require_capability"
        )
        self.require_capability = self.authorization.start()
        self.addCleanup(self.authorization.stop)

    def test_create_open_save_and_stale_write_are_typed_and_project_exact(self):
        manifest = vector("valid_3x4")
        definition = create_project_definition_draft(
            project=self.project,
            code="DEF-001",
            version="1.0.0",
            manifest=manifest,
            principal=self.principal,
        )
        self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)
        self.assertEqual(definition.manifest_hash, hash_project_definition_manifest_v1(manifest))
        opened = open_project_definition_draft(definition, principal=self.principal)
        self.assertEqual(opened.pk, definition.pk)

        edited = copy.deepcopy(manifest)
        edited["actors"][1]["parent_id"] = "11000000-0000-4000-8000-000000000099"
        saved = save_project_definition_draft(
            definition,
            manifest=edited,
            expected_manifest_hash=definition.manifest_hash,
            principal=self.principal,
        )
        self.assertNotEqual(saved.manifest_hash, definition.manifest_hash)
        self.assertFalse(
            validate_project_definition_manifest_v1(
                saved.manifest, project=self.project
            ).valid
        )
        with self.assertRaises(ProjectDefinitionDraftConflict):
            save_project_definition_draft(
                saved,
                manifest=manifest,
                expected_manifest_hash=definition.manifest_hash,
                principal=self.principal,
            )

        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Persisted project name")
        self.assertEqual(self.project.description, "Persisted description")
        self.assertEqual(self.project.metadata, {"persisted": True})

    def test_project_identity_mismatch_is_rejected_without_project_rewrite(self):
        manifest = vector("valid_3x4")
        manifest["project"]["code"] = "OTHER-PROJECT"
        with self.assertRaises(ProjectDefinitionManifestError):
            create_project_definition_draft(
                project=self.project,
                code="DEF-MISMATCH",
                version="1.0.0",
                manifest=manifest,
                principal=self.principal,
            )
        self.project.refresh_from_db()
        self.assertEqual(self.project.code, "PROJECT-STUDIO-V1")
        self.assertEqual(ProjectDefinitionVersion.objects.count(), 0)

    def test_clone_creates_successor_and_source_bytes_remain_unchanged(self):
        source = create_project_definition_draft(
            project=self.project,
            code="DEF-SOURCE",
            version="1.0.0",
            manifest=vector("valid_6x8"),
            principal=self.principal,
        )
        source_manifest = copy.deepcopy(source.manifest)
        successor = clone_project_definition_draft(
            source,
            code="DEF-SUCCESSOR",
            version="2.0.0",
            principal=self.principal,
        )
        self.assertEqual(successor.supersedes_id, source.pk)
        self.assertEqual(successor.publication_status, PublicationStatus.DRAFT)
        self.assertEqual(successor.manifest, source_manifest)
        source.refresh_from_db()
        self.assertEqual(source.manifest, source_manifest)

    def test_nonempty_parallel_definition_metadata_is_rejected(self):
        with self.assertRaises(ValidationError):
            create_project_definition_draft(
                project=self.project,
                code="DEF-METADATA",
                version="1.0.0",
                manifest=vector("valid_3x4"),
                principal=self.principal,
                metadata={"second_authority": True},
            )
        self.assertFalse(ProjectDefinitionVersion.objects.exists())
