from __future__ import annotations

import base64
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import Resolver404, resolve
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory

from domain.api.studio_definitions import (
    attempt_definition_package_2_1,
    project_access_group_name,
)
from domain.enums import PublicationStatus
from domain.models import (
    AuditEvent,
    ImportRun,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    ProjectWorkspace,
    _canonical_studio_write,
)
from domain.policies import (
    StudioCapability,
    StudioPrincipal,
    StudioRole,
    bootstrap_initial_project_definition,
    validate_project_definition,
)
from domain.services.foundation_packages import (
    FOUNDATION_RAW_JSON_MAX_BYTES,
    FOUNDATION_RAW_JSON_MAX_NESTING,
    FoundationPackageValidationError,
    RawJSONError,
    canonical_json,
    capture_json_source,
    export_project_definition_package_2_1,
    foundation_import_service_capabilities_2_1,
    parse_captured_json,
    parse_raw_json_bytes,
    preview_foundation_package_2_1,
    seal_foundation_package_2_1,
    validate_foundation_package_2_1,
)
from domain.services.project_definitions import (
    clone_project_definition_draft,
    create_project_definition_draft,
    hash_project_definition_manifest_v1,
)
from domain.tests.test_foundation_studio_bootstrap import (
    FoundationStudioBootstrapMixin,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "foundation_studio_definition_vectors_v1.json"
)


