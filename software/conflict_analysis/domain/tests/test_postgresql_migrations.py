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
    migrate_to = [("domain", "0012_xlsx_metadata_contract")]

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
