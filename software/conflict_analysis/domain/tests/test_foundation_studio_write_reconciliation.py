from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
import threading
from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from domain.enums import AuditAction, AuditActorType, PublicationStatus
from domain.models import (
    AuditEvent,
    Project,
    ProjectDefinitionVersion,
    _canonical_studio_write,
)
from domain.policies import (
    StudioAuthorizationDenied,
    StudioCapability,
    StudioPrincipal,
    studio_principal_from_user,
)
from domain.services.project_definitions import (
    FoundationHumanWriteError,
    FoundationHumanWriteOperation,
    FoundationHumanWriteRequestIdentity,
    FoundationStudioApplicationConflict,
    ProjectDefinitionManifestDiagnostic,
    ProjectDefinitionManifestValidation,
    bootstrap_project_definition_draft_human_write,
    clone_project_definition_draft_human_write,
    create_project_definition_draft,
    create_project_definition_draft_human_write,
    hash_project_definition_manifest_v1,
    save_project_definition_draft,
    save_project_definition_draft_human_write,
    validate_project_definition_human_write,
)
from domain.tests.test_foundation_studio_bootstrap import (
    FD05_HUMAN_WRITE_FAILURE_STAGES,
    FoundationStudioBootstrapMixin,
    manifest_vector,
)


RECEIPT_KEYS = {
    "contract",
    "version",
    "operation",
    "operation_id",
    "audit_event_id",
    "audit_action",
    "actor_type",
    "actor_identifier",
    "project_id",
    "source_definition",
    "before_definition",
    "after_definition",
    "bootstrap_result",
    "validation",
    "request",
    "occurred_at",
    "original_http_status",
}


class FoundationStudioWriteContractMixin(FoundationStudioBootstrapMixin):
    password = "fd05-test-password"

    def make_write_contract(self) -> None:
        self.make_contract()
        user_model = get_user_model()
        self.editor_user = user_model.objects.create_user(
            username=f"fd05-editor-{uuid4().hex}", password=self.password
        )
        self.publisher_user = user_model.objects.create_user(
            username=f"fd05-publisher-{uuid4().hex}", password=self.password
        )
        self.other_editor = user_model.objects.create_user(
            username=f"fd05-other-{uuid4().hex}", password=self.password
        )
        self.viewer_user = user_model.objects.create_user(
            username=f"fd05-viewer-{uuid4().hex}", password=self.password
        )
        permissions = {
            item.codename: item
            for item in Permission.objects.filter(
                content_type__app_label="domain",
                content_type__model="projectdefinitionversion",
            )
        }
        editor_permissions = (
            permissions["studio_read_definition"],
            permissions["studio_create_definition_draft"],
            permissions["studio_clone_definition_draft"],
            permissions["studio_save_definition_draft"],
        )
        self.editor_user.user_permissions.add(*editor_permissions)
        self.other_editor.user_permissions.add(*editor_permissions)
        self.publisher_user.user_permissions.add(
            permissions["studio_read_definition"],
            permissions["studio_validate_definition"],
        )
        self.viewer_user.user_permissions.add(permissions["studio_read_definition"])
        scope = Group.objects.create(name=f"studio-project:{self.project.pk}")
        scope.user_set.add(self.editor_user, self.other_editor, self.publisher_user)
        for name in ("editor_user", "publisher_user", "other_editor", "viewer_user"):
            user = user_model.objects.get(pk=getattr(self, name).pk)
            setattr(self, name, user)
        self.editor_principal = studio_principal_from_user(self.editor_user)
        self.publisher_principal = studio_principal_from_user(self.publisher_user)
        self.other_principal = studio_principal_from_user(self.other_editor)
        self.client = APIClient()

    @staticmethod
    def raw(payload: object) -> bytes:
        return json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

    def identity(
        self,
        operation: FoundationHumanWriteOperation,
        *,
        operation_id: UUID,
        actor: str,
        project_id: UUID,
        target_id: UUID,
        raw: bytes,
        route: str,
        source_id: UUID | None = None,
        if_match: str | None = None,
    ) -> FoundationHumanWriteRequestIdentity:
        method = "PUT" if operation is FoundationHumanWriteOperation.SAVE_DRAFT else "POST"
        return FoundationHumanWriteRequestIdentity.build(
            operation=operation,
            operation_id=operation_id,
            method=method,
            route=route,
            actor_identifier=actor,
            project_id=project_id,
            source_definition_id=source_id,
            target_definition_id=target_id,
            content_type="application/json",
            raw_input_sha256=hashlib.sha256(raw).hexdigest(),
            raw_input_byte_length=len(raw),
            if_match=if_match,
        )

    def direct_draft(self, *, code: str | None = None, version: str | None = None):
        return create_project_definition_draft(
            project=self.project,
            definition_id=uuid4(),
            code=code or f"FD05-{uuid4().hex}",
            version=version or f"1.0.{ProjectDefinitionVersion.objects.count() + 1}",
            manifest=copy.deepcopy(self.manifest),
            principal=self.editor_principal,
        )

    def create_write(
        self,
        *,
        operation_id: UUID | None = None,
        definition_id: UUID | None = None,
        code: str | None = None,
        version: str | None = None,
        raw: bytes | None = None,
        principal=None,
        inject_failure_at: str | None = None,
    ):
        operation_id = operation_id or uuid4()
        definition_id = definition_id or uuid4()
        code = code or f"FD05-CREATE-{uuid4().hex}"
        version = version or f"2.0.{ProjectDefinitionVersion.objects.count() + 1}"
        principal = principal or self.editor_principal
        payload = {
            "id": str(definition_id),
            "code": code,
            "version": version,
            "manifest": copy.deepcopy(self.manifest),
            "semantic_version": "1.0.0",
            "construct_version": "1.0.0",
        }
        raw = raw if raw is not None else self.raw(payload)
        request = self.identity(
            FoundationHumanWriteOperation.CREATE_DRAFT,
            operation_id=operation_id,
            actor=principal.actor_identifier,
            project_id=self.project.pk,
            target_id=definition_id,
            raw=raw,
            route=f"/api/foundation/projects/{self.project.pk}/definitions/",
        )
        return create_project_definition_draft_human_write(
            request_identity=request,
            project=self.project,
            definition_id=definition_id,
            code=code,
            version=version,
            manifest=copy.deepcopy(self.manifest),
            principal=principal,
            inject_failure_at=inject_failure_at,
        )

    def save_write(
        self,
        definition,
        *,
        operation_id: UUID | None = None,
        expected_hash: str | None = None,
        manifest: dict | None = None,
        principal=None,
        inject_failure_at: str | None = None,
    ):
        operation_id = operation_id or uuid4()
        principal = principal or self.editor_principal
        expected_hash = expected_hash or definition.manifest_hash
        manifest = copy.deepcopy(manifest or definition.manifest)
        raw = self.raw({"manifest": manifest})
        request = self.identity(
            FoundationHumanWriteOperation.SAVE_DRAFT,
            operation_id=operation_id,
            actor=principal.actor_identifier,
            project_id=definition.project_id,
            target_id=definition.pk,
            raw=raw,
            route=f"/api/foundation/definitions/{definition.pk}/draft/",
            if_match=expected_hash,
        )
        return save_project_definition_draft_human_write(
            definition,
            request_identity=request,
            expected_manifest_hash=expected_hash,
            manifest=manifest,
            principal=principal,
            inject_failure_at=inject_failure_at,
        )

    def validate_write(
        self,
        definition,
        *,
        operation_id: UUID | None = None,
        expected_hash: str | None = None,
        principal=None,
        inject_failure_at: str | None = None,
    ):
        operation_id = operation_id or uuid4()
        principal = principal or self.publisher_principal
        expected_hash = expected_hash or definition.manifest_hash
        raw = b"{}"
        request = self.identity(
            FoundationHumanWriteOperation.VALIDATE_DEFINITION,
            operation_id=operation_id,
            actor=principal.actor_identifier,
            project_id=definition.project_id,
            target_id=definition.pk,
            raw=raw,
            route=f"/api/foundation/definitions/{definition.pk}/validate/",
            if_match=expected_hash,
        )
        return validate_project_definition_human_write(
            definition,
            request_identity=request,
            expected_manifest_hash=expected_hash,
            principal=principal,
            inject_failure_at=inject_failure_at,
        )

    def assert_receipt(self, result, *, operation, actor, action, status) -> dict:
        receipt = result.receipt.as_dict()
        self.assertEqual(set(receipt), RECEIPT_KEYS)
        self.assertEqual(receipt["contract"], "FOUNDATION_AUDITED_DEFINITION_WRITE_V1")
        self.assertEqual(receipt["version"], "1.0.0")
        self.assertEqual(receipt["operation"], operation.value)
        self.assertEqual(receipt["operation_id"], receipt["audit_event_id"])
        self.assertEqual(receipt["operation_id"], str(result.audit_event.pk))
        self.assertEqual(receipt["actor_type"], AuditActorType.HUMAN)
        self.assertEqual(receipt["actor_identifier"], actor)
        self.assertEqual(receipt["audit_action"], action)
        self.assertEqual(receipt["original_http_status"], status)
        self.assertEqual(
            set(receipt["request"]),
            {
                "contract",
                "sha256",
                "raw_input_sha256",
                "raw_input_byte_length",
                "if_match",
            },
        )
        self.assertEqual(
            receipt["request"]["contract"],
            "FOUNDATION_HUMAN_WRITE_REQUEST_IDENTITY_V1",
        )
        self.assertEqual(len(receipt["request"]["sha256"]), 64)
        self.assertEqual(
            result.receipt.sha256,
            hashlib.sha256(self.raw(receipt)).hexdigest(),
        )
        event = AuditEvent.objects.get(pk=result.audit_event.pk)
        self.assertEqual(event.code, f"AUD-DEF-OP-{event.pk.hex}")
        self.assertEqual(event.action, action)
        self.assertEqual(event.actor_type, AuditActorType.HUMAN)
        self.assertEqual(event.actor_identifier, actor)
        self.assertEqual(event.before, receipt["before_definition"])
        self.assertEqual(event.after, {"foundation_human_operation": receipt})
        return receipt

    def http(self, user, method: str, url: str, raw: bytes, *, key=None, token=None, **headers):
        self.client.force_authenticate(user)
        if key is not None:
            headers["HTTP_IDEMPOTENCY_KEY"] = str(key)
        if token is not None:
            headers["HTTP_IF_MATCH"] = token
        return self.client.generic(
            method,
            url,
            raw,
            content_type="application/json",
            **headers,
        )


