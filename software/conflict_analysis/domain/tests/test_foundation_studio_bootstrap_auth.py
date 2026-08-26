from __future__ import annotations

import copy
import hashlib
import json
import threading
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from domain.enums import AuditAction, AuditScope, HelpApplicationScope, PublicationStatus
from domain.models import (
    AuditEvent,
    HelpTopic,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    ProjectWorkspace,
    UIHelpBinding,
)
from domain.policies import (
    StudioCapability,
    StudioPrincipal,
    StudioRole,
    bootstrap_initial_project_definition,
    can_modify_project_structure,
    publish_project_definition,
    require_studio_capability,
    validate_project_definition,
)
from domain.services.project_definitions import (
    create_project_definition_draft,
    hash_project_definition_manifest_v1,
    open_project_definition_draft,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "foundation_studio_definition_vectors_v1.json"
)


def manifest_vector() -> dict:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return copy.deepcopy(fixture["vectors"][0]["manifest"])


class FoundationStudioBootstrapMixin:
    project: Project
    manifest: dict
    topic: HelpTopic

    def make_contract(self) -> None:
        self.manifest = manifest_vector()
        identity = self.manifest["project"]
        self.project = Project.objects.create(
            id=identity["id"],
            code=identity["code"],
            version=identity["version"],
            name="Persisted project name",
            description="Persisted project description",
            metadata={"authority": "Project"},
        )
        sanitized_html = "<p>Exact Studio welcome help.</p>"
        checksum = hashlib.sha256(sanitized_html.encode("utf-8")).hexdigest()
        self.topic = HelpTopic(
            code="HELP-TOPIC-STUDIO-WELCOME",
            version="1.0.0",
            stable_key="studio.welcome",
            title="Studio welcome",
            application_scope=HelpApplicationScope.STUDIO,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="en",
            sanitized_html=sanitized_html,
            content_sha256=checksum,
            publication_status=PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.topic.save(force_insert=True)
        global_binding = UIHelpBinding(
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            code="GLOBAL-STUDIO-WELCOME",
            version="1.0.0",
            ui_key="studio.welcome",
            locale="en",
            help_topic=self.topic,
        )
        global_binding.save(force_insert=True)
        self.manifest["help_bindings"][0]["topic_sha256"] = checksum

    @staticmethod
    def editor(actor: str = "editor") -> StudioPrincipal:
        return StudioPrincipal.for_role(
            actor_identifier=actor,
            role=StudioRole.STUDIO_EDITOR,
        )

    @staticmethod
    def publisher(actor: str = "publisher") -> StudioPrincipal:
        return StudioPrincipal.for_role(
            actor_identifier=actor,
            role=StudioRole.STUDIO_PUBLISHER,
        )

    def draft(self, *, code: str = "DEF-STUDIO-V1") -> ProjectDefinitionVersion:
        return create_project_definition_draft(
            project=self.project,
            code=code,
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )

    @staticmethod
    def workspace_spec() -> dict:
        return {
            "id": "16000000-0000-4000-8000-000000000001",
            "code": "STUDIO-INITIAL",
            "version": "1.0.0",
            "name": "Initial Studio workspace",
            "is_default": True,
            "metadata": {"bootstrap": "FOUNDATION_STUDIO_CONTRACT_V1"},
        }


class FoundationStudioBootstrapTests(FoundationStudioBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.make_contract()

    def test_blank_project_bootstrap_is_one_atomic_publication_authority(self):
        definition = self.draft()
        original_project = (self.project.name, self.project.description, self.project.metadata)
        result = bootstrap_initial_project_definition(
            definition=definition,
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )

        result.definition.refresh_from_db()
        self.project.refresh_from_db()
        self.assertEqual(result.definition.publication_status, PublicationStatus.PUBLISHED)
        self.assertTrue(result.definition.is_current)
        self.assertEqual(
            result.definition.manifest_hash,
            hash_project_definition_manifest_v1(self.manifest, project=self.project),
        )
        self.assertEqual(
            (self.project.name, self.project.description, self.project.metadata),
            original_project,
        )
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        publication = ProjectPublication.objects.get()
        self.assertEqual(publication.initial_workspace_id, result.workspace.pk)
        self.assertEqual(publication.definition_version_id, result.definition.pk)
        self.assertEqual(result.workspace.definition_manifest_hash, result.definition.manifest_hash)
        self.assertEqual(len(result.help_bindings), 1)
        self.assertEqual(result.help_bindings[0].help_topic_id, self.topic.pk)

        definition_events = AuditEvent.objects.filter(scope=AuditScope.DEFINITION)
        workspace_events = AuditEvent.objects.filter(scope=AuditScope.WORKSPACE)
        self.assertEqual(
            list(definition_events.values_list("action", flat=True).order_by("action")),
            [AuditAction.PUBLISH, AuditAction.VALIDATE],
        )
        self.assertEqual(
            list(workspace_events.values_list("action", flat=True)),
            [AuditAction.BOOTSTRAP],
        )
        self.assertFalse(definition_events.exclude(workspace=None).exists())
        self.assertFalse(workspace_events.exclude(definition_version=None).exists())

        with self.assertRaises(ValidationError):
            bootstrap_initial_project_definition(
                definition=result.definition,
                principal=self.publisher(),
                actor_identifier="publisher",
                workspace_spec=self.workspace_spec(),
                locale="en",
            )
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)

    def test_injected_failure_at_every_bootstrap_stage_rolls_back_all_success_state(self):
        stages = (
            "after_bootstrap_lock",
            "after_validation_transition",
            "after_validation_audit",
            "after_publication_transition",
            "after_initial_workspace",
            "after_workspace_help_bindings",
            "after_project_publication",
            "after_definition_publish_audit",
            "after_workspace_bootstrap_audit",
        )
        for stage in stages:
            with self.subTest(stage=stage):
                definition = self.draft(code=f"DEF-{stage.upper().replace('_', '-')}")
                with self.assertRaisesRegex(RuntimeError, stage):
                    bootstrap_initial_project_definition(
                        definition=definition,
                        principal=self.publisher(),
                        actor_identifier="publisher",
                        workspace_spec=self.workspace_spec(),
                        locale="en",
                        inject_failure_at=stage,
                    )
                definition.refresh_from_db()
                self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)
                self.assertIsNone(definition.validated_at)
                self.assertIsNone(definition.published_at)
                self.assertFalse(ProjectWorkspace.objects.exists())
                self.assertFalse(ProjectPublication.objects.exists())
                self.assertFalse(AuditEvent.objects.exists())
                self.assertEqual(UIHelpBinding.objects.filter(workspace__isnull=False).count(), 0)
                definition.delete()

    def test_typed_validation_rejects_caller_valid_true_and_workspace_borrowing(self):
        definition = self.draft()
        with self.assertRaises(ValidationError):
            validate_project_definition(
                definition,
                actor_identifier="publisher",
                principal=self.publisher(),
                validation_result={"valid": True},
            )
        definition.refresh_from_db()
        self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)


