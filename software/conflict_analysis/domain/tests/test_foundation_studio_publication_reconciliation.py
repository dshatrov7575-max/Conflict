from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import threading
from unittest import skipUnless
from unittest.mock import patch
from uuid import UUID, uuid1, uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name
from domain.enums import PublicationStatus
from domain.models import (
    AuditEvent,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    ProjectWorkspace,
    UIHelpBinding,
)
from domain.policies import (
    StudioPrincipal,
    StudioRole,
    studio_principal_from_user,
    validate_project_definition,
)
from domain.services.project_definitions import (
    FoundationStudioApplicationConflict,
    clone_project_definition_draft,
    create_project_definition_draft,
    reconcile_publication_operation,
)
from domain.tests.test_foundation_studio_bootstrap import (
    FoundationStudioBootstrapMixin,
)


_REQUEST_CONTRACT = "FOUNDATION_PUBLICATION_OPERATION_REQUEST_V1"
_REQUEST_VERSION = "1.0.0"
_RESULT_CONTRACT = "FOUNDATION_PUBLICATION_OPERATION_RESULT_V1"
_RESULT_VERSION = "1.0.0"
_PUBLICATION_CONFLICT_MESSAGE = (
    "The requested Foundation publication operation conflicts with persisted state."
)
_PUBLICATION_ADMISSION_MESSAGES = {
    "PUBLICATION_OPERATION_KEY_REQUIRED": "Idempotency-Key is required.",
    "PUBLICATION_OPERATION_KEY_INVALID": (
        "Idempotency-Key must be one canonical lowercase RFC 4122 UUIDv4."
    ),
    "PUBLICATION_IF_MATCH_REQUIRED": "If-Match is required.",
    "PUBLICATION_IF_MATCH_INVALID": (
        "If-Match must be one strong quoted lowercase SHA-256."
    ),
    "PUBLICATION_ENVELOPE_INVALID": (
        "The request must match the exact publication envelope."
    ),
}
_CAPABILITY_DENIAL = {
    "code": "STUDIO_CAPABILITY_DENIED",
    "errors": [
        "The authenticated principal lacks the required Studio capability."
    ],
}
_NOT_FOUND = {
    "code": "STUDIO_RESOURCE_NOT_FOUND",
    "errors": ["Resource not found."],
}
_INITIAL_FAILURE_STAGES = (
    "after_bootstrap_lock",
    "after_canonical_validation",
    "after_validation_transition",
    "after_validation_audit",
    "after_publication_transition",
    "after_initial_workspace",
    "after_workspace_help_bindings",
    "after_project_publication",
    "after_definition_publish_audit",
    "after_workspace_bootstrap_audit",
)
_SUCCESSOR_FAILURE_STAGES = (
    "after_publication_transition",
    "after_project_publication",
    "after_definition_publish_audit",
)


def _canonical_json_bytes(value: object, *, terminal_lf: bool = False) -> bytes:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return encoded + (b"\n" if terminal_lf else b"")


def _semantic_request_sha256(
    *,
    operation_kind: str,
    project_id: UUID,
    definition_id: UUID,
    expected_manifest_hash: str,
    actor_identifier: str,
    locale: str,
    initial_workspace: dict | None,
) -> str:
    semantic_request = {
        "contract": _REQUEST_CONTRACT,
        "version": _REQUEST_VERSION,
        "operation_kind": operation_kind,
        "project_id": str(project_id),
        "definition_id": str(definition_id),
        "expected_manifest_hash": expected_manifest_hash,
        "actor_identifier": actor_identifier,
        "locale": locale,
        "initial_workspace": copy.deepcopy(initial_workspace),
    }
    return hashlib.sha256(_canonical_json_bytes(semantic_request)).hexdigest()


def _database_fingerprint() -> str:
    snapshot: dict[str, object] = {}
    with connection.cursor() as cursor:
        for table in sorted(connection.introspection.table_names(cursor)):
            cursor.execute(f"SELECT * FROM {connection.ops.quote_name(table)}")
            columns = [item[0] for item in cursor.description or ()]
            rows = sorted(repr(tuple(row)) for row in cursor.fetchall())
            snapshot[table] = {"columns": columns, "rows": rows}
    return hashlib.sha256(_canonical_json_bytes(snapshot)).hexdigest()


class FoundationStudioPublicationReconciliationTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()
        self.permissions = {
            codename: Permission.objects.get(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
                codename=codename,
            )
            for codename in (
                "studio_read_definition",
                "studio_validate_definition",
                "studio_publish_definition",
            )
        }
        self.user = self._make_user(
            username=f"fd06-publisher-{uuid4()}",
            capabilities=tuple(self.permissions),
            projects=(self.project,),
        )
        self.client = APIClient()
        self._authenticate(self.user)

    def _make_user(
        self,
        *,
        username: str,
        capabilities: tuple[str, ...] = (),
        projects: tuple[Project, ...] = (),
        password: str = "test-password",
    ):
        user = get_user_model().objects.create_user(
            username=username,
            password=password,
        )
        user.user_permissions.add(
            *(self.permissions[codename] for codename in capabilities)
        )
        for project in projects:
            self._scope_group(project).user_set.add(user)
        return get_user_model().objects.get(pk=user.pk)

    @staticmethod
    def _scope_group(project: Project) -> Group:
        group, _ = Group.objects.get_or_create(
            name=project_access_group_name(project.pk)
        )
        return group

    def _authenticate(self, user) -> object:
        current = get_user_model().objects.get(pk=user.pk)
        self.user = current if user.pk == self.user.pk else self.user
        self.client.force_authenticate(current)
        return current

    @staticmethod
    def _actor(user) -> str:
        current = get_user_model().objects.get(pk=user.pk)
        return studio_principal_from_user(current).actor_identifier

    @staticmethod
    def _basic_authorization(
        username: str,
        password: str = "test-password",
    ) -> str:
        encoded = base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {encoded}"

    @staticmethod
    def _headers(definition, operation_id=None) -> tuple[UUID, dict[str, str]]:
        operation_id = operation_id or uuid4()
        return operation_id, {
            "HTTP_IDEMPOTENCY_KEY": str(operation_id),
            "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
        }

    @staticmethod
    def _recovery_url(project_id: UUID, operation_id: UUID) -> str:
        return (
            f"/api/foundation/projects/{project_id}/"
            f"publication-operations/{operation_id}/"
        )

    @staticmethod
    def _publication_result_url(publication: ProjectPublication) -> str:
        return (
            f"/api/foundation/projects/{publication.project_id}/"
            f"publication-results/{publication.pk}/"
        )

    @staticmethod
    def _assert_no_response_cookie_mutation(response) -> None:
        if response.cookies:
            raise AssertionError(response.cookies.output())
        if "Set-Cookie" in response.headers:
            raise AssertionError(response.headers["Set-Cookie"])
        if response.wsgi_request.META.get("CSRF_COOKIE_NEEDS_UPDATE", False):
            raise AssertionError("The response attempted to update the CSRF cookie.")

    def _assert_fixed_error(self, response, *, status: int, code: str) -> None:
        if code in _PUBLICATION_ADMISSION_MESSAGES:
            payload = {
                "code": code,
                "errors": [_PUBLICATION_ADMISSION_MESSAGES[code]],
            }
        elif code == "STUDIO_CAPABILITY_DENIED":
            payload = _CAPABILITY_DENIAL
        elif code == "STUDIO_RESOURCE_NOT_FOUND":
            payload = _NOT_FOUND
        else:
            payload = {
                "code": code,
                "errors": [_PUBLICATION_CONFLICT_MESSAGE],
            }
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json(), payload)
        self.assertEqual(
            response.content,
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )
        self.assertNotIn("detail_sha256", response.json())

    def _assert_cache_barrier(self, response) -> None:
        self.assertEqual(response["Cache-Control"], "no-store")
        vary = {item.strip() for item in response.get("Vary", "").split(",")}
        self.assertIn("Cookie", vary)
        self.assertIn("Authorization", vary)

    def _workspace(self, *, unique: bool = False, suffix: str = "") -> dict:
        workspace = copy.deepcopy(self.workspace_spec())
        if unique:
            workspace["id"] = str(uuid4())
            workspace["code"] = f"FD06-WORKSPACE-{suffix or uuid4().hex[:8]}"
        return workspace

    def _draft_version(
        self,
        *,
        code: str,
        version: str,
    ) -> ProjectDefinitionVersion:
        return create_project_definition_draft(
            project=self.project,
            code=code,
            version=version,
            manifest=copy.deepcopy(self.manifest),
            principal=self.editor(actor="fd06-editor"),
        )

    def _initial(
        self,
        *,
        definition: ProjectDefinitionVersion | None = None,
        operation_id: UUID | None = None,
        workspace: dict | None = None,
        locale: str = "ru",
        client: APIClient | None = None,
    ):
        definition = definition or self.draft(
            code=f"FD06-I-{uuid4().hex[:12]}"
        )
        operation_id, headers = self._headers(definition, operation_id)
        workspace = copy.deepcopy(
            self.workspace_spec() if workspace is None else workspace
        )
        selected_client = self.client if client is None else client
        response = selected_client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            {"locale": locale, "workspace": workspace},
            format="json",
            **headers,
        )
        return definition, operation_id, headers, workspace, response

    def _validated_successor(
        self,
        predecessor: ProjectDefinitionVersion,
        *,
        code: str | None = None,
        version: str = "2.0.0",
        actor: str | None = None,
    ) -> ProjectDefinitionVersion:
        draft = clone_project_definition_draft(
            predecessor,
            code=code or f"FD06-S-{uuid4().hex[:12]}",
            version=version,
            principal=self.editor(actor="fd06-editor"),
        )
        return validate_project_definition(
            draft,
            actor_identifier=actor or self._actor(self.user),
            principal=self.publisher(actor=actor or self._actor(self.user)),
        )

    def _successor(
        self,
        *,
        predecessor: ProjectDefinitionVersion | None = None,
        operation_id: UUID | None = None,
        client: APIClient | None = None,
    ):
        if predecessor is None:
            initial = self._initial()
            self.assertEqual(initial[-1].status_code, 201, initial[-1].content)
            predecessor = initial[0]
            predecessor.refresh_from_db()
        successor = self._validated_successor(predecessor)
        operation_id, headers = self._headers(successor, operation_id)
        selected_client = self.client if client is None else client
        response = selected_client.post(
            f"/api/foundation/definitions/{successor.pk}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **headers,
        )
        return predecessor, successor, operation_id, headers, response

    def _expected_receipt(
        self,
        publication: ProjectPublication,
        *,
        operation_id: UUID,
        request_sha256: str,
        operation_kind: str,
    ) -> dict:
        publication.refresh_from_db()
        definition = ProjectDefinitionVersion.objects.get(
            pk=publication.definition_version_id
        )
        workspace = (
            ProjectWorkspace.objects.get(pk=publication.initial_workspace_id)
            if publication.initial_workspace_id
            else None
        )
        core = {
            "contract": _RESULT_CONTRACT,
            "contract_version": _RESULT_VERSION,
            "operation_id": str(operation_id),
            "operation_request_sha256": request_sha256,
            "operation_kind": operation_kind,
            "publication_id": str(publication.pk),
            "project_id": str(publication.project_id),
            "definition": {
                "id": str(definition.pk),
                "project_id": str(definition.project_id),
                "code": definition.code,
                "version": definition.version,
                "publication_status": PublicationStatus.PUBLISHED,
                "manifest": definition.manifest,
                "manifest_hash": definition.manifest_hash,
                "schema_version": definition.schema_version,
                "semantic_version": definition.semantic_version,
                "construct_version": definition.construct_version,
                "supersedes_id": (
                    str(definition.supersedes_id)
                    if definition.supersedes_id
                    else None
                ),
            },
            "initial_workspace_id": str(workspace.pk) if workspace else None,
            "initial_workspace_definition_id": (
                str(workspace.definition_version_id) if workspace else None
            ),
            "initial_workspace_definition_manifest_hash": (
                workspace.definition_manifest_hash if workspace else None
            ),
            "help_binding_ids": (
                [str(item["id"]) for item in definition.manifest["help_bindings"]]
                if workspace
                else []
            ),
            "locale": publication.locale,
            "actor_identifier": publication.actor_identifier,
            "validation_result": publication.validation_result,
            "published_at": publication.published_at.isoformat().replace(
                "+00:00", "Z"
            ),
        }
        return {
            **core,
            "result_sha256": hashlib.sha256(
                _canonical_json_bytes(core)
            ).hexdigest(),
        }

    def _assert_receipt(
        self,
        response,
        publication: ProjectPublication,
        *,
        operation_id: UUID,
        request_sha256: str,
        operation_kind: str,
        status: int,
        replayed: bool,
    ) -> dict:
        expected = self._expected_receipt(
            publication,
            operation_id=operation_id,
            request_sha256=request_sha256,
            operation_kind=operation_kind,
        )
        expected_bytes = _canonical_json_bytes(expected, terminal_lf=True)
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.content, expected_bytes)
        self.assertEqual(response.json(), expected)
        self.assertEqual(
            response["ETag"],
            f'"{hashlib.sha256(expected_bytes).hexdigest()}"',
        )
        self.assertEqual(
            response["Location"],
            self._publication_result_url(publication),
        )
        self.assertEqual(
            response["Idempotency-Replayed"],
            "true" if replayed else "false",
        )
        return expected

    @staticmethod
    def _raw_set_publication_code(
        publication: ProjectPublication,
        code: str,
    ) -> None:
        table = connection.ops.quote_name(ProjectPublication._meta.db_table)
        pk_column = connection.ops.quote_name(
            ProjectPublication._meta.pk.column
        )
        code_column = connection.ops.quote_name(
            ProjectPublication._meta.get_field("code").column
        )
        prepared_pk = ProjectPublication._meta.pk.get_db_prep_value(
            publication.pk,
            connection,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET {code_column} = %s WHERE {pk_column} = %s",
                [code, prepared_pk],
            )

    def _other_project_definition(self) -> tuple[Project, ProjectDefinitionVersion]:
        project_id = uuid4()
        project_code = f"FD06-PROJECT-{uuid4().hex[:10]}"
        project = Project.objects.create(
            id=project_id,
            code=project_code,
            version="1.0.0",
            name="FD06 independent project",
            description="Project-scoped operation identity oracle.",
            metadata={"oracle": "FD06"},
        )
        manifest = copy.deepcopy(self.manifest)
        manifest["project"].update(
            {
                "id": str(project.pk),
                "code": project.code,
                "version": project.version,
                "name": project.name,
                "description": project.description,
                "metadata": project.metadata,
            }
        )
        # Binding UUIDs are immutable global row identities even though the
        # operation key is deliberately project-scoped.
        manifest["help_bindings"][0]["id"] = str(uuid4())
        definition = create_project_definition_draft(
            project=project,
            code=f"FD06-OTHER-{uuid4().hex[:10]}",
            version="1.0.0",
            manifest=manifest,
            principal=self.editor(actor="fd06-cross-project-editor"),
        )
        return project, definition

    def _set_capability(self, user, codename: str, *, enabled: bool) -> object:
        current = get_user_model().objects.get(pk=user.pk)
        if enabled:
            current.user_permissions.add(self.permissions[codename])
        else:
            current.user_permissions.remove(self.permissions[codename])
        return get_user_model().objects.get(pk=user.pk)

    def test_initial_and_successor_require_exact_key_if_match_envelope_and_prebody_method_gate(self):
        definition = self.draft(code="FD06-ADMISSION")
        initial_url = (
            f"/api/foundation/definitions/{definition.pk}/publish-initial/"
        )
        baseline = _database_fingerprint()

        with patch(
            "domain.api.studio_definitions.capture_http_json",
            side_effect=AssertionError("non-POST must not capture a body"),
        ) as capture:
            for method in ("GET", "PUT", "PATCH", "DELETE"):
                with self.subTest(method=method):
                    response = self.client.generic(
                        method,
                        initial_url,
                        b"{not-json",
                        content_type="application/json",
                    )
                    self.assertEqual(response.status_code, 405)
                    self.assertEqual(response.content, b"")
                    self.assertEqual(response["Allow"], "POST")
            capture.assert_not_called()

        body = {"locale": "ru", "workspace": self.workspace_spec()}
        missing_key = self.client.post(initial_url, body, format="json")
        self._assert_fixed_error(
            missing_key,
            status=400,
            code="PUBLICATION_OPERATION_KEY_REQUIRED",
        )

        for invalid_key in (
            "",
            str(uuid4()).upper(),
            "{" + str(uuid4()) + "}",
            str(uuid1()),
            "not-a-uuid",
        ):
            with self.subTest(invalid_key=invalid_key):
                response = self.client.post(
                    initial_url,
                    body,
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=invalid_key,
                )
                self._assert_fixed_error(
                    response,
                    status=400,
                    code=(
                        "PUBLICATION_OPERATION_KEY_REQUIRED"
                        if invalid_key == ""
                        else "PUBLICATION_OPERATION_KEY_INVALID"
                    ),
                )

        non_v4_recovery = self.client.get(
            f"/api/foundation/projects/{definition.project_id}/"
            f"publication-operations/{uuid1()}/"
        )
        self._assert_fixed_error(
            non_v4_recovery,
            status=404,
            code="STUDIO_RESOURCE_NOT_FOUND",
        )

        operation_id = uuid4()
        missing_match = self.client.post(
            initial_url,
            body,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
        )
        self._assert_fixed_error(
            missing_match,
            status=400,
            code="PUBLICATION_IF_MATCH_REQUIRED",
        )
        for invalid_match in (
            definition.manifest_hash,
            f'W/"{definition.manifest_hash}"',
            f'"{definition.manifest_hash.upper()}"',
            f'"{definition.manifest_hash}", "{definition.manifest_hash}"',
        ):
            with self.subTest(invalid_match=invalid_match):
                response = self.client.post(
                    initial_url,
                    body,
                    format="json",
                    HTTP_IDEMPOTENCY_KEY=str(operation_id),
                    HTTP_IF_MATCH=invalid_match,
                )
                self._assert_fixed_error(
                    response,
                    status=400,
                    code="PUBLICATION_IF_MATCH_INVALID",
                )

        admitted_headers = {
            "HTTP_IDEMPOTENCY_KEY": str(operation_id),
            "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
        }
        envelope_cases = (
            (
                initial_url + "?unexpected=1",
                body,
                "application/json",
            ),
            (
                initial_url,
                {**body, "actor_identifier": "spoofed"},
                "application/json",
            ),
            (
                initial_url,
                {"locale": "ru"},
                "application/json",
            ),
        )
        for url, payload, content_type in envelope_cases:
            with self.subTest(url=url, payload=payload):
                response = self.client.post(
                    url,
                    payload,
                    format="json",
                    **admitted_headers,
                )
                self._assert_fixed_error(
                    response,
                    status=400,
                    code="PUBLICATION_ENVELOPE_INVALID",
                )

        # The exact successor envelope is admitted before lifecycle evaluation,
        # so the same untouched DRAFT can prove that an extra workspace member
        # is rejected without creating a second project/version fixture.
        successor = definition
        successor_url = (
            f"/api/foundation/definitions/{successor.pk}/publish-successor/"
        )
        successor_operation, successor_headers = self._headers(successor)
        self.assertIsInstance(successor_operation, UUID)
        extra = self.client.post(
            successor_url,
            {"locale": "ru", "workspace": self.workspace_spec()},
            format="json",
            **successor_headers,
        )
        self._assert_fixed_error(
            extra,
            status=400,
            code="PUBLICATION_ENVELOPE_INVALID",
        )
        self.assertEqual(_database_fingerprint(), baseline)

    def test_initial_fresh_result_persists_hash_bound_project_operation_and_exact_receipt(self):
        definition, operation_id, _, workspace, response = self._initial()
        self.assertEqual(response.status_code, 201, response.content)
        publication = ProjectPublication.objects.get(
            pk=response.json()["publication_id"]
        )
        actor = self._actor(self.user)
        request_hash = _semantic_request_sha256(
            operation_kind="INITIAL",
            project_id=definition.project_id,
            definition_id=definition.pk,
            expected_manifest_hash=definition.manifest_hash,
            actor_identifier=actor,
            locale="ru",
            initial_workspace=workspace,
        )
        self.assertEqual(
            publication.code,
            f"PUBOP-{operation_id}-{request_hash}",
        )
        self.assertRegex(
            publication.code,
            re.compile(
                r"^PUBOP-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
                r"[89ab][0-9a-f]{3}-[0-9a-f]{12}-[0-9a-f]{64}$"
            ),
        )
        expected = self._assert_receipt(
            response,
            publication,
            operation_id=operation_id,
            request_sha256=request_hash,
            operation_kind="INITIAL",
            status=201,
            replayed=False,
        )
        self.assertEqual(
            expected["help_binding_ids"],
            [str(item["id"]) for item in definition.manifest["help_bindings"]],
        )
        self.assertEqual(
            list(
                UIHelpBinding.objects.filter(
                    workspace_id=publication.initial_workspace_id
                ).values_list("id", flat=True)
            ),
            [UUID(item) for item in expected["help_binding_ids"]],
        )
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)

    def test_successor_fresh_result_preserves_predecessor_and_exact_receipt(self):
        predecessor, successor, operation_id, headers, response = self._successor()
        self.assertEqual(response.status_code, 201, response.content)
        initial_publication = ProjectPublication.objects.get(
            initial_workspace__isnull=False
        )
        workspace = initial_publication.initial_workspace
        assert workspace is not None
        old_pin = (
            workspace.pk,
            workspace.definition_version_id,
            workspace.definition_manifest_hash,
        )
        publication = ProjectPublication.objects.get(
            pk=response.json()["publication_id"]
        )
        request_hash = _semantic_request_sha256(
            operation_kind="SUCCESSOR",
            project_id=successor.project_id,
            definition_id=successor.pk,
            expected_manifest_hash=successor.manifest_hash,
            actor_identifier=self._actor(self.user),
            locale="ru",
            initial_workspace=None,
        )
        expected = self._assert_receipt(
            response,
            publication,
            operation_id=operation_id,
            request_sha256=request_hash,
            operation_kind="SUCCESSOR",
            status=201,
            replayed=False,
        )
        self.assertIsNone(expected["initial_workspace_id"])
        self.assertIsNone(expected["initial_workspace_definition_id"])
        self.assertIsNone(
            expected["initial_workspace_definition_manifest_hash"]
        )
        self.assertEqual(expected["help_binding_ids"], [])
        predecessor.refresh_from_db()
        successor.refresh_from_db()
        workspace.refresh_from_db()
        self.assertEqual(predecessor.publication_status, PublicationStatus.PUBLISHED)
        self.assertFalse(predecessor.is_current)
        self.assertEqual(successor.publication_status, PublicationStatus.PUBLISHED)
        self.assertTrue(successor.is_current)
        self.assertEqual(
            (
                workspace.pk,
                workspace.definition_version_id,
                workspace.definition_manifest_hash,
            ),
            old_pin,
        )

        self.user = self._set_capability(
            self.user,
            "studio_publish_definition",
            enabled=False,
        )
        self._authenticate(self.user)
        denied_baseline = _database_fingerprint()
        denied = self.client.post(
            f"/api/foundation/definitions/{successor.pk}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **headers,
        )
        self._assert_fixed_error(
            denied,
            status=403,
            code="STUDIO_CAPABILITY_DENIED",
        )
        self.assertNotIn(str(operation_id).encode(), denied.content)
        self.assertEqual(_database_fingerprint(), denied_baseline)

        self.user = self._set_capability(
            self.user,
            "studio_publish_definition",
            enabled=True,
        )
        self._authenticate(self.user)
        restored_baseline = _database_fingerprint()
        replay = self.client.post(
            f"/api/foundation/definitions/{successor.pk}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **headers,
        )
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.content, response.content)
        self.assertEqual(replay["ETag"], response["ETag"])
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(_database_fingerprint(), restored_baseline)

    def test_same_key_same_request_replays_before_lifecycle_rejection_and_after_workspace_or_lifecycle_change(self):
        definition, _, headers, workspace_spec, fresh = self._initial()
        self.assertEqual(fresh.status_code, 201, fresh.content)

        for codename in (
            "studio_validate_definition",
            "studio_publish_definition",
        ):
            with self.subTest(revoked=codename):
                self.user = self._set_capability(
                    self.user,
                    codename,
                    enabled=False,
                )
                self._authenticate(self.user)
                baseline = _database_fingerprint()
                denied = self.client.post(
                    f"/api/foundation/definitions/{definition.pk}/publish-initial/",
                    {"locale": "ru", "workspace": workspace_spec},
                    format="json",
                    **headers,
                )
                self._assert_fixed_error(
                    denied,
                    status=403,
                    code="STUDIO_CAPABILITY_DENIED",
                )
                self.assertEqual(_database_fingerprint(), baseline)
                self.user = self._set_capability(
                    self.user,
                    codename,
                    enabled=True,
                )
                self._authenticate(self.user)

        successor = self._validated_successor(definition)
        successor_operation, successor_headers = self._headers(successor)
        successor_response = self.client.post(
            f"/api/foundation/definitions/{successor.pk}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **successor_headers,
        )
        self.assertEqual(
            successor_response.status_code,
            201,
            successor_response.content,
        )
        self.assertIsInstance(successor_operation, UUID)
        persisted_workspace = ProjectWorkspace.objects.get(pk=workspace_spec["id"])
        persisted_workspace.name = "Mutable after publication"
        persisted_workspace.metadata = {"changed": True}
        persisted_workspace.save()
        definition.refresh_from_db()
        self.assertFalse(definition.is_current)
        self.assertEqual(definition.publication_status, PublicationStatus.PUBLISHED)

        baseline = _database_fingerprint()
        replay = self.client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            {"locale": "ru", "workspace": workspace_spec},
            format="json",
            **headers,
        )
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.content, fresh.content)
        self.assertEqual(replay["ETag"], fresh["ETag"])
        self.assertEqual(replay["Location"], fresh["Location"])
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(_database_fingerprint(), baseline)
        self.assertEqual(ProjectPublication.objects.count(), 2)

    def test_same_uuid_key_is_independent_across_projects_and_foreign_operation_is_hidden(self):
        operation_id = uuid4()
        first = self._initial(operation_id=operation_id)
        self.assertEqual(first[-1].status_code, 201, first[-1].content)
        first_publication = ProjectPublication.objects.get(
            pk=first[-1].json()["publication_id"]
        )

        other_project, other_definition = self._other_project_definition()
        self._scope_group(other_project).user_set.add(self.user)
        self._authenticate(self.user)
        other_workspace = self._workspace(unique=True, suffix="OTHER")
        second = self._initial(
            definition=other_definition,
            operation_id=operation_id,
            workspace=other_workspace,
        )
        self.assertEqual(second[-1].status_code, 201, second[-1].content)
        second_publication = ProjectPublication.objects.get(
            pk=second[-1].json()["publication_id"]
        )
        self.assertNotEqual(first_publication.pk, second_publication.pk)
        self.assertNotEqual(first_publication.code, second_publication.code)
        self.assertTrue(first_publication.code.startswith(f"PUBOP-{operation_id}-"))
        self.assertTrue(second_publication.code.startswith(f"PUBOP-{operation_id}-"))

        scoped_reader = self._make_user(
            username=f"fd06-first-only-{uuid4()}",
            capabilities=("studio_read_definition",),
            projects=(self.project,),
        )
        reader_client = APIClient()
        reader_client.force_authenticate(scoped_reader)
        foreign = reader_client.get(
            self._recovery_url(other_project.pk, operation_id)
        )
        absent = reader_client.get(
            self._recovery_url(uuid4(), operation_id)
        )
        self._assert_fixed_error(
            foreign,
            status=404,
            code="STUDIO_RESOURCE_NOT_FOUND",
        )
        self.assertEqual(foreign.content, absent.content)

        self._scope_group(self.project).user_set.remove(self.user)
        self._authenticate(self.user)
        hidden_baseline = _database_fingerprint()
        hidden_replay = self.client.post(
            f"/api/foundation/definitions/{first[0].pk}/publish-initial/",
            {"locale": "ru", "workspace": first[3]},
            format="json",
            **first[2],
        )
        hidden_recovery = self.client.get(
            self._recovery_url(self.project.pk, operation_id)
        )
        self._assert_fixed_error(
            hidden_replay,
            status=404,
            code="STUDIO_RESOURCE_NOT_FOUND",
        )
        self._assert_fixed_error(
            hidden_recovery,
            status=404,
            code="STUDIO_RESOURCE_NOT_FOUND",
        )
        self.assertEqual(_database_fingerprint(), hidden_baseline)

        self._scope_group(self.project).user_set.add(self.user)
        self._authenticate(self.user)
        restored_baseline = _database_fingerprint()
        restored = self.client.get(
            self._recovery_url(self.project.pk, operation_id)
        )
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual(restored.content, first[-1].content)
        self.assertEqual(_database_fingerprint(), restored_baseline)

    def test_same_key_different_request_actor_or_target_is_typed_conflict(self):
        definition, operation_id, headers, workspace, fresh = self._initial()
        self.assertEqual(fresh.status_code, 201, fresh.content)
        changed_workspace = copy.deepcopy(workspace)
        changed_workspace["name"] = "Changed semantic request"
        target = self._draft_version(
            code=f"FD06-REUSED-TARGET-{uuid4().hex[:8]}",
            version="2.0.0",
        )
        target_headers = {
            "HTTP_IDEMPOTENCY_KEY": str(operation_id),
            "HTTP_IF_MATCH": f'"{target.manifest_hash}"',
        }
        other_actor = self._make_user(
            username=f"fd06-other-actor-{uuid4()}",
            capabilities=tuple(self.permissions),
            projects=(self.project,),
        )
        other_client = APIClient()
        other_client.force_authenticate(other_actor)
        wrong_precondition = {
            "HTTP_IDEMPOTENCY_KEY": str(operation_id),
            "HTTP_IF_MATCH": f'"{"0" * 64}"',
        }
        cases = (
            (
                self.client,
                f"/api/foundation/definitions/{definition.pk}/publish-initial/",
                {"locale": "ru", "workspace": changed_workspace},
                headers,
            ),
            (
                self.client,
                f"/api/foundation/definitions/{definition.pk}/publish-initial/",
                {"locale": "en", "workspace": workspace},
                headers,
            ),
            (
                other_client,
                f"/api/foundation/definitions/{definition.pk}/publish-initial/",
                {"locale": "ru", "workspace": workspace},
                headers,
            ),
            (
                self.client,
                f"/api/foundation/definitions/{target.pk}/publish-initial/",
                {"locale": "ru", "workspace": workspace},
                target_headers,
            ),
            (
                self.client,
                f"/api/foundation/definitions/{definition.pk}/publish-initial/",
                {"locale": "ru", "workspace": workspace},
                wrong_precondition,
            ),
        )
        baseline = _database_fingerprint()
        for selected_client, url, body, selected_headers in cases:
            with self.subTest(url=url, actor=getattr(selected_client, "handler", None)):
                response = selected_client.post(
                    url,
                    body,
                    format="json",
                    **selected_headers,
                )
                self._assert_fixed_error(
                    response,
                    status=409,
                    code="PUBLICATION_OPERATION_KEY_REUSE",
                )
                self.assertNotIn(str(operation_id).encode(), response.content)
                self.assertNotIn(
                    fresh.json()["operation_request_sha256"].encode(),
                    response.content,
                )
                self.assertEqual(_database_fingerprint(), baseline)

    def test_response_loss_recovers_immutable_receipt_and_fd03_current_state_remains_separate(self):
        definition, operation_id, headers, workspace, fresh = self._initial()
        self.assertEqual(fresh.status_code, 201, fresh.content)
        publication = ProjectPublication.objects.get(
            pk=fresh.json()["publication_id"]
        )
        request_hash = _semantic_request_sha256(
            operation_kind="INITIAL",
            project_id=definition.project_id,
            definition_id=definition.pk,
            expected_manifest_hash=definition.manifest_hash,
            actor_identifier=self._actor(self.user),
            locale="ru",
            initial_workspace=workspace,
        )
        recovery_url = self._recovery_url(self.project.pk, operation_id)

        admission_baseline = _database_fingerprint()
        for url, request_headers in (
            (recovery_url + "?unexpected=1", {}),
            (recovery_url, {"HTTP_IDEMPOTENCY_KEY": str(uuid4())}),
            (
                recovery_url,
                {"HTTP_IF_MATCH": f'"{definition.manifest_hash}"'},
            ),
            (recovery_url, {"HTTP_X_STUDIO_ROLE": "STUDIO_PUBLISHER"}),
        ):
            with self.subTest(url=url, request_headers=request_headers):
                response = self.client.get(url, **request_headers)
                self._assert_fixed_error(
                    response,
                    status=400,
                    code="PUBLICATION_ENVELOPE_INVALID",
                )
                self.assertEqual(_database_fingerprint(), admission_baseline)

        session = APIClient(enforce_csrf_checks=True)
        self.assertTrue(
            session.login(
                username=self.user.username,
                password="test-password",
            )
        )
        session_baseline = _database_fingerprint()
        session_recovery = session.get(recovery_url)
        self._assert_receipt(
            session_recovery,
            publication,
            operation_id=operation_id,
            request_sha256=request_hash,
            operation_kind="INITIAL",
            status=200,
            replayed=True,
        )
        self.assertEqual(session_recovery.content, fresh.content)
        self._assert_cache_barrier(session_recovery)
        self._assert_no_response_cookie_mutation(session_recovery)
        self.assertEqual(_database_fingerprint(), session_baseline)

        no_capability = self._make_user(
            username=f"fd06-no-read-{uuid4()}",
            projects=(self.project,),
        )
        no_capability_client = APIClient()
        no_capability_client.force_authenticate(no_capability)
        no_capability_baseline = _database_fingerprint()
        denied = no_capability_client.get(recovery_url)
        self._assert_fixed_error(
            denied,
            status=403,
            code="STUDIO_CAPABILITY_DENIED",
        )
        self.assertNotIn(str(operation_id).encode(), denied.content)
        self.assertEqual(_database_fingerprint(), no_capability_baseline)

        self.user = self._set_capability(
            self.user,
            "studio_read_definition",
            enabled=False,
        )
        revoked_baseline = _database_fingerprint()
        revoked = session.get(recovery_url)
        self._assert_fixed_error(
            revoked,
            status=403,
            code="STUDIO_CAPABILITY_DENIED",
        )
        self.assertNotIn(fresh.content, revoked.content)
        self.assertEqual(_database_fingerprint(), revoked_baseline)

        self.user = self._set_capability(
            self.user,
            "studio_read_definition",
            enabled=True,
        )
        restored_baseline = _database_fingerprint()
        restored = session.get(recovery_url)
        self.assertEqual(restored.status_code, 200, restored.content)
        self.assertEqual(restored.content, fresh.content)
        self.assertEqual(restored["ETag"], fresh["ETag"])
        self._assert_cache_barrier(restored)
        self.assertEqual(_database_fingerprint(), restored_baseline)

        self._scope_group(self.project).user_set.remove(self.user)
        self._authenticate(self.user)
        scope_baseline = _database_fingerprint()
        hidden_get = self.client.get(recovery_url)
        hidden_post = self.client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            {"locale": "ru", "workspace": workspace},
            format="json",
            **headers,
        )
        self._assert_fixed_error(
            hidden_get,
            status=404,
            code="STUDIO_RESOURCE_NOT_FOUND",
        )
        self._assert_fixed_error(
            hidden_post,
            status=404,
            code="STUDIO_RESOURCE_NOT_FOUND",
        )
        self.assertEqual(_database_fingerprint(), scope_baseline)
        self._scope_group(self.project).user_set.add(self.user)
        self._authenticate(self.user)

        basic_reader = self._make_user(
            username=f"fd06-basic-reader-{uuid4()}",
            capabilities=("studio_read_definition",),
            projects=(self.project,),
        )
        password_hasher = PBKDF2PasswordHasher()
        upgrade_eligible = password_hasher.encode(
            "test-password",
            password_hasher.salt(),
            iterations=1,
        )
        self.assertTrue(password_hasher.must_update(upgrade_eligible))
        get_user_model().objects.filter(pk=basic_reader.pk).update(
            password=upgrade_eligible
        )
        basic_baseline = _database_fingerprint()
        basic = APIClient(enforce_csrf_checks=True)
        basic_recovery = basic.get(
            recovery_url,
            HTTP_AUTHORIZATION=self._basic_authorization(
                basic_reader.username
            ),
        )
        self.assertEqual(basic_recovery.status_code, 200, basic_recovery.content)
        self.assertEqual(basic_recovery.content, fresh.content)
        self.assertEqual(basic_recovery["ETag"], fresh["ETag"])
        self._assert_cache_barrier(basic_recovery)
        self._assert_no_response_cookie_mutation(basic_recovery)
        self.assertEqual(
            get_user_model().objects.values_list("password", flat=True).get(
                pk=basic_reader.pk
            ),
            upgrade_eligible,
        )
        self.assertEqual(_database_fingerprint(), basic_baseline)

        basic_reader = self._set_capability(
            basic_reader,
            "studio_read_definition",
            enabled=False,
        )
        second_principal_revoked_baseline = _database_fingerprint()
        second_principal_revoked = basic.get(
            recovery_url,
            HTTP_AUTHORIZATION=self._basic_authorization(
                basic_reader.username
            ),
        )
        self._assert_fixed_error(
            second_principal_revoked,
            status=403,
            code="STUDIO_CAPABILITY_DENIED",
        )
        self.assertEqual(
            _database_fingerprint(),
            second_principal_revoked_baseline,
        )

        self._authenticate(self.user)
        fd03_baseline = _database_fingerprint()
        current = self.client.get(self._publication_result_url(publication))
        self.assertEqual(current.status_code, 200, current.content)
        self.assertEqual(
            set(current.json()),
            {
                "publication_id",
                "project_id",
                "definition_id",
                "definition_manifest_hash",
                "definition_publication_status",
                "definition_is_current",
                "initial_workspace_id",
                "initial_workspace_definition_id",
                "initial_workspace_definition_manifest_hash",
                "locale",
                "actor_identifier",
                "validation_result",
                "published_at",
            },
        )
        self.assertNotIn("operation_id", current.json())
        self.assertNotIn("operation_request_sha256", current.json())
        self.assertNotIn("result_sha256", current.json())
        self.assertNotIn("contract", current.json())
        self.assertNotEqual(current.content, fresh.content)
        self.assertEqual(_database_fingerprint(), fd03_baseline)

    def test_already_published_stale_noncurrent_and_cross_scope_failures_are_typed(self):
        initial = self._initial()
        definition, operation_id, headers, workspace, fresh = initial
        self.assertEqual(fresh.status_code, 201, fresh.content)
        initial_publication = ProjectPublication.objects.get(
            pk=fresh.json()["publication_id"]
        )
        original_code = initial_publication.code

        _, different_headers = self._headers(definition)
        already = self.client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            {"locale": "ru", "workspace": workspace},
            format="json",
            **different_headers,
        )
        self._assert_fixed_error(
            already,
            status=409,
            code="PUBLICATION_ALREADY_COMMITTED",
        )

        stale_definition = self._draft_version(
            code=f"FD06-STALE-{uuid4().hex[:8]}",
            version="9.0.0",
        )
        stale_operation, _ = self._headers(stale_definition)
        stale = self.client.post(
            f"/api/foundation/definitions/{stale_definition.pk}/publish-initial/",
            {"locale": "ru", "workspace": self._workspace(unique=True)},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(stale_operation),
            HTTP_IF_MATCH=f'"{"0" * 64}"',
        )
        self._assert_fixed_error(
            stale,
            status=409,
            code="PUBLICATION_STALE",
        )

        winner = self._validated_successor(
            definition,
            code=f"FD06-WINNER-{uuid4().hex[:8]}",
            version="2.0.0",
        )
        loser = self._validated_successor(
            definition,
            code=f"FD06-LOSER-{uuid4().hex[:8]}",
            version="3.0.0",
        )
        winner_operation, winner_headers = self._headers(winner)
        winner_response = self.client.post(
            f"/api/foundation/definitions/{winner.pk}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **winner_headers,
        )
        self.assertEqual(
            winner_response.status_code,
            201,
            winner_response.content,
        )
        winner_publication = ProjectPublication.objects.get(
            pk=winner_response.json()["publication_id"]
        )
        loser_operation, loser_headers = self._headers(loser)
        noncurrent = self.client.post(
            f"/api/foundation/definitions/{loser.pk}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **loser_headers,
        )
        self._assert_fixed_error(
            noncurrent,
            status=409,
            code="PUBLICATION_TARGET_STATE_CONFLICT",
        )
        self.assertFalse(
            ProjectPublication.objects.filter(
                code__startswith=f"PUBOP-{loser_operation}-"
            ).exists()
        )

        outsider = self._make_user(
            username=f"fd06-out-of-scope-{uuid4()}",
            capabilities=tuple(self.permissions),
        )
        outsider_client = APIClient()
        outsider_client.force_authenticate(outsider)
        cross_scope_baseline = _database_fingerprint()
        cross_scope = outsider_client.post(
            f"/api/foundation/definitions/{loser.pk}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **loser_headers,
        )
        absent = outsider_client.post(
            f"/api/foundation/definitions/{uuid4()}/publish-successor/",
            {"locale": "ru"},
            format="json",
            **loser_headers,
        )
        self._assert_fixed_error(
            cross_scope,
            status=404,
            code="STUDIO_RESOURCE_NOT_FOUND",
        )
        self.assertEqual(cross_scope.content, absent.content)
        self.assertEqual(_database_fingerprint(), cross_scope_baseline)

        malformed_suffix = "not-a-lowercase-sha256"
        self._raw_set_publication_code(
            initial_publication,
            f"PUBOP-{operation_id}-{malformed_suffix}",
        )
        malformed_baseline = _database_fingerprint()
        malformed_post = self.client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            {"locale": "ru", "workspace": workspace},
            format="json",
            **headers,
        )
        malformed_get = self.client.get(
            self._recovery_url(self.project.pk, operation_id)
        )
        for response in (malformed_post, malformed_get):
            self._assert_fixed_error(
                response,
                status=409,
                code="PUBLICATION_OPERATION_IDENTITY_CORRUPT",
            )
            self.assertNotIn(malformed_suffix.encode(), response.content)
            self.assertNotIn(original_code.encode(), response.content)
        self.assertEqual(_database_fingerprint(), malformed_baseline)

        self._raw_set_publication_code(initial_publication, original_code)
        duplicate_hash = "0" * 64
        self._raw_set_publication_code(
            winner_publication,
            f"PUBOP-{operation_id}-{duplicate_hash}",
        )
        duplicate_baseline = _database_fingerprint()
        duplicate_post = self.client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            {"locale": "ru", "workspace": workspace},
            format="json",
            **headers,
        )
        duplicate_get = self.client.get(
            self._recovery_url(self.project.pk, operation_id)
        )
        for response in (duplicate_post, duplicate_get):
            self._assert_fixed_error(
                response,
                status=409,
                code="PUBLICATION_OPERATION_IDENTITY_CORRUPT",
            )
            self.assertNotIn(duplicate_hash.encode(), response.content)
        self.assertEqual(_database_fingerprint(), duplicate_baseline)
        self.assertIsInstance(winner_operation, UUID)

    def test_every_initial_failure_stage_rolls_back_definition_workspace_help_publication_and_audits(self):
        definition = self.draft(code="FD06-ROLLBACK-INITIAL")
        operation_id = uuid4()
        workspace = self.workspace_spec()
        actor = self._actor(self.user)
        request_hash = _semantic_request_sha256(
            operation_kind="INITIAL",
            project_id=definition.project_id,
            definition_id=definition.pk,
            expected_manifest_hash=definition.manifest_hash,
            actor_identifier=actor,
            locale="ru",
            initial_workspace=workspace,
        )
        principal = self.publisher(actor=actor)

        for stage in _INITIAL_FAILURE_STAGES:
            with self.subTest(stage=stage):
                baseline = _database_fingerprint()
                with self.assertRaisesRegex(RuntimeError, stage):
                    reconcile_publication_operation(
                        definition=definition,
                        operation_id=operation_id,
                        request_sha256=request_hash,
                        expected_manifest_hash=definition.manifest_hash,
                        operation_kind="INITIAL",
                        principal=principal,
                        locale="ru",
                        workspace_spec=workspace,
                        inject_failure_at=stage,
                    )
                self.assertEqual(_database_fingerprint(), baseline)
                definition.refresh_from_db()
                self.assertEqual(
                    definition.publication_status,
                    PublicationStatus.DRAFT,
                )
                self.assertFalse(definition.is_current)
                self.assertFalse(
                    ProjectPublication.objects.filter(
                        code__startswith=f"PUBOP-{operation_id}-"
                    ).exists()
                )
                self.assertFalse(ProjectWorkspace.objects.exists())
                self.assertEqual(
                    UIHelpBinding.objects.filter(workspace__isnull=False).count(),
                    0,
                )

    def test_every_successor_failure_stage_rolls_back_currentness_publication_and_audits(self):
        initial = self._initial()
        self.assertEqual(initial[-1].status_code, 201, initial[-1].content)
        predecessor = initial[0]
        predecessor.refresh_from_db()
        successor = self._validated_successor(predecessor)
        operation_id = uuid4()
        actor = self._actor(self.user)
        request_hash = _semantic_request_sha256(
            operation_kind="SUCCESSOR",
            project_id=successor.project_id,
            definition_id=successor.pk,
            expected_manifest_hash=successor.manifest_hash,
            actor_identifier=actor,
            locale="ru",
            initial_workspace=None,
        )
        principal = self.publisher(actor=actor)
        workspace = ProjectWorkspace.objects.get()
        pin = (
            workspace.pk,
            workspace.definition_version_id,
            workspace.definition_manifest_hash,
        )

        for stage in _SUCCESSOR_FAILURE_STAGES:
            with self.subTest(stage=stage):
                baseline = _database_fingerprint()
                with self.assertRaisesRegex(RuntimeError, stage):
                    reconcile_publication_operation(
                        definition=successor,
                        operation_id=operation_id,
                        request_sha256=request_hash,
                        expected_manifest_hash=successor.manifest_hash,
                        operation_kind="SUCCESSOR",
                        principal=principal,
                        locale="ru",
                        workspace_spec=None,
                        inject_failure_at=stage,
                    )
                self.assertEqual(_database_fingerprint(), baseline)
                predecessor.refresh_from_db()
                successor.refresh_from_db()
                workspace.refresh_from_db()
                self.assertTrue(predecessor.is_current)
                self.assertEqual(
                    predecessor.publication_status,
                    PublicationStatus.PUBLISHED,
                )
                self.assertFalse(successor.is_current)
                self.assertEqual(
                    successor.publication_status,
                    PublicationStatus.VALIDATED,
                )
                self.assertEqual(
                    (
                        workspace.pk,
                        workspace.definition_version_id,
                        workspace.definition_manifest_hash,
                    ),
                    pin,
                )
                self.assertEqual(ProjectPublication.objects.count(), 1)
                self.assertFalse(
                    ProjectPublication.objects.filter(
                        code__startswith=f"PUBOP-{operation_id}-"
                    ).exists()
                )

    def test_auth_csrf_basic_cookie_and_nonpost_paths_are_bounded_and_write_free_before_admission(self):
        definition = self.draft(code="FD06-AUTH-BASIC")
        operation_id, headers = self._headers(definition)
        workspace = self.workspace_spec()
        url = f"/api/foundation/definitions/{definition.pk}/publish-initial/"
        password_hasher = PBKDF2PasswordHasher()
        upgrade_eligible = password_hasher.encode(
            "test-password",
            password_hasher.salt(),
            iterations=1,
        )
        self.assertTrue(password_hasher.must_update(upgrade_eligible))
        get_user_model().objects.filter(pk=self.user.pk).update(
            password=upgrade_eligible
        )
        stored_password = get_user_model().objects.values_list(
            "password", flat=True
        ).get(pk=self.user.pk)
        before_counts = (
            ProjectPublication.objects.count(),
            ProjectWorkspace.objects.count(),
            UIHelpBinding.objects.filter(workspace__isnull=False).count(),
            AuditEvent.objects.count(),
        )

        basic = APIClient(enforce_csrf_checks=True)
        published = basic.post(
            url,
            {"locale": "ru", "workspace": workspace},
            format="json",
            HTTP_AUTHORIZATION=self._basic_authorization(self.user.username),
            **headers,
        )
        self.assertEqual(published.status_code, 201, published.content)
        self._assert_no_response_cookie_mutation(published)
        self.assertEqual(
            get_user_model().objects.values_list("password", flat=True).get(
                pk=self.user.pk
            ),
            stored_password,
        )
        after_counts = (
            ProjectPublication.objects.count(),
            ProjectWorkspace.objects.count(),
            UIHelpBinding.objects.filter(workspace__isnull=False).count(),
            AuditEvent.objects.count(),
        )
        self.assertEqual(
            tuple(after - before for before, after in zip(before_counts, after_counts)),
            (1, 1, len(definition.manifest["help_bindings"]), 3),
        )
        publication = ProjectPublication.objects.get(
            pk=published.json()["publication_id"]
        )
        self.assertEqual(publication.actor_identifier, self._actor(self.user))

        recovery_url = self._recovery_url(self.project.pk, operation_id)
        recovery_baseline = _database_fingerprint()
        basic_recovery = basic.get(
            recovery_url,
            HTTP_AUTHORIZATION=self._basic_authorization(self.user.username),
        )
        self.assertEqual(basic_recovery.status_code, 200, basic_recovery.content)
        self.assertEqual(basic_recovery.content, published.content)
        self._assert_cache_barrier(basic_recovery)
        self._assert_no_response_cookie_mutation(basic_recovery)
        self.assertEqual(_database_fingerprint(), recovery_baseline)

        invalid_baseline = _database_fingerprint()
        with patch(
            "domain.api.studio_definitions.capture_http_json",
            side_effect=AssertionError("invalid Basic must not capture a body"),
        ) as capture:
            invalid = basic.generic(
                "POST",
                url,
                b"{not-json",
                content_type="application/json",
                HTTP_AUTHORIZATION=self._basic_authorization(
                    self.user.username,
                    password="wrong-password",
                ),
                **headers,
            )
            self.assertEqual(invalid.status_code, 401, invalid.content)
            self.assertEqual(
                invalid.content,
                b'{"detail":"Invalid username/password."}',
            )
            self._assert_no_response_cookie_mutation(invalid)
            capture.assert_not_called()
        self.assertEqual(_database_fingerprint(), invalid_baseline)
        self.assertEqual(
            get_user_model().objects.values_list("password", flat=True).get(
                pk=self.user.pk
            ),
            stored_password,
        )

        invalid_foreign = basic.get(
            self._recovery_url(uuid4(), uuid4()),
            HTTP_AUTHORIZATION=self._basic_authorization(
                self.user.username,
                password="wrong-password",
            ),
        )
        self.assertEqual(invalid_foreign.status_code, 401)
        self.assertEqual(invalid_foreign.content, invalid.content)

        session_user = self._make_user(
            username=f"fd06-session-publisher-{uuid4()}",
            capabilities=tuple(self.permissions),
            projects=(self.project,),
        )
        session_definition = self._draft_version(
            code=f"FD06-CSRF-{uuid4().hex[:8]}",
            version="2.0.0",
        )
        session_operation, session_headers = self._headers(session_definition)
        session_client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(
            session_client.login(
                username=session_user.username,
                password="test-password",
            )
        )
        request_cookies = {
            key: morsel.value for key, morsel in session_client.cookies.items()
        }
        csrf_baseline = _database_fingerprint()
        with patch(
            "domain.api.studio_definitions.capture_http_json",
            side_effect=AssertionError("CSRF denial must precede body capture"),
        ) as capture:
            csrf_denied = session_client.post(
                f"/api/foundation/definitions/{session_definition.pk}/publish-initial/",
                {"locale": "ru", "workspace": self._workspace(unique=True)},
                format="json",
                **session_headers,
            )
            self.assertEqual(csrf_denied.status_code, 403, csrf_denied.content)
            capture.assert_not_called()
        self._assert_no_response_cookie_mutation(csrf_denied)
        self.assertEqual(
            {
                key: morsel.value for key, morsel in session_client.cookies.items()
            },
            request_cookies,
        )
        self.assertEqual(_database_fingerprint(), csrf_baseline)
        self.assertIsInstance(session_operation, UUID)

        non_get_baseline = _database_fingerprint()
        anonymous = APIClient(enforce_csrf_checks=True)
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            with self.subTest(recovery_method=method):
                response = anonymous.generic(
                    method,
                    recovery_url,
                    b"{not-json",
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 405)
                self.assertEqual(response.content, b"")
                self.assertEqual(response["Allow"], "GET")
                self._assert_no_response_cookie_mutation(response)
        self.assertEqual(_database_fingerprint(), non_get_baseline)