class FoundationStudioWriteReconciliationTests(
    FoundationStudioWriteContractMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_write_contract()

    def test_all_five_operations_emit_exact_immutable_human_receipts(self):
        bootstrap_project_id = uuid4()
        bootstrap_definition_id = uuid4()
        bootstrap_manifest = copy.deepcopy(self.manifest)
        bootstrap_manifest["project"].update(
            {"id": str(bootstrap_project_id), "code": "FD05-BOOTSTRAP", "version": "1.0.0"}
        )
        bootstrap_manifest["actors"][0]["order"] = -0.0
        bootstrap_metadata = {
            "negative_zero": -0.0,
            "nested": {"negative_zero": -0.0},
        }
        bootstrap_raw = self.raw(
            {
                "project": {
                    "id": str(bootstrap_project_id),
                    "metadata": bootstrap_metadata,
                },
                "definition": {"id": str(bootstrap_definition_id)},
            }
        )
        bootstrap_request = self.identity(
            FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
            operation_id=uuid4(),
            actor=self.editor_principal.actor_identifier,
            project_id=bootstrap_project_id,
            target_id=bootstrap_definition_id,
            raw=bootstrap_raw,
            route="/api/foundation/projects/bootstrap-first-draft/",
        )
        bootstrap_kwargs = {
            "request_identity": bootstrap_request,
            "project_id": bootstrap_project_id,
            "project_code": "FD05-BOOTSTRAP",
            "project_version": "1.0.0",
            "project_name": "FD05 bootstrap",
            "project_metadata": bootstrap_metadata,
            "definition_id": bootstrap_definition_id,
            "definition_code": "FD05-BOOTSTRAP-DRAFT",
            "definition_version": "1.0.0",
            "manifest": bootstrap_manifest,
            "principal": self.editor_principal,
            "user": self.editor_user,
        }
        bootstrap = bootstrap_project_definition_draft_human_write(
            **bootstrap_kwargs
        )
        persisted_bootstrap_definition = ProjectDefinitionVersion.objects.get(
            pk=bootstrap_definition_id
        )
        fresh_order = bootstrap.definition.manifest["actors"][0]["order"]
        persisted_order = persisted_bootstrap_definition.manifest["actors"][0][
            "order"
        ]
        self.assertEqual(fresh_order, 0.0)
        self.assertEqual(persisted_order, 0.0)
        self.assertEqual(math.copysign(1.0, fresh_order), 1.0)
        self.assertEqual(math.copysign(1.0, persisted_order), 1.0)
        self.assertEqual(
            bootstrap.definition.manifest,
            persisted_bootstrap_definition.manifest,
        )
        self.assertEqual(
            persisted_bootstrap_definition.manifest_hash,
            hash_project_definition_manifest_v1(
                persisted_bootstrap_definition.manifest,
                project=persisted_bootstrap_definition.project,
            ),
        )
        roundtrip = save_project_definition_draft(
            persisted_bootstrap_definition,
            manifest=copy.deepcopy(persisted_bootstrap_definition.manifest),
            expected_manifest_hash=persisted_bootstrap_definition.manifest_hash,
            principal=self.editor_principal,
        )
        self.assertEqual(
            roundtrip.manifest_hash,
            persisted_bootstrap_definition.manifest_hash,
        )
        bootstrap_replay = bootstrap_project_definition_draft_human_write(
            **bootstrap_kwargs
        )
        self.assertTrue(bootstrap_replay.replayed)
        self.assertEqual(
            bootstrap_replay.receipt.as_dict(),
            bootstrap.receipt.as_dict(),
        )
        self.assertEqual(bootstrap_replay.receipt.sha256, bootstrap.receipt.sha256)
        persisted_bootstrap_project = Project.objects.get(pk=bootstrap_project_id)
        receipt_metadata = bootstrap.receipt.as_dict()["bootstrap_result"][
            "project"
        ]["metadata"]
        self.assertEqual(bootstrap.project.metadata, persisted_bootstrap_project.metadata)
        self.assertEqual(bootstrap.project.metadata, receipt_metadata)
        bootstrap_event = AuditEvent.objects.get(pk=bootstrap_request.operation_id)
        bootstrap_event.refresh_from_db()
        self.assertEqual(
            bootstrap_event.after["foundation_human_operation"],
            bootstrap.receipt.as_dict(),
        )
        created = self.create_write()
        source = created.definition
        clone_id = uuid4()
        clone_raw = self.raw({"id": str(clone_id), "code": "FD05-CLONE", "version": "3.0.0"})
        clone_request = self.identity(
            FoundationHumanWriteOperation.CLONE_DRAFT,
            operation_id=uuid4(),
            actor=self.editor_principal.actor_identifier,
            project_id=self.project.pk,
            source_id=source.pk,
            target_id=clone_id,
            raw=clone_raw,
            route=f"/api/foundation/definitions/{source.pk}/clone/",
            if_match=source.manifest_hash,
        )
        cloned = clone_project_definition_draft_human_write(
            source,
            request_identity=clone_request,
            expected_manifest_hash=source.manifest_hash,
            definition_id=clone_id,
            code="FD05-CLONE",
            version="3.0.0",
            principal=self.editor_principal,
        )
        changed = copy.deepcopy(cloned.definition.manifest)
        changed["project"]["description"] = "FD05 saved snapshot"
        saved = self.save_write(cloned.definition, manifest=changed)
        validated = self.validate_write(saved.definition)

        receipts = (
            self.assert_receipt(bootstrap, operation=FoundationHumanWriteOperation.BOOTSTRAP_DRAFT, actor=self.editor_principal.actor_identifier, action=AuditAction.CREATE, status=201),
            self.assert_receipt(created, operation=FoundationHumanWriteOperation.CREATE_DRAFT, actor=self.editor_principal.actor_identifier, action=AuditAction.CREATE, status=201),
            self.assert_receipt(cloned, operation=FoundationHumanWriteOperation.CLONE_DRAFT, actor=self.editor_principal.actor_identifier, action=AuditAction.CREATE, status=201),
            self.assert_receipt(saved, operation=FoundationHumanWriteOperation.SAVE_DRAFT, actor=self.editor_principal.actor_identifier, action=AuditAction.UPDATE, status=200),
            self.assert_receipt(validated, operation=FoundationHumanWriteOperation.VALIDATE_DEFINITION, actor=self.publisher_principal.actor_identifier, action=AuditAction.VALIDATE, status=200),
        )
        self.assertEqual(len({item["operation_id"] for item in receipts}), 5)
        self.assertEqual(AuditEvent.objects.count(), 5)
        self.assertIsNone(receipts[0]["before_definition"])
        self.assertIsNotNone(receipts[0]["bootstrap_result"])
        self.assertIsNotNone(receipts[2]["source_definition"])
        self.assertIsNotNone(receipts[3]["before_definition"])
        self.assertIsNotNone(receipts[4]["validation"])

    def test_operation_key_is_required_and_validated_before_body_capture(self):
        url = f"/api/foundation/projects/{self.project.pk}/definitions/"
        raw = b'{"body":"must-not-be-read"}'
        baseline = (ProjectDefinitionVersion.objects.count(), AuditEvent.objects.count())
        from unittest.mock import patch

        with patch(
            "domain.api.studio_definitions.capture_http_json",
            side_effect=AssertionError("body captured before operation-key admission"),
        ):
            missing = self.http(self.editor_user, "POST", url, raw)
            malformed = self.http(self.editor_user, "POST", url, raw, key="NOT-A-UUID")
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["code"], "WRITE_OPERATION_KEY_REQUIRED")
        self.assertEqual(malformed.status_code, 400)
        self.assertEqual(malformed.json()["code"], "WRITE_OPERATION_KEY_INVALID")
        self.assertEqual(
            (ProjectDefinitionVersion.objects.count(), AuditEvent.objects.count()), baseline
        )

    def test_create_clone_envelopes_and_preselected_ids_are_exact(self):
        create_url = f"/api/foundation/projects/{self.project.pk}/definitions/"
        surrogate_project_id = uuid4()
        surrogate_definition_id = uuid4()
        surrogate_manifest = copy.deepcopy(self.manifest)
        surrogate_manifest["project"].update(
            {
                "id": str(surrogate_project_id),
                "code": "FD05-UNICODE-REJECT",
                "version": "1.0.0",
            }
        )
        surrogate_payload = {
            "project": {
                "id": str(surrogate_project_id),
                "code": "FD05-UNICODE-REJECT",
                "version": "1.0.0",
                "name": "Unicode rejection",
                "description": "Nested metadata must be scalar-safe.",
                "metadata": {"nested": {"invalid": "\ud800"}},
            },
            "definition": {
                "id": str(surrogate_definition_id),
                "code": "FD05-UNICODE-REJECT-DRAFT",
                "version": "1.0.0",
                "manifest": surrogate_manifest,
                "semantic_version": "1.0.0",
                "construct_version": "1.0.0",
            },
        }
        baseline = (
            Project.objects.count(),
            ProjectDefinitionVersion.objects.count(),
            AuditEvent.objects.count(),
        )
        surrogate = self.http(
            self.editor_user,
            "POST",
            "/api/foundation/projects/bootstrap-first-draft/",
            json.dumps(
                surrogate_payload,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8"),
            key=uuid4(),
        )
        self.assertEqual(
            (surrogate.status_code, surrogate.json()["code"]),
            (400, "AUTHORING_ENVELOPE_INVALID"),
        )
        self.assertEqual(
            (
                Project.objects.count(),
                ProjectDefinitionVersion.objects.count(),
                AuditEvent.objects.count(),
            ),
            baseline,
        )
        self.assertFalse(Project.objects.filter(pk=surrogate_project_id).exists())

        definition_id = uuid4()
        exact = {
            "id": str(definition_id),
            "code": "FD05-HTTP-CREATE",
            "version": "4.0.0",
            "manifest": self.manifest,
            "semantic_version": "1.0.0",
            "construct_version": "1.0.0",
        }
        for invalid in ({**exact, "extra": True}, {k: v for k, v in exact.items() if k != "id"}):
            response = self.http(self.editor_user, "POST", create_url, self.raw(invalid), key=uuid4())
            self.assertEqual((response.status_code, response.json()["code"]), (400, "AUTHORING_ENVELOPE_INVALID"))
        created = self.http(self.editor_user, "POST", create_url, self.raw(exact), key=uuid4())
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["id"], str(definition_id))
        clone_id = uuid4()
        clone_url = f"/api/foundation/definitions/{definition_id}/clone/"
        clone_payload = {"id": str(clone_id), "code": "FD05-HTTP-CLONE", "version": "4.1.0"}
        rejected = self.http(self.editor_user, "POST", clone_url, self.raw({**clone_payload, "extra": 1}), key=uuid4(), token=f'"{created.json()["manifest_hash"]}"')
        self.assertEqual((rejected.status_code, rejected.json()["code"]), (400, "AUTHORING_ENVELOPE_INVALID"))
        cloned = self.http(self.editor_user, "POST", clone_url, self.raw(clone_payload), key=uuid4(), token=f'"{created.json()["manifest_hash"]}"')
        self.assertEqual(cloned.status_code, 201)
        self.assertEqual(cloned.json()["id"], str(clone_id))

    def test_clone_save_validate_require_exact_strong_if_match(self):
        definition = self.direct_draft(code="FD05-TOKEN-SOURCE", version="5.0.0")
        cases = (
            ("POST", f"/api/foundation/definitions/{definition.pk}/clone/", self.raw({"id": str(uuid4()), "code": "TOKEN-CLONE", "version": "5.1.0"})),
            ("PUT", f"/api/foundation/definitions/{definition.pk}/draft/", self.raw({"manifest": definition.manifest})),
            ("POST", f"/api/foundation/definitions/{definition.pk}/validate/", b"{}"),
        )
        for method, url, raw in cases:
            missing = self.http(self.editor_user if "validate" not in url else self.publisher_user, method, url, raw, key=uuid4())
            self.assertEqual((missing.status_code, missing.json()["code"]), (400, "IF_MATCH_REQUIRED"))
            weak = self.http(self.editor_user if "validate" not in url else self.publisher_user, method, url, raw, key=uuid4(), token=f'W/"{definition.manifest_hash}"')
            self.assertEqual((weak.status_code, weak.json()["code"]), (400, "IF_MATCH_INVALID"))
        self.assertFalse(AuditEvent.objects.exists())

    def test_exact_retry_reconciles_before_stale_lifecycle_or_duplicate_checks(self):
        operation_id = uuid4()
        created = self.create_write(operation_id=operation_id)
        replay = self.create_write(
            operation_id=operation_id,
            definition_id=created.definition.pk,
            code=created.definition.code,
            version=created.definition.version,
        )
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.receipt.as_dict(), created.receipt.as_dict())

        clone_id, clone_operation_id = uuid4(), uuid4()
        clone_code, clone_version = "FD05-REPLAY-CLONE", "5.0.1"
        clone_raw = self.raw(
            {
                "id": str(clone_id),
                "code": clone_code,
                "version": clone_version,
            }
        )
        clone_request = self.identity(
            FoundationHumanWriteOperation.CLONE_DRAFT,
            operation_id=clone_operation_id,
            actor=self.editor_principal.actor_identifier,
            project_id=self.project.pk,
            source_id=created.definition.pk,
            target_id=clone_id,
            raw=clone_raw,
            route=f"/api/foundation/definitions/{created.definition.pk}/clone/",
            if_match=created.definition.manifest_hash,
        )
        clone_kwargs = {
            "request_identity": clone_request,
            "expected_manifest_hash": created.definition.manifest_hash,
            "definition_id": clone_id,
            "code": clone_code,
            "version": clone_version,
            "principal": self.editor_principal,
        }
        cloned = clone_project_definition_draft_human_write(
            created.definition,
            **clone_kwargs,
        )
        clone_replay = clone_project_definition_draft_human_write(
            created.definition,
            **clone_kwargs,
        )
        self.assertTrue(clone_replay.replayed)
        self.assertEqual(clone_replay.receipt.as_dict(), cloned.receipt.as_dict())
        self.assertEqual(ProjectDefinitionVersion.objects.filter(pk=clone_id).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(pk=clone_operation_id).count(), 1)

        save_operation_id = uuid4()
        saved_manifest = copy.deepcopy(cloned.definition.manifest)
        saved_manifest["project"]["description"] = "FD05 exact save replay"
        saved = self.save_write(
            cloned.definition,
            operation_id=save_operation_id,
            expected_hash=cloned.definition.manifest_hash,
            manifest=saved_manifest,
        )
        save_replay = self.save_write(
            cloned.definition,
            operation_id=save_operation_id,
            expected_hash=cloned.definition.manifest_hash,
            manifest=saved_manifest,
        )
        self.assertTrue(save_replay.replayed)
        self.assertEqual(save_replay.receipt.as_dict(), saved.receipt.as_dict())
        self.assertEqual(AuditEvent.objects.filter(pk=save_operation_id).count(), 1)

        validate_id = uuid4()
        validated = self.validate_write(created.definition, operation_id=validate_id)
        validate_replay = self.validate_write(
            created.definition,
            operation_id=validate_id,
            expected_hash=created.definition.manifest_hash,
        )
        self.assertTrue(validate_replay.replayed)
        self.assertEqual(validate_replay.receipt.as_dict(), validated.receipt.as_dict())

        bootstrap_project_id, bootstrap_definition_id = uuid4(), uuid4()
        bootstrap_manifest = copy.deepcopy(self.manifest)
        bootstrap_manifest["project"].update(
            {
                "id": str(bootstrap_project_id),
                "code": "FD05-REPLAY-SCOPE",
                "version": "1.0.0",
            }
        )
        bootstrap_raw = self.raw(
            {
                "project": str(bootstrap_project_id),
                "definition": str(bootstrap_definition_id),
            }
        )
        bootstrap_request = self.identity(
            FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
            operation_id=uuid4(),
            actor=self.editor_principal.actor_identifier,
            project_id=bootstrap_project_id,
            target_id=bootstrap_definition_id,
            raw=bootstrap_raw,
            route="/api/foundation/projects/bootstrap-first-draft/",
        )
        bootstrap_kwargs = {
            "request_identity": bootstrap_request,
            "project_id": bootstrap_project_id,
            "project_code": "FD05-REPLAY-SCOPE",
            "project_version": "1.0.0",
            "project_name": "FD05 replay current scope",
            "project_metadata": {},
            "definition_id": bootstrap_definition_id,
            "definition_code": "FD05-REPLAY-SCOPE-DRAFT",
            "definition_version": "1.0.0",
            "manifest": bootstrap_manifest,
            "principal": self.editor_principal,
            "user": self.editor_user,
        }
        bootstrap = bootstrap_project_definition_draft_human_write(
            **bootstrap_kwargs
        )
        self.assertEqual(
            bootstrap.receipt.actor_identifier,
            self.editor_principal.actor_identifier,
        )
        self.assertTrue(
            bootstrap.scope_group.user_set.filter(pk=self.editor_user.pk).exists()
        )
        bootstrap.scope_group.user_set.remove(self.editor_user)
        with self.assertRaises(StudioAuthorizationDenied):
            bootstrap_project_definition_draft_human_write(**bootstrap_kwargs)
        for out_of_scope_key in (bootstrap_request.operation_id, uuid4()):
            with self.subTest(out_of_scope_key=out_of_scope_key):
                out_of_scope_request = self.identity(
                    FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
                    operation_id=out_of_scope_key,
                    actor=self.other_principal.actor_identifier,
                    project_id=bootstrap_project_id,
                    target_id=bootstrap_definition_id,
                    raw=bootstrap_raw,
                    route="/api/foundation/projects/bootstrap-first-draft/",
                )
                with self.assertRaises(StudioAuthorizationDenied):
                    bootstrap_project_definition_draft_human_write(
                        **{
                            **bootstrap_kwargs,
                            "request_identity": out_of_scope_request,
                            "principal": self.other_principal,
                            "user": self.other_editor,
                        }
                    )
        bootstrap.scope_group.user_set.add(self.editor_user)
        bootstrap_replay = bootstrap_project_definition_draft_human_write(
            **bootstrap_kwargs
        )
        self.assertTrue(bootstrap_replay.replayed)
        self.assertEqual(
            bootstrap_replay.receipt.as_dict(),
            bootstrap.receipt.as_dict(),
        )
        self.assertEqual(AuditEvent.objects.count(), 5)

    def test_operation_key_reuse_changed_actor_route_target_body_or_token_is_typed(self):
        operation_id = uuid4()
        created = self.create_write(operation_id=operation_id)
        mutations = (
            {"principal": self.other_principal},
            {"raw": self.raw({"same": "semantic value", "spacing": "changed"})},
            {"definition_id": uuid4()},
        )
        for kwargs in mutations:
            with self.subTest(kwargs=sorted(kwargs)):
                call = {
                    "definition_id": created.definition.pk,
                    "code": created.definition.code,
                    "version": created.definition.version,
                    **kwargs,
                }
                with self.assertRaises(FoundationStudioApplicationConflict) as caught:
                    self.create_write(
                        operation_id=operation_id,
                        **call,
                    )
                self.assertEqual(caught.exception.conflict_code, "WRITE_OPERATION_KEY_REUSED")

        original_payload = {
            "id": str(created.definition.pk),
            "code": created.definition.code,
            "version": created.definition.version,
            "manifest": copy.deepcopy(self.manifest),
            "semantic_version": "1.0.0",
            "construct_version": "1.0.0",
        }
        changed_route_request = self.identity(
            FoundationHumanWriteOperation.CREATE_DRAFT,
            operation_id=operation_id,
            actor=self.editor_principal.actor_identifier,
            project_id=self.project.pk,
            target_id=created.definition.pk,
            raw=self.raw(original_payload),
            route=(
                f"/api/foundation/projects/{self.project.pk}/"
                "definitions/alternate/"
            ),
        )
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            create_project_definition_draft_human_write(
                request_identity=changed_route_request,
                project=self.project,
                definition_id=created.definition.pk,
                code=created.definition.code,
                version=created.definition.version,
                manifest=copy.deepcopy(self.manifest),
                principal=self.editor_principal,
            )
        self.assertEqual(caught.exception.conflict_code, "WRITE_OPERATION_KEY_REUSED")

        source = self.direct_draft(code="FD05-KEY-TOKEN", version="5.5.0")
        clone_id = uuid4()
        clone_key = uuid4()
        raw = self.raw({"id": str(clone_id), "code": "FD05-KEY-CLONE", "version": "5.6.0"})
        request = self.identity(FoundationHumanWriteOperation.CLONE_DRAFT, operation_id=clone_key, actor=self.editor_principal.actor_identifier, project_id=self.project.pk, source_id=source.pk, target_id=clone_id, raw=raw, route=f"/api/foundation/definitions/{source.pk}/clone/", if_match=source.manifest_hash)
        clone_project_definition_draft_human_write(source, request_identity=request, expected_manifest_hash=source.manifest_hash, definition_id=clone_id, code="FD05-KEY-CLONE", version="5.6.0", principal=self.editor_principal)
        changed_token = "0" * 64
        changed_request = self.identity(FoundationHumanWriteOperation.CLONE_DRAFT, operation_id=clone_key, actor=self.editor_principal.actor_identifier, project_id=self.project.pk, source_id=source.pk, target_id=clone_id, raw=raw, route=f"/api/foundation/definitions/{source.pk}/clone/", if_match=changed_token)
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            clone_project_definition_draft_human_write(source, request_identity=changed_request, expected_manifest_hash=changed_token, definition_id=clone_id, code="FD05-KEY-CLONE", version="5.6.0", principal=self.editor_principal)
        self.assertEqual(caught.exception.conflict_code, "WRITE_OPERATION_KEY_REUSED")

        other_project_id = uuid4()
        other_manifest = copy.deepcopy(self.manifest)
        other_manifest["project"].update(
            {
                "id": str(other_project_id),
                "code": "FD05-GLOBAL-KEY-B",
                "version": "1.0.0",
            }
        )
        other_project = Project.objects.create(
            id=other_project_id,
            code="FD05-GLOBAL-KEY-B",
            version="1.0.0",
            name="Global operation-key collision target",
            description="",
            metadata={},
        )
        other_definition = create_project_definition_draft(
            project=other_project,
            definition_id=uuid4(),
            code="FD05-GLOBAL-KEY-B-DRAFT",
            version="1.0.0",
            manifest=other_manifest,
            principal=self.editor_principal,
        )
        changed_manifest = copy.deepcopy(other_definition.manifest)
        changed_manifest["project"]["description"] = "must roll back"
        collision_request = self.identity(
            FoundationHumanWriteOperation.SAVE_DRAFT,
            operation_id=operation_id,
            actor=self.editor_principal.actor_identifier,
            project_id=other_project.pk,
            target_id=other_definition.pk,
            raw=self.raw({"manifest": changed_manifest}),
            route=f"/api/foundation/definitions/{other_definition.pk}/draft/",
            if_match=other_definition.manifest_hash,
        )
        baseline_hash = other_definition.manifest_hash
        baseline_audits = AuditEvent.objects.count()
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            save_project_definition_draft_human_write(
                other_definition,
                request_identity=collision_request,
                expected_manifest_hash=other_definition.manifest_hash,
                manifest=changed_manifest,
                principal=self.editor_principal,
            )
        self.assertEqual(caught.exception.conflict_code, "WRITE_OPERATION_KEY_REUSED")
        other_definition.refresh_from_db()
        self.assertEqual(other_definition.manifest_hash, baseline_hash)
        self.assertEqual(AuditEvent.objects.count(), baseline_audits)

    def test_create_clone_identity_conflicts_have_stable_precedence(self):
        existing = self.direct_draft(code="FD05-CONFLICT-CODE", version="6.0.0")
        cases = (
            (existing.pk, existing.code, existing.version, "DEFINITION_ID_CONFLICT"),
            (uuid4(), existing.code, "6.1.0", "DEFINITION_CODE_CONFLICT"),
            (uuid4(), "FD05-CONFLICT-OTHER", existing.version, "DEFINITION_VERSION_CONFLICT"),
        )
        for definition_id, code, version, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(FoundationStudioApplicationConflict) as caught:
                    self.create_write(definition_id=definition_id, code=code, version=version)
                self.assertEqual(caught.exception.conflict_code, expected)
        self.assertFalse(AuditEvent.objects.exists())

    def test_save_and_validate_stale_or_non_draft_outcomes_are_typed(self):
        stale = self.direct_draft(code="FD05-STALE", version="7.0.0")
        opened_hash = stale.manifest_hash
        updated = copy.deepcopy(stale.manifest)
        updated["project"]["description"] = "changed before stale write"
        save_project_definition_draft(stale, manifest=updated, expected_manifest_hash=opened_hash, principal=self.editor_principal)
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            self.save_write(stale, expected_hash=opened_hash)
        self.assertEqual(caught.exception.conflict_code, "DRAFT_STALE")

        validated_target = self.direct_draft(code="FD05-ALREADY-VALIDATED", version="7.1.0")
        validated_target = self.validate_write(validated_target).definition
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            self.validate_write(validated_target, operation_id=uuid4())
        self.assertEqual(caught.exception.conflict_code, "DEFINITION_ALREADY_VALIDATED")

        lifecycle_time = timezone.now()
        retired_target = ProjectDefinitionVersion(
            project=self.project,
            code="FD05-RETIRED",
            version="7.2.0",
            manifest=copy.deepcopy(self.manifest),
            manifest_hash=hash_project_definition_manifest_v1(
                self.manifest,
                project=self.project,
            ),
            schema_version="1.0.0",
            semantic_version="1.0.0",
            construct_version="1.0.0",
            publication_status=PublicationStatus.RETIRED,
            validated_at=lifecycle_time,
            validated_by=self.publisher_principal.actor_identifier,
            validation_result={"valid": True},
            published_at=lifecycle_time,
            published_by=self.publisher_principal.actor_identifier,
        )
        with _canonical_studio_write("definition"):
            retired_target.save(force_insert=True)
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            self.validate_write(retired_target, operation_id=uuid4())
        self.assertEqual(caught.exception.conflict_code, "DEFINITION_NOT_DRAFT")

    def test_validate_uses_fd01_policy_report_and_replay_is_immutable(self):
        definition = self.direct_draft(code="FD05-VALIDATION-POLICY", version="8.0.0")
        operation_id = uuid4()
        from unittest.mock import patch

        with patch(
            "domain.policies.validate_project_definition_manifest_policy",
            wraps=__import__("domain.policies", fromlist=["validate_project_definition_manifest_policy"]).validate_project_definition_manifest_policy,
        ) as policy:
            result = self.validate_write(definition, operation_id=operation_id)
        self.assertEqual(policy.call_count, 1)
        self.assertEqual(result.receipt.validation, result.definition.validation_result)
        replay = self.validate_write(definition, operation_id=operation_id)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.receipt.as_dict(), result.receipt.as_dict())

        invalid = self.direct_draft(code="FD05-INVALID", version="8.1.0")
        invalid_validation = ProjectDefinitionManifestValidation(
            valid=False,
            manifest_sha256="",
            diagnostics=(
                ProjectDefinitionManifestDiagnostic(
                    level="ERROR",
                    code="FIELD_REQUIRED",
                    path="/actors/0/code",
                    message="Required field 'code' is missing.",
                ),
                ProjectDefinitionManifestDiagnostic(
                    level="ERROR",
                    code="REFERENCE_NOT_FOUND",
                    path="/parameters/0/actor_code",
                    message="Parameter actor_code must reference an existing actor code.",
                ),
            ),
        )
        invalid_report = invalid_validation.as_dict()
        invalid_before = (
            invalid.publication_status,
            invalid.manifest_hash,
            copy.deepcopy(invalid.validation_result),
            AuditEvent.objects.count(),
        )
        with patch(
            "domain.policies.validate_project_definition_manifest_policy",
            return_value=invalid_validation,
        ) as invalid_policy:
            with self.assertRaises(FoundationHumanWriteError) as caught:
                self.validate_write(invalid)
        self.assertEqual(caught.exception.error_code, "DEFINITION_VALIDATION_FAILED")
        self.assertEqual(caught.exception.report, invalid_report)
        self.assertEqual(invalid_policy.call_count, 1)
        invalid.refresh_from_db()
        self.assertEqual(
            (
                invalid.publication_status,
                invalid.manifest_hash,
                invalid.validation_result,
                AuditEvent.objects.count(),
            ),
            invalid_before,
        )

        oversized_path = "/" + ("path-segment/" * 48)
        oversized_message = "validation diagnostic " * 32
        complete_diagnostics = tuple(
            ProjectDefinitionManifestDiagnostic(
                level="ERROR",
                code=f"FD05_BOUNDED_DIAGNOSTIC_{ordinal:04d}",
                path=(oversized_path if ordinal == 0 else f"/actors/{ordinal}"),
                message=(
                    oversized_message
                    if ordinal == 0
                    else f"Ordered diagnostic {ordinal}."
                ),
            )
            for ordinal in range(1001)
        )
        bounded_validation = ProjectDefinitionManifestValidation(
            valid=False,
            manifest_sha256="",
            diagnostics=complete_diagnostics,
        )
        complete_payload = [item.as_dict() for item in complete_diagnostics]
        operation_id = uuid4()
        body = b"{}"
        http_before = (
            invalid.publication_status,
            invalid.manifest_hash,
            copy.deepcopy(invalid.validation_result),
            AuditEvent.objects.count(),
        )
        with patch(
            "domain.policies.validate_project_definition_manifest_policy",
            return_value=bounded_validation,
        ) as http_policy:
            response = self.http(
                self.publisher_user,
                "POST",
                f"/api/foundation/definitions/{invalid.pk}/validate/",
                body,
                key=operation_id,
                token=f'"{invalid.manifest_hash}"',
            )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(http_policy.call_count, 1)
        payload = response.data
        self.assertEqual(set(payload), {"code", "validation"})
        self.assertEqual(payload["code"], "DEFINITION_VALIDATION_FAILED")
        validation = payload["validation"]
        self.assertEqual(
            set(validation),
            {
                "contract",
                "contract_version",
                "schema_id",
                "schema_version",
                "definition_id",
                "project_id",
                "base_manifest_sha256",
                "request_sha256",
                "request_byte_length",
                "candidate_sha256",
                "manifest_sha256",
                "valid",
                "diagnostics_total",
                "diagnostics_returned",
                "diagnostics_truncated",
                "diagnostics_sha256",
                "diagnostics",
                "validation_report_sha256",
            },
        )
        self.assertEqual(
            {
                "contract": validation["contract"],
                "contract_version": validation["contract_version"],
                "schema_id": validation["schema_id"],
                "schema_version": validation["schema_version"],
                "definition_id": validation["definition_id"],
                "project_id": validation["project_id"],
                "base_manifest_sha256": validation["base_manifest_sha256"],
                "request_sha256": validation["request_sha256"],
                "request_byte_length": validation["request_byte_length"],
                "candidate_sha256": validation["candidate_sha256"],
                "manifest_sha256": validation["manifest_sha256"],
                "valid": validation["valid"],
                "diagnostics_total": validation["diagnostics_total"],
                "diagnostics_returned": validation["diagnostics_returned"],
                "diagnostics_truncated": validation["diagnostics_truncated"],
            },
            {
                "contract": "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1",
                "contract_version": "1.0.0",
                "schema_id": bounded_validation.schema_id,
                "schema_version": bounded_validation.schema_version,
                "definition_id": str(invalid.pk),
                "project_id": str(invalid.project_id),
                "base_manifest_sha256": invalid.manifest_hash,
                "request_sha256": hashlib.sha256(body).hexdigest(),
                "request_byte_length": len(body),
                "candidate_sha256": hashlib.sha256(
                    self.raw(invalid.manifest)
                ).hexdigest(),
                "manifest_sha256": "",
                "valid": False,
                "diagnostics_total": 1001,
                "diagnostics_returned": 1000,
                "diagnostics_truncated": True,
            },
        )
        self.assertEqual(
            validation["diagnostics_sha256"],
            hashlib.sha256(self.raw(complete_payload)).hexdigest(),
        )
        self.assertEqual(len(validation["diagnostics"]), 1000)
        self.assertEqual(
            set(validation["diagnostics"][0]),
            {
                "ordinal",
                "level",
                "code",
                "path",
                "path_sha256",
                "message",
                "message_sha256",
            },
        )
        self.assertEqual(validation["diagnostics"][0]["ordinal"], 0)
        self.assertEqual(validation["diagnostics"][-1]["ordinal"], 999)
        self.assertEqual(validation["diagnostics"][0]["path"], "<TRUNCATED>")
        self.assertEqual(
            validation["diagnostics"][0]["path_sha256"],
            hashlib.sha256(oversized_path.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(validation["diagnostics"][0]["message"], "<TRUNCATED>")
        self.assertEqual(
            validation["diagnostics"][0]["message_sha256"],
            hashlib.sha256(oversized_message.encode("utf-8")).hexdigest(),
        )
        validation_core = {
            key: value
            for key, value in validation.items()
            if key != "validation_report_sha256"
        }
        self.assertEqual(
            validation["validation_report_sha256"],
            hashlib.sha256(self.raw(validation_core)).hexdigest(),
        )
        serialized = self.raw(payload).decode("utf-8")
        self.assertNotIn('"errors"', serialized)
        self.assertNotIn('"detail', serialized)
        self.assertNotIn("exception", serialized.lower())
        invalid.refresh_from_db()
        self.assertEqual(
            (
                invalid.publication_status,
                invalid.manifest_hash,
                invalid.validation_result,
                AuditEvent.objects.count(),
            ),
            http_before,
        )
        self.assertFalse(AuditEvent.objects.filter(pk=operation_id).exists())

    def test_replay_uses_audit_snapshot_after_later_definition_change(self):
        operation_id = uuid4()
        created = self.create_write(operation_id=operation_id)
        original = created.receipt.as_dict()
        changed = copy.deepcopy(created.definition.manifest)
        changed["project"]["description"] = "later mutable definition state"
        self.save_write(created.definition, manifest=changed)
        replay = self.create_write(operation_id=operation_id, definition_id=created.definition.pk, code=created.definition.code, version=created.definition.version)
        self.assertTrue(replay.replayed)
        self.assertEqual(replay.receipt.as_dict(), original)
        created.definition.refresh_from_db()
        self.assertNotEqual(created.definition.manifest_hash, original["after_definition"]["manifest_hash"])

    def test_auth_scope_capability_csrf_and_spoof_order_remains_fail_closed(self):
        url = f"/api/foundation/projects/{self.project.pk}/definitions/"
        raw = b'{"actor":"SERVICE"}'
        baseline = (ProjectDefinitionVersion.objects.count(), AuditEvent.objects.count())
        anonymous = APIClient().generic("POST", url, raw, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(anonymous.status_code, 401)
        out_of_scope = self.http(self.viewer_user, "POST", url, raw, key=uuid4())
        self.assertEqual(out_of_scope.status_code, 404)
        in_scope_without_capability = self.http(
            self.publisher_user,
            "POST",
            url,
            raw,
            key=uuid4(),
        )
        self.assertEqual(in_scope_without_capability.status_code, 403)
        spoofed = self.http(self.editor_user, "POST", url, raw, key=uuid4(), HTTP_X_ACTOR_TYPE="SERVICE")
        self.assertEqual((spoofed.status_code, spoofed.json()["code"]), (400, "AUTHORING_ENVELOPE_INVALID"))

        service = StudioPrincipal.service(
            actor_identifier=self.editor_principal.actor_identifier,
            purpose="prove public HUMAN write isolation",
            capabilities=frozenset({StudioCapability.DRAFT_CREATE}),
        )
        service_definition_id = uuid4()
        service_request = self.identity(
            FoundationHumanWriteOperation.CREATE_DRAFT,
            operation_id=uuid4(),
            actor=service.actor_identifier,
            project_id=self.project.pk,
            target_id=service_definition_id,
            raw=self.raw(
                {
                    "id": str(service_definition_id),
                    "code": "FD05-SERVICE-SUBSTITUTION",
                    "version": "10.0.0",
                    "manifest": self.manifest,
                    "semantic_version": "1.0.0",
                    "construct_version": "1.0.0",
                }
            ),
            route=url,
        )
        with self.assertRaises(StudioAuthorizationDenied):
            create_project_definition_draft_human_write(
                request_identity=service_request,
                project=self.project,
                definition_id=service_definition_id,
                code="FD05-SERVICE-SUBSTITUTION",
                version="10.0.0",
                manifest=copy.deepcopy(self.manifest),
                principal=service,
            )

        session = APIClient(enforce_csrf_checks=True)
        self.assertTrue(session.login(username=self.editor_user.username, password=self.password))
        denied_csrf = session.generic("POST", url, raw, content_type="application/json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(denied_csrf.status_code, 403)
        self.assertFalse(denied_csrf.cookies)
        self.assertEqual((ProjectDefinitionVersion.objects.count(), AuditEvent.objects.count()), baseline)

        definition_id = uuid4()
        operation_id = uuid4()
        body = self.raw(
            {
                "id": str(definition_id),
                "code": "FD05-BASIC-REPLAY",
                "version": "10.1.0",
                "manifest": self.manifest,
                "semantic_version": "1.0.0",
                "construct_version": "1.0.0",
            }
        )
        credentials = base64.b64encode(
            f"{self.editor_user.username}:{self.password}".encode("utf-8")
        ).decode("ascii")
        password_bytes = self.editor_user.password
        basic = APIClient(enforce_csrf_checks=True)
        created = basic.generic(
            "POST",
            url,
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_AUTHORIZATION=f"Basic {credentials}",
        )
        self.assertEqual(created.status_code, 201, created.data)
        receipt = created.data["write_receipt"]
        self.assertEqual(receipt["operation_id"], str(operation_id))
        self.assertEqual(created["X-Foundation-Operation-Replayed"], "false")
        self.assertEqual(
            created["X-Foundation-Receipt-SHA256"],
            hashlib.sha256(self.raw(receipt)).hexdigest(),
        )
        self.assertEqual(created["ETag"], f'"{created.data["manifest_hash"]}"')
        self.assertFalse(created.cookies)

        replay = basic.generic(
            "POST",
            url,
            body,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(operation_id),
            HTTP_AUTHORIZATION=f"Basic {credentials}",
        )
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(set(replay.data), {"code", "write_receipt"})
        self.assertEqual(replay.data["code"], "WRITE_OPERATION_RECONCILED")
        self.assertEqual(replay.data["write_receipt"], receipt)
        self.assertEqual(replay["X-Foundation-Operation-Replayed"], "true")
        self.assertEqual(
            replay["X-Foundation-Receipt-SHA256"],
            created["X-Foundation-Receipt-SHA256"],
        )
        self.assertEqual(replay["ETag"], created["ETag"])
        self.assertFalse(replay.cookies)
        self.assertEqual(AuditEvent.objects.filter(pk=operation_id).count(), 1)
        self.editor_user.refresh_from_db()
        self.assertEqual(self.editor_user.password, password_bytes)

    def test_fault_injection_rolls_back_definition_scope_membership_and_audit_without_orphans(self):
        for stage in FD05_HUMAN_WRITE_FAILURE_STAGES:
            with self.subTest(operation="create", stage=stage):
                definition_id, operation_id = uuid4(), uuid4()
                with self.assertRaisesRegex(RuntimeError, stage):
                    self.create_write(
                        operation_id=operation_id,
                        definition_id=definition_id,
                        inject_failure_at=stage,
                    )
                self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=definition_id).exists())
                self.assertFalse(AuditEvent.objects.filter(pk=operation_id).exists())

            with self.subTest(operation="bootstrap", stage=stage):
                project_id, definition_id, operation_id = uuid4(), uuid4(), uuid4()
                stage_code = stage.upper().replace("_", "-")
                manifest = manifest_vector()
                manifest["project"].update({"id": str(project_id), "code": f"FD05-ROLLBACK-{stage_code}", "version": "1.0.0"})
                raw = self.raw({"project": str(project_id), "definition": str(definition_id)})
                request = self.identity(FoundationHumanWriteOperation.BOOTSTRAP_DRAFT, operation_id=operation_id, actor=self.editor_principal.actor_identifier, project_id=project_id, target_id=definition_id, raw=raw, route="/api/foundation/projects/bootstrap-first-draft/")
                with self.assertRaisesRegex(RuntimeError, stage):
                    bootstrap_project_definition_draft_human_write(request_identity=request, project_id=project_id, project_code=f"FD05-ROLLBACK-{stage_code}", project_version="1.0.0", project_name="rollback", project_metadata={}, definition_id=definition_id, definition_code=f"FD05-ROLLBACK-DEF-{stage_code}", definition_version="1.0.0", manifest=manifest, principal=self.editor_principal, user=self.editor_user, inject_failure_at=stage)
                self.assertFalse(Project.objects.filter(pk=project_id).exists())
                self.assertFalse(Group.objects.filter(name=f"studio-project:{project_id}").exists())
                self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=definition_id).exists())
                self.assertFalse(AuditEvent.objects.filter(pk=operation_id).exists())

            with self.subTest(operation="clone", stage=stage):
                source = self.direct_draft(
                    code=f"FD05-ROLLBACK-CLONE-SOURCE-{uuid4().hex}",
                )
                source_snapshot = (
                    source.manifest_hash,
                    source.publication_status,
                )
                target_id, operation_id = uuid4(), uuid4()
                clone_code = f"FD05-ROLLBACK-CLONE-{uuid4().hex}"
                clone_version = f"30.0.{ProjectDefinitionVersion.objects.count()}"
                clone_raw = self.raw(
                    {
                        "id": str(target_id),
                        "code": clone_code,
                        "version": clone_version,
                    }
                )
                clone_request = self.identity(
                    FoundationHumanWriteOperation.CLONE_DRAFT,
                    operation_id=operation_id,
                    actor=self.editor_principal.actor_identifier,
                    project_id=self.project.pk,
                    source_id=source.pk,
                    target_id=target_id,
                    raw=clone_raw,
                    route=f"/api/foundation/definitions/{source.pk}/clone/",
                    if_match=source.manifest_hash,
                )
                with self.assertRaisesRegex(RuntimeError, stage):
                    clone_project_definition_draft_human_write(
                        source,
                        request_identity=clone_request,
                        expected_manifest_hash=source.manifest_hash,
                        definition_id=target_id,
                        code=clone_code,
                        version=clone_version,
                        principal=self.editor_principal,
                        inject_failure_at=stage,
                    )
                source.refresh_from_db()
                self.assertEqual(
                    (source.manifest_hash, source.publication_status),
                    source_snapshot,
                )
                self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=target_id).exists())
                self.assertFalse(AuditEvent.objects.filter(pk=operation_id).exists())

            with self.subTest(operation="save", stage=stage):
                definition = self.direct_draft(
                    code=f"FD05-ROLLBACK-SAVE-{uuid4().hex}",
                )
                operation_id = uuid4()
                original_manifest = copy.deepcopy(definition.manifest)
                original_hash = definition.manifest_hash
                changed_manifest = copy.deepcopy(original_manifest)
                changed_manifest["project"]["description"] = (
                    f"must roll back {stage}"
                )
                with self.assertRaisesRegex(RuntimeError, stage):
                    self.save_write(
                        definition,
                        operation_id=operation_id,
                        expected_hash=original_hash,
                        manifest=changed_manifest,
                        inject_failure_at=stage,
                    )
                definition.refresh_from_db()
                self.assertEqual(definition.manifest, original_manifest)
                self.assertEqual(definition.manifest_hash, original_hash)
                self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)
                self.assertFalse(AuditEvent.objects.filter(pk=operation_id).exists())

            with self.subTest(operation="validate", stage=stage):
                definition = self.direct_draft(
                    code=f"FD05-ROLLBACK-VALIDATE-{uuid4().hex}",
                )
                operation_id = uuid4()
                original_hash = definition.manifest_hash
                with self.assertRaisesRegex(RuntimeError, stage):
                    self.validate_write(
                        definition,
                        operation_id=operation_id,
                        expected_hash=original_hash,
                        inject_failure_at=stage,
                    )
                definition.refresh_from_db()
                self.assertEqual(definition.manifest_hash, original_hash)
                self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)
                self.assertIsNone(definition.validated_at)
                self.assertEqual(definition.validated_by, "")
                self.assertEqual(definition.validation_result, {})
                self.assertFalse(AuditEvent.objects.filter(pk=operation_id).exists())


