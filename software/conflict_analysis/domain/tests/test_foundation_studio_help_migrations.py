import hashlib
import importlib
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


class FoundationStudioContractReverseMigrationTests(TransactionTestCase):
    migrate_from = [("domain", "0012_xlsx_metadata_contract")]
    migrate_to = [("domain", "0015_foundation_studio_contract_constraints")]
    guarded_model_names = (
        "Project",
        "ProjectDefinitionVersion",
        "ProjectWorkspace",
        "ProjectPublication",
        "HelpTopic",
        "UIHelpBinding",
        "ImportRun",
        "AuditEvent",
    )
    guarded_schema_model_names = (
        "AuditEvent",
        "UIHelpBinding",
        "ProjectPublication",
        "ImportRun",
    )

    def _restore_leaf_migrations(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _contract_apps(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.addCleanup(self._restore_leaf_migrations)
        return executor.loader.project_state(self.migrate_to).apps

    def _seed_contract_core(self, apps):
        Project = apps.get_model("domain", "Project")
        Definition = apps.get_model("domain", "ProjectDefinitionVersion")
        Workspace = apps.get_model("domain", "ProjectWorkspace")
        Topic = apps.get_model("domain", "HelpTopic")

        project = Project.objects.create(
            code="REVERSE-GUARD-PROJECT",
            version="1.0.0",
            name="Reverse guard project",
        )
        now = timezone.now()
        manifest = {}
        definition = Definition.objects.create(
            project=project,
            code="REVERSE-GUARD-DEFINITION",
            version="1.0.0",
            is_current=True,
            publication_status="PUBLISHED",
            manifest=manifest,
            manifest_hash=_manifest_hash(manifest),
            validated_at=now,
            validated_by="reverse-guard-owner",
            validation_result={"valid": True},
            published_at=now,
            published_by="reverse-guard-owner",
        )
        workspace = Workspace.objects.create(
            project=project,
            definition_version=definition,
            definition_manifest_hash=definition.manifest_hash,
            code="REVERSE-GUARD-WORKSPACE",
            version="1.0.0",
            name="Reverse guard workspace",
            is_default=True,
        )
        html = "<p>Reverse guard help.</p>"
        topic = Topic.objects.create(
            code="REVERSE-GUARD-TOPIC",
            stable_key="studio.reverse-guard",
            version="1.0.0",
            title="Reverse guard help",
            application_scope="STUDIO",
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="ru-RU",
            sanitized_html=html,
            content_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
            publication_status="PUBLISHED",
            published_at=now,
        )
        return {
            "project": project,
            "definition": definition,
            "workspace": workspace,
            "topic": topic,
        }

    def _create_import_run(self, apps, core, *, package_scope, workspace):
        ImportRun = apps.get_model("domain", "ImportRun")
        suffix = "WORKSPACE" if workspace is not None else "DEFINITION"
        return ImportRun.objects.create(
            project=core["project"],
            workspace=workspace,
            definition_version=core["definition"],
            package_scope=package_scope,
            code=f"REVERSE-GUARD-{suffix}-IMPORT",
            version="1.0.0",
            package_format="CONFLICT_ANALYSIS_FOUNDATION",
            package_id=f"REVERSE-GUARD-{suffix}-PACKAGE",
            package_version="2.1.0",
            schema_version="2.1.0",
            template_version="1.0.0",
            method_version="1.0.0",
            ontology_version="1.0.0",
            dataset_version="1.0.0",
            checksum=("c" if workspace is not None else "d") * 64,
            adapter="reverse-guard-test",
            selected_input={"preserve": True},
            status="PREVIEWED",
            actor_identifier="reverse-guard-owner",
        )

    def _seed_legacy_compatible_rows(self, apps, core):
        Binding = apps.get_model("domain", "UIHelpBinding")
        Publication = apps.get_model("domain", "ProjectPublication")
        Audit = apps.get_model("domain", "AuditEvent")

        binding = Binding.objects.create(
            workspace=core["workspace"],
            application_scope="STUDIO",
            help_topic=core["topic"],
            code="REVERSE-GUARD-WORKSPACE-HELP",
            version="1.0.0",
            ui_key="studio.reverse-guard",
            locale="ru-RU",
        )
        publication = Publication.objects.create(
            project=core["project"],
            definition_version=core["definition"],
            initial_workspace=None,
            code="REVERSE-GUARD-LEGACY-PUBLICATION",
            version="1.0.0",
            locale="ru-RU",
            actor_identifier="reverse-guard-owner",
            validation_result={"valid": True},
        )
        receipt = self._create_import_run(
            apps,
            core,
            package_scope="WORKSPACE",
            workspace=core["workspace"],
        )
        audit = Audit.objects.create(
            project=core["project"],
            workspace=core["workspace"],
            definition_version=None,
            scope="WORKSPACE",
            code="REVERSE-GUARD-WORKSPACE-AUDIT",
            version="1.0.0",
            action="IMPORT",
            actor_type="HUMAN",
            actor_identifier="reverse-guard-owner",
            entity_type="IMPORT_RUN",
            entity_id=receipt.id,
        )
        return {
            "UIHelpBinding": binding.id,
            "ProjectPublication": publication.id,
            "ImportRun": receipt.id,
            "AuditEvent": audit.id,
        }

    def _seed_blocker(self, apps, core, blocker):
        if blocker == "definition_audit":
            Audit = apps.get_model("domain", "AuditEvent")
            return Audit.objects.create(
                project=core["project"],
                workspace=None,
                definition_version=core["definition"],
                scope="DEFINITION",
                code="REVERSE-GUARD-DEFINITION-AUDIT",
                version="1.0.0",
                action="PUBLISH",
                actor_type="HUMAN",
                actor_identifier="reverse-guard-owner",
                entity_type="PROJECT_DEFINITION_VERSION",
                entity_id=core["definition"].id,
            )
        if blocker == "global_help_binding":
            Binding = apps.get_model("domain", "UIHelpBinding")
            return Binding.objects.create(
                workspace=None,
                application_scope="STUDIO",
                help_topic=core["topic"],
                code="REVERSE-GUARD-GLOBAL-HELP",
                version="1.0.0",
                ui_key="studio.reverse-guard",
                locale="ru-RU",
            )
        if blocker == "initial_workspace_publication":
            Publication = apps.get_model("domain", "ProjectPublication")
            return Publication.objects.create(
                project=core["project"],
                definition_version=core["definition"],
                initial_workspace=core["workspace"],
                code="REVERSE-GUARD-BOOTSTRAP-PUBLICATION",
                version="1.0.0",
                locale="ru-RU",
                actor_identifier="reverse-guard-owner",
                validation_result={"valid": True},
            )
        if blocker == "project_definition_import":
            return self._create_import_run(
                apps,
                core,
                package_scope="PROJECT_DEFINITION",
                workspace=None,
            )
        raise AssertionError(f"Unknown reverse blocker: {blocker}")

    def _row_snapshot(self, apps):
        return {
            model_name: list(
                apps.get_model("domain", model_name)
                .objects.order_by("pk")
                .values()
            )
            for model_name in self.guarded_model_names
        }

    @staticmethod
    def _constraint_signature(details):
        foreign_key = details.get("foreign_key")
        if foreign_key is not None:
            foreign_key = tuple(foreign_key)
        return {
            "columns": tuple(details.get("columns") or ()),
            "primary_key": bool(details.get("primary_key")),
            "unique": bool(details.get("unique")),
            "foreign_key": foreign_key,
            "check": bool(details.get("check")),
            "index": bool(details.get("index")),
            "orders": tuple(details.get("orders") or ()),
            "type": details.get("type"),
        }

    def _schema_snapshot(self, apps):
        snapshot = {}
        with connection.cursor() as cursor:
            for model_name in self.guarded_schema_model_names:
                model = apps.get_model("domain", model_name)
                table_name = model._meta.db_table
                description = connection.introspection.get_table_description(
                    cursor, table_name
                )
                constraints = connection.introspection.get_constraints(
                    cursor, table_name
                )
                snapshot[table_name] = {
                    "columns": tuple(
                        (field.name, field.null_ok) for field in description
                    ),
                    "constraints": {
                        name: self._constraint_signature(details)
                        for name, details in sorted(constraints.items())
                    },
                }
        return snapshot

    def _assert_reverse_blocked(self, blocker, expected_message):
        apps = self._contract_apps()
        core = self._seed_contract_core(apps)
        self._seed_blocker(apps, core, blocker)
        rows_before = self._row_snapshot(apps)
        schema_before = self._schema_snapshot(apps)

        executor = MigrationExecutor(connection)
        with self.assertRaises(RuntimeError) as caught:
            executor.migrate(self.migrate_from)

        self.assertEqual(str(caught.exception), expected_message)
        self.assertEqual(self._row_snapshot(apps), rows_before)
        self.assertEqual(self._schema_snapshot(apps), schema_before)
        self.assertEqual(
            MigrationExecutor(connection).migration_plan(self.migrate_to),
            [],
            "A refused reverse must leave 0015 recorded as applied.",
        )

    def test_reverse_guard_is_the_last_forward_operation(self):
        migration_module = importlib.import_module(
            "domain.migrations.0015_foundation_studio_contract_constraints"
        )
        operation = migration_module.Migration.operations[-1]

        self.assertEqual(operation.__class__.__name__, "RunPython")
        self.assertEqual(operation.code.__name__, "noop")
        self.assertIs(
            operation.reverse_code,
            migration_module.reject_lossy_reverse_before_schema_changes,
        )

    def test_clean_0015_to_0012_reverse_succeeds_and_preserves_legacy_rows(self):
        apps = self._contract_apps()
        core = self._seed_contract_core(apps)
        row_ids = self._seed_legacy_compatible_rows(apps, core)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        legacy_apps = executor.loader.project_state(self.migrate_from).apps

        for model_name, row_id in row_ids.items():
            self.assertTrue(
                legacy_apps.get_model("domain", model_name)
                .objects.filter(pk=row_id)
                .exists()
            )
        self.assertEqual(
            MigrationExecutor(connection).migration_plan(self.migrate_from),
            [],
        )

        legacy_schema = self._schema_snapshot(legacy_apps)
        removed_columns = {
            "domain_auditevent": {"definition_version_id", "scope"},
            "domain_uihelpbinding": {"application_scope"},
            "domain_projectpublication": {"initial_workspace_id"},
            "domain_importrun": {
                "project_id",
                "definition_version_id",
                "package_scope",
            },
        }
        for table_name, column_names in removed_columns.items():
            actual_columns = {
                name for name, _null_ok in legacy_schema[table_name]["columns"]
            }
            self.assertTrue(column_names.isdisjoint(actual_columns))

        legacy_constraints = {
            "domain_uihelpbinding": "domain_ui_help_binding_uniq",
            "domain_importrun": "domain_import_run_code_uniq",
            "domain_auditevent": "domain_audit_workspace_code_uniq",
        }
        for table_name, constraint_name in legacy_constraints.items():
            self.assertIn(
                constraint_name,
                legacy_schema[table_name]["constraints"],
            )

    def test_definition_audit_refuses_reverse_before_schema_changes(self):
        self._assert_reverse_blocked(
            "definition_audit",
            "Cannot reverse after definition-scoped audit provenance exists.",
        )

    def test_global_help_binding_refuses_reverse_before_schema_changes(self):
        self._assert_reverse_blocked(
            "global_help_binding",
            "Cannot reverse after pre-workspace HelpTopic bindings exist.",
        )

    def test_initial_workspace_publication_refuses_reverse_before_schema_changes(self):
        self._assert_reverse_blocked(
            "initial_workspace_publication",
            "Cannot reverse after an initial-workspace publication receipt exists.",
        )

    def test_project_definition_import_refuses_reverse_before_schema_changes(self):
        self._assert_reverse_blocked(
            "project_definition_import",
            "Cannot reverse after project-definition import receipts exist.",
        )
