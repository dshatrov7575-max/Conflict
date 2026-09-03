from __future__ import annotations

import copy
import hashlib
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.models import BooleanField, Exists, F, OuterRef, Q, Subquery
from django.db.models.expressions import RawSQL
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
    ProjectPrimaryLanguageAssignment,
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
    PACKAGE_VERSION,
    PROJECT_PACKAGE_PRIMARY_LANGUAGE_REQUIRED,
    PACKAGE_JSON_SCHEMA,
    ProjectPackageValidationError,
    export_project_json,
    export_project_package,
    import_project_package,
    seal_project_package,
    upgrade_project_package_1_0_to_1_1,
)
from domain.services.language_tags import (
    LanguageTagValidationError,
    canonicalize_language_tag,
)
from domain.services.seed import SeedConflictError, seed_zhanaozen_demo


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


class ProjectPrimaryLanguageContractTests(TestCase):
    def _project(self, code: str, language: str = "ru", **values):
        return Project.objects.create(
            code=code,
            version="1.0.0",
            name=values.pop("name", code),
            primary_language_tag=language,
            **values,
        )

    @staticmethod
    def _downgrade_to_frozen_1_0(package):
        downgraded = copy.deepcopy(package)
        downgraded.pop("manifest", None)
        downgraded["format_version"] = "1.0.0"
        downgraded["project"].pop("primary_language_tag")
        downgraded["project"].pop("primary_language_assignment")
        return seal_project_package(downgraded)

    def test_language_tag_well_formedness_and_canonicalization_vectors_are_exact(self):
        vectors = {
            "ru": "ru",
            "KY": "ky",
            "kk": "kk",
            "UZ": "uz",
            "uz-cYRL": "uz-Cyrl",
            "UZ-latn": "uz-Latn",
            "EN-us": "en-US",
            "zh-hANT-tw": "zh-Hant-TW",
            "de-ch-1901": "de-CH-1901",
            "SL-ROZAJ-BISKE-1994": "sl-rozaj-biske-1994",
            "en-A-AAA-b-CCC-X-Private": "en-a-aaa-b-ccc-x-private",
            "I-KLINGON": "i-klingon",
            "X-Project-Local": "x-project-local",
        }
        for supplied, expected in vectors.items():
            with self.subTest(supplied=supplied):
                self.assertEqual(canonicalize_language_tag(supplied), expected)

        exactly_255 = "x-" + "-".join(["aaaaaaaa"] * 28 + ["b"])
        self.assertEqual(len(exactly_255), 255)
        self.assertEqual(canonicalize_language_tag(exactly_255), exactly_255)
        self.assertEqual(
            canonicalize_language_tag("UND", allow_und=True),
            "und",
        )

        invalid = (
            "",
            "en_US",
            "en US",
            "en--US",
            "e",
            "en-abcdefghi",
            "en-US-Latn",
            "sl-rozaj-ROZAJ",
            "en-a-aaa-A-bbb",
            "Russian language",
            f"{exactly_255}-c",
        )
        for supplied in invalid:
            with self.subTest(supplied=supplied):
                with self.assertRaises(LanguageTagValidationError):
                    canonicalize_language_tag(supplied)
        with self.assertRaisesRegex(LanguageTagValidationError, "legacy restoration"):
            canonicalize_language_tag("und")

    def test_project_create_and_base_manager_require_explicit_non_und_language(self):
        managers = (Project.objects, Project._default_manager, Project._base_manager)
        for index, manager in enumerate(managers):
            with self.subTest(manager=manager):
                with self.assertRaises(ValidationError):
                    manager.create(code=f"MISSING-{index}", name="Missing")
                with self.assertRaises(ValidationError):
                    manager.create(
                        code=f"UNKNOWN-{index}",
                        name="Unknown",
                        primary_language_tag="und",
                    )
                with self.assertRaises(ValidationError):
                    manager.create(
                        code=f"MALFORMED-{index}",
                        name="Malformed",
                        primary_language_tag="ru_RU",
                    )
                with self.assertRaises(ValidationError):
                    manager.create(
                        code=f"EXPRESSION-{index}",
                        name="Expression",
                        primary_language_tag=F("code"),
                    )

        project = Project._base_manager.create(
            code="CANONICAL-CREATE",
            name="Canonical create",
            primary_language_tag="RU",
        )
        self.assertEqual(project.primary_language_tag, "ru")
        self.assertEqual(
            project.primary_language_assignment,
            ProjectPrimaryLanguageAssignment.EXPLICIT,
        )

        async def async_create_without_language():
            await Project.objects.acreate(
                code="ASYNC-CREATE-MISSING",
                name="Async create missing language",
            )

        with self.assertRaises(ValidationError):
            async_to_sync(async_create_without_language)()
        self.assertFalse(
            Project.objects.filter(code="ASYNC-CREATE-MISSING").exists()
        )

    def test_instance_save_rejects_relanguage_and_other_fields_remain_mutable(self):
        project = self._project("INSTANCE-IMMUTABLE")
        project.name = "Hidden relanguage"
        project.primary_language_tag = "kk"
        with self.assertRaises(ValidationError):
            project.save(update_fields=["name"])
        project.refresh_from_db()
        self.assertEqual(project.name, "INSTANCE-IMMUTABLE")
        self.assertEqual(project.primary_language_tag, "ru")

        project.primary_language_assignment = (
            ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN
        )
        with self.assertRaises(ValidationError):
            project.save()
        project.refresh_from_db()
        project.name = "Mutable name"
        project.save(update_fields=["name"])
        project.refresh_from_db()
        self.assertEqual(project.name, "Mutable name")
        self.assertEqual(project.primary_language_tag, "ru")

        deferred = Project.objects.only("id", "name").get(pk=project.pk)
        deferred.name = "Deferred mutable name"
        deferred.save(update_fields=["name"])
        deferred.refresh_from_db()
        self.assertEqual(deferred.primary_language_tag, "ru")
        deferred.primary_language_tag = "kk"
        deferred.name = "Deferred hidden relanguage"
        with self.assertRaises(ValidationError):
            deferred.save(update_fields=["name"])

    def test_queryset_update_and_bulk_update_reject_relanguage(self):
        project = self._project("QUERYSET-IMMUTABLE")
        with self.assertRaises(ValidationError):
            Project.objects.filter(pk=project.pk).update(primary_language_tag="kk")
        with self.assertRaises(ValidationError):
            Project.objects.filter(pk=project.pk).update(
                primary_language_tag=F("primary_language_tag")
            )

        async def async_queryset_relanguage():
            await Project.objects.filter(pk=project.pk).aupdate(
                primary_language_tag="kk"
            )

        with self.assertRaises(ValidationError):
            async_to_sync(async_queryset_relanguage)()

        project.primary_language_tag = "kk"
        project.name = "Hidden bulk relanguage"

        async def async_bulk_relanguage():
            await Project.objects.abulk_update(
                [project],
                ["primary_language_tag"],
            )

        with self.assertRaises(ValidationError):
            async_to_sync(async_bulk_relanguage)()
        with self.assertRaises(ValidationError):
            Project.objects.bulk_update([project], ["name"])
        with self.assertRaises(ValidationError):
            Project.objects.bulk_update([project], ["primary_language_tag"])

        project.refresh_from_db()
        Project.objects.filter(pk=project.pk).update(name="Queryset mutable")
        project.refresh_from_db()
        project.name = "Bulk mutable"
        self.assertEqual(Project.objects.bulk_update([project], ["name"]), 1)
        project.refresh_from_db()
        self.assertEqual(project.name, "Bulk mutable")

        database_project_id = Project._meta.get_field("id").get_db_prep_value(
            project.pk,
            connection,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE domain_project "
                        "SET primary_language_tag = %s WHERE id = %s",
                        ["und", database_project_id],
                    )
        project.refresh_from_db()
        self.assertEqual(
            (
                project.primary_language_tag,
                project.primary_language_assignment,
            ),
            ("ru", ProjectPrimaryLanguageAssignment.EXPLICIT),
        )

    def test_get_or_create_requires_language_for_create_and_preserves_existing_identity(self):
        with self.assertRaises(ValidationError):
            Project.objects.get_or_create(
                code="GET-OR-CREATE",
                defaults={"name": "Missing language"},
            )
        project, created = Project.objects.get_or_create(
            code="GET-OR-CREATE",
            defaults={"name": "Created", "primary_language_tag": "RU"},
        )
        self.assertTrue(created)
        same, created = Project.objects.get_or_create(code=project.code)
        self.assertFalse(created)
        self.assertEqual(same.pk, project.pk)
        same, created = Project.objects.get_or_create(
            code=project.code,
            primary_language_tag="rU",
        )
        self.assertFalse(created)
        self.assertEqual(same.pk, project.pk)
        same, created = Project.objects.get_or_create(
            code=project.code,
            primary_language_tag="RU",
            defaults={"primary_language_tag": "rU"},
        )
        self.assertFalse(created)
        self.assertEqual(same.pk, project.pk)

        callable_language = mock.Mock(return_value="UZ-latn")
        callable_project, created = Project.objects.get_or_create(
            code="GET-OR-CREATE-CALLABLE",
            defaults={
                "name": "Callable language",
                "primary_language_tag": callable_language,
            },
        )
        self.assertTrue(created)
        self.assertEqual(callable_project.primary_language_tag, "uz-Latn")
        callable_language.assert_called_once_with()

        for forbidden_lookup in (
            {"primary_language_tag__iexact": "ru"},
            {"primary_language_tag__in": ["ru"]},
            {"primary_language_assignment__isnull": False},
        ):
            with self.subTest(forbidden_lookup=forbidden_lookup):
                with self.assertNumQueries(0), self.assertRaises(ValidationError):
                    Project.objects.get_or_create(
                        code=project.code,
                        **forbidden_lookup,
                    )
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.get_or_create(
                code=project.code,
                defaults={"primary_language_tag__iexact": "ru"},
            )

        invalid_callable = mock.Mock(return_value=F("code"))
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.get_or_create(
                code=project.code,
                defaults={"primary_language_tag": invalid_callable},
            )
        invalid_callable.assert_called_once_with()
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.get_or_create(
                code=project.code,
                primary_language_tag=F("code"),
            )
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.get_or_create(
                code=project.code,
                primary_language_tag="RU",
                defaults={"primary_language_tag": "kk"},
            )
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.get_or_create(
                code=project.code,
                primary_language_assignment=lambda: object(),
            )

        with self.assertRaises(ValidationError):
            Project.objects.get_or_create(
                code=project.code,
                defaults={"primary_language_tag": "kk"},
            )

        filtered, created = Project.objects.filter(code=project.code).get_or_create(
            defaults={"name": "Filtered ordinary read"},
        )
        self.assertFalse(created)
        self.assertEqual(filtered.pk, project.pk)
        annotated, created = (
            Project.objects.annotate(unrelated_name=F("name"))
            .filter(code=project.code)
            .get_or_create(defaults={"name": "Annotated ordinary read"})
        )
        self.assertFalse(created)
        self.assertEqual(annotated.pk, project.pk)

        language_subquery = Project.objects.filter(
            pk=OuterRef("pk"),
        ).values("primary_language_tag")[:1]
        unsafe_querysets = (
            (
                "transformed lookup",
                Project.objects.filter(primary_language_tag__iexact="ru"),
            ),
            (
                "negated predicate",
                Project.objects.filter(~Q(primary_language_tag="kk")),
            ),
            (
                "exclude negated predicate",
                Project.objects.exclude(primary_language_tag="kk"),
            ),
            (
                "nested Q",
                Project.objects.filter(Q(Q(primary_language_tag="ru"))),
            ),
            (
                "language alias",
                Project.objects.alias(
                    project_language=F("primary_language_tag"),
                ).filter(project_language="ru"),
            ),
            (
                "language F",
                Project.objects.filter(code=F("primary_language_tag")),
            ),
            (
                "language Subquery",
                Project.objects.filter(
                    code=Subquery(language_subquery),
                ),
            ),
            (
                "language Exists",
                Project.objects.filter(
                    Exists(
                        Project.objects.filter(
                            pk=OuterRef("pk"),
                            primary_language_tag="ru",
                        )
                    )
                ),
            ),
            (
                "ExtraWhere",
                Project.objects.extra(
                    where=["primary_language_tag = %s"],
                    params=["ru"],
                ),
            ),
            (
                "RawSQL",
                Project.objects.filter(
                    RawSQL(
                        "primary_language_tag = %s",
                        ["ru"],
                        output_field=BooleanField(),
                    ),
                ),
            ),
            (
                "combined OR QuerySet",
                Project.objects.filter(code=project.code)
                | Project.objects.filter(primary_language_tag="ru"),
            ),
            (
                "combined UNION QuerySet",
                Project.objects.filter(code=project.code).union(
                    Project.objects.filter(primary_language_tag="ru")
                ),
            ),
        )
        for label, unsafe_queryset in unsafe_querysets:
            with self.subTest(label=label):
                callable_language = mock.Mock(
                    side_effect=AssertionError("callable must not run")
                )
                with self.assertNumQueries(0), self.assertRaises(ValidationError):
                    unsafe_queryset.get_or_create(
                        code=project.code,
                        defaults={
                            "name": "Must not be evaluated",
                            "primary_language_tag": callable_language,
                        },
                    )
                self.assertEqual(callable_language.call_count, 0, label)

        async def async_get_or_create_with_language_lookup():
            await Project.objects.aget_or_create(
                code=project.code,
                primary_language_tag__iexact="ru",
            )

        with self.assertRaises(ValidationError):
            async_to_sync(async_get_or_create_with_language_lookup)()
        async_callable = mock.Mock(
            side_effect=AssertionError("callable must not run")
        )

        async def async_get_or_create_with_preexisting_state():
            await Project.objects.filter(
                primary_language_tag__iexact="ru"
            ).aget_or_create(
                code=project.code,
                defaults={"primary_language_tag": async_callable},
            )

        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            async_to_sync(async_get_or_create_with_preexisting_state)()
        async_callable.assert_not_called()
        project.refresh_from_db()
        self.assertEqual(project.primary_language_tag, "ru")

    def test_update_or_create_same_language_is_idempotent_and_different_language_conflicts(self):
        with self.assertRaises(ValidationError):
            Project.objects.update_or_create(
                code="UPDATE-OR-CREATE-MISSING",
                defaults={"name": "Must not persist"},
                create_defaults={"name": "Missing language"},
            )
        with self.assertRaises(ValidationError):
            Project.objects.update_or_create(
                code="UPDATE-OR-CREATE-NO-DEFAULTS-LEAK",
                defaults={"primary_language_tag": "ru"},
                create_defaults={"name": "Explicit create defaults stay exact"},
            )
        project, created = Project.objects.update_or_create(
            code="UPDATE-OR-CREATE",
            defaults={"name": "Created", "primary_language_tag": "RU"},
        )
        self.assertTrue(created)
        same, created = Project.objects.update_or_create(
            code=project.code,
            defaults={"name": "Updated", "primary_language_tag": "rU"},
        )
        self.assertFalse(created)
        self.assertEqual(same.pk, project.pk)
        self.assertEqual(same.name, "Updated")

        for values in (
            {
                "kwargs": {"primary_language_tag__iexact": "ru"},
                "defaults": {"name": "Must not update"},
            },
            {
                "kwargs": {},
                "defaults": {"primary_language_assignment__in": ["EXPLICIT"]},
            },
            {
                "kwargs": {},
                "defaults": {"name": "Must not update"},
                "create_defaults": {"primary_language_tag__in": ["ru"]},
            },
        ):
            with self.subTest(values=values):
                with self.assertNumQueries(0), self.assertRaises(ValidationError):
                    Project.objects.update_or_create(
                        code=project.code,
                        defaults=values["defaults"],
                        create_defaults=values.get("create_defaults"),
                        **values["kwargs"],
                    )

        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.update_or_create(
                code=project.code,
                primary_language_tag="RU",
                defaults={
                    "name": "Must not update",
                    "primary_language_tag": "rU",
                },
                create_defaults={"primary_language_tag": "kk"},
            )
        malformed_create_language = mock.Mock(return_value=object())
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.update_or_create(
                code=project.code,
                defaults={"name": "Must not update"},
                create_defaults={
                    "primary_language_tag": malformed_create_language,
                },
            )
        malformed_create_language.assert_called_once_with()
        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            Project.objects.update_or_create(
                code=project.code,
                primary_language_tag="ru",
                defaults={"name": "Must not update"},
                create_defaults={
                    "primary_language_assignment": "LEGACY_UNKNOWN",
                },
            )
        filtered, created = Project.objects.filter(code=project.code).update_or_create(
            defaults={"name": "Updated"},
        )
        self.assertFalse(created)
        self.assertEqual(filtered.pk, project.pk)
        for label, unsafe_queryset in (
            (
                "transformed update lookup",
                Project.objects.filter(primary_language_tag__iexact="ru"),
            ),
            (
                "nested Q update",
                Project.objects.filter(Q(Q(primary_language_tag="ru"))),
            ),
            (
                "combined update QuerySet",
                Project.objects.filter(code=project.code).union(
                    Project.objects.filter(primary_language_tag="ru")
                ),
            ),
        ):
            with self.subTest(label=label):
                callable_language = mock.Mock(
                    side_effect=AssertionError("callable must not run")
                )
                with self.assertNumQueries(0), self.assertRaises(ValidationError):
                    unsafe_queryset.update_or_create(
                        code=project.code,
                        defaults={"primary_language_tag": callable_language},
                    )
                callable_language.assert_not_called()
        project.refresh_from_db()
        self.assertEqual(project.name, "Updated")

        async def async_update_or_create_with_language_lookup():
            await Project.objects.aupdate_or_create(
                code=project.code,
                primary_language_assignment__in=["EXPLICIT"],
                defaults={"name": "Must not update"},
            )

        with self.assertRaises(ValidationError):
            async_to_sync(async_update_or_create_with_language_lookup)()
        async_update_callable = mock.Mock(
            side_effect=AssertionError("callable must not run")
        )

        async def async_update_or_create_with_preexisting_state():
            await Project.objects.filter(
                primary_language_assignment__in=["EXPLICIT"]
            ).aupdate_or_create(
                code=project.code,
                defaults={"primary_language_tag": async_update_callable},
            )

        with self.assertNumQueries(0), self.assertRaises(ValidationError):
            async_to_sync(async_update_or_create_with_preexisting_state)()
        async_update_callable.assert_not_called()

        same, created = Project.objects.update_or_create(
            code="UPDATE-OR-CREATE-WITH-CREATE-DEFAULTS",
            defaults={"name": "Updated after create"},
            create_defaults={
                "name": "Created through create_defaults",
                "primary_language_tag": "RU",
            },
        )
        self.assertTrue(created)
        self.assertEqual(same.primary_language_tag, "ru")
        with self.assertRaises(ValidationError):
            Project.objects.update_or_create(
                code=same.code,
                defaults={"name": "Must roll back"},
                create_defaults={"primary_language_tag": "kk"},
            )
        same.refresh_from_db()
        self.assertEqual(same.name, "Created through create_defaults")
        with self.assertRaises(ValidationError):
            Project.objects.update_or_create(
                code=project.code,
                defaults={"name": "Must roll back", "primary_language_tag": "kk"},
            )
        project.refresh_from_db()
        self.assertEqual(project.name, "Updated")
        self.assertEqual(project.primary_language_tag, "ru")

    def test_bulk_create_validates_the_full_batch_and_rejects_conflict_modes(self):
        created = Project.objects.bulk_create(
            [
                Project(code="BULK-RU", name="Bulk RU", primary_language_tag="RU"),
                Project(code="BULK-KK", name="Bulk KK", primary_language_tag="KK"),
            ]
        )
        self.assertEqual(
            [project.primary_language_tag for project in created],
            ["ru", "kk"],
        )
        count_before = Project.objects.count()
        with self.assertRaises(ValidationError):
            Project.objects.bulk_create(
                [
                    Project(
                        code="BULK-ATOMIC-VALID",
                        name="Valid",
                        primary_language_tag="uz-Latn",
                    ),
                    Project(
                        code="BULK-ATOMIC-INVALID",
                        name="Invalid",
                        primary_language_tag="uz_Latn",
                    ),
                ]
            )
        self.assertEqual(Project.objects.count(), count_before)
        candidate = Project(
            code="BULK-CONFLICT-MODE",
            name="Conflict mode",
            primary_language_tag="ru",
        )
        with self.assertRaises(ValidationError):
            Project.objects.bulk_create([candidate], ignore_conflicts=True)
        with self.assertRaises(ValidationError):
            Project.objects.bulk_create(
                [candidate],
                update_conflicts=True,
                update_fields=["name"],
                unique_fields=["code"],
            )

        async def async_bulk_create_invalid_language():
            await Project.objects.abulk_create(
                [
                    Project(
                        code="ASYNC-BULK-VALID",
                        name="Async bulk valid",
                        primary_language_tag="ru",
                    ),
                    Project(
                        code="ASYNC-BULK-INVALID",
                        name="Async bulk invalid",
                        primary_language_tag=F("code"),
                    ),
                ]
            )

        with self.assertRaises(ValidationError):
            async_to_sync(async_bulk_create_invalid_language)()
        self.assertFalse(
            Project.objects.filter(code__startswith="ASYNC-BULK-").exists()
        )

    def test_seed_creates_ru_replays_and_rejects_existing_non_ru_identity(self):
        project_id = stable_demo_uuid("project", PROJECT_CODE)
        conflicting = Project.objects.create(
            id=project_id,
            code=PROJECT_CODE,
            version="1.0.0",
            name="Conflicting language",
            primary_language_tag="kk",
        )
        with self.assertRaises(SeedConflictError):
            seed_zhanaozen_demo()
        conflicting.refresh_from_db()
        self.assertEqual(conflicting.primary_language_tag, "kk")
        conflicting.delete()

        project = seed_zhanaozen_demo()
        replay = seed_zhanaozen_demo()
        self.assertEqual(replay.pk, project.pk)
        self.assertEqual(project.primary_language_tag, "ru")
        self.assertEqual(
            project.primary_language_assignment,
            ProjectPrimaryLanguageAssignment.EXPLICIT,
        )

    def test_project_package_1_1_round_trip_preserves_explicit_and_legacy_unknown_language(self):
        explicit = self._project("PACKAGE-EXPLICIT", "UZ-latn")
        explicit_package = export_project_package(explicit)
        self.assertEqual(explicit_package["format_version"], PACKAGE_VERSION)
        self.assertEqual(explicit_package["project"]["primary_language_tag"], "uz-Latn")
        explicit.delete()
        restored_explicit = import_project_package(explicit_package)
        self.assertEqual(restored_explicit.primary_language_tag, "uz-Latn")
        self.assertEqual(
            restored_explicit.primary_language_assignment,
            ProjectPrimaryLanguageAssignment.EXPLICIT,
        )

        legacy_source = self._project("PACKAGE-LEGACY-UNKNOWN", "kk")
        legacy_package = export_project_package(legacy_source)
        legacy_package["project"]["primary_language_tag"] = "und"
        legacy_package["project"]["primary_language_assignment"] = "LEGACY_UNKNOWN"
        legacy_package = seal_project_package(legacy_package)
        legacy_source.delete()
        restored_legacy = import_project_package(legacy_package)
        self.assertEqual(restored_legacy.primary_language_tag, "und")
        self.assertEqual(
            restored_legacy.primary_language_assignment,
            ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN,
        )

    def test_project_package_1_0_is_frozen_and_only_exact_kz_upgrade_is_admitted(self):
        schema_path = (
            Path(__file__).resolve().parents[1]
            / "services"
            / "schemas"
            / "project-package-1.0.0.schema.json"
        )
        self.assertEqual(
            hashlib.sha256(schema_path.read_bytes()).hexdigest(),
            "6956ef96da4ec58b4b7b35257190917c628d46e4b983c33641abfac6ef9915c3",
        )

        ordinary = self._project("PACKAGE-V1-NEEDS-LANGUAGE", "kk")
        ordinary_v1 = self._downgrade_to_frozen_1_0(
            export_project_package(ordinary)
        )
        ordinary.delete()
        with self.assertRaises(ProjectPackageValidationError) as raised:
            import_project_package(ordinary_v1)
        self.assertEqual(raised.exception.code, PROJECT_PACKAGE_PRIMARY_LANGUAGE_REQUIRED)

        uuid_only = copy.deepcopy(ordinary_v1)
        uuid_only.pop("manifest")
        uuid_only["project"]["id"] = str(
            stable_demo_uuid("project", PROJECT_CODE)
        )
        uuid_only = seal_project_package(uuid_only)
        with self.assertRaises(ProjectPackageValidationError) as raised:
            import_project_package(uuid_only)
        self.assertEqual(raised.exception.code, PROJECT_PACKAGE_PRIMARY_LANGUAGE_REQUIRED)

        code_only = copy.deepcopy(ordinary_v1)
        code_only.pop("manifest")
        code_only["project"]["code"] = PROJECT_CODE
        code_only = seal_project_package(code_only)
        with self.assertRaises(ProjectPackageValidationError) as raised:
            import_project_package(code_only)
        self.assertEqual(raised.exception.code, PROJECT_PACKAGE_PRIMARY_LANGUAGE_REQUIRED)
        self.assertFalse(Project.objects.filter(code=PROJECT_CODE).exists())

        upgraded = upgrade_project_package_1_0_to_1_1(
            ordinary_v1,
            primary_language_tag="kk",
            primary_language_assignment="EXPLICIT",
        )
        restored = import_project_package(upgraded)
        self.assertEqual(restored.primary_language_tag, "kk")

        for tag, assignment in (
            ("und", "EXPLICIT"),
            ("ru", "LEGACY_UNKNOWN"),
            ("RU", "EXPLICIT"),
        ):
            with self.subTest(tag=tag, assignment=assignment):
                with self.assertRaises(ProjectPackageValidationError):
                    upgrade_project_package_1_0_to_1_1(
                        ordinary_v1,
                        primary_language_tag=tag,
                        primary_language_assignment=assignment,
                    )

        restored.delete()
        legacy_upgraded = upgrade_project_package_1_0_to_1_1(
            ordinary_v1,
            primary_language_tag="und",
            primary_language_assignment="LEGACY_UNKNOWN",
        )
        legacy_restored = import_project_package(legacy_upgraded)
        self.assertEqual(
            (
                legacy_restored.primary_language_tag,
                legacy_restored.primary_language_assignment,
            ),
            ("und", ProjectPrimaryLanguageAssignment.LEGACY_UNKNOWN),
        )

        kz = Project.objects.create(
            id=stable_demo_uuid("project", PROJECT_CODE),
            code=PROJECT_CODE,
            name="Exact KZ v1 identity",
            primary_language_tag="ru",
        )
        kz_v1 = self._downgrade_to_frozen_1_0(export_project_package(kz))
        kz.delete()
        restored_kz = import_project_package(kz_v1)
        self.assertEqual(restored_kz.primary_language_tag, "ru")
        self.assertEqual(
            restored_kz.primary_language_assignment,
            ProjectPrimaryLanguageAssignment.EXPLICIT,
        )


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
        project = Project.objects.create(
            code="STUDIO-TEST",
            name="Studio test",
            primary_language_tag="ru",
        )
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
        # Preserve a genuinely blank import target without bypassing any
        # append-only manager.  The round-trip test rolls back to this
        # checkpoint instead of deleting immutable audit/receipt rows.
        self.blank_import_savepoint = transaction.savepoint()
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

    def _restore_blank_import_checkpoint(self):
        transaction.savepoint_rollback(self.blank_import_savepoint)

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
        self._restore_blank_import_checkpoint()

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
