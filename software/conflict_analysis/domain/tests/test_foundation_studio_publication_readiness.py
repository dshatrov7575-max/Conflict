from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import timedelta
from uuid import UUID, uuid4
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.contrib.auth.models import Group, Permission
from django.contrib.sessions.models import Session
from django.db import connection, models
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from django.utils import timezone
from rest_framework.exceptions import NotAuthenticated
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
    _canonical_studio_write,
)
from domain.policies import (
    bootstrap_initial_project_definition,
    publish_project_definition,
    validate_project_definition,
)
from domain.services.project_definitions import (
    _publication_readiness_validation_result_valid,
    clone_project_definition_draft,
    create_project_definition_draft,
    hash_project_definition_manifest_v1,
    publication_readiness_snapshot,
)
from domain.tests.test_foundation_studio_bootstrap import (
    FoundationStudioBootstrapMixin,
)


_READINESS_KEYS = {
    "contract",
    "contract_version",
    "snapshot_scope",
    "project_id",
    "definition_id",
    "manifest_hash",
    "publication_status",
    "validation_result_valid",
    "supersedes_id",
    "project_publication_count",
    "project_workspace_count",
    "initial_publication_receipt_count",
    "current_definition_id",
    "current_definition_publication_status",
    "candidate_kind",
    "required_next_action",
    "blocker_codes",
    "readiness_sha256",
}
_READINESS_INVALID = {
    "code": "PUBLICATION_READINESS_REQUEST_INVALID",
    "errors": [
        "Publication readiness requires an empty query and no operation headers."
    ],
}
_NOT_FOUND = {
    "code": "STUDIO_RESOURCE_NOT_FOUND",
    "errors": ["Resource not found."],
}


def _canonical_json_bytes(value: object, *, terminal_lf: bool = False) -> bytes:
    body = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return body + (b"\n" if terminal_lf else b"")


def _database_fingerprint() -> str:
    snapshot: dict[str, object] = {}
    with connection.cursor() as cursor:
        for table in sorted(connection.introspection.table_names(cursor)):
            cursor.execute(f"SELECT * FROM {connection.ops.quote_name(table)}")
            columns = [item[0] for item in cursor.description or ()]
            rows = sorted(repr(tuple(row)) for row in cursor.fetchall())
            snapshot[table] = {"columns": columns, "rows": rows}
    return hashlib.sha256(_canonical_json_bytes(snapshot)).hexdigest()


class _PoisonWSGIInput:
    def __init__(self) -> None:
        self.read_attempts = 0

    def read(self, size: int = -1) -> bytes:
        self.read_attempts += 1
        raise AssertionError("publication readiness must not read a request body")

    def readline(self, size: int = -1) -> bytes:
        self.read_attempts += 1
        raise AssertionError("publication readiness must not read a request body")


class FoundationStudioPublicationReadinessTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()
        self._sequence = 0
        self.permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
            )
        }
        self.viewer_user = self._make_user(
            "fd07-viewer",
            ("studio_read_definition",),
        )
        self.editor_user = self._make_user(
            "fd07-editor",
            (
                "studio_read_definition",
                "studio_create_definition_draft",
                "studio_clone_definition_draft",
                "studio_save_definition_draft",
            ),
        )
        self.publisher_user = self._make_user(
            "fd07-publisher",
            (
                "studio_read_definition",
                "studio_validate_definition",
                "studio_publish_definition",
            ),
        )
        self.no_capability_user = self._make_user("fd07-no-capability", ())
        self.out_of_scope_user = self._make_user(
            "fd07-out-of-scope",
            ("studio_read_definition",),
            scoped=False,
        )
        self.client = self._client_for(self.viewer_user)

    def _next(self, label: str) -> tuple[str, str]:
        self._sequence += 1
        bounded = label.upper().replace("_", "-")[:28]
        return f"FD07-{bounded}-{self._sequence}", f"{self._sequence}.0.0"

    def _make_user(
        self,
        username: str,
        codenames: tuple[str, ...],
        *,
        scoped: bool = True,
    ):
        user = get_user_model().objects.create_user(
            username=username,
            password="test-password",
        )
        user.user_permissions.add(*(self.permissions[name] for name in codenames))
        if scoped:
            self._scope(self.project, user)
        return user

    @staticmethod
    def _client_for(user) -> APIClient:
        client = APIClient(enforce_csrf_checks=True)
        client.force_authenticate(user)
        return client

    @staticmethod
    def _scope(project: Project, *users) -> Group:
        group, _ = Group.objects.get_or_create(
            name=project_access_group_name(project.pk)
        )
        group.user_set.add(*users)
        return group

    @staticmethod
    def _url(definition: ProjectDefinitionVersion | UUID) -> str:
        definition_id = definition.pk if hasattr(definition, "pk") else definition
        return (
            f"/api/foundation/definitions/{definition_id}/"
            "publication-readiness/"
        )

    def _manifest_for(self, project: Project) -> dict:
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
        return manifest

    def _project(self, label: str) -> Project:
        code, _ = self._next(label)
        return Project.objects.create(
            id=uuid4(),
            code=code,
            version="1.0.0",
            name=f"{label} project",
            description=f"{label} project topology",
            metadata={"fd07": label},
            primary_language_tag="ru",
            primary_language_assignment="EXPLICIT",
        )

    def _draft(
        self,
        label: str,
        *,
        project: Project | None = None,
    ) -> ProjectDefinitionVersion:
        selected_project = self.project if project is None else project
        code, version = self._next(label)
        return create_project_definition_draft(
            project=selected_project,
            code=code,
            version=version,
            manifest=self._manifest_for(selected_project),
            principal=self.editor(actor=f"{label}-editor"),
        )

    def _definition(
        self,
        label: str,
        *,
        status: str,
        project: Project | None = None,
        supersedes: ProjectDefinitionVersion | None = None,
        is_current: bool = False,
        typed: bool = True,
        definition_id: UUID | None = None,
    ) -> ProjectDefinitionVersion:
        selected_project = self.project if project is None else project
        code, version = self._next(label)
        manifest = (
            self._manifest_for(selected_project)
            if typed
            else {
                "legacy_contract": "foundation-v4",
                "project_id": str(selected_project.pk),
                "label": label,
            }
        )
        manifest_hash = (
            hash_project_definition_manifest_v1(
                manifest,
                project=selected_project,
            )
            if typed
            else hashlib.sha256(_canonical_json_bytes(manifest)).hexdigest()
        )
        lifecycle: dict[str, object] = {}
        if status in {
            PublicationStatus.VALIDATED,
            PublicationStatus.PUBLISHED,
            PublicationStatus.RETIRED,
        }:
            lifecycle.update(
                validated_at=timezone.now(),
                validated_by=f"validator:{label}",
                validation_result={"valid": True, "source": label},
            )
        if status in {PublicationStatus.PUBLISHED, PublicationStatus.RETIRED}:
            lifecycle.update(
                published_at=timezone.now(),
                published_by=f"publisher:{label}",
            )
        definition = ProjectDefinitionVersion(
            id=definition_id or uuid4(),
            project=selected_project,
            code=code,
            version=version,
            is_current=is_current,
            publication_status=status,
            manifest=manifest,
            manifest_hash=manifest_hash,
            schema_version="1.0.0",
            semantic_version="1.0.0",
            construct_version="1.0.0",
            supersedes=supersedes,
            **lifecycle,
        )
        if typed:
            with _canonical_studio_write("definition"):
                definition.save(force_insert=True)
        else:
            definition.save(force_insert=True)
        return definition

    def _workspace(
        self,
        definition: ProjectDefinitionVersion,
        label: str,
        *,
        is_default: bool = False,
    ) -> ProjectWorkspace:
        code, version = self._next(label)
        workspace = ProjectWorkspace(
            project=definition.project,
            definition_version=definition,
            definition_manifest_hash=definition.manifest_hash,
            code=code,
            version=version,
            name=f"{label} workspace",
            is_default=is_default,
            metadata={"fd07": label},
        )
        workspace.save(force_insert=True)
        return workspace

    def _publication(
        self,
        definition: ProjectDefinitionVersion,
        label: str,
        *,
        initial_workspace: ProjectWorkspace | None = None,
        locale: str = "en",
    ) -> ProjectPublication:
        code, version = self._next(label)
        publication = ProjectPublication(
            project=definition.project,
            definition_version=definition,
            initial_workspace=initial_workspace,
            code=code,
            version=version,
            locale=locale,
            actor_identifier=f"actor:{label}",
            validation_result={"valid": True, "source": label},
            published_at=timezone.now(),
        )
        publication.save(force_insert=True)
        return publication

    def _initial(self, label: str = "initial"):
        definition = self._draft(f"{label}-definition")
        code, version = self._next(f"{label}-workspace")
        return bootstrap_initial_project_definition(
            definition=definition,
            principal=self.publisher(actor=f"{label}-publisher"),
            actor_identifier=f"{label}-publisher",
            workspace_spec={
                "id": str(uuid4()),
                "code": code,
                "version": version,
                "name": f"{label} initial workspace",
                "is_default": True,
                "metadata": {"fd07": label},
            },
            locale="en",
            publication_code=self._next(f"{label}-publication")[0],
        )

    def _successor(
        self,
        predecessor: ProjectDefinitionVersion,
        label: str,
        *,
        validate: bool = False,
        publish: bool = False,
    ) -> ProjectDefinitionVersion:
        code, version = self._next(label)
        successor = clone_project_definition_draft(
            predecessor,
            code=code,
            version=version,
            principal=self.editor(actor=f"{label}-editor"),
        )
        if validate or publish:
            successor = validate_project_definition(
                successor,
                actor_identifier=f"{label}-publisher",
                principal=self.publisher(actor=f"{label}-publisher"),
            )
        if publish:
            publication = publish_project_definition(
                successor,
                actor_identifier=f"{label}-publisher",
                principal=self.publisher(actor=f"{label}-publisher"),
                locale="en",
                publication_code=self._next(f"{label}-publication")[0],
            )
            successor = publication.definition_version
        return successor

    def _binding(self, workspace: ProjectWorkspace, label: str) -> UIHelpBinding:
        code, _ = self._next(label)
        binding = UIHelpBinding(
            workspace=workspace,
            application_scope=self.topic.application_scope,
            code=code,
            version=self.topic.version,
            ui_key=f"fd07.{label.lower()}.{self._sequence}",
            locale=self.topic.locale,
            help_topic=self.topic,
        )
        binding.save(force_insert=True)
        return binding

    @staticmethod
    def _persist_corrupt_initial_workspace(
        publication: ProjectPublication,
        workspace: ProjectWorkspace | None,
    ) -> None:
        publication.initial_workspace = workspace
        models.Model.save(
            publication,
            update_fields=("initial_workspace",),
        )

    @staticmethod
    def _persist_corrupt_manifest_state(
        definition: ProjectDefinitionVersion,
        *,
        manifest: dict,
        manifest_hash: str,
    ) -> None:
        definition.manifest = manifest
        definition.manifest_hash = manifest_hash
        models.Model.save(
            definition,
            update_fields=(
                "manifest",
                "manifest_hash",
            )
        )

    @staticmethod
    def _persist_corrupt_publication_definition(
        publication: ProjectPublication,
        definition: ProjectDefinitionVersion,
    ) -> None:
        publication.definition_version = definition
        models.Model.save(
            publication,
            update_fields=("definition_version",),
        )

    def _get(
        self,
        definition: ProjectDefinitionVersion,
        *,
        user=None,
        **headers,
    ):
        client = self.client if user is None else self._client_for(user)
        return client.get(self._url(definition), **headers)

    def _payload(
        self,
        definition: ProjectDefinitionVersion,
        *,
        user=None,
    ) -> dict[str, object]:
        response = self._get(definition, user=user)
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(set(payload), _READINESS_KEYS)
        return payload

    def _assert_candidate(
        self,
        payload: dict[str, object],
        *,
        kind: str,
        action: str,
        blockers: list[str],
    ) -> None:
        self.assertEqual(payload["candidate_kind"], kind)
        self.assertEqual(payload["required_next_action"], action)
        self.assertEqual(payload["blocker_codes"], blockers)

    def _assert_stable_one_statement_snapshot(
        self,
        definition: ProjectDefinitionVersion,
        *,
        kind: str,
        action: str,
        blockers: list[str],
        stored_manifest_hash: str,
        not_disclosed: tuple[object, ...] = (),
    ) -> dict[str, object]:
        snapshots: list[dict[str, object]] = []
        statements: list[str] = []

        def capture_service_snapshot(*, definition_id, scoped_project_id):
            self.assertEqual(definition_id, definition.pk)
            self.assertEqual(scoped_project_id, definition.project_id)
            with CaptureQueriesContext(connection) as captured:
                snapshot = publication_readiness_snapshot(
                    definition_id=definition_id,
                    scoped_project_id=scoped_project_id,
                )
            self.assertEqual(len(captured), 1, captured.captured_queries)
            statement = captured[0]["sql"]
            normalized = " ".join(
                statement.replace('"', "").replace("`", "").split()
            ).upper()
            self.assertTrue(statement.lstrip().startswith("SELECT"), statement)
            self.assertNotIn("FOR UPDATE", normalized)

            project_table = Project._meta.db_table.upper()
            definition_table = ProjectDefinitionVersion._meta.db_table.upper()
            publication_table = ProjectPublication._meta.db_table.upper()
            workspace_table = ProjectWorkspace._meta.db_table.upper()
            self.assertIn(f"JOIN {project_table}", normalized)
            self.assertIn(definition_table, normalized)
            self.assertGreaterEqual(normalized.count("COUNT("), 5)
            self.assertGreaterEqual(normalized.count(publication_table), 4)
            self.assertIn(workspace_table, normalized)

            for field_name in ("manifest", "manifest_hash"):
                column = (
                    ProjectDefinitionVersion._meta.get_field(field_name).column
                ).upper()
                self.assertIn(f".{column}", normalized)

            target_definition_column = (
                ProjectPublication._meta.get_field(
                    "definition_version"
                ).column
            ).upper()
            self.assertIn(f".{target_definition_column}", normalized)

            current_column = ProjectDefinitionVersion._meta.get_field(
                "is_current"
            ).column.upper()
            project_id_column = ProjectDefinitionVersion._meta.get_field(
                "project"
            ).column.upper()
            id_column = ProjectDefinitionVersion._meta.get_field(
                "id"
            ).column.upper()
            status_column = ProjectDefinitionVersion._meta.get_field(
                "publication_status"
            ).column.upper()
            select_clauses = normalized.split("SELECT ")[1:]
            aggregate_clauses = []
            for clause in select_clauses:
                projection, separator, source = clause.partition(" FROM ")
                if separator and "COUNT(" in projection:
                    aggregate_clauses.append((projection, source))
            self.assertGreaterEqual(len(aggregate_clauses), 5)
            for projection, _source in aggregate_clauses:
                self.assertNotIn(" ORDER BY ", projection)

            # Only the two deterministic current-definition scalar subqueries
            # retain ordering. Every aggregate subquery explicitly clears it.
            self.assertEqual(normalized.count(" ORDER BY "), 2, normalized)
            order_fragments = normalized.split(" ORDER BY ")[1:]
            self.assertEqual(len(order_fragments), 2)
            for order_fragment in order_fragments:
                self.assertIn(" ASC LIMIT 1", order_fragment)
                ordered_column = order_fragment.split(" ASC LIMIT 1", 1)[0]
                self.assertTrue(
                    ordered_column.endswith(f".{id_column}")
                    or ordered_column == "1",
                    order_fragment,
                )

            def has_current_scalar_subquery(projected_column: str) -> bool:
                for clause in select_clauses:
                    projection, separator, source = clause.partition(" FROM ")
                    if not separator or "COUNT(" in projection:
                        continue
                    if f".{projected_column}" not in projection:
                        continue
                    if (
                        definition_table in source
                        and f".{current_column}" in source
                        and f".{project_id_column}" in source
                        and "LIMIT 1" in source
                    ):
                        return True
                return False

            self.assertTrue(
                has_current_scalar_subquery(id_column),
                normalized,
            )
            self.assertTrue(
                has_current_scalar_subquery(status_column),
                normalized,
            )
            snapshots.append(snapshot)
            statements.append(normalized)
            return snapshot

        zero_write_baseline = _database_fingerprint()
        role_clients = [
            self._client_for(user)
            for user in (
                self.viewer_user,
                self.editor_user,
                self.publisher_user,
            )
        ]
        incoming_cookie_jars = [
            client.cookies.output(header="Cookie:", sep="\r\n")
            for client in role_clients
        ]
        with patch(
            "domain.api.studio_definitions.publication_readiness_snapshot",
            side_effect=capture_service_snapshot,
        ):
            responses = [
                client.get(self._url(definition))
                for client in role_clients
            ]

        self.assertEqual(len(snapshots), len(role_clients))
        self.assertEqual(len(statements), len(role_clients))
        first = snapshots[0]
        for repeated in snapshots[1:]:
            self.assertEqual(repeated, first)
        self.assertEqual(set(first), _READINESS_KEYS)
        for internal_key in (
            "target_publication_count",
            "valid_initial_publication_receipt_count",
            "publication_id",
            "publication_locale",
            "publication_actor_identifier",
            "publication_initial_workspace_id",
        ):
            self.assertNotIn(internal_key, first)
        self.assertEqual(first["manifest_hash"], stored_manifest_hash)
        for count_key in (
            "project_publication_count",
            "project_workspace_count",
            "initial_publication_receipt_count",
        ):
            self.assertIs(type(first[count_key]), int)
        self._assert_candidate(
            first,
            kind=kind,
            action=action,
            blockers=blockers,
        )
        core = dict(first)
        readiness_hash = core.pop("readiness_sha256")
        self.assertEqual(
            readiness_hash,
            hashlib.sha256(_canonical_json_bytes(core)).hexdigest(),
        )

        expected_bytes = _canonical_json_bytes(first, terminal_lf=True)
        for forbidden_value in not_disclosed:
            self.assertNotIn(str(forbidden_value).encode("utf-8"), expected_bytes)
        for client, incoming_cookie_jar, response in zip(
            role_clients,
            incoming_cookie_jars,
            responses,
            strict=True,
        ):
            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(response.content, expected_bytes)
            self.assertEqual(response["ETag"], f'"{readiness_hash}"')
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response["Vary"], "Cookie, Authorization")
            self.assertFalse(response.cookies)
            self.assertEqual(response.cookies.output(), "")
            self.assertNotIn("Set-Cookie", response.headers)
            self.assertIs(
                response.wsgi_request.META["CSRF_COOKIE_NEEDS_UPDATE"],
                False,
            )
            self.assertEqual(
                client.cookies.output(header="Cookie:", sep="\r\n"),
                incoming_cookie_jar,
            )
        self.assertEqual(
            {response.content for response in responses},
            {expected_bytes},
        )
        denied_client = self._client_for(self.no_capability_user)
        denied_cookie_jar = denied_client.cookies.output(
            header="Cookie:",
            sep="\r\n",
        )
        with patch(
            "domain.api.studio_definitions.publication_readiness_snapshot",
            side_effect=AssertionError("capability denial must precede FD07 service"),
        ) as denied_service:
            denied = denied_client.get(self._url(definition))
        denied_service.assert_not_called()
        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertEqual(denied.json()["code"], "STUDIO_CAPABILITY_DENIED")
        self.assertEqual(denied["Cache-Control"], "no-store")
        self.assertEqual(denied["Vary"], "Cookie, Authorization")
        self.assertFalse(denied.cookies)
        self.assertNotIn("Set-Cookie", denied.headers)
        self.assertIs(
            denied.wsgi_request.META["CSRF_COOKIE_NEEDS_UPDATE"],
            False,
        )
        self.assertEqual(
            denied_client.cookies.output(header="Cookie:", sep="\r\n"),
            denied_cookie_jar,
        )
        self.assertEqual(_database_fingerprint(), zero_write_baseline)
        return first

    def _topology_eligibility_vectors(
        self,
        label: str,
        *,
        supersedes: ProjectDefinitionVersion | None,
    ) -> tuple[
        list[
            tuple[
                str,
                ProjectDefinitionVersion,
                str,
                tuple[object, ...],
            ]
        ],
        ProjectDefinitionVersion,
        tuple[object, ...],
    ]:
        unsupported: list[
            tuple[
                str,
                ProjectDefinitionVersion,
                str,
                tuple[object, ...],
            ]
        ] = []

        legacy = self._definition(
            f"{label}-non-typed",
            status=PublicationStatus.DRAFT,
            supersedes=supersedes,
            typed=False,
        )
        unsupported.append(
            ("non-typed", legacy, legacy.manifest_hash, (legacy.code,))
        )

        for vector_name in (
            "blank-hash",
            "non-lower-hash",
            "noncanonical-hash",
            "mismatched-hash",
        ):
            definition = self._definition(
                f"{label}-{vector_name}",
                status=PublicationStatus.DRAFT,
                supersedes=supersedes,
            )
            canonical_hash = definition.manifest_hash
            if vector_name == "blank-hash":
                stored_hash = ""
            elif vector_name == "non-lower-hash":
                stored_hash = canonical_hash.upper()
                self.assertNotEqual(stored_hash, canonical_hash)
            elif vector_name == "noncanonical-hash":
                stored_hash = "g" * 64
            else:
                stored_hash = "0" * 64
                self.assertNotEqual(stored_hash, canonical_hash)
            self._persist_corrupt_manifest_state(
                definition,
                manifest=copy.deepcopy(definition.manifest),
                manifest_hash=stored_hash,
            )
            unsupported.append(
                (vector_name, definition, stored_hash, (definition.code,))
            )

        stale = self._definition(
            f"{label}-stale-hash",
            status=PublicationStatus.DRAFT,
            supersedes=supersedes,
        )
        stale_hash = stale.manifest_hash
        stale_manifest = copy.deepcopy(stale.manifest)
        stale_description = f"Persisted manifest changed after {label} hash"
        stale_manifest["project"]["description"] = stale_description
        self.assertNotEqual(
            hash_project_definition_manifest_v1(
                stale_manifest,
                project=self.project,
            ),
            stale_hash,
        )
        self._persist_corrupt_manifest_state(
            stale,
            manifest=stale_manifest,
            manifest_hash=stale_hash,
        )
        unsupported.append(
            (
                "stale-hash",
                stale,
                stale_hash,
                (stale.code, stale_description),
            )
        )

        mismatch_values = {
            "project-id-mismatch": str(uuid4()),
            "project-code-mismatch": "FD07-MISMATCHED-PROJECT",
            "project-version-mismatch": "9.9.9",
        }
        mismatch_fields = {
            "project-id-mismatch": "id",
            "project-code-mismatch": "code",
            "project-version-mismatch": "version",
        }
        for vector_name, mismatch_value in mismatch_values.items():
            definition = self._definition(
                f"{label}-{vector_name}",
                status=PublicationStatus.DRAFT,
                supersedes=supersedes,
            )
            mismatched_manifest = copy.deepcopy(definition.manifest)
            mismatched_manifest["project"][
                mismatch_fields[vector_name]
            ] = mismatch_value
            self_consistent_unbound_hash = hash_project_definition_manifest_v1(
                mismatched_manifest
            )
            self._persist_corrupt_manifest_state(
                definition,
                manifest=mismatched_manifest,
                manifest_hash=self_consistent_unbound_hash,
            )
            unsupported.append(
                (
                    vector_name,
                    definition,
                    self_consistent_unbound_hash,
                    (definition.code, mismatch_value),
                )
            )

        semantic = self._definition(
            f"{label}-semantic-diagnostic",
            status=PublicationStatus.DRAFT,
            supersedes=supersedes,
        )
        semantic_manifest = copy.deepcopy(semantic.manifest)
        broken_parent_id = str(uuid4())
        semantic_manifest["actors"][1]["parent_id"] = broken_parent_id
        semantic_hash = hash_project_definition_manifest_v1(
            semantic_manifest,
            project=self.project,
        )
        self._persist_corrupt_manifest_state(
            semantic,
            manifest=semantic_manifest,
            manifest_hash=semantic_hash,
        )
        return unsupported, semantic, (semantic.code, broken_parent_id)

    def _fd06_successor_post(self, definition, *, user):
        client = self._client_for(user)
        operation_id = uuid4()
        response = client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-successor/",
            {"locale": "en"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
        )
        return operation_id, response

    def test_route_method_auth_scope_query_headers_and_zero_write_are_exact(self):
        definition = self._draft("admission")
        url = self._url(definition)
        self.assertEqual(
            resolve(url).url_name,
            "foundation-definition-publication-readiness",
        )

        missing_auth = {
            "detail": str(NotAuthenticated.default_detail),
        }
        missing_auth_body = _canonical_json_bytes(missing_auth)
        capability_denial = {
            "code": "STUDIO_CAPABILITY_DENIED",
            "errors": [
                "The authenticated principal lacks the required Studio capability."
            ],
        }

        def cookie_jar_bytes(client: APIClient) -> bytes:
            return client.cookies.output(
                header="Cookie:",
                sep="\r\n",
            ).encode("latin-1")

        def guarded_request(operation):
            guards = (
                (
                    "domain.api.studio_definitions.get_token",
                    "FD07 must not request a CSRF token",
                ),
                (
                    "rest_framework.request.Request._load_data_and_files",
                    "FD07 must not materialize a parser",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.save",
                    "FD07 must not save a session",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.delete",
                    "FD07 must not delete a session",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.flush",
                    "FD07 must not flush a session",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.cycle_key",
                    "FD07 must not rotate a session",
                ),
            )
            active = []
            try:
                for target, message in guards:
                    patcher = patch(target, side_effect=AssertionError(message))
                    patcher.start()
                    active.append(patcher)
                return operation()
            finally:
                for patcher in reversed(active):
                    patcher.stop()

        def assert_fd07_transport(
            response,
            client: APIClient,
            incoming_cookie_jar: bytes,
            *,
            status: int,
            body: bytes,
            fingerprint: str | None,
            outer_method_gate: bool = False,
            www_authenticate: str | None = None,
        ) -> None:
            self.assertEqual(response.status_code, status, response.content)
            self.assertEqual(response.content, body)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response["Vary"], "Cookie, Authorization")
            self.assertFalse(response.cookies)
            self.assertEqual(response.cookies.output(), "")
            self.assertNotIn("Set-Cookie", response.headers)
            self.assertIn(
                "CSRF_COOKIE_NEEDS_UPDATE",
                response.wsgi_request.META,
            )
            self.assertIs(
                response.wsgi_request.META["CSRF_COOKIE_NEEDS_UPDATE"],
                False,
            )
            self.assertEqual(cookie_jar_bytes(client), incoming_cookie_jar)
            self.assertEqual(
                response.headers.get("Content-Length"),
                str(len(body)),
            )
            self.assertEqual(
                response.headers.get("WWW-Authenticate"),
                www_authenticate,
            )
            if outer_method_gate:
                self.assertEqual(response.headers.get("Allow"), "GET")
            else:
                self.assertEqual(
                    {
                        item.strip()
                        for item in response.headers.get("Allow", "").split(",")
                        if item.strip()
                    },
                    {"GET", "OPTIONS"},
                )
            if fingerprint is not None:
                self.assertEqual(_database_fingerprint(), fingerprint)

        baseline = _database_fingerprint()
        method_client = APIClient(enforce_csrf_checks=True)
        method_client.cookies[settings.SESSION_COOKIE_NAME] = "outer-invalid-session"
        method_client.cookies[settings.CSRF_COOKIE_NAME] = "outer-invalid-csrf"
        with patch(
            "domain.api.studio_definitions._ReadOnlyBasicAuthentication.authenticate",
            side_effect=AssertionError("method gate must precede authentication"),
        ) as basic_auth, patch(
            "domain.api.studio_definitions._RawJSONSessionAuthentication.authenticate",
            side_effect=AssertionError("method gate must precede session authentication"),
        ) as session_auth, patch(
            "domain.api.studio_definitions.publication_readiness_snapshot",
            side_effect=AssertionError("method gate must precede the service"),
        ) as service:
            for method in (
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "HEAD",
                "OPTIONS",
                "TRACE",
                "CONNECT",
            ):
                with self.subTest(method=method):
                    poison = _PoisonWSGIInput()
                    incoming_cookie_jar = cookie_jar_bytes(method_client)
                    response = guarded_request(
                        lambda: method_client.request(
                            PATH_INFO=url,
                            REQUEST_METHOD=method,
                            CONTENT_TYPE="application/json",
                            CONTENT_LENGTH="64",
                            **{"wsgi.input": poison},
                        )
                    )
                    self.assertEqual(poison.read_attempts, 0)
                    assert_fd07_transport(
                        response,
                        method_client,
                        incoming_cookie_jar,
                        status=405,
                        body=b"",
                        fingerprint=baseline,
                        outer_method_gate=True,
                    )
            basic_auth.assert_not_called()
            session_auth.assert_not_called()
            service.assert_not_called()

        unauthenticated = APIClient(enforce_csrf_checks=True)
        with patch(
            "domain.api.studio_definitions.publication_readiness_snapshot"
        ) as service:
            missing_cookie_jar = cookie_jar_bytes(unauthenticated)
            missing_auth_response = guarded_request(lambda: unauthenticated.get(url))
            assert_fd07_transport(
                missing_auth_response,
                unauthenticated,
                missing_cookie_jar,
                status=401,
                body=missing_auth_body,
                fingerprint=baseline,
                www_authenticate='Basic realm="api"',
            )
            self.assertEqual(missing_auth_response.json(), missing_auth)
            self.assertFalse(
                missing_auth_response.wsgi_request.user.is_authenticated
            )

            no_capability_client = self._client_for(self.no_capability_user)
            no_capability_cookie_jar = cookie_jar_bytes(no_capability_client)
            no_capability = guarded_request(
                lambda: no_capability_client.get(
                    f"{url}?forbidden=1",
                    HTTP_IDEMPOTENCY_KEY=str(uuid4()),
                )
            )
            assert_fd07_transport(
                no_capability,
                no_capability_client,
                no_capability_cookie_jar,
                status=403,
                body=_canonical_json_bytes(capability_denial),
                fingerprint=baseline,
            )
            self.assertEqual(no_capability.json(), capability_denial)

            absent_cookie_jar = cookie_jar_bytes(self.client)
            absent = guarded_request(
                lambda: self.client.get(self._url(uuid4()))
            )
            assert_fd07_transport(
                absent,
                self.client,
                absent_cookie_jar,
                status=404,
                body=_canonical_json_bytes(_NOT_FOUND),
                fingerprint=baseline,
            )
            self.assertEqual(absent.json(), _NOT_FOUND)
            service.assert_not_called()

        invalid_vectors = [
            (f"{url}?forbidden=1", {}),
            (url, {"HTTP_IDEMPOTENCY_KEY": str(uuid4())}),
            (url, {"HTTP_IF_MATCH": f'"{definition.manifest_hash}"'}),
        ]
        invalid_vectors.extend(
            (url, {header: "forbidden"})
            for header in (
                "HTTP_X_ACTOR",
                "HTTP_X_ACTOR_IDENTIFIER",
                "HTTP_X_ACTOR_TYPE",
                "HTTP_X_AUDIT_CONTEXT",
                "HTTP_X_CAPABILITIES",
                "HTTP_X_EXPECTED_MANIFEST_HASH",
                "HTTP_X_PROJECT_ID",
                "HTTP_X_SERVICE_CONTEXT",
                "HTTP_X_SERVICE_PURPOSE",
                "HTTP_X_STUDIO_CAPABILITY",
                "HTTP_X_STUDIO_CAPABILITIES",
                "HTTP_X_STUDIO_ROLE",
            )
        )
        invalid_body = _canonical_json_bytes(_READINESS_INVALID)
        with patch(
            "domain.api.studio_definitions.publication_readiness_snapshot"
        ) as service:
            for invalid_url, headers in invalid_vectors:
                with self.subTest(url=invalid_url, headers=tuple(headers)):
                    incoming_cookie_jar = cookie_jar_bytes(self.client)
                    response = guarded_request(
                        lambda invalid_url=invalid_url, headers=headers: self.client.get(
                            invalid_url,
                            **headers,
                        )
                    )
                    assert_fd07_transport(
                        response,
                        self.client,
                        incoming_cookie_jar,
                        status=400,
                        body=invalid_body,
                        fingerprint=baseline,
                    )
                    self.assertEqual(response.json(), _READINESS_INVALID)
            service.assert_not_called()

        permitted_cookie_jar = cookie_jar_bytes(self.client)
        permitted = guarded_request(lambda: self._get(definition))
        permitted_payload = permitted.json()
        permitted_body = _canonical_json_bytes(
            permitted_payload,
            terminal_lf=True,
        )
        assert_fd07_transport(
            permitted,
            self.client,
            permitted_cookie_jar,
            status=200,
            body=permitted_body,
            fingerprint=baseline,
        )
        self.assertEqual(
            permitted_payload["required_next_action"],
            "PREVIEW_OR_INITIAL_PUBLISH",
        )

        poison = _PoisonWSGIInput()
        poison_cookie_jar = cookie_jar_bytes(self.client)
        poisoned_success = guarded_request(
            lambda: self.client.request(
                PATH_INFO=url,
                REQUEST_METHOD="GET",
                CONTENT_TYPE="application/json",
                CONTENT_LENGTH="64",
                **{"wsgi.input": poison},
            )
        )
        self.assertEqual(poison.read_attempts, 0)
        assert_fd07_transport(
            poisoned_success,
            self.client,
            poison_cookie_jar,
            status=200,
            body=permitted_body,
            fingerprint=baseline,
        )

        self.viewer_user.user_permissions.remove(
            self.permissions["studio_read_definition"]
        )
        revoked_baseline = _database_fingerprint()
        revoked_cookie_jar = cookie_jar_bytes(self.client)
        revoked = guarded_request(lambda: self._get(definition))
        assert_fd07_transport(
            revoked,
            self.client,
            revoked_cookie_jar,
            status=403,
            body=_canonical_json_bytes(capability_denial),
            fingerprint=revoked_baseline,
        )
        self.viewer_user.user_permissions.add(
            self.permissions["studio_read_definition"]
        )
        restored_baseline = _database_fingerprint()
        restored_cookie_jar = cookie_jar_bytes(self.client)
        restored = guarded_request(lambda: self._get(definition))
        assert_fd07_transport(
            restored,
            self.client,
            restored_cookie_jar,
            status=200,
            body=permitted_body,
            fingerprint=restored_baseline,
        )

        operation_id = uuid4()
        denied_write = self.client.post(
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            {"locale": "en", "workspace": self.workspace_spec()},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
        )
        self.assertEqual(denied_write.status_code, 403)
        self.assertFalse(ProjectPublication.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())
        self.assertEqual(_database_fingerprint(), restored_baseline)

        session = APIClient(enforce_csrf_checks=True)
        self.assertTrue(session.login(username="fd07-viewer", password="test-password"))
        session_baseline = _database_fingerprint()
        session_cookie_jar = cookie_jar_bytes(session)
        session_response = guarded_request(lambda: session.get(url))
        assert_fd07_transport(
            session_response,
            session,
            session_cookie_jar,
            status=200,
            body=permitted_body,
            fingerprint=session_baseline,
        )
        self.assertTrue(session_response.wsgi_request.user.is_authenticated)

        admitted_project_id = definition.project_id
        foreign_project = self._project("admission-race-foreign")
        original_service = publication_readiness_snapshot
        replacement: list[ProjectDefinitionVersion] = []

        def replace_after_admission(*, definition_id, scoped_project_id):
            self.assertEqual(scoped_project_id, admitted_project_id)
            definition.delete()
            replacement.append(
                self._definition(
                    "admission-race-replacement",
                    status=PublicationStatus.DRAFT,
                    project=foreign_project,
                    definition_id=definition_id,
                )
            )
            return original_service(
                definition_id=definition_id,
                scoped_project_id=scoped_project_id,
            )

        with patch(
            "domain.api.studio_definitions.publication_readiness_snapshot",
            side_effect=replace_after_admission,
        ):
            replaced_cookie_jar = cookie_jar_bytes(self.client)
            replaced = guarded_request(lambda: self.client.get(url))
        assert_fd07_transport(
            replaced,
            self.client,
            replaced_cookie_jar,
            status=404,
            body=_canonical_json_bytes(_NOT_FOUND),
            fingerprint=None,
        )
        self.assertEqual(replaced.json(), _NOT_FOUND)
        self.assertEqual(len(replacement), 1)
        self.assertEqual(replacement[0].project_id, foreign_project.pk)
        self.assertNotIn(str(foreign_project.pk).encode(), replaced.content)
        self.assertNotIn(replacement[0].manifest_hash.encode(), replaced.content)

    def test_first_project_draft_is_initial_candidate_snapshot_only(self):
        definition = self._draft("first-project")
        payload = self._payload(definition)
        self.assertEqual(
            payload,
            {
                "contract": "FOUNDATION_PUBLICATION_READINESS_V1",
                "contract_version": "1.0.0",
                "snapshot_scope": "LIFECYCLE_TOPOLOGY_ONLY",
                "project_id": str(self.project.pk),
                "definition_id": str(definition.pk),
                "manifest_hash": definition.manifest_hash,
                "publication_status": PublicationStatus.DRAFT,
                "validation_result_valid": None,
                "supersedes_id": None,
                "project_publication_count": 0,
                "project_workspace_count": 0,
                "initial_publication_receipt_count": 0,
                "current_definition_id": None,
                "current_definition_publication_status": None,
                "candidate_kind": "INITIAL",
                "required_next_action": "PREVIEW_OR_INITIAL_PUBLISH",
                "blocker_codes": [],
                "readiness_sha256": payload["readiness_sha256"],
            },
        )
        self.assertNotEqual(payload["readiness_sha256"], definition.manifest_hash)

    def test_standalone_draft_in_published_project_is_never_initial_candidate(self):
        initial = self._initial("standalone-base")
        standalone = self._draft("standalone")
        payload = self._payload(standalone)
        self._assert_candidate(
            payload,
            kind="NONE",
            action="NONE",
            blockers=[
                "INITIAL_PROJECT_HAS_PUBLICATION",
                "INITIAL_PROJECT_HAS_WORKSPACE",
                "INITIAL_PROJECT_HAS_CURRENT_DEFINITION",
                "SUCCESSOR_PREDECESSOR_REQUIRED",
            ],
        )
        self.assertEqual(payload["project_publication_count"], 1)
        self.assertEqual(payload["project_workspace_count"], 1)
        self.assertEqual(payload["initial_publication_receipt_count"], 1)
        self.assertEqual(payload["current_definition_id"], str(initial.definition.pk))
        self.assertEqual(
            payload["current_definition_publication_status"],
            PublicationStatus.PUBLISHED,
        )

    def test_exact_successor_draft_requires_validate_and_validated_requires_publish(self):
        initial = self._initial("successor-base")
        successor = self._successor(initial.definition, "successor")
        draft = self._payload(successor)
        self._assert_candidate(
            draft,
            kind="SUCCESSOR",
            action="VALIDATE",
            blockers=[],
        )
        self.assertIsNone(draft["validation_result_valid"])
        self.assertEqual(draft["supersedes_id"], str(initial.definition.pk))
        self.assertEqual(
            ProjectDefinitionVersion.objects.values_list(
                "validation_result",
                flat=True,
            ).get(pk=successor.pk),
            {},
        )

        validated = validate_project_definition(
            successor,
            actor_identifier="successor-validator",
            principal=self.publisher(actor="successor-validator"),
        )
        validated_payload = self._payload(validated)
        self._assert_candidate(
            validated_payload,
            kind="SUCCESSOR",
            action="SUCCESSOR_PUBLISH",
            blockers=[],
        )
        self.assertIs(validated_payload["validation_result_valid"], True)
        self.assertEqual(draft["manifest_hash"], validated_payload["manifest_hash"])
        self.assertNotEqual(
            draft["readiness_sha256"],
            validated_payload["readiness_sha256"],
        )
        self.assertIs(
            ProjectDefinitionVersion.objects.values_list(
                "validation_result__valid",
                flat=True,
            ).get(pk=validated.pk),
            True,
        )

        projection_vectors = (
            ("true", True, True),
            ("false", False, False),
            ("missing", None, None),
            ("null", None, None),
            ("zero", 0, None),
            ("one", 1, None),
            ("string", "true", None),
            ("list", [], None),
            ("mapping", {}, None),
        )
        projection_baseline = _database_fingerprint()
        with CaptureQueriesContext(connection) as captured:
            for label, raw_valid, expected_projection in projection_vectors:
                with self.subTest(pure_validation_projection=label):
                    projected = _publication_readiness_validation_result_valid(
                        raw_valid
                    )
                    if expected_projection is None:
                        self.assertIsNone(projected)
                    else:
                        self.assertIs(projected, expected_projection)
        self.assertEqual(captured.captured_queries, [])
        self.assertEqual(_database_fingerprint(), projection_baseline)

    def test_wrong_predecessor_missing_current_and_initial_receipt_integrity_fail_closed(self):
        cross_target = self._definition(
            "integrity-cross-receipt-target",
            status=PublicationStatus.DRAFT,
        )
        foreign_project = self._project("integrity-cross-receipt-foreign")
        foreign_definition = self._definition(
            "integrity-cross-receipt-source",
            status=PublicationStatus.PUBLISHED,
            project=foreign_project,
            typed=False,
        )
        foreign_workspace = self._workspace(
            foreign_definition,
            "integrity-cross-receipt-workspace",
            is_default=True,
        )
        foreign_receipt = self._publication(
            foreign_definition,
            "integrity-cross-receipt",
            initial_workspace=foreign_workspace,
            locale="fr-CA",
        )
        self._persist_corrupt_publication_definition(
            foreign_receipt,
            cross_target,
        )
        cross_read_baseline = _database_fingerprint()
        cross_snapshot = self._assert_stable_one_statement_snapshot(
            cross_target,
            kind="NONE",
            action="NONE",
            blockers=["DEFINITION_ALREADY_PUBLISHED"],
            stored_manifest_hash=cross_target.manifest_hash,
            not_disclosed=(
                foreign_project.pk,
                foreign_project.code,
                foreign_definition.pk,
                foreign_definition.code,
                foreign_workspace.pk,
                foreign_workspace.code,
                foreign_receipt.pk,
                foreign_receipt.code,
                foreign_receipt.actor_identifier,
                foreign_receipt.locale,
            ),
        )
        self.assertEqual(cross_snapshot["project_publication_count"], 0)
        self.assertEqual(cross_snapshot["project_workspace_count"], 0)
        self.assertEqual(cross_snapshot["initial_publication_receipt_count"], 0)
        self.assertIsNone(cross_snapshot["current_definition_id"])
        self.assertEqual(_database_fingerprint(), cross_read_baseline)

        def relational_receipt_topology(label: str, *, locale: str):
            project = self._project(f"{label}-project")
            self._scope(
                project,
                self.viewer_user,
                self.editor_user,
                self.publisher_user,
                self.no_capability_user,
            )
            initial_definition = self._definition(
                f"{label}-initial-definition",
                status=PublicationStatus.PUBLISHED,
                project=project,
                is_current=True,
                typed=False,
            )
            initial_workspace = self._workspace(
                initial_definition,
                f"{label}-initial-workspace",
                is_default=True,
            )
            initial_publication = self._publication(
                initial_definition,
                f"{label}-publication",
                initial_workspace=initial_workspace,
                locale=locale,
            )
            target = self._definition(
                f"{label}-successor",
                status=PublicationStatus.DRAFT,
                project=project,
                supersedes=initial_definition,
            )
            return (
                project,
                initial_definition,
                initial_workspace,
                initial_publication,
                target,
            )

        (
            foreign_workspace_project,
            _foreign_workspace_initial_definition,
            foreign_workspace,
            foreign_workspace_publication,
            foreign_workspace_target,
        ) = relational_receipt_topology(
            "receipt-foreign-workspace-project",
            locale="it-IT",
        )
        foreign_workspace_owner = self._project(
            "receipt-foreign-workspace-owner"
        )
        foreign_workspace.project = foreign_workspace_owner
        models.Model.save(
            foreign_workspace,
            update_fields=("project",),
        )
        foreign_workspace_baseline = _database_fingerprint()
        foreign_workspace_snapshot = self._assert_stable_one_statement_snapshot(
            foreign_workspace_target,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_INITIAL_RECEIPT_COUNT_INVALID"],
            stored_manifest_hash=foreign_workspace_target.manifest_hash,
            not_disclosed=(
                foreign_workspace_owner.pk,
                foreign_workspace_owner.code,
                foreign_workspace_owner.name,
                foreign_workspace.pk,
                foreign_workspace.code,
                foreign_workspace_publication.pk,
                foreign_workspace_publication.code,
                foreign_workspace_publication.actor_identifier,
                foreign_workspace_publication.locale,
            ),
        )
        self.assertEqual(
            foreign_workspace_snapshot["project_id"],
            str(foreign_workspace_project.pk),
        )
        self.assertEqual(
            foreign_workspace_snapshot["project_publication_count"],
            1,
        )
        self.assertEqual(
            foreign_workspace_snapshot["project_workspace_count"],
            0,
        )
        self.assertEqual(
            foreign_workspace_snapshot["initial_publication_receipt_count"],
            1,
        )
        self.assertEqual(
            _database_fingerprint(),
            foreign_workspace_baseline,
        )

        (
            pinned_definition_project,
            _pinned_initial_definition,
            pinned_workspace,
            pinned_publication,
            pinned_definition_target,
        ) = relational_receipt_topology(
            "receipt-different-definition-pin",
            locale="pt-BR",
        )
        different_pinned_definition = self._definition(
            "receipt-different-pinned-definition",
            status=PublicationStatus.PUBLISHED,
            project=pinned_definition_project,
        )
        pinned_workspace.definition_version = different_pinned_definition
        pinned_workspace.definition_manifest_hash = (
            different_pinned_definition.manifest_hash
        )
        models.Model.save(
            pinned_workspace,
            update_fields=(
                "definition_version",
                "definition_manifest_hash",
            ),
        )
        pinned_definition_baseline = _database_fingerprint()
        pinned_definition_snapshot = self._assert_stable_one_statement_snapshot(
            pinned_definition_target,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_INITIAL_RECEIPT_COUNT_INVALID"],
            stored_manifest_hash=pinned_definition_target.manifest_hash,
            not_disclosed=(
                different_pinned_definition.pk,
                different_pinned_definition.code,
                pinned_workspace.pk,
                pinned_workspace.code,
                pinned_publication.pk,
                pinned_publication.code,
                pinned_publication.actor_identifier,
                pinned_publication.locale,
            ),
        )
        self.assertEqual(
            pinned_definition_snapshot["project_publication_count"],
            1,
        )
        self.assertEqual(
            pinned_definition_snapshot["project_workspace_count"],
            1,
        )
        self.assertEqual(
            pinned_definition_snapshot["initial_publication_receipt_count"],
            1,
        )
        self.assertEqual(
            _database_fingerprint(),
            pinned_definition_baseline,
        )

        (
            _,
            mismatched_hash_definition,
            mismatched_hash_workspace,
            mismatched_hash_publication,
            mismatched_hash_target,
        ) = relational_receipt_topology(
            "receipt-mismatched-workspace-hash",
            locale="nl-NL",
        )
        corrupt_workspace_hash = "0" * 64
        self.assertNotEqual(
            corrupt_workspace_hash,
            mismatched_hash_definition.manifest_hash,
        )
        mismatched_hash_workspace.definition_manifest_hash = (
            corrupt_workspace_hash
        )
        models.Model.save(
            mismatched_hash_workspace,
            update_fields=("definition_manifest_hash",),
        )
        mismatched_hash_baseline = _database_fingerprint()
        mismatched_hash_snapshot = self._assert_stable_one_statement_snapshot(
            mismatched_hash_target,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_INITIAL_RECEIPT_COUNT_INVALID"],
            stored_manifest_hash=mismatched_hash_target.manifest_hash,
            not_disclosed=(
                corrupt_workspace_hash,
                mismatched_hash_workspace.pk,
                mismatched_hash_workspace.code,
                mismatched_hash_publication.pk,
                mismatched_hash_publication.code,
                mismatched_hash_publication.actor_identifier,
                mismatched_hash_publication.locale,
            ),
        )
        self.assertEqual(
            mismatched_hash_snapshot["project_publication_count"],
            1,
        )
        self.assertEqual(
            mismatched_hash_snapshot["project_workspace_count"],
            1,
        )
        self.assertEqual(
            mismatched_hash_snapshot["initial_publication_receipt_count"],
            1,
        )
        self.assertEqual(_database_fingerprint(), mismatched_hash_baseline)

        initial = self._initial("integrity-base")
        wrong_predecessor = self._definition(
            "wrong-predecessor",
            status=PublicationStatus.PUBLISHED,
            typed=False,
        )
        wrong_target = self._definition(
            "wrong-target",
            status=PublicationStatus.DRAFT,
            supersedes=wrong_predecessor,
        )
        wrong = self._payload(wrong_target)
        self._assert_candidate(
            wrong,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_PREDECESSOR_MISMATCH"],
        )

        current = initial.definition
        current.is_current = False
        with _canonical_studio_write("definition"):
            current.save(update_fields=("is_current", "updated_at"))
        missing = self._payload(wrong_target)
        self._assert_candidate(
            missing,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_CURRENT_PUBLISHED_REQUIRED"],
        )

        current.is_current = True
        with _canonical_studio_write("definition"):
            current.save(update_fields=("is_current", "updated_at"))
        correct_target = self._definition(
            "correct-target",
            status=PublicationStatus.DRAFT,
            supersedes=current,
        )
        self._persist_corrupt_initial_workspace(initial.publication, None)
        missing_receipt = self._payload(correct_target)
        self._assert_candidate(
            missing_receipt,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_INITIAL_RECEIPT_COUNT_INVALID"],
        )
        self._persist_corrupt_initial_workspace(
            initial.publication,
            initial.workspace,
        )

        extra_definition = self._definition(
            "extra-receipt-definition",
            status=PublicationStatus.PUBLISHED,
            typed=False,
        )
        extra_workspace = self._workspace(
            extra_definition,
            "extra-receipt-workspace",
        )
        extra_publication = self._publication(
            extra_definition,
            "extra-receipt-publication",
        )
        self._persist_corrupt_initial_workspace(
            extra_publication,
            extra_workspace,
        )
        duplicate_receipt = self._payload(correct_target)
        self._assert_candidate(
            duplicate_receipt,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_INITIAL_RECEIPT_COUNT_INVALID"],
        )
        self.assertEqual(duplicate_receipt["project_publication_count"], 2)
        self.assertEqual(duplicate_receipt["initial_publication_receipt_count"], 2)

        same_target = self._definition(
            "integrity-same-receipt-target",
            status=PublicationStatus.DRAFT,
            supersedes=current,
        )
        same_source = self._definition(
            "integrity-same-receipt-source",
            status=PublicationStatus.PUBLISHED,
            typed=False,
        )
        same_receipt = self._publication(
            same_source,
            "integrity-same-receipt",
            locale="es-MX",
        )
        self._persist_corrupt_publication_definition(
            same_receipt,
            same_target,
        )
        same_read_baseline = _database_fingerprint()
        same_snapshot = self._assert_stable_one_statement_snapshot(
            same_target,
            kind="NONE",
            action="NONE",
            blockers=["DEFINITION_ALREADY_PUBLISHED"],
            stored_manifest_hash=same_target.manifest_hash,
            not_disclosed=(
                same_source.pk,
                same_source.code,
                same_receipt.pk,
                same_receipt.code,
                same_receipt.actor_identifier,
                same_receipt.locale,
            ),
        )
        self.assertEqual(same_snapshot["project_publication_count"], 3)
        self.assertEqual(same_snapshot["project_workspace_count"], 2)
        self.assertEqual(same_snapshot["initial_publication_receipt_count"], 2)
        self.assertEqual(same_snapshot["current_definition_id"], str(current.pk))
        self.assertEqual(_database_fingerprint(), same_read_baseline)

    def test_published_retired_and_validated_initial_states_have_no_publication_action(self):
        published = self._definition(
            "published-terminal",
            status=PublicationStatus.PUBLISHED,
        )
        retired = self._definition(
            "retired-terminal",
            status=PublicationStatus.RETIRED,
        )
        validated = self._definition(
            "validated-initial",
            status=PublicationStatus.VALIDATED,
        )
        expectations = (
            (published, ["DEFINITION_ALREADY_PUBLISHED"]),
            (retired, ["DEFINITION_RETIRED"]),
            (
                validated,
                ["INITIAL_REQUIRES_DRAFT", "SUCCESSOR_PREDECESSOR_REQUIRED"],
            ),
        )
        for definition, blockers in expectations:
            with self.subTest(status=definition.publication_status):
                payload = self._payload(definition)
                self._assert_candidate(
                    payload,
                    kind="NONE",
                    action="NONE",
                    blockers=blockers,
                )
                self.assertIs(payload["validation_result_valid"], True)

        receipted_retired = self._definition(
            "receipted-retired-terminal",
            status=PublicationStatus.RETIRED,
        )
        retired_receipt_source = self._definition(
            "receipted-retired-source",
            status=PublicationStatus.PUBLISHED,
            typed=False,
        )
        retired_receipt = self._publication(
            retired_receipt_source,
            "receipted-retired-publication",
            locale="de-DE",
        )
        self._persist_corrupt_publication_definition(
            retired_receipt,
            receipted_retired,
        )
        precedence_baseline = _database_fingerprint()
        with patch(
            "domain.services.project_definitions."
            "identify_typed_project_definition_manifest",
            side_effect=AssertionError(
                "target receipt guard must precede typed-envelope evaluation"
            ),
        ) as identify_manifest, patch(
            "domain.services.project_definitions."
            "hash_project_definition_manifest_v1",
            side_effect=AssertionError(
                "target receipt guard must precede canonical hashing"
            ),
        ) as canonical_hash:
            self._assert_stable_one_statement_snapshot(
                receipted_retired,
                kind="NONE",
                action="NONE",
                blockers=["DEFINITION_ALREADY_PUBLISHED"],
                stored_manifest_hash=receipted_retired.manifest_hash,
                not_disclosed=(
                    retired_receipt_source.pk,
                    retired_receipt_source.code,
                    retired_receipt.pk,
                    retired_receipt.code,
                    retired_receipt.actor_identifier,
                    retired_receipt.locale,
                ),
            )
        identify_manifest.assert_not_called()
        canonical_hash.assert_not_called()
        self.assertEqual(_database_fingerprint(), precedence_baseline)

    def test_response_is_canonical_hash_bound_no_store_and_deterministic(self):
        (
            initial_unsupported,
            initial_semantic,
            initial_semantic_not_disclosed,
        ) = self._topology_eligibility_vectors(
            "response-initial-eligibility",
            supersedes=None,
        )
        initial_read_baseline = _database_fingerprint()
        for (
            vector_name,
            target,
            stored_hash,
            not_disclosed,
        ) in initial_unsupported:
            with self.subTest(topology="initial", vector=vector_name):
                self._assert_stable_one_statement_snapshot(
                    target,
                    kind="NONE",
                    action="NONE",
                    blockers=["PUBLICATION_TOPOLOGY_UNSUPPORTED"],
                    stored_manifest_hash=stored_hash,
                    not_disclosed=not_disclosed,
                )
        with self.subTest(topology="initial", vector="semantic-diagnostic"):
            initial_zero_snapshot = self._assert_stable_one_statement_snapshot(
                initial_semantic,
                kind="INITIAL",
                action="PREVIEW_OR_INITIAL_PUBLISH",
                blockers=[],
                stored_manifest_hash=initial_semantic.manifest_hash,
                not_disclosed=initial_semantic_not_disclosed,
            )
        for count_key in (
            "project_publication_count",
            "project_workspace_count",
            "initial_publication_receipt_count",
        ):
            self.assertIs(type(initial_zero_snapshot[count_key]), int)
            self.assertEqual(initial_zero_snapshot[count_key], 0)
        self.assertEqual(_database_fingerprint(), initial_read_baseline)

        current = self._definition(
            "count-current",
            status=PublicationStatus.PUBLISHED,
            is_current=True,
            typed=False,
        )
        initial_workspace = self._workspace(
            current,
            "count-initial-workspace",
            is_default=True,
        )
        self._publication(
            current,
            "count-initial-publication",
            initial_workspace=initial_workspace,
        )
        for index in range(2):
            definition = self._definition(
                f"count-publication-{index}",
                status=PublicationStatus.PUBLISHED,
                typed=False,
            )
            self._publication(definition, f"count-publication-receipt-{index}")
        workspaces = [initial_workspace]
        for index in range(3):
            workspaces.append(
                self._workspace(current, f"count-workspace-{index}")
            )
        for workspace_index, workspace in enumerate(workspaces):
            for binding_index in range(3):
                self._binding(
                    workspace,
                    f"count-binding-{workspace_index}-{binding_index}",
                )

        target = self._definition(
            "count-target",
            status=PublicationStatus.DRAFT,
            supersedes=current,
        )
        persisted_manifest_hash = target.manifest_hash
        persisted_project_id = target.project_id

        (
            successor_unsupported,
            successor_semantic,
            successor_semantic_not_disclosed,
        ) = (
            self._topology_eligibility_vectors(
                "response-successor-eligibility",
                supersedes=current,
            )
        )
        successor_read_baseline = _database_fingerprint()
        for (
            vector_name,
            vector_target,
            stored_hash,
            not_disclosed,
        ) in successor_unsupported:
            with self.subTest(topology="successor", vector=vector_name):
                self._assert_stable_one_statement_snapshot(
                    vector_target,
                    kind="NONE",
                    action="NONE",
                    blockers=["PUBLICATION_TOPOLOGY_UNSUPPORTED"],
                    stored_manifest_hash=stored_hash,
                    not_disclosed=not_disclosed,
                )
        with self.subTest(topology="successor", vector="semantic-diagnostic"):
            self._assert_stable_one_statement_snapshot(
                successor_semantic,
                kind="SUCCESSOR",
                action="VALIDATE",
                blockers=[],
                stored_manifest_hash=successor_semantic.manifest_hash,
                not_disclosed=successor_semantic_not_disclosed,
            )
        self.assertEqual(_database_fingerprint(), successor_read_baseline)

        unrelated = self._project("unrelated-counts")
        for index in range(4):
            definition = self._definition(
                f"unrelated-definition-{index}",
                status=PublicationStatus.PUBLISHED,
                project=unrelated,
                is_current=index == 0,
                typed=False,
            )
            workspace = self._workspace(
                definition,
                f"unrelated-workspace-{index}",
                is_default=index == 0,
            )
            self._publication(
                definition,
                f"unrelated-publication-{index}",
                initial_workspace=workspace if index == 0 else None,
            )

        target.manifest_hash = "0" * 64
        target.publication_status = PublicationStatus.RETIRED
        target.project_id = unrelated.pk
        with CaptureQueriesContext(connection) as captured:
            service_snapshot = publication_readiness_snapshot(
                definition_id=target.pk,
                scoped_project_id=persisted_project_id,
            )
        self.assertEqual(len(captured), 1)
        query = captured[0]["sql"].upper()
        self.assertNotIn("FOR UPDATE", query)
        self.assertGreaterEqual(query.count("COUNT("), 4)
        self.assertIn(ProjectPublication._meta.db_table.upper(), query)
        self.assertIn(ProjectWorkspace._meta.db_table.upper(), query)
        self.assertIn(ProjectDefinitionVersion._meta.db_table.upper(), query)

        self.assertEqual(service_snapshot["project_id"], str(persisted_project_id))
        self.assertEqual(service_snapshot["manifest_hash"], persisted_manifest_hash)
        self.assertEqual(
            service_snapshot["publication_status"],
            PublicationStatus.DRAFT,
        )
        self.assertEqual(service_snapshot["project_publication_count"], 3)
        self.assertEqual(service_snapshot["project_workspace_count"], 4)
        self.assertEqual(service_snapshot["initial_publication_receipt_count"], 1)
        self.assertEqual(service_snapshot["current_definition_id"], str(current.pk))
        self._assert_candidate(
            service_snapshot,
            kind="SUCCESSOR",
            action="VALIDATE",
            blockers=[],
        )

        response = self.client.get(self._url(target.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), service_snapshot)
        core = dict(service_snapshot)
        readiness_hash = core.pop("readiness_sha256")
        self.assertEqual(
            readiness_hash,
            hashlib.sha256(_canonical_json_bytes(core)).hexdigest(),
        )
        self.assertEqual(
            response.content,
            _canonical_json_bytes(service_snapshot, terminal_lf=True),
        )
        self.assertEqual(response["ETag"], f'"{readiness_hash}"')
        self.assertEqual(response["Cache-Control"], "no-store")
        self.assertEqual(response["Vary"], "Cookie, Authorization")
        self.assertFalse(response.cookies)
        self.assertNotIn("Set-Cookie", response.headers)

        repeated = self.client.get(self._url(target.pk))
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.content, response.content)
        self.assertEqual(repeated["ETag"], response["ETag"])

        service_owned = dict(service_snapshot)
        service_owned["project_id"] = str(uuid4())
        service_owned["manifest_hash"] = "f" * 64
        service_core = dict(service_owned)
        service_core.pop("readiness_sha256")
        service_owned["readiness_sha256"] = hashlib.sha256(
            _canonical_json_bytes(service_core)
        ).hexdigest()
        with patch(
            "domain.api.studio_definitions.publication_readiness_snapshot",
            return_value=service_owned,
        ):
            service_owned_response = self.client.get(self._url(target.pk))
        self.assertEqual(service_owned_response.json(), service_owned)
        self.assertEqual(
            service_owned_response["ETag"],
            f'"{service_owned["readiness_sha256"]}"',
        )

    def test_old_hash_basic_absent_and_cross_scope_are_password_cookie_write_free(self):
        definition = self._draft("basic")
        other_project = self._project("cross-scope")
        other_definition = self._definition(
            "cross-scope-definition",
            status=PublicationStatus.DRAFT,
            project=other_project,
        )

        password_hasher = PBKDF2PasswordHasher()
        old_hash = password_hasher.encode(
            "test-password",
            password_hasher.salt(),
            iterations=1,
        )
        self.assertTrue(password_hasher.must_update(old_hash))
        get_user_model().objects.filter(pk=self.viewer_user.pk).update(
            password=old_hash
        )
        self.viewer_user.refresh_from_db()

        valid_session = APIClient(enforce_csrf_checks=True)
        valid_session.force_login(self.viewer_user)
        valid_session_key = valid_session.cookies[
            settings.SESSION_COOKIE_NAME
        ].value

        valid_session_malformed_csrf = APIClient(enforce_csrf_checks=True)
        valid_session_malformed_csrf.cookies[
            settings.SESSION_COOKIE_NAME
        ] = valid_session_key
        valid_session_malformed_csrf.cookies[
            settings.CSRF_COOKIE_NAME
        ] = "bad"

        expired_session = APIClient(enforce_csrf_checks=True)
        expired_session.force_login(self.viewer_user)
        expired_session_key = expired_session.cookies[
            settings.SESSION_COOKIE_NAME
        ].value
        self.assertEqual(
            Session.objects.filter(pk=expired_session_key).update(
                expire_date=timezone.now() - timedelta(minutes=5)
            ),
            1,
        )

        malformed_session = APIClient(enforce_csrf_checks=True)
        malformed_session.cookies[
            settings.SESSION_COOKIE_NAME
        ] = "not-a-session"
        malformed_session.cookies[settings.CSRF_COOKIE_NAME] = "bad"
        missing_session = APIClient(enforce_csrf_checks=True)

        def cookie_jar_bytes(client: APIClient) -> bytes:
            return client.cookies.output(
                header="Cookie:",
                sep="\r\n",
            ).encode("latin-1")

        def guarded_request(operation):
            guards = (
                (
                    "domain.api.studio_definitions.get_token",
                    "FD07 must not request a CSRF token",
                ),
                (
                    "rest_framework.request.Request._load_data_and_files",
                    "FD07 must not materialize a parser",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.save",
                    "FD07 must not save a session",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.delete",
                    "FD07 must not delete a session",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.flush",
                    "FD07 must not flush a session",
                ),
                (
                    "django.contrib.sessions.backends.db.SessionStore.cycle_key",
                    "FD07 must not rotate a session",
                ),
            )
            active = []
            try:
                for target, message in guards:
                    patcher = patch(target, side_effect=AssertionError(message))
                    patcher.start()
                    active.append(patcher)
                return operation()
            finally:
                for patcher in reversed(active):
                    patcher.stop()

        def assert_fd07_transport(
            response,
            client: APIClient,
            incoming_cookie_jar: bytes,
            *,
            status: int,
            body: bytes,
            fingerprint: str,
            www_authenticate: str | None = None,
        ) -> None:
            self.assertEqual(response.status_code, status, response.content)
            self.assertEqual(response.content, body)
            self.assertEqual(response["Cache-Control"], "no-store")
            self.assertEqual(response["Vary"], "Cookie, Authorization")
            self.assertFalse(response.cookies)
            self.assertEqual(response.cookies.output(), "")
            self.assertNotIn("Set-Cookie", response.headers)
            self.assertIn(
                "CSRF_COOKIE_NEEDS_UPDATE",
                response.wsgi_request.META,
            )
            self.assertIs(
                response.wsgi_request.META["CSRF_COOKIE_NEEDS_UPDATE"],
                False,
            )
            self.assertEqual(cookie_jar_bytes(client), incoming_cookie_jar)
            self.assertEqual(
                response.headers.get("Content-Length"),
                str(len(body)),
            )
            self.assertEqual(
                response.headers.get("WWW-Authenticate"),
                www_authenticate,
            )
            self.assertEqual(
                {
                    item.strip()
                    for item in response.headers.get("Allow", "").split(",")
                    if item.strip()
                },
                {"GET", "OPTIONS"},
            )
            self.assertEqual(_database_fingerprint(), fingerprint)

        baseline = _database_fingerprint()
        missing_auth = {
            "detail": str(NotAuthenticated.default_detail),
        }
        missing_auth_body = _canonical_json_bytes(missing_auth)
        invalid_basic_body = b'{"detail":"Invalid username/password."}'
        not_found_body = _canonical_json_bytes(_NOT_FOUND)
        authorization = "Basic " + base64.b64encode(
            b"fd07-viewer:test-password"
        ).decode("ascii")
        basic = APIClient(enforce_csrf_checks=True)

        basic_cookie_jar = cookie_jar_bytes(basic)
        success = guarded_request(
            lambda: basic.get(
                self._url(definition),
                HTTP_AUTHORIZATION=authorization,
            )
        )
        success_body = _canonical_json_bytes(success.json(), terminal_lf=True)
        assert_fd07_transport(
            success,
            basic,
            basic_cookie_jar,
            status=200,
            body=success_body,
            fingerprint=baseline,
        )
        self.assertTrue(success.wsgi_request.user.is_authenticated)

        absent_cookie_jar = cookie_jar_bytes(basic)
        absent = guarded_request(
            lambda: basic.get(
                self._url(uuid4()),
                HTTP_AUTHORIZATION=authorization,
            )
        )
        assert_fd07_transport(
            absent,
            basic,
            absent_cookie_jar,
            status=404,
            body=not_found_body,
            fingerprint=baseline,
        )
        cross_scope_cookie_jar = cookie_jar_bytes(basic)
        cross_scope = guarded_request(
            lambda: basic.get(
                self._url(other_definition),
                HTTP_AUTHORIZATION=authorization,
            )
        )
        assert_fd07_transport(
            cross_scope,
            basic,
            cross_scope_cookie_jar,
            status=404,
            body=not_found_body,
            fingerprint=baseline,
        )
        self.assertEqual(absent.json(), _NOT_FOUND)
        self.assertEqual(cross_scope.json(), _NOT_FOUND)
        self.assertEqual(absent.content, cross_scope.content)

        invalid_cookie_jar = cookie_jar_bytes(basic)
        invalid = guarded_request(
            lambda: basic.get(
                self._url(definition),
                HTTP_AUTHORIZATION="Basic "
                + base64.b64encode(
                    b"fd07-viewer:not-the-password"
                ).decode("ascii"),
            )
        )
        assert_fd07_transport(
            invalid,
            basic,
            invalid_cookie_jar,
            status=401,
            body=invalid_basic_body,
            fingerprint=baseline,
            www_authenticate='Basic realm="api"',
        )
        self.assertFalse(invalid.wsgi_request.user.is_authenticated)

        absent_user_cookie_jar = cookie_jar_bytes(basic)
        absent_user = guarded_request(
            lambda: basic.get(
                self._url(definition),
                HTTP_AUTHORIZATION="Basic "
                + base64.b64encode(
                    b"fd07-absent:test-password"
                ).decode("ascii"),
            )
        )
        assert_fd07_transport(
            absent_user,
            basic,
            absent_user_cookie_jar,
            status=401,
            body=invalid_basic_body,
            fingerprint=baseline,
            www_authenticate='Basic realm="api"',
        )
        self.assertFalse(absent_user.wsgi_request.user.is_authenticated)

        session_cases = (
            (
                "missing_session",
                missing_session,
                401,
                missing_auth_body,
                False,
                'Basic realm="api"',
            ),
            (
                "malformed_session",
                malformed_session,
                401,
                missing_auth_body,
                False,
                'Basic realm="api"',
            ),
            (
                "expired_session",
                expired_session,
                401,
                missing_auth_body,
                False,
                'Basic realm="api"',
            ),
            (
                "valid_session",
                valid_session,
                200,
                success_body,
                True,
                None,
            ),
            (
                "valid_session_malformed_csrf",
                valid_session_malformed_csrf,
                200,
                success_body,
                True,
                None,
            ),
        )
        for (
            label,
            session_client,
            status,
            body,
            authenticated,
            www_authenticate,
        ) in session_cases:
            with self.subTest(session=label):
                session_cookie_jar = cookie_jar_bytes(session_client)
                response = guarded_request(
                    lambda session_client=session_client: session_client.get(
                        self._url(definition)
                    )
                )
                assert_fd07_transport(
                    response,
                    session_client,
                    session_cookie_jar,
                    status=status,
                    body=body,
                    fingerprint=baseline,
                    www_authenticate=www_authenticate,
                )
                self.assertIs(
                    bool(response.wsgi_request.user.is_authenticated),
                    authenticated,
                )
                if not authenticated:
                    self.assertEqual(response.json(), missing_auth)

        self.assertTrue(Session.objects.filter(pk=expired_session_key).exists())
        self.assertEqual(
            get_user_model().objects.values_list("password", flat=True).get(
                pk=self.viewer_user.pk
            ),
            old_hash,
        )
        self.assertEqual(_database_fingerprint(), baseline)

    def test_readiness_is_advisory_and_fd06_rechecks_after_persisted_state_changes(self):
        initial = self._initial("advisory-base")
        target = self._successor(
            initial.definition,
            "advisory-target",
            validate=True,
        )
        winner = self._successor(
            initial.definition,
            "advisory-winner",
            validate=True,
        )
        original_manifest_hash = target.manifest_hash

        role_responses = [
            self._get(target, user=user)
            for user in (
                self.viewer_user,
                self.editor_user,
                self.publisher_user,
            )
        ]
        for response in role_responses:
            self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            {response.content for response in role_responses},
            {role_responses[0].content},
        )
        displayed = role_responses[0].json()
        self._assert_candidate(
            displayed,
            kind="SUCCESSOR",
            action="SUCCESSOR_PUBLISH",
            blockers=[],
        )
        self.assertNotEqual(
            displayed["readiness_sha256"],
            displayed["manifest_hash"],
        )

        denied_baseline = _database_fingerprint()
        for user in (self.viewer_user, self.editor_user):
            with self.subTest(role=user.username):
                _, denied = self._fd06_successor_post(target, user=user)
                self.assertEqual(denied.status_code, 403, denied.content)
                self.assertEqual(denied.json()["code"], "STUDIO_CAPABILITY_DENIED")
        self.assertEqual(_database_fingerprint(), denied_baseline)

        publish_project_definition(
            winner,
            actor_identifier="advisory-winner-publisher",
            principal=self.publisher(actor="advisory-winner-publisher"),
            locale="en",
            publication_code=self._next("advisory-winner-publication")[0],
        )
        target.refresh_from_db()
        self.assertEqual(target.manifest_hash, original_manifest_hash)
        fresh = self._payload(target, user=self.publisher_user)
        self.assertEqual(fresh["manifest_hash"], displayed["manifest_hash"])
        self.assertNotEqual(
            fresh["readiness_sha256"],
            displayed["readiness_sha256"],
        )
        self._assert_candidate(
            fresh,
            kind="NONE",
            action="NONE",
            blockers=["SUCCESSOR_PREDECESSOR_MISMATCH"],
        )

        operation_id, rejected = self._fd06_successor_post(
            target,
            user=self.publisher_user,
        )
        self.assertEqual(rejected.status_code, 409, rejected.content)
        self.assertEqual(
            rejected.json(),
            {
                "code": "PUBLICATION_TARGET_STATE_CONFLICT",
                "errors": [
                    "The requested Foundation publication operation conflicts with persisted state."
                ],
            },
        )
        self.assertFalse(
            ProjectPublication.objects.filter(definition_version=target).exists()
        )
        self.assertFalse(
            ProjectPublication.objects.filter(
                code__startswith=f"PUBOP-{operation_id}-"
            ).exists()
        )
        self.assertEqual(ProjectPublication.objects.count(), 2)
