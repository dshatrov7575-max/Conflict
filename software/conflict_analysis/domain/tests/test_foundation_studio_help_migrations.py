import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
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
from domain.services.help_topics import HelpTopicResolutionError, resolve_help_topic


def _manifest_hash(manifest):
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class FoundationStudioContractModelTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            code="STUDIO-CONTRACT-PROJECT",
            version="1.0.0",
            name="Studio contract project",
        )
        manifest = {}
        now = timezone.now()
        self.definition = ProjectDefinitionVersion.objects.create(
            project=self.project,
            code="STUDIO-CONTRACT-DEFINITION",
            version="1.0.0",
            is_current=True,
            publication_status=PublicationStatus.PUBLISHED,
            manifest=manifest,
            manifest_hash=_manifest_hash(manifest),
            validated_at=now,
            validated_by="owner",
            validation_result={"valid": True},
            published_at=now,
            published_by="owner",
        )
        self.workspace = ProjectWorkspace.objects.create(
            project=self.project,
            definition_version=self.definition,
            definition_manifest_hash=self.definition.manifest_hash,
            code="STUDIO-CONTRACT-WORKSPACE",
            version="1.0.0",
            name="Studio contract workspace",
            is_default=True,
        )
        html = "<p>Exact Studio help.</p>"
        self.topic = HelpTopic.objects.create(
            code="STUDIO-CONTRACT-TOPIC",
            stable_key="studio.welcome",
            version="1.0.0",
            title="Welcome",
            application_scope=HelpApplicationScope.STUDIO,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="ru-RU",
            sanitized_html=html,
            content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
            publication_status=PublicationStatus.PUBLISHED,
            published_at=now,
        )

    def test_preworkspace_help_is_exact_and_never_a_workspace_fallback(self):
        UIHelpBinding.objects.create(
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            code="STUDIO-GLOBAL-WELCOME",
            version="1.0.0",
            ui_key="studio.welcome",
            locale="ru-RU",
            help_topic=self.topic,
        )

        resolved = resolve_help_topic(
            application_scope=HelpApplicationScope.STUDIO,
            ui_key="studio.welcome",
            locale="ru-RU",
            version="1.0.0",
        )
        self.assertEqual(resolved.pk, self.topic.pk)

        for changed in (
            {"locale": "en"},
            {"version": "1.0.1"},
            {"application_scope": HelpApplicationScope.PLAYER},
            {"workspace": self.workspace},
        ):
            lookup = {
                "application_scope": HelpApplicationScope.STUDIO,
                "ui_key": "studio.welcome",
                "locale": "ru-RU",
                "version": "1.0.0",
            }
            lookup.update(changed)
            with self.assertRaises(HelpTopicResolutionError):
                resolve_help_topic(**lookup)

    def test_help_binding_rejects_scope_version_and_nonstudio_global_rows(self):
        wrong_version = UIHelpBinding(
            workspace=self.workspace,
            application_scope=HelpApplicationScope.STUDIO,
            code="STUDIO-HELP-WRONG-VERSION",
            version="2.0.0",
            ui_key="studio.welcome",
            locale="ru-RU",
            help_topic=self.topic,
        )
        with self.assertRaises(ValidationError):
            wrong_version.full_clean()

        wrong_scope = UIHelpBinding(
            workspace=self.workspace,
            application_scope=HelpApplicationScope.PLAYER,
            code="STUDIO-HELP-WRONG-SCOPE",
            version="1.0.0",
            ui_key="studio.welcome",
            locale="ru-RU",
            help_topic=self.topic,
        )
        with self.assertRaises(ValidationError):
            wrong_scope.full_clean()

        shared_html = "<p>Shared help.</p>"
        shared_topic = HelpTopic.objects.create(
            code="SHARED-CONTRACT-TOPIC",
            stable_key="shared.welcome",
            version="1.0.0",
            title="Shared welcome",
            application_scope=HelpApplicationScope.SHARED,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="ru-RU",
            sanitized_html=shared_html,
            content_sha256=hashlib.sha256(shared_html.encode("utf-8")).hexdigest(),
            publication_status=PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        global_shared = UIHelpBinding(
            workspace=None,
            application_scope=HelpApplicationScope.SHARED,
            code="SHARED-GLOBAL-WELCOME",
            version="1.0.0",
            ui_key="shared.welcome",
            locale="ru-RU",
            help_topic=shared_topic,
        )
        with self.assertRaises(ValidationError):
            global_shared.full_clean()

    def test_audit_scopes_are_exclusive_and_publication_pin_is_exact(self):
        definition_event = AuditEvent.objects.create(
            project=self.project,
            workspace=None,
            definition_version=self.definition,
            scope=AuditScope.DEFINITION,
            code="STUDIO-DEFINITION-AUDIT",
            version="1.0.0",
            action=AuditAction.PUBLISH,
            actor_type=AuditActorType.HUMAN,
            actor_identifier="owner",
            entity_type="PROJECT_DEFINITION_VERSION",
            entity_id=self.definition.id,
        )
        self.assertIsNone(definition_event.workspace_id)

        invalid = AuditEvent(
            project=self.project,
            workspace=self.workspace,
            definition_version=self.definition,
            scope=AuditScope.DEFINITION,
            code="STUDIO-MIXED-AUDIT",
            version="1.0.0",
            action=AuditAction.BOOTSTRAP,
            actor_type=AuditActorType.HUMAN,
            actor_identifier="owner",
            entity_type="PROJECT_DEFINITION_VERSION",
            entity_id=self.definition.id,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

        publication = ProjectPublication.objects.create(
            project=self.project,
            definition_version=self.definition,
            initial_workspace=self.workspace,
            code="STUDIO-INITIAL-PUBLICATION",
            version="1.0.0",
            locale="ru-RU",
            actor_identifier="owner",
            validation_result={"valid": True},
        )
        self.assertEqual(publication.initial_workspace_id, self.workspace.id)

    def test_import_receipt_boundary_hydrates_legacy_workspace_identity(self):
        receipt = ImportRun.objects.create(
            workspace=self.workspace,
            code="STUDIO-WORKSPACE-IMPORT",
            version="1.0.0",
            package_format="CONFLICT_ANALYSIS_FOUNDATION",
            package_id="STUDIO-WORKSPACE-PACKAGE",
            package_version="2.0.0",
            schema_version="2.0.0",
            template_version="1.0.0",
            method_version="1.0.0",
            ontology_version="1.0.0",
            dataset_version="1.0.0",
            checksum="a" * 64,
            adapter="test",
            status=ImportRunStatus.PREVIEWED,
            actor_identifier="owner",
        )
        self.assertEqual(receipt.package_scope, ImportPackageScope.WORKSPACE)
        self.assertEqual(receipt.project_id, self.project.id)
        self.assertEqual(receipt.definition_version_id, self.definition.id)


class FoundationStudioContractMigrationTests(TransactionTestCase):
    migrate_from = [("domain", "0012_xlsx_metadata_contract")]
    migrate_to = [("domain", "0015_foundation_studio_contract_constraints")]

    def _restore_leaf_migrations(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_existing_receipts_and_bindings_gain_exact_boundaries(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self._restore_leaf_migrations)
        apps = executor.loader.project_state(self.migrate_from).apps

        Project = apps.get_model("domain", "Project")
        Definition = apps.get_model("domain", "ProjectDefinitionVersion")
        Workspace = apps.get_model("domain", "ProjectWorkspace")
        Topic = apps.get_model("domain", "HelpTopic")
        Binding = apps.get_model("domain", "UIHelpBinding")
        Receipt = apps.get_model("domain", "ImportRun")
        Audit = apps.get_model("domain", "AuditEvent")

        project = Project.objects.create(
            code="MIGRATION-STUDIO-PROJECT",
            version="1.0.0",
            name="Migration Studio project",
        )
        now = timezone.now()
        manifest = {}
        definition = Definition.objects.create(
            project=project,
            code="MIGRATION-STUDIO-DEFINITION",
            version="1.0.0",
            is_current=True,
            publication_status="PUBLISHED",
            manifest=manifest,
            manifest_hash=_manifest_hash(manifest),
            validated_at=now,
            validated_by="migration-owner",
            validation_result={"valid": True},
            published_at=now,
            published_by="migration-owner",
        )
        workspace = Workspace.objects.create(
            project=project,
            definition_version=definition,
            definition_manifest_hash=definition.manifest_hash,
            code="MIGRATION-STUDIO-WORKSPACE",
            version="1.0.0",
            name="Migration Studio workspace",
            is_default=True,
        )
        html = "<p>Legacy exact help.</p>"
        topic = Topic.objects.create(
            code="MIGRATION-STUDIO-TOPIC",
            stable_key="studio.legacy",
            version="1.0.0",
            title="Legacy exact help",
            application_scope="STUDIO",
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="ru-RU",
            sanitized_html=html,
            content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
            publication_status="PUBLISHED",
            published_at=now,
        )
        binding = Binding.objects.create(
            workspace=workspace,
            help_topic=topic,
            code="MIGRATION-STUDIO-BINDING",
            version="1.0.0",
            ui_key="studio.legacy",
            locale="ru-RU",
        )
        receipt = Receipt.objects.create(
            workspace=workspace,
            code="MIGRATION-STUDIO-RECEIPT",
            version="1.0.0",
            package_format="CONFLICT_ANALYSIS_FOUNDATION",
            package_id="MIGRATION-STUDIO-PACKAGE",
            package_version="2.0.0",
            schema_version="2.0.0",
            template_version="1.0.0",
            method_version="1.0.0",
            ontology_version="1.0.0",
            dataset_version="1.0.0",
            checksum="b" * 64,
            adapter="legacy-test",
            selected_input={"preserve": True},
            status="PREVIEWED",
            actor_identifier="migration-owner",
        )
        audit = Audit.objects.create(
            project=project,
            workspace=workspace,
            code="MIGRATION-STUDIO-AUDIT",
            version="1.0.0",
            action="IMPORT",
            actor_type="HUMAN",
            actor_identifier="migration-owner",
            entity_type="IMPORT_RUN",
            entity_id=receipt.id,
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps

        migrated_binding = apps.get_model("domain", "UIHelpBinding").objects.get(
            pk=binding.id
        )
        migrated_receipt = apps.get_model("domain", "ImportRun").objects.get(
            pk=receipt.id
        )
        migrated_audit = apps.get_model("domain", "AuditEvent").objects.get(
            pk=audit.id
        )
        self.assertEqual(migrated_binding.application_scope, "STUDIO")
        self.assertEqual(migrated_binding.workspace_id, workspace.id)
        self.assertEqual(migrated_receipt.project_id, project.id)
        self.assertEqual(migrated_receipt.definition_version_id, definition.id)
        self.assertEqual(migrated_receipt.package_scope, "WORKSPACE")
        self.assertEqual(migrated_receipt.checksum, "b" * 64)
        self.assertEqual(migrated_receipt.selected_input, {"preserve": True})
        self.assertEqual(migrated_audit.scope, "WORKSPACE")
        self.assertEqual(migrated_audit.workspace_id, workspace.id)
        self.assertIsNone(migrated_audit.definition_version_id)
