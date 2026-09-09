"""Exact predecessor installation and private SYSTEM projection regression gate."""
from django.test import TestCase
from domain.services.seed import seed_zhanaozen_demo, _verify_typed_installation
from domain.services import zhanaozen_typed_manifest as typed
from domain.models import ProjectDefinitionVersion, ProjectWorkspace, ProjectPublication, TimeSlice, AuditEvent


class ZhanaozenTypedManifestRepairTests(TestCase):
    def test_fresh_and_replay(self):
        project = seed_zhanaozen_demo()
        _verify_typed_installation(project)
        models = (ProjectDefinitionVersion, ProjectWorkspace, ProjectPublication, TimeSlice, AuditEvent)
        before = [list(m.objects.order_by("pk").values()) for m in models]
        seed_zhanaozen_demo()
        seed_zhanaozen_demo()
        self.assertEqual(before, [list(m.objects.order_by("pk").values()) for m in models])
        self.assertEqual(TimeSlice.objects.filter(project=project).count(), 6)
        self.assertEqual(ProjectPublication.objects.filter(project=project).count(), 3)
        self.assertEqual(AuditEvent.objects.get(pk=typed.PROJECTION_RECEIPT_ID).after, typed.system_audit()["after"])


import hashlib
import json
import threading
from unittest import skipUnless
from unittest.mock import patch
from uuid import UUID, uuid4, uuid5
from django.db import connection, connections, close_old_connections, transaction
from django.test import TransactionTestCase
from domain.models import (
    Project, Actor, AnalyticalElement, ActorElementRole, ParameterDefinition,
    ParameterValue, AssessmentSet, Experiment, ImportRun, EvidenceSource, EvidenceLink,
)
from domain.policies import StudioPrincipal
from domain.services.seed import SeedConflictError, _system_principal
from domain.services import player_projection as projection
from domain.services.project_definitions import canonicalize_project_definition_manifest_v1
from domain.services.project_packages import export_project_json, import_project_package


def _snapshot():
    return {model.__name__: list(model.objects.order_by("pk").values()) for model in (
        Project, ProjectDefinitionVersion, ProjectWorkspace, ProjectPublication,
        TimeSlice, Actor, AnalyticalElement, ActorElementRole, ParameterDefinition,
        AuditEvent, AssessmentSet,
    )}


def _accepted_legacy_seed():
    # Exact accepted-G7 service is a frozen upgrade fixture, never a runtime fallback.
    raw = _ACCEPTED_LEGACY_SEED.encode("utf-8")
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == (
        "cc03537defa0a750e970faab7480718f188f045d"
    )
    namespace = {"__name__": "frozen_accepted_g7_seed"}
    exec(compile(raw, "<accepted-G7 seed fixture>", "exec"), namespace)
    return namespace["seed_zhanaozen_demo"]()


