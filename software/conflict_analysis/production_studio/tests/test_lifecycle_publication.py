from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import models
from django.test import Client, TestCase
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name
from domain.enums import PublicationStatus
from domain.models import AuditEvent, Project, ProjectDefinitionVersion, ProjectPublication
from domain.policies import (
    StudioPrincipal,
    StudioRole,
    bootstrap_initial_project_definition,
    validate_project_definition,
)
from domain.services.project_definitions import (
    clone_project_definition_draft,
    create_project_definition_draft,
)
from domain.tests.test_foundation_studio_bootstrap import FoundationStudioBootstrapMixin
from production_studio.lifecycle_claim_boundaries import (
    LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_BYTES,
    LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_ID,
    LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_PATH,
    LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256,
    LIFECYCLE_CLAIM_BOUNDARY_EXPECTED_SIDECAR,
    LIFECYCLE_CLAIM_BOUNDARY_SIDECAR_PATH,
    LifecycleClaimBoundaryContractError,
    load_lifecycle_claim_boundaries,
)
from production_studio.tests import database_fingerprint


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LIFECYCLE_SCRIPT = (
    PROJECT_ROOT
    / "production_studio"
    / "static"
    / "production_studio"
    / "lifecycle_publication.js"
)
AUDITED_DRAFT_SCRIPT = LIFECYCLE_SCRIPT.with_name("audited_draft.js")
LIFECYCLE_TEMPLATE = (
    PROJECT_ROOT
    / "production_studio"
    / "templates"
    / "production_studio"
    / "lifecycle_publication_definition.html"
)
LIFECYCLE_BROWSER = (
    PROJECT_ROOT
    / "production_studio"
    / "browser_tests"
    / "lifecycle_publication.mjs"
)

def _canonical_json(value: object, *, terminal_lf: bool = False) -> bytes:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return encoded + (b"\n" if terminal_lf else b"")


