from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone

from domain.enums import HelpApplicationScope, ImportPackageScope, PublicationStatus
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
from domain.policies import StudioCapability, StudioPrincipal, StudioRole
from domain.services.foundation_packages import (
    FOUNDATION_PACKAGE_VERSION,
    FOUNDATION_PACKAGE_VERSION_2_1,
    FoundationPackageConflictError,
    FoundationPackageValidationError,
    FoundationPackageValidationError,
    canonical_json,
    commit_foundation_package_2_1,
    export_project_definition_package_2_1,
    export_workspace_package_2_1,
    preview_foundation_package_2_1,
    seal_foundation_package_2_1,
    validate_foundation_package_2_1,
)
from domain.services.project_definitions import create_project_definition_draft


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
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_1(
                workspace_preview,
                project=self.project,
                workspace=workspace,
                principal=self.service,
                actor_identifier=self.service.actor_identifier,
                allow_nonempty=True,
            )

    def test_definition_import_receipt_and_audit_failures_roll_back_domain_and_success_receipt(self):
        source = self.create_draft()
        source_id = source.pk
        package = export_project_definition_package_2_1(source)
        source.delete()
        preview = preview_foundation_package_2_1(package, project=self.project)
        for stage in (
            "after_definition_import_receipt",
            "after_definition_import_audit",
        ):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(RuntimeError, stage):
                    commit_foundation_package_2_1(
                        preview,
                        project=self.project,
                        principal=self.service,
                        actor_identifier=self.service.actor_identifier,
                        inject_failure_at=stage,
                    )
                self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())
                self.assertFalse(ImportRun.objects.exists())
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
