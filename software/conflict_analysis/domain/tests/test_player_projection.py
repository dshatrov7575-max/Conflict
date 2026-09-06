from __future__ import annotations

import copy
import hashlib
from importlib import import_module
import json
import threading
from datetime import date
from decimal import Decimal
from unittest import skipUnless
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import (
    DatabaseError,
    IntegrityError,
    close_old_connections,
    connection,
    connections,
    transaction,
)
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.db.models.deletion import RestrictedError
from django.test import TransactionTestCase
from django.utils import timezone

from domain.enums import AssessmentProjectionStatus, TargetType, ValueStatus
from domain.models import (
    Actor,
    ActorElementRole,
    AnalyticalElement,
    AssessmentSet,
    AuditEvent,
    ParameterDefinition,
    ParameterValue,
    ProjectWorkspace,
    TimeSlice,
    _canonical_assessment_projection_write,
    _target_model,
)
from domain.policies import (
    bootstrap_initial_project_definition,
    validate_project_definition,
)
from domain.services.player_projection import (
    AssessmentProjectionConflict,
    AssessmentProjectionError,
    materialize_workspace_assessment_projection,
    verify_workspace_assessment_projection,
)
from domain.services.foundation_packages import (
    FoundationPackageConflictError,
    FoundationPackageValidationError,
    commit_foundation_package_2_2,
    export_workspace_json_2_2,
    export_workspace_package_2_2,
    preview_foundation_package_2_2,
    validate_foundation_package_2_2,
)
from domain.services.project_definitions import (
    clone_project_definition_draft,
    publish_successor_project_definition,
)
from domain.tests.test_foundation_studio_bootstrap import (
    FoundationStudioBootstrapMixin,
)


_PROJECTION_RECEIPT_ENTITY_TYPE = (
    "FOUNDATION_WORKSPACE_ASSESSMENT_PROJECTION_V1"
)
_MIGRATION_FROM = [("domain", "0017_multilingual_evidence_lineage")]
_MIGRATION_TO = [("domain", "0018_workspace_assessment_projection")]


def _canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _projection_manifest(manifest: dict) -> dict:
    """Give the standard typed fixture one real hierarchy and direct targets."""

    payload = copy.deepcopy(manifest)
    actors = payload["actors"]
    elements = payload["analytical_elements"]
    roles = payload["actor_element_roles"]
    actors[1]["parent_id"] = actors[0]["id"]
    elements[1]["parent_id"] = elements[0]["id"]

    actor_parameter = payload["parameter_definitions"][0]
    actor_parameter.update(
        {
            "code": "PARAMETER-ACTOR",
            "target_type": "ACTOR",
            "applicability": {
                "actor_ids": [actors[0]["id"]],
                "analytical_element_ids": [],
                "actor_element_role_ids": [],
            },
        }
    )
    element_parameter = copy.deepcopy(actor_parameter)
    element_parameter.update(
        {
            "id": "14000000-0000-4000-8000-000000000002",
            "code": "PARAMETER-ELEMENT",
            "target_type": "ANALYTICAL_ELEMENT",
            "applicability": {
                "actor_ids": [],
                "analytical_element_ids": [elements[0]["id"]],
                "actor_element_role_ids": [],
            },
        }
    )
    role_parameter = copy.deepcopy(actor_parameter)
    role_parameter.update(
        {
            "id": "14000000-0000-4000-8000-000000000003",
            "code": "PARAMETER-ROLE",
            "target_type": "ACTOR_ELEMENT_ROLE",
            "applicability": {
                "actor_ids": [],
                "analytical_element_ids": [],
                "actor_element_role_ids": [roles[0]["id"]],
            },
        }
    )
    payload["parameter_definitions"].extend((element_parameter, role_parameter))
    return payload


def _canonical_rows(workspace: ProjectWorkspace) -> dict[str, list]:
    return {
        "actors": list(
            Actor.objects.filter(
                workspace=workspace,
                source_manifest_entity_id__isnull=False,
            ).order_by("source_manifest_entity_id")
        ),
        "elements": list(
            AnalyticalElement.objects.filter(
                workspace=workspace,
                source_manifest_entity_id__isnull=False,
            ).order_by("source_manifest_entity_id")
        ),
        "roles": list(
            ActorElementRole.objects.filter(
                workspace=workspace,
                source_manifest_entity_id__isnull=False,
            ).order_by("source_manifest_entity_id")
        ),
        "parameters": list(
            ParameterDefinition.objects.filter(
                definition_version=workspace.definition_version,
            ).order_by("source_manifest_parameter_id")
        ),
    }


def _source_mapping(workspace: ProjectWorkspace) -> dict[str, list[tuple[str, str]]]:
    rows = _canonical_rows(workspace)
    return {
        "actors": [
            (str(row.source_manifest_entity_id), str(row.pk)) for row in rows["actors"]
        ],
        "elements": [
            (str(row.source_manifest_entity_id), str(row.pk))
            for row in rows["elements"]
        ],
        "roles": [
            (str(row.source_manifest_entity_id), str(row.pk)) for row in rows["roles"]
        ],
        "parameters": [
            (str(row.source_manifest_parameter_id), str(row.pk))
            for row in rows["parameters"]
        ],
    }


def _projection_semantic_counts() -> tuple[int, int, int, int, int, int]:
    """The 2.2 reconciliation route is read-only across all projection state."""

    return (
        ProjectWorkspace.objects.count(),
        Actor.objects.count(),
        AnalyticalElement.objects.count(),
        ActorElementRole.objects.count(),
        ParameterDefinition.objects.count(),
        AuditEvent.objects.count(),
    )


def _make_workspace(
    *,
    definition,
    project,
    code: str,
    is_default: bool = False,
) -> ProjectWorkspace:
    return ProjectWorkspace.objects.create(
        id=uuid4(),
        project=project,
        definition_version=definition,
        definition_manifest_hash=definition.manifest_hash,
        code=code,
        version="1.0.0",
        name=f"{code} workspace",
        is_default=is_default,
        metadata={"fd08": "explicit-workspace"},
    )


def _restore_leaf_migrations() -> None:
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())


