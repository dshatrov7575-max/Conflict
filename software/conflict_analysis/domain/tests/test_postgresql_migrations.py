import hashlib
import importlib
import json
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid5

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from domain.tests.test_v4_foundation_contracts import covers


FOUNDATION_MIGRATION_NAMESPACE = UUID("4ae5c076-cda7-43a3-a265-7519e02e9e94")


def _manifest_hash(manifest):
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _migrated_uuid(kind, *parts):
    identity = json.dumps(
        [str(kind), *(str(part) for part in parts)],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return uuid5(FOUNDATION_MIGRATION_NAMESPACE, identity)


class FoundationPR21UpgradeTests(TransactionTestCase):
    migrate_from = [("domain", "0001_initial")]
    migrate_to = [("domain", "0015_foundation_studio_contract_constraints")]

    def _restore_leaf_migrations(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _seed_pr21_rows(self, apps):
        Project = apps.get_model("domain", "Project")
        ProjectSchemaVersion = apps.get_model("domain", "ProjectSchemaVersion")
        TimeSlice = apps.get_model("domain", "TimeSlice")
        AssessmentSet = apps.get_model("domain", "AssessmentSet")
        ParameterDefinition = apps.get_model("domain", "ParameterDefinition")
        ParameterValue = apps.get_model("domain", "ParameterValue")
        EvidenceSource = apps.get_model("domain", "EvidenceSource")
        EvidenceLink = apps.get_model("domain", "EvidenceLink")
        AuditEvent = apps.get_model("domain", "AuditEvent")

        ids = {
            name: UUID(value)
            for name, value in {
                "project": "33000000-0000-4000-8000-000000000001",
                "schema": "33000000-0000-4000-8000-000000000002",
                "time_slice": "33000000-0000-4000-8000-000000000003",
                "human_set": "33000000-0000-4000-8000-000000000004",
                "ai_set": "33000000-0000-4000-8000-000000000005",
                "non_human_set": "33000000-0000-4000-8000-000000000012",
                "definition": "33000000-0000-4000-8000-000000000006",
                "unknown_value": "33000000-0000-4000-8000-000000000007",
                "zero_value": "33000000-0000-4000-8000-000000000008",
                "source": "33000000-0000-4000-8000-000000000009",
                "evidence_link": "33000000-0000-4000-8000-000000000009",
                "evidence_link_two": "33000000-0000-4000-8000-000000000010",
                "audit": "33000000-0000-4000-8000-000000000011",
            }.items()
        }
        project = Project.objects.create(
            id=ids["project"],
            code="PROJECT-PR21-UPGRADE",
            version="1.0.0",
            name="PR21 upgrade fixture",
            metadata={"fixture": "existing-installation"},
        )
        manifest = {
            "ontology_version": "3.0.0",
            "project": project.code,
        }
        ProjectSchemaVersion.objects.create(
            id=ids["schema"],
            project=project,
            code="SCHEMA-PR21-001",
            version="3.0.0",
            is_current=True,
            manifest=manifest,
            manifest_hash=_manifest_hash(manifest),
        )
        time_slice = TimeSlice.objects.create(
            id=ids["time_slice"],
            project=project,
            code="TS-PR21-001",
            version="1.0.0",
            name="Historical cutoff",
            cutoff_date=date(2022, 1, 2),
            order=0,
        )
        human_set = AssessmentSet.objects.create(
            id=ids["human_set"],
            project=project,
            code="SET-PR21-HUMAN",
            version="1.0.0",
            kind="HUMAN",
            name="Historical matching business key coding",
        )
        ai_set = AssessmentSet.objects.create(
            id=ids["ai_set"],
            project=project,
            code="SET-PR21-AI",
            version="1.0.0",
            kind="AI",
            name="Historical matching business key coding",
        )
        AssessmentSet.objects.create(
            id=ids["non_human_set"],
            project=project,
            code="SET-PR21-CONSENSUS",
            version="1.0.0",
            kind="CONSENSUS",
            name="Historical unresolved consensus coding",
        )
        definition = ParameterDefinition.objects.create(
            id=ids["definition"],
            project=project,
            code="POS-PR21",
            version="1.0.0",
            name="Historical position",
            target_type="TIME_SLICE",
            value_type="INTEGER",
            scale_min=-10,
            scale_max=10,
        )
        unknown_value = ParameterValue.objects.create(
            id=ids["unknown_value"],
            project=project,
            time_slice=time_slice,
            assessment_set=human_set,
            parameter_definition=definition,
            target_type="TIME_SLICE",
            target_id=time_slice.id,
            code="VALUE-PR21-UNKNOWN",
            version="1.0.0",
            status="UNKNOWN",
            value=None,
            confidence=None,
            rationale="No value was coded.",
        )
        zero_value = ParameterValue.objects.create(
            id=ids["zero_value"],
            project=project,
            time_slice=time_slice,
            assessment_set=ai_set,
            parameter_definition=definition,
            target_type="TIME_SLICE",
            target_id=time_slice.id,
            code="VALUE-PR21-ZERO",
            version="1.0.0",
            status="CONFIRMED",
            value=0,
            confidence=Decimal("0.7500"),
            rationale="An explicit zero, not an unknown.",
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ParameterValue.objects.create(
                id=UUID("33000000-0000-4000-8000-000000000013"),
                project=project,
                time_slice=time_slice,
                assessment_set=human_set,
                parameter_definition=definition,
                target_type="TIME_SLICE",
                target_id=time_slice.id,
                code="VALUE-PR21-NUMERIC-CONTEXT-COLLISION",
                version="1.0.0",
                status="CONFIRMED",
                value=0,
                confidence=Decimal("0.5000"),
                rationale="Must not overwrite the existing UNKNOWN lane.",
            )
        unknown_value.refresh_from_db()
        self.assertEqual((unknown_value.status, unknown_value.value), ("UNKNOWN", None))
        source = EvidenceSource.objects.create(
            id=ids["source"],
            project=project,
            code="LEGACY-SHARED-CODE",
            version="1.0.0",
            title="Legacy URL evidence",
            url="https://example.test/legacy",
            published_on=date(2022, 1, 1),
            accessed_on=date(2022, 1, 2),
        )
        EvidenceLink.objects.create(
            id=ids["evidence_link"],
            project=project,
            parameter_value=unknown_value,
            source=source,
            code="LEGACY-SHARED-CODE",
            version="1.0.0",
            relation="SUPPORTS",
            rationale="Legacy linkage cannot fabricate an immutable anchor.",
        )
        EvidenceLink.objects.create(
            id=ids["evidence_link_two"],
            project=project,
            parameter_value=zero_value,
            source=source,
            code="EVIDENCE-LINK-PR21-002",
            version="1.0.0",
            relation="CONTRADICTS",
            rationale="Same source, distinct value semantics remain a distinct receipt.",
        )
        AuditEvent.objects.create(
            id=ids["audit"],
            project=project,
            assessment_set=human_set,
            parameter_value=unknown_value,
            code="AUDIT-PR21-001",
            version="1.0.0",
            action="CREATE",
            actor_type="HUMAN",
            actor_identifier="legacy-owner",
            entity_type="PARAMETER_VALUE",
            entity_id=unknown_value.id,
            after={"status": "UNKNOWN", "value": None},
        )
        return ids

    @covers("FND-W05", "FND-M03", "FND-M05")
    def test_existing_pr21_rows_upgrade_without_id_churn_or_semantic_reinterpretation(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self._restore_leaf_migrations)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        ids = self._seed_pr21_rows(old_apps)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps

        ProjectDefinitionVersion = apps.get_model(
            "domain", "ProjectDefinitionVersion"
        )
        ProjectWorkspace = apps.get_model("domain", "ProjectWorkspace")
        ProjectPublication = apps.get_model("domain", "ProjectPublication")
        TimeSlice = apps.get_model("domain", "TimeSlice")
        TextFragment = apps.get_model("domain", "TextFragment")
        AssessmentSet = apps.get_model("domain", "AssessmentSet")
        ParameterValue = apps.get_model("domain", "ParameterValue")
        Experiment = apps.get_model("domain", "Experiment")
        ExpertProfile = apps.get_model("domain", "ExpertProfile")
        LegacyCompatibilityReceipt = apps.get_model(
            "domain", "LegacyCompatibilityReceipt"
        )
        EvidenceSource = apps.get_model("domain", "EvidenceSource")
        EvidenceLink = apps.get_model("domain", "EvidenceLink")
        Fact = apps.get_model("domain", "Fact")
        PowerComponent = apps.get_model("domain", "PowerComponent")
        AuditEvent = apps.get_model("domain", "AuditEvent")

        definition = ProjectDefinitionVersion.objects.get(pk=ids["schema"])
        expected_workspace_id = _migrated_uuid(
            "workspace", ids["project"], "DEFAULT"
        )
        workspace = ProjectWorkspace.objects.get(pk=expected_workspace_id)
        self.assertEqual(definition.code, "SCHEMA-PR21-001")
        self.assertEqual(definition.version, "3.0.0")
        self.assertTrue(definition.is_current)
        self.assertEqual(
            definition.validated_by,
            "MIGRATION-CA-SUITE-I1-FOUNDATION-001",
        )
        self.assertEqual(
            definition.published_by,
            "MIGRATION-CA-SUITE-I1-FOUNDATION-001",
        )
        self.assertEqual(
            definition.validation_result,
            {"valid": True, "source": "PR21_UPGRADE_COMPATIBILITY"},
        )
        self.assertIsNotNone(definition.validated_at)
        publication = ProjectPublication.objects.get(
            pk=_migrated_uuid("publication", definition.id, "ru-RU")
        )
        self.assertEqual(
            publication.actor_identifier,
            "MIGRATION-CA-SUITE-I1-FOUNDATION-001",
        )
        self.assertEqual(
            publication.validation_result,
            {"valid": True, "source": "PR21_UPGRADE_COMPATIBILITY"},
        )
        self.assertIsNone(
            publication.initial_workspace_id,
            "Historical publication receipts are preserved, not silently rewritten.",
        )
        self.assertEqual(workspace.project_id, ids["project"])
        self.assertEqual(workspace.definition_version_id, ids["schema"])
        self.assertEqual(workspace.definition_manifest_hash, definition.manifest_hash)
        self.assertEqual(workspace.code, "DEFAULT")
        self.assertTrue(workspace.is_default)
        self.assertEqual(
            ProjectWorkspace.objects.filter(project_id=ids["project"]).count(),
            1,
        )

        migrated_slice = TimeSlice.objects.get(pk=ids["time_slice"])
        self.assertEqual(migrated_slice.workspace_id, workspace.id)
        self.assertEqual(migrated_slice.metadata, {})
        self.assertEqual(TimeSlice._meta.get_field("metadata").default(), {})
        self.assertEqual(TextFragment._meta.get_field("metadata").default(), {})
        self.assertFalse(TextFragment.objects.exists())
        sets = {
            item.id: item
            for item in AssessmentSet.objects.filter(project_id=ids["project"])
        }
        self.assertEqual(
            set(sets),
            {ids["human_set"], ids["ai_set"], ids["non_human_set"]},
        )
        self.assertTrue(all(item.workspace_id == workspace.id for item in sets.values()))

        experiments = {
            item.assessment_set_id: item
            for item in Experiment.objects.filter(workspace_id=workspace.id)
        }
        self.assertEqual(set(experiments), {ids["human_set"], ids["ai_set"]})
        self.assertNotIn(ids["non_human_set"], experiments)
        self.assertEqual(
            experiments[ids["human_set"]].experiment_type,
            "ASSESSMENT",
        )
        self.assertEqual(
            experiments[ids["ai_set"]].experiment_type,
            "ASSESSMENT",
        )
        self.assertEqual(
            experiments[ids["human_set"]].id,
            _migrated_uuid("experiment", ids["human_set"]),
        )
        profiles = {
            profile.metadata["legacy_assessment_set_id"]: profile
            for profile in ExpertProfile.objects.filter(workspace_id=workspace.id)
        }
        self.assertEqual(
            set(profiles),
            {str(ids["human_set"]), str(ids["ai_set"])},
        )
        self.assertEqual(
            {profile.code for profile in profiles.values()},
            {
                f"EXPERT-{ids['human_set'].hex}",
                f"EXPERT-{ids['ai_set'].hex}",
            },
        )
        self.assertEqual(
            {experiment.code for experiment in experiments.values()},
            {
                f"EXPERIMENT-{ids['human_set'].hex}",
                f"EXPERIMENT-{ids['ai_set'].hex}",
            },
        )
        self.assertEqual(
            ids["human_set"].hex[:16],
            ids["ai_set"].hex[:16],
            "collision oracle requires distinct legacy UUIDs sharing the old prefix",
        )
        self.assertNotEqual(
            profiles[str(ids["human_set"])].code,
            profiles[str(ids["ai_set"])].code,
        )
        logical_rows = [
            ("experiment", ids["human_set"]),
            ("experiment", ids["ai_set"]),
            ("compatibility-receipt", "EvidenceSource", ids["source"]),
            ("compatibility-receipt", "EvidenceLink", ids["evidence_link"]),
        ]
        forward_identities = {
            row: _migrated_uuid(row[0], *row[1:]) for row in logical_rows
        }
        reversed_identities = {
            row: _migrated_uuid(row[0], *row[1:])
            for row in reversed(logical_rows)
        }
        self.assertEqual(forward_identities, reversed_identities)
        self.assertNotEqual(
            _migrated_uuid("delimiter-oracle", "a:b", "c"),
            _migrated_uuid("delimiter-oracle", "a", "b:c"),
            "canonical JSON tuple identity must be injective across delimiter layouts",
        )

        unknown = ParameterValue.objects.get(pk=ids["unknown_value"])
        zero = ParameterValue.objects.get(pk=ids["zero_value"])
        self.assertEqual(unknown.workspace_id, workspace.id)
        self.assertEqual(zero.workspace_id, workspace.id)
        self.assertEqual((unknown.status, unknown.value), ("UNKNOWN", None))
        self.assertEqual((zero.status, zero.value), ("CONFIRMED", 0))
        self.assertEqual(ParameterValue.objects.filter(project_id=ids["project"]).count(), 2)
        self.assertEqual(PowerComponent.objects.filter(workspace_id=workspace.id).count(), 0)

        receipts = list(
            LegacyCompatibilityReceipt.objects.filter(workspace_id=workspace.id)
            .order_by("legacy_model")
            .values_list(
                "legacy_model",
                "legacy_id",
                "status",
                "canonical_id",
                "reason",
            )
        )
        self.assertEqual(
            {(model, legacy_id) for model, legacy_id, *_ in receipts},
            {
                ("AssessmentSet", ids["non_human_set"]),
                ("EvidenceSource", ids["source"]),
                ("EvidenceLink", ids["evidence_link"]),
                ("EvidenceLink", ids["evidence_link_two"]),
            },
        )
        self.assertTrue(
            all(
                status == "UNRESOLVED" and canonical_id is None and reason
                for _, _, status, canonical_id, reason in receipts
            )
        )
        receipt_codes = set(
            LegacyCompatibilityReceipt.objects.filter(
                workspace_id=workspace.id
            ).values_list("code", flat=True)
        )
        self.assertIn(
            f"LEGACY-EVIDENCESOURCE-{ids['source'].hex}",
            receipt_codes,
        )
        self.assertIn(
            f"LEGACY-EVIDENCELINK-{ids['evidence_link'].hex}",
            receipt_codes,
        )
        self.assertIn(
            f"LEGACY-EVIDENCELINK-{ids['evidence_link_two'].hex}",
            receipt_codes,
        )
        self.assertIn(
            f"LEGACY-ASSESSMENTSET-{ids['non_human_set'].hex}",
            receipt_codes,
        )
        self.assertTrue(EvidenceSource.objects.filter(pk=ids["source"]).exists())
        self.assertTrue(EvidenceLink.objects.filter(pk=ids["evidence_link"]).exists())
        self.assertEqual(
            EvidenceLink.objects.filter(source_id=ids["source"]).count(),
            2,
        )
        self.assertEqual(Fact.objects.filter(workspace_id=workspace.id).count(), 0)

        audit = AuditEvent.objects.get(pk=ids["audit"])
        self.assertEqual(audit.workspace_id, workspace.id)
        self.assertEqual(audit.parameter_value_id, ids["unknown_value"])
        self.assertEqual(audit.scope, "WORKSPACE")
        self.assertIsNone(audit.definition_version_id)

        counts_before_rerun = {
            "definitions": ProjectDefinitionVersion.objects.count(),
            "workspaces": ProjectWorkspace.objects.count(),
            "publications": ProjectPublication.objects.count(),
            "sets": AssessmentSet.objects.count(),
            "profiles": ExpertProfile.objects.count(),
            "experiments": Experiment.objects.count(),
            "values": ParameterValue.objects.count(),
            "receipts": LegacyCompatibilityReceipt.objects.count(),
            "audits": AuditEvent.objects.count(),
        }
        migration_module = importlib.import_module(
            "domain.migrations.0002_foundation_v4_schema"
        )
        migration_module.migrate_pr21_foundation(apps, None)
        migration_module.migrate_pr21_foundation(apps, None)
        self.assertEqual(
            {
                "definitions": ProjectDefinitionVersion.objects.count(),
                "workspaces": ProjectWorkspace.objects.count(),
                "publications": ProjectPublication.objects.count(),
                "sets": AssessmentSet.objects.count(),
                "profiles": ExpertProfile.objects.count(),
                "experiments": Experiment.objects.count(),
                "values": ParameterValue.objects.count(),
                "receipts": LegacyCompatibilityReceipt.objects.count(),
                "audits": AuditEvent.objects.count(),
            },
            counts_before_rerun,
        )


class PostgreSQLMigrationGateTests(TransactionTestCase):
    @covers("FND-M04")
    def test_clean_test_database_is_at_every_migration_leaf(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only migration gate")

        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        self.assertEqual(executor.migration_plan(targets), [])

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
            primary_language_tag="ru",
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


class ProjectPrimaryLanguageMigrationGateTests(TransactionTestCase):
    migrate_from = [("domain", "0015_foundation_studio_contract_constraints")]
    migrate_to = [("domain", "0016_project_primary_language")]
    kz_id = UUID("3de70d1d-f4cf-535a-95b9-94c0a65e60e3")
    other_id = UUID("48000000-0000-4000-8000-000000000001")
    id_only_id = kz_id
    code_only_id = UUID("48000000-0000-4000-8000-000000000002")

    def setUp(self):
        super().setUp()
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only migration gate")

    def _restore_leaf_migrations(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def _seed_0015_projects(self, apps):
        Project = apps.get_model("domain", "Project")
        ProjectSchemaVersion = apps.get_model("domain", "ProjectSchemaVersion")
        kz = Project.objects.create(
            id=self.kz_id,
            code="KZ-ZHANAOZEN-DEMO",
            version="7.2.1",
            name="Exact KZ durable identity",
            description="preserve KZ description",
            metadata={"preserve": "kz", "nested": {"value": 0}},
        )
        other = Project.objects.create(
            id=self.other_id,
            code="OTHER-PROJECT",
            version="4.5.6",
            name="Other durable identity",
            description="preserve other description",
            metadata={"preserve": "other", "false": False},
        )
        # Exact-pair authority: matching the code without the UUID is not KZ.
        code_only = Project.objects.create(
            id=self.code_only_id,
            code="KZ-ZHANAOZEN-DEMO-DECOY",
            version="1.0.0",
            name="Code-prefix decoy",
            metadata={"preserve": "code-only"},
        )
        schema = ProjectSchemaVersion.objects.create(
            id=UUID("48000000-0000-4000-8000-000000000003"),
            project=other,
            code="SCHEMA-PRESERVE",
            version="4.5.6",
            is_current=True,
            manifest={"identity": "must-not-drift", "zero": 0},
            manifest_hash="a" * 64,
        )
        return {
            "kz": kz,
            "other": other,
            "code_only": code_only,
            "schema": schema,
        }

    @staticmethod
    def _project_snapshot(Project):
        return list(
            Project.objects.order_by("id").values(
                "id",
                "code",
                "version",
                "name",
                "description",
                "metadata",
            )
        )

    def test_0015_to_0016_maps_exact_kz_to_ru_and_other_projects_to_und_without_drift(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self._restore_leaf_migrations)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        rows = self._seed_0015_projects(old_apps)
        before_projects = self._project_snapshot(
            old_apps.get_model("domain", "Project")
        )
        before_schema = old_apps.get_model(
            "domain", "ProjectSchemaVersion"
        ).objects.values(
            "id", "project_id", "manifest", "manifest_hash"
        ).get(pk=rows["schema"].pk)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps = executor.loader.project_state(self.migrate_to).apps
        Project = apps.get_model("domain", "Project")
        self.assertEqual(
            tuple(
                Project.objects.values_list(
                    "primary_language_tag",
                    "primary_language_assignment",
                ).get(pk=self.kz_id)
            ),
            ("ru", "EXPLICIT"),
        )
        for project_id in (self.other_id, self.code_only_id):
            self.assertEqual(
                tuple(
                    Project.objects.values_list(
                        "primary_language_tag",
                        "primary_language_assignment",
                    ).get(pk=project_id)
                ),
                ("und", "LEGACY_UNKNOWN"),
            )
        self.assertEqual(self._project_snapshot(Project), before_projects)
        after_schema = apps.get_model(
            "domain", "ProjectSchemaVersion"
        ).objects.values(
            "id", "project_id", "manifest", "manifest_hash"
        ).get(pk=rows["schema"].pk)
        self.assertEqual(after_schema, before_schema)

        # A second 0015-shaped pass proves that neither half of the durable
        # KZ identity is independently sufficient to infer Russian.
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        apps_0015 = executor.loader.project_state(self.migrate_from).apps
        Project0015 = apps_0015.get_model("domain", "Project")
        Project0015.objects.filter(pk=self.kz_id).delete()
        code_only = Project0015.objects.get(pk=self.code_only_id)
        code_only.code = "KZ-ZHANAOZEN-DEMO"
        code_only.save(update_fields=["code"])
        Project0015.objects.create(
            id=self.kz_id,
            code="UUID-ONLY-KZ-DECOY",
            version="1.0.0",
            name="UUID-only decoy",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        near_match_project = executor.loader.project_state(
            self.migrate_to
        ).apps.get_model("domain", "Project")
        for project_id in (self.kz_id, self.code_only_id):
            self.assertEqual(
                tuple(
                    near_match_project.objects.values_list(
                        "primary_language_tag",
                        "primary_language_assignment",
                    ).get(pk=project_id)
                ),
                ("und", "LEGACY_UNKNOWN"),
            )

    def test_0016_reverse_reapply_and_clean_database_seed_are_exact(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        self.addCleanup(self._restore_leaf_migrations)
        apps_0015 = executor.loader.project_state(self.migrate_from).apps
        self._seed_0015_projects(apps_0015)
        before_projects = self._project_snapshot(
            apps_0015.get_model("domain", "Project")
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        apps_0016 = executor.loader.project_state(self.migrate_to).apps
        first_pairs = list(
            apps_0016.get_model("domain", "Project")
            .objects.order_by("id")
            .values_list(
                "id",
                "primary_language_tag",
                "primary_language_assignment",
            )
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        reversed_apps = executor.loader.project_state(self.migrate_from).apps
        reversed_project = reversed_apps.get_model("domain", "Project")
        self.assertNotIn(
            "primary_language_tag",
            {field.name for field in reversed_project._meta.get_fields()},
        )
        self.assertEqual(self._project_snapshot(reversed_project), before_projects)

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        reapplied_apps = executor.loader.project_state(self.migrate_to).apps
        reapplied_project = reapplied_apps.get_model("domain", "Project")
        self.assertEqual(
            list(
                reapplied_project.objects.order_by("id").values_list(
                    "id",
                    "primary_language_tag",
                    "primary_language_assignment",
                )
            ),
            first_pairs,
        )
        self.assertEqual(self._project_snapshot(reapplied_project), before_projects)

        reapplied_project.objects.all().delete()
        from domain.demo_data import PROJECT_CODE, stable_demo_uuid
        from domain.services.seed import seed_zhanaozen_demo

        seeded = seed_zhanaozen_demo()
        replayed = seed_zhanaozen_demo()
        self.assertEqual(seeded.pk, replayed.pk)
        self.assertEqual(seeded.pk, stable_demo_uuid("project", PROJECT_CODE))
        self.assertEqual(seeded.primary_language_tag, "ru")
        self.assertEqual(seeded.primary_language_assignment, "EXPLICIT")