class _AdversarialBoundedWSGIInput:
    """Short-read stream that raises if a caller asks past the byte budget."""

    def __init__(self, payload: bytes, *, max_bytes: int) -> None:
        self._payload = payload
        self._offset = 0
        self._budget = max_bytes + 1
        self.bytes_served = 0

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        if self.bytes_served >= self._budget:
            raise AssertionError("HTTP body read exceeded max_bytes + 1")
        remaining_budget = self._budget - self.bytes_served
        requested = len(self._payload) - self._offset if size < 0 else size
        served = min(
            requested,
            remaining_budget,
            len(self._payload) - self._offset,
        )
        chunk = self._payload[self._offset : self._offset + served]
        self._offset += served
        self.bytes_served += served
        return chunk

    def readline(self, size: int = -1) -> bytes:
        return self.read(size)


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
        self.editor_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="domain",
                content_type__model="importrun",
                codename="add_importrun",
            )
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

    def test_raw_ingress_has_one_authoritative_service_module(self):
        domain_dir = Path(__file__).resolve().parents[1]
        self.assertFalse((domain_dir / "services" / "raw_ingest.py").exists())

        for relative_path in (
            Path("api") / "studio_definitions.py",
            Path("services") / "foundation_packages.py",
            Path("services") / "project_definitions.py",
        ):
            source = (domain_dir / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("domain.services.raw_ingest", source)

    def test_only_the_exact_canonical_foundation_routes_are_public(self):
        paths = (
            self.create_url,
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/clone/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/draft/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/validate/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/publish-initial/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/publish-successor/",
            "/api/foundation/definitions/17000000-0000-4000-8000-000000000001/package/2.1/",
            "/api/foundation/projects/17000000-0000-4000-8000-000000000001/definition-packages/2.1/preview/",
            "/api/foundation/projects/17000000-0000-4000-8000-000000000001/definition-packages/2.1/attempt/",
            "/api/foundation/projects/bootstrap-first-draft/",
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

    def test_package_http_preview_attempt_and_export_preserve_both_hashes(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="HTTP-PACKAGE",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor_principal,
        )
        package = export_project_definition_package_2_1(definition)
        request_bytes = canonical_json(package).encode("utf-8")
        project_prefix = f"/api/foundation/projects/{self.project.pk}"

        preview = self.client.generic(
            "POST",
            f"{project_prefix}/definition-packages/2.1/preview/",
            request_bytes,
            content_type="application/json",
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["intended_action"], "REUSE_EXACT")
        self.assertEqual(preview.data["raw_input_kind"], "HTTP_BYTES")
        self.assertEqual(
            preview.data["raw_input_sha256"],
            hashlib.sha256(request_bytes).hexdigest(),
        )
        self.assertFalse(ImportRun.objects.exists())

        attempt = self.client.generic(
            "POST",
            f"{project_prefix}/definition-packages/2.1/attempt/",
            request_bytes,
            content_type="application/json",
        )
        self.assertEqual(attempt.status_code, 200, attempt.data)
        self.assertEqual(attempt.data["status"], "COMMITTED")
        self.assertEqual(attempt.data["receipt"]["id"], attempt.data["receipt_id"])
        self.assertEqual(
            attempt.data["receipt"]["selected_input"]["raw_input_sha256"],
            hashlib.sha256(request_bytes).hexdigest(),
        )

        exported = self.client.get(
            f"/api/foundation/definitions/{definition.pk}/package/2.1/"
        )
        expected_bytes = (canonical_json(package) + "\n").encode("utf-8")
        representation_sha256 = hashlib.sha256(expected_bytes).hexdigest()
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.content, expected_bytes)
        self.assertEqual(exported["ETag"], f'"{representation_sha256}"')
        self.assertEqual(
            exported["X-Foundation-Semantic-Payload-SHA256"],
            package["manifest"]["payload_sha256"],
        )
        self.assertNotEqual(
            representation_sha256,
            package["manifest"]["payload_sha256"],
        )
        reimport_preview = preview_foundation_package_2_1(
            exported.content,
            project=self.project,
        )
        self.assertEqual(reimport_preview.selected_definition_id, str(definition.pk))

    def test_attempt_malformed_bytes_uses_minimal_service_and_durable_receipt(self):
        baseline_definitions = ProjectDefinitionVersion.objects.count()
        response = self.client.generic(
            "POST",
            f"/api/foundation/projects/{self.project.pk}/definition-packages/2.1/attempt/",
            b'{"format":',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "REJECTED")
        self.assertIsNone(response.data["preview"])
        receipt = ImportRun.objects.get(pk=response.data["receipt_id"])
        self.assertEqual(
            receipt.actor_identifier,
            f"foundation-http-import:django-user:{self.editor_user.pk}",
        )
        self.assertEqual(receipt.selected_input["raw_input_kind"], "HTTP_BYTES")
        self.assertEqual(ProjectDefinitionVersion.objects.count(), baseline_definitions)

    def test_create_draft_package_requires_human_create_before_service(self):
        source = create_project_definition_draft(
            project=self.project,
            code="HTTP-PACKAGE-CREATE",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor_principal,
        )
        source_id = source.pk
        raw = canonical_json(export_project_definition_package_2_1(source)).encode(
            "utf-8"
        )
        source.delete()

        User = get_user_model()
        reader = User.objects.create_user(
            username="http-package-reader",
            password="test-password",
        )
        reader.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
                codename="studio_read_definition",
            ),
            Permission.objects.get(
                content_type__app_label="domain",
                content_type__model="importrun",
                codename="add_importrun",
            ),
        )
        reader.groups.add(
            Group.objects.get(name=project_access_group_name(self.project.pk))
        )
        prefix = f"/api/foundation/projects/{self.project.pk}/definition-packages/2.1"
        self.client.force_authenticate(reader)
        preview = self.client.generic(
            "POST",
            f"{prefix}/preview/",
            raw,
            content_type="application/json",
        )
        self.assertEqual(preview.status_code, 200, preview.data)
        self.assertEqual(preview.data["intended_action"], "CREATE_DRAFT")
        denied = self.client.generic(
            "POST",
            f"{prefix}/attempt/",
            raw,
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertFalse(ImportRun.objects.exists())
        self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())

        self.client.force_authenticate(self.editor_user)
        committed = self.client.generic(
            "POST",
            f"{prefix}/attempt/",
            raw,
            content_type="application/json",
        )
        self.assertEqual(committed.status_code, 200, committed.data)
        self.assertEqual(committed.data["status"], "COMMITTED")
        self.assertTrue(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())

    def test_package_query_and_service_authority_spoof_fail_before_receipt(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="HTTP-PACKAGE-SPOOF",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor_principal,
        )
        raw = canonical_json(export_project_definition_package_2_1(definition)).encode(
            "utf-8"
        )
        prefix = f"/api/foundation/projects/{self.project.pk}/definition-packages/2.1"
        responses = (
            self.client.generic(
                "POST",
                f"{prefix}/preview/",
                raw,
                content_type="application/json",
                HTTP_X_SERVICE_CONTEXT="spoof",
            ),
            self.client.generic(
                "POST",
                f"{prefix}/attempt/?locale=ru",
                raw,
                content_type="application/json",
            ),
            self.client.generic(
                "POST",
                f"{prefix}/attempt/?service_purpose=spoof",
                raw,
                content_type="application/json",
            ),
            self.client.generic(
                "POST",
                f"{prefix}/attempt/",
                raw,
                content_type="application/json",
                HTTP_IF_MATCH='"' + "0" * 64 + '"',
            ),
        )
        self.assertEqual(
            [item.status_code for item in responses],
            [400, 400, 400, 400],
        )
        self.assertFalse(ImportRun.objects.exists())

    def test_new_package_routes_have_401_403_scoped_404_and_real_csrf(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="HTTP-PACKAGE-AUTH",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor_principal,
        )
        raw = canonical_json(export_project_definition_package_2_1(definition)).encode(
            "utf-8"
        )
        prefix = f"/api/foundation/projects/{self.project.pk}/definition-packages/2.1"
        anonymous = APIClient()
        self.assertEqual(
            anonymous.generic(
                "POST",
                f"{prefix}/preview/",
                raw,
                content_type="application/json",
            ).status_code,
            401,
        )

        User = get_user_model()
        no_import = User.objects.create_user(
            username="http-package-no-import", password="test-password"
        )
        read_permission = Permission.objects.get(
            content_type__app_label="domain",
            content_type__model="projectdefinitionversion",
            codename="studio_read_definition",
        )
        import_permission = Permission.objects.get(
            content_type__app_label="domain",
            content_type__model="importrun",
            codename="add_importrun",
        )
        no_import.user_permissions.add(read_permission)
        no_import.groups.add(
            Group.objects.get(name=project_access_group_name(self.project.pk))
        )
        self.client.force_authenticate(no_import)
        self.assertEqual(
            self.client.generic(
                "POST",
                f"{prefix}/preview/",
                raw,
                content_type="application/json",
            ).status_code,
            403,
        )

        inaccessible = User.objects.create_user(
            username="http-package-inaccessible", password="test-password"
        )
        inaccessible.user_permissions.add(read_permission, import_permission)
        self.client.force_authenticate(inaccessible)
        self.assertEqual(
            self.client.generic(
                "POST",
                f"{prefix}/preview/",
                raw,
                content_type="application/json",
            ).status_code,
            404,
        )
        self.assertFalse(ImportRun.objects.exists())

        session = APIClient(enforce_csrf_checks=True)
        self.assertTrue(
            session.login(username="raw-editor", password="test-password")
        )
        definition_url = f"/api/foundation/definitions/{definition.pk}/"
        self.assertEqual(session.get(definition_url).status_code, 200)
        csrf_token = session.cookies["csrftoken"].value
        denied = session.generic(
            "POST",
            f"{prefix}/attempt/",
            raw,
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(ImportRun.objects.exists())
        accepted = session.generic(
            "POST",
            f"{prefix}/attempt/",
            bytes(bytearray(raw)),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)
        self.assertEqual(accepted.data["status"], "COMMITTED")
        receipt_count = ImportRun.objects.count()
        for content_type in ("text/plain", "application/json; charset=iso-8859-1"):
            with self.subTest(content_type=content_type):
                invalid_media = session.generic(
                    "POST",
                    f"{prefix}/attempt/",
                    raw,
                    content_type=content_type,
                    HTTP_X_CSRFTOKEN=csrf_token,
                )
                self.assertEqual(invalid_media.status_code, 400)
                self.assertEqual(ImportRun.objects.count(), receipt_count)

    def test_successor_rejects_unknown_query_before_lifecycle_transition(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="HTTP-SUCCESSOR-QUERY",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor_principal,
        )
        User = get_user_model()
        publisher = User.objects.create_user(
            username="http-successor-publisher",
            password="test-password",
        )
        publisher.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
                codename__in=(
                    "studio_read_definition",
                    "studio_validate_definition",
                    "studio_publish_definition",
                ),
            )
        )
        publisher.groups.add(
            Group.objects.get(name=project_access_group_name(self.project.pk))
        )
        self.client.force_authenticate(publisher)
        response = self.client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-successor/?unexpected=1",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        for locale in (None, "", "ru RU", "en-" + "x" * 40):
            with self.subTest(locale=locale):
                malformed_locale = self.client.post(
                    f"/api/foundation/definitions/{definition.pk}/publish-successor/",
                    {"locale": locale},
                    format="json",
                )
                self.assertEqual(
                    malformed_locale.status_code,
                    400,
                    malformed_locale.data,
                )
        definition.refresh_from_db()
        self.assertEqual(definition.publication_status, "DRAFT")

    def test_first_project_bootstrap_is_atomic_audited_and_retries_as_409(self):
        project_id = uuid4()
        definition_id = uuid4()
        manifest = copy.deepcopy(self.manifest)
        manifest["project"].update(
            {
                "id": str(project_id),
                "code": "HTTP-FIRST-PROJECT",
                "version": "1.0.0",
            }
        )
        payload = {
            "project": {
                "id": str(project_id),
                "code": "HTTP-FIRST-PROJECT",
                "version": "1.0.0",
                "name": "First project",
                "description": "Created by the canonical bootstrap gateway.",
                "metadata": {},
            },
            "definition": {
                "id": str(definition_id),
                "code": "HTTP-FIRST-DRAFT",
                "version": "1.0.0",
                "manifest": manifest,
                "semantic_version": "1.0.0",
                "construct_version": "1.0.0",
            },
        }
        url = "/api/foundation/projects/bootstrap-first-draft/"
        created = self.client.post(url, payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual(created.data["project"]["id"], str(project_id))
        self.assertEqual(created.data["definition"]["id"], str(definition_id))
        self.assertEqual(
            created.data["object_scope_group"],
            project_access_group_name(project_id),
        )
        self.assertTrue(
            self.editor_user.groups.filter(
                name=project_access_group_name(project_id)
            ).exists()
        )
        audit = AuditEvent.objects.get(pk=created.data["audit_event_id"])
        self.assertEqual(audit.actor_identifier, f"django-user:{self.editor_user.pk}")
        self.assertEqual(audit.action, "CREATE")

        repeated = self.client.post(url, payload, format="json")
        self.assertEqual(repeated.status_code, 409, repeated.data)
        self.assertEqual(repeated.data["code"], "PROJECT_ID_CONFLICT")
        self.assertEqual(Project.objects.filter(pk=project_id).count(), 1)
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(pk=definition_id).count(),
            1,
        )

    def test_exact_help_query_rejects_duplicate_values(self):
        response = self.client.get(
            "/api/foundation/help/studio.welcome/"
            "?application=OTHER&application=STUDIO&locale=en&version=1.0.0"
        )
        self.assertEqual(response.status_code, 404, response.data)


class FoundationStudioApplicationGatewayHttpTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()
        user_model = get_user_model()
        self.editor_user = user_model.objects.create_user(
            username="gateway-http-editor",
            password="test-password",
        )
        self.publisher_user = user_model.objects.create_user(
            username="gateway-http-publisher",
            password="test-password",
        )
        self.import_reader = user_model.objects.create_user(
            username="gateway-http-import-reader",
            password="test-password",
        )
        definition_permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
            )
        }
        import_permission = Permission.objects.get(
            content_type__app_label="domain",
            content_type__model="importrun",
            codename="add_importrun",
        )
        self.editor_user.user_permissions.add(
            definition_permissions["studio_read_definition"],
            definition_permissions["studio_create_definition_draft"],
            definition_permissions["studio_clone_definition_draft"],
            definition_permissions["studio_save_definition_draft"],
        )
        self.publisher_user.user_permissions.add(
            definition_permissions["studio_read_definition"],
            definition_permissions["studio_validate_definition"],
            definition_permissions["studio_publish_definition"],
            import_permission,
        )
        self.import_reader.user_permissions.add(
            definition_permissions["studio_read_definition"],
            import_permission,
        )
        scope = Group.objects.create(name=project_access_group_name(self.project.pk))
        scope.user_set.add(
            self.editor_user,
            self.publisher_user,
            self.import_reader,
        )
        self.client = APIClient()

    def test_http_admission_is_transport_bounded_before_domain_work(self):
        definition = self.draft(code="HTTP-ADMISSION-BUDGET")
        attempt_url = (
            f"/api/foundation/projects/{self.project.pk}/"
            "definition-packages/2.1/attempt/"
        )
        oversized = (
            b'{"padding":"'
            + b"x" * (FOUNDATION_RAW_JSON_MAX_BYTES + 4096)
            + b'"}'
        )
        basic_authorization = "Basic " + base64.b64encode(
            b"gateway-http-import-reader:test-password"
        ).decode("ascii")

        session = APIClient(enforce_csrf_checks=True)
        self.assertTrue(
            session.login(
                username="gateway-http-import-reader",
                password="test-password",
            )
        )
        self.assertEqual(
            session.get(
                f"/api/foundation/definitions/{definition.pk}/"
            ).status_code,
            200,
        )
        csrf_token = session.cookies["csrftoken"].value

        membership_model = Group.user_set.through

        def domain_counts() -> dict[str, int]:
            return {
                "projects": Project.objects.count(),
                "definitions": ProjectDefinitionVersion.objects.count(),
                "imports": ImportRun.objects.count(),
                "audits": AuditEvent.objects.count(),
                "publications": ProjectPublication.objects.count(),
                "workspaces": ProjectWorkspace.objects.count(),
                "groups": Group.objects.count(),
                "memberships": membership_model.objects.count(),
            }

        baseline = domain_counts()

        def direct_request(
            stream: _AdversarialBoundedWSGIInput,
            *,
            content_type: str = "application/json",
            content_length: str | None = None,
            session_csrf: str | None | bool = False,
        ):
            factory = APIRequestFactory(enforce_csrf_checks=True)
            headers: dict[str, str] = {}
            if session_csrf is False:
                headers["HTTP_AUTHORIZATION"] = basic_authorization
            else:
                headers["HTTP_COOKIE"] = f"csrftoken={csrf_token}"
                if isinstance(session_csrf, str):
                    headers["HTTP_X_CSRFTOKEN"] = session_csrf
            django_request = factory.generic(
                "POST",
                attempt_url,
                b"",
                content_type=content_type,
                **headers,
            )
            if session_csrf is not False:
                django_request.user = self.import_reader
            django_request._stream = stream
            django_request._read_started = False
            django_request.META["CONTENT_TYPE"] = content_type
            django_request.META.pop("CONTENT_LENGTH", None)
            if content_length is not None:
                django_request.META["CONTENT_LENGTH"] = content_length
            return attempt_definition_package_2_1(
                django_request,
                project_id=self.project.pk,
            )

        # Lengthless Basic and valid-session requests may consume only the
        # sentinel byte that establishes over-budget input, never the remainder.
        for name, session_csrf in (
            ("basic", False),
            ("valid_session_csrf", csrf_token),
        ):
            with self.subTest(name=name):
                stream = _AdversarialBoundedWSGIInput(
                    oversized,
                    max_bytes=FOUNDATION_RAW_JSON_MAX_BYTES,
                )
                response = direct_request(stream, session_csrf=session_csrf)
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(
                    response.data["code"],
                    "RAW_JSON_BYTE_BUDGET_EXCEEDED",
                )
                self.assertLessEqual(
                    stream.bytes_served,
                    FOUNDATION_RAW_JSON_MAX_BYTES + 1,
                )
                self.assertEqual(domain_counts(), baseline)

        # Missing/invalid session CSRF is denied before transport admission.
        for name, token in (
            ("missing_session_csrf", None),
            ("invalid_session_csrf", "0" * 64),
        ):
            with self.subTest(name=name):
                stream = _AdversarialBoundedWSGIInput(
                    oversized,
                    max_bytes=FOUNDATION_RAW_JSON_MAX_BYTES,
                )
                response = direct_request(stream, session_csrf=token)
                self.assertEqual(response.status_code, 403)
                self.assertEqual(stream.bytes_served, 0)
                self.assertEqual(domain_counts(), baseline)

        # Media admission and a trustworthy known-over-budget length are both
        # zero-read failures. No full-body raw identity or receipt is created.
        for name, content_type, content_length in (
            (
                "malformed_charset",
                "application/json; charset=iso-8859-1",
                None,
            ),
            (
                "known_content_length_oversize",
                "application/json",
                str(len(oversized)),
            ),
        ):
            with self.subTest(name=name):
                stream = _AdversarialBoundedWSGIInput(
                    oversized,
                    max_bytes=FOUNDATION_RAW_JSON_MAX_BYTES,
                )
                response = direct_request(
                    stream,
                    content_type=content_type,
                    content_length=content_length,
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(stream.bytes_served, 0)
                self.assertEqual(domain_counts(), baseline)

        # A declared/observed length mismatch is also an admission failure and
        # cannot be converted into a durable malformed-package attempt.
        mismatched_stream = _AdversarialBoundedWSGIInput(
            b"{}",
            max_bytes=FOUNDATION_RAW_JSON_MAX_BYTES,
        )
        mismatched = direct_request(
            mismatched_stream,
            content_length="16",
        )
        self.assertEqual(mismatched.status_code, 400, mismatched.data)
        self.assertEqual(
            mismatched.data["code"],
            "RAW_JSON_CONTENT_LENGTH_MISMATCH",
        )
        self.assertEqual(mismatched_stream.bytes_served, 2)
        self.assertEqual(domain_counts(), baseline)

    def test_preloaded_oversize_body_has_no_partial_identity_or_receipt(self):
        attempt_url = (
            f"/api/foundation/projects/{self.project.pk}/"
            "definition-packages/2.1/attempt/"
        )
        oversized = (
            b'{"padding":"'
            + b"x" * (FOUNDATION_RAW_JSON_MAX_BYTES + 4096)
            + b'"}'
        )
        authorization = "Basic " + base64.b64encode(
            b"gateway-http-import-reader:test-password"
        ).decode("ascii")
        factory = APIRequestFactory(enforce_csrf_checks=True)
        django_request = factory.generic(
            "POST",
            attempt_url,
            b"",
            content_type="application/json",
            HTTP_AUTHORIZATION=authorization,
        )
        stream = _AdversarialBoundedWSGIInput(
            oversized,
            max_bytes=FOUNDATION_RAW_JSON_MAX_BYTES,
        )
        django_request._stream = stream
        django_request._read_started = False
        django_request._body = oversized
        django_request.META["CONTENT_TYPE"] = "application/json"
        django_request.META.pop("CONTENT_LENGTH", None)

        membership_model = Group.user_set.through
        baseline = {
            "projects": Project.objects.count(),
            "definitions": ProjectDefinitionVersion.objects.count(),
            "imports": ImportRun.objects.count(),
            "audits": AuditEvent.objects.count(),
            "publications": ProjectPublication.objects.count(),
            "workspaces": ProjectWorkspace.objects.count(),
            "groups": Group.objects.count(),
            "memberships": membership_model.objects.count(),
        }
        real_sha256 = hashlib.sha256

        def bounded_sha256(value=b"", *args, **kwargs):
            if isinstance(value, (bytes, bytearray, memoryview)) and len(value) > (
                FOUNDATION_RAW_JSON_MAX_BYTES + 1
            ):
                raise AssertionError("oversized preloaded body was hashed")
            return real_sha256(value, *args, **kwargs)

        with patch(
            "domain.services.foundation_packages.hashlib.sha256",
            side_effect=bounded_sha256,
        ):
            response = attempt_definition_package_2_1(
                django_request,
                project_id=self.project.pk,
            )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data["code"], "RAW_JSON_BYTE_BUDGET_EXCEEDED")
        self.assertEqual(stream.bytes_served, 0)
        self.assertFalse(
            hasattr(django_request, "_foundation_raw_json_capture")
        )
        self.assertEqual(
            {
                "projects": Project.objects.count(),
                "definitions": ProjectDefinitionVersion.objects.count(),
                "imports": ImportRun.objects.count(),
                "audits": AuditEvent.objects.count(),
                "publications": ProjectPublication.objects.count(),
                "workspaces": ProjectWorkspace.objects.count(),
                "groups": Group.objects.count(),
                "memberships": membership_model.objects.count(),
            },
            baseline,
        )

    def test_successor_http_201_etag_pin_preservation_and_stable_retry_409(self):
        initial = bootstrap_initial_project_definition(
            definition=self.draft(code="HTTP-SUCCESSOR-INITIAL"),
            principal=self.publisher(actor="initial-publisher"),
            actor_identifier="initial-publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        old_pin = (
            initial.workspace.pk,
            initial.workspace.definition_version_id,
            initial.workspace.definition_manifest_hash,
        )
        successor = clone_project_definition_draft(
            initial.definition,
            code="HTTP-SUCCESSOR-V2",
            version="2.0.0",
            principal=self.editor(actor="successor-editor"),
        )
        successor = validate_project_definition(
            successor,
            actor_identifier="successor-publisher",
            principal=self.publisher(actor="successor-publisher"),
        )
        self.client.force_authenticate(self.publisher_user)
        url = f"/api/foundation/definitions/{successor.pk}/publish-successor/"
        response = self.client.post(url, {}, format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response["ETag"], f'"{successor.manifest_hash}"')
        self.assertIsNone(response.data["initial_workspace_id"])
        self.assertEqual(response.data["definition"]["id"], str(successor.pk))
        self.assertEqual(
            response.data["definition"]["publication_status"],
            PublicationStatus.PUBLISHED,
        )
        publication = ProjectPublication.objects.get(
            pk=response.data["publication_id"]
        )
        self.assertIsNone(publication.initial_workspace_id)
        self.assertEqual(
            ProjectPublication.objects.filter(initial_workspace__isnull=True).count(),
            1,
        )
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        initial.workspace.refresh_from_db()
        self.assertEqual(
            (
                initial.workspace.pk,
                initial.workspace.definition_version_id,
                initial.workspace.definition_manifest_hash,
            ),
            old_pin,
        )

        retry = self.client.post(url, {}, format="json")
        self.assertEqual(retry.status_code, 409, retry.data)
        self.assertEqual(retry.data["code"], "SUCCESSOR_PUBLICATION_CONFLICT")
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)

    def test_first_project_http_rejects_non_exact_nested_dto_without_rows(self):
        project_id = uuid4()
        definition_id = uuid4()
        manifest = copy.deepcopy(self.manifest)
        manifest["project"].update(
            {
                "id": str(project_id),
                "code": "HTTP-EXACT-ENVELOPE",
                "version": "1.0.0",
            }
        )
        base = {
            "project": {
                "id": str(project_id),
                "code": "HTTP-EXACT-ENVELOPE",
                "version": "1.0.0",
                "name": "Exact envelope project",
                "description": "Must remain absent on invalid nested DTOs.",
                "metadata": {},
            },
            "definition": {
                "id": str(definition_id),
                "code": "HTTP-EXACT-ENVELOPE-DRAFT",
                "version": "1.0.0",
                "manifest": manifest,
                "semantic_version": "1.0.0",
                "construct_version": "1.0.0",
            },
        }
        baseline = {
            "projects": Project.objects.count(),
            "groups": Group.objects.count(),
            "memberships": self.editor_user.groups.count(),
            "definitions": ProjectDefinitionVersion.objects.count(),
            "audits": AuditEvent.objects.count(),
        }
        variants = {}
        invalid_string_values = {
            "numeric": 123,
            "boolean": True,
            "list": [],
            "null": None,
        }
        for section, fields in (
            (
                "project",
                ("id", "code", "version", "name", "description"),
            ),
            (
                "definition",
                (
                    "id",
                    "code",
                    "version",
                    "semantic_version",
                    "construct_version",
                ),
            ),
        ):
            for field in fields:
                for value_kind, value in invalid_string_values.items():
                    variants[f"{section}_{field}_{value_kind}"] = (
                        section,
                        field,
                        value,
                    )
        variants.update(
            {
                "invalid_project_uuid": ("project", "id", "not-a-uuid"),
                "invalid_definition_uuid": (
                    "definition",
                    "id",
                    "not-a-uuid",
                ),
            }
        )
        for section, field in (
            ("project", "metadata"),
            ("definition", "manifest"),
        ):
            for value_kind, value in {
                "string": "{}",
                **invalid_string_values,
            }.items():
                variants[f"{section}_{field}_{value_kind}"] = (
                    section,
                    field,
                    value,
                )
        self.client.force_authenticate(self.editor_user)
        for name, (section, field, value) in variants.items():
            with self.subTest(name=name):
                payload = copy.deepcopy(base)
                payload[section][field] = value
                response = self.client.post(
                    "/api/foundation/projects/bootstrap-first-draft/",
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(Project.objects.count(), baseline["projects"])
                self.assertEqual(Group.objects.count(), baseline["groups"])
                self.assertEqual(
                    self.editor_user.groups.count(),
                    baseline["memberships"],
                )
                self.assertEqual(
                    ProjectDefinitionVersion.objects.count(),
                    baseline["definitions"],
                )
                self.assertEqual(AuditEvent.objects.count(), baseline["audits"])
                self.assertFalse(Project.objects.filter(pk=project_id).exists())
                self.assertFalse(
                    Group.objects.filter(
                        name=project_access_group_name(project_id)
                    ).exists()
                )

    def test_retired_http_get_exact_dto_etag_and_lifecycle_mutation_denial(self):
        now = timezone.now()
        manifest_hash = hash_project_definition_manifest_v1(
            self.manifest,
            project=self.project,
        )
        retired = ProjectDefinitionVersion(
            project=self.project,
            code="HTTP-RETIRED-READ",
            version="9.0.0",
            manifest=copy.deepcopy(self.manifest),
            manifest_hash=manifest_hash,
            schema_version="1.0.0",
            semantic_version="1.0.0",
            construct_version="1.0.0",
            publication_status=PublicationStatus.RETIRED,
            validated_at=now,
            validated_by="retired-publisher",
            validation_result={"valid": True},
            published_at=now,
            published_by="retired-publisher",
        )
        with _canonical_studio_write("definition"):
            retired.save(force_insert=True)

        self.client.force_authenticate(self.editor_user)
        url = f"/api/foundation/definitions/{retired.pk}/"
        response = self.client.get(url)
        expected_dto = {
            "id": str(retired.pk),
            "project_id": str(self.project.pk),
            "code": retired.code,
            "version": retired.version,
            "publication_status": PublicationStatus.RETIRED,
            "manifest": retired.manifest,
            "manifest_hash": manifest_hash,
            "schema_version": "1.0.0",
            "semantic_version": "1.0.0",
            "construct_version": "1.0.0",
            "supersedes_id": None,
        }
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data, expected_dto)
        self.assertEqual(response["ETag"], f'"{manifest_hash}"')

        changed = copy.deepcopy(self.manifest)
        changed["project"]["name"] = "Forbidden RETIRED mutation"
        denied = self.client.put(
            f"{url}draft/",
            {"manifest": changed},
            format="json",
            HTTP_IF_MATCH=f'"{manifest_hash}"',
        )
        self.assertEqual(denied.status_code, 400, denied.data)
        retired.refresh_from_db()
        self.assertEqual(retired.publication_status, PublicationStatus.RETIRED)
        self.assertEqual(retired.manifest_hash, manifest_hash)
        self.assertEqual(retired.manifest, self.manifest)

    def test_bootstrap_published_package_human_gate_query_and_service_path(self):
        source = self.draft(code="HTTP-PACKAGE-BOOTSTRAP")
        source_id = source.pk
        package = export_project_definition_package_2_1(source)
        package["project_definition"].update(
            publication_status=PublicationStatus.PUBLISHED,
            is_current=True,
            validated_at="2026-08-27T00:00:00Z",
            validated_by="source-publisher",
            validation_result={"valid": True, "source": "external receipt"},
            published_at="2026-08-27T00:01:00Z",
            published_by="source-publisher",
        )
        package = seal_foundation_package_2_1(package)
        source.delete()
        raw = canonical_json(package).encode("utf-8")
        attempt_url = (
            f"/api/foundation/projects/{self.project.pk}/"
            "definition-packages/2.1/attempt/"
        )
        query_items = [
            ("locale", "en"),
            ("initial_workspace_id", "28000000-0000-4000-8000-000000000001"),
            ("initial_workspace_code", "HTTP-PACKAGE-INITIAL"),
            ("initial_workspace_version", "1.0.0"),
            ("initial_workspace_name", "HTTP package initial workspace"),
            ("initial_workspace_is_default", "true"),
        ]
        complete_url = f"{attempt_url}?{urlencode(query_items)}"

        self.client.force_authenticate(self.import_reader)
        for invalid_query in (
            "",
            "?" + urlencode(query_items[:-1]),
            "?" + urlencode(query_items + [("locale", "ru")]),
            "?" + urlencode(query_items + [("unexpected", "value")]),
        ):
            with self.subTest(invalid_query=invalid_query):
                invalid = self.client.generic(
                    "POST",
                    attempt_url + invalid_query,
                    raw,
                    content_type="application/json",
                )
                self.assertEqual(invalid.status_code, 400, invalid.data)
                self.assertFalse(ImportRun.objects.exists())
                self.assertFalse(
                    ProjectDefinitionVersion.objects.filter(pk=source_id).exists()
                )
                self.assertFalse(ProjectPublication.objects.exists())
                self.assertFalse(ProjectWorkspace.objects.exists())

        denied = self.client.generic(
            "POST",
            complete_url,
            raw,
            content_type="application/json",
        )
        self.assertEqual(denied.status_code, 403, denied.data)
        self.assertFalse(ImportRun.objects.exists())
        self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=source_id).exists())
        self.assertFalse(ProjectPublication.objects.exists())
        self.assertFalse(ProjectWorkspace.objects.exists())

        observed_service_caps: list[tuple[str | None, frozenset]] = []

        def observe_service_caps(intended_action):
            capabilities = foundation_import_service_capabilities_2_1(
                intended_action
            )
            observed_service_caps.append((intended_action, capabilities))
            return capabilities

        self.client.force_authenticate(self.publisher_user)
        with patch(
            "domain.api.studio_definitions.foundation_import_service_capabilities_2_1",
            side_effect=observe_service_caps,
        ):
            committed = self.client.generic(
                "POST",
                complete_url,
                raw,
                content_type="application/json",
            )
        self.assertEqual(committed.status_code, 200, committed.data)
        self.assertEqual(committed.data["status"], "COMMITTED")
        self.assertEqual(
            committed.data["commit"]["action"],
            "BOOTSTRAP_PUBLISHED",
        )
        self.assertEqual(
            observed_service_caps,
            [
                (
                    "BOOTSTRAP_PUBLISHED",
                    frozenset(
                        {
                            StudioCapability.FOUNDATION_IMPORT,
                            StudioCapability.DRAFT_CREATE,
                            StudioCapability.DEFINITION_VALIDATE,
                            StudioCapability.DEFINITION_PUBLISH,
                        }
                    ),
                )
            ],
        )
        receipt = ImportRun.objects.get(pk=committed.data["receipt_id"])
        self.assertEqual(receipt.status, "COMMITTED")
        self.assertEqual(
            receipt.actor_identifier,
            f"foundation-http-import:django-user:{self.publisher_user.pk}",
        )
        self.assertEqual(
            receipt.selected_input["intended_action"],
            "BOOTSTRAP_PUBLISHED",
        )
        imported = ProjectDefinitionVersion.objects.get(pk=source_id)
        self.assertEqual(imported.publication_status, PublicationStatus.PUBLISHED)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(
            str(ProjectWorkspace.objects.get().pk),
            "28000000-0000-4000-8000-000000000001",
        )

        reuse_raw = canonical_json(
            export_project_definition_package_2_1(imported)
        ).encode("utf-8")
        preview_url = (
            f"/api/foundation/projects/{self.project.pk}/"
            "definition-packages/2.1/preview/"
        )
        reuse_preview = self.client.generic(
            "POST",
            preview_url,
            reuse_raw,
            content_type="application/json",
        )
        self.assertEqual(reuse_preview.status_code, 200, reuse_preview.data)
        self.assertEqual(reuse_preview.data["intended_action"], "REUSE_EXACT")
        receipt_count = ImportRun.objects.count()
        forbidden_workspace = self.client.generic(
            "POST",
            complete_url,
            reuse_raw,
            content_type="application/json",
        )
        self.assertEqual(forbidden_workspace.status_code, 400, forbidden_workspace.data)
        self.assertEqual(ImportRun.objects.count(), receipt_count)
