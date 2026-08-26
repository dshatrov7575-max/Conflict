from __future__ import annotations

import copy
import hashlib
import json
import threading
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name

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
        self.publisher_user = User.objects.create_user(username="publisher", password="test-password")
        self.viewer_user = User.objects.create_user(username="viewer", password="test-password")
        self.inaccessible_user = User.objects.create_user(
            username="inaccessible", password="test-password"
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
        self.publisher_user.user_permissions.add(
            permissions["studio_read_definition"],
            permissions["studio_validate_definition"],
            permissions["studio_publish_definition"],
        )
        self.viewer_user.user_permissions.add(permissions["studio_read_definition"])
        self.inaccessible_user.user_permissions.add(permissions["studio_read_definition"])
        access_group = Group.objects.create(name=project_access_group_name(self.project.pk))
        access_group.user_set.add(
            self.player,
            self.editor_user,
            self.publisher_user,
            self.viewer_user,
        )
        self.create_url = f"/api/foundation/projects/{self.project.pk}/definitions/"

    def test_exact_401_403_and_object_scoped_404(self):
        payload = {"code": "HTTP-DRAFT", "version": "1.0.0", "manifest": self.manifest}
        self.assertEqual(self.client.post(self.create_url, payload, format="json").status_code, 401)

        self.client.force_authenticate(self.player)
        self.assertEqual(self.client.post(self.create_url, payload, format="json").status_code, 403)

        definition = create_project_definition_draft(
            project=self.project,
            code="INACCESSIBLE-DRAFT",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        self.client.force_authenticate(self.inaccessible_user)
        self.assertEqual(
            self.client.get(f"/api/foundation/definitions/{definition.pk}/").status_code,
            404,
        )

        other_manifest = copy.deepcopy(self.manifest)
        other_project = Project.objects.create(
            code="PROJECT-STUDIO-OTHER",
            version="2.0.0",
            name="Other inaccessible project",
        )
        other_manifest["project"].update(
            {
                "id": str(other_project.pk),
                "code": other_project.code,
                "version": other_project.version,
            }
        )
        other_definition = create_project_definition_draft(
            project=other_project,
            code="CROSS-PROJECT-DRAFT",
            version="1.0.0",
            manifest=other_manifest,
            principal=self.editor(),
        )
        self.client.force_authenticate(self.viewer_user)
        self.assertEqual(
            self.client.get(
                f"/api/foundation/definitions/{other_definition.pk}/"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/foundation/projects/{other_project.pk}/definitions/",
                {
                    "code": "CROSS-PROJECT-CREATE",
                    "version": "2.0.0",
                    "manifest": other_manifest,
                },
                format="json",
            ).status_code,
            404,
        )

    def test_complete_public_http_role_denial_matrix(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="HTTP-ROLE-MATRIX",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        definition_url = f"/api/foundation/definitions/{definition.pk}/"
        create_payload = {
            "code": "HTTP-ROLE-MATRIX-NEW",
            "version": "2.0.0",
            "manifest": self.manifest,
        }
        mutation_count = ProjectDefinitionVersion.objects.count()

        cases = (
            (self.player, "GET", definition_url, None, {}, 403),
            (self.player, "POST", self.create_url, create_payload, {}, 403),
            (self.viewer_user, "POST", self.create_url, create_payload, {}, 403),
            (
                self.viewer_user,
                "POST",
                f"{definition_url}clone/",
                {"code": "VIEWER-CLONE", "version": "3.0.0"},
                {},
                403,
            ),
            (
                self.viewer_user,
                "PUT",
                f"{definition_url}draft/",
                {"manifest": self.manifest},
                {"HTTP_IF_MATCH": f'"{definition.manifest_hash}"'},
                403,
            ),
            (self.viewer_user, "POST", f"{definition_url}validate/", {}, {}, 403),
            (
                self.viewer_user,
                "POST",
                f"{definition_url}publish-initial/",
                {"workspace": self.workspace_spec(), "locale": "en"},
                {},
                403,
            ),
            (self.editor_user, "POST", f"{definition_url}validate/", {}, {}, 403),
            (
                self.editor_user,
                "POST",
                f"{definition_url}publish-initial/",
                {"workspace": self.workspace_spec(), "locale": "en"},
                {},
                403,
            ),
            (self.publisher_user, "POST", self.create_url, create_payload, {}, 403),
            (
                self.publisher_user,
                "POST",
                f"{definition_url}clone/",
                {"code": "PUBLISHER-CLONE", "version": "4.0.0"},
                {},
                403,
            ),
            (
                self.publisher_user,
                "PUT",
                f"{definition_url}draft/",
                {"manifest": self.manifest},
                {"HTTP_IF_MATCH": f'"{definition.manifest_hash}"'},
                403,
            ),
        )
        for user, method, path, payload, headers, expected in cases:
            with self.subTest(user=user.username, method=method, path=path):
                self.client.force_authenticate(user)
                request = getattr(self.client, method.lower())
                response = request(path, payload, format="json", **headers)
                self.assertEqual(response.status_code, expected, response.data)

        malformed_denials = (
            (self.player, "POST", self.create_url),
            (self.viewer_user, "POST", f"{definition_url}validate/"),
            (self.editor_user, "POST", f"{definition_url}publish-initial/"),
            (self.publisher_user, "POST", f"{definition_url}clone/"),
        )
        for user, method, path in malformed_denials:
            with self.subTest(user=user.username, malformed_path=path):
                self.client.force_authenticate(user)
                response = self.client.generic(
                    method,
                    path,
                    b"{not-json",
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 403, response.data)

        self.client.force_authenticate(self.viewer_user)
        self.assertEqual(self.client.get(definition_url).status_code, 200)
        self.assertEqual(
            self.client.get(
                "/api/foundation/help/studio.welcome/",
                {"application": "STUDIO", "locale": "en", "version": "1.0.0"},
            ).status_code,
            200,
        )
        self.client.force_authenticate(self.publisher_user)
        self.assertEqual(self.client.get(definition_url).status_code, 200)
        self.client.force_authenticate(self.player)
        self.assertEqual(
            self.client.get(
                "/api/foundation/help/studio.welcome/",
                {"application": "STUDIO", "locale": "en", "version": "1.0.0"},
            ).status_code,
            403,
        )
        self.assertEqual(ProjectDefinitionVersion.objects.count(), mutation_count)
        self.assertFalse(ProjectPublication.objects.exists())
        self.assertFalse(ProjectWorkspace.objects.exists())

    def test_server_authority_spoof_vectors_reject_without_mutation(self):
        self.client.force_authenticate(self.editor_user)
        baseline = ProjectDefinitionVersion.objects.count()
        base = {"code": "SPOOF-DRAFT", "version": "1.0.0", "manifest": self.manifest}
        body_spoof = self.client.post(
            self.create_url,
            {**base, "actor_identifier": "spoof", "role": "STUDIO_PUBLISHER"},
            format="json",
        )
        header_spoof = self.client.post(
            self.create_url,
            base,
            format="json",
            HTTP_X_STUDIO_ROLE="STUDIO_EDITOR",
        )
        query_spoof = self.client.post(
            f"{self.create_url}?capability=DRAFT_CREATE",
            base,
            format="json",
        )
        self.assertEqual(
            [body_spoof.status_code, header_spoof.status_code, query_spoof.status_code],
            [400, 400, 400],
        )
        self.assertEqual(ProjectDefinitionVersion.objects.count(), baseline)

    def test_editor_viewer_publisher_matrix_and_exact_routes(self):
        self.client.force_authenticate(self.editor_user)
        create_response = self.client.post(
            self.create_url,
            {"code": "HTTP-DRAFT", "version": "1.0.0", "manifest": self.manifest},
            format="json",
        )
        self.assertEqual(create_response.status_code, 201, create_response.data)
        self.assertEqual(create_response["ETag"], f'"{create_response.data["manifest_hash"]}"')
        definition_url = f"/api/foundation/definitions/{create_response.data['id']}/"

        clone_response = self.client.post(
            f"{definition_url}clone/",
            {"code": "HTTP-CLONE", "version": "2.0.0"},
            format="json",
        )
        self.assertEqual(clone_response.status_code, 201, clone_response.data)
        changed_manifest = copy.deepcopy(self.manifest)
        changed_manifest["project"]["name"] = "Changed snapshot description"
        save_response = self.client.put(
            f"/api/foundation/definitions/{clone_response.data['id']}/draft/",
            {"manifest": changed_manifest},
            format="json",
            HTTP_IF_MATCH=f'"{clone_response.data["manifest_hash"]}"',
        )
        self.assertEqual(save_response.status_code, 200, save_response.data)

        self.client.force_authenticate(self.viewer_user)
        self.assertEqual(self.client.get(definition_url).status_code, 200)
        self.assertEqual(
            self.client.put(
                f"{definition_url}draft/",
                {"manifest": self.manifest},
                format="json",
                HTTP_IF_MATCH=f'"{create_response.data["manifest_hash"]}"',
            ).status_code,
            403,
        )

        self.client.force_authenticate(self.publisher_user)
        response = self.client.post(
            f"{definition_url}publish-initial/",
            {"workspace": self.workspace_spec(), "locale": "en"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(
            set(AuditEvent.objects.values_list("actor_identifier", flat=True)),
            {f"django-user:{self.publisher_user.pk}"},
        )
        self.assertEqual(self.client.post(self.create_url, {}, format="json").status_code, 403)

        self.client.force_authenticate(self.viewer_user)
        help_response = self.client.get(
            "/api/foundation/help/studio.welcome/",
            {"application": "STUDIO", "locale": "en", "version": "1.0.0"},
        )
        self.assertEqual(help_response.status_code, 200, help_response.data)
        self.assertEqual(help_response.data["content_sha256"], self.topic.content_sha256)

    def test_session_authentication_enforces_csrf_and_strong_if_match(self):
        definition = create_project_definition_draft(
            project=self.project,
            code="SESSION-DRAFT",
            version="1.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        client = APIClient(enforce_csrf_checks=True)
        self.assertTrue(client.login(username="editor", password="test-password"))
        definition_url = f"/api/foundation/definitions/{definition.pk}/"
        self.assertEqual(client.get(definition_url).status_code, 200)
        token = client.cookies["csrftoken"].value
        changed = copy.deepcopy(self.manifest)
        changed["project"]["name"] = "CSRF exact save"
        denied = client.put(
            f"{definition_url}draft/",
            {"manifest": changed},
            format="json",
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
        )
        self.assertEqual(denied.status_code, 403)
        definition.refresh_from_db()
        self.assertEqual(definition.manifest, self.manifest)
        accepted = client.put(
            f"{definition_url}draft/",
            {"manifest": changed},
            format="json",
            HTTP_IF_MATCH=f'"{definition.manifest_hash}"',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(accepted.status_code, 200, accepted.data)


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
