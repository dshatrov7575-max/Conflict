from __future__ import annotations

import copy
import hashlib
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name
from domain.enums import HelpApplicationScope, PublicationStatus
from domain.models import (
    HelpTopic,
    Project,
    ProjectDefinitionVersion,
    UIHelpBinding,
    _canonical_studio_write,
)
from domain.services.foundation_packages import (
    canonical_json,
    export_project_definition_package_2_1,
)
from domain.services.project_definitions import hash_project_definition_manifest_v1
from production_studio.claim_boundaries import (
    CLAIM_BOUNDARY_CONTRACT_BYTES,
    CLAIM_BOUNDARY_CONTRACT_PATH,
    CLAIM_BOUNDARY_CONTRACT_SHA256,
)
from production_studio.tests import database_fingerprint, foundation_manifest


class ProductionStudioReadOnlyHttpTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.manifest = foundation_manifest()
        identity = cls.manifest["project"]
        cls.project = Project.objects.create(
            id=identity["id"],
            code=identity["code"],
            version=identity["version"],
            name=identity["name"],
        )
        cls.manifest_hash = hash_project_definition_manifest_v1(
            cls.manifest,
            project=cls.project,
        )
        cls.definitions: dict[str, ProjectDefinitionVersion] = {}
        now = timezone.now()
        for index, status in enumerate(PublicationStatus.values, start=1):
            lifecycle: dict[str, object] = {}
            if status in {
                PublicationStatus.VALIDATED,
                PublicationStatus.PUBLISHED,
                PublicationStatus.RETIRED,
            }:
                lifecycle.update(
                    validated_at=now,
                    validated_by="fixture-validator",
                    validation_result={"valid": True},
                )
            if status in {PublicationStatus.PUBLISHED, PublicationStatus.RETIRED}:
                lifecycle.update(
                    published_at=now,
                    published_by="fixture-publisher",
                )
            definition = ProjectDefinitionVersion(
                project=cls.project,
                code=f"C0-{status}",
                version=f"{index}.0.0",
                publication_status=status,
                manifest=copy.deepcopy(cls.manifest),
                manifest_hash=cls.manifest_hash,
                schema_version="1.0.0",
                semantic_version="1.0.0",
                construct_version="1.0.0",
                **lifecycle,
            )
            with _canonical_studio_write("definition"):
                definition.save(force_insert=True)
            cls.definitions[status] = definition

        user_model = get_user_model()
        cls.reader = user_model.objects.create_user(
            username="c0-reader",
            password="unused-by-production-studio",
        )
        cls.in_scope_without_capability = user_model.objects.create_user(
            username="c0-in-scope-no-capability",
            password="unused-by-production-studio",
        )
        cls.out_of_scope_reader = user_model.objects.create_user(
            username="c0-out-of-scope-reader",
            password="unused-by-production-studio",
        )
        read_permission = Permission.objects.get(
            content_type__app_label="domain",
            content_type__model="projectdefinitionversion",
            codename="studio_read_definition",
        )
        cls.reader.user_permissions.add(read_permission)
        cls.out_of_scope_reader.user_permissions.add(read_permission)
        scope = Group.objects.create(name=project_access_group_name(cls.project.pk))
        cls.reader.groups.add(scope)
        cls.in_scope_without_capability.groups.add(scope)

        cls.help_html = "<p>Точная справка C0.</p>"
        cls.help_sha256 = hashlib.sha256(cls.help_html.encode("utf-8")).hexdigest()
        cls.help_topic = HelpTopic(
            code="C0-HELP-TOPIC",
            version="1.0.0",
            stable_key="studio.welcome",
            title="Точная справка",
            application_scope=HelpApplicationScope.STUDIO,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="ru",
            sanitized_html=cls.help_html,
            content_sha256=cls.help_sha256,
            publication_status=PublicationStatus.PUBLISHED,
            published_at=now,
        )
        cls.help_topic.save(force_insert=True)
        cls.help_binding = UIHelpBinding(
            code="C0-HELP-BINDING",
            version="1.0.0",
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            ui_key="studio.welcome",
            locale="ru",
            help_topic=cls.help_topic,
        )
        cls.help_binding.save(force_insert=True)

    def setUp(self) -> None:
        self.api = APIClient()

    def _open_url(self, definition: ProjectDefinitionVersion) -> str:
        return f"/api/foundation/definitions/{definition.pk}/"

    def test_public_claim_contract_is_exact_cacheable_bytes_without_cookie(self):
        before = database_fingerprint()
        response = Client().get(
            reverse("production_studio:claim_boundaries_read_only_v1")
        )
        after = database_fingerprint()

        payload = CLAIM_BOUNDARY_CONTRACT_PATH.read_bytes()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, payload)
        self.assertEqual(len(response.content), CLAIM_BOUNDARY_CONTRACT_BYTES)
        self.assertEqual(
            hashlib.sha256(response.content).hexdigest(),
            CLAIM_BOUNDARY_CONTRACT_SHA256,
        )
        self.assertEqual(response["Content-Length"], str(CLAIM_BOUNDARY_CONTRACT_BYTES))
        self.assertEqual(response["ETag"], f'"{CLAIM_BOUNDARY_CONTRACT_SHA256}"')
        self.assertEqual(
            response["Cache-Control"],
            "public, max-age=31536000, immutable, no-transform",
        )
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertFalse(response.cookies)
        self.assertNotIn("Vary", response)
        self.assertEqual(after, before)

    def test_every_public_studio_route_is_get_only(self):
        definition = self.definitions[PublicationStatus.DRAFT]
        urls = (
            reverse("production_studio:entry"),
            reverse("production_studio:definition", args=(definition.pk,)),
            reverse("production_studio:claim_boundaries_read_only_v1"),
        )
        for url in urls:
            for method in ("post", "put", "patch", "delete", "head"):
                with self.subTest(url=url, method=method):
                    before = database_fingerprint()
                    response = getattr(Client(), method)(url)
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(database_fingerprint(), before)

    def test_entry_and_definition_are_pre_authenticated_shells_not_credentials(self):
        definition = self.definitions[PublicationStatus.DRAFT]
        anonymous = Client()
        before = database_fingerprint()
        entry = anonymous.get(reverse("production_studio:entry"))
        shell = anonymous.get(
            reverse("production_studio:definition", args=(definition.pk,))
        )
        self.assertEqual(entry.status_code, 401)
        self.assertEqual(shell.status_code, 401)
        self.assertFalse(entry.cookies)
        self.assertFalse(shell.cookies)
        self.assertNotIn("Location", entry)
        self.assertContains(entry, "Требуется заранее выданная сессия", status_code=401)
        combined = (entry.content + shell.content).decode("utf-8").lower()
        self.assertNotIn('type="password"', combined)
        self.assertNotIn("/login", combined)
        self.assertNotIn("/logout", combined)
        self.assertEqual(database_fingerprint(), before)

        authenticated = Client()
        authenticated.force_login(self.reader)
        issued_session = authenticated.cookies["sessionid"].value
        measured_before = database_fingerprint()
        authenticated_entry = authenticated.get(reverse("production_studio:entry"))
        authenticated_shell = authenticated.get(
            reverse("production_studio:definition", args=(definition.pk,))
        )
        self.assertEqual(authenticated_entry.status_code, 200)
        self.assertEqual(authenticated_shell.status_code, 200)
        self.assertEqual(authenticated.cookies["sessionid"].value, issued_session)
        self.assertFalse(authenticated_entry.cookies)
        self.assertFalse(authenticated_shell.cookies)
        self.assertEqual(database_fingerprint(), measured_before)

    def test_foundation_object_scope_and_capability_semantics_are_preserved(self):
        definition = self.definitions[PublicationStatus.DRAFT]
        url = self._open_url(definition)

        anonymous = self.api.get(url)
        self.assertEqual(anonymous.status_code, 401)

        self.api.force_authenticate(self.in_scope_without_capability)
        denied = self.api.get(url)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["code"], "STUDIO_CAPABILITY_DENIED")

        self.api.force_authenticate(self.out_of_scope_reader)
        inaccessible = self.api.get(url)
        absent = self.api.get(f"/api/foundation/definitions/{uuid4()}/")
        self.assertEqual(inaccessible.status_code, 404)
        self.assertEqual(absent.status_code, 404)
        self.assertEqual(inaccessible.data, absent.data)

    def test_open_all_literal_lifecycle_states_has_exact_hash_etag_and_zero_writes(self):
        self.api.force_authenticate(self.reader)
        for status, definition in self.definitions.items():
            with self.subTest(status=status):
                before = database_fingerprint()
                response = self.api.get(self._open_url(definition))
                after = database_fingerprint()
                canonical = canonical_json(response.data["manifest"]).encode("utf-8")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["publication_status"], status)
                self.assertEqual(
                    hashlib.sha256(canonical).hexdigest(),
                    response.data["manifest_hash"],
                )
                self.assertEqual(response.data["manifest_hash"], self.manifest_hash)
                self.assertEqual(response["ETag"], f'"{self.manifest_hash}"')
                self.assertEqual(
                    set(response.data),
                    {
                        "id",
                        "project_id",
                        "code",
                        "version",
                        "publication_status",
                        "is_current",
                        "validation_result",
                        "validated_at",
                        "validated_by",
                        "published_at",
                        "published_by",
                        "manifest",
                        "manifest_hash",
                        "schema_version",
                        "semantic_version",
                        "construct_version",
                        "supersedes_id",
                    },
                )
                self.assertEqual(response.data["is_current"], definition.is_current)
                self.assertEqual(
                    response.data["validation_result"],
                    definition.validation_result,
                )
                self.assertEqual(
                    response.data["validated_at"],
                    (
                        definition.validated_at.isoformat().replace("+00:00", "Z")
                        if definition.validated_at is not None
                        else None
                    ),
                )
                self.assertEqual(response.data["validated_by"], definition.validated_by)
                self.assertEqual(
                    response.data["published_at"],
                    (
                        definition.published_at.isoformat().replace("+00:00", "Z")
                        if definition.published_at is not None
                        else None
                    ),
                )
                self.assertEqual(response.data["published_by"], definition.published_by)
                self.assertEqual(after, before)

    def test_help_is_one_exact_tuple_or_indistinguishable_unavailable(self):
        self.api.force_authenticate(self.reader)
        exact_url = (
            "/api/foundation/help/studio.welcome/"
            "?application=STUDIO&locale=ru&version=1.0.0"
        )
        before = database_fingerprint()
        exact = self.api.get(exact_url)
        missing = self.api.get(
            "/api/foundation/help/studio.welcome/"
            "?application=STUDIO&locale=ru&version=9.9.9"
        )
        malformed = self.api.get(
            "/api/foundation/help/studio.welcome/"
            "?application=STUDIO&locale=ru&version=1.0.0&fallback=1"
        )
        self.assertEqual(exact.status_code, 200, exact.data)
        self.assertEqual(
            exact.data,
            {
                "stable_key": "studio.welcome",
                "version": "1.0.0",
                "locale": "ru",
                "title": "Точная справка",
                "sanitized_html": self.help_html,
                "content_sha256": self.help_sha256,
            },
        )
        self.assertEqual(
            hashlib.sha256(exact.data["sanitized_html"].encode("utf-8")).hexdigest(),
            exact.data["content_sha256"],
        )
        for unavailable in (missing, malformed):
            self.assertEqual(unavailable.status_code, 404)
            self.assertIn(unavailable.data["code"], {"HELP_TOPIC_NOT_FOUND", "STUDIO_RESOURCE_NOT_FOUND"})
        self.assertEqual(database_fingerprint(), before)

    def test_export_retry_is_exact_bytes_filename_hash_newline_and_zero_writes(self):
        definition = self.definitions[PublicationStatus.DRAFT]
        self.api.force_authenticate(self.reader)
        package = export_project_definition_package_2_1(definition)
        expected = (canonical_json(package) + "\n").encode("utf-8")
        representation_sha256 = hashlib.sha256(expected).hexdigest()
        url = f"{self._open_url(definition)}package/2.1/"
        before = database_fingerprint()
        first = self.api.get(url)
        second = self.api.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.content, expected)
        self.assertEqual(second.content, expected)
        self.assertTrue(first.content.endswith(b"\n"))
        self.assertFalse(first.content.endswith(b"\n\n"))
        self.assertEqual(first["ETag"], f'"{representation_sha256}"')
        self.assertEqual(second["ETag"], first["ETag"])
        self.assertEqual(
            first["Content-Disposition"],
            f'attachment; filename="foundation-definition-{definition.pk}-2.1.json"',
        )
        self.assertEqual(
            first["X-Foundation-Semantic-Payload-SHA256"],
            package["manifest"]["payload_sha256"],
        )
        self.assertEqual(database_fingerprint(), before)
