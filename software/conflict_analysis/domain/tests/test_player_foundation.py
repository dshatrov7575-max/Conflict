"""The literal G7 Foundation Player registry (12 portable + 2 PostgreSQL nodes)."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
from contextlib import contextmanager
from datetime import date
from unittest import skipUnless
from unittest.mock import patch
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name
from domain.enums import AuditScope, ExperimentType, PublicationStatus
from domain.models import (
    Actor,
    ActorElementRole,
    AnalyticalElement,
    AuditEvent,
    Experiment,
    ImmutableCapturedModel,
    HelpTopic,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    ProjectWorkspace,
    TimeSlice,
    UIHelpBinding,
    _canonical_assessment_projection_write,
)
from domain.policies import bootstrap_initial_project_definition, validate_project_definition
from domain.services.player_help_catalog import CATALOG_LOCALE, CATALOG_VERSION, PLAYER_HELP_KEYS
from domain.services.project_definitions import (
    clone_project_definition_draft,
    create_project_definition_draft,
    publish_successor_project_definition,
)
from domain.tests.test_foundation_studio_bootstrap import FoundationStudioBootstrapMixin
from domain.tests.test_player_help_provisioning import (
    add_valid_future_player_help_binding,
    assert_player_help_http_payload,
    assert_player_help_provisioning_contract,
    player_help_snapshot,
)
from domain.tests.test_player_projection import _FD08ProjectionGuardTeardownMixin
from production_studio.tests import database_fingerprint as studio_database_fingerprint


PLAYER_PERMISSION_CODENAMES = (
    "view_project",
    "view_projectdefinitionversion",
    "view_projectworkspace",
    "view_timeslice",
    "view_experiment",
    "view_expertprofile",
    "view_assessmentset",
    "view_helptopic",
    "add_projectworkspace",
    "add_timeslice",
)


class FoundationPlayerFixture(FoundationStudioBootstrapMixin):
    """Shared, real-session Foundation fixture for the G7 and Product suites."""

    maxDiff = None

    def setUp_player_fixture(self) -> None:
        self.make_contract()
        bootstrap = bootstrap_initial_project_definition(
            definition=self.draft(code=f"G7-DEF-{uuid4().hex[:12]}"),
            principal=self.publisher(actor="g7-publisher"),
            actor_identifier="g7-publisher",
            workspace_spec=self.workspace_spec(),
            locale="ru",
        )
        self.project = bootstrap.definition.project
        self.definition = bootstrap.definition
        self.default_workspace = bootstrap.workspace
        self.assertEqual(self.definition.publication_status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.definition.is_current)
        self.assertTrue(self.default_workspace.is_default)
        self.assertEqual(
            ProjectPublication.objects.filter(
                project=self.project,
                initial_workspace=self.default_workspace,
                definition_version=self.definition,
            ).count(),
            1,
        )

        # RC4 allows PLAYER bindings for historical/default Workspaces only
        # through explicit provisioning.  The helper calls the command and
        # verifies its second execution is byte-for-byte row-idempotent.
        assert_player_help_provisioning_contract(self, self.default_workspace)

        self.player_user = self.make_player_user(project=self.project, suffix="primary")
        self.player_group = Group.objects.get(
            name=project_access_group_name(self.project.pk)
        )
        self.player_client = self.player_session(self.player_user)

    @staticmethod
    def canonical_json(payload: object) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def make_player_user(
        self,
        *,
        project: Project,
        suffix: str,
        permissions: tuple[str, ...] = PLAYER_PERMISSION_CODENAMES,
        scoped: bool = True,
        staff: bool = False,
        superuser: bool = False,
    ):
        user_model = get_user_model()
        username = f"g7-player-{suffix}-{uuid4().hex[:10]}"
        user = user_model.objects.create_user(
            username=username,
            password="g7-test-password",
            is_staff=staff,
            is_superuser=superuser,
            is_active=True,
        )
        granted = list(
            Permission.objects.filter(
                content_type__app_label="domain",
                codename__in=permissions,
            ).order_by("codename")
        )
        self.assertEqual({permission.codename for permission in granted}, set(permissions))
        user.user_permissions.add(*granted)
        if scoped:
            group, _ = Group.objects.get_or_create(
                name=project_access_group_name(project.pk)
            )
            user.groups.add(group)
        return user

    def player_session(self, user, *, project_id=None) -> APIClient:
        """A real Django session plus a real same-origin CSRF cookie."""

        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        response = self.player_get(
            client, self.definition_list_url(project_id or self.project.pk)
        )
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertIn(settings.CSRF_COOKIE_NAME, client.cookies)
        return client

    @staticmethod
    def domain_fingerprint() -> dict[str, str]:
        """Byte/content hashes for every persisted domain table only."""

        return {
            table: digest
            for table, digest in studio_database_fingerprint().items()
            if table.startswith("domain_")
        }

    @staticmethod
    def project_domain_fingerprint(project: Project) -> dict[str, str]:
        """Hash the full persisted graph that is reachable from one Project.

        This deliberately uses table values rather than model serialization so
        a concurrent loser cannot conceal an in-place update behind unchanged
        row counts.  Workspace and definition foreign-key lanes cover the
        canonical projection tables whose rows do not carry `project_id`.
        """

        def database_uuid(value) -> str:
            parsed = UUID(str(value))
            return parsed.hex if connection.vendor == "sqlite" else str(parsed)

        project_id = database_uuid(project.pk)
        workspace_ids = [
            database_uuid(value)
            for value in ProjectWorkspace.objects.filter(project=project)
            .order_by("pk")
            .values_list("pk", flat=True)
        ]
        definition_ids = [
            database_uuid(value)
            for value in ProjectDefinitionVersion.objects.filter(project=project)
            .order_by("pk")
            .values_list("pk", flat=True)
        ]
        snapshots: dict[str, str] = {}

        def where_for(columns: set[str]) -> tuple[str, list[str]] | None:
            if "project_id" in columns:
                return "project_id", [project_id]
            if "workspace_id" in columns and workspace_ids:
                return "workspace_id", workspace_ids
            if "definition_version_id" in columns and definition_ids:
                return "definition_version_id", definition_ids
            if "definition_id" in columns and definition_ids:
                return "definition_id", definition_ids
            if "id" in columns and table == Project._meta.db_table:
                return "id", [project_id]
            return None

        with connection.cursor() as cursor:
            for table in sorted(connection.introspection.table_names(cursor)):
                if not table.startswith("domain_"):
                    continue
                description = connection.introspection.get_table_description(
                    cursor, table
                )
                columns = [field.name for field in description]
                scope = where_for(set(columns))
                if scope is None:
                    continue
                column, values = scope
                quoted_columns = ", ".join(
                    connection.ops.quote_name(name) for name in columns
                )
                placeholders = ", ".join("%s" for _ in values)
                cursor.execute(
                    f"SELECT {quoted_columns} FROM {connection.ops.quote_name(table)} "
                    f"WHERE {connection.ops.quote_name(column)} IN ({placeholders})",
                    values,
                )
                rows = sorted(repr(tuple(row)) for row in cursor.fetchall())
                payload = json.dumps(
                    {"columns": columns, "rows": rows},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
                snapshots[table] = hashlib.sha256(payload).hexdigest()
        return snapshots

    @staticmethod
    def domain_write_sql(captured: CaptureQueriesContext) -> tuple[str, ...]:
        """Bound SQL proof that a Player read/replay issued no domain DML."""

        writes: list[str] = []
        for query in captured:
            sql = str(query["sql"])
            if (
                re.match(r"^\s*(?:INSERT|UPDATE|DELETE)\b", sql, flags=re.I)
                and "domain_" in sql.lower()
            ):
                writes.append(sql)
        return tuple(writes)

    @contextmanager
    def capture_no_domain_writes(self):
        with CaptureQueriesContext(connection) as captured:
            yield
        self.assertEqual(self.domain_write_sql(captured), ())

    def player_get(self, client: APIClient, url: str):
        """Run a Player GET while proving domain bytes and DML are unchanged."""

        before = self.domain_fingerprint()
        with self.capture_no_domain_writes():
            response = client.get(url)
        self.assertEqual(self.domain_fingerprint(), before)
        return response

    @staticmethod
    def definition_list_url(project_id) -> str:
        return f"/api/foundation/player/projects/{project_id}/definitions/"

    @staticmethod
    def definition_url(definition_id) -> str:
        return f"/api/foundation/player/definitions/{definition_id}/"

    @staticmethod
    def workspace_list_url(project_id) -> str:
        return f"/api/foundation/player/projects/{project_id}/workspaces/"

    @staticmethod
    def workspace_url(workspace_id) -> str:
        return f"/api/foundation/player/workspaces/{workspace_id}/"

    @staticmethod
    def time_slice_url(workspace_id) -> str:
        return f"/api/foundation/player/workspaces/{workspace_id}/time-slices/"

    @staticmethod
    def experiments_url(workspace_id) -> str:
        return f"/api/foundation/player/workspaces/{workspace_id}/experiments/"

    @staticmethod
    def help_url(workspace_id, ui_key: str, *, locale: str, version: str) -> str:
        return (
            f"/api/foundation/player/workspaces/{workspace_id}/help/{ui_key}/"
            f"?locale={locale}&version={version}"
        )

    def csrf_post(
        self,
        client: APIClient,
        url: str,
        body: bytes,
        *,
        operation_id: UUID,
        if_match: str,
        csrf: bool = True,
        **headers,
    ):
        request_headers = {
            "HTTP_IDEMPOTENCY_KEY": str(operation_id),
            "HTTP_IF_MATCH": if_match,
            **headers,
        }
        if csrf:
            request_headers["HTTP_X_CSRFTOKEN"] = client.cookies[
                settings.CSRF_COOKIE_NAME
            ].value
        return client.generic(
            "POST",
            url,
            body,
            content_type="application/json",
            **request_headers,
        )

    def workspace_body(
        self,
        *,
        workspace_id: UUID | None = None,
        code: str | None = None,
        name: str = "Рабочее пространство Player",
        is_default: bool = False,
        definition_id=None,
        definition_manifest_hash: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        workspace_id = workspace_id or uuid4()
        return {
            "id": str(workspace_id),
            "code": code or f"PLAYER-WS-{workspace_id.hex[:12]}",
            "version": "1.0.0",
            "name": name,
            "definition_id": str(definition_id or self.definition.pk),
            "definition_manifest_hash": (
                definition_manifest_hash or self.definition.manifest_hash
            ),
            "is_default": is_default,
            "metadata": {} if metadata is None else metadata,
        }

    @staticmethod
    def slice_body(
        *,
        slice_id: UUID | None = None,
        code: str | None = None,
        cutoff_date: str = "2026-01-15",
        name: str = "Временной срез Player",
        metadata: dict | None = None,
    ) -> dict:
        slice_id = slice_id or uuid4()
        return {
            "id": str(slice_id),
            "code": code or f"PLAYER-SLICE-{slice_id.hex[:12]}",
            "version": "1.0.0",
            "name": name,
            "cutoff_date": cutoff_date,
            "order": 0,
            "metadata": {} if metadata is None else metadata,
        }

    def row_counts(self) -> tuple[int, ...]:
        return (
            ProjectWorkspace.objects.count(),
            TimeSlice.objects.count(),
            AuditEvent.objects.count(),
            Actor.objects.count(),
            AnalyticalElement.objects.count(),
            ActorElementRole.objects.count(),
            UIHelpBinding.objects.count(),
            HelpTopic.objects.count(),
        )

    def database_fingerprint(self) -> tuple[int, ...]:
        """Compatibility alias for Product's existing count arithmetic.

        Foundation's zero-write proofs use ``domain_fingerprint``; this older
        name remains only until the dependent Product fixture switches to the
        explicit ``row_counts`` spelling.
        """

        return self.row_counts()

    def assert_error(self, response, *, status: int, code: str) -> None:
        self.assertEqual(response.status_code, status, getattr(response, "data", None))
        payload = response.json()
        self.assertEqual(set(payload), {"code", "errors"})
        self.assertEqual(payload["code"], code)
        self.assertEqual(len(payload["errors"]), 1)
        self.assertIsInstance(payload["errors"][0], str)
        self.assertTrue(payload["errors"][0])
        # A stable Russian message is deliberately checked as a literal response
        # property, not by importing the implementation's error map.
        self.assertTrue(
            any("А" <= char <= "я" or char in "Ёё" for char in payload["errors"][0])
        )

    def assert_same_bounded_error(self, left, right, *, status: int, code: str) -> None:
        self.assert_error(left, status=status, code=code)
        self.assert_error(right, status=status, code=code)
        self.assertEqual(left.content, right.content)

    def assert_canonical_get(self, response, *, keys: set[str]) -> dict:
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Content-Type"].split(";", 1)[0], "application/json")
        payload = response.json()
        common = {"contract", "version", "response_sha256"}
        self.assertEqual(set(payload), common | keys)
        core = {key: value for key, value in payload.items() if key != "response_sha256"}
        self.assertEqual(
            payload["response_sha256"],
            hashlib.sha256(self.canonical_json(core)).hexdigest(),
        )
        self.assertEqual(
            response["ETag"],
            f'"{hashlib.sha256(response.content).hexdigest()}"',
        )
        self.assertEqual(response.content, self.canonical_json(payload))
        return payload

    def create_complete_workspace(
        self,
        *,
        client: APIClient | None = None,
        operation_id: UUID | None = None,
        body: dict | None = None,
    ) -> tuple[ProjectWorkspace, object, dict, UUID]:
        client = client or self.player_client
        operation_id = operation_id or uuid4()
        body = body or self.workspace_body()
        response = self.csrf_post(
            client,
            self.workspace_list_url(self.project.pk),
            self.canonical_json(body),
            operation_id=operation_id,
            if_match=f'"{self.definition.manifest_hash}"',
        )
        self.assertEqual(response.status_code, 201, getattr(response, "data", None))
        payload = response.json()
        self.assertEqual(payload["contract"], "FOUNDATION_PLAYER_WORKSPACE_CREATE_V1")
        self.assertEqual(payload["operation_id"], str(operation_id))
        workspace = ProjectWorkspace.objects.get(pk=body["id"])
        self.assertFalse(workspace.is_default)
        self.assertEqual(workspace.definition_version_id, self.definition.pk)
        self.assertEqual(workspace.definition_manifest_hash, self.definition.manifest_hash)
        receipt_core = {
            key: value for key, value in payload.items() if key != "receipt_sha256"
        }
        self.assertEqual(
            payload["receipt_sha256"],
            hashlib.sha256(self.canonical_json(receipt_core)).hexdigest(),
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                pk=operation_id,
                scope=AuditScope.WORKSPACE,
                workspace=workspace,
            ).count(),
            1,
        )
        return workspace, response, body, operation_id

    def make_other_project(self):
        """Make an independently bootstrapped Project for scope/collision probes."""

        project_id = uuid4()
        replacements: dict[str, str] = {}

        def remap_manifest_uuids(value):
            """Keep every manifest reference internally coherent and globally fresh."""

            if isinstance(value, dict):
                return {
                    key: remap_manifest_uuids(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [remap_manifest_uuids(item) for item in value]
            if isinstance(value, str):
                try:
                    UUID(value)
                except ValueError:
                    return value
                return replacements.setdefault(value, str(uuid4()))
            return value

        # The shared Studio vector uses fixed UUIDs for every projection and
        # workspace Help binding.  An independent Project must not reuse even
        # those internal UUIDs: remap all references before canonical bootstrap.
        manifest = remap_manifest_uuids(copy.deepcopy(self.manifest))
        manifest["project"].update(
            {
                "id": str(project_id),
                "code": f"G7-OTHER-{project_id.hex[:10]}",
                "version": "1.0.0",
                "name": "Другой проект G7",
                "description": "Изолированный проект для scope-проверок.",
                "metadata": {},
            }
        )
        project = Project.objects.create(
            id=project_id,
            code=manifest["project"]["code"],
            version="1.0.0",
            name=manifest["project"]["name"],
            description=manifest["project"]["description"],
            metadata={},
            primary_language_tag="ru",
            primary_language_assignment="EXPLICIT",
        )
        definition = create_project_definition_draft(
            project=project,
            code=f"G7-OTHER-DEF-{project_id.hex[:10]}",
            version="1.0.0",
            manifest=manifest,
            principal=self.editor(actor="g7-other-editor"),
        )
        bootstrap = bootstrap_initial_project_definition(
            definition=definition,
            principal=self.publisher(actor="g7-other-publisher"),
            actor_identifier="g7-other-publisher",
            workspace_spec={
                **self.workspace_spec(),
                "id": str(uuid4()),
                "code": f"G7-OTHER-DEFAULT-{project_id.hex[:8]}",
            },
            locale="ru",
        )
        return bootstrap.definition.project, bootstrap.definition, bootstrap.workspace


class FoundationPlayerWorkspaceSliceTests(FoundationPlayerFixture, TestCase):
    def setUp(self) -> None:
        self.setUp_player_fixture()

    def test_player_permission_family_session_scope_and_no_studio_mixing_are_exact(self):
        baseline = self.domain_fingerprint()
        self.assert_canonical_get(
            self.player_get(self.player_client, self.definition_list_url(self.project.pk)),
            keys={"project", "definitions"},
        )

        anonymous = self.player_get(
            APIClient(), self.definition_list_url(self.project.pk)
        )
        self.assert_error(
            anonymous, status=401, code="PLAYER_AUTHENTICATION_REQUIRED"
        )

        missing = self.make_player_user(
            project=self.project,
            suffix="missing-read",
            permissions=PLAYER_PERMISSION_CODENAMES[:-1],
        )
        missing_client = APIClient(enforce_csrf_checks=True)
        missing_client.force_login(missing)
        self.assert_error(
            self.player_get(missing_client, self.definition_list_url(self.project.pk)),
            status=403,
            code="PLAYER_PERMISSION_DENIED",
        )

        unscoped = self.make_player_user(
            project=self.project,
            suffix="unscoped",
            scoped=False,
        )
        unscoped_client = APIClient(enforce_csrf_checks=True)
        unscoped_client.force_login(unscoped)
        absent = self.player_get(self.player_client, self.definition_list_url(uuid4()))
        denied = self.player_get(unscoped_client, self.definition_list_url(self.project.pk))
        self.assert_same_bounded_error(
            absent, denied, status=404, code="PLAYER_NOT_FOUND"
        )

        studio = Permission.objects.get(
            content_type__app_label="domain", codename="studio_read_definition"
        )
        self.player_user.user_permissions.add(studio)
        mixed = APIClient(enforce_csrf_checks=True)
        mixed.force_login(self.player_user)
        self.assert_error(
            self.player_get(mixed, self.definition_list_url(self.project.pk)),
            status=403,
            code="PLAYER_PERMISSION_DENIED",
        )

        staff = self.make_player_user(
            project=self.project, suffix="staff", staff=True
        )
        staff_client = APIClient(enforce_csrf_checks=True)
        staff_client.force_login(staff)
        self.assert_error(
            self.player_get(staff_client, self.definition_list_url(self.project.pk)),
            status=403,
            code="PLAYER_PERMISSION_DENIED",
        )
        self.assertEqual(self.domain_fingerprint(), baseline)

    def test_definition_list_returns_only_scoped_published_current_and_noncurrent_versions(self):
        successor = clone_project_definition_draft(
            self.definition,
            code=f"G7-SUCCESSOR-{uuid4().hex[:12]}",
            version="2.0.0",
            principal=self.editor(actor="g7-successor-editor"),
        )
        successor = validate_project_definition(
            successor,
            actor_identifier="g7-successor-validator",
            principal=self.publisher(actor="g7-successor-validator"),
        )
        publish_successor_project_definition(
            successor,
            principal=self.publisher(actor="g7-successor-publisher"),
            locale="ru",
        )
        self.definition.refresh_from_db()
        successor.refresh_from_db()

        response = self.player_get(self.player_client, self.definition_list_url(self.project.pk))
        payload = self.assert_canonical_get(response, keys={"project", "definitions"})
        definitions = payload["definitions"]
        self.assertEqual({row["id"] for row in definitions}, {str(self.definition.pk), str(successor.pk)})
        current = {row["id"]: row["is_current"] for row in definitions}
        self.assertFalse(current[str(self.definition.pk)])
        self.assertTrue(current[str(successor.pk)])
        self.assertTrue(
            all(row["publication_status"] == PublicationStatus.PUBLISHED for row in definitions)
        )
        self.assertTrue(all(row["manifest_hash"] for row in definitions))

    def test_definition_open_hides_draft_validated_foreign_and_absent_with_zero_writes(self):
        draft = clone_project_definition_draft(
            self.definition,
            code=f"G7-HIDDEN-DRAFT-{uuid4().hex[:10]}",
            version="2.0.0",
            principal=self.editor(actor="g7-hidden-draft-editor"),
        )
        validated = clone_project_definition_draft(
            self.definition,
            code=f"G7-HIDDEN-VALIDATED-{uuid4().hex[:10]}",
            version="3.0.0",
            principal=self.editor(actor="g7-hidden-validated-editor"),
        )
        validated = validate_project_definition(
            validated,
            actor_identifier="g7-hidden-validator",
            principal=self.publisher(actor="g7-hidden-validator"),
        )
        other_project, other_definition, _ = self.make_other_project()
        other_user = self.make_player_user(
            project=other_project, suffix="other-definition"
        )
        other_client = self.player_session(other_user, project_id=other_project.pk)
        baseline = self.domain_fingerprint()

        visible = self.player_get(self.player_client, self.definition_url(self.definition.pk))
        self.assert_canonical_get(visible, keys={"project", "definition"})
        responses = (
            self.player_get(self.player_client, self.definition_url(draft.pk)),
            self.player_get(self.player_client, self.definition_url(validated.pk)),
            self.player_get(self.player_client, self.definition_url(other_definition.pk)),
            self.player_get(self.player_client, self.definition_url(uuid4())),
            self.player_get(other_client, self.definition_url(self.definition.pk)),
        )
        for response in responses:
            self.assert_error(response, status=404, code="PLAYER_NOT_FOUND")
            self.assertEqual(response.content, responses[0].content)
        self.assertEqual(self.domain_fingerprint(), baseline)

    def test_workspace_list_open_and_manifest_pin_truth_are_exact(self):
        listed = self.player_get(self.player_client, self.workspace_list_url(self.project.pk))
        payload = self.assert_canonical_get(listed, keys={"project", "workspaces"})
        default = next(row for row in payload["workspaces"] if row["id"] == str(self.default_workspace.pk))
        self.assertEqual(default["assessment_projection_status"], "NOT_PROVEN")
        self.assertIsNone(default["assessment_projection_sha256"])

        workspace, _, _, _ = self.create_complete_workspace()
        after_create = self.domain_fingerprint()
        opened = self.player_get(self.player_client, self.workspace_url(workspace.pk))
        opened_payload = self.assert_canonical_get(
            opened, keys={"project", "workspace", "definition"}
        )
        exact = opened_payload["workspace"]
        self.assertEqual(exact["id"], str(workspace.pk))
        self.assertEqual(exact["definition_id"], str(self.definition.pk))
        self.assertEqual(exact["definition_manifest_hash"], self.definition.manifest_hash)
        self.assertEqual(exact["assessment_projection_status"], "COMPLETE")
        self.assertEqual(len(exact["assessment_projection_sha256"]), 64)
        self.assertEqual(self.domain_fingerprint(), after_create)

        # RC6: stored evidence is never a read-model authority.  A forged
        # COMPLETE marker on the historical, receipt-less default Workspace
        # must be exposed as bounded integrity conflict, not silently trusted
        # or repaired by GET.
        with _canonical_assessment_projection_write("projection"):
            ProjectWorkspace.objects.filter(pk=self.default_workspace.pk).update(
                assessment_projection_status="COMPLETE",
                assessment_projection_sha256="0" * 64,
            )
        before_conflict_open = self.domain_fingerprint()
        drifted = self.player_get(self.player_client, self.workspace_url(self.default_workspace.pk))
        drift_payload = self.assert_canonical_get(
            drifted, keys={"project", "workspace", "definition"}
        )
        self.assertEqual(
            drift_payload["workspace"]["assessment_projection_status"],
            "INTEGRITY_CONFLICT",
        )
        self.assertIsNone(drift_payload["workspace"]["assessment_projection_sha256"])
        self.assertEqual(self.domain_fingerprint(), before_conflict_open)
        blocked_slice = self.csrf_post(
            self.player_client,
            self.time_slice_url(self.default_workspace.pk),
            self.canonical_json(self.slice_body()),
            operation_id=uuid4(),
            if_match=f'"{self.default_workspace.definition_manifest_hash}"',
        )
        self.assert_error(
            blocked_slice,
            status=409,
            code="ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT",
        )
        self.assertEqual(self.domain_fingerprint(), before_conflict_open)

    def test_workspace_create_requires_exact_key_if_match_body_nondefault_and_published_definition(self):
        url = self.workspace_list_url(self.project.pk)
        body = self.workspace_body()
        raw = self.canonical_json(body)
        before = self.domain_fingerprint()

        missing_key = self.player_client.generic(
            "POST",
            url,
            raw,
            content_type="application/json",
            HTTP_IF_MATCH=f'"{self.definition.manifest_hash}"',
            HTTP_X_CSRFTOKEN=self.player_client.cookies[settings.CSRF_COOKIE_NAME].value,
        )
        self.assert_error(missing_key, status=400, code="PLAYER_REQUEST_INVALID")
        self.assertEqual(self.domain_fingerprint(), before)

        weak = self.csrf_post(
            self.player_client,
            url,
            raw,
            operation_id=uuid4(),
            if_match=self.definition.manifest_hash,
        )
        self.assert_error(weak, status=400, code="PLAYER_REQUEST_INVALID")
        stale = self.csrf_post(
            self.player_client,
            url,
            raw,
            operation_id=uuid4(),
            if_match='"' + "0" * 64 + '"',
        )
        self.assert_error(stale, status=409, code="PLAYER_STALE")
        bad_default = self.workspace_body(is_default=True)
        denied_default = self.csrf_post(
            self.player_client,
            url,
            self.canonical_json(bad_default),
            operation_id=uuid4(),
            if_match=f'"{self.definition.manifest_hash}"',
        )
        self.assert_error(denied_default, status=400, code="PLAYER_REQUEST_INVALID")
        no_csrf = self.csrf_post(
            self.player_client,
            url,
            raw,
            operation_id=uuid4(),
            if_match=f'"{self.definition.manifest_hash}"',
            csrf=False,
        )
        self.assert_error(no_csrf, status=403, code="PLAYER_CSRF_FAILED")
        self.assertEqual(self.domain_fingerprint(), before)

        workspace, response, _, operation_id = self.create_complete_workspace(body=body)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["operation_id"], str(operation_id))
        self.assertEqual(ProjectWorkspace.objects.filter(pk=workspace.pk, is_default=False).count(), 1)

    def test_workspace_fresh_replay_key_reuse_identity_conflict_and_rollback_are_exact(self):
        body = self.workspace_body()
        raw = self.canonical_json(body)
        operation_id = uuid4()
        url = self.workspace_list_url(self.project.pk)
        fresh = self.csrf_post(
            self.player_client,
            url,
            raw,
            operation_id=operation_id,
            if_match=f'"{self.definition.manifest_hash}"',
        )
        self.assertEqual(fresh.status_code, 201, getattr(fresh, "data", fresh.content))
        after_fresh = self.domain_fingerprint()
        with self.capture_no_domain_writes():
            replay = self.csrf_post(
                self.player_client,
                url,
                raw,
                operation_id=operation_id,
                if_match=f'"{self.definition.manifest_hash}"',
            )
        self.assertEqual(replay.status_code, 200, getattr(replay, "data", replay.content))
        self.assertEqual(replay.content, fresh.content)
        self.assertEqual(self.domain_fingerprint(), after_fresh)

        changed = dict(body, name="Изменённое имя")
        with self.capture_no_domain_writes():
            key_reuse = self.csrf_post(
                self.player_client,
                url,
                self.canonical_json(changed),
                operation_id=operation_id,
                if_match=f'"{self.definition.manifest_hash}"',
            )
        self.assert_error(key_reuse, status=409, code="PLAYER_OPERATION_KEY_REUSE")
        self.assertEqual(self.domain_fingerprint(), after_fresh)

        with self.capture_no_domain_writes():
            identity = self.csrf_post(
                self.player_client,
                url,
                raw,
                operation_id=uuid4(),
                if_match=f'"{self.definition.manifest_hash}"',
            )
        self.assert_error(identity, status=409, code="PLAYER_IDENTITY_CONFLICT")
        self.assertEqual(self.domain_fingerprint(), after_fresh)

        other = self.make_player_user(project=self.project, suffix="same-project-replay")
        other_client = self.player_session(other)
        with self.capture_no_domain_writes():
            other_replay = self.csrf_post(
                other_client,
                url,
                raw,
                operation_id=operation_id,
                if_match=f'"{self.definition.manifest_hash}"',
            )
        self.assert_error(other_replay, status=409, code="PLAYER_OPERATION_KEY_REUSE")
        self.assertEqual(self.domain_fingerprint(), after_fresh)

        created = ProjectWorkspace.objects.get(pk=body["id"])
        ProjectWorkspace.objects.filter(pk=created.pk).update(name="Поздняя внешняя правка")
        after_external_drift = self.domain_fingerprint()
        with self.capture_no_domain_writes():
            drift = self.csrf_post(
                self.player_client,
                url,
                raw,
                operation_id=operation_id,
                if_match=f'"{self.definition.manifest_hash}"',
            )
        self.assert_error(drift, status=409, code="PLAYER_OPERATION_RESULT_DRIFT")
        self.assertEqual(self.domain_fingerprint(), after_external_drift)

        failure_body = self.workspace_body()
        before_failure = self.domain_fingerprint()
        with patch(
            "domain.services.player_workspaces.bind_player_help",
            side_effect=RuntimeError("g7-test-help-binding-failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "g7-test-help-binding-failure"):
                self.csrf_post(
                    self.player_client,
                    url,
                    self.canonical_json(failure_body),
                    operation_id=uuid4(),
                    if_match=f'"{self.definition.manifest_hash}"',
                )
        self.assertEqual(self.domain_fingerprint(), before_failure)
        self.assertFalse(ProjectWorkspace.objects.filter(pk=failure_body["id"]).exists())

    def test_workspace_pin_and_default_workspace_cannot_be_reassigned_or_mutated(self):
        workspace, _, _, _ = self.create_complete_workspace()
        default = ProjectWorkspace.objects.get(pk=self.default_workspace.pk)
        before = (
            default.is_default,
            default.definition_version_id,
            default.definition_manifest_hash,
            workspace.is_default,
        )
        workspace.definition_manifest_hash = "0" * 64
        with self.assertRaises(ValidationError):
            workspace.save()
        self.default_workspace.refresh_from_db()
        workspace.refresh_from_db()
        self.assertEqual(
            (
                self.default_workspace.is_default,
                self.default_workspace.definition_version_id,
                self.default_workspace.definition_manifest_hash,
                workspace.is_default,
            ),
            before,
        )
        patch_response = self.player_client.generic(
            "PATCH",
            self.workspace_url(workspace.pk),
            b"{}",
            content_type="application/json",
        )
        self.assertIn(patch_response.status_code, {404, 405})

        # The accepted model intentionally supports older non-G7 callers, so
        # make a synthetic broken topology and prove that Player neither
        # repairs nor replaces the default Workspace.
        self.assertEqual(
            ProjectWorkspace.objects.filter(pk=self.default_workspace.pk).update(
                is_default=False
            ),
            1,
        )
        topology_body = self.workspace_body()
        topology = self.csrf_post(
            self.player_client,
            self.workspace_list_url(self.project.pk),
            self.canonical_json(topology_body),
            operation_id=uuid4(),
            if_match=f'"{self.definition.manifest_hash}"',
        )
        self.assert_error(
            topology, status=409, code="PLAYER_PROJECT_TOPOLOGY_INVALID"
        )
        self.assertFalse(ProjectWorkspace.objects.filter(pk=topology_body["id"]).exists())

    def test_time_slice_list_and_create_require_exact_workspace_project_and_pin(self):
        before = self.domain_fingerprint()
        with self.capture_no_domain_writes():
            unproven = self.csrf_post(
                self.player_client,
                self.time_slice_url(self.default_workspace.pk),
                self.canonical_json(self.slice_body()),
                operation_id=uuid4(),
                if_match=f'"{self.default_workspace.definition_manifest_hash}"',
            )
        self.assert_error(
            unproven, status=409, code="ASSESSMENT_PROJECTION_NOT_PROVEN"
        )
        self.assertEqual(self.domain_fingerprint(), before)

        workspace, _, _, _ = self.create_complete_workspace()
        listed = self.player_get(self.player_client, self.time_slice_url(workspace.pk))
        self.assertEqual(
            self.assert_canonical_get(listed, keys={"workspace_id", "time_slices"})["time_slices"],
            [],
        )
        body = self.slice_body()
        response = self.csrf_post(
            self.player_client,
            self.time_slice_url(workspace.pk),
            self.canonical_json(body),
            operation_id=uuid4(),
            if_match=f'"{workspace.definition_manifest_hash}"',
        )
        self.assertEqual(response.status_code, 201, getattr(response, "data", response.content))
        receipt = response.json()
        self.assertEqual(receipt["contract"], "FOUNDATION_PLAYER_TIME_SLICE_CREATE_V1")
        self.assertEqual(receipt["created_slice"]["id"], body["id"])
        self.assertEqual(receipt["created_slice"]["cutoff_date"], body["cutoff_date"])
        receipt_core = {
            key: value for key, value in receipt.items() if key != "receipt_sha256"
        }
        self.assertEqual(
            receipt["receipt_sha256"],
            hashlib.sha256(self.canonical_json(receipt_core)).hexdigest(),
        )
        time_slice = TimeSlice.objects.get(pk=body["id"])
        self.assertEqual(time_slice.workspace_id, workspace.pk)
        self.assertEqual(time_slice.project_id, self.project.pk)

    def test_time_slice_fresh_replay_key_reuse_date_code_conflict_and_rollback_are_exact(self):
        workspace, _, _, _ = self.create_complete_workspace()
        body = self.slice_body()
        raw = self.canonical_json(body)
        operation_id = uuid4()
        url = self.time_slice_url(workspace.pk)
        fresh = self.csrf_post(
            self.player_client,
            url,
            raw,
            operation_id=operation_id,
            if_match=f'"{workspace.definition_manifest_hash}"',
        )
        self.assertEqual(fresh.status_code, 201, getattr(fresh, "data", fresh.content))
        after_fresh = self.domain_fingerprint()
        with self.capture_no_domain_writes():
            replay = self.csrf_post(
                self.player_client,
                url,
                raw,
                operation_id=operation_id,
                if_match=f'"{workspace.definition_manifest_hash}"',
            )
        self.assertEqual(replay.status_code, 200, getattr(replay, "data", replay.content))
        self.assertEqual(replay.content, fresh.content)
        self.assertEqual(self.domain_fingerprint(), after_fresh)

        changed = dict(body, name="Другая подпись")
        with self.capture_no_domain_writes():
            key_reuse = self.csrf_post(
                self.player_client,
                url,
                self.canonical_json(changed),
                operation_id=operation_id,
                if_match=f'"{workspace.definition_manifest_hash}"',
            )
        self.assert_error(key_reuse, status=409, code="PLAYER_OPERATION_KEY_REUSE")
        same_date = self.slice_body(cutoff_date=body["cutoff_date"])
        with self.capture_no_domain_writes():
            identity = self.csrf_post(
                self.player_client,
                url,
                self.canonical_json(same_date),
                operation_id=uuid4(),
                if_match=f'"{workspace.definition_manifest_hash}"',
            )
        self.assert_error(identity, status=409, code="PLAYER_IDENTITY_CONFLICT")
        self.assertEqual(self.domain_fingerprint(), after_fresh)

        rollback = self.slice_body(cutoff_date="2026-02-15")
        before_rollback = self.domain_fingerprint()
        with patch.object(
            AuditEvent,
            "save",
            side_effect=RuntimeError("g7-test-audit-insert-failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "g7-test-audit-insert-failure"):
                self.csrf_post(
                    self.player_client,
                    url,
                    self.canonical_json(rollback),
                    operation_id=uuid4(),
                    if_match=f'"{workspace.definition_manifest_hash}"',
                )
        self.assertEqual(self.domain_fingerprint(), before_rollback)
        self.assertFalse(TimeSlice.objects.filter(pk=rollback["id"]).exists())

    def test_persisted_time_slice_has_no_update_delete_or_metadata_hiding_path(self):
        workspace, _, _, _ = self.create_complete_workspace()
        body = self.slice_body()
        created = self.csrf_post(
            self.player_client,
            self.time_slice_url(workspace.pk),
            self.canonical_json(body),
            operation_id=uuid4(),
            if_match=f'"{workspace.definition_manifest_hash}"',
        )
        self.assertEqual(created.status_code, 201, getattr(created, "data", created.content))
        time_slice = TimeSlice.objects.get(pk=body["id"])
        original = (
            time_slice.name,
            time_slice.metadata,
            time_slice.cutoff_date,
            time_slice.code,
        )
        time_slice.name = "Скрытая правка"
        with self.assertRaises(ValidationError):
            time_slice.save()
        with self.assertRaises(ValidationError):
            time_slice.delete()
        with self.assertRaises(ValidationError):
            TimeSlice.objects.filter(pk=time_slice.pk).update(metadata={"hidden": True})
        with self.assertRaises(ValidationError):
            TimeSlice.objects.filter(pk=time_slice.pk).delete()
        for method in ("PUT", "PATCH", "DELETE"):
            response = self.player_client.generic(
                method,
                self.time_slice_url(workspace.pk) + f"{time_slice.pk}/",
                b"{}",
                content_type="application/json",
            )
            self.assertIn(response.status_code, {404, 405})
        time_slice.refresh_from_db()
        self.assertEqual(
            (time_slice.name, time_slice.metadata, time_slice.cutoff_date, time_slice.code),
            original,
        )

    def test_experiment_list_is_dynamic_read_only_and_modeling_is_never_an_action(self):
        workspace, _, _, _ = self.create_complete_workspace()
        before = self.domain_fingerprint()
        response = self.player_get(self.player_client, self.experiments_url(workspace.pk))
        payload = self.assert_canonical_get(response, keys={"workspace_id", "experiments"})
        self.assertIsInstance(payload["experiments"], list)
        self.assertEqual(
            {row["id"] for row in payload["experiments"]},
            {
                str(row.pk)
                for row in Experiment.objects.filter(
                    workspace=workspace, experiment_type=ExperimentType.ASSESSMENT
                )
            },
        )
        self.assertTrue(
            all(
                set(row).issubset(
                    {
                        "id",
                        "name",
                        "status",
                        "order",
                        "color",
                        "type",
                        "expert_profile",
                        "assessment_set",
                    }
                )
                for row in payload["experiments"]
            )
        )
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            denied = self.player_client.generic(
                method,
                self.experiments_url(workspace.pk),
                b"{}",
                content_type="application/json",
            )
            self.assertIn(denied.status_code, {404, 405})
        self.assertEqual(self.domain_fingerprint(), before)

    def test_player_help_is_exact_versioned_sanitized_and_scope_hidden(self):
        assert_player_help_provisioning_contract(self, self.default_workspace)
        workspace, _, _, operation_id = self.create_complete_workspace()
        before = self.domain_fingerprint()
        before_help = player_help_snapshot(workspace)
        self.assertEqual(len(before_help), len(PLAYER_HELP_KEYS))
        ui_key = PLAYER_HELP_KEYS[0]
        response = self.player_get(self.player_client,
            self.help_url(
                workspace.pk,
                ui_key,
                locale=CATALOG_LOCALE,
                version=CATALOG_VERSION,
            )
        )
        payload = self.assert_canonical_get(
            response,
            keys={"workspace_id", "ui_key", "locale", "help_topic"},
        )
        assert_player_help_http_payload(self, payload, ui_key=ui_key)
        wrong_key = self.player_get(self.player_client,
            self.help_url(
                workspace.pk,
                "player.absent",
                locale=CATALOG_LOCALE,
                version=CATALOG_VERSION,
            )
        )
        wrong_version = self.player_get(self.player_client,
            self.help_url(
                workspace.pk,
                ui_key,
                locale=CATALOG_LOCALE,
                version="9.9.9",
            )
        )
        wrong_locale = self.player_get(self.player_client,
            self.help_url(
                workspace.pk,
                ui_key,
                locale="en",
                version=CATALOG_VERSION,
            )
        )
        absent_workspace = self.player_get(self.player_client,
            self.help_url(
                uuid4(), ui_key, locale=CATALOG_LOCALE, version=CATALOG_VERSION
            )
        )
        for denied in (wrong_key, wrong_version, wrong_locale, absent_workspace):
            self.assert_error(denied, status=404, code="PLAYER_NOT_FOUND")
            self.assertEqual(denied.content, wrong_key.content)
        self.assertEqual(self.domain_fingerprint(), before)

        add_valid_future_player_help_binding(self, workspace)
        after_future = self.domain_fingerprint()
        replay_body = self.workspace_body(
            workspace_id=workspace.pk,
            code=workspace.code,
            name=workspace.name,
            definition_id=workspace.definition_version_id,
            definition_manifest_hash=workspace.definition_manifest_hash,
            metadata=workspace.metadata,
        )
        with self.capture_no_domain_writes():
            replay = self.csrf_post(
                self.player_client,
                self.workspace_list_url(self.project.pk),
                self.canonical_json(replay_body),
                operation_id=operation_id,
                if_match=f'"{self.definition.manifest_hash}"',
            )
        self.assertEqual(replay.status_code, 200, getattr(replay, "data", replay.content))
        self.assertEqual(self.domain_fingerprint(), after_future)


@skipUnless(connection.vendor == "postgresql", "G7 concurrency contract is PostgreSQL-only")
class FoundationPlayerConcurrencyTests(
    _FD08ProjectionGuardTeardownMixin,
    FoundationPlayerFixture,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self) -> None:
        self.setUp_player_fixture()

    def _session_cookies(self, user, *, project_id=None) -> dict[str, str]:
        client = self.player_session(user, project_id=project_id)
        return {name: morsel.value for name, morsel in client.cookies.items()}

    @staticmethod
    def _thread_client(cookies: dict[str, str]) -> APIClient:
        client = APIClient(enforce_csrf_checks=True)
        for name, value in cookies.items():
            client.cookies[name] = value
        return client

    def _race_posts(self, requests: list[dict]) -> list[tuple[int, bytes, dict]]:
        gate = threading.Barrier(len(requests))
        outcomes: list[tuple[int, bytes, dict]] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def worker(spec: dict) -> None:
            close_old_connections()
            try:
                client = self._thread_client(spec["cookies"])
                gate.wait(timeout=20)
                response = client.generic(
                    "POST",
                    spec["url"],
                    spec["raw"],
                    content_type="application/json",
                    HTTP_IDEMPOTENCY_KEY=str(spec["operation_id"]),
                    HTTP_IF_MATCH=spec["if_match"],
                    HTTP_X_CSRFTOKEN=client.cookies[settings.CSRF_COOKIE_NAME].value,
                )
                with lock:
                    outcomes.append((response.status_code, response.content, response.json()))
            except BaseException as exc:  # exact failures are asserted by caller
                with lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(spec,)) for spec in requests]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=45)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        return outcomes

    def test_concurrent_workspace_same_key_and_competing_identity_have_one_graph_and_typed_loser(self):
        # The late UUID collision below exercises the accepted immutable model
        # path, not a mocked or API-local audit substitute.
        self.assertIs(AuditEvent.save, ImmutableCapturedModel.save)
        body = self.workspace_body()
        operation_id = uuid4()
        cookies = self._session_cookies(self.player_user)
        exact = {
            "cookies": cookies,
            "url": self.workspace_list_url(self.project.pk),
            "raw": self.canonical_json(body),
            "operation_id": operation_id,
            "if_match": f'"{self.definition.manifest_hash}"',
        }
        before = self.row_counts()
        outcomes = self._race_posts([exact, exact])
        self.assertEqual(sorted(status for status, _, _ in outcomes), [200, 201])
        self.assertEqual(outcomes[0][1], outcomes[1][1])
        self.assertEqual(ProjectWorkspace.objects.filter(pk=body["id"]).count(), 1)
        workspace = ProjectWorkspace.objects.get(pk=body["id"])
        self.assertEqual(AuditEvent.objects.filter(pk=operation_id, workspace=workspace).count(), 1)
        self.assertGreater(
            Actor.objects.filter(
                workspace=workspace, source_manifest_entity_id__isnull=False
            ).count(),
            0,
        )
        self.assertGreater(UIHelpBinding.objects.filter(workspace=workspace).count(), 0)
        self.assertEqual(self.row_counts()[0], before[0] + 1)

        competing_id = uuid4()
        competing_body = self.workspace_body(workspace_id=competing_id)
        first = {
            **exact,
            "raw": self.canonical_json(competing_body),
            "operation_id": uuid4(),
        }
        second = {**first, "operation_id": uuid4()}
        before_competing = self.row_counts()
        competing = self._race_posts([first, second])
        self.assertEqual(sorted(status for status, _, _ in competing), [201, 409])
        loser = next(payload for status, _, payload in competing if status == 409)
        self.assertEqual(set(loser), {"code", "errors"})
        self.assertEqual(loser["code"], "PLAYER_IDENTITY_CONFLICT")
        self.assertEqual(ProjectWorkspace.objects.filter(pk=competing_id).count(), 1)
        self.assertEqual(self.row_counts()[0], before_competing[0] + 1)
        self.assertEqual(self.row_counts()[2], before_competing[2] + 1)

        other_project, other_definition, _ = self.make_other_project()
        other_user = self.make_player_user(project=other_project, suffix="cross-project")
        other_cookies = self._session_cookies(
            other_user, project_id=other_project.pk
        )
        other_body = {
            **self.workspace_body(),
            "definition_id": str(other_definition.pk),
            "definition_manifest_hash": other_definition.manifest_hash,
        }
        shared_operation = uuid4()
        primary_body = self.workspace_body()
        before_cross = self.row_counts()
        primary_before_cross = self.project_domain_fingerprint(self.project)
        other_before_cross = self.project_domain_fingerprint(other_project)
        inherited_save = AuditEvent.save
        self.assertIs(inherited_save, ImmutableCapturedModel.save)
        audit_save_gate = threading.Barrier(2)
        audit_save_calls: list[tuple[object, object, object]] = []
        audit_save_lock = threading.Lock()

        def gated_inherited_audit_save(event, *args, **kwargs):
            # This wrapper deliberately delegates to the real inherited save;
            # it only proves both independent Project lanes reached the exact
            # immutable AuditEvent insert before either one can win the UUID.
            if event._state.adding and event.pk == shared_operation:
                with audit_save_lock:
                    audit_save_calls.append(
                        (event.pk, event.project_id, event.workspace_id)
                    )
                audit_save_gate.wait(timeout=30)
            return inherited_save(event, *args, **kwargs)

        cross_specs = [
            {
                "cookies": cookies,
                "url": self.workspace_list_url(self.project.pk),
                "raw": self.canonical_json(primary_body),
                "operation_id": shared_operation,
                "if_match": f'"{self.definition.manifest_hash}"',
            },
            {
                "cookies": other_cookies,
                "url": self.workspace_list_url(other_project.pk),
                "raw": self.canonical_json(other_body),
                "operation_id": shared_operation,
                "if_match": f'"{other_definition.manifest_hash}"',
            },
        ]
        with patch.object(AuditEvent, "save", gated_inherited_audit_save):
            cross = self._race_posts(cross_specs)
        self.assertIs(AuditEvent.save, inherited_save)
        self.assertEqual(len(audit_save_calls), 2)
        self.assertEqual(
            {project_id for _, project_id, _ in audit_save_calls},
            {self.project.pk, other_project.pk},
        )
        self.assertEqual(sorted(status for status, _, _ in cross), [201, 409])
        cross_winner = next(payload for status, _, payload in cross if status == 201)
        cross_loser = next(payload for status, _, payload in cross if status == 409)
        self.assertEqual(cross_loser["code"], "PLAYER_OPERATION_KEY_REUSE")
        self.assertEqual(AuditEvent.objects.filter(pk=shared_operation).count(), 1)
        self.assertEqual(self.row_counts()[0], before_cross[0] + 1)
        self.assertEqual(self.row_counts()[2], before_cross[2] + 1)
        if cross_winner["project_id"] == str(self.project.pk):
            self.assertEqual(
                self.project_domain_fingerprint(other_project), other_before_cross
            )
        else:
            self.assertEqual(
                self.project_domain_fingerprint(self.project), primary_before_cross
            )

    def test_concurrent_time_slice_same_key_and_competing_date_have_one_slice_and_typed_loser(self):
        workspace, _, _, _ = self.create_complete_workspace()
        body = self.slice_body()
        operation_id = uuid4()
        cookies = self._session_cookies(self.player_user)
        exact = {
            "cookies": cookies,
            "url": self.time_slice_url(workspace.pk),
            "raw": self.canonical_json(body),
            "operation_id": operation_id,
            "if_match": f'"{workspace.definition_manifest_hash}"',
        }
        outcomes = self._race_posts([exact, exact])
        self.assertEqual(sorted(status for status, _, _ in outcomes), [200, 201])
        self.assertEqual(outcomes[0][1], outcomes[1][1])
        self.assertEqual(TimeSlice.objects.filter(pk=body["id"]).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(pk=operation_id, workspace=workspace).count(), 1)

        # The first exact-key race consumed 2026-01-15.  Race a distinct
        # date here so this asserts the competing-identity path rather than
        # two pre-existing-date rejections.
        same_date = self.slice_body(cutoff_date="2026-02-15")
        competitor = {**exact, "raw": self.canonical_json(same_date), "operation_id": uuid4()}
        winner = {**competitor, "operation_id": uuid4()}
        before_competitor = self.row_counts()
        outcomes = self._race_posts([winner, competitor])
        self.assertEqual(sorted(status for status, _, _ in outcomes), [201, 409])
        loser = next(payload for status, _, payload in outcomes if status == 409)
        self.assertEqual(loser["code"], "PLAYER_IDENTITY_CONFLICT")
        self.assertEqual(TimeSlice.objects.filter(workspace=workspace, cutoff_date=date(2026, 2, 15)).count(), 1)
        self.assertEqual(self.row_counts()[1], before_competitor[1] + 1)
        self.assertEqual(self.row_counts()[2], before_competitor[2] + 1)