@skipUnless(
    connection.vendor == "postgresql",
    "PostgreSQL concurrency authority only",
)
class FoundationStudioPublicationReconciliationConcurrencyTests(
    FoundationStudioBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self) -> None:
        self.make_contract()

    @staticmethod
    def _principal(actor: str) -> StudioPrincipal:
        return StudioPrincipal.for_role(
            actor_identifier=actor,
            role=StudioRole.STUDIO_PUBLISHER,
        )

    @staticmethod
    def _postgresql_timeouts() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '5s'")
            cursor.execute("SET statement_timeout = '20s'")

    def _run_race(self, workers) -> tuple[list[object], list[Exception]]:
        barrier = threading.Barrier(len(workers))
        outcomes: list[object] = []
        errors: list[Exception] = []
        outcome_lock = threading.Lock()

        def run(worker) -> None:
            close_old_connections()
            try:
                self._postgresql_timeouts()
                barrier.wait(timeout=10)
                value = worker()
                with outcome_lock:
                    outcomes.append(value)
            except Exception as exc:  # exact loser type/code asserted by caller
                with outcome_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=run, args=(worker,), daemon=True)
            for worker in workers
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(
            any(thread.is_alive() for thread in threads),
            "FD06 PostgreSQL race exceeded its bounded join.",
        )
        self.assertFalse(
            any(isinstance(error, OperationalError) for error in errors),
            f"FD06 PostgreSQL race raised OperationalError: {errors!r}",
        )
        return outcomes, errors

    def _initial_operation(self, *, code: str, actor: str):
        definition = self.draft(code=code)
        operation_id = uuid4()
        workspace = copy.deepcopy(self.workspace_spec())
        request_hash = _semantic_request_sha256(
            operation_kind="INITIAL",
            project_id=definition.project_id,
            definition_id=definition.pk,
            expected_manifest_hash=definition.manifest_hash,
            actor_identifier=actor,
            locale="ru",
            initial_workspace=workspace,
        )
        return definition, operation_id, workspace, request_hash

    def _commit_initial(self, *, code: str, actor: str):
        definition, operation_id, workspace, request_hash = (
            self._initial_operation(code=code, actor=actor)
        )
        result = reconcile_publication_operation(
            definition=definition,
            operation_id=operation_id,
            request_sha256=request_hash,
            expected_manifest_hash=definition.manifest_hash,
            operation_kind="INITIAL",
            principal=self._principal(actor),
            locale="ru",
            workspace_spec=workspace,
        )
        definition.refresh_from_db()
        return definition, result.publication, workspace

    def _validated_race_successor(
        self,
        predecessor: ProjectDefinitionVersion,
        *,
        code: str,
        version: str,
        actor: str,
    ) -> ProjectDefinitionVersion:
        draft = clone_project_definition_draft(
            predecessor,
            code=code,
            version=version,
            principal=FoundationStudioBootstrapMixin.editor(
                actor="fd06-race-editor"
            ),
        )
        return validate_project_definition(
            draft,
            actor_identifier=actor,
            principal=self._principal(actor),
        )

    def test_concurrent_initial_same_key_has_one_fresh_and_one_replay(self):
        actor = "fd06-race-initial-same"
        definition, operation_id, workspace, request_hash = self._initial_operation(
            code="FD06-RACE-INITIAL-SAME",
            actor=actor,
        )
        definition_id = definition.pk

        def worker():
            local = ProjectDefinitionVersion.objects.get(pk=definition_id)
            result = reconcile_publication_operation(
                definition=local,
                operation_id=operation_id,
                request_sha256=request_hash,
                expected_manifest_hash=local.manifest_hash,
                operation_kind="INITIAL",
                principal=self._principal(actor),
                locale="ru",
                workspace_spec=workspace,
            )
            return result.replayed, str(result.publication.pk)

        outcomes, errors = self._run_race((worker, worker))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(item[0] for item in outcomes), [False, True])
        self.assertEqual(len({item[1] for item in outcomes}), 1)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(
            UIHelpBinding.objects.filter(workspace__isnull=False).count(),
            len(definition.manifest["help_bindings"]),
        )
        self.assertEqual(AuditEvent.objects.count(), 3)
        publication = ProjectPublication.objects.get()
        self.assertEqual(
            publication.code,
            f"PUBOP-{operation_id}-{request_hash}",
        )

    def test_concurrent_initial_different_keys_has_one_commit_and_one_typed_loser(self):
        actor = "fd06-race-initial-different"
        definition, _, workspace, request_hash = self._initial_operation(
            code="FD06-RACE-INITIAL-DIFFERENT",
            actor=actor,
        )
        definition_id = definition.pk
        operation_ids = (uuid4(), uuid4())

        def make_worker(operation_id):
            def worker():
                local = ProjectDefinitionVersion.objects.get(pk=definition_id)
                result = reconcile_publication_operation(
                    definition=local,
                    operation_id=operation_id,
                    request_sha256=request_hash,
                    expected_manifest_hash=local.manifest_hash,
                    operation_kind="INITIAL",
                    principal=self._principal(actor),
                    locale="ru",
                    workspace_spec=workspace,
                )
                return operation_id, result.replayed, str(result.publication.pk)

            return worker

        outcomes, errors = self._run_race(
            tuple(make_worker(operation_id) for operation_id in operation_ids)
        )
        self.assertEqual(len(outcomes), 1)
        self.assertFalse(outcomes[0][1])
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FoundationStudioApplicationConflict)
        self.assertEqual(
            errors[0].conflict_code,
            "PUBLICATION_ALREADY_COMMITTED",
        )
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        winner_operation = outcomes[0][0]
        loser_operation = next(
            item for item in operation_ids if item != winner_operation
        )
        self.assertTrue(
            ProjectPublication.objects.filter(
                code__startswith=f"PUBOP-{winner_operation}-"
            ).exists()
        )
        self.assertFalse(
            ProjectPublication.objects.filter(
                code__startswith=f"PUBOP-{loser_operation}-"
            ).exists()
        )

    def test_concurrent_successor_same_key_has_one_fresh_and_one_replay(self):
        actor = "fd06-race-successor-same"
        predecessor, _, _ = self._commit_initial(
            code="FD06-RACE-SUCCESSOR-SAME-INITIAL",
            actor=actor,
        )
        successor = self._validated_race_successor(
            predecessor,
            code="FD06-RACE-SUCCESSOR-SAME",
            version="2.0.0",
            actor=actor,
        )
        successor_id = successor.pk
        operation_id = uuid4()
        request_hash = _semantic_request_sha256(
            operation_kind="SUCCESSOR",
            project_id=successor.project_id,
            definition_id=successor.pk,
            expected_manifest_hash=successor.manifest_hash,
            actor_identifier=actor,
            locale="ru",
            initial_workspace=None,
        )

        def worker():
            local = ProjectDefinitionVersion.objects.get(pk=successor_id)
            result = reconcile_publication_operation(
                definition=local,
                operation_id=operation_id,
                request_sha256=request_hash,
                expected_manifest_hash=local.manifest_hash,
                operation_kind="SUCCESSOR",
                principal=self._principal(actor),
                locale="ru",
                workspace_spec=None,
            )
            return result.replayed, str(result.publication.pk)

        outcomes, errors = self._run_race((worker, worker))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(item[0] for item in outcomes), [False, True])
        self.assertEqual(len({item[1] for item in outcomes}), 1)
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(
            ProjectPublication.objects.filter(
                initial_workspace__isnull=True
            ).count(),
            1,
        )
        predecessor.refresh_from_db()
        successor.refresh_from_db()
        self.assertFalse(predecessor.is_current)
        self.assertTrue(successor.is_current)

    def test_concurrent_successor_different_keys_has_one_current_winner_and_one_typed_loser(self):
        actor = "fd06-race-successor-different"
        predecessor, initial_publication, _ = self._commit_initial(
            code="FD06-RACE-SUCCESSOR-DIFFERENT-INITIAL",
            actor=actor,
        )
        old_workspace = initial_publication.initial_workspace
        assert old_workspace is not None
        old_pin = (
            old_workspace.pk,
            old_workspace.definition_version_id,
            old_workspace.definition_manifest_hash,
        )
        successors = (
            self._validated_race_successor(
                predecessor,
                code="FD06-RACE-SUCCESSOR-DIFFERENT-1",
                version="2.0.0",
                actor=actor,
            ),
            self._validated_race_successor(
                predecessor,
                code="FD06-RACE-SUCCESSOR-DIFFERENT-2",
                version="3.0.0",
                actor=actor,
            ),
        )
        operation_ids = (uuid4(), uuid4())

        def make_worker(successor, operation_id):
            request_hash = _semantic_request_sha256(
                operation_kind="SUCCESSOR",
                project_id=successor.project_id,
                definition_id=successor.pk,
                expected_manifest_hash=successor.manifest_hash,
                actor_identifier=actor,
                locale="ru",
                initial_workspace=None,
            )

            def worker():
                local = ProjectDefinitionVersion.objects.get(pk=successor.pk)
                result = reconcile_publication_operation(
                    definition=local,
                    operation_id=operation_id,
                    request_sha256=request_hash,
                    expected_manifest_hash=local.manifest_hash,
                    operation_kind="SUCCESSOR",
                    principal=self._principal(actor),
                    locale="ru",
                    workspace_spec=None,
                )
                return successor.pk, operation_id, str(result.publication.pk)

            return worker

        outcomes, errors = self._run_race(
            tuple(
                make_worker(successor, operation_id)
                for successor, operation_id in zip(successors, operation_ids)
            )
        )
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FoundationStudioApplicationConflict)
        self.assertEqual(
            errors[0].conflict_code,
            "PUBLICATION_TARGET_STATE_CONFLICT",
        )
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        old_workspace.refresh_from_db()
        self.assertEqual(
            (
                old_workspace.pk,
                old_workspace.definition_version_id,
                old_workspace.definition_manifest_hash,
            ),
            old_pin,
        )
        winner_id = outcomes[0][0]
        loser_id = next(item.pk for item in successors if item.pk != winner_id)
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(
                pk=winner_id,
                publication_status=PublicationStatus.PUBLISHED,
                is_current=True,
            ).count(),
            1,
        )
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(
                pk=loser_id,
                publication_status=PublicationStatus.VALIDATED,
                is_current=False,
            ).count(),
            1,
        )
        predecessor.refresh_from_db()
        self.assertFalse(predecessor.is_current)
