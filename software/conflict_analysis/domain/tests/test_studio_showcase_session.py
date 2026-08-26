from __future__ import annotations

import copy
import json

from django.test import SimpleTestCase

from studio_showcase.session import (
    FIXTURES,
    SHOWCASE_FORMAT,
    SHOWCASE_VERSION,
    build_fixture,
    fixture,
    validate_session,
    validated_copy,
)


class ShowcaseFixtureTests(SimpleTestCase):
    def assert_fixture_shape(
        self,
        payload: dict[str, object],
        *,
        element_count: int,
        actor_count: int,
    ) -> None:
        self.assertEqual(payload["format"], "SHOWCASE_SESSION_V1")
        self.assertEqual(payload["version"], "1.0.0")
        self.assertEqual(len(payload["analyticalElements"]), element_count)
        self.assertEqual(len(payload["actors"]), actor_count)
        self.assertEqual(
            payload["meta"],
            {
                "presentationOnly": True,
                "fixture": f"{element_count}x{actor_count}",
            },
        )

        rows = [*payload["analyticalElements"], *payload["actors"]]
        ids = [row["id"] for row in rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(validate_session(payload), [])

    def test_required_6x8_and_3x4_fixtures_have_exact_cardinality(self):
        self.assertTrue({"6x8", "3x4"}.issubset(FIXTURES))
        self.assert_fixture_shape(fixture("6x8"), element_count=6, actor_count=8)
        self.assert_fixture_shape(fixture("3x4"), element_count=3, actor_count=4)

    def test_builder_supports_arbitrary_cardinality_without_layout_constants(self):
        for element_count, actor_count in ((0, 0), (1, 9), (9, 1), (17, 11)):
            with self.subTest(
                element_count=element_count,
                actor_count=actor_count,
            ):
                self.assert_fixture_shape(
                    build_fixture(element_count, actor_count),
                    element_count=element_count,
                    actor_count=actor_count,
                )

    def test_fixture_access_is_a_deep_copy_and_unknown_name_is_rejected(self):
        first = fixture("3x4")
        first["project"]["name"] = "Изменено только в этой сессии"
        first["actors"].reverse()

        second = fixture("3x4")
        self.assertNotEqual(first, second)
        self.assertNotEqual(first["project"]["name"], second["project"]["name"])

        with self.assertRaisesRegex(ValueError, "Unknown showcase fixture"):
            fixture("4x4")

    def test_negative_cardinality_is_rejected(self):
        for dimensions in ((-1, 0), (0, -1), (-1, -1)):
            with self.subTest(dimensions=dimensions):
                with self.assertRaisesRegex(ValueError, "cannot be negative"):
                    build_fixture(*dimensions)


class ShowcaseSessionValidationTests(SimpleTestCase):
    def test_blank_duplicate_and_dangling_reference_diagnostics_are_stable(self):
        payload = fixture("3x4")
        payload["project"]["name"] = "  "

        first_element = payload["analyticalElements"][0]
        second_element = payload["analyticalElements"][1]
        third_element = payload["analyticalElements"][2]
        first_element["name"] = ""
        first_element["definition"] = "\t"
        second_element["code"] = first_element["code"].swapcase()
        third_element["id"] = first_element["id"]
        third_element["parentId"] = "element-does-not-exist"

        first_actor = payload["actors"][0]
        second_actor = payload["actors"][1]
        third_actor = payload["actors"][2]
        fourth_actor = payload["actors"][3]
        first_actor["id"] = " "
        first_actor["code"] = ""
        second_actor["name"] = "\n"
        third_actor["description"] = ""
        fourth_actor["id"] = first_element["id"]
        fourth_actor["parentId"] = "actor-does-not-exist"

        before = copy.deepcopy(payload)
        diagnostics = validate_session(payload)

        self.assertEqual(payload, before, "validation must be non-mutating")
        self.assertEqual(
            [(item["code"], item["path"]) for item in diagnostics],
            [
                ("PROJECT_NAME_BLANK", "project.name"),
                ("NAME_BLANK", "analyticalElements[0].name"),
                ("DEFINITION_BLANK", "analyticalElements[0].definition"),
                ("CODE_DUPLICATE", "analyticalElements[1].code"),
                ("ID_DUPLICATE", "analyticalElements[2].id"),
                (
                    "PARENT_REFERENCE_MISSING",
                    "analyticalElements[2].parentId",
                ),
                ("ID_BLANK", "actors[0].id"),
                ("CODE_BLANK", "actors[0].code"),
                ("NAME_BLANK", "actors[1].name"),
                ("DESCRIPTION_BLANK", "actors[2].description"),
                ("ID_DUPLICATE", "actors[3].id"),
                ("PARENT_REFERENCE_MISSING", "actors[3].parentId"),
            ],
        )
        for diagnostic in diagnostics:
            self.assertEqual(diagnostic["level"], "error")
            self.assertTrue(diagnostic["path"])
            self.assertTrue(diagnostic["message"].strip())

    def test_non_object_collections_and_rows_receive_explicit_diagnostics(self):
        payload = fixture("3x4")
        payload["analyticalElements"] = {"not": "an array"}
        payload["actors"][0] = "not an object"

        diagnostics = validate_session(payload)
        self.assertIn("COLLECTION_NOT_ARRAY", {item["code"] for item in diagnostics})
        self.assertIn("ROW_NOT_OBJECT", {item["code"] for item in diagnostics})

        self.assertEqual(
            validate_session([])[0]["code"],
            "SESSION_NOT_OBJECT",
        )

    def test_showcase_json_round_trip_preserves_marker_ids_and_order(self):
        payload = build_fixture(7, 5)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        decoded = json.loads(encoded)
        imported = validated_copy(decoded)

        self.assertIn('"format": "SHOWCASE_SESSION_V1"', encoded)
        self.assertEqual(SHOWCASE_FORMAT, "SHOWCASE_SESSION_V1")
        self.assertEqual(SHOWCASE_VERSION, "1.0.0")
        self.assertEqual(imported, payload)
        self.assertIsNot(imported, decoded)
        self.assertEqual(
            [row["id"] for row in imported["analyticalElements"]],
            [row["id"] for row in payload["analyticalElements"]],
        )
        self.assertEqual(
            [row["id"] for row in imported["actors"]],
            [row["id"] for row in payload["actors"]],
        )

    def test_non_showcase_marker_and_wrong_version_are_not_silently_imported(self):
        payload = fixture("3x4")
        payload["format"] = "FOUNDATION_PACKAGE_V2"
        payload["version"] = "999.0"

        diagnostics = validate_session(payload)
        self.assertEqual(
            {item["code"] for item in diagnostics},
            {"FORMAT_MISMATCH", "VERSION_MISMATCH"},
        )
        with self.assertRaises(ValueError):
            validated_copy(payload)
