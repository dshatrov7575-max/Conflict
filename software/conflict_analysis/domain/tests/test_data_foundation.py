from __future__ import annotations

import copy
import json
from datetime import date
from decimal import Decimal
from unittest import mock
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.test import TestCase

from domain.demo_data import (
    GU_VERSION,
    PROJECT_CODE,
    PTN_VERSION,
    stable_demo_uuid,
)
from domain.enums import (
    AssessmentKind,
    AuditAction,
    AuditActorType,
    EvidenceRelation,
    TargetType,
    ValueStatus,
)
from domain.models import (
    AssessmentSet,
    AuditEvent,
    EvidenceLink,
    EvidenceSource,
    GroupTensionRelation,
    ParameterDefinition,
    ParameterValue,
    ParticipantGroup,
    Project,
    ProjectLock,
    ProjectSchemaVersion,
    Scenario,
    ScenarioOverride,
    TensionPoint,
    TimeSlice,
)
from domain.policies import (
    StructureActor,
    StructureMutationDenied,
    can_modify_project_structure,
    require_project_structure_mutation,
)
from domain.services.project_packages import (
    PACKAGE_JSON_SCHEMA,
    ProjectPackageValidationError,
    export_project_json,
    export_project_package,
    import_project_package,
    seal_project_package,
)
from domain.services.seed import seed_zhanaozen_demo


def clean_save(instance):
    instance.full_clean()
    instance.save()
    return instance


class DemoSeedTests(TestCase):
    def test_seed_is_exact_versioned_and_idempotent(self):
        project = seed_zhanaozen_demo()
        initial_ids = {
            model.__name__: set(
                model.objects.filter(project=project).values_list("id", flat=True)
            )
            for model in (
                TimeSlice,
                TensionPoint,
                ParticipantGroup,
                GroupTensionRelation,
            )
        }

        self.assertEqual(TimeSlice.objects.filter(project=project).count(), 3)
        self.assertEqual(TensionPoint.objects.filter(project=project).count(), 6)
        self.assertEqual(ParticipantGroup.objects.filter(project=project).count(), 8)
        self.assertEqual(GroupTensionRelation.objects.filter(project=project).count(), 48)
        self.assertEqual(
            set(TimeSlice.objects.filter(project=project).values_list("cutoff_date", flat=True)),
            {date(2011, 12, 15), date(2022, 1, 2), date(2026, 8, 21)},
        )
        self.assertEqual(
            GroupTensionRelation.objects.filter(project=project)
            .values("participant_group_id", "tension_point_id")
            .distinct()
            .count(),
            48,
        )
        self.assertEqual(
            set(AssessmentSet.objects.filter(project=project).values_list("code", flat=True)),
            {"HUMAN_DRAFT", "AI_DRAFT"},
        )
        self.assertEqual(
            set(
                ParameterDefinition.objects.filter(project=project).values_list(
                    "code", "version"
                )
            ),
            {
                ("UOS", "OPEN_METHOD"),
                ("KVS", "OPEN_METHOD"),
                ("RGU", "OPEN_METHOD"),
                ("KVPTN", "OPEN_METHOD"),
            },
        )
        self.assertFalse(ParameterValue.objects.filter(project=project).exists())
        self.assertEqual(
            set(TensionPoint.objects.filter(project=project).values_list("version", flat=True)),
            {PTN_VERSION},
        )
        self.assertEqual(
            set(
                ParticipantGroup.objects.filter(project=project).values_list(
                    "version", flat=True
                )
            ),
            {GU_VERSION},
        )

        schema = ProjectSchemaVersion.objects.get(project=project, is_current=True)
        self.assertEqual(schema.manifest["ptn_version"], PTN_VERSION)
        self.assertEqual(schema.manifest["gu_version"], GU_VERSION)
        lock = ProjectLock.objects.get(project=project)
        self.assertTrue(lock.is_structure_locked)
        self.assertFalse(lock.ordinary_user_can_edit_structure)
        self.assertFalse(lock.studio_can_edit_structure)

        same_project = seed_zhanaozen_demo()
        self.assertEqual(same_project.id, project.id)
        for model in (TimeSlice, TensionPoint, ParticipantGroup, GroupTensionRelation):
            self.assertEqual(
                set(model.objects.filter(project=project).values_list("id", flat=True)),
                initial_ids[model.__name__],
            )

    def test_stable_uuid_does_not_depend_on_seed_release_label(self):
        expected = stable_demo_uuid("tension-point", "PTN-01")
        with mock.patch("domain.demo_data.SEED_VERSION", "FUTURE-SEED-99"):
            self.assertEqual(stable_demo_uuid("tension-point", "PTN-01"), expected)