class FoundationStudioCapabilityTests(FoundationStudioBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.make_contract()

    def test_exact_role_and_bounded_service_matrix(self):
        expected = {
            StudioRole.STUDIO_EDITOR: {
                StudioCapability.DEFINITION_READ,
                StudioCapability.DRAFT_CREATE,
                StudioCapability.DRAFT_CLONE,
                StudioCapability.DRAFT_SAVE,
            },
            StudioRole.STUDIO_PUBLISHER: {
                StudioCapability.DEFINITION_READ,
                StudioCapability.DEFINITION_VALIDATE,
                StudioCapability.DEFINITION_PUBLISH,
            },
            StudioRole.VIEWER: {StudioCapability.DEFINITION_READ},
            StudioRole.PLAYER: set(),
        }
        principals = {
            role: StudioPrincipal.for_role(
                actor_identifier=role.value.lower(),
                role=role,
            )
            for role in expected
        }
        for role, granted in expected.items():
            for capability in StudioCapability:
                with self.subTest(role=role, capability=capability):
                    if capability in granted:
                        require_studio_capability(principals[role], capability)
                    else:
                        with self.assertRaises(PermissionDenied):
                            require_studio_capability(principals[role], capability)
        with self.assertRaises(ValueError):
            StudioPrincipal.for_role(
                actor_identifier="service", role=StudioRole.SERVICE
            )
        service = StudioPrincipal.service(
            actor_identifier="import-service",
            purpose="Foundation 2.1 definition import",
            capabilities=frozenset({StudioCapability.DRAFT_CREATE}),
        )
        require_studio_capability(service, StudioCapability.DRAFT_CREATE)
        with self.assertRaises(PermissionDenied):
            require_studio_capability(service, StudioCapability.DEFINITION_PUBLISH)
        self.assertFalse(
            can_modify_project_structure(self.project, actor="SERVICE"),
            "An unbounded legacy SERVICE label must not bypass structure policy.",
        )
        self.assertTrue(
            can_modify_project_structure(
                self.project,
                actor="SERVICE",
                service_principal=StudioPrincipal.service(
                    actor_identifier="structure-service",
                    purpose="Install an exact validated Foundation structure",
                    capabilities=frozenset({StudioCapability.STRUCTURE_MUTATE}),
                ),
            )
        )

    def test_direct_principal_constructor_cannot_spoof_role_capabilities(self):
        for role, capability in (
            (StudioRole.VIEWER, StudioCapability.DEFINITION_PUBLISH),
            (StudioRole.PLAYER, StudioCapability.DEFINITION_READ),
            (StudioRole.STUDIO_EDITOR, StudioCapability.DEFINITION_VALIDATE),
            (StudioRole.STUDIO_PUBLISHER, StudioCapability.DRAFT_SAVE),
        ):
            with self.subTest(role=role, capability=capability):
                with self.assertRaisesRegex(ValueError, "authorized role matrix"):
                    StudioPrincipal(
                        actor_identifier="direct-spoof",
                        role=role,
                        capabilities=frozenset({capability}),
                    )
        with self.assertRaises(ValueError):
            StudioPrincipal(
                actor_identifier="direct-service-spoof",
                role=StudioRole.SERVICE,
                capabilities=frozenset({StudioCapability.DEFINITION_PUBLISH}),
            )

    def test_viewer_can_open_but_player_and_publisher_cannot_create_draft(self):
        definition = self.draft()
        viewer = StudioPrincipal.for_role(
            actor_identifier="viewer", role=StudioRole.VIEWER
        )
        self.assertEqual(
            open_project_definition_draft(definition, principal=viewer).pk,
            definition.pk,
        )
        for principal in (
            StudioPrincipal.for_role(
                actor_identifier="player", role=StudioRole.PLAYER
            ),
            self.publisher(),
        ):
            with self.assertRaises(PermissionDenied):
                create_project_definition_draft(
                    project=self.project,
                    code=f"DENIED-{principal.role.value}",
                    version="2.0.0",
                    manifest=self.manifest,
                    principal=principal,
                )


class FoundationStudioPersistedDispatchTests(FoundationStudioBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.make_contract()
        initial = bootstrap_initial_project_definition(
            definition=self.draft(code="DISPATCH-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        self.audit_workspace = initial.workspace

    def test_stale_legacy_envelope_cannot_bypass_typed_validation_authorization(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="TYPED-PERSISTED-DRAFT",
            version="2.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        definition.manifest = {"legacy": "caller-forged-envelope"}

        with self.assertRaises(PermissionDenied):
            validate_project_definition(
                definition,
                audit_workspace=self.audit_workspace,
                actor_identifier="legacy-caller",
                validation_result={"valid": True},
                principal=None,
            )

        definition.refresh_from_db()
        self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)
        self.assertEqual(
            definition.manifest["format"],
            "conflict-analysis-project-definition",
        )
        self.assertFalse(
            AuditEvent.objects.filter(definition_version=definition).exists()
        )

        validated = validate_project_definition(
            definition,
            actor_identifier="typed-publisher",
            principal=self.publisher(actor="typed-publisher"),
        )
        validated.manifest = {"legacy": "caller-forged-publish-envelope"}
        with self.assertRaises(PermissionDenied):
            publish_project_definition(
                validated,
                audit_workspace=self.audit_workspace,
                actor_identifier="legacy-caller",
                principal=None,
            )
        validated.refresh_from_db()
        self.assertEqual(
            validated.publication_status,
            PublicationStatus.VALIDATED,
        )
        self.assertEqual(ProjectPublication.objects.count(), 1)

    def test_stale_typed_envelope_does_not_misroute_persisted_legacy_lifecycle(self):
        persisted_manifest = {"legacy_contract": "foundation-v4"}
        definition = ProjectDefinitionVersion.objects.create(
            project=self.project,
            code="LEGACY-PERSISTED-DRAFT",
            version="2.0.0",
            manifest=persisted_manifest,
        )
        definition.manifest = copy.deepcopy(self.manifest)

        validated = validate_project_definition(
            definition,
            audit_workspace=self.audit_workspace,
            actor_identifier="legacy-publisher",
            validation_result={"valid": True, "source": "legacy-validator"},
            principal=self.publisher(actor="ignored-for-legacy-dispatch"),
        )
        self.assertEqual(validated.publication_status, PublicationStatus.VALIDATED)
        self.assertEqual(validated.manifest, persisted_manifest)

        validated.manifest = copy.deepcopy(self.manifest)
        publication = publish_project_definition(
            validated,
            audit_workspace=self.audit_workspace,
            actor_identifier="legacy-publisher",
            locale="en",
            principal=self.publisher(actor="ignored-for-legacy-dispatch"),
        )
        publication.definition_version.refresh_from_db()
        self.assertEqual(
            publication.definition_version.publication_status,
            PublicationStatus.PUBLISHED,
        )
        self.assertEqual(publication.definition_version.manifest, persisted_manifest)
        self.assertIsNone(publication.initial_workspace_id)


class FoundationStudioPersistenceGuardTests(FoundationStudioBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.make_contract()

    def test_definition_bulk_writes_cannot_bypass_validation_or_lifecycle(self):
        typed_draft = ProjectDefinitionVersion(
            project=self.project,
            code="BULK-TYPED-DRAFT",
            version="1.0.0",
            manifest=self.manifest,
        )
        with self.assertRaisesRegex(ValidationError, "canonical Studio draft service"):
            ProjectDefinitionVersion.objects.bulk_create([typed_draft])
        self.assertFalse(
            ProjectDefinitionVersion.objects.filter(pk=typed_draft.pk).exists()
        )

        draft = ProjectDefinitionVersion(
            project=self.project,
            code="BULK-LEGACY-DRAFT",
            version="2.0.0",
            manifest={"legacy_contract": "foundation-v4"},
        )
        ProjectDefinitionVersion.objects.bulk_create([draft])
        self.assertTrue(ProjectDefinitionVersion.objects.filter(pk=draft.pk).exists())

        with self.assertRaisesRegex(ValidationError, "lifecycle updates"):
            ProjectDefinitionVersion.objects.filter(pk=draft.pk).update(manifest={})
        draft.manifest = {}
        with self.assertRaisesRegex(ValidationError, "lifecycle updates"):
            ProjectDefinitionVersion.objects.bulk_update([draft], ["manifest"])

        forged_published = ProjectDefinitionVersion(
            project=self.project,
            code="BULK-FORGED-PUBLISHED",
            version="3.0.0",
            publication_status=PublicationStatus.PUBLISHED,
            manifest={"legacy_contract": "foundation-v4"},
        )
        with self.assertRaisesRegex(ValidationError, "DRAFT records only"):
            ProjectDefinitionVersion.objects.bulk_create([forged_published])
        with self.assertRaisesRegex(ValidationError, "identity conflicts"):
            ProjectDefinitionVersion.objects.bulk_create([draft], ignore_conflicts=True)

    def test_publication_bulk_writes_are_validated_and_append_only(self):
        result = bootstrap_initial_project_definition(
            definition=self.draft(code="PUBLICATION-GUARD-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        publication = result.publication

        with self.assertRaisesRegex(ValidationError, "append-only"):
            ProjectPublication.objects.filter(pk=publication.pk).update(locale="ru")
        publication.locale = "ru"
        with self.assertRaisesRegex(ValidationError, "append-only"):
            ProjectPublication.objects.bulk_update([publication], ["locale"])

        alternate_locale = ProjectPublication(
            project=self.project,
            definition_version=result.definition,
            initial_workspace=None,
            code="BULK-ALTERNATE-LOCALE",
            version="1.0.0",
            locale="ru",
            actor_identifier="alternate-publisher",
            validation_result=result.definition.validation_result,
        )
        with self.assertRaisesRegex(
            ValidationError,
            "canonical Studio publication service",
        ):
            ProjectPublication.objects.bulk_create([alternate_locale])
        self.assertEqual(ProjectPublication.objects.count(), 1)

        invalid = ProjectPublication(
            project=self.project,
            definition_version=result.definition,
            initial_workspace=result.workspace,
            code="BULK-INVALID-PUBLICATION",
            version="1.0.0",
            locale="en",
            actor_identifier="",
            validation_result={"valid": True},
        )
        with self.assertRaises(ValidationError):
            ProjectPublication.objects.bulk_create([invalid])
        with self.assertRaisesRegex(ValidationError, "identity conflicts"):
            ProjectPublication.objects.bulk_create(
                [publication],
                ignore_conflicts=True,
            )

class FoundationStudioHttpAuthorizationTests(FoundationStudioBootstrapMixin, TestCase):
    def setUp(self) -> None:
        self.make_contract()
        self.client = APIClient()
        User = get_user_model()
        self.player = User.objects.create_user(username="player", password="test-password")
        self.editor_user = User.objects.create_user(username="editor", password="test-password")
        self.publisher_user = User.objects.create_user(
            username="publisher", password="test-password"
        )
        self.viewer_user = User.objects.create_user(username="viewer", password="test-password")
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
        self.publisher_user.user_permissions.add(
            permissions["studio_read_definition"],
            permissions["studio_validate_definition"],
            permissions["studio_publish_definition"],
        )
        self.viewer_user.user_permissions.add(permissions["studio_read_definition"])

    def test_unauthenticated_and_body_role_spoof_are_denied(self):
        payload = {
            "project_id": str(self.project.pk),
            "code": "HTTP-DRAFT",
            "version": "1.0.0",
            "manifest": self.manifest,
            "role": "STUDIO_PUBLISHER",
            "actor_identifier": "owner-spoof",
        }
        self.assertIn(
            self.client.post("/api/studio/definitions/drafts/", payload, format="json").status_code,
            {401, 403},
        )
        self.client.force_authenticate(self.player)
        response = self.client.post(
            "/api/studio/definitions/drafts/",
            payload,
            format="json",
            HTTP_X_STUDIO_ROLE="STUDIO_EDITOR",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ProjectDefinitionVersion.objects.exists())

    def test_editor_create_viewer_read_publisher_atomic_bootstrap(self):
        self.client.force_authenticate(self.editor_user)
        create_response = self.client.post(
            "/api/studio/definitions/drafts/",
            {
                "project_id": str(self.project.pk),
                "code": "HTTP-DRAFT",
                "version": "1.0.0",
                "manifest": self.manifest,
            },
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.data)
        definition_id = create_response.data["id"]

        self.client.force_authenticate(self.viewer_user)
        read_response = self.client.get(f"/api/studio/definitions/{definition_id}/")
        self.assertEqual(read_response.status_code, 200, read_response.data)
        denied = self.client.put(
            f"/api/studio/definitions/{definition_id}/save/",
            {
                "manifest": self.manifest,
                "expected_manifest_hash": create_response.data["manifest_hash"],
            },
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.publisher_user)
        publish_response = self.client.post(
            f"/api/studio/definitions/{definition_id}/bootstrap/",
            {
                "workspace": self.workspace_spec(),
                "locale": "en",
                "role": "SERVICE",
                "actor_identifier": "owner-spoof",
            },
            format="json",
        )
        self.assertEqual(publish_response.status_code, 201, publish_response.data)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        definition = ProjectDefinitionVersion.objects.get(pk=definition_id)
        self.assertEqual(definition.published_by, f"django-user:{self.publisher_user.pk}")
        self.assertEqual(
            set(AuditEvent.objects.values_list("actor_identifier", flat=True)),
            {f"django-user:{self.publisher_user.pk}"},
        )
        self.assertNotIn(
            "owner-spoof",
            AuditEvent.objects.values_list("actor_identifier", flat=True),
        )

    def test_http_role_matrix_denies_every_ungranted_mutation(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="ROLE-MATRIX-DRAFT",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        definition_url = f"/api/studio/definitions/{definition.pk}/"

        self.client.force_authenticate(self.editor_user)
        self.assertEqual(self.client.get(definition_url).status_code, 200)
        self.assertEqual(
            self.client.post(f"{definition_url}validate/", {}, format="json").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"{definition_url}bootstrap/",
                {"workspace": self.workspace_spec()},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"{definition_url}publish/",
                {"workspace": self.workspace_spec()},
                format="json",
            ).status_code,
            403,
        )

        self.client.force_authenticate(self.publisher_user)
        self.assertEqual(self.client.get(definition_url).status_code, 200)
        self.assertEqual(
            self.client.put(
                f"{definition_url}save/",
                {
                    "manifest": self.manifest,
                    "expected_manifest_hash": definition.manifest_hash,
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/studio/definitions/drafts/",
                {
                    "project_id": str(self.project.pk),
                    "code": "PUBLISHER-CANNOT-CREATE",
                    "version": "2.0.0",
                    "manifest": self.manifest,
                },
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"{definition_url}clone/",
                {"code": "PUBLISHER-CANNOT-CLONE", "version": "2.0.0"},
                format="json",
            ).status_code,
            403,
        )

        self.client.force_authenticate(self.viewer_user)
        self.assertEqual(self.client.get(definition_url).status_code, 200)
        viewer_denials = (
            self.client.post(
                "/api/studio/definitions/drafts/",
                {
                    "project_id": str(self.project.pk),
                    "code": "VIEWER-CANNOT-CREATE",
                    "version": "2.0.0",
                    "manifest": self.manifest,
                },
                format="json",
            ),
            self.client.post(
                f"{definition_url}clone/",
                {"code": "VIEWER-CANNOT-CLONE", "version": "2.0.0"},
                format="json",
            ),
            self.client.put(
                f"{definition_url}save/",
                {
                    "manifest": self.manifest,
                    "expected_manifest_hash": definition.manifest_hash,
                },
                format="json",
            ),
            self.client.post(f"{definition_url}validate/", {}, format="json"),
            self.client.post(
                f"{definition_url}publish/",
                {"workspace": self.workspace_spec()},
                format="json",
            ),
            self.client.post(
                f"{definition_url}bootstrap/",
                {"workspace": self.workspace_spec()},
                format="json",
            ),
        )
        self.assertEqual([response.status_code for response in viewer_denials], [403] * 6)

        self.client.force_authenticate(self.player)
        self.assertEqual(self.client.get(definition_url).status_code, 403)
        player_denials = (
            self.client.post(
                "/api/studio/definitions/drafts/",
                {
                    "project_id": str(self.project.pk),
                    "code": "PLAYER-CANNOT-CREATE",
                    "version": "2.0.0",
                    "manifest": self.manifest,
                },
                format="json",
            ),
            self.client.post(
                f"{definition_url}clone/",
                {"code": "PLAYER-CLONE", "version": "2.0.0"},
                format="json",
            ),
            self.client.put(
                f"{definition_url}save/",
                {
                    "manifest": self.manifest,
                    "expected_manifest_hash": definition.manifest_hash,
                },
                format="json",
            ),
            self.client.post(f"{definition_url}validate/", {}, format="json"),
            self.client.post(
                f"{definition_url}publish/",
                {"workspace": self.workspace_spec()},
                format="json",
            ),
            self.client.post(
                f"{definition_url}bootstrap/",
                {"workspace": self.workspace_spec()},
                format="json",
            ),
        )
        self.assertEqual([response.status_code for response in player_denials], [403] * 6)
        definition.refresh_from_db()
        self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)
        self.assertEqual(ProjectDefinitionVersion.objects.count(), 1)

    def test_http_positive_clone_save_validate_publish_and_exact_help_paths(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="HTTP-POSITIVE-DRAFT",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        definition_url = f"/api/studio/definitions/{definition.pk}/"

        self.client.force_authenticate(self.editor_user)
        clone_response = self.client.post(
            f"{definition_url}clone/",
            {"code": "HTTP-POSITIVE-CLONE", "version": "2.0.0"},
            format="json",
        )
        self.assertEqual(clone_response.status_code, 201, clone_response.data)
        changed_manifest = copy.deepcopy(self.manifest)
        changed_manifest["project"]["name"] = "Changed snapshot description"
        save_response = self.client.put(
            f"/api/studio/definitions/{clone_response.data['id']}/save/",
            {
                "manifest": changed_manifest,
                "expected_manifest_hash": clone_response.data["manifest_hash"],
            },
            format="json",
        )
        self.assertEqual(save_response.status_code, 200, save_response.data)
        self.assertNotEqual(
            save_response.data["manifest_hash"],
            clone_response.data["manifest_hash"],
        )

        self.client.force_authenticate(self.publisher_user)
        validate_response = self.client.post(
            f"{definition_url}validate/",
            {},
            format="json",
        )
        self.assertEqual(validate_response.status_code, 200, validate_response.data)
        self.assertEqual(
            validate_response.data["publication_status"],
            PublicationStatus.VALIDATED,
        )
        publish_response = self.client.post(
            f"{definition_url}publish/",
            {"workspace": self.workspace_spec(), "locale": "en"},
            format="json",
        )
        self.assertEqual(publish_response.status_code, 201, publish_response.data)
        workspace_id = publish_response.data["initial_workspace_id"]

        self.client.force_authenticate(self.viewer_user)
        preworkspace_help = self.client.get(
            "/api/studio/help/studio.welcome/?locale=en&version=1.0.0"
        )
        self.assertEqual(preworkspace_help.status_code, 200, preworkspace_help.data)
        workspace_help = self.client.get(
            "/api/studio/help/studio.welcome/",
            {
                "locale": "en",
                "version": "1.0.0",
                "workspace_id": workspace_id,
            },
        )
        self.assertEqual(workspace_help.status_code, 200, workspace_help.data)
        self.assertEqual(
            workspace_help.data["content_sha256"],
            self.topic.content_sha256,
        )

        self.client.force_authenticate(self.player)
        self.assertEqual(
            self.client.get(
                "/api/studio/help/studio.welcome/?locale=en&version=1.0.0"
            ).status_code,
            403,
        )


class FoundationStudioBootstrapConcurrencyTests(
    FoundationStudioBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self) -> None:
        self.make_contract()

    def test_postgresql_concurrent_bootstrap_has_one_winner_and_one_explicit_conflict(self):
        if connection.vendor != "postgresql":
            self.skipTest("Concurrent select_for_update bootstrap gate is PostgreSQL-only.")
        definition = self.draft()
        definition_id = definition.pk
        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(index: int) -> None:
            close_old_connections()
            try:
                local_definition = ProjectDefinitionVersion.objects.get(pk=definition_id)
                barrier.wait(timeout=10)
                result = bootstrap_initial_project_definition(
                    definition=local_definition,
                    principal=self.publisher(actor=f"publisher-{index}"),
                    actor_identifier=f"publisher-{index}",
                    workspace_spec={
                        **self.workspace_spec(),
                        "id": f"19000000-0000-4000-8000-{index:012d}",
                    },
                    locale="en",
                )
                with lock:
                    outcomes.append(str(result.publication.pk))
            except Exception as exc:  # exact loser type asserted below
                with lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [threading.Thread(target=worker, args=(index,)) for index in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValidationError)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(
            list(
                AuditEvent.objects.filter(scope=AuditScope.DEFINITION)
                .order_by("action")
                .values_list("action", flat=True)
            ),
            [AuditAction.PUBLISH, AuditAction.VALIDATE],
        )
        self.assertEqual(
            list(
                AuditEvent.objects.filter(scope=AuditScope.WORKSPACE)
                .values_list("action", flat=True)
            ),
            [AuditAction.BOOTSTRAP],
        )
