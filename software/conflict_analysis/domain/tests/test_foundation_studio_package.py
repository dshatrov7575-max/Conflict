from __future__ import annotations

import copy
import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import OperationalError, close_old_connections, connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase

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


def reverse_object_keys(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: reverse_object_keys(value[key])
            for key in reversed(tuple(value))
        }
    if isinstance(value, list):
        return [reverse_object_keys(item) for item in value]
    return copy.deepcopy(value)


def diagnostic_bytes(diagnostics: list[dict[str, str]]) -> bytes:
    return json.dumps(
        diagnostics,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


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

    def test_adversarial_diagnostic_order_is_a_frozen_pass_ordered_vector(self):
        fixtures = load_vectors()
        oracle = fixtures["diagnostic_order_oracle"]
        identity = fixtures["project"]
        project = mock.Mock(
            pk=UUID(identity["id"]),
            code=identity["code"],
            version=identity["version"],
        )
        manifest = copy.deepcopy(oracle["manifest"])

        def validate(value: object) -> list[dict[str, str]]:
            report = validate_project_definition_manifest_v1(
                value,  # type: ignore[arg-type]
                project=project,
                help_topic_resolver=lambda _reference: None,
            )
            return [item.as_dict() for item in report.diagnostics]

        expected_bytes = diagnostic_bytes(oracle["expected_diagnostics"])
        first = validate(manifest)
        self.assertEqual(diagnostic_bytes(first), expected_bytes)
        self.assertEqual(diagnostic_bytes(validate(manifest)), expected_bytes)

        key_reordered = reverse_object_keys(manifest)
        self.assertEqual(diagnostic_bytes(validate(key_reordered)), expected_bytes)

        row_reordered = copy.deepcopy(manifest)
        row_reordered["actors"][0], row_reordered["actors"][1] = (
            row_reordered["actors"][1],
            row_reordered["actors"][0],
        )
        reordered = validate(row_reordered)
        self.assertNotEqual(diagnostic_bytes(reordered), expected_bytes)
        self.assertIn("/actors/1/label", {item["path"] for item in reordered})

        messages = "\n".join(item["message"] for item in first)
        for raw_jsonschema_fragment in (
            "is a required property",
            "Additional properties are not allowed",
            "is not of type",
            "is not one of",
            "is not valid under any of the given schemas",
        ):
            self.assertNotIn(raw_jsonschema_fragment, messages)

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

import copy
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from domain.enums import (
    AuditActorType,
    HelpApplicationScope,
    ImportPackageScope,
    PublicationStatus,
)
from domain.models import (
    AuditEvent,
    HelpTopic,
    ImportRun,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    ProjectWorkspace,
    UIHelpBinding,
)
from domain.policies import (
    StudioCapability,
    StudioPrincipal,
    StudioRole,
    bootstrap_initial_project_definition,
    publish_project_definition,
    validate_project_definition,
)
from domain.services.foundation_packages import (
    FOUNDATION_PACKAGE_VERSION,
    FOUNDATION_PACKAGE_VERSION_2_1,
    FOUNDATION_RAW_JSON_MAX_BYTES,
    FoundationPackageConflictError,
    FoundationPackageValidationError,
    attempt_foundation_import_2_1,
    canonical_json,
    commit_foundation_package_2_1,
    export_project_definition_package_2_1,
    export_workspace_package_2_1,
    preview_foundation_package_2_1,
    seal_foundation_package_2_1,
    validate_foundation_package_2_1,
)
from domain.services.project_definitions import (
    create_project_definition_draft,
    save_project_definition_draft,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "foundation_studio_definition_vectors_v1.json"
)


class FoundationStudioPackage21Tests(TestCase):
    def setUp(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.manifest = copy.deepcopy(fixture["vectors"][0]["manifest"])
        identity = self.manifest["project"]
        self.project = Project.objects.create(
            id=identity["id"],
            code=identity["code"],
            version=identity["version"],
            name="Persisted Project",
        )
        html = "<p>Package help.</p>"
        help_sha = hashlib.sha256(html.encode()).hexdigest()
        self.topic = HelpTopic(
            code="HELP-PACKAGE",
            version="1.0.0",
            stable_key="studio.welcome",
            title="Package help",
            application_scope=HelpApplicationScope.STUDIO,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="en",
            sanitized_html=html,
            content_sha256=help_sha,
            publication_status=PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.topic.save(force_insert=True)
        UIHelpBinding(
            code="GLOBAL-PACKAGE-HELP",
            version="1.0.0",
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            ui_key="studio.welcome",
            locale="en",
            help_topic=self.topic,
        ).save(force_insert=True)
        self.manifest["help_bindings"][0]["topic_sha256"] = help_sha
        self.editor = StudioPrincipal.for_role(
            actor_identifier="editor", role=StudioRole.STUDIO_EDITOR
        )
        self.service = StudioPrincipal.service(
            actor_identifier="foundation-package-service",
            purpose="Foundation 2.1 project-definition import",
            capabilities=frozenset(
                {
                    StudioCapability.DRAFT_CREATE,
                    StudioCapability.DEFINITION_VALIDATE,
                    StudioCapability.DEFINITION_PUBLISH,
                    StudioCapability.FOUNDATION_IMPORT,
                }
            ),
        )

    def create_draft(self) -> ProjectDefinitionVersion:
        return create_project_definition_draft(
            project=self.project,
            definition_id="17000000-0000-4000-8000-000000000001",
            code="DEF-PACKAGE-V1",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor,
        )

    def test_project_definition_draft_roundtrip_preserves_stable_id_hash_and_bytes(self):
        source = self.create_draft()
        package = export_project_definition_package_2_1(source)
        self.assertEqual(package["format_version"], FOUNDATION_PACKAGE_VERSION_2_1)
        self.assertEqual(package["package_scope"], "PROJECT_DEFINITION")
        self.assertEqual(package["project_definition"]["id"], str(source.pk))
        self.assertEqual(package["project_definition"]["manifest_hash"], source.manifest_hash)
        source_id = source.pk
        source.delete()

        preview = preview_foundation_package_2_1(package, project=self.project)
        self.assertEqual(preview.intended_action, "CREATE_DRAFT")
        result = commit_foundation_package_2_1(
            preview,
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
        )
        imported = ProjectDefinitionVersion.objects.get(pk=source_id)
        self.assertEqual(result.definition_id, str(source_id))
        self.assertEqual(imported.manifest, self.manifest)
        self.assertEqual(imported.manifest_hash, source.manifest_hash)
        self.assertEqual(
            canonical_json(export_project_definition_package_2_1(imported)),
            canonical_json(package),
        )
        receipt = ImportRun.objects.get(pk=result.receipt_id)
        self.assertEqual(str(receipt.project_id), str(self.project.pk))
        self.assertIsNone(receipt.workspace_id)
        self.assertEqual(receipt.definition_version_id, imported.pk)
        self.assertEqual(receipt.package_scope, ImportPackageScope.PROJECT_DEFINITION)
        self.assertEqual(receipt.package_version, FOUNDATION_PACKAGE_VERSION_2_1)
        self.assertEqual(receipt.selected_input["raw_input_kind"], "CANONICAL_MAPPING")
        self.assertEqual(receipt.selected_input["raw_input_sha256"], preview.raw_input_sha256)
        self.assertEqual(
            receipt.selected_input["canonical_payload_sha256"],
            package["manifest"]["payload_sha256"],
        )

    def test_exact_reuse_is_allowed_once_but_drift_and_replay_fail_closed(self):
        definition = self.create_draft()
        package = export_project_definition_package_2_1(definition)
        preview = preview_foundation_package_2_1(package, project=self.project)
        self.assertEqual(preview.intended_action, "REUSE_EXACT")
        commit_foundation_package_2_1(
            preview,
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
        )
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_1(
                preview,
                project=self.project,
                principal=self.service,
                actor_identifier=self.service.actor_identifier,
            )
        self.assertEqual(ImportRun.objects.count(), 1)

        drifted = copy.deepcopy(package)
        drifted["project"]["code"] = "OTHER-PROJECT"
        drifted = seal_foundation_package_2_1(drifted)
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package_2_1(drifted, project=self.project)

    def test_format_and_import_actor_spoof_fail_before_any_write(self):
        source = self.create_draft()
        package = export_project_definition_package_2_1(source)
        source.delete()
        preview = preview_foundation_package_2_1(package, project=self.project)

        with self.assertRaises(PermissionDenied):
            commit_foundation_package_2_1(
                preview,
                project=self.project,
                principal=self.editor,
                actor_identifier=self.editor.actor_identifier,
            )
        with self.assertRaises(FoundationPackageValidationError):
            commit_foundation_package_2_1(
                preview,
                project=self.project,
                principal=self.service,
                actor_identifier="spoofed-import-actor",
            )
        self.assertFalse(ProjectDefinitionVersion.objects.exists())
        self.assertFalse(ImportRun.objects.exists())

        malformed = copy.deepcopy(package)
        malformed["selected_definition_id"] = "not-a-uuid"
        malformed = seal_foundation_package_2_1(malformed)
        with self.assertRaises(FoundationPackageValidationError):
            validate_foundation_package_2_1(malformed)
        self.assertFalse(ProjectDefinitionVersion.objects.exists())
        self.assertFalse(ImportRun.objects.exists())

    def test_published_package_bootstraps_through_canonical_lifecycle_and_wraps_workspace(self):
        # Keep this wrapper round-trip focused on transport/receipt semantics;
        # exact HelpTopic binding materialization has its own bootstrap gates.
        self.manifest["help_bindings"] = []
        draft = self.create_draft()
        package = export_project_definition_package_2_1(draft)
        source = package["project_definition"]
        source.update(
            publication_status="PUBLISHED",
            is_current=True,
            validated_at="2026-08-26T00:00:00Z",
            validated_by="source-publisher",
            validation_result={"valid": True, "source": "external receipt"},
            published_at="2026-08-26T00:01:00Z",
            published_by="source-publisher",
        )
        package = seal_foundation_package_2_1(package)
        validate_foundation_package_2_1(package)
        draft.delete()

        preview = preview_foundation_package_2_1(package, project=self.project)
        self.assertEqual(preview.intended_action, "BOOTSTRAP_PUBLISHED")
        result = commit_foundation_package_2_1(
            preview,
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
            initial_workspace={
                "id": "18000000-0000-4000-8000-000000000001",
                "code": "PACKAGE-WORKSPACE",
                "version": "1.0.0",
                "name": "Package workspace",
                "is_default": True,
                "metadata": {},
            },
            locale="en",
        )
        definition = ProjectDefinitionVersion.objects.get(pk=source["id"])
        self.assertEqual(definition.publication_status, PublicationStatus.PUBLISHED)
        self.assertEqual(definition.manifest_hash, source["manifest_hash"])
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(result.workspace_id, str(ProjectWorkspace.objects.get().pk))
        receipt = ImportRun.objects.get(pk=result.receipt_id)
        self.assertEqual(receipt.selected_input["source_validated_at"], source["validated_at"])
        self.assertEqual(receipt.selected_input["source_published_at"], source["published_at"])
        service_events = AuditEvent.objects.order_by("occurred_at", "code")
        self.assertEqual(service_events.count(), 4)
        for event in service_events:
            with self.subTest(action=event.action, scope=event.scope):
                self.assertEqual(event.actor_type, AuditActorType.SYSTEM)
                self.assertEqual(event.actor_identifier, self.service.actor_identifier)
                self.assertEqual(
                    event.after["foundation_audit_context"],
                    {
                        "actor_identifier": self.service.actor_identifier,
                        "service_purpose": self.service.service_context.purpose,
                    },
                )

        wrapped = export_workspace_package_2_1(ProjectWorkspace.objects.get())
        self.assertEqual(wrapped["format_version"], FOUNDATION_PACKAGE_VERSION_2_1)
        self.assertEqual(wrapped["package_scope"], "WORKSPACE")
        self.assertEqual(wrapped["workspace_package"]["format_version"], FOUNDATION_PACKAGE_VERSION)
        self.assertEqual(
            wrapped["workspace_package"]["workspace"],
            wrapped["workspace"],
        )

        workspace = ProjectWorkspace.objects.get()
        workspace_preview = preview_foundation_package_2_1(
            wrapped,
            project=self.project,
            workspace=workspace,
            allow_nonempty=True,
        )
        self.assertEqual(workspace_preview.package_scope, "WORKSPACE")
        self.assertEqual(
            workspace_preview.intended_action,
            "IMPORT_WORKSPACE_2_0_PAYLOAD",
        )
        workspace_result = commit_foundation_package_2_1(
            workspace_preview,
            project=self.project,
            workspace=workspace,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
            allow_nonempty=True,
        )
        nested_receipt = ImportRun.objects.get(pk=workspace_result.receipt_id)
        self.assertEqual(workspace_result.package_scope, "WORKSPACE")
        self.assertEqual(nested_receipt.package_scope, ImportPackageScope.WORKSPACE)
        self.assertEqual(nested_receipt.workspace_id, workspace.pk)
        self.assertEqual(
            nested_receipt.checksum,
            wrapped["workspace_package"]["manifest"]["payload_sha256"],
        )
        self.assertEqual(
            ImportRun.objects.filter(package_scope=ImportPackageScope.WORKSPACE).count(),
            1,
        )
        workspace_import_event = AuditEvent.objects.get(entity_id=nested_receipt.pk)
        self.assertEqual(workspace_import_event.actor_type, AuditActorType.SYSTEM)
        self.assertEqual(
            workspace_import_event.actor_identifier,
            self.service.actor_identifier,
        )
        self.assertEqual(
            workspace_import_event.after["foundation_audit_context"],
            {
                "actor_identifier": self.service.actor_identifier,
                "service_purpose": self.service.service_context.purpose,
            },
        )
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_1(
                workspace_preview,
                project=self.project,
                workspace=workspace,
                principal=self.service,
                actor_identifier=self.service.actor_identifier,
                allow_nonempty=True,
            )

    def test_definition_import_failures_create_durable_failed_receipts_then_retry(self):
        source = self.create_draft()
        source_id = source.pk
        package = export_project_definition_package_2_1(source)
        source.delete()
        for stage in (
            "after_definition_import_receipt",
            "after_definition_import_audit",
        ):
            with self.subTest(stage=stage):
                outcome = attempt_foundation_import_2_1(
                    canonical_json(package).encode("utf-8"),
                    project=self.project,
                    principal=self.service,
                    actor_identifier=self.service.actor_identifier,
                    inject_failure_at=stage,
                )
                self.assertEqual(outcome.status, "FAILED")
                self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())
                self.assertFalse(AuditEvent.objects.exists())
                receipt = ImportRun.objects.get(pk=outcome.receipt_id)
                self.assertEqual(receipt.status, "FAILED")
                self.assertIsNone(receipt.definition_version_id)
                self.assertEqual(receipt.package_scope, ImportPackageScope.PROJECT_DEFINITION)
                self.assertEqual(receipt.selected_input["raw_input_kind"], "BYTES")
                self.assertTrue(receipt.selected_input["raw_input_sha256"])

        prior = list(ImportRun.objects.order_by("created_at").values("id", "status", "errors"))
        success = attempt_foundation_import_2_1(
            canonical_json(package).encode("utf-8"),
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
        )
        self.assertEqual(success.status, "COMMITTED")
        self.assertTrue(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())
        self.assertEqual(ImportRun.objects.filter(status="FAILED").count(), 2)
        self.assertEqual(ImportRun.objects.filter(status="COMMITTED").count(), 1)
        self.assertEqual(
            list(ImportRun.objects.order_by("created_at")[:2].values("id", "status", "errors")),
            prior,
        )

    def test_rejected_receipt_and_receipt_failure_never_resurrect_domain_writes(self):
        source = self.create_draft()
        source_id = source.pk
        package = export_project_definition_package_2_1(source)
        source.delete()
        raw = canonical_json(package).encode("utf-8")
        duplicate = raw.replace(b'"package_scope":"PROJECT_DEFINITION"', b'"package_scope":"PROJECT_DEFINITION","package_scope":"PROJECT_DEFINITION"')
        rejected = attempt_foundation_import_2_1(
            duplicate,
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
        )
        self.assertEqual(rejected.status, "REJECTED")
        receipt = ImportRun.objects.get(pk=rejected.receipt_id)
        self.assertEqual(receipt.status, "REJECTED")
        self.assertIn("RAW_JSON_DUPLICATE_KEY", receipt.errors[0]["code"])
        self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())

        with patch(
            "domain.services.foundation_packages._record_unsuccessful_definition_import_2_1",
            side_effect=RuntimeError("receipt persistence unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "receipt persistence unavailable"):
                attempt_foundation_import_2_1(
                    raw,
                    project=self.project,
                    principal=self.service,
                    actor_identifier=self.service.actor_identifier,
                    inject_failure_at="after_definition_import_receipt",
                )
        self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())
        self.assertEqual(ImportRun.objects.count(), 1)

    def test_rejected_receipt_does_not_echo_schema_input(self):
        source = self.create_draft()
        package = export_project_definition_package_2_1(source)
        secret_key = "SECRET_PACKAGE_MATERIAL_" + "z" * 100_000
        package["project_definition"][secret_key] = "must-not-persist"
        package = seal_foundation_package_2_1(package)

        outcome = attempt_foundation_import_2_1(
            canonical_json(package).encode("utf-8"),
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
        )

        self.assertEqual(outcome.status, "REJECTED")
        receipt = ImportRun.objects.get(pk=outcome.receipt_id)
        serialized_errors = canonical_json(receipt.errors)
        self.assertLess(len(serialized_errors), 1024)
        self.assertNotIn(secret_key, serialized_errors)
        self.assertNotIn("must-not-persist", serialized_errors)
        self.assertIn("detail_sha256", receipt.errors[0])

    def test_oversized_path_is_stream_bounded_and_receipted_by_exact_identity(self):
        raw = b"{" + b" " * (FOUNDATION_RAW_JSON_MAX_BYTES + 4096) + b"}"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized-definition-package.json"
            path.write_bytes(raw)
            outcome = attempt_foundation_import_2_1(
                path,
                project=self.project,
                principal=self.service,
                actor_identifier=self.service.actor_identifier,
            )

        self.assertEqual(outcome.status, "REJECTED")
        self.assertFalse(ProjectDefinitionVersion.objects.exists())
        receipt = ImportRun.objects.get(pk=outcome.receipt_id)
        self.assertEqual(receipt.selected_input["raw_input_kind"], "PATH_BYTES")
        self.assertEqual(
            receipt.selected_input["raw_input_name"],
            "oversized-definition-package.json",
        )
        self.assertEqual(receipt.selected_input["raw_input_byte_length"], len(raw))
        self.assertEqual(
            receipt.selected_input["raw_input_sha256"],
            hashlib.sha256(raw).hexdigest(),
        )
        self.assertEqual(receipt.errors[0]["code"], "RAW_JSON_BYTE_BUDGET_EXCEEDED")

    def test_stale_definition_attempt_is_rejected_durably_without_repair(self):
        source = self.create_draft()
        package = export_project_definition_package_2_1(source)
        changed = copy.deepcopy(self.manifest)
        changed["project"]["name"] = "Persisted stale successor bytes"
        saved = save_project_definition_draft(
            source,
            manifest=changed,
            expected_manifest_hash=source.manifest_hash,
            principal=self.editor,
        )
        outcome = attempt_foundation_import_2_1(
            canonical_json(package).encode("utf-8"),
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
        )
        self.assertEqual(outcome.status, "REJECTED")
        saved.refresh_from_db()
        self.assertEqual(saved.manifest, changed)
        self.assertEqual(ProjectDefinitionVersion.objects.count(), 1)
        receipt = ImportRun.objects.get(pk=outcome.receipt_id)
        self.assertEqual(receipt.status, "REJECTED")
        self.assertEqual(receipt.definition_version_id, saved.pk)
        self.assertEqual(
            receipt.selected_input["canonical_payload_sha256"],
            package["manifest"]["payload_sha256"],
        )

    def test_identity_rejection_receipt_binds_unambiguous_code_and_version(self):
        source = self.create_draft()
        package = export_project_definition_package_2_1(source)
        drifted_id = "17000000-0000-4000-8000-000000000099"
        package["project_definition"]["id"] = drifted_id
        package["selected_definition_id"] = drifted_id
        package = seal_foundation_package_2_1(package)

        outcome = attempt_foundation_import_2_1(
            canonical_json(package).encode("utf-8"),
            project=self.project,
            principal=self.service,
            actor_identifier=self.service.actor_identifier,
        )

        self.assertEqual(outcome.status, "REJECTED")
        self.assertEqual(ProjectDefinitionVersion.objects.count(), 1)
        persisted = ProjectDefinitionVersion.objects.get()
        self.assertEqual(persisted.pk, source.pk)
        receipt = ImportRun.objects.get(pk=outcome.receipt_id)
        self.assertEqual(receipt.status, "REJECTED")
        self.assertEqual(receipt.definition_version_id, source.pk)
        self.assertEqual(
            receipt.selected_input["source_definition_id"],
            drifted_id,
        )

    def test_every_bootstrap_stage_rolls_back_then_appends_one_failed_receipt(self):
        self.manifest["help_bindings"] = []
        source = self.create_draft()
        source_id = source.pk
        package = export_project_definition_package_2_1(source)
        package["project_definition"].update(
            publication_status="PUBLISHED",
            is_current=True,
            validated_at="2026-08-26T00:00:00Z",
            validated_by="source-publisher",
            validation_result={"valid": True, "source": "external receipt"},
            published_at="2026-08-26T00:01:00Z",
            published_by="source-publisher",
        )
        package = seal_foundation_package_2_1(package)
        source.delete()
        raw = canonical_json(package).encode("utf-8")
        stages = (
            "after_bootstrap_lock",
            "after_canonical_validation",
            "after_validation_transition",
            "after_validation_audit",
            "after_publication_transition",
            "after_initial_workspace",
            "after_workspace_help_bindings",
            "after_project_publication",
            "after_definition_publish_audit",
            "after_workspace_bootstrap_audit",
        )
        workspace = {
            "id": "18000000-0000-4000-8000-000000000099",
            "code": "FAILED-PACKAGE-WORKSPACE",
            "version": "1.0.0",
            "name": "Failed package workspace",
            "is_default": True,
            "metadata": {},
        }
        for expected_count, stage in enumerate(stages, start=1):
            with self.subTest(stage=stage):
                outcome = attempt_foundation_import_2_1(
                    raw,
                    project=self.project,
                    principal=self.service,
                    actor_identifier=self.service.actor_identifier,
                    initial_workspace=workspace,
                    locale="en",
                    inject_failure_at=stage,
                )
                self.assertEqual(outcome.status, "FAILED")
                self.assertEqual(ImportRun.objects.filter(status="FAILED").count(), expected_count)
                self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())
                self.assertFalse(ProjectWorkspace.objects.exists())
                self.assertFalse(ProjectPublication.objects.exists())
                self.assertFalse(AuditEvent.objects.exists())

    def test_legacy_constants_and_typed_dispatch_are_not_reinterpreted(self):
        self.assertEqual(FOUNDATION_PACKAGE_VERSION, "2.0.0")
        with self.assertRaises(FoundationPackageValidationError):
            validate_foundation_package_2_1(
                {
                    "format": "conflict-analysis-foundation",
                    "format_version": "2.0.0",
                }
            )


class FoundationStudioCrossPathLockOrderTests(TransactionTestCase):
    """PostgreSQL oracle for Project -> definition -> dependent-row locking."""

    reset_sequences = True

    def setUp(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.manifest = copy.deepcopy(fixture["vectors"][0]["manifest"])
        identity = self.manifest["project"]
        self.project = Project.objects.create(
            id=identity["id"],
            code=identity["code"],
            version=identity["version"],
            name="Lock-order Project",
        )
        html = "<p>Lock-order help.</p>"
        checksum = hashlib.sha256(html.encode("utf-8")).hexdigest()
        topic = HelpTopic(
            code="HELP-LOCK-ORDER",
            version="1.0.0",
            stable_key="studio.welcome",
            title="Lock-order help",
            application_scope=HelpApplicationScope.STUDIO,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="en",
            sanitized_html=html,
            content_sha256=checksum,
            publication_status=PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        topic.save(force_insert=True)
        UIHelpBinding(
            code="GLOBAL-LOCK-ORDER-HELP",
            version="1.0.0",
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            ui_key="studio.welcome",
            locale="en",
            help_topic=topic,
        ).save(force_insert=True)
        self.manifest["help_bindings"][0]["topic_sha256"] = checksum
        self.editor = StudioPrincipal.for_role(
            actor_identifier="lock-editor",
            role=StudioRole.STUDIO_EDITOR,
        )
        self.publisher = StudioPrincipal.for_role(
            actor_identifier="lock-publisher",
            role=StudioRole.STUDIO_PUBLISHER,
        )
        self.service = StudioPrincipal.service(
            actor_identifier="lock-import-service",
            purpose="Foundation 2.1 lock-order import",
            capabilities=frozenset(
                {
                    StudioCapability.DRAFT_CREATE,
                    StudioCapability.DEFINITION_VALIDATE,
                    StudioCapability.DEFINITION_PUBLISH,
                    StudioCapability.FOUNDATION_IMPORT,
                }
            ),
        )

    @staticmethod
    def _run_pair(*workers: object) -> tuple[list[str], list[Exception]]:
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        errors: list[Exception] = []
        result_lock = threading.Lock()

        def invoke(worker: object) -> None:
            close_old_connections()
            try:
                assert callable(worker)
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '20s'")
                barrier.wait(timeout=10)
                outcome = worker()
                with result_lock:
                    outcomes.append(str(outcome))
            except Exception as exc:
                with result_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=invoke, args=(worker,), daemon=True)
            for worker in workers
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        if any(thread.is_alive() for thread in threads):
            raise AssertionError("Cross-path publication threads did not terminate (deadlock).")
        return outcomes, errors

    def test_postgresql_import_initial_and_successor_paths_share_one_lock_order(self):
        if connection.vendor != "postgresql":
            self.skipTest("Cross-path lock-order oracle is PostgreSQL-only.")

        imported_source = create_project_definition_draft(
            project=self.project,
            definition_id="32000000-0000-4000-8000-000000000001",
            code="LOCK-IMPORT-INITIAL",
            version="2.0.0",
            manifest=self.manifest,
            principal=self.editor,
        )
        package = export_project_definition_package_2_1(imported_source)
        package["project_definition"].update(
            publication_status="PUBLISHED",
            is_current=True,
            validated_at="2026-08-26T00:00:00Z",
            validated_by="source-publisher",
            validation_result={"valid": True, "source": "lock-order oracle"},
            published_at="2026-08-26T00:01:00Z",
            published_by="source-publisher",
        )
        package = seal_foundation_package_2_1(package)
        imported_source.delete()
        preview = preview_foundation_package_2_1(package, project=self.project)

        canonical = create_project_definition_draft(
            project=self.project,
            definition_id="32000000-0000-4000-8000-000000000002",
            code="LOCK-CANONICAL-INITIAL",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor,
        )

        def canonical_initial() -> object:
            local = ProjectDefinitionVersion.objects.get(pk=canonical.pk)
            return bootstrap_initial_project_definition(
                definition=local,
                principal=self.publisher,
                actor_identifier=self.publisher.actor_identifier,
                workspace_spec={
                    "id": "32000000-0000-4000-8000-000000000011",
                    "code": "LOCK-CANONICAL-WORKSPACE",
                    "version": "1.0.0",
                    "name": "Canonical lock workspace",
                    "is_default": True,
                    "metadata": {},
                },
                locale="en",
            ).publication.pk

        def imported_initial() -> object:
            local_project = Project.objects.get(pk=self.project.pk)
            return commit_foundation_package_2_1(
                preview,
                project=local_project,
                principal=self.service,
                actor_identifier=self.service.actor_identifier,
                initial_workspace={
                    "id": "32000000-0000-4000-8000-000000000012",
                    "code": "LOCK-IMPORT-WORKSPACE",
                    "version": "1.0.0",
                    "name": "Imported lock workspace",
                    "is_default": True,
                    "metadata": {},
                },
                locale="en",
            ).receipt_id

        initial_outcomes, initial_errors = self._run_pair(
            canonical_initial,
            imported_initial,
        )
        self.assertEqual(len(initial_outcomes), 1)
        self.assertEqual(len(initial_errors), 1)
        self.assertIsInstance(initial_errors[0], ValidationError)
        self.assertNotIsInstance(initial_errors[0], OperationalError)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.filter(is_default=True).count(), 1)
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(is_current=True).count(),
            1,
        )

        initial_workspace = ProjectWorkspace.objects.get()
        initial_pin = (
            initial_workspace.pk,
            initial_workspace.definition_version_id,
            initial_workspace.definition_manifest_hash,
        )
        current = ProjectDefinitionVersion.objects.get(is_current=True)
        successors = []
        for index in (1, 2):
            draft = clone_project_definition_draft(
                current,
                code=f"LOCK-SUCCESSOR-{index}",
                version=f"{index + 2}.0.0",
                principal=self.editor,
            )
            successors.append(
                validate_project_definition(
                    draft,
                    actor_identifier=self.publisher.actor_identifier,
                    principal=self.publisher,
                )
            )

        def successor_worker(definition_id: object) -> object:
            local = ProjectDefinitionVersion.objects.get(pk=definition_id)
            return publish_project_definition(
                local,
                actor_identifier=self.publisher.actor_identifier,
                principal=self.publisher,
                workspace_spec=None,
                locale="en",
            ).pk

        successor_outcomes, successor_errors = self._run_pair(
            lambda: successor_worker(successors[0].pk),
            lambda: successor_worker(successors[1].pk),
        )
        self.assertEqual(len(successor_outcomes), 1)
        self.assertEqual(len(successor_errors), 1)
        self.assertIsInstance(successor_errors[0], ValidationError)
        self.assertNotIsInstance(successor_errors[0], OperationalError)
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(
            ProjectPublication.objects.filter(initial_workspace__isnull=False).count(),
            1,
        )
        self.assertEqual(
            ProjectPublication.objects.filter(initial_workspace__isnull=True).count(),
            1,
        )
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.filter(is_default=True).count(), 1)
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(is_current=True).count(),
            1,
        )
        initial_workspace.refresh_from_db()
        self.assertEqual(
            (
                initial_workspace.pk,
                initial_workspace.definition_version_id,
                initial_workspace.definition_manifest_hash,
            ),
            initial_pin,
        )