class AssessmentIsolationTests(TestCase):
    def setUp(self):
        self.project = seed_zhanaozen_demo()
        self.time_slice = TimeSlice.objects.get(project=self.project, code="2011-12-15")
        self.relation = GroupTensionRelation.objects.filter(project=self.project).first()
        self.definition = ParameterDefinition.objects.get(project=self.project, code="UOS")

    def _value(self, code: str, set_code: str, value: int) -> ParameterValue:
        return clean_save(
            ParameterValue(
                project=self.project,
                code=code,
                time_slice=self.time_slice,
                assessment_set=AssessmentSet.objects.get(
                    project=self.project, code=set_code
                ),
                parameter_definition=self.definition,
                target_type=TargetType.GROUP_TENSION_RELATION,
                target_id=self.relation.id,
                status=ValueStatus.PROVISIONAL,
                value=value,
                confidence=Decimal("0.5000"),
                range_min=0,
                range_max=10,
                rationale="Синтетическое значение создано только для проверки изоляции.",
            )
        )

    def test_human_and_ai_values_are_independent(self):
        human = self._value("TEST-HUMAN", "HUMAN_DRAFT", 2)
        ai = self._value("TEST-AI", "AI_DRAFT", 7)

        human.refresh_from_db()
        ai.refresh_from_db()
        self.assertEqual(human.value, 2)
        self.assertEqual(ai.value, 7)
        self.assertNotEqual(human.assessment_set_id, ai.assessment_set_id)
        self.assertEqual(
            ParameterValue.objects.filter(
                project=self.project,
                time_slice=self.time_slice,
                parameter_definition=self.definition,
                target_id=self.relation.id,
            ).count(),
            2,
        )

    def test_unknown_is_null_and_zero_is_rejected(self):
        unknown = clean_save(
            ParameterValue(
                project=self.project,
                code="TEST-UNKNOWN",
                time_slice=self.time_slice,
                assessment_set=AssessmentSet.objects.get(
                    project=self.project, code="HUMAN_DRAFT"
                ),
                parameter_definition=self.definition,
                target_type=TargetType.GROUP_TENSION_RELATION,
                target_id=self.relation.id,
                status=ValueStatus.UNKNOWN,
                value=None,
            )
        )
        unknown.refresh_from_db()
        self.assertIsNone(unknown.value)
        self.assertEqual(unknown.status, ValueStatus.UNKNOWN)

        invalid = ParameterValue(
            project=self.project,
            code="TEST-UNKNOWN-ZERO",
            time_slice=self.time_slice,
            assessment_set=AssessmentSet.objects.get(
                project=self.project, code="AI_DRAFT"
            ),
            parameter_definition=self.definition,
            target_type=TargetType.GROUP_TENSION_RELATION,
            target_id=self.relation.id,
            status=ValueStatus.UNKNOWN,
            value=0,
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()


class StructurePolicyTests(TestCase):
    def test_demo_is_locked_for_ordinary_and_studio_actors(self):
        project = seed_zhanaozen_demo()
        self.assertFalse(can_modify_project_structure(project))
        self.assertFalse(
            can_modify_project_structure(project, actor=StructureActor.STUDIO)
        )
        with self.assertRaises(StructureMutationDenied):
            require_project_structure_mutation(project)
        with self.assertRaises(StructureMutationDenied):
            require_project_structure_mutation(project, actor=StructureActor.STUDIO)

    def test_studio_can_create_a_differently_sized_unlocked_project(self):
        project = Project.objects.create(code="STUDIO-TEST", name="Studio test")
        clean_save(
            ProjectLock(
                project=project,
                code="EDITABLE",
                is_structure_locked=False,
                ordinary_user_can_edit_structure=True,
                studio_can_edit_structure=True,
            )
        )
        require_project_structure_mutation(project, actor=StructureActor.STUDIO)
        for order in (1, 2):
            TensionPoint.objects.create(
                project=project,
                code=f"CUSTOM-PTN-{order}",
                name=f"Custom tension {order}",
                definition="Test-only structure.",
                order=order,
            )
        ParticipantGroup.objects.create(
            project=project,
            code="CUSTOM-GU-1",
            name="Custom group",
            definition="Test-only structure.",
            order=1,
        )
        self.assertEqual(project.tension_points.count(), 2)
        self.assertEqual(project.participant_groups.count(), 1)


class ProjectPackageTests(TestCase):
    def setUp(self):
        self.project = seed_zhanaozen_demo()

    def _add_assessments_and_evidence(self):
        time_slice = TimeSlice.objects.get(project=self.project, code="2011-12-15")
        relation = GroupTensionRelation.objects.filter(project=self.project).first()
        definition = ParameterDefinition.objects.get(project=self.project, code="UOS")
        human_set = AssessmentSet.objects.get(project=self.project, code="HUMAN_DRAFT")
        ai_set = AssessmentSet.objects.get(project=self.project, code="AI_DRAFT")
        present = clean_save(
            ParameterValue(
                project=self.project,
                code="ROUNDTRIP-PROVISIONAL-NO-RANGE",
                time_slice=time_slice,
                assessment_set=human_set,
                parameter_definition=definition,
                target_type=TargetType.GROUP_TENSION_RELATION,
                target_id=relation.id,
                status=ValueStatus.PROVISIONAL,
                value=2,
                confidence=Decimal("0.7500"),
                range_min=None,
                range_max=None,
                rationale="Test value verifies a present assessment without a range.",
            )
        )
        unknown = clean_save(
            ParameterValue(
                project=self.project,
                code="ROUNDTRIP-UNKNOWN",
                time_slice=time_slice,
                assessment_set=ai_set,
                parameter_definition=definition,
                target_type=TargetType.GROUP_TENSION_RELATION,
                target_id=relation.id,
                status=ValueStatus.UNKNOWN,
                value=None,
            )
        )
        source = clean_save(
            EvidenceSource(
                project=self.project,
                code="SOURCE-1",
                title="Round-trip source",
                url="https://example.com/source",
                additional_urls=["https://example.org/context"],
                published_on=date(2020, 1, 2),
                accessed_on=date(2026, 8, 21),
                metadata={"language": "ru"},
            )
        )
        link = clean_save(
            EvidenceLink(
                project=self.project,
                code="LINK-1",
                parameter_value=present,
                source=source,
                relation=EvidenceRelation.SUPPORTS,
                rationale="Источник используется только для проверки переноса связи.",
            )
        )
        audit = clean_save(
            AuditEvent(
                project=self.project,
                code="AUDIT-1",
                assessment_set=human_set,
                parameter_value=present,
                action=AuditAction.CREATE,
                actor_type=AuditActorType.SYSTEM,
                actor_identifier="focused-test",
                entity_type="PARAMETER_VALUE",
                entity_id=present.id,
                before=None,
                after={"status": ValueStatus.PROVISIONAL},
            )
        )
        return present, unknown, source, link, audit

    def _add_scenario_override_without_range(self):
        time_slice = TimeSlice.objects.get(project=self.project, code="2011-12-15")
        base_set = AssessmentSet.objects.get(
            project=self.project, code="HUMAN_DRAFT"
        )
        scenario_set = clean_save(
            AssessmentSet(
                project=self.project,
                code="SCENARIO-RANGE-TEST",
                kind=AssessmentKind.SCENARIO,
                name="Scenario range test",
            )
        )
        scenario = clean_save(
            Scenario(
                project=self.project,
                code="SCENARIO-RANGE-TEST",
                time_slice=time_slice,
                assessment_set=scenario_set,
                base_assessment_set=base_set,
                name="Scenario range test",
            )
        )
        relation = GroupTensionRelation.objects.filter(project=self.project).first()
        definition = ParameterDefinition.objects.get(project=self.project, code="UOS")
        return clean_save(
            ScenarioOverride(
                project=self.project,
                code="SCENARIO-OVERRIDE-NO-RANGE",
                scenario=scenario,
                parameter_definition=definition,
                target_type=TargetType.GROUP_TENSION_RELATION,
                target_id=relation.id,
                status=ValueStatus.PROVISIONAL,
                value=1,
                confidence=Decimal("0.6000"),
                range_min=None,
                range_max=None,
                rationale="Scenario override intentionally omits an admissible range.",
            )
        )

    def _delete_project_graph(self):
        EvidenceLink.objects.filter(project=self.project).delete()
        # Test-only teardown uses Django's non-public base manager; the public
        # append-only manager remains fail-closed for product callers.
        AuditEvent._base_manager.filter(project=self.project).delete()
        ScenarioOverride.objects.filter(project=self.project).delete()
        Scenario.objects.filter(project=self.project).delete()
        ParameterValue.objects.filter(project=self.project).delete()
        GroupTensionRelation.objects.filter(project=self.project).delete()
        self.project.delete()

    def test_present_value_without_range_full_clean_and_json_round_trip(self):
        present, unknown, source, link, audit = self._add_assessments_and_evidence()
        override = self._add_scenario_override_without_range()
        exported_json = export_project_json(self.project)
        self.assertEqual(exported_json, export_project_json(self.project))
        package = json.loads(exported_json)

        self.assertEqual(
            PACKAGE_JSON_SCHEMA["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertTrue(PACKAGE_JSON_SCHEMA["$id"])
        self.assertEqual(package["manifest"]["ptn_version"], PTN_VERSION)
        self.assertEqual(package["manifest"]["gu_version"], GU_VERSION)
        original_project_id = self.project.id
        self._delete_project_graph()

        imported = import_project_package(package)
        self.assertEqual(imported.id, original_project_id)
        restored_present = ParameterValue.objects.get(pk=present.id)
        restored_unknown = ParameterValue.objects.get(pk=unknown.id)
        self.assertEqual(restored_present.code, present.code)
        self.assertEqual(restored_present.status, ValueStatus.PROVISIONAL)
        self.assertEqual(restored_present.value, 2)
        self.assertEqual(restored_present.confidence, Decimal("0.7500"))
        self.assertEqual(
            (restored_present.range_min, restored_present.range_max),
            (None, None),
        )
        self.assertEqual(restored_present.rationale, present.rationale)
        self.assertEqual(restored_unknown.status, ValueStatus.UNKNOWN)
        self.assertIsNone(restored_unknown.value)
        restored_source = EvidenceSource.objects.get(pk=source.id)
        self.assertEqual(restored_source.code, source.code)
        self.assertEqual(restored_source.url, source.url)
        self.assertEqual(restored_source.additional_urls, source.additional_urls)
        restored_link = EvidenceLink.objects.get(pk=link.id)
        self.assertEqual(restored_link.parameter_value_id, present.id)
        self.assertEqual(restored_link.source_id, source.id)
        self.assertEqual(AuditEvent.objects.get(pk=audit.id).entity_id, present.id)
        restored_override = ScenarioOverride.objects.get(pk=override.id)
        self.assertEqual(restored_override.status, ValueStatus.PROVISIONAL)
        self.assertEqual(restored_override.value, 1)
        self.assertEqual(
            (restored_override.range_min, restored_override.range_max),
            (None, None),
        )
        self.assertEqual(export_project_json(imported), exported_json)

    def test_one_sided_ranges_are_rejected_by_models_and_packages(self):
        present, *_ = self._add_assessments_and_evidence()
        present.range_min = 0
        with self.assertRaises(ValidationError):
            present.full_clean()
        present.range_min = None

        package = export_project_package(self.project)
        packaged_value = next(
            item
            for item in package["parameter_values"]
            if item["id"] == str(present.id)
        )
        packaged_value["range_min"] = 0
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(seal_project_package(package))

        override = self._add_scenario_override_without_range()
        override.range_max = 2
        with self.assertRaises(ValidationError):
            override.full_clean()
        override.range_min = 0
        override.full_clean()
        override.range_min = None
        override.range_max = None

        package = export_project_package(self.project)
        packaged_override = next(
            item
            for item in package["scenario_overrides"]
            if item["id"] == str(override.id)
        )
        packaged_override["range_max"] = 2
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(seal_project_package(package))

    def test_two_sided_range_order_and_containment_validation_remain_active(self):
        present, *_ = self._add_assessments_and_evidence()
        override = self._add_scenario_override_without_range()

        present.range_min = 3
        present.range_max = 1
        with self.assertRaises(ValidationError):
            present.full_clean()

        present.range_min = 0
        present.range_max = 1
        with self.assertRaises(ValidationError):
            present.full_clean()

        present.range_max = 3
        clean_save(present)

        override.range_min = 2
        override.range_max = 0
        with self.assertRaises(ValidationError):
            override.full_clean()

        override.range_min = 2
        override.range_max = 3
        with self.assertRaises(ValidationError):
            override.full_clean()

        override.range_min = 0
        override.range_max = 2
        clean_save(override)
        package = export_project_package(self.project)

        reversed_range = copy.deepcopy(package)
        packaged_value = next(
            item
            for item in reversed_range["parameter_values"]
            if item["id"] == str(present.id)
        )
        packaged_value["range_min"] = 3
        packaged_value["range_max"] = 1
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(seal_project_package(reversed_range))

        outside_range = copy.deepcopy(package)
        packaged_value = next(
            item
            for item in outside_range["parameter_values"]
            if item["id"] == str(present.id)
        )
        packaged_value["range_min"] = 0
        packaged_value["range_max"] = 1
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(seal_project_package(outside_range))

        reversed_override_range = copy.deepcopy(package)
        packaged_override = next(
            item
            for item in reversed_override_range["scenario_overrides"]
            if item["id"] == str(override.id)
        )
        packaged_override["range_min"] = 2
        packaged_override["range_max"] = 0
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(seal_project_package(reversed_override_range))

        outside_override_range = copy.deepcopy(package)
        packaged_override = next(
            item
            for item in outside_override_range["scenario_overrides"]
            if item["id"] == str(override.id)
        )
        packaged_override["range_min"] = 2
        packaged_override["range_max"] = 3
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(seal_project_package(outside_override_range))

    def test_invalid_reference_duplicate_version_and_boolean_are_rejected_atomically(self):
        original = export_project_package(self.project)
        counts_before = (
            Project.objects.count(),
            TimeSlice.objects.count(),
            TensionPoint.objects.count(),
            GroupTensionRelation.objects.count(),
        )

        bad_reference = copy.deepcopy(original)
        bad_reference["group_tension_relations"][0]["participant_group_id"] = str(
            uuid4()
        )
        bad_reference = seal_project_package(bad_reference)
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(bad_reference)

        checksum_mismatch = copy.deepcopy(original)
        checksum_mismatch["project"]["name"] = "Tampered after sealing"
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(checksum_mismatch)

        duplicate = copy.deepcopy(original)
        duplicate_item = copy.deepcopy(duplicate["tension_points"][0])
        duplicate_item["id"] = str(uuid4())
        duplicate["tension_points"].append(duplicate_item)
        duplicate = seal_project_package(duplicate)
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(duplicate)

        incompatible = copy.deepcopy(original)
        incompatible["format_version"] = "2.0.0"
        incompatible = seal_project_package(incompatible)
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(incompatible)

        malformed_boolean = copy.deepcopy(original)
        malformed_boolean["project_lock"]["is_structure_locked"] = "true"
        malformed_boolean = seal_project_package(malformed_boolean)
        with self.assertRaises(ProjectPackageValidationError):
            import_project_package(malformed_boolean)

        self.assertEqual(
            (
                Project.objects.count(),
                TimeSlice.objects.count(),
                TensionPoint.objects.count(),
                GroupTensionRelation.objects.count(),
            ),
            counts_before,
        )

    def test_present_value_requires_evidence_and_audit_target_must_resolve(self):
        time_slice = TimeSlice.objects.get(project=self.project, code="2011-12-15")
        relation = GroupTensionRelation.objects.filter(project=self.project).first()
        definition = ParameterDefinition.objects.get(project=self.project, code="UOS")
        value = clean_save(
            ParameterValue(
                project=self.project,
                code="NO-EVIDENCE",
                time_slice=time_slice,
                assessment_set=AssessmentSet.objects.get(
                    project=self.project, code="HUMAN_DRAFT"
                ),
                parameter_definition=definition,
                target_type=TargetType.GROUP_TENSION_RELATION,
                target_id=relation.id,
                status=ValueStatus.PROVISIONAL,
                value=1,
                confidence=Decimal("0.5000"),
                range_min=0,
                range_max=2,
                rationale="Тестовая оценка без источника должна быть отклонена импортом.",
            )
        )
        with self.assertRaises(ProjectPackageValidationError):
            export_project_package(self.project)

        value.delete()
        clean_save(
            AuditEvent(
                project=self.project,
                code="DANGLING-AUDIT",
                action=AuditAction.DELETE,
                actor_type=AuditActorType.SYSTEM,
                actor_identifier="focused-test",
                entity_type="PARAMETER_VALUE",
                entity_id=uuid4(),
            )
        )
        with self.assertRaises(ProjectPackageValidationError):
            export_project_package(self.project)
