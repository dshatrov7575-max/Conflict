from __future__ import annotations

import copy
import hashlib
import threading

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from domain.enums import (
    AuditAction,
    AuditActorType,
    AuditScope,
    HelpApplicationScope,
    ImportPackageScope,
    ImportRunStatus,
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
    bootstrap_initial_project_definition,
    publish_project_definition,
    validate_project_definition,
)
from domain.services.project_definitions import (
    clone_project_definition_draft,
    create_project_definition_draft,
)
from domain.tests.test_foundation_studio_bootstrap_auth import (
    FoundationStudioBootstrapMixin,
)


def _legacy_manifest_hash(manifest: dict) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class FoundationStudioP0PersistenceIntegrityTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()

    def _bootstrap(self, *, code: str = "P0-INTEGRITY-INITIAL"):
        return bootstrap_initial_project_definition(
            definition=self.draft(code=code),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )

    def test_typed_definition_model_and_manager_paths_cannot_forge_lifecycle(self):
        direct = ProjectDefinitionVersion(
            project=self.project,
            code="P0-DIRECT-TYPED",
            version="2.0.0",
            manifest=copy.deepcopy(self.manifest),
        )
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            direct.save(force_insert=True)
        self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=direct.pk).exists())
        with self.assertRaises(ValidationError):
            ProjectDefinitionVersion._base_manager.bulk_create([direct])

        forged_bulk = ProjectDefinitionVersion(
            project=self.project,
            code="P0-BULK-FORGED",
            version="3.0.0",
            publication_status=PublicationStatus.PUBLISHED,
            manifest=copy.deepcopy(self.manifest),
            manifest_hash="f" * 64,
            validated_at=timezone.now(),
            validated_by="caller",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="caller",
            is_current=True,
        )
        for conflict_kwargs in (
            {},
            {"ignore_conflicts": True},
            {
                "update_conflicts": True,
                "update_fields": ["manifest"],
                "unique_fields": ["id"],
            },
        ):
            with self.subTest(conflict_kwargs=conflict_kwargs):
                with self.assertRaises(ValidationError):
                    ProjectDefinitionVersion.objects.bulk_create(
                        [forged_bulk],
                        **conflict_kwargs,
                    )
                self.assertFalse(
                    ProjectDefinitionVersion.objects.filter(pk=forged_bulk.pk).exists()
                )

        draft = create_project_definition_draft(
            project=self.project,
            code="P0-SERVICE-DRAFT",
            version="4.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        draft.publication_status = PublicationStatus.VALIDATED
        draft.validated_at = timezone.now()
        draft.validated_by = "caller"
        draft.validation_result = {"valid": True}
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            draft.save()
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            ProjectDefinitionVersion.objects.filter(pk=draft.pk).update(
                is_current=False
            )
        draft.refresh_from_db()
        self.assertEqual(draft.publication_status, PublicationStatus.DRAFT)
        self.assertEqual(draft.validation_result, {})

    def test_workspace_save_and_bulk_recheck_published_project_and_hash(self):
        draft = self.draft(code="P0-WORKSPACE-DRAFT-PIN")
        draft_pin = ProjectWorkspace(
            project=self.project,
            definition_version=draft,
            definition_manifest_hash=draft.manifest_hash,
            code="P0-DRAFT-PIN",
            version="1.0.0",
            name="Invalid DRAFT pin",
        )
        with self.assertRaises(ValidationError):
            draft_pin.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([draft_pin])
        with self.assertRaises(ValidationError):
            ProjectWorkspace._base_manager.bulk_create([draft_pin])
        self.assertFalse(ProjectWorkspace.objects.filter(pk=draft_pin.pk).exists())

        result = bootstrap_initial_project_definition(
            definition=draft,
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        stale_hash = ProjectWorkspace(
            project=self.project,
            definition_version=result.definition,
            definition_manifest_hash="0" * 64,
            code="P0-STALE-HASH",
            version="1.0.0",
            name="Invalid stale checksum",
        )
        with self.assertRaises(ValidationError):
            stale_hash.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([stale_hash])

        foreign_project = Project.objects.create(
            code="P0-FOREIGN-PROJECT",
            version="1.0.0",
            name="Foreign project",
        )
        foreign_manifest = {"legacy": "published-definition"}
        foreign_definition = ProjectDefinitionVersion.objects.create(
            project=foreign_project,
            code="P0-FOREIGN-DEFINITION",
            version="1.0.0",
            publication_status=PublicationStatus.PUBLISHED,
            manifest=foreign_manifest,
            manifest_hash=_legacy_manifest_hash(foreign_manifest),
            validated_at=timezone.now(),
            validated_by="legacy",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="legacy",
            is_current=True,
        )
        foreign_pin = ProjectWorkspace(
            project=self.project,
            definition_version=foreign_definition,
            definition_manifest_hash=foreign_definition.manifest_hash,
            code="P0-FOREIGN-PIN",
            version="1.0.0",
            name="Invalid cross-project pin",
        )
        with self.assertRaises(ValidationError):
            foreign_pin.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([foreign_pin])
        with self.assertRaisesRegex(ValidationError, "project/definition pin"):
            ProjectWorkspace.objects.filter(pk=result.workspace.pk).update(
                project=foreign_project
            )
        result.workspace.project = foreign_project
        with self.assertRaisesRegex(ValidationError, "project/definition pin"):
            ProjectWorkspace.objects.bulk_update([result.workspace], ["project"])
        result.workspace.refresh_from_db()
        self.assertEqual(str(result.workspace.project_id), str(self.project.pk))

        duplicate_default = ProjectWorkspace(
            project=self.project,
            definition_version=result.definition,
            definition_manifest_hash=result.definition.manifest_hash,
            code="P0-SECOND-DEFAULT",
            version="1.0.0",
            name="Second default",
            is_default=True,
        )
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([duplicate_default])
        with self.assertRaisesRegex(ValidationError, "identity conflicts"):
            ProjectWorkspace.objects.bulk_create(
                [duplicate_default],
                ignore_conflicts=True,
            )
        self.assertEqual(ProjectWorkspace.objects.count(), 1)

    def test_publication_direct_and_bulk_paths_cannot_forge_typed_receipts(self):
        result = self._bootstrap()
        forged = ProjectPublication(
            project=self.project,
            definition_version=result.definition,
            initial_workspace=None,
            code="P0-FORGED-PUBLICATION",
            version="1.0.0",
            locale="ru",
            actor_identifier="caller",
            validation_result=result.definition.validation_result,
        )
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            forged.save(force_insert=True)
        with self.assertRaisesRegex(ValidationError, "canonical Studio publication service"):
            ProjectPublication.objects.bulk_create([forged])
        with self.assertRaisesRegex(ValidationError, "canonical Studio publication service"):
            ProjectPublication._base_manager.bulk_create([forged])
        with self.assertRaisesRegex(ValidationError, "identity conflicts"):
            ProjectPublication.objects.bulk_create([forged], ignore_conflicts=True)
        self.assertEqual(ProjectPublication.objects.count(), 1)

        other_project = Project.objects.create(
            code="P0-PUBLICATION-FOREIGN",
            version="1.0.0",
            name="Other project",
        )
        foreign_manifest = {"legacy": "foreign-publication-definition"}
        foreign_definition = ProjectDefinitionVersion.objects.create(
            project=other_project,
            code="P0-PUBLICATION-FOREIGN-DEFINITION",
            version="1.0.0",
            publication_status=PublicationStatus.PUBLISHED,
            manifest=foreign_manifest,
            manifest_hash=_legacy_manifest_hash(foreign_manifest),
            validated_at=timezone.now(),
            validated_by="legacy",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="legacy",
            is_current=True,
        )
        foreign_workspace = ProjectWorkspace.objects.create(
            project=other_project,
            definition_version=foreign_definition,
            definition_manifest_hash=foreign_definition.manifest_hash,
            code="P0-MISMATCHED-INITIAL",
            version="1.0.0",
            name="Mismatched initial",
            is_default=True,
        )
        mismatched_publication = ProjectPublication(
            project=self.project,
            definition_version=result.definition,
            initial_workspace=foreign_workspace,
            code="P0-MISMATCHED-PUBLICATION",
            version="1.0.0",
            locale="ru",
            actor_identifier="caller",
            validation_result=result.definition.validation_result,
        )
        with self.assertRaises(ValidationError):
            mismatched_publication.full_clean()
        with self.assertRaises(ValidationError):
            mismatched_publication.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectPublication.objects.bulk_create([mismatched_publication])

    def test_scoped_immutable_models_reject_bulk_bypass_and_conflict_flags(self):
        result = self._bootstrap(code="P0-SCOPED-INITIAL")
        workspace = result.workspace
        definition = result.definition

        invalid_audits = (
            AuditEvent(
                project=self.project,
                workspace=workspace,
                definition_version=definition,
                scope=AuditScope.DEFINITION,
                code="P0-AUDIT-DUAL",
                version="1.0.0",
                action=AuditAction.PUBLISH,
                actor_type=AuditActorType.HUMAN,
                actor_identifier="caller",
                entity_type="PROJECT_DEFINITION_VERSION",
                entity_id=definition.pk,
            ),
            AuditEvent(
                project=self.project,
                workspace=None,
                definition_version=None,
                scope=AuditScope.DEFINITION,
                code="P0-AUDIT-ZERO",
                version="1.0.0",
                action=AuditAction.PUBLISH,
                actor_type=AuditActorType.HUMAN,
                actor_identifier="caller",
                entity_type="PROJECT_DEFINITION_VERSION",
                entity_id=definition.pk,
            ),
        )
        for event in invalid_audits:
            with self.subTest(code=event.code):
                with self.assertRaises(ValidationError):
                    event.save(force_insert=True)
                with self.assertRaises(ValidationError):
                    AuditEvent.objects.bulk_create([event])
                with self.assertRaises(ValidationError):
                    AuditEvent._base_manager.bulk_create([event])
                self.assertFalse(AuditEvent.objects.filter(pk=event.pk).exists())

        duplicate_binding = UIHelpBinding(
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            code="P0-DUPLICATE-GLOBAL-HELP",
            version="1.0.0",
            ui_key="studio.welcome",
            locale="en",
            help_topic=self.topic,
        )
        with self.assertRaises(ValidationError):
            duplicate_binding.save(force_insert=True)
        with self.assertRaises(ValidationError):
            UIHelpBinding.objects.bulk_create([duplicate_binding])
        with self.assertRaises(ValidationError):
            UIHelpBinding._base_manager.bulk_create([duplicate_binding])

        player_html = "<p>Player-only help.</p>"
        player_topic = HelpTopic(
            code="P0-PLAYER-HELP",
            version="1.0.0",
            stable_key="player.only",
            title="Player help",
            application_scope=HelpApplicationScope.PLAYER,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="en",
            sanitized_html=player_html,
            content_sha256=hashlib.sha256(player_html.encode("utf-8")).hexdigest(),
            publication_status=PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        player_topic.save(force_insert=True)
        illegal_global_binding = UIHelpBinding(
            workspace=None,
            application_scope=HelpApplicationScope.PLAYER,
            code="P0-ILLEGAL-GLOBAL-HELP",
            version="1.0.0",
            ui_key="player.only",
            locale="en",
            help_topic=player_topic,
        )
        with self.assertRaises(ValidationError):
            illegal_global_binding.save(force_insert=True)
        with self.assertRaises(ValidationError):
            UIHelpBinding.objects.bulk_create([illegal_global_binding])

        invalid_receipt = ImportRun(
            project=self.project,
            workspace=workspace,
            definition_version=definition,
            package_scope=ImportPackageScope.PROJECT_DEFINITION,
            code="P0-ILLEGAL-DEFINITION-RECEIPT",
            version="2.1.0",
            package_format="conflict-analysis-foundation",
            package_id="P0-ILLEGAL-PACKAGE",
            package_version="2.1.0",
            schema_version="2.1.0",
            template_version="1.0.0",
            method_version="PROJECT_DEFINITION_MANIFEST_VALIDATION_V1",
            ontology_version="1.0.0",
            dataset_version="1.0.0",
            checksum="a" * 64,
            adapter="json",
            status=ImportRunStatus.REJECTED,
            actor_identifier="caller",
        )
        with self.assertRaises(ValidationError):
            invalid_receipt.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ImportRun.objects.bulk_create([invalid_receipt])
        with self.assertRaises(ValidationError):
            ImportRun._base_manager.bulk_create([invalid_receipt])

        existing_audit = AuditEvent.objects.filter(scope=AuditScope.DEFINITION).first()
        existing_binding = UIHelpBinding.objects.filter(workspace__isnull=True).first()
        committed_receipt = ImportRun.objects.create(
            project=self.project,
            workspace=None,
            definition_version=definition,
            package_scope=ImportPackageScope.PROJECT_DEFINITION,
            code="P0-EXISTING-DEFINITION-RECEIPT",
            version="2.1.0",
            package_format="conflict-analysis-foundation",
            package_id="P0-EXISTING-PACKAGE",
            package_version="2.1.0",
            schema_version="2.1.0",
            template_version="1.0.0",
            method_version="PROJECT_DEFINITION_MANIFEST_VALIDATION_V1",
            ontology_version="1.0.0",
            dataset_version="1.0.0",
            checksum="b" * 64,
            adapter="json",
            status=ImportRunStatus.COMMITTED,
            actor_identifier="service",
            committed_at=timezone.now(),
        )
        for model, row in (
            (AuditEvent, existing_audit),
            (UIHelpBinding, existing_binding),
            (ImportRun, committed_receipt),
        ):
            assert row is not None
            with self.subTest(model=model.__name__, operation="ignore"):
                with self.assertRaisesRegex(ValidationError, "identity conflicts"):
                    model.objects.bulk_create([row], ignore_conflicts=True)
            with self.subTest(model=model.__name__, operation="update_conflicts"):
                with self.assertRaisesRegex(ValidationError, "identity conflicts"):
                    model.objects.bulk_create(
                        [row],
                        update_conflicts=True,
                        update_fields=["version"],
                        unique_fields=["id"],
                    )
            with self.subTest(model=model.__name__, operation="update"):
                with self.assertRaisesRegex(ValidationError, "append-only"):
                    model.objects.filter(pk=row.pk).update(version="9.9.9")


class FoundationStudioTypedSuccessorPublicationTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()
        self.initial = bootstrap_initial_project_definition(
            definition=self.draft(code="P0-SUCCESSOR-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )

    def _validated_successor(self, *, code: str, version: str):
        draft = clone_project_definition_draft(
            self.initial.definition,
            code=code,
            version=version,
            principal=self.editor(),
        )
        return validate_project_definition(
            draft,
            actor_identifier="publisher",
            principal=self.publisher(),
        )

    def test_successor_has_one_ordinary_receipt_and_preserves_old_workspace_pin(self):
        old_workspace_id = self.initial.workspace.pk
        old_definition_id = self.initial.workspace.definition_version_id
        old_hash = self.initial.workspace.definition_manifest_hash
        old_binding_ids = tuple(
            UIHelpBinding.objects.filter(workspace=self.initial.workspace)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        old_workspace_audit_count = AuditEvent.objects.filter(
            scope=AuditScope.WORKSPACE
        ).count()
        successor = self._validated_successor(
            code="P0-SUCCESSOR-V2",
            version="2.0.0",
        )

        publication = publish_project_definition(
            successor,
            actor_identifier="publisher",
            principal=self.publisher(),
            workspace_spec=None,
            locale="en",
        )
        self.assertIsNone(publication.initial_workspace_id)
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(
            ProjectPublication.objects.filter(
                definition_version=successor
            ).count(),
            1,
        )
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.initial.workspace.refresh_from_db()
        self.initial.definition.refresh_from_db()
        successor.refresh_from_db()
        self.assertEqual(self.initial.workspace.pk, old_workspace_id)
        self.assertEqual(self.initial.workspace.definition_version_id, old_definition_id)
        self.assertEqual(self.initial.workspace.definition_manifest_hash, old_hash)
        self.assertEqual(
            tuple(
                UIHelpBinding.objects.filter(workspace=self.initial.workspace)
                .order_by("pk")
                .values_list("pk", flat=True)
            ),
            old_binding_ids,
        )
        self.assertEqual(
            AuditEvent.objects.filter(scope=AuditScope.WORKSPACE).count(),
            old_workspace_audit_count,
        )
        self.assertFalse(self.initial.definition.is_current)
        self.assertTrue(successor.is_current)

        with self.assertRaises(ValidationError):
            publish_project_definition(
                successor,
                actor_identifier="publisher",
                principal=self.publisher(),
                workspace_spec=None,
                locale="en",
            )
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)

    def test_successor_rejects_workspace_recreation_and_noncurrent_lineage(self):
        successor = self._validated_successor(
            code="P0-SUCCESSOR-WORKSPACE-REJECT",
            version="2.0.0",
        )
        with self.assertRaises(ValidationError):
            publish_project_definition(
                successor,
                actor_identifier="publisher",
                principal=self.publisher(),
                workspace_spec={
                    **self.workspace_spec(),
                    "id": "26000000-0000-4000-8000-000000000001",
                    "code": "P0-SECOND-INITIAL",
                },
                locale="en",
            )
        successor.refresh_from_db()
        self.assertEqual(successor.publication_status, PublicationStatus.VALIDATED)
        self.assertEqual(ProjectPublication.objects.count(), 1)

        good_publication = publish_project_definition(
            successor,
            actor_identifier="publisher",
            principal=self.publisher(),
            workspace_spec=None,
            locale="en",
        )
        self.assertIsNone(good_publication.initial_workspace_id)

        stale_lineage = create_project_definition_draft(
            project=self.project,
            code="P0-STALE-LINEAGE",
            version="3.0.0",
            manifest=self.manifest,
            supersedes=self.initial.definition,
            principal=self.editor(),
        )
        stale_lineage = validate_project_definition(
            stale_lineage,
            actor_identifier="publisher",
            principal=self.publisher(),
        )
        with self.assertRaisesRegex(ValidationError, "exact current published"):
            publish_project_definition(
                stale_lineage,
                actor_identifier="publisher",
                principal=self.publisher(),
                workspace_spec=None,
                locale="en",
            )
        self.assertEqual(ProjectPublication.objects.count(), 2)

    def test_successor_failure_stages_roll_back_transition_receipt_and_audit(self):
        successor = self._validated_successor(
            code="P0-SUCCESSOR-ROLLBACK",
            version="2.0.0",
        )
        initial_audits = AuditEvent.objects.count()
        for stage in (
            "after_publication_transition",
            "after_project_publication",
            "after_definition_publish_audit",
        ):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(RuntimeError, stage):
                    publish_project_definition(
                        successor,
                        actor_identifier="publisher",
                        principal=self.publisher(),
                        workspace_spec=None,
                        locale="en",
                        inject_failure_at=stage,
                    )
                successor.refresh_from_db()
                self.initial.definition.refresh_from_db()
                self.assertEqual(
                    successor.publication_status,
                    PublicationStatus.VALIDATED,
                )
                self.assertFalse(successor.is_current)
                self.assertTrue(self.initial.definition.is_current)
                self.assertEqual(ProjectPublication.objects.count(), 1)
                self.assertEqual(ProjectWorkspace.objects.count(), 1)
                self.assertEqual(AuditEvent.objects.count(), initial_audits)


class FoundationStudioSuccessorConcurrencyTests(
    FoundationStudioBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self) -> None:
        self.make_contract()

    def test_postgresql_competing_successors_have_one_winner_and_preserve_old_pin(self):
        if connection.vendor != "postgresql":
            self.skipTest("Typed successor race gate is PostgreSQL-only.")
        initial = bootstrap_initial_project_definition(
            definition=self.draft(code="P0-RACE-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        old_pin = (
            initial.workspace.pk,
            initial.workspace.definition_version_id,
            initial.workspace.definition_manifest_hash,
        )
        successor_ids = []
        for index in (1, 2):
            draft = clone_project_definition_draft(
                initial.definition,
                code=f"P0-RACE-SUCCESSOR-{index}",
                version=f"{index + 1}.0.0",
                principal=self.editor(),
            )
            validated = validate_project_definition(
                draft,
                actor_identifier="publisher",
                principal=self.publisher(),
            )
            successor_ids.append(validated.pk)

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        errors: list[Exception] = []
        outcome_lock = threading.Lock()

        def worker(definition_id) -> None:
            close_old_connections()
            try:
                local = ProjectDefinitionVersion.objects.get(pk=definition_id)
                barrier.wait(timeout=10)
                publication = publish_project_definition(
                    local,
                    actor_identifier="publisher",
                    principal=self.publisher(),
                    workspace_spec=None,
                    locale="en",
                )
                with outcome_lock:
                    outcomes.append(str(publication.pk))
            except Exception as exc:
                with outcome_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=worker, args=(definition_id,))
            for definition_id in successor_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValidationError)
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        initial.workspace.refresh_from_db()
        self.assertEqual(
            (
                initial.workspace.pk,
                initial.workspace.definition_version_id,
                initial.workspace.definition_manifest_hash,
            ),
            old_pin,
        )
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(is_current=True).count(),
            1,
        )
