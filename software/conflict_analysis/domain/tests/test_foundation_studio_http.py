from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import Resolver404, resolve
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name
from domain.models import Project, ProjectDefinitionVersion
from domain.policies import StudioPrincipal, StudioRole
from domain.services.foundation_packages import (
    FOUNDATION_RAW_JSON_MAX_BYTES,
    FOUNDATION_RAW_JSON_MAX_NESTING,
    FoundationPackageValidationError,
    RawJSONError,
    canonical_json,
    capture_json_source,
    export_project_definition_package_2_1,
    parse_captured_json,
    parse_raw_json_bytes,
    preview_foundation_package_2_1,
    validate_foundation_package_2_1,
)
from domain.services.project_definitions import create_project_definition_draft


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "foundation_studio_definition_vectors_v1.json"
)


class FoundationStudioRawIngressTests(TestCase):
    def setUp(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.manifest = copy.deepcopy(fixture["vectors"][0]["manifest"])
        identity = self.manifest["project"]
        self.project = Project.objects.create(
            id=identity["id"],
            code=identity["code"],
            version=identity["version"],
            name="Raw ingress Project",
        )
        self.editor_principal = StudioPrincipal.for_role(
            actor_identifier="raw-editor",
            role=StudioRole.STUDIO_EDITOR,
        )
        User = get_user_model()
        self.editor_user = User.objects.create_user(
            username="raw-editor", password="test-password"
        )
        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
            )
        }
        self.editor_user.user_permissions.add(
            permissions["studio_read_definition"],
            permissions["studio_create_definition_draft"],
            permissions["studio_clone_definition_draft"],
            permissions["studio_save_definition_draft"],
        )
        group = Group.objects.create(name=project_access_group_name(self.project.pk))
        self.editor_user.groups.add(group)
        self.client = APIClient()
        self.client.force_authenticate(self.editor_user)
        self.create_url = f"/api/foundation/projects/{self.project.pk}/definitions/"

    def _create_body(self, manifest_text: str | None = None) -> bytes:
        if manifest_text is None:
            manifest_text = json.dumps(
                self.manifest, ensure_ascii=False, separators=(",", ":")
            )
        return (
            '{"code":"RAW-DRAFT","version":"1.0.0","manifest":'
            + manifest_text
            + "}"
        ).encode("utf-8")

    def _post_raw(self, payload: bytes, *, content_type: str = "application/json"):
        return self.client.generic(
            "POST", self.create_url, payload, content_type=content_type
        )

    def test_only_the_exact_canonical_foundation_routes_are_public(self):
        paths = (
            self.create_url,
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/clone/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/draft/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/validate/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/publish-initial/",
            "/api/foundation/help/studio.welcome/",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assertTrue(resolve(path).url_name.startswith("foundation-"))
        for path in (
            "/api/studio/definitions/drafts/",
            "/api/studio/definitions/17000000-0000-4000-8000-000000000001/save/",
            "/api/studio/help/studio.welcome/",
        ):
            with self.subTest(path=path), self.assertRaises(Resolver404):
                resolve(path)

    def test_real_http_rejects_every_raw_byte_vector_without_mutation(self):
        manifest_text = json.dumps(
            self.manifest, ensure_ascii=False, separators=(",", ":")
        )
        duplicate = manifest_text.replace(
            '"format":"conflict-analysis-project-definition"',
            '"format":"conflict-analysis-project-definition",'
            '"format":"conflict-analysis-project-definition"',
            1,
        )
        nested_duplicate = manifest_text.replace(
            f'"id":"{self.project.pk}"',
            f'"id":"{self.project.pk}","id":"{self.project.pk}"',
            1,
        )
        numeric_decimal = manifest_text.replace('"minimum":"-10"', '"minimum":-10', 1)
        vectors = {
            "duplicate": self._create_body(duplicate),
            "nested_duplicate": self._create_body(nested_duplicate),
            "bom": b"\xef\xbb\xbf" + self._create_body(),
            "invalid_utf8": self._create_body()[:-1] + b"\xff}",
            "nan": self._create_body().replace(b'"order":0', b'"order":NaN', 1),
            "infinity": self._create_body().replace(b'"order":0', b'"order":Infinity', 1),
            "negative_infinity": self._create_body().replace(b'"order":0', b'"order":-Infinity', 1),
            "exponent_overflow": self._create_body().replace(
                b'"order":0', b'"order":1e1000000', 1
            ),
            "trailing": self._create_body() + b"{}",
            "numeric_decimal": self._create_body(numeric_decimal),
            "non_object": b"[]",
            "wrong_exact_envelope": self._create_body(
                manifest_text.replace(
                    '"format":"conflict-analysis-project-definition"',
                    '"format":"another-definition-authority"',
                    1,
                )
            ),
        }
        for name, payload in vectors.items():
            with self.subTest(name=name):
                response = self._post_raw(payload)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(ProjectDefinitionVersion.objects.exists())

        for content_type in (
            "text/plain",
            "application/json; charset=iso-8859-1",
            "application/json; charset=utf-8; charset=utf-8",
            'application/json; charset=utf-8"',
            'application/json; charset="utf-8',
            'application/json; charset="""utf-8"""',
        ):
            with self.subTest(content_type=content_type):
                response = self._post_raw(self._create_body(), content_type=content_type)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(ProjectDefinitionVersion.objects.exists())

    def test_byte_budget_below_at_above_and_diagnostics_are_deterministic(self):
        for size in (FOUNDATION_RAW_JSON_MAX_BYTES - 1, FOUNDATION_RAW_JSON_MAX_BYTES):
            payload = b"{" + b" " * (size - 2) + b"}"
            document = parse_raw_json_bytes(payload)
            self.assertEqual(document.identity.byte_length, size)
            self.assertEqual(document.value, {})
        oversized = b"{" + b" " * (FOUNDATION_RAW_JSON_MAX_BYTES - 1) + b"}"
        failures = []
        for _ in range(2):
            with self.assertRaises(RawJSONError) as raised:
                parse_raw_json_bytes(oversized)
            failures.append(dict(raised.exception.as_dict()))
        self.assertEqual(failures[0], failures[1])
        self.assertEqual(failures[0]["code"], "RAW_JSON_BYTE_BUDGET_EXCEEDED")
        response = self._post_raw(oversized)
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(ProjectDefinitionVersion.objects.exists())

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path_oversized = oversized + b" " * 4096
            path.write_bytes(path_oversized)
            captured = capture_json_source(path)
            self.assertEqual(captured.identity.kind, "PATH_BYTES")
            self.assertEqual(captured.identity.byte_length, len(path_oversized))
            self.assertEqual(
                captured.identity.sha256,
                hashlib.sha256(path_oversized).hexdigest(),
            )
            self.assertEqual(len(captured.payload), FOUNDATION_RAW_JSON_MAX_BYTES + 1)
            with self.assertRaises(RawJSONError) as path_error:
                parse_captured_json(captured)
            self.assertEqual(path_error.exception.code, "RAW_JSON_BYTE_BUDGET_EXCEEDED")

    def test_http_validation_does_not_echo_attacker_controlled_schema_material(self):
        secret_key = "SECRET_MATERIAL_" + "x" * 100_000
        manifest = copy.deepcopy(self.manifest)
        manifest["project"][secret_key] = "must-not-echo"
        response = self._post_raw(
            self._create_body(
                json.dumps(manifest, ensure_ascii=False, separators=(",", ":"))
            )
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertLess(len(response.content), 1024)
        self.assertNotIn(secret_key.encode("utf-8"), response.content)
        self.assertNotIn(b"must-not-echo", response.content)
        self.assertFalse(ProjectDefinitionVersion.objects.exists())

    def test_deep_nesting_and_oversized_integer_are_stable_raw_failures(self):
        deep = (
            b'{"deep":'
            + b"[" * (FOUNDATION_RAW_JSON_MAX_NESTING + 1)
            + b"0"
            + b"]" * (FOUNDATION_RAW_JSON_MAX_NESTING + 1)
            + b"}"
        )
        huge_integer = b'{"value":' + b"9" * 5000 + b"}"
        for payload, expected_code in (
            (deep, "RAW_JSON_NESTING_EXCEEDED"),
            (huge_integer, "RAW_JSON_NUMBER_INVALID"),
        ):
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(RawJSONError) as raised:
                    parse_raw_json_bytes(payload)
                self.assertEqual(raised.exception.code, expected_code)
                response = self._post_raw(payload)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(response.data["code"], expected_code)
                self.assertFalse(ProjectDefinitionVersion.objects.exists())

    def test_strong_if_match_is_the_only_draft_save_authority(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="IF-MATCH-DRAFT",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor_principal,
        )
        url = f"/api/foundation/definitions/{definition.pk}/draft/"
        changed = copy.deepcopy(self.manifest)
        changed["project"]["name"] = "If-Match changed"
        body = json.dumps(
            {"manifest": changed}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        validators = (
            None,
            "*",
            f'W/"{definition.manifest_hash}"',
            definition.manifest_hash,
            f'"{definition.manifest_hash}", "{definition.manifest_hash}"',
            f'"{definition.manifest_hash.upper()}"',
            '"short"',
        )
        for validator in validators:
            kwargs = {"HTTP_IF_MATCH": validator} if validator is not None else {}
            response = self.client.generic(
                "PUT", url, body, content_type="application/json", **kwargs
            )
            self.assertEqual(response.status_code, 400, (validator, response.data))
            definition.refresh_from_db()
            self.assertEqual(definition.manifest, self.manifest)

        spoofed_body = json.dumps(
            {
                "manifest": changed,
                "expected_manifest_hash": definition.manifest_hash,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        response = self.client.generic(
            "PUT",
            url,
            spoofed_body,
            content_type="application/json",
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
        )
        self.assertEqual(response.status_code, 400, response.data)
        definition.refresh_from_db()
        self.assertEqual(definition.manifest, self.manifest)

        stale = "0" * 64
        response = self.client.generic(
            "PUT",
            url,
            body,
            content_type="application/json",
            HTTP_IF_MATCH=f'"{stale}"',
        )
        self.assertEqual(response.status_code, 409, response.data)
        definition.refresh_from_db()
        self.assertEqual(definition.manifest, self.manifest)

        response = self.client.generic(
            "PUT",
            url,
            body,
            content_type="application/json",
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response["ETag"], f'"{response.data["manifest_hash"]}"')

    def test_package_bytes_path_and_mapping_share_one_strict_parser(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="RAW-PACKAGE",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor_principal,
        )
        package = export_project_definition_package_2_1(definition)
        canonical = canonical_json(package).encode("utf-8")
        duplicate = canonical.replace(
            b'"package_scope":"PROJECT_DEFINITION"',
            b'"package_scope":"PROJECT_DEFINITION","package_scope":"PROJECT_DEFINITION"',
            1,
        )
        malformed = (
            duplicate,
            b"\xef\xbb\xbf" + canonical,
            canonical[:-1] + b"\xff",
            canonical + b"{}",
            canonical.replace(b'"order":0', b'"order":NaN', 1),
        )
        for raw in malformed:
            with self.assertRaises(FoundationPackageValidationError):
                validate_foundation_package_2_1(raw)

        reversed_top = {
            key: package[key] for key in reversed(tuple(package.keys()))
        }
        pretty = json.dumps(reversed_top, ensure_ascii=False, indent=2).encode("utf-8")
        preview_one = preview_foundation_package_2_1(canonical, project=self.project)
        preview_two = preview_foundation_package_2_1(pretty, project=self.project)
        self.assertEqual(preview_one.checksum, preview_two.checksum)
        self.assertNotEqual(preview_one.raw_input_sha256, preview_two.raw_input_sha256)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "definition-package.json"
            path.write_bytes(canonical)
            path_preview = preview_foundation_package_2_1(path, project=self.project)
        self.assertEqual(path_preview.raw_input_kind, "PATH_BYTES")
        self.assertEqual(path_preview.raw_input_sha256, hashlib.sha256(canonical).hexdigest())
        mapping_preview = preview_foundation_package_2_1(package, project=self.project)
        self.assertEqual(mapping_preview.raw_input_kind, "CANONICAL_MAPPING")

        cyclic: dict[str, object] = {}
        cyclic["self"] = cyclic
        with self.assertRaises(RawJSONError) as cyclic_error:
            capture_json_source(cyclic)
        self.assertEqual(
            cyclic_error.exception.code,
            "RAW_JSON_MAPPING_NOT_SERIALIZABLE",
        )

    def test_exact_help_query_rejects_duplicate_values(self):
        response = self.client.get(
            "/api/foundation/help/studio.welcome/"
            "?application=OTHER&application=STUDIO&locale=en&version=1.0.0"
        )
        self.assertEqual(response.status_code, 404, response.data)