class FoundationStudioWriteReconciliationConcurrencyTests(
    FoundationStudioWriteContractMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self) -> None:
        self.make_write_contract()

    def _parallel(self, *operations):
        barrier = threading.Barrier(len(operations))
        outcomes: list[object] = []
        errors: list[Exception] = []
        result_lock = threading.Lock()

        def worker(operation) -> None:
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '20s'")
                barrier.wait(timeout=10)
                result = operation()
                with result_lock:
                    outcomes.append(result)
            except Exception as exc:  # exact typed assertions are below
                with result_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=worker, args=(operation,), daemon=True)
            for operation in operations
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertFalse(
            any(isinstance(error, OperationalError) for error in errors),
            f"PostgreSQL FD05 race raised OperationalError: {errors!r}",
        )
        return outcomes, errors

    def test_postgresql_concurrent_bootstrap_same_key_has_one_graph_one_audit_one_reconcile(self):
        if connection.vendor != "postgresql":
            self.skipTest("FD05 same-key bootstrap reconciliation is PostgreSQL-only.")
        project_id, definition_id, operation_id = uuid4(), uuid4(), uuid4()
        project_code = "FD05-CONCURRENT-BOOTSTRAP"
        manifest = copy.deepcopy(self.manifest)
        manifest["project"].update(
            {"id": str(project_id), "code": project_code, "version": "1.0.0"}
        )
        raw = self.raw({"project": str(project_id), "definition": str(definition_id)})
        request = self.identity(
            FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
            operation_id=operation_id,
            actor=self.editor_principal.actor_identifier,
            project_id=project_id,
            target_id=definition_id,
            raw=raw,
            route="/api/foundation/projects/bootstrap-first-draft/",
        )

        def invoke():
            return bootstrap_project_definition_draft_human_write(
                request_identity=request,
                project_id=project_id,
                project_code=project_code,
                project_version="1.0.0",
                project_name="Concurrent bootstrap",
                project_metadata={"race": True},
                definition_id=definition_id,
                definition_code="FD05-CONCURRENT-BOOTSTRAP-DRAFT",
                definition_version="1.0.0",
                manifest=copy.deepcopy(manifest),
                principal=self.editor_principal,
                user=self.editor_user,
            )

        outcomes, errors = self._parallel(invoke, invoke)
        self.assertFalse(errors)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(sorted(result.replayed for result in outcomes), [False, True])
        self.assertEqual(
            len(
                {
                    json.dumps(
                        result.receipt.as_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    for result in outcomes
                }
            ),
            1,
        )
        self.assertEqual(Project.objects.filter(pk=project_id).count(), 1)
        self.assertEqual(ProjectDefinitionVersion.objects.filter(pk=definition_id).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(pk=operation_id).count(), 1)
        self.assertEqual(
            Group.objects.filter(name=f"studio-project:{project_id}").count(), 1
        )
        self.assertEqual(
            Group.objects.get(
                name=f"studio-project:{project_id}"
            ).user_set.filter(pk=self.editor_user.pk).count(),
            1,
        )

    def test_postgresql_concurrent_create_same_key_has_one_commit_one_reconcile(self):
        if connection.vendor != "postgresql":
            self.skipTest("FD05 same-key create reconciliation is PostgreSQL-only.")
        operation_id, definition_id = uuid4(), uuid4()
        code, version = "FD05-CONCURRENT-CREATE", "20.0.0"

        def invoke():
            return self.create_write(
                operation_id=operation_id,
                definition_id=definition_id,
                code=code,
                version=version,
            )

        outcomes, errors = self._parallel(invoke, invoke)
        self.assertFalse(errors)
        self.assertEqual(len(outcomes), 2)
        self.assertEqual(sorted(result.replayed for result in outcomes), [False, True])
        self.assertEqual(ProjectDefinitionVersion.objects.filter(pk=definition_id).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(pk=operation_id).count(), 1)

        global_operation_id = uuid4()
        other_project_id = uuid4()
        other_project = Project.objects.create(
            id=other_project_id,
            code="FD05-GLOBAL-RACE-B",
            version="1.0.0",
            name="Global operation UUID race B",
            description="",
            metadata={},
        )
        other_manifest = copy.deepcopy(self.manifest)
        other_manifest["project"].update(
            {
                "id": str(other_project_id),
                "code": other_project.code,
                "version": other_project.version,
            }
        )
        global_targets = (uuid4(), uuid4())

        def global_race_create(
            *,
            project,
            manifest,
            target_id,
            code,
            version,
        ):
            payload = {
                "id": str(target_id),
                "code": code,
                "version": version,
                "manifest": manifest,
                "semantic_version": "1.0.0",
                "construct_version": "1.0.0",
            }
            request = self.identity(
                FoundationHumanWriteOperation.CREATE_DRAFT,
                operation_id=global_operation_id,
                actor=self.editor_principal.actor_identifier,
                project_id=project.pk,
                target_id=target_id,
                raw=self.raw(payload),
                route=f"/api/foundation/projects/{project.pk}/definitions/",
            )
            return lambda: create_project_definition_draft_human_write(
                request_identity=request,
                project=project,
                definition_id=target_id,
                code=code,
                version=version,
                manifest=copy.deepcopy(manifest),
                principal=self.editor_principal,
            )

        from domain.services import project_definitions as project_definition_service
        from unittest.mock import patch

        audit_barrier = threading.Barrier(2)
        record_audit = project_definition_service._record_human_write_audit

        def synchronized_audit_insert(*args, **kwargs):
            audit_barrier.wait(timeout=10)
            return record_audit(*args, **kwargs)

        with patch(
            "domain.services.project_definitions._record_human_write_audit",
            side_effect=synchronized_audit_insert,
        ):
            global_outcomes, global_errors = self._parallel(
                global_race_create(
                    project=self.project,
                    manifest=self.manifest,
                    target_id=global_targets[0],
                    code="FD05-GLOBAL-RACE-A-DRAFT",
                    version="20.1.0",
                ),
                global_race_create(
                    project=other_project,
                    manifest=other_manifest,
                    target_id=global_targets[1],
                    code="FD05-GLOBAL-RACE-B-DRAFT",
                    version="20.2.0",
                ),
            )
        self.assertEqual(len(global_outcomes), 1)
        self.assertEqual(len(global_errors), 1)
        self.assertIsInstance(
            global_errors[0],
            FoundationStudioApplicationConflict,
        )
        self.assertEqual(
            global_errors[0].conflict_code,
            "WRITE_OPERATION_KEY_REUSED",
        )
        self.assertEqual(AuditEvent.objects.filter(pk=global_operation_id).count(), 1)
        global_event = AuditEvent.objects.get(pk=global_operation_id)
        self.assertEqual(
            global_event.definition_version_id,
            global_outcomes[0].definition.pk,
        )
        self.assertEqual(
            sum(
                ProjectDefinitionVersion.objects.filter(pk=target).count()
                for target in global_targets
            ),
            1,
        )
        losing_target = next(
            target
            for target in global_targets
            if target != global_outcomes[0].definition.pk
        )
        self.assertFalse(
            ProjectDefinitionVersion.objects.filter(pk=losing_target).exists()
        )
        self.assertFalse(AuditEvent.objects.filter(entity_id=losing_target).exists())

    def test_postgresql_different_keys_same_create_or_clone_identity_have_one_typed_loser(self):
        if connection.vendor != "postgresql":
            self.skipTest("FD05 different-key identity races are PostgreSQL-only.")
        definition_id = uuid4()
        code, version = "FD05-DIFFERENT-KEYS", "21.0.0"

        def invoke(operation_id):
            return lambda: self.create_write(
                operation_id=operation_id,
                definition_id=definition_id,
                code=code,
                version=version,
            )

        outcomes, errors = self._parallel(invoke(uuid4()), invoke(uuid4()))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FoundationStudioApplicationConflict)
        self.assertEqual(errors[0].conflict_code, "DEFINITION_ID_CONFLICT")
        self.assertEqual(ProjectDefinitionVersion.objects.filter(pk=definition_id).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(entity_id=definition_id).count(), 1)

        source = self.direct_draft(
            code="FD05-DIFFERENT-KEYS-CLONE-SOURCE",
            version="21.1.0",
        )
        clone_id = uuid4()
        clone_code, clone_version = "FD05-DIFFERENT-KEYS-CLONE", "21.2.0"
        clone_raw = self.raw(
            {
                "id": str(clone_id),
                "code": clone_code,
                "version": clone_version,
            }
        )

        def invoke_clone(operation_id):
            request = self.identity(
                FoundationHumanWriteOperation.CLONE_DRAFT,
                operation_id=operation_id,
                actor=self.editor_principal.actor_identifier,
                project_id=self.project.pk,
                source_id=source.pk,
                target_id=clone_id,
                raw=clone_raw,
                route=f"/api/foundation/definitions/{source.pk}/clone/",
                if_match=source.manifest_hash,
            )
            return lambda: clone_project_definition_draft_human_write(
                source,
                request_identity=request,
                expected_manifest_hash=source.manifest_hash,
                definition_id=clone_id,
                code=clone_code,
                version=clone_version,
                principal=self.editor_principal,
            )

        clone_outcomes, clone_errors = self._parallel(
            invoke_clone(uuid4()),
            invoke_clone(uuid4()),
        )
        self.assertEqual(len(clone_outcomes), 1)
        self.assertEqual(len(clone_errors), 1)
        self.assertIsInstance(
            clone_errors[0],
            FoundationStudioApplicationConflict,
        )
        self.assertEqual(
            clone_errors[0].conflict_code,
            "DEFINITION_ID_CONFLICT",
        )
        self.assertEqual(ProjectDefinitionVersion.objects.filter(pk=clone_id).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(entity_id=clone_id).count(), 1)

    def test_postgresql_concurrent_stale_saves_have_one_commit_one_draft_stale(self):
        if connection.vendor != "postgresql":
            self.skipTest("FD05 stale-save serialization is PostgreSQL-only.")
        definition = self.direct_draft(code="FD05-CONCURRENT-SAVE", version="22.0.0")
        expected_hash = definition.manifest_hash
        manifests = []
        for label in ("winner-a", "winner-b"):
            manifest = copy.deepcopy(definition.manifest)
            manifest["project"]["description"] = label
            manifests.append(manifest)

        def invoke(manifest):
            return lambda: self.save_write(
                definition,
                operation_id=uuid4(),
                expected_hash=expected_hash,
                manifest=manifest,
            )

        outcomes, errors = self._parallel(*(invoke(item) for item in manifests))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FoundationStudioApplicationConflict)
        self.assertEqual(errors[0].conflict_code, "DRAFT_STALE")
        self.assertEqual(AuditEvent.objects.filter(entity_id=definition.pk).count(), 1)
        definition.refresh_from_db()
        self.assertIn(
            definition.manifest["project"]["description"],
            {"winner-a", "winner-b"},
        )

    def test_postgresql_save_validate_race_obeys_project_first_lock_order(self):
        if connection.vendor != "postgresql":
            self.skipTest("FD05 save/validate lock-order race is PostgreSQL-only.")
        definition = self.direct_draft(code="FD05-SAVE-VALIDATE-RACE", version="23.0.0")
        expected_hash = definition.manifest_hash
        saved_manifest = copy.deepcopy(definition.manifest)
        saved_manifest["project"]["description"] = "save won the shared Project lock"

        outcomes, errors = self._parallel(
            lambda: self.save_write(
                definition,
                operation_id=uuid4(),
                expected_hash=expected_hash,
                manifest=saved_manifest,
            ),
            lambda: self.validate_write(
                definition,
                operation_id=uuid4(),
                expected_hash=expected_hash,
            ),
        )
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FoundationStudioApplicationConflict)
        self.assertIn(
            errors[0].conflict_code,
            {"DRAFT_STALE", "DEFINITION_NOT_DRAFT"},
        )
        self.assertEqual(AuditEvent.objects.filter(entity_id=definition.pk).count(), 1)