class _FD08ProjectionGuardTeardownMixin:
    """Let TransactionTestCase flush fixtures without weakening in-test D-09 guards."""

    _guard_migration_app = "domain"
    _guard_migration_name = "0018_workspace_assessment_projection"

    @classmethod
    def _fd08_guard_migration_is_applied(cls, database: str) -> bool:
        return MigrationRecorder(connections[database]).migration_qs.filter(
            app=cls._guard_migration_app,
            name=cls._guard_migration_name,
        ).exists()

    def _fixture_teardown(self) -> None:
        migration = import_module(
            "domain.migrations.0018_workspace_assessment_projection"
        )
        guarded_databases: list[str] = []
        try:
            for database in self._databases_names(include_mirrors=False):
                if not self._fd08_guard_migration_is_applied(database):
                    continue
                with connections[database].schema_editor() as schema_editor:
                    migration._drop_canonical_projection_guards(schema_editor)
                guarded_databases.append(database)
            super()._fixture_teardown()
        finally:
            for database in guarded_databases:
                if not self._fd08_guard_migration_is_applied(database):
                    continue
                with connections[database].schema_editor() as schema_editor:
                    migration._install_canonical_projection_guards(None, schema_editor)


class FoundationWorkspaceAssessmentProjectionTests(
    _FD08ProjectionGuardTeardownMixin,
    FoundationStudioBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def _bootstrap(self, *, projection_manifest: bool = False):
        self.make_contract()
        if projection_manifest:
            self.manifest = _projection_manifest(self.manifest)
        definition = self.draft(code=f"FD08-DEF-{uuid4().hex[:12]}")
        principal = self.publisher(actor="fd08-projection-human")
        bootstrap = bootstrap_initial_project_definition(
            definition=definition,
            principal=principal,
            actor_identifier=principal.actor_identifier,
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        return bootstrap.definition, bootstrap.workspace, principal

    @staticmethod
    def _materialize(workspace, operation_identity, principal, **kwargs):
        return materialize_workspace_assessment_projection(
            workspace,
            operation_identity,
            getattr(principal, "actor_identifier", principal),
            **kwargs,
        )

    def _time_and_set(self, workspace: ProjectWorkspace) -> tuple[TimeSlice, AssessmentSet]:
        time_slice = TimeSlice.objects.create(
            id=uuid4(),
            project=workspace.project,
            workspace=workspace,
            code=f"FD08-SLICE-{uuid4().hex[:10]}",
            version="1.0.0",
            name="FD08 exact target time slice",
            cutoff_date=date(2025, 1, 1),
            order=0,
            metadata={},
        )
        assessment_set = AssessmentSet.objects.create(
            id=uuid4(),
            project=workspace.project,
            workspace=workspace,
            code=f"FD08-SET-{uuid4().hex[:10]}",
            version="1.0.0",
            kind="HUMAN",
            name="FD08 exact target set",
            description="",
        )
        return time_slice, assessment_set

    def _parameter_value(
        self,
        *,
        workspace: ProjectWorkspace,
        time_slice: TimeSlice,
        assessment_set: AssessmentSet,
        parameter: ParameterDefinition,
        target_type: str,
        target_id,
    ) -> ParameterValue:
        return ParameterValue(
            id=uuid4(),
            project=workspace.project,
            workspace=workspace,
            time_slice=time_slice,
            assessment_set=assessment_set,
            parameter_definition=parameter,
            target_type=target_type,
            target_id=target_id,
            code=f"FD08-VALUE-{uuid4().hex[:12]}",
            version="1.0.0",
            status=ValueStatus.UNKNOWN,
            value=None,
            confidence=None,
            rationale="",
        )

    def test_manifest_target_enum_and_domain_target_model_are_exactly_aligned(self):
        expected = {
            TargetType.ACTOR: Actor,
            TargetType.ANALYTICAL_ELEMENT: AnalyticalElement,
            TargetType.ACTOR_ELEMENT_ROLE: ActorElementRole,
            TargetType.ACTOR_ELEMENT_ASSESSMENT: _target_model(
                TargetType.ACTOR_ELEMENT_ASSESSMENT
            ),
        }
        self.assertEqual(_target_model(TargetType.ACTOR), Actor)
        self.assertEqual(_target_model(TargetType.ANALYTICAL_ELEMENT), AnalyticalElement)
        self.assertEqual(_target_model(TargetType.ACTOR_ELEMENT_ROLE), ActorElementRole)
        self.assertTrue(all(model is not None for model in expected.values()))
        self.assertEqual(
            set(expected),
            {
                "ACTOR",
                "ANALYTICAL_ELEMENT",
                "ACTOR_ELEMENT_ROLE",
                "ACTOR_ELEMENT_ASSESSMENT",
            },
        )
        self.assertEqual(Actor._meta.get_field("source_manifest_entity_id").null, True)
        self.assertEqual(
            ParameterDefinition._meta.get_field("source_manifest_parameter_id").null,
            True,
        )

    def test_upgrade_preserves_every_legacy_parameter_definition_value_and_target_identity(self):
        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATION_FROM)
        self.addCleanup(_restore_leaf_migrations)
        old_apps = executor.loader.project_state(_MIGRATION_FROM).apps

        Project = old_apps.get_model("domain", "Project")
        ProjectDefinitionVersion = old_apps.get_model(
            "domain", "ProjectDefinitionVersion"
        )
        ProjectWorkspace = old_apps.get_model("domain", "ProjectWorkspace")
        TimeSlice = old_apps.get_model("domain", "TimeSlice")
        AssessmentSet = old_apps.get_model("domain", "AssessmentSet")
        ParameterDefinition = old_apps.get_model("domain", "ParameterDefinition")
        ParameterValue = old_apps.get_model("domain", "ParameterValue")

        ids = {
            "project": UUID("82000000-0000-4000-8000-000000000001"),
            "definition": UUID("82000000-0000-4000-8000-000000000002"),
            "workspace": UUID("82000000-0000-4000-8000-000000000003"),
            "time_slice": UUID("82000000-0000-4000-8000-000000000004"),
            "assessment_set": UUID("82000000-0000-4000-8000-000000000005"),
            "parameter": UUID("82000000-0000-4000-8000-000000000006"),
            "value": UUID("82000000-0000-4000-8000-000000000007"),
        }
        project = Project.objects.create(
            id=ids["project"],
            code="FD08-UPGRADE-PROJECT",
            version="1.0.0",
            name="FD08 migration fixture",
            description="Legacy values must remain byte-identical.",
            metadata={"fd08": "legacy"},
            primary_language_tag="und",
            primary_language_assignment="LEGACY_UNKNOWN",
        )
        manifest = {"legacy": "FD08"}
        definition = ProjectDefinitionVersion.objects.create(
            id=ids["definition"],
            project=project,
            code="FD08-UPGRADE-DEFINITION",
            version="1.0.0",
            schema_version="1.0.0",
            semantic_version="1.0.0",
            construct_version="1.0.0",
            manifest=manifest,
            manifest_hash=_canonical_json_sha256(manifest),
            publication_status="PUBLISHED",
            validation_result={"valid": True},
            validated_at=timezone.now(),
            validated_by="fd08-migration",
            published_at=timezone.now(),
            published_by="fd08-migration",
            is_current=True,
        )
        workspace = ProjectWorkspace.objects.create(
            id=ids["workspace"],
            project=project,
            definition_version=definition,
            definition_manifest_hash=definition.manifest_hash,
            code="FD08-UPGRADE-WORKSPACE",
            version="1.0.0",
            name="FD08 upgrade workspace",
            is_default=True,
            metadata={},
        )
        time_slice = TimeSlice.objects.create(
            id=ids["time_slice"],
            project=project,
            workspace=workspace,
            code="FD08-UPGRADE-SLICE",
            version="1.0.0",
            name="FD08 upgrade cutoff",
            cutoff_date=date(2024, 1, 1),
            order=0,
            metadata={},
        )
        assessment_set = AssessmentSet.objects.create(
            id=ids["assessment_set"],
            project=project,
            workspace=workspace,
            code="FD08-UPGRADE-SET",
            version="1.0.0",
            kind="HUMAN",
            name="FD08 upgrade assessment set",
            description="",
        )
        parameter = ParameterDefinition.objects.create(
            id=ids["parameter"],
            project=project,
            code="FD08-UPGRADE-PARAMETER",
            version="1.0.0",
            name="Legacy parameter",
            description="Legacy target identity must persist.",
            target_type="TIME_SLICE",
            value_type="INTEGER",
            scale_min=-10,
            scale_max=10,
            scale_metadata={"legacy": True},
        )
        ParameterValue.objects.create(
            id=ids["value"],
            project=project,
            workspace=workspace,
            time_slice=time_slice,
            assessment_set=assessment_set,
            parameter_definition=parameter,
            target_type="TIME_SLICE",
            target_id=time_slice.pk,
            code="FD08-UPGRADE-VALUE",
            version="1.0.0",
            status="CONFIRMED",
            temporal_status="UNKNOWN",
            value=0,
            note="Legacy numeric zero is not UNKNOWN.",
            confidence=Decimal("1.0000"),
            range_min=None,
            range_max=None,
            rationale="Legacy evidence preserves numeric zero exactly.",
        )

        executor = MigrationExecutor(connection)
        executor.migrate(_MIGRATION_TO)
        apps = executor.loader.project_state(_MIGRATION_TO).apps
        NewParameterDefinition = apps.get_model("domain", "ParameterDefinition")
        NewParameterValue = apps.get_model("domain", "ParameterValue")
        migrated_parameter = NewParameterDefinition.objects.get(pk=ids["parameter"])
        migrated_value = NewParameterValue.objects.get(pk=ids["value"])

        self.assertEqual(migrated_parameter.pk, ids["parameter"])
        self.assertIsNone(migrated_parameter.definition_version_id)
        self.assertIsNone(migrated_parameter.source_manifest_parameter_id)
        self.assertIsNone(migrated_parameter.manifest_snapshot_sha256)
        self.assertEqual(migrated_parameter.target_type, "TIME_SLICE")
        self.assertEqual(migrated_value.pk, ids["value"])
        self.assertEqual(migrated_value.parameter_definition_id, ids["parameter"])
        self.assertEqual(migrated_value.target_type, "TIME_SLICE")
        self.assertEqual(migrated_value.target_id, ids["time_slice"])
        self.assertEqual((migrated_value.status, migrated_value.value), ("CONFIRMED", 0))

    def test_clean_migration_creates_conditional_legacy_and_canonical_constraints(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor,
                ParameterDefinition._meta.db_table,
            )
        required = {
            "domain_parameter_legacy_project_code_uniq",
            "domain_parameter_definition_code_uniq",
            "domain_parameter_definition_source_uniq",
            "domain_parameter_canonical_bridge_pair",
            "domain_parameter_scale_step_positive",
        }
        self.assertTrue(required.issubset(constraints), constraints)
        self.assertTrue(
            ParameterDefinition._meta.get_field("definition_version").null,
            "The additive upgrade must retain nullable legacy rows.",
        )
        self.assertTrue(
            ParameterDefinition._meta.get_field("source_manifest_parameter_id").null
        )
        self.assertEqual(
            ProjectWorkspace._meta.get_field("assessment_projection_status").default,
            AssessmentProjectionStatus.NOT_PROVEN,
        )

    def test_projection_requires_exact_published_workspace_definition_and_hash_pin(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        with self.assertRaises(ValidationError):
            self._time_and_set(workspace)
        self.assertFalse(TimeSlice.objects.filter(workspace=workspace).exists())
        baseline = _canonical_rows(workspace)
        table = connection.ops.quote_name(ProjectWorkspace._meta.db_table)
        hash_column = connection.ops.quote_name(
            ProjectWorkspace._meta.get_field("definition_manifest_hash").column
        )
        pk_column = connection.ops.quote_name(ProjectWorkspace._meta.pk.column)
        prepared_pk = ProjectWorkspace._meta.pk.get_db_prep_value(
            workspace.pk,
            connection,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {hash_column} = %s WHERE {pk_column} = %s",
                ["0" * 64, prepared_pk],
            )
        workspace.refresh_from_db()
        with self.assertRaises(AssessmentProjectionConflict):
            self._materialize(workspace, uuid4(), principal)
        self.assertEqual(_canonical_rows(workspace), baseline)
        self.assertFalse(
            AuditEvent.objects.filter(
                workspace=workspace,
                entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
            ).exists()
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {hash_column} = %s WHERE {pk_column} = %s",
                [definition.manifest_hash, prepared_pk],
            )
        workspace.refresh_from_db()
        self.assertEqual(workspace.definition_version_id, definition.pk)

    def test_projection_materializes_actor_element_role_hierarchy_with_deterministic_workspace_ids(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        operation = uuid4()
        self._materialize(workspace, operation, principal)
        verification = verify_workspace_assessment_projection(workspace)
        workspace.refresh_from_db()
        self.assertEqual(verification.status, AssessmentProjectionStatus.COMPLETE)
        self.assertEqual(workspace.assessment_projection_status, AssessmentProjectionStatus.COMPLETE)
        self.assertEqual(workspace.assessment_projection_sha256, verification.projection_sha256)
        self.assertIsNotNone(verification.receipt)

        rows = _canonical_rows(workspace)
        self.assertEqual(len(rows["actors"]), len(self.manifest["actors"]))
        self.assertEqual(
            len(rows["elements"]), len(self.manifest["analytical_elements"])
        )
        self.assertEqual(len(rows["roles"]), len(self.manifest["actor_element_roles"]))
        actor_by_source = {str(row.source_manifest_entity_id): row for row in rows["actors"]}
        element_by_source = {
            str(row.source_manifest_entity_id): row for row in rows["elements"]
        }
        role_by_source = {str(row.source_manifest_entity_id): row for row in rows["roles"]}
        self.assertEqual(
            actor_by_source[self.manifest["actors"][1]["id"]].parent_id,
            actor_by_source[self.manifest["actors"][0]["id"]].pk,
        )
        for source in self.manifest["actors"]:
            self.assertEqual(
                actor_by_source[source["id"]].source_manifest_entity_sha256,
                _canonical_json_sha256(source),
            )
        self.assertEqual(
            element_by_source[self.manifest["analytical_elements"][1]["id"]].parent_id,
            element_by_source[self.manifest["analytical_elements"][0]["id"]].pk,
        )
        for source in self.manifest["analytical_elements"]:
            self.assertEqual(
                element_by_source[source["id"]].source_manifest_entity_sha256,
                _canonical_json_sha256(source),
            )
        role_spec = self.manifest["actor_element_roles"][0]
        role = role_by_source[role_spec["id"]]
        self.assertEqual(role.actor_id, actor_by_source[role_spec["actor_id"]].pk)
        self.assertEqual(role.element_id, element_by_source[role_spec["element_id"]].pk)
        self.assertEqual(role.order, role_spec["order"])
        self.assertEqual(
            role.source_manifest_entity_sha256,
            _canonical_json_sha256(role_spec),
        )
        for source in self.manifest["actor_element_roles"]:
            source_role = role_by_source[source["id"]]
            self.assertEqual(source_role.order, source["order"])
            self.assertEqual(
                source_role.source_manifest_entity_sha256,
                _canonical_json_sha256(source),
            )
        mapping_before_replay = _source_mapping(workspace)
        self._materialize(workspace, operation, principal)
        self.assertEqual(_source_mapping(workspace), mapping_before_replay)
        self.assertEqual(
            AuditEvent.objects.filter(
                workspace=workspace,
                entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
            ).count(),
            1,
        )

    def test_two_workspaces_same_definition_have_distinct_rows_and_identical_source_mapping(self):
        definition, workspace_one, principal = self._bootstrap(projection_manifest=True)
        workspace_two = _make_workspace(
            definition=definition,
            project=self.project,
            code=f"FD08-SECOND-{uuid4().hex[:10]}",
        )
        self._materialize(workspace_one, uuid4(), principal)
        self._materialize(workspace_two, uuid4(), principal)
        one = _source_mapping(workspace_one)
        two = _source_mapping(workspace_two)
        for family in ("actors", "elements", "roles"):
            self.assertEqual([source for source, _ in one[family]], [source for source, _ in two[family]])
            self.assertNotEqual([row_id for _, row_id in one[family]], [row_id for _, row_id in two[family]])
        self.assertEqual(
            [source for source, _ in one["parameters"]],
            [source for source, _ in two["parameters"]],
        )
        self.assertEqual(
            [row_id for _, row_id in one["parameters"]],
            [row_id for _, row_id in two["parameters"]],
            "Definition-bound snapshots are shared by workspaces pinned to that exact definition.",
        )
        self.assertNotEqual(
            verify_workspace_assessment_projection(workspace_one).projection_sha256,
            verify_workspace_assessment_projection(workspace_two).projection_sha256,
            "The workspace identity is part of a canonical projection.",
        )
        package = export_workspace_package_2_2(workspace_one)
        baseline = _projection_semantic_counts()
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package_2_2(package, workspace=workspace_two)
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_2(package, workspace=workspace_two)
        self.assertEqual(_projection_semantic_counts(), baseline)
        empty_workspace = _make_workspace(
            definition=definition,
            project=self.project,
            code=f"FD08-EMPTY-{uuid4().hex[:10]}",
        )
        self.assertFalse(
            AuditEvent.objects.filter(
                workspace=empty_workspace,
                entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
            ).exists()
        )
        self.assertFalse(Actor.objects.filter(workspace=empty_workspace).exists())
        baseline = _projection_semantic_counts()
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_2(package, workspace=empty_workspace)
        self.assertEqual(_projection_semantic_counts(), baseline)

    def test_definition_bound_parameter_snapshots_are_exact_immutable_and_replay_safe(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        operation = uuid4()
        self._materialize(workspace, operation, principal)
        snapshots = list(
            ParameterDefinition.objects.filter(definition_version=definition).order_by(
                "source_manifest_parameter_id"
            )
        )
        expected = {
            item["id"]: item for item in self.manifest["parameter_definitions"]
        }
        self.assertEqual(len(snapshots), len(expected))
        for snapshot in snapshots:
            source = expected[str(snapshot.source_manifest_parameter_id)]
            self.assertEqual(snapshot.code, source["code"])
            self.assertEqual(snapshot.target_type, source["target_type"])
            self.assertEqual(snapshot.allowed_statuses, source["allowed_statuses"])
            self.assertEqual(snapshot.applicability, source["applicability"])
            self.assertEqual(snapshot.reference_statement, source["reference_statement"])
            self.assertEqual(
                snapshot.manifest_snapshot_sha256,
                _canonical_json_sha256(source),
            )
        package = export_workspace_package_2_2(workspace)
        self.assertEqual(validate_foundation_package_2_2(package), package)
        self.assertEqual(
            json.loads(export_workspace_json_2_2(workspace)),
            package,
        )
        self.assertEqual(package["format_version"], "2.2.0")
        self.assertEqual(
            package["package_scope"],
            "WORKSPACE_ASSESSMENT_PROJECTION",
        )
        self.assertNotIn("FULL_BACKUP", package)
        full_backup = copy.deepcopy(package)
        full_backup["package_scope"] = "FULL_BACKUP"
        with self.assertRaises(FoundationPackageValidationError):
            validate_foundation_package_2_2(full_backup)
        downgraded = copy.deepcopy(package)
        downgraded["format_version"] = "2.1.0"
        with self.assertRaises(FoundationPackageValidationError):
            validate_foundation_package_2_2(downgraded)
        self.assertEqual(package["selected_definition_id"], str(definition.pk))
        self.assertEqual(package["manifest"]["definition_id"], str(definition.pk))
        self.assertEqual(package["manifest"]["sha256"], definition.manifest_hash)
        self.assertEqual(package["manifest"]["payload"], definition.manifest)
        package_actors = {
            row["source_manifest_entity_id"]: row for row in package["actors"]
        }
        package_elements = {
            row["source_manifest_entity_id"]: row
            for row in package["analytical_elements"]
        }
        package_roles = {
            row["source_manifest_entity_id"]: row
            for row in package["actor_element_roles"]
        }
        for source in self.manifest["actors"]:
            exported = package_actors[source["id"]]
            self.assertEqual(exported["source_manifest_entity_sha256"], _canonical_json_sha256(source))
            self.assertEqual(exported["source_manifest_parent_id"], source["parent_id"])
            self.assertEqual(exported["order"], source["order"])
        for source in self.manifest["analytical_elements"]:
            exported = package_elements[source["id"]]
            self.assertEqual(exported["source_manifest_entity_sha256"], _canonical_json_sha256(source))
            self.assertEqual(exported["source_manifest_parent_id"], source["parent_id"])
            self.assertEqual(exported["order"], source["order"])
        for source in self.manifest["actor_element_roles"]:
            exported = package_roles[source["id"]]
            self.assertEqual(exported["source_manifest_entity_sha256"], _canonical_json_sha256(source))
            self.assertEqual(exported["source_manifest_actor_id"], source["actor_id"])
            self.assertEqual(exported["source_manifest_element_id"], source["element_id"])
            self.assertEqual(exported["source_manifest_order"], source["order"])
            self.assertEqual(exported["order"], source["order"])
        package_parameters = {
            row["source_manifest_parameter_id"]: row
            for row in package["parameter_definitions"]
        }
        for snapshot in snapshots:
            exported = package_parameters[str(snapshot.source_manifest_parameter_id)]
            self.assertEqual(exported["id"], str(snapshot.pk))
            self.assertEqual(exported["definition_version_id"], str(definition.pk))
            self.assertEqual(
                exported["manifest_snapshot_sha256"],
                snapshot.manifest_snapshot_sha256,
            )
        original = snapshots[0]
        original.name = "forbidden canonical rewrite"
        with self.assertRaises(ValidationError):
            original.save()
        with self.assertRaises(ValidationError):
            ParameterDefinition.objects.filter(pk=original.pk).update(name="forbidden")
        with self.assertRaises(ValidationError):
            ParameterDefinition.objects.filter(pk=original.pk).delete()
        with self.assertRaises(ValidationError):
            ParameterDefinition.objects.filter(pk=original.pk)._raw_delete(connection.alias)
        protected_rows = (
            _canonical_rows(workspace)["actors"][0],
            _canonical_rows(workspace)["elements"][0],
            _canonical_rows(workspace)["roles"][0],
            original,
        )
        for row in protected_rows:
            model = type(row)
            with self.subTest(d09="instance-update", model=model.__name__):
                row.code = f"FD08-INSTANCE-UPDATE-{uuid4().hex[:8]}"
                with self.assertRaises(ValidationError):
                    row.save()
            with self.subTest(d09="queryset-update", model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.objects.filter(pk=row.pk).update(
                        code=f"FD08-QUERYSET-UPDATE-{uuid4().hex[:8]}"
                    )
            with self.subTest(d09="bulk-update", model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.objects.bulk_update([row], ["code"])
            with self.subTest(d09="direct", model=model.__name__):
                with self.assertRaises(ValidationError):
                    row.delete()
            with self.subTest(d09="queryset", model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.objects.filter(pk=row.pk).delete()
            with self.subTest(d09="raw", model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.objects.filter(pk=row.pk)._raw_delete(connection.alias)
            with self.subTest(d09="database-raw", model=model.__name__):
                table = connection.ops.quote_name(model._meta.db_table)
                pk_column = connection.ops.quote_name(model._meta.pk.column)
                prepared_pk = model._meta.pk.get_db_prep_value(row.pk, connection)
                with self.assertRaises(DatabaseError):
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute(
                                f"DELETE FROM {table} WHERE {pk_column} = %s",
                                [prepared_pk],
                            )
            with self.subTest(d09="database-raw-update", model=model.__name__):
                table = connection.ops.quote_name(model._meta.db_table)
                pk_column = connection.ops.quote_name(model._meta.pk.column)
                code_column = connection.ops.quote_name(
                    model._meta.get_field("code").column
                )
                prepared_pk = model._meta.pk.get_db_prep_value(row.pk, connection)
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        with connection.cursor() as cursor:
                            cursor.execute(
                                f"UPDATE {table} SET {code_column} = %s "
                                f"WHERE {pk_column} = %s",
                                [f"FD08-RAW-UPDATE-{uuid4().hex[:8]}", prepared_pk],
                            )
        with self.subTest(d09="ancestor-cascade"):
            with self.assertRaises((ValidationError, RestrictedError)):
                ProjectWorkspace.objects.filter(pk=workspace.pk).delete()
            self.assertTrue(ProjectWorkspace.objects.filter(pk=workspace.pk).exists())
            self.assertTrue(Actor.objects.filter(pk=protected_rows[0].pk).exists())

        # The initial workspace also has bootstrap records with RESTRICT FKs, so
        # prove the actual cascade lane separately.  Removing only the derived
        # receipt by raw SQL leaves a non-initial workspace whose sole dependent
        # structure is the canonical projection.  A workspace queryset delete
        # must still fail closed rather than cascade through those rows.
        cascade_workspace = _make_workspace(
            definition=definition,
            project=self.project,
            code=f"FD08-CASCADE-{uuid4().hex[:10]}",
        )
        self._materialize(cascade_workspace, uuid4(), principal)
        cascade_actor = _canonical_rows(cascade_workspace)["actors"][0]
        receipt = AuditEvent.objects.get(
            workspace=cascade_workspace,
            entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
        )
        audit_table = connection.ops.quote_name(AuditEvent._meta.db_table)
        audit_pk = connection.ops.quote_name(AuditEvent._meta.pk.column)
        prepared_receipt_pk = AuditEvent._meta.pk.get_db_prep_value(
            receipt.pk,
            connection,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {audit_table} WHERE {audit_pk} = %s",
                [prepared_receipt_pk],
            )
        with self.subTest(d09="ancestor-cascade-without-receipt-blocker"):
            with self.assertRaises((ValidationError, IntegrityError)):
                ProjectWorkspace.objects.filter(pk=cascade_workspace.pk).delete()
            self.assertTrue(
                ProjectWorkspace.objects.filter(pk=cascade_workspace.pk).exists()
            )
            self.assertTrue(Actor.objects.filter(pk=cascade_actor.pk).exists())
        before = _source_mapping(workspace)
        self._materialize(workspace, operation, principal)
        self.assertEqual(_source_mapping(workspace), before)
        before_reconciliation = _projection_semantic_counts()
        preview = preview_foundation_package_2_2(package, workspace=workspace)
        self.assertTrue(preview.valid)
        self.assertEqual(preview.payload_copy(), package)
        reuse = commit_foundation_package_2_2(package, workspace=workspace)
        self.assertEqual(reuse.action, "REUSE_EXACT")
        self.assertEqual(reuse.workspace_id, str(workspace.pk))
        self.assertEqual(reuse.definition_id, str(definition.pk))
        self.assertEqual(
            reuse.receipt_id,
            package["projection"]["receipt"]["id"],
        )
        self.assertEqual(
            reuse.projection_sha256,
            package["projection"]["projection_sha256"],
        )
        self.assertEqual(_projection_semantic_counts(), before_reconciliation)

    def test_successor_definition_gets_separate_parameter_snapshots_without_rewriting_history(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        self._materialize(workspace, uuid4(), principal)
        predecessor_snapshot_ids = set(
            ParameterDefinition.objects.filter(definition_version=definition).values_list(
                "pk", flat=True
            )
        )
        successor = clone_project_definition_draft(
            definition,
            code=f"FD08-SUCCESSOR-{uuid4().hex[:10]}",
            version="2.0.0",
            principal=self.editor(actor="fd08-successor-editor"),
        )
        successor = validate_project_definition(
            successor,
            actor_identifier=principal.actor_identifier,
            principal=principal,
        )
        publish_successor_project_definition(successor, principal=principal, locale="en")
        successor_workspace = _make_workspace(
            definition=successor,
            project=self.project,
            code=f"FD08-SUCCESSOR-WS-{uuid4().hex[:10]}",
        )
        self._materialize(successor_workspace, uuid4(), principal)
        successor_snapshot_ids = set(
            ParameterDefinition.objects.filter(definition_version=successor).values_list(
                "pk", flat=True
            )
        )
        self.assertTrue(predecessor_snapshot_ids)
        self.assertTrue(successor_snapshot_ids)
        self.assertTrue(predecessor_snapshot_ids.isdisjoint(successor_snapshot_ids))
        self.assertEqual(
            list(
                ParameterDefinition.objects.filter(definition_version=definition)
                .order_by("source_manifest_parameter_id")
                .values_list("source_manifest_parameter_id", flat=True)
            ),
            list(
                ParameterDefinition.objects.filter(definition_version=successor)
                .order_by("source_manifest_parameter_id")
                .values_list("source_manifest_parameter_id", flat=True)
            ),
        )
        self.assertEqual(
            set(
                ParameterDefinition.objects.filter(definition_version=definition).values_list(
                    "pk", flat=True
                )
            ),
            predecessor_snapshot_ids,
        )
        predecessor_package = export_workspace_package_2_2(workspace)
        successor_package = export_workspace_package_2_2(successor_workspace)
        predecessor_parameters = predecessor_package["parameter_definitions"]
        successor_parameters = successor_package["parameter_definitions"]
        self.assertEqual(
            [row["code"] for row in predecessor_parameters],
            [row["code"] for row in successor_parameters],
            "A reused parameter code remains disambiguated by exact definition identity.",
        )
        self.assertEqual(
            [row["source_manifest_parameter_id"] for row in predecessor_parameters],
            [row["source_manifest_parameter_id"] for row in successor_parameters],
        )
        self.assertTrue(
            all(
                row["definition_version_id"] == str(definition.pk)
                for row in predecessor_parameters
            )
        )
        self.assertTrue(
            all(
                row["definition_version_id"] == str(successor.pk)
                for row in successor_parameters
            )
        )
        self.assertNotEqual(
            [row["id"] for row in predecessor_parameters],
            [row["id"] for row in successor_parameters],
        )
        before_wrong_target = _projection_semantic_counts()
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package_2_2(successor_package, workspace=workspace)
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_2(successor_package, workspace=workspace)
        self.assertEqual(_projection_semantic_counts(), before_wrong_target)
        self.assertEqual(
            verify_workspace_assessment_projection(workspace).status,
            AssessmentProjectionStatus.COMPLETE,
        )

    def test_canonical_parameter_values_accept_only_exact_workspace_actor_element_role_targets(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        workspace_two = _make_workspace(
            definition=definition,
            project=self.project,
            code=f"FD08-VALUE-OTHER-{uuid4().hex[:10]}",
        )
        self._materialize(workspace, uuid4(), principal)
        self._materialize(workspace_two, uuid4(), principal)
        time_slice, assessment_set = self._time_and_set(workspace)
        source_to_target = {
            TargetType.ACTOR: Actor.objects.get(
                workspace=workspace,
                source_manifest_entity_id=self.manifest["actors"][0]["id"],
            ),
            TargetType.ANALYTICAL_ELEMENT: AnalyticalElement.objects.get(
                workspace=workspace,
                source_manifest_entity_id=self.manifest["analytical_elements"][0]["id"],
            ),
            TargetType.ACTOR_ELEMENT_ROLE: ActorElementRole.objects.get(
                workspace=workspace,
                source_manifest_entity_id=self.manifest["actor_element_roles"][0]["id"],
            ),
        }
        parameters = {
            row.target_type: row
            for row in ParameterDefinition.objects.filter(definition_version=definition)
        }
        for target_type, target in source_to_target.items():
            value = self._parameter_value(
                workspace=workspace,
                time_slice=time_slice,
                assessment_set=assessment_set,
                parameter=parameters[target_type],
                target_type=target_type,
                target_id=target.pk,
            )
            value.save()
            self.assertEqual((value.status, value.value), (ValueStatus.UNKNOWN, None))

        foreign_actor = Actor.objects.get(
            workspace=workspace_two,
            source_manifest_entity_id=self.manifest["actors"][0]["id"],
        )
        wrong_workspace = self._parameter_value(
            workspace=workspace,
            time_slice=time_slice,
            assessment_set=assessment_set,
            parameter=parameters[TargetType.ACTOR],
            target_type=TargetType.ACTOR,
            target_id=foreign_actor.pk,
        )
        with self.assertRaises(ValidationError):
            wrong_workspace.save()
        inapplicable_actor = Actor.objects.get(
            workspace=workspace,
            source_manifest_entity_id=self.manifest["actors"][1]["id"],
        )
        inapplicable = self._parameter_value(
            workspace=workspace,
            time_slice=time_slice,
            assessment_set=assessment_set,
            parameter=parameters[TargetType.ACTOR],
            target_type=TargetType.ACTOR,
            target_id=inapplicable_actor.pk,
        )
        with self.assertRaises(ValidationError):
            inapplicable.save()

    def test_legacy_targets_remain_backward_only_and_no_tension_group_rows_are_created(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        self.assertFalse(Actor.objects.filter(workspace=workspace).exists())
        self._materialize(workspace, uuid4(), principal)
        from domain.models import GroupTensionRelation, ParticipantGroup, TensionPoint

        self.assertFalse(ParticipantGroup.objects.filter(project=self.project).exists())
        self.assertFalse(TensionPoint.objects.filter(project=self.project).exists())
        self.assertFalse(GroupTensionRelation.objects.filter(project=self.project).exists())
        legacy = ParameterDefinition.objects.create(
            id=uuid4(),
            project=self.project,
            code=f"FD08-LEGACY-{uuid4().hex[:10]}",
            version="1.0.0",
            name="Legacy target",
            description="Legacy rows remain outside canonical provenance.",
            target_type=TargetType.TIME_SLICE,
            value_type="INTEGER",
            scale_min=-10,
            scale_max=10,
            scale_metadata={},
        )
        time_slice, assessment_set = self._time_and_set(workspace)
        legacy_value = self._parameter_value(
            workspace=workspace,
            time_slice=time_slice,
            assessment_set=assessment_set,
            parameter=legacy,
            target_type=TargetType.TIME_SLICE,
            target_id=time_slice.pk,
        )
        legacy_value.save()
        legacy.refresh_from_db()
        self.assertIsNone(legacy.definition_version_id)
        self.assertEqual(legacy_value.target_id, time_slice.pk)
        self.assertEqual((legacy_value.status, legacy_value.value), (ValueStatus.UNKNOWN, None))
        self.assertEqual(
            ParameterDefinition.objects.filter(definition_version=definition).count(),
            len(self.manifest["parameter_definitions"]),
        )

    def test_partial_extra_or_drifted_projection_fails_closed_without_repair(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        operation = uuid4()
        self._materialize(workspace, operation, principal)
        original_package = export_workspace_package_2_2(workspace)
        with _canonical_assessment_projection_write("projection"):
            extra = Actor.objects.create(
                id=uuid4(),
                workspace=workspace,
                code=f"FD08-EXTRA-{uuid4().hex[:10]}",
                version="1.0.0",
                actor_type="GROUP",
                label="Unexpected canonical row",
                description="Must not be silently removed by projection replay.",
                order=99,
                metadata={},
                source_manifest_entity_id=uuid4(),
                source_manifest_entity_sha256="a" * 64,
            )
        before = _source_mapping(workspace)
        with self.assertRaises(AssessmentProjectionConflict):
            self._materialize(workspace, operation, principal)
        self.assertTrue(Actor.objects.filter(pk=extra.pk).exists())
        self.assertEqual(_source_mapping(workspace), before)
        before_graph_refusal = _projection_semantic_counts()
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package_2_2(original_package, workspace=workspace)
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_2(original_package, workspace=workspace)
        self.assertEqual(_projection_semantic_counts(), before_graph_refusal)

        partial_workspace = _make_workspace(
            definition=definition,
            project=self.project,
            code=f"FD08-PARTIAL-{uuid4().hex[:10]}",
        )
        with _canonical_assessment_projection_write("projection"):
            partial = Actor.objects.create(
                id=uuid4(),
                workspace=partial_workspace,
                code=f"FD08-PARTIAL-ACTOR-{uuid4().hex[:10]}",
                version="1.0.0",
                actor_type="GROUP",
                label="Incomplete canonical graph",
                description="A partial graph must never be completed or repaired.",
                order=0,
                metadata={},
                source_manifest_entity_id=uuid4(),
                source_manifest_entity_sha256="b" * 64,
            )
        with self.assertRaises(AssessmentProjectionConflict):
            self._materialize(partial_workspace, uuid4(), principal)
        self.assertTrue(Actor.objects.filter(pk=partial.pk).exists())
        self.assertFalse(
            AuditEvent.objects.filter(
                workspace=partial_workspace,
                entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
            ).exists()
        )

        drift_workspace = _make_workspace(
            definition=definition,
            project=self.project,
            code=f"FD08-DRIFT-{uuid4().hex[:10]}",
        )
        drift_operation = uuid4()
        self._materialize(drift_workspace, drift_operation, principal)
        drift_package = export_workspace_package_2_2(drift_workspace)
        workspace_table = connection.ops.quote_name(ProjectWorkspace._meta.db_table)
        workspace_pk = connection.ops.quote_name(ProjectWorkspace._meta.pk.column)
        workspace_sha = connection.ops.quote_name(
            ProjectWorkspace._meta.get_field("assessment_projection_sha256").column
        )
        prepared_workspace_pk = ProjectWorkspace._meta.pk.get_db_prep_value(
            drift_workspace.pk,
            connection,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {workspace_table} SET {workspace_sha} = %s "
                f"WHERE {workspace_pk} = %s",
                ["c" * 64, prepared_workspace_pk],
            )
        with self.assertRaises(AssessmentProjectionConflict):
            self._materialize(drift_workspace, drift_operation, principal)
        drift_workspace.refresh_from_db()
        self.assertEqual(drift_workspace.assessment_projection_sha256, "c" * 64)
        self.assertEqual(
            verify_workspace_assessment_projection(drift_workspace).status,
            AssessmentProjectionStatus.INTEGRITY_CONFLICT,
        )
        before_evidence_refusal = _projection_semantic_counts()
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package_2_2(drift_package, workspace=drift_workspace)
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_2(drift_package, workspace=drift_workspace)
        self.assertEqual(_projection_semantic_counts(), before_evidence_refusal)

        receiptless_workspace = _make_workspace(
            definition=definition,
            project=self.project,
            code=f"FD08-RECEIPTLESS-{uuid4().hex[:10]}",
        )
        self._materialize(receiptless_workspace, uuid4(), principal)
        receiptless_package = export_workspace_package_2_2(receiptless_workspace)
        receiptless_receipt = AuditEvent.objects.get(
            workspace=receiptless_workspace,
            entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
        )
        audit_table = connection.ops.quote_name(AuditEvent._meta.db_table)
        audit_pk = connection.ops.quote_name(AuditEvent._meta.pk.column)
        prepared_receipt_pk = AuditEvent._meta.pk.get_db_prep_value(
            receiptless_receipt.pk,
            connection,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {audit_table} WHERE {audit_pk} = %s",
                [prepared_receipt_pk],
            )
        before_receipt_refusal = _projection_semantic_counts()
        with self.assertRaises(FoundationPackageConflictError):
            preview_foundation_package_2_2(
                receiptless_package,
                workspace=receiptless_workspace,
            )
        with self.assertRaises(FoundationPackageConflictError):
            commit_foundation_package_2_2(
                receiptless_package,
                workspace=receiptless_workspace,
            )
        self.assertEqual(_projection_semantic_counts(), before_receipt_refusal)

    def test_every_projection_failure_stage_rolls_back_rows_and_immutable_receipt(self):
        definition, workspace, principal = self._bootstrap(projection_manifest=True)
        stages = (
            "after_actors",
            "after_elements",
            "after_roles",
            "after_parameters",
            "before_receipt",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                candidate = _make_workspace(
                    definition=definition,
                    project=self.project,
                    code=f"FD08-FAIL-{stage}-{uuid4().hex[:8]}",
                )
                with self.assertRaises(AssessmentProjectionError):
                    self._materialize(
                        candidate,
                        uuid4(),
                        principal,
                        inject_failure_at=stage,
                    )
                rows = _canonical_rows(candidate)
                self.assertFalse(rows["actors"])
                self.assertFalse(rows["elements"])
                self.assertFalse(rows["roles"])
                self.assertFalse(
                    AuditEvent.objects.filter(
                        workspace=candidate,
                        entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
                    ).exists()
                )
                candidate.refresh_from_db()
                self.assertEqual(
                    candidate.assessment_projection_status,
                    AssessmentProjectionStatus.NOT_PROVEN,
                )
                self.assertIsNone(candidate.assessment_projection_sha256)
        self.assertFalse(_canonical_rows(workspace)["actors"])


@skipUnless(connection.vendor == "postgresql", "requires PostgreSQL")
class FoundationWorkspaceAssessmentProjectionPostgreSQLTests(
    _FD08ProjectionGuardTeardownMixin,
    FoundationStudioBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def _bootstrap(self):
        self.make_contract()
        self.manifest = _projection_manifest(self.manifest)
        definition = self.draft(code=f"FD08-PG-{uuid4().hex[:12]}")
        principal = self.publisher(actor="fd08-postgresql-human")
        bootstrap = bootstrap_initial_project_definition(
            definition=definition,
            principal=principal,
            actor_identifier=principal.actor_identifier,
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        return bootstrap.workspace, principal

    @staticmethod
    def _race(workspace_id, operation_ids, principal):
        barrier = threading.Barrier(len(operation_ids))
        lock = threading.Lock()
        outcomes: list[tuple[str, object]] = []

        def worker(operation_identity):
            close_old_connections()
            try:
                workspace = ProjectWorkspace.objects.get(pk=workspace_id)
                barrier.wait(timeout=15)
                result = materialize_workspace_assessment_projection(
                    workspace,
                    operation_identity,
                    getattr(principal, "actor_identifier", principal),
                )
                outcome: tuple[str, object] = ("result", result)
            except Exception as exc:  # captured so both contenders join deterministically
                outcome = ("error", exc)
            finally:
                close_old_connections()
            with lock:
                outcomes.append(outcome)

        threads = [threading.Thread(target=worker, args=(identity,)) for identity in operation_ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
            if thread.is_alive():
                raise AssertionError("FD08 projection contender did not finish")
        return outcomes

    def test_concurrent_same_workspace_projection_has_one_commit_and_one_exact_replay(self):
        workspace, principal = self._bootstrap()
        operation = uuid4()
        outcomes = self._race(workspace.pk, (operation, operation), principal)
        self.assertEqual([kind for kind, _ in outcomes].count("error"), 0, outcomes)
        self.assertEqual([kind for kind, _ in outcomes].count("result"), 2, outcomes)
        workspace.refresh_from_db()
        verification = verify_workspace_assessment_projection(workspace)
        self.assertEqual(verification.status, AssessmentProjectionStatus.COMPLETE)
        self.assertEqual(
            AuditEvent.objects.filter(
                workspace=workspace,
                entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
            ).count(),
            1,
        )
        self.assertEqual(len(_canonical_rows(workspace)["actors"]), len(self.manifest["actors"]))

    def test_competing_projection_identity_or_snapshot_has_one_commit_and_one_typed_loser(self):
        workspace, principal = self._bootstrap()
        outcomes = self._race(workspace.pk, (uuid4(), uuid4()), principal)
        results = [value for kind, value in outcomes if kind == "result"]
        errors = [value for kind, value in outcomes if kind == "error"]
        self.assertEqual(len(results), 1, outcomes)
        self.assertEqual(len(errors), 1, outcomes)
        self.assertIsInstance(errors[0], AssessmentProjectionConflict)
        workspace.refresh_from_db()
        self.assertEqual(verify_workspace_assessment_projection(workspace).status, AssessmentProjectionStatus.COMPLETE)
        self.assertEqual(
            AuditEvent.objects.filter(
                workspace=workspace,
                entity_type=_PROJECTION_RECEIPT_ENTITY_TYPE,
            ).count(),
            1,
        )