class ZhanaozenRepairIntegrityTests(TestCase):
    def test_project_version_drift_is_not_repaired(self):
        project = _accepted_legacy_seed()
        Project.objects.filter(pk=project.pk).update(version="9.0.0")
        before = _snapshot()
        with self.assertRaises(SeedConflictError):
            seed_zhanaozen_demo()
        self.assertEqual(before, _snapshot())

    def test_duplicate_system_receipt_is_not_adopted(self):
        seed_zhanaozen_demo()
        row = typed.system_audit()
        row.update(id=uuid4(), code="DUPLICATE-SYSTEM-RECEIPT")
        AuditEvent.objects.create(**row)
        before = _snapshot()
        with self.assertRaises(SeedConflictError):
            seed_zhanaozen_demo()
        self.assertEqual(before, _snapshot())

    def test_unreceipted_partial_system_graph_rolls_back(self):
        original = projection._materialize_zhanaozen_system_projection
        def inject_partial(workspace, *, principal):
            from domain.models import _canonical_assessment_projection_write
            item = projection._expected_projection(workspace)["actors"][0]
            with _canonical_assessment_projection_write("projection"):
                projection._create_ordered_tree(workspace=workspace, expected=[item], model=Actor, kind="ACTOR")
            return original(workspace, principal=principal)
        with patch.object(projection, "_materialize_zhanaozen_system_projection", inject_partial):
            with self.assertRaises(SeedConflictError):
                seed_zhanaozen_demo()
        self.assertFalse(Project.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_exact_fixture(self):
        manifest = typed.manifest()
        raw = canonicalize_project_definition_manifest_v1(manifest)
        self.assertEqual(len(raw), 42602)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "6f149d681d4413d0e8f5cb61c2ed790cf277a385b900b2db35395794c94391ca")
        self.assertEqual([len(manifest[k]) for k in ("actors", "analytical_elements", "actor_element_roles", "parameter_definitions")], [8, 6, 48, 2])
        for role in manifest["actor_element_roles"]:
            self.assertEqual(str(uuid5(UUID(typed.PROJECT_ID), f"PROJECT_DEFINITION_MANIFEST_V1:TECHNICAL_OTHER_ROLE:{role['actor_id']}:{role['element_id']}")), role["id"])
            self.assertEqual(role["note"], "Technical applicability bridge only; no substantive actor-role classification.")
            self.assertEqual(role["role"], "OTHER")
        for item in typed.time_slices():
            self.assertEqual(str(uuid5(UUID(typed.WORKSPACE_ID), "PROJECT_DEFINITION_MANIFEST_V1:TIME_SLICE:"+item["code"])), item["typed_pk"])
            self.assertNotEqual(item["legacy_pk"], item["typed_pk"])

    def test_upgrade_preserves_accepted_legacy_bytes_and_timestamps(self):
        project = _accepted_legacy_seed()
        before = _snapshot()
        seed_zhanaozen_demo()
        after = _snapshot()
        for model in ("Project", "ProjectWorkspace", "ProjectPublication", "TimeSlice"):
            for row in before[model]:
                self.assertIn(row, after[model], model)
        old_definition = before["ProjectDefinitionVersion"][0]
        old_definition["is_current"] = False  # sole canonical successor transition
        self.assertIn(old_definition, after["ProjectDefinitionVersion"])
        self.assertEqual(Project.objects.get(pk=project.pk).version, "1.0.0")

    def test_system_projection_and_human_sibling(self):
        project = seed_zhanaozen_demo()
        workspace = ProjectWorkspace.objects.get(pk=typed.WORKSPACE_ID)
        verification = projection.verify_workspace_assessment_projection(workspace)
        self.assertTrue(verification.complete)
        self.assertEqual(verification.receipt.after, typed.system_audit()["after"])
        self.assertEqual(projection._sha256(verification.receipt.after), "58d5e14b7576e1b714464728de6a03185311186c6f6eb05ca5435bb101071c89")
        before = _snapshot()
        result = projection._materialize_zhanaozen_system_projection(workspace, principal=_system_principal())
        self.assertTrue(result.replayed)
        self.assertEqual(before, _snapshot())
        sibling = ProjectWorkspace.objects.create(project=project, definition_version=workspace.definition_version,
            definition_manifest_hash=typed.MANIFEST_SHA256, code="HUMAN-SIBLING", name="Human sibling", is_default=False)
        human = projection.materialize_workspace_assessment_projection(sibling, uuid4(), "human-test")
        self.assertEqual(human.receipt.actor_type, "HUMAN")
        self.assertEqual(human.receipt.entity_type, projection.PROJECTION_CONTRACT)
        self.assertTrue(projection.verify_workspace_assessment_projection(sibling).complete)
        self.assertEqual(ParameterDefinition.objects.filter(definition_version_id=typed.DEFINITION_ID).count(), 2)

    def test_replay_preserves_future_typed_assessment_set(self):
        project = seed_zhanaozen_demo()
        future = AssessmentSet.objects.create(project=project, workspace_id=typed.WORKSPACE_ID,
            code="FUTURE-G8-REPRESENTATIVE", name="Representative typed set", kind="HUMAN")
        before = _snapshot()
        seed_zhanaozen_demo()
        seed_zhanaozen_demo()
        self.assertEqual(before, _snapshot())
        self.assertTrue(AssessmentSet.objects.filter(pk=future.pk).exists())

    def test_legacy_membership_remains_exact(self):
        project = seed_zhanaozen_demo()
        AssessmentSet.objects.create(project=project, workspace_id=typed.LEGACY_WORKSPACE_ID,
            code="UNEXPECTED-LEGACY", name="Contamination", kind="HUMAN")
        before = _snapshot()
        with self.assertRaises(SeedConflictError):
            seed_zhanaozen_demo()
        self.assertEqual(before, _snapshot())

    def test_no_canonical_value_or_evidence_seed(self):
        seed_zhanaozen_demo()
        for model in (AssessmentSet, Experiment):
            self.assertFalse(model.objects.filter(workspace_id=typed.WORKSPACE_ID).exists())
        for model in (ParameterValue, ImportRun, EvidenceSource, EvidenceLink):
            self.assertFalse(model.objects.exists(), model.__name__)

    def test_wrong_service_context_and_public_contract_fail_without_writes(self):
        seed_zhanaozen_demo()
        workspace = ProjectWorkspace.objects.get(pk=typed.WORKSPACE_ID)
        before = _snapshot()
        principals = [None, StudioPrincipal.service(actor_identifier=typed.SYSTEM_ACTOR,
            purpose="different-purpose", capabilities=typed.SYSTEM_CAPABILITIES),
            StudioPrincipal.service(actor_identifier=typed.SYSTEM_ACTOR, purpose=typed.SYSTEM_PURPOSE,
                capabilities=typed.SYSTEM_CAPABILITIES | {"DEFINITION_READ"}),
            StudioPrincipal.service(actor_identifier="SYSTEM:OTHER", purpose=typed.SYSTEM_PURPOSE,
                capabilities=typed.SYSTEM_CAPABILITIES)]
        for principal in principals:
            with self.assertRaises(projection.AssessmentProjectionConflict):
                projection._materialize_zhanaozen_system_projection(workspace, principal=principal)
        with self.assertRaises(projection.AssessmentProjectionError):
            projection.materialize_workspace_assessment_projection(workspace, uuid4(), "human-test",
                receipt_contract=typed.SYSTEM_CONTRACT)
        with self.assertRaises(TypeError):
            projection._materialize_zhanaozen_system_projection(workspace, principal=_system_principal(),
                projection_sha256=typed.MANIFEST_SHA256)
        self.assertEqual(before, _snapshot())

    def test_each_projection_failure_rolls_back_entire_installation(self):
        original = projection._materialize_zhanaozen_system_projection
        for stage in ("after_actors", "after_elements", "after_roles", "after_parameters", "before_receipt"):
            with self.subTest(stage=stage):
                with patch.object(projection, "_materialize_zhanaozen_system_projection",
                    side_effect=lambda ws, *, principal: original(ws, principal=principal, inject_failure_at=stage)):
                    with self.assertRaises(SeedConflictError):
                        seed_zhanaozen_demo()
                self.assertFalse(Project.objects.exists())
                self.assertFalse(AuditEvent.objects.exists())

    def test_lifecycle_and_slice_failures_roll_back(self):
        from domain import policies
        for name in ("validate_project_definition", "publish_project_definition"):
            with self.subTest(stage=name):
                with patch.object(policies, name, side_effect=SeedConflictError("failure")):
                    with self.assertRaises(SeedConflictError):
                        seed_zhanaozen_demo()
                self.assertFalse(Project.objects.exists())
        original = TimeSlice.save
        def reject_typed(obj, *args, **kwargs):
            if str(obj.workspace_id) == typed.WORKSPACE_ID and obj.order == 2:
                self.assertTrue(projection.verify_workspace_assessment_projection(obj.workspace).complete)
                self.assertEqual(TimeSlice.objects.filter(workspace=obj.workspace).count(), 1)
                raise SeedConflictError("failure at typed slice")
            return original(obj, *args, **kwargs)
        with patch.object(TimeSlice, "save", reject_typed):
            with self.assertRaises(SeedConflictError):
                seed_zhanaozen_demo()
        self.assertFalse(Project.objects.exists())

    def test_graph_drift_and_partial_receipt_fail_closed(self):
        seed_zhanaozen_demo()
        workspace = ProjectWorkspace.objects.get(pk=typed.WORKSPACE_ID)
        # Simulate out-of-service storage corruption; production guards stay enabled.
        with connection.cursor() as cursor:
            cursor.execute(f"UPDATE {connection.ops.quote_name(ProjectWorkspace._meta.db_table)} SET assessment_projection_sha256 = %s WHERE id = %s",
                ["c" * 64, ProjectWorkspace._meta.pk.get_db_prep_value(workspace.pk, connection)])
        before = _snapshot()
        self.assertFalse(projection.verify_workspace_assessment_projection(workspace).complete)
        with self.assertRaises(SeedConflictError):
            seed_zhanaozen_demo()
        self.assertEqual(before, _snapshot())

    def test_v1_roundtrip_after_typed_install(self):
        savepoint = transaction.savepoint()
        project = seed_zhanaozen_demo()
        text = export_project_json(project)
        payload = json.loads(text)
        self.assertEqual(len(payload["time_slices"]), 3)
        self.assertEqual({p["code"] for p in payload["parameter_definitions"]}, {"UOS", "KVS", "RGU", "KVPTN"})
        transaction.savepoint_rollback(savepoint)
        restored = import_project_package(payload)
        self.assertEqual(export_project_json(restored), text)


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row-lock concurrency gate")
class ZhanaozenRepairConcurrentTests(TransactionTestCase):
    def test_postgresql_concurrent_bootstrap(self):
        barrier = threading.Barrier(2)
        results = []
        def install():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                results.append(("installed", str(seed_zhanaozen_demo().pk)))
            except SeedConflictError as exc:
                results.append(("conflict", str(exc)))
            except BaseException as exc:
                results.append(("unexpected", repr(exc)))
            finally:
                connections.close_all()
        workers = [threading.Thread(target=install) for _ in range(2)]
        for worker in workers: worker.start()
        for worker in workers: worker.join(timeout=60)
        self.assertTrue(all(not worker.is_alive() for worker in workers))
        self.assertEqual(len(results), 2)
        self.assertNotIn("unexpected", [status for status, _ in results], results)
        self.assertIn(("installed", typed.PROJECT_ID), results)
        project = Project.objects.get(pk=typed.PROJECT_ID)
        _verify_typed_installation(project)
        self.assertEqual(ProjectWorkspace.objects.filter(project=project).count(), 2)