class _LifecyclePublicationFixture(FoundationStudioBootstrapMixin):
    password = "c2a-lifecycle-password"

    def make_lifecycle_fixture(self) -> None:
        self.make_contract()
        self.permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
            )
        }
        self.viewer_user = self._user("viewer", ("studio_read_definition",))
        self.editor_user = self._user(
            "editor",
            (
                "studio_read_definition",
                "studio_create_definition_draft",
                "studio_clone_definition_draft",
                "studio_save_definition_draft",
            ),
        )
        self.publisher_user = self._user(
            "publisher",
            (
                "studio_read_definition",
                "studio_validate_definition",
                "studio_publish_definition",
            ),
        )
        self.no_capability_user = self._user("no-capability", ())
        self.out_of_scope_publisher = self._user(
            "out-of-scope",
            (
                "studio_read_definition",
                "studio_validate_definition",
                "studio_publish_definition",
            ),
            scoped=False,
        )
        self.definition = create_project_definition_draft(
            project=self.project,
            code=f"C2A-DRAFT-{uuid4().hex[:12]}",
            version="1.0.0",
            manifest=copy.deepcopy(self.manifest),
            principal=self.editor(actor="c2a-fixture-editor"),
        )

    def _user(
        self,
        label: str,
        permissions: tuple[str, ...],
        *,
        scoped: bool = True,
    ):
        user = get_user_model().objects.create_user(
            username=f"c2a-{label}-{uuid4().hex}",
            password=self.password,
        )
        user.user_permissions.add(*(self.permissions[name] for name in permissions))
        if scoped:
            self._scope(self.project, user)
        return get_user_model().objects.get(pk=user.pk)

    @staticmethod
    def _scope(project: Project, *users: object) -> Group:
        group, _ = Group.objects.get_or_create(
            name=project_access_group_name(project.pk)
        )
        group.user_set.add(*users)
        return group

    @staticmethod
    def _shell_url(definition: ProjectDefinitionVersion | UUID) -> str:
        definition_id = definition.pk if hasattr(definition, "pk") else definition
        return f"/studio/lifecycle/definitions/{definition_id}/"

    @staticmethod
    def _open_url(definition: ProjectDefinitionVersion) -> str:
        return f"/api/foundation/definitions/{definition.pk}/"

    @staticmethod
    def _readiness_url(definition: ProjectDefinitionVersion) -> str:
        return f"/api/foundation/definitions/{definition.pk}/publication-readiness/"

    @staticmethod
    def _operation_url(project: Project, operation_id: UUID) -> str:
        return (
            f"/api/foundation/projects/{project.pk}/"
            f"publication-operations/{operation_id}/"
        )

    @staticmethod
    def _api(user: object) -> APIClient:
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _session_api(self, user: object) -> tuple[APIClient, str]:
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(user)
        shell = client.get(self._shell_url(self.definition))
        self.assertEqual(shell.status_code, 200)
        return client, client.cookies[settings.CSRF_COOKIE_NAME].value

    def _publish_initial(
        self,
        *,
        definition: ProjectDefinitionVersion | None = None,
        user: object | None = None,
        operation_id: UUID | None = None,
        locale: str = "ru",
        workspace_id: UUID | None = None,
    ):
        definition = definition or self.definition
        operation_id = operation_id or uuid4()
        workspace_id = workspace_id or uuid4()
        body = _canonical_json(
            {
                "locale": locale,
                "workspace": {
                    "code": f"C2A-WORKSPACE-{workspace_id.hex[:12]}",
                    "id": str(workspace_id),
                    "is_default": True,
                    "metadata": {"slice": "C2A"},
                    "name": "C2A initial workspace",
                    "version": "1.0.0",
                },
            }
        )
        client = self._api(user or self.publisher_user)
        response = client.generic(
            "POST",
            f"/api/foundation/definitions/{definition.pk}/publish-initial/",
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
        )
        return operation_id, body, response

    def _publish_predecessor(self) -> ProjectDefinitionVersion:
        result = bootstrap_initial_project_definition(
            definition=self.definition,
            principal=self.publisher(actor="c2a-bootstrap-publisher"),
            actor_identifier="c2a-bootstrap-publisher",
            workspace_spec={
                "id": str(uuid4()),
                "code": f"C2A-INITIAL-{uuid4().hex[:12]}",
                "version": "1.0.0",
                "name": "C2A initial workspace",
                "is_default": True,
                "metadata": {"slice": "C2A"},
            },
            locale="ru",
            publication_code=f"C2A-PUB-{uuid4().hex[:12]}",
        )
        self.definition = result.definition
        self.definition.refresh_from_db()
        return self.definition

    def _successor(self) -> ProjectDefinitionVersion:
        predecessor = self.definition
        if predecessor.publication_status != PublicationStatus.PUBLISHED:
            predecessor = self._publish_predecessor()
        return clone_project_definition_draft(
            predecessor,
            code=f"C2A-SUCCESSOR-{uuid4().hex[:12]}",
            version="2.0.0",
            principal=self.editor(actor="c2a-successor-editor"),
        )

    def _validate(
        self,
        definition: ProjectDefinitionVersion,
        *,
        operation_id: UUID | None = None,
        if_match: str | None = None,
        user: object | None = None,
    ):
        operation_id = operation_id or uuid4()
        response = self._api(user or self.publisher_user).generic(
            "POST",
            f"/api/foundation/definitions/{definition.pk}/validate/",
            b"{}",
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{if_match or definition.manifest_hash}"',
        )
        return operation_id, response

    def _publish_successor(
        self,
        definition: ProjectDefinitionVersion,
        *,
        operation_id: UUID | None = None,
        user: object | None = None,
    ):
        operation_id = operation_id or uuid4()
        body = b'{"locale":"ru"}'
        response = self._api(user or self.publisher_user).generic(
            "POST",
            f"/api/foundation/definitions/{definition.pk}/publish-successor/",
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
        )
        return operation_id, body, response

    def _fresh_project_and_draft(self, label: str) -> tuple[Project, ProjectDefinitionVersion]:
        project = Project.objects.create(
            id=uuid4(),
            code=f"C2A-{label.upper()}-{uuid4().hex[:10]}",
            version="1.0.0",
            name=f"C2A {label}",
            description=f"C2A {label} topology",
            metadata={"slice": "C2A", "fixture": label},
            primary_language_tag="ru",
            primary_language_assignment="EXPLICIT",
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
        definition = create_project_definition_draft(
            project=project,
            code=f"C2A-{label.upper()}-DRAFT-{uuid4().hex[:8]}",
            version="1.0.0",
            manifest=manifest,
            principal=self.editor(actor=f"c2a-{label}-editor"),
        )
        self._scope(project, self.publisher_user, self.viewer_user, self.editor_user)
        return project, definition


class ProductionStudioLifecyclePublicationTests(
    _LifecyclePublicationFixture,
    TestCase,
):
    def setUp(self) -> None:
        self.make_lifecycle_fixture()

    def test_route_auth_and_checksum_bound_claim_contract_are_exact(self):
        payload = LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_PATH.read_bytes()
        sidecar = LIFECYCLE_CLAIM_BOUNDARY_SIDECAR_PATH.read_bytes()
        verified = load_lifecycle_claim_boundaries()
        public_before = database_fingerprint()
        public = Client().get("/studio/claim-boundaries/lifecycle-publication/v1/")
        anonymous = Client().get(self._shell_url(self.definition))
        self.assertEqual(database_fingerprint(), public_before)
        mixed_user = self._user(
            "mixed-route-matrix",
            (
                "studio_read_definition",
                "studio_create_definition_draft",
                "studio_clone_definition_draft",
                "studio_save_definition_draft",
                "studio_validate_definition",
                "studio_publish_definition",
            ),
        )
        role_clients = {}
        for label, user in (
            ("editor", self.editor_user),
            ("publisher", self.publisher_user),
            ("viewer", self.viewer_user),
            ("player", self.no_capability_user),
            ("mixed", mixed_user),
        ):
            role_clients[label] = Client()
            role_clients[label].force_login(user)
        before = database_fingerprint()
        role_shells = {
            label: client.get(self._shell_url(self.definition))
            for label, client in role_clients.items()
        }
        shell = role_shells["publisher"]

        self.assertEqual(public.status_code, 200)
        self.assertEqual(public.content, payload)
        self.assertEqual(len(payload), LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_BYTES)
        self.assertEqual(hashlib.sha256(payload).hexdigest(), LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256)
        self.assertEqual(sidecar, LIFECYCLE_CLAIM_BOUNDARY_EXPECTED_SIDECAR)
        self.assertEqual(public["Content-Length"], str(len(payload)))
        self.assertEqual(public["ETag"], f'"{LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256}"')
        self.assertEqual(public["Cache-Control"], "public, max-age=31536000, immutable, no-transform")
        self.assertEqual(public["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(public["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("Vary", public)
        self.assertFalse(public.cookies)
        self.assertEqual(verified.contract, LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_ID)
        self.assertEqual(len(verified.statements), 15)
        self.assertEqual(anonymous.status_code, 401)
        self.assertEqual(anonymous["Cache-Control"], "no-store")
        self.assertEqual(anonymous["X-Content-Type-Options"], "nosniff")
        self.assertFalse(anonymous.cookies)
        self.assertEqual(shell.status_code, 200)
        self.assertEqual(shell["Cache-Control"], "no-store")
        html = shell.content.decode("utf-8")
        self.assertIn(f'data-claim-sha256="{LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256}"', html)
        for endpoint in (
            self._open_url(self.definition),
            self._readiness_url(self.definition),
            f"/api/foundation/definitions/{self.definition.pk}/validation-preview/",
            f"/api/foundation/definitions/{self.definition.pk}/validate/",
            f"/api/foundation/definitions/{self.definition.pk}/publish-initial/",
            f"/api/foundation/definitions/{self.definition.pk}/publish-successor/",
        ):
            self.assertIn(endpoint, html)
        for method in ("post", "put", "patch", "delete"):
            self.assertEqual(getattr(Client(), method)(self._shell_url(self.definition)).status_code, 405)
        self.assertEqual(database_fingerprint(), before)

        expected_role_facts = {
            "editor": (True, True, False, False, True),
            "publisher": (True, False, True, True, True),
            "viewer": (True, False, False, False, False),
            "player": (False, False, False, False, False),
            "mixed": (False, False, False, False, False),
        }
        for label, expected in expected_role_facts.items():
            can_read, can_preview, can_validate, can_publish, has_csrf = expected
            with self.subTest(role=label):
                response = role_shells[label]
                self.assertEqual(response.status_code, 200)
                role_html = response.content.decode("utf-8")
                for fact, enabled in (
                    ("read", can_read),
                    ("preview", can_preview),
                    ("validate", can_validate),
                    ("publish", can_publish),
                ):
                    self.assertIn(
                        f'data-can-{fact}="{str(enabled).lower()}"',
                        role_html,
                    )
                self.assertEqual(
                    settings.CSRF_COOKIE_NAME in response.cookies,
                    has_csrf,
                )

        fixed_failure = (
            b"STUDIO_LIFECYCLE_PUBLICATION_CLAIM_BOUNDARY_"
            b"CONTRACT_UNAVAILABLE\n"
        )
        drift_vectors = (
            ("contract", payload[:-1], sidecar),
            ("sidecar", payload, b"0" + sidecar[1:]),
        )
        publisher = role_clients["publisher"]
        for drift_label, drift_payload, drift_sidecar in drift_vectors:

            def drift_read(_path, label):
                return drift_payload if label == "contract" else drift_sidecar

            with self.subTest(drift=drift_label):
                with patch(
                    "production_studio.lifecycle_claim_boundaries._read_exact",
                    side_effect=drift_read,
                ):
                    with self.assertRaises(LifecycleClaimBoundaryContractError):
                        load_lifecycle_claim_boundaries()
                    drift_before = database_fingerprint()
                    responses = (
                        Client().get(
                            "/studio/claim-boundaries/lifecycle-publication/v1/"
                        ),
                        publisher.get(self._shell_url(self.definition)),
                    )
                    for response in responses:
                        self.assertEqual(response.status_code, 503)
                        self.assertEqual(response.content, fixed_failure)
                        self.assertEqual(response["Cache-Control"], "no-store")
                        self.assertEqual(
                            response["X-Content-Type-Options"],
                            "nosniff",
                        )
                        self.assertFalse(response.cookies)
                    self.assertEqual(database_fingerprint(), drift_before)

    def test_initial_draft_uses_optional_preview_then_atomic_publication_without_prior_validate(self):
        editor, csrf = self._session_api(self.editor_user)
        publisher, publisher_csrf = self._session_api(self.publisher_user)
        self.assertNotEqual(
            editor.cookies[settings.SESSION_COOKIE_NAME].value,
            publisher.cookies[settings.SESSION_COOKIE_NAME].value,
        )
        before_preview = database_fingerprint()
        preview = editor.generic(
            "POST",
            f"/api/foundation/definitions/{self.definition.pk}/validation-preview/",
            _canonical_json({"manifest": self.definition.manifest}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(preview.status_code, 200, preview.content)
        self.assertTrue(preview.json()["valid"])
        self.assertEqual(database_fingerprint(), before_preview)
        readiness = publisher.get(self._readiness_url(self.definition))
        self.assertEqual(readiness.status_code, 200)
        readiness_payload = readiness.json()
        self.assertEqual(
            (
                readiness_payload["candidate_kind"],
                readiness_payload["required_next_action"],
            ),
            ("INITIAL", "PREVIEW_OR_INITIAL_PUBLISH"),
        )
        self.definition.refresh_from_db()
        self.assertEqual(self.definition.publication_status, PublicationStatus.DRAFT)
        self.assertIsNone(self.definition.validated_at)
        audit_before = AuditEvent.objects.count()
        operation_id = uuid4()
        body = _canonical_json(
            {
                "locale": "ru",
                "workspace": self.workspace_spec(),
            }
        )
        published = publisher.generic(
            "POST",
            f"/api/foundation/definitions/{self.definition.pk}/publish-initial/",
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{self.definition.manifest_hash}"',
            HTTP_X_CSRFTOKEN=publisher_csrf,
        )
        self.assertEqual(published.status_code, 201, published.content)
        self.definition.refresh_from_db()
        self.assertEqual(self.definition.publication_status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.definition.is_current)
        self.assertEqual(ProjectPublication.objects.filter(definition_version=self.definition).count(), 1)
        self.assertEqual(AuditEvent.objects.count(), audit_before + 3)

    def test_validation_unknown_outcome_allows_only_explicit_same_request_reconciliation(self):
        successor = self._successor()
        operation_id = uuid4()
        audit_before = AuditEvent.objects.count()
        _, fresh = self._validate(successor, operation_id=operation_id)
        self.assertEqual(fresh.status_code, 200, fresh.content)
        self.assertEqual(fresh["X-Foundation-Operation-Replayed"], "false")
        receipt = fresh.data["write_receipt"]
        _, replay = self._validate(successor, operation_id=operation_id)
        self.assertEqual(replay.status_code, 200, replay.content)
        self.assertEqual(replay.data["code"], "WRITE_OPERATION_RECONCILED")
        self.assertEqual(replay["X-Foundation-Operation-Replayed"], "true")
        self.assertEqual(replay.data["write_receipt"], receipt)
        self.assertEqual(AuditEvent.objects.count(), audit_before + 1)
        _, replacement = self._validate(successor, operation_id=uuid4())
        self.assertEqual(replacement.status_code, 409)
        self.assertEqual(AuditEvent.objects.count(), audit_before + 1)
        script = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("memory.unresolvedWrite !== attempt", script)
        self.assertIn("performSealedAttempt(memory.unresolvedWrite, { reconciliation: true })", script)
        self.assertNotIn("setInterval(", script)
        ambiguous = script[
            script.index("function isAmbiguousWriteResponse"):
            script.index("async function handleKnownFailure")
        ]
        self.assertIn("[408, 425, 429].includes(response.status)", ambiguous)
        self.assertIn("response.status >= 500", ambiguous)
        self.assertIn(
            "response.ok && response.status !== 200 && response.status !== 201",
            script,
        )
        attempt_source = script[
            script.index("async function performSealedAttempt"):
            script.index("async function recoverPublication")
        ]
        self.assertGreaterEqual(attempt_source.count("showUnknownOutcome(attempt)"), 3)
        validation_verify = attempt_source.index(
            "await verifyValidationReceipt(response, parsed, attempt)"
        )
        publication_verify = attempt_source.index(
            "await verifyPublicationReceipt(response, parsed, attempt)"
        )
        self.assertLess(
            validation_verify,
            attempt_source.index("clearResolvedAttempt(", validation_verify),
        )
        self.assertLess(
            publication_verify,
            attempt_source.index("clearResolvedAttempt(", publication_verify),
        )
        validation_receipt = script[
            script.index("async function verifyValidationReceipt"):
            script.index("async function verifyPublicationReceipt")
        ]
        self.assertIn(
            "const expectedRequestSha = exactHumanActor(receipt?.actor_identifier)",
            validation_receipt,
        )
        self.assertIn("request?.sha256 !== expectedRequestSha", validation_receipt)
        self.assertIn(
            "!exactKeys(validation, PERSISTED_VALIDATION_KEYS)",
            validation_receipt,
        )
        self.assertIn(
            "exactKeys(item, PERSISTED_DIAGNOSTIC_KEYS)",
            validation_receipt,
        )
        self.assertIn("!exactTimestamp(receipt.occurred_at)", validation_receipt)
        self.assertIn("!exactHumanActor(receipt.actor_identifier)", validation_receipt)
        validation_keys = re.search(
            r"const PERSISTED_VALIDATION_KEYS = Object\.freeze\(\[(.*?)\]\);",
            script,
            re.S,
        )
        diagnostic_keys = re.search(
            r"const PERSISTED_DIAGNOSTIC_KEYS = Object\.freeze\(\[(.*?)\]\);",
            script,
            re.S,
        )
        self.assertIsNotNone(validation_keys)
        self.assertIsNotNone(diagnostic_keys)
        self.assertEqual(
            tuple(re.findall(r'"([a-z0-9_]+)"', validation_keys.group(1))),
            (
                "contract",
                "diagnostics",
                "manifest_sha256",
                "schema_id",
                "schema_version",
                "valid",
            ),
        )
        self.assertEqual(
            tuple(re.findall(r'"([a-z0-9_]+)"', diagnostic_keys.group(1))),
            ("code", "level", "message", "path"),
        )

    def test_fd07_never_labels_standalone_or_validated_initial_as_publishable_and_is_refetched_before_attempt(self):
        predecessor = self._publish_predecessor()
        standalone = create_project_definition_draft(
            project=self.project,
            code=f"C2A-STANDALONE-{uuid4().hex[:10]}",
            version="9.0.0",
            manifest=copy.deepcopy(self.manifest),
            principal=self.editor(actor="c2a-standalone-editor"),
        )
        standalone_readiness = self._api(self.publisher_user).get(self._readiness_url(standalone))
        self.assertEqual(standalone_readiness.status_code, 200)
        standalone_payload = standalone_readiness.json()
        self.assertEqual(standalone_payload["candidate_kind"], "NONE")
        self.assertEqual(standalone_payload["required_next_action"], "NONE")
        self.assertEqual(standalone.supersedes_id, None)
        self.assertTrue(predecessor.is_current)

        _, initial = self._fresh_project_and_draft("validated-initial")
        validated = validate_project_definition(
            initial,
            actor_identifier="c2a-validated-initial-publisher",
            principal=StudioPrincipal.for_role(
                actor_identifier="c2a-validated-initial-publisher",
                role=StudioRole.STUDIO_PUBLISHER,
            ),
        )
        validated_readiness = self._api(self.publisher_user).get(self._readiness_url(validated))
        self.assertEqual(validated_readiness.status_code, 200)
        validated_payload = validated_readiness.json()
        self.assertEqual(validated_payload["candidate_kind"], "NONE")
        self.assertEqual(validated_payload["required_next_action"], "NONE")

        script = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        prepare = script[script.index("async function prepareAttempt()"):script.index("function renderAttempt")]
        self.assertIn("readFreshSnapshot({ rejectDrift: true })", prepare)
        self.assertLess(prepare.index("readFreshSnapshot({ rejectDrift: true })"), prepare.index("randomUUIDv4()"))
        self.assertIn("FD07 не является полномочием", LIFECYCLE_TEMPLATE.read_text(encoding="utf-8"))

    def test_successor_draft_validates_then_fd07_allows_only_exact_successor_publication(self):
        predecessor = self._publish_predecessor()
        successor = self._successor()
        draft_readiness = self._api(self.publisher_user).get(self._readiness_url(successor))
        draft_payload = draft_readiness.json()
        self.assertEqual(
            (
                draft_payload["candidate_kind"],
                draft_payload["required_next_action"],
            ),
            ("SUCCESSOR", "VALIDATE"),
        )
        _, validated = self._validate(successor)
        self.assertEqual(validated.status_code, 200, validated.content)
        successor.refresh_from_db()
        validated_readiness = self._api(self.publisher_user).get(self._readiness_url(successor))
        validated_payload = validated_readiness.json()
        self.assertEqual(
            (
                validated_payload["candidate_kind"],
                validated_payload["required_next_action"],
            ),
            ("SUCCESSOR", "SUCCESSOR_PUBLISH"),
        )
        _, _, published = self._publish_successor(successor)
        self.assertEqual(published.status_code, 201, published.content)
        predecessor.refresh_from_db()
        successor.refresh_from_db()
        self.assertFalse(predecessor.is_current)
        self.assertTrue(successor.is_current)
        self.assertEqual(successor.publication_status, PublicationStatus.PUBLISHED)
        self.assertEqual(successor.supersedes_id, predecessor.pk)

    def test_publication_unknown_outcome_disables_post_and_uses_only_operation_recovery_get(self):
        operation_id, _body, fresh = self._publish_initial()
        self.assertEqual(fresh.status_code, 201, fresh.content)
        publication_count = ProjectPublication.objects.count()
        read_only_baseline = database_fingerprint()
        recovery = self._api(self.publisher_user).get(self._operation_url(self.project, operation_id))
        self.assertEqual(recovery.status_code, 200, recovery.content)
        self.assertEqual(recovery["Idempotency-Replayed"], "true")
        self.assertEqual(recovery.content, fresh.content)
        self.assertEqual(
            recovery.content,
            _canonical_json(recovery.json(), terminal_lf=True),
        )
        self.assertEqual(recovery["ETag"], fresh["ETag"])
        self.assertEqual(recovery["Cache-Control"], "no-store")
        self.assertTrue(
            {"Cookie", "Authorization"}.issubset(
                {item.strip() for item in recovery["Vary"].split(",")}
            )
        )
        self.assertEqual(ProjectPublication.objects.count(), publication_count)
        absent = self._api(self.publisher_user).get(self._operation_url(self.project, uuid4()))
        self.assertEqual(absent.status_code, 404)
        self.assertEqual(ProjectPublication.objects.count(), publication_count)
        self.assertEqual(database_fingerprint(), read_only_baseline)
        script = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        recovery_source = script[
            script.index("async function recoverPublication()"):
            script.index("async function verifyImportedValidationTicket")
        ]
        self.assertIn('method: "GET"', recovery_source)
        self.assertNotIn('method: "POST"', recovery_source)
        publication_receipt = script[
            script.index("async function verifyPublicationReceipt"):
            script.index("function renderVerifiedResult")
        ]
        self.assertIn(
            "const expectedRequestSha = exactHumanActor(receipt?.actor_identifier) && requestShapeValid",
            publication_receipt,
        )
        self.assertIn(
            "receipt?.operation_request_sha256 !== expectedRequestSha",
            publication_receipt,
        )
        self.assertIn(
            "!exactHumanActor(receipt?.actor_identifier)",
            publication_receipt,
        )
        self.assertIn("!exactTimestamp(receipt?.published_at)", publication_receipt)
        self.assertIn(
            'response.headers.get("Cache-Control") !== "no-store"',
            publication_receipt,
        )
        self.assertIn(
            '["authorization|cookie", "accept|authorization|cookie"].includes(receiptVary)',
            publication_receipt,
        )
        self.assertIn("404 означает только отсутствие видимого результата", recovery_source)

    def test_operation_identity_and_receipts_never_enter_browser_persistent_storage(self):
        lifecycle = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        audited = AUDITED_DRAFT_SCRIPT.read_text(encoding="utf-8")
        for forbidden in (
            "localStorage",
            "sessionStorage",
            "indexedDB",
            "caches.open",
            "serviceWorker.register",
        ):
            self.assertNotIn(forbidden, lifecycle)
        storage_writes = re.findall(r"localStorage\s*\.\s*setItem\s*\(([^,\n]+)", audited)
        self.assertEqual({item.strip() for item in storage_writes}, {"STORAGE_KEY"})
        self.assertIn('storagePolicy: "NO_OPERATION_DATA_IN_PERSISTENT_BROWSER_STORAGE"', lifecycle)
        self.assertNotRegex(audited, r"localStorage\s*\.\s*setItem\s*\([^,]*(operation|receipt|manifest|ticket)")

    def test_current_noncurrent_retired_and_unknown_lifecycle_states_render_truthfully(self):
        predecessor = self._publish_predecessor()
        successor = self._successor()
        _, validated = self._validate(successor)
        self.assertEqual(validated.status_code, 200)
        _, _, published = self._publish_successor(successor)
        self.assertEqual(published.status_code, 201)
        predecessor.refresh_from_db()
        successor.refresh_from_db()
        noncurrent = self._api(self.publisher_user).get(
            self._open_url(predecessor)
        )
        self.assertEqual(
            (
                noncurrent.data["publication_status"],
                noncurrent.data["is_current"],
            ),
            ("PUBLISHED", False),
        )
        predecessor.publication_status = PublicationStatus.RETIRED
        models.Model.save(predecessor, update_fields=("publication_status",))
        retired = self._api(self.publisher_user).get(self._open_url(predecessor))
        current = self._api(self.publisher_user).get(self._open_url(successor))
        self.assertEqual((retired.data["publication_status"], retired.data["is_current"]), ("RETIRED", False))
        self.assertEqual((current.data["publication_status"], current.data["is_current"]), ("PUBLISHED", True))
        script = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('Object.freeze(["DRAFT", "VALIDATED", "PUBLISHED", "RETIRED"])', script)
        self.assertIn("!DEFINITION_STATUSES.includes(dto.publication_status)", script)
        self.assertIn(
            'setText("lifecycle-publication-status", definition.publication_status)',
            script,
        )
        self.assertIn(
            'setText("lifecycle-is-current", definition.is_current ? "true" : "false")',
            script,
        )
        unknown = script[
            script.index('setText("lifecycle-project-id", "UNKNOWN_UNVERIFIED")'):
        ]
        self.assertIn(
            'setText("lifecycle-publication-status", "UNKNOWN_UNVERIFIED")',
            unknown,
        )
        self.assertIn('setText("readiness-candidate-kind", "NONE")', unknown)
        self.assertIn('setText("readiness-next-action", "NONE")', unknown)
        self.assertIn('memory.actionKind = "NONE"', script)

    def test_typed_auth_scope_capability_csrf_stale_reuse_and_state_conflicts_are_bounded(self):
        readiness_url = self._readiness_url(self.definition)
        preview_url = f"/api/foundation/definitions/{self.definition.pk}/validation-preview/"
        publish_url = f"/api/foundation/definitions/{self.definition.pk}/publish-initial/"
        preview_body = _canonical_json({"manifest": self.definition.manifest})
        anonymous = APIClient().get(readiness_url)
        self.assertEqual(anonymous.status_code, 401)
        editor = self._api(self.editor_user)
        editor_preview = editor.generic(
            "POST",
            preview_url,
            preview_body,
            content_type="application/json",
        )
        self.assertEqual(editor_preview.status_code, 200)
        editor_publish = editor.post(
            publish_url,
            {"locale": "ru", "workspace": self.workspace_spec()},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_IF_MATCH=f'"{self.definition.manifest_hash}"',
        )
        self.assertEqual(editor_publish.status_code, 403)
        publisher_preview = self._api(self.publisher_user).generic(
            "POST",
            preview_url,
            preview_body,
            content_type="application/json",
        )
        self.assertEqual(publisher_preview.status_code, 403)

        mixed_user = self._user(
            "mixed-role",
            (
                "studio_read_definition",
                "studio_create_definition_draft",
                "studio_clone_definition_draft",
                "studio_save_definition_draft",
                "studio_validate_definition",
                "studio_publish_definition",
            ),
        )
        mixed_shell = Client()
        mixed_shell.force_login(mixed_user)
        mixed_html = mixed_shell.get(self._shell_url(self.definition)).content.decode("utf-8")
        for fact in ("data-can-read", "data-can-preview", "data-can-validate", "data-can-publish"):
            self.assertIn(f'{fact}="false"', mixed_html)
        mixed_preview = self._api(mixed_user).generic(
            "POST",
            preview_url,
            preview_body,
            content_type="application/json",
        )
        self.assertEqual(mixed_preview.status_code, 403)
        viewer = self._api(self.viewer_user)
        self.assertEqual(viewer.get(readiness_url).status_code, 200)
        denied = viewer.post(
            publish_url,
            {"locale": "ru", "workspace": self.workspace_spec()},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_IF_MATCH=f'"{self.definition.manifest_hash}"',
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.data["code"], "STUDIO_CAPABILITY_DENIED")
        out_of_scope = self._api(self.out_of_scope_publisher).get(readiness_url)
        self.assertEqual(out_of_scope.status_code, 404)

        session = APIClient(enforce_csrf_checks=True)
        session.force_login(self.publisher_user)
        body = _canonical_json({"locale": "ru", "workspace": self.workspace_spec()})
        missing_csrf = session.generic(
            "POST",
            publish_url,
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_IF_MATCH=f'"{self.definition.manifest_hash}"',
        )
        self.assertEqual(missing_csrf.status_code, 403)
        stale = self._api(self.publisher_user).generic(
            "POST",
            publish_url,
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_IF_MATCH=f'"{"0" * 64}"',
        )
        self.assertEqual(stale.status_code, 409)
        operation_id, _, fresh = self._publish_initial()
        self.assertEqual(fresh.status_code, 201)
        conflict = self._api(self.publisher_user).generic(
            "POST",
            publish_url,
            body.replace(b'"ru"', b'"en"', 1),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_IF_MATCH=f'"{self.definition.manifest_hash}"',
        )
        self.assertEqual(conflict.status_code, 409)

    def test_package_science_chat_document_prediction_and_recommendation_controls_remain_unavailable(self):
        client = Client()
        client.force_login(self.publisher_user)
        shell = client.get(self._shell_url(self.definition))
        self.assertEqual(shell.status_code, 200)
        html = shell.content.decode("utf-8")
        for selector in (
            "lifecycle-package-control",
            "lifecycle-document-control",
            "lifecycle-chat-control",
            "lifecycle-science-control",
            "lifecycle-prediction-control",
            "lifecycle-recommendation-control",
        ):
            self.assertRegex(html, rf'<button id="{selector}"[^>]*disabled')
        combined = html + LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("/api/studio", combined)
        self.assertNotIn("WebSocket", combined)
        self.assertNotIn("EventSource", combined)

    def test_dirty_busy_unresolved_navigation_and_unload_are_guarded_without_automatic_mutation(self):
        lifecycle = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        audited = AUDITED_DRAFT_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('window.addEventListener("beforeunload"', lifecycle)
        self.assertIn("memory.dirtyInputs", lifecycle)
        self.assertIn("memory.busy", lifecycle)
        self.assertIn("memory.unresolvedWrite", lifecycle)
        self.assertIn("ATTEMPT_INVALIDATED_BY_EDIT", lifecycle)
        self.assertIn("lifecycle-navigation-guard", audited)
        self.assertIn("open-lifecycle-publication", audited)
        for forbidden in ("navigator.sendBeacon", "setInterval(", "fetch(attempt.route, attempt.options)"):
            self.assertNotIn(forbidden, lifecycle)

    def test_publication_requires_human_retained_recovery_ticket_and_busy_unload_is_guarded(self):
        lifecycle = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        template = LIFECYCLE_TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(template, r'id="execute-sealed-attempt"[^>]*disabled')
        self.assertIn("FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1", lifecycle)
        self.assertIn("!memory.ticketRetained", lifecycle)
        self.assertIn("retainTicket(\"download\")", lifecycle)
        self.assertIn("retainTicket(\"exact-copy\")", lifecycle)
        self.assertIn("if (byId(\"ticket-copy-proof\")?.value !== memory.sealedAttempt.ticketText)", lifecycle)
        prepare = lifecycle[
            lifecycle.index("async function prepareAttempt()"):
            lifecycle.index("function renderAttempt")
        ]
        self.assertLess(
            prepare.index("const ticket = await buildTicket(attemptCore)"),
            prepare.index("memory.sealedAttempt = Object.freeze"),
        )
        self.assertLess(
            prepare.index("memory.sealedAttempt = Object.freeze"),
            prepare.index("memory.ticketRetained = false"),
        )
        attempt = lifecycle[
            lifecycle.index("async function performSealedAttempt"):
            lifecycle.index("async function recoverPublication")
        ]
        self.assertLess(
            attempt.index("(!reconciliation && !memory.ticketRetained)"),
            attempt.index("response = await fetch(attempt.route"),
        )
        self.assertIn(
            "!memory.dirtyInputs && !memory.busy && !memory.sealedAttempt && "
            "!memory.unresolvedWrite",
            lifecycle,
        )

    def test_recovery_ticket_and_post_share_one_frozen_attempt_and_edits_require_new_operation(self):
        lifecycle = LIFECYCLE_SCRIPT.read_text(encoding="utf-8")
        expected_keys = {
            "body_byte_length",
            "body_sha256",
            "body_utf8",
            "content_type",
            "contract",
            "contract_version",
            "definition_id",
            "if_match",
            "method",
            "operation_id",
            "operation_kind",
            "project_id",
            "route",
            "ticket_sha256",
        }
        ticket_match = re.search(r"const TICKET_KEYS = Object\.freeze\(\[(.*?)\]\);", lifecycle, re.S)
        self.assertIsNotNone(ticket_match)
        self.assertEqual(set(re.findall(r'"([a-z0-9_]+)"', ticket_match.group(1))), expected_keys)
        self.assertIn("const ticket = Object.freeze({ ...ticketCore, ticket_sha256: ticketSha256 })", lifecycle)
        self.assertIn("memory.sealedAttempt = Object.freeze", lifecycle)
        self.assertIn("memory.sealedAttempt !== attempt", lifecycle)
        self.assertIn("memory.sealedAttempt.ticketText", lifecycle)
        self.assertIn("discardUnsentAttempt(\"ATTEMPT_INVALIDATED_BY_EDIT\")", lifecycle)
        self.assertIn("Любая замена получит новый operation UUID", lifecycle)
        core = {
            "contract": "FOUNDATION_HUMAN_WRITE_RECOVERY_TICKET_V1",
            "contract_version": "1.0.0",
            "operation_kind": "VALIDATE_DEFINITION",
            "operation_id": str(uuid4()),
            "project_id": str(self.project.pk),
            "definition_id": str(self.definition.pk),
            "method": "POST",
            "route": f"/api/foundation/definitions/{self.definition.pk}/validate/",
            "if_match": f'"{self.definition.manifest_hash}"',
            "content_type": "application/json",
            "body_utf8": "{}",
            "body_sha256": hashlib.sha256(b"{}").hexdigest(),
            "body_byte_length": 2,
        }
        first = hashlib.sha256(_canonical_json(core)).hexdigest()
        changed = {**core, "operation_id": str(uuid4())}
        second = hashlib.sha256(_canonical_json(changed)).hexdigest()
        self.assertNotEqual(first, second)


class ProductionStudioLifecyclePublicationBrowserTests(
    _LifecyclePublicationFixture,
    StaticLiveServerTestCase,
):
    host = "localhost"

    def setUp(self) -> None:
        self.make_lifecycle_fixture()

    def _run_browser(
        self,
        *,
        scenario: str,
        definition: ProjectDefinitionVersion,
        predecessor_id: UUID | None = None,
    ) -> dict[str, object]:
        self.client.force_login(self.publisher_user)
        editor_client = Client()
        editor_client.force_login(self.editor_user)
        environment = os.environ.copy()
        environment.update(
            STUDIO_BASE_URL=self.live_server_url,
            STUDIO_DEFINITION_ID=str(definition.pk),
            STUDIO_SESSION_COOKIE_NAME=settings.SESSION_COOKIE_NAME,
            STUDIO_EDITOR_SESSION_COOKIE_VALUE=editor_client.cookies[settings.SESSION_COOKIE_NAME].value,
            STUDIO_PUBLISHER_SESSION_COOKIE_VALUE=self.client.cookies[settings.SESSION_COOKIE_NAME].value,
            STUDIO_EXPECTED_CLAIM_SHA256=LIFECYCLE_CLAIM_BOUNDARY_CONTRACT_SHA256,
            STUDIO_C2A_SCENARIO=scenario,
            STUDIO_PREDECESSOR_ID=str(predecessor_id or ""),
            STUDIO_CDP_TIMEOUT_MS=environment.get("STUDIO_CDP_TIMEOUT_MS", "60000"),
        )
        completed = subprocess.run(
            ["node", str(LIFECYCLE_BROWSER)],
            cwd=PROJECT_ROOT,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"browser stdout:\n{completed.stdout}\nbrowser stderr:\n{completed.stderr}",
        )
        output = [line for line in completed.stdout.splitlines() if line.strip()]
        self.assertTrue(output, completed.stderr)
        return json.loads(output[-1])

    def test_chromium_draft_preview_atomic_initial_publish_recover_and_reload(self):
        result = self._run_browser(
            scenario="test_chromium_draft_preview_atomic_initial_publish_recover_and_reload",
            definition=self.definition,
        )
        self.assertEqual(result["browser_result"], "PASS")
        self.assertEqual(result["scenario"], "test_chromium_draft_preview_atomic_initial_publish_recover_and_reload")
        self.assertEqual(result["definition_id"], str(self.definition.pk))
        self.definition.refresh_from_db()
        self.assertEqual(self.definition.publication_status, PublicationStatus.PUBLISHED)
        self.assertTrue(self.definition.is_current)
        self.assertEqual(ProjectPublication.objects.filter(definition_version=self.definition).count(), 1)

    def test_chromium_successor_validate_publish_lost_response_recovery_and_predecessor_noncurrent(self):
        predecessor = self._publish_predecessor()
        successor = self._successor()
        result = self._run_browser(
            scenario="test_chromium_successor_validate_publish_lost_response_recovery_and_predecessor_noncurrent",
            definition=successor,
            predecessor_id=predecessor.pk,
        )
        self.assertEqual(result["browser_result"], "PASS")
        self.assertEqual(
            result["scenario"],
            "test_chromium_successor_validate_publish_lost_response_recovery_"
            "and_predecessor_noncurrent",
        )
        self.assertEqual(result["definition_id"], str(successor.pk))
        predecessor.refresh_from_db()
        successor.refresh_from_db()
        self.assertFalse(predecessor.is_current)
        self.assertTrue(successor.is_current)
        self.assertEqual(successor.publication_status, PublicationStatus.PUBLISHED)