_ACCEPTED_LEGACY_SEED = '"""Installation service for the versioned Zhanaozen demo seed."""\n\nfrom __future__ import annotations\n\nimport hashlib\nimport json\nfrom datetime import date, datetime, timezone\nfrom typing import Any, TypeVar\nfrom uuid import UUID\n\nfrom django.db import models, transaction\n\nfrom domain.demo_data import (\n    ASSESSMENT_SETS,\n    PARTICIPANT_GROUPS,\n    PARAMETER_DEFINITIONS,\n    GU_VERSION,\n    PROJECT_CODE,\n    PROJECT_NAME,\n    PTN_VERSION,\n    SCHEMA_VERSION,\n    SEED_VERSION,\n    TENSION_POINTS,\n    TIME_SLICES,\n    stable_demo_uuid,\n)\nfrom domain.models import (\n    AssessmentSet,\n    ExpertProfile,\n    Experiment,\n    GroupTensionRelation,\n    ParameterDefinition,\n    ParticipantGroup,\n    Project,\n    ProjectDefinitionVersion,\n    ProjectPrimaryLanguageAssignment,\n    ProjectLock,\n    ProjectPublication,\n    ProjectSchemaVersion,\n    ProjectWorkspace,\n    TensionPoint,\n    TimeSlice,\n)\n\n\nclass SeedConflictError(ValueError):\n    """Existing data conflicts with the stable identity of the demo seed."""\n\n\nModelT = TypeVar("ModelT", bound=models.Model)\n\n\ndef _canonical_json(value: Any) -> str:\n    return json.dumps(\n        value,\n        ensure_ascii=False,\n        sort_keys=True,\n        separators=(",", ":"),\n    )\n\n\ndef _stable_manifest() -> tuple[dict[str, Any], str]:\n    manifest = {\n        "seed_version": SEED_VERSION,\n        "schema_version": SCHEMA_VERSION,\n        "project_code": PROJECT_CODE,\n        "ptn_version": PTN_VERSION,\n        "gu_version": GU_VERSION,\n        "time_slices": [item["code"] for item in TIME_SLICES],\n        "tension_points": [item["code"] for item in TENSION_POINTS],\n        "participant_groups": [item["code"] for item in PARTICIPANT_GROUPS],\n        "assessment_sets": [item["code"] for item in ASSESSMENT_SETS],\n        "parameter_definitions": [\n            {"code": item["code"], "version": item["version"]}\n            for item in PARAMETER_DEFINITIONS\n        ],\n    }\n    digest = hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()\n    return manifest, digest\n\n\ndef _assert_stable_identity(\n    model: type[ModelT],\n    *,\n    object_id: UUID,\n    code: str,\n    project: Project | None = None,\n) -> None:\n    identity_match = model.objects.filter(pk=object_id).first()\n    if identity_match is not None and identity_match.code != code:\n        raise SeedConflictError(\n            f"{model.__name__} id {object_id} already belongs to code "\n            f"{identity_match.code!r}."\n        )\n    if (\n        identity_match is not None\n        and project is not None\n        and getattr(identity_match, "project_id", project.id) != project.id\n    ):\n        raise SeedConflictError(\n            f"{model.__name__} id {object_id} belongs to a different project."\n        )\n\n    code_query: dict[str, Any] = {"code": code}\n    if project is not None:\n        code_query["project"] = project\n    code_match = model.objects.filter(**code_query).first()\n    if code_match is not None and code_match.pk != object_id:\n        raise SeedConflictError(\n            f"{model.__name__} code {code!r} already has a different stable id."\n        )\n\n\ndef _upsert(\n    model: type[ModelT],\n    *,\n    object_id: UUID,\n    code: str,\n    defaults: dict[str, Any],\n    project: Project | None = None,\n) -> ModelT:\n    _assert_stable_identity(\n        model,\n        object_id=object_id,\n        code=code,\n        project=project,\n    )\n    obj, _ = model.objects.update_or_create(\n        pk=object_id,\n        defaults={"code": code, **defaults},\n    )\n    return obj\n\n\ndef _require_exact_codes(\n    model: type[ModelT], project: Project, expected_codes: set[str]\n) -> None:\n    actual_codes = set(model.objects.filter(project=project).values_list("code", flat=True))\n    if actual_codes != expected_codes:\n        unexpected = sorted(actual_codes - expected_codes)\n        missing = sorted(expected_codes - actual_codes)\n        raise SeedConflictError(\n            f"{model.__name__} seed membership drift: unexpected={unexpected}, "\n            f"missing={missing}."\n        )\n\n\n@transaction.atomic\ndef seed_zhanaozen_demo() -> Project:\n    """Create or refresh the demo project without duplicating stable entities.\n\n    The service never deletes or silently adopts unexpected structural rows.  A\n    drifted demo project is rejected and the transaction rolls back, preserving\n    the owner-approved seed membership.\n    """\n\n    project_id = stable_demo_uuid("project", PROJECT_CODE)\n    _assert_stable_identity(Project, object_id=project_id, code=PROJECT_CODE)\n    existing_project = Project.objects.filter(pk=project_id).first()\n    if existing_project is not None and (\n        existing_project.primary_language_tag != "ru"\n        or existing_project.primary_language_assignment\n        != ProjectPrimaryLanguageAssignment.EXPLICIT\n    ):\n        raise SeedConflictError(\n            "The stable Zhanaozen Project identity has a different immutable "\n            "primary language."\n        )\n    project = _upsert(\n        Project,\n        object_id=project_id,\n        code=PROJECT_CODE,\n        defaults={\n            "version": SCHEMA_VERSION,\n            "name": PROJECT_NAME,\n            "description": "",\n            "primary_language_tag": "ru",\n            "primary_language_assignment": (\n                ProjectPrimaryLanguageAssignment.EXPLICIT\n            ),\n            "metadata": {\n                "seed_version": SEED_VERSION,\n                "compatibility_profile": "V1_LEGACY_REGRESSION_ONLY",\n            },\n        },\n    )\n\n    seed_manifest, seed_manifest_hash = _stable_manifest()\n    definition_code = f"DEFINITION-{SCHEMA_VERSION}"\n    ProjectDefinitionVersion.objects.filter(project=project).exclude(\n        code=definition_code\n    ).update(is_current=False)\n    definition = _upsert(\n        ProjectDefinitionVersion,\n        object_id=stable_demo_uuid("project-definition-version", definition_code),\n        code=definition_code,\n        project=project,\n        defaults={\n            "project": project,\n            "version": SCHEMA_VERSION,\n            "is_current": True,\n            "publication_status": "PUBLISHED",\n            "manifest": seed_manifest,\n            "manifest_hash": seed_manifest_hash,\n            "published_at": datetime(2025, 1, 1, tzinfo=timezone.utc),\n            "schema_version": SCHEMA_VERSION,\n            "semantic_version": SCHEMA_VERSION,\n            "construct_version": SCHEMA_VERSION,\n            "validated_at": datetime(2025, 1, 1, tzinfo=timezone.utc),\n            "validated_by": "SEED-ZHANAOZEN-1.0.0",\n            "validation_result": {"valid": True, "source": "LEGACY_V1_SEED"},\n            "published_by": "SEED-ZHANAOZEN-1.0.0",\n            "supersedes": None,\n        },\n    )\n    _upsert(\n        ProjectPublication,\n        object_id=stable_demo_uuid("project-publication", definition_code),\n        code=f"PUBLICATION-{SCHEMA_VERSION}",\n        project=project,\n        defaults={\n            "project": project,\n            "definition_version": definition,\n            "version": SCHEMA_VERSION,\n            "locale": "en",\n            "actor_identifier": "SEED-ZHANAOZEN-1.0.0",\n            "validation_result": {"valid": True, "source": "LEGACY_V1_SEED"},\n            "published_at": datetime(2025, 1, 1, tzinfo=timezone.utc),\n        },\n    )\n    workspace = _upsert(\n        ProjectWorkspace,\n        object_id=stable_demo_uuid("project-workspace", "DEFAULT"),\n        code="DEFAULT",\n        defaults={\n            "project": project,\n            "definition_version": definition,\n            "definition_manifest_hash": seed_manifest_hash,\n            "version": SCHEMA_VERSION,\n            "name": "Default",\n            "is_default": True,\n            "metadata": {\n                "migration": "deterministic-demo-default",\n                "compatibility_profile": "V1_LEGACY_REGRESSION_ONLY",\n            },\n        },\n    )\n\n    time_slices: dict[str, TimeSlice] = {}\n    for item in TIME_SLICES:\n        code = item["code"]\n        time_slices[code] = _upsert(\n            TimeSlice,\n            object_id=stable_demo_uuid("time-slice", code),\n            code=code,\n            project=project,\n            defaults={\n                "project": project,\n                "workspace": workspace,\n                "version": SCHEMA_VERSION,\n                "name": code,\n                "cutoff_date": date.fromisoformat(item["cutoff_date"]),\n                "order": item["order"],\n            },\n        )\n\n    tension_points: dict[str, TensionPoint] = {}\n    for item in TENSION_POINTS:\n        code = item["code"]\n        tension_points[code] = _upsert(\n            TensionPoint,\n            object_id=stable_demo_uuid("tension-point", code),\n            code=code,\n            project=project,\n            defaults={\n                "project": project,\n                "version": PTN_VERSION,\n                "name": item["name"],\n                "short_name": item["short_name"],\n                "definition": item["definition"],\n                "order": item["order"],\n            },\n        )\n\n    participant_groups: dict[str, ParticipantGroup] = {}\n    for item in PARTICIPANT_GROUPS:\n        code = item["code"]\n        participant_groups[code] = _upsert(\n            ParticipantGroup,\n            object_id=stable_demo_uuid("participant-group", code),\n            code=code,\n            project=project,\n            defaults={\n                "project": project,\n                "version": GU_VERSION,\n                "name": item["name"],\n                "short_name": item["short_name"],\n                "definition": item["definition"],\n                "order": item["order"],\n            },\n        )\n\n    relation_codes: set[str] = set()\n    for group_code, group in participant_groups.items():\n        for tension_code, tension in tension_points.items():\n            code = f"{group_code}--{tension_code}"\n            relation_codes.add(code)\n            _upsert(\n                GroupTensionRelation,\n                object_id=stable_demo_uuid("group-tension-relation", code),\n                code=code,\n                project=project,\n                defaults={\n                    "project": project,\n                    "version": SCHEMA_VERSION,\n                    "participant_group": group,\n                    "tension_point": tension,\n                },\n            )\n\n    assessment_sets: dict[str, AssessmentSet] = {}\n    for item in ASSESSMENT_SETS:\n        code = item["code"]\n        assessment_sets[code] = _upsert(\n            AssessmentSet,\n            object_id=stable_demo_uuid("assessment-set", code),\n            code=code,\n            project=project,\n            defaults={\n                "project": project,\n                "workspace": workspace,\n                "version": SCHEMA_VERSION,\n                "kind": item["kind"],\n                "name": item["name"],\n                "description": "",\n            },\n        )\n\n    for item in ASSESSMENT_SETS:\n        assessment_set = assessment_sets[item["code"]]\n        kind = item["kind"]\n        profile_code = f"EXPERT-{kind}"\n        profile = _upsert(\n            ExpertProfile,\n            object_id=stable_demo_uuid("expert-profile", profile_code),\n            code=profile_code,\n            defaults={\n                "workspace": workspace,\n                "version": SCHEMA_VERSION,\n                "kind": kind,\n                "display_name": f"{kind} demo expert",\n                "identity_key": f"demo:{kind.lower()}",\n                "provider": "demo" if kind == "AI" else "",\n                "model_name": "demo-placeholder" if kind == "AI" else "",\n                "metadata": {"seed_version": SEED_VERSION},\n            },\n        )\n        experiment_code = f"EXP-{item[\'code\']}"\n        _upsert(\n            Experiment,\n            object_id=stable_demo_uuid("experiment", experiment_code),\n            code=experiment_code,\n            defaults={\n                "workspace": workspace,\n                "version": SCHEMA_VERSION,\n                "expert_profile": profile,\n                "assessment_set": assessment_set,\n                "experiment_type": "ASSESSMENT",\n                "name": f"{item[\'name\']} experiment",\n                "status": "DRAFT",\n                "color": "",\n                "order": 0,\n                "method_version": "",\n                "frozen_at": None,\n                "metadata": {"seed_version": SEED_VERSION},\n            },\n        )\n\n    for item in PARAMETER_DEFINITIONS:\n        code = item["code"]\n        _upsert(\n            ParameterDefinition,\n            object_id=stable_demo_uuid("parameter-definition", code),\n            code=code,\n            project=project,\n            defaults={\n                "project": project,\n                "version": item["version"],\n                "name": item["name"],\n                "description": "",\n                "target_type": item["target_type"],\n                "value_type": item["value_type"],\n                "scale_min": None,\n                "scale_max": None,\n                "scale_metadata": {"method_status": "OPEN_METHOD"},\n            },\n        )\n\n    # Verify exact demo membership.  Unexpected structure is never pruned.\n    _require_exact_codes(TimeSlice, project, set(time_slices))\n    _require_exact_codes(TensionPoint, project, set(tension_points))\n    _require_exact_codes(ParticipantGroup, project, set(participant_groups))\n    _require_exact_codes(GroupTensionRelation, project, relation_codes)\n    _require_exact_codes(\n        AssessmentSet, project, {item["code"] for item in ASSESSMENT_SETS}\n    )\n    _require_exact_codes(\n        ParameterDefinition,\n        project,\n        {item["code"] for item in PARAMETER_DEFINITIONS},\n    )\n\n    schema_code = f"SCHEMA-{SCHEMA_VERSION}"\n    schema_id = stable_demo_uuid("project-schema-version", schema_code)\n    ProjectSchemaVersion.objects.filter(project=project).exclude(pk=schema_id).update(\n        is_current=False\n    )\n    _upsert(\n        ProjectSchemaVersion,\n        object_id=schema_id,\n        code=schema_code,\n        project=project,\n        defaults={\n            "project": project,\n            "version": SCHEMA_VERSION,\n            "is_current": True,\n            "manifest": seed_manifest,\n            "manifest_hash": seed_manifest_hash,\n        },\n    )\n\n    _upsert(\n        ProjectLock,\n        object_id=stable_demo_uuid("project-lock", "STRUCTURE-LOCK"),\n        code="STRUCTURE-LOCK",\n        project=project,\n        defaults={\n            "project": project,\n            "version": SCHEMA_VERSION,\n            "is_structure_locked": True,\n            "ordinary_user_can_edit_structure": False,\n            "studio_can_edit_structure": False,\n            "reason": (\n                "FROZEN_FOR_DEMO_V1: изменение состава требует отдельного прямого "\n                "OWNER_DECISION и новой версии перечня."\n            ),\n        },\n    )\n    return project\n'
