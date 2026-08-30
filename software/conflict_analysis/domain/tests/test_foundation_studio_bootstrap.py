from __future__ import annotations

import copy
import hashlib
import json
import threading
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import OperationalError, close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from domain.api.studio_definitions import project_access_group_name

from domain.enums import (
    AuditAction,
    AuditActorType,
    AuditScope,
    HelpApplicationScope,
    PublicationStatus,
)
from domain.models import (
    AuditEvent,
    HelpTopic,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    ProjectWorkspace,
    UIHelpBinding,
    _canonical_studio_write,
)
from domain.policies import (
    FoundationAuditContext,
    ServiceMutationContext,
    StudioAuthorizationDenied,
    StudioCapability,
    StudioDefinitionRole,
    StudioPrincipal,
    StudioRole,
    bootstrap_initial_project_definition,
    can_modify_project_structure,
    publish_project_definition,
    require_studio_capability,
    studio_principal_from_user,
    validate_project_definition,
)
from domain.services.project_definitions import (
    FoundationStudioApplicationConflict,
    bootstrap_project_definition_draft,
    clone_project_definition_draft,
    create_project_definition_draft,
    hash_project_definition_manifest_v1,
    open_project_definition,
    open_project_definition_draft,
    publish_successor_project_definition,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "foundation_studio_definition_vectors_v1.json"
)

# Shared by the FD05 write-reconciliation suite.  These are the three atomic
# boundary probes accepted for every audited HUMAN mutation: a fault after the
# domain change, immediately before the immutable audit append, and immediately
# after that append must all leave the database at its pre-operation snapshot.
FD05_HUMAN_WRITE_FAILURE_STAGES = (
    "after_domain_mutation",
    "before_audit_insert",
    "after_audit_insert",
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
        self.assertFalse(
            AuditEvent.objects.exclude(
                actor_type=AuditActorType.HUMAN,
                actor_identifier="publisher",
            ).exists()
        )

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
        for stage in stages:
            with self.subTest(stage=stage):
                definition = self.draft(code=f"DEF-{stage.upper().replace('_', '-')}")
                original_manifest = copy.deepcopy(definition.manifest)
                original_hash = definition.manifest_hash
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
                self.assertEqual(definition.manifest, original_manifest)
                self.assertEqual(definition.manifest_hash, original_hash)
                self.assertEqual(definition.publication_status, PublicationStatus.DRAFT)
                self.assertIsNone(definition.validated_at)
                self.assertIsNone(definition.published_at)
                self.assertFalse(definition.is_current)
                self.assertFalse(ProjectWorkspace.objects.exists())
                self.assertFalse(ProjectPublication.objects.exists())
                self.assertFalse(AuditEvent.objects.exists())
                self.assertEqual(UIHelpBinding.objects.filter(workspace__isnull=False).count(), 0)
                definition.delete()

    def test_initial_bootstrap_rejects_competing_unreceipted_current_without_demotion(self):
        competing_manifest = {"legacy_contract": "foundation-v4"}
        competing_hash = hashlib.sha256(
            json.dumps(
                competing_manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        competing = ProjectDefinitionVersion.objects.create(
            project=self.project,
            code="LEGACY-COMPETING-CURRENT",
            version="0.9.0",
            schema_version="2.0.0",
            semantic_version="1.0.0",
            construct_version="1.0.0",
            manifest=competing_manifest,
            manifest_hash=competing_hash,
            publication_status=PublicationStatus.PUBLISHED,
            validated_at=timezone.now(),
            validated_by="legacy-publisher",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="legacy-publisher",
            is_current=True,
        )
        candidate = self.draft(code="TYPED-COMPETING-CANDIDATE")

        with self.assertRaisesRegex(ValidationError, "unreceipted current"):
            bootstrap_initial_project_definition(
                definition=candidate,
                principal=self.publisher(),
                actor_identifier="publisher",
                workspace_spec=self.workspace_spec(),
                locale="en",
            )

        candidate.refresh_from_db()
        competing.refresh_from_db()
        self.assertEqual(candidate.publication_status, PublicationStatus.DRAFT)
        self.assertFalse(candidate.is_current)
        self.assertTrue(competing.is_current)
        self.assertFalse(ProjectPublication.objects.exists())
        self.assertFalse(ProjectWorkspace.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

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

    def test_accepted_policy_names_and_sealed_service_context(self):
        self.assertIs(StudioRole, StudioDefinitionRole)
        self.assertTrue(issubclass(StudioAuthorizationDenied, PermissionDenied))
        service = StudioPrincipal.service(
            actor_identifier="sealed-service",
            purpose="Exact Foundation mutation",
            capabilities=frozenset({StudioCapability.FOUNDATION_IMPORT}),
        )
        self.assertIsInstance(service.service_context, ServiceMutationContext)
        self.assertEqual(service.service_context.purpose, "Exact Foundation mutation")
        self.assertEqual(service.service_purpose, "Exact Foundation mutation")
        with self.assertRaisesRegex(ValueError, "trusted server factory"):
            ServiceMutationContext(
                actor_identifier="forged-service",
                purpose="Forged mutation",
                capabilities=frozenset({StudioCapability.FOUNDATION_IMPORT}),
            )
        with self.assertRaisesRegex(ValueError, "trusted server factory"):
            FoundationAuditContext(
                actor_type=AuditActorType.HUMAN,
                actor_identifier="forged-human",
                purpose="",
                scope=AuditScope.DEFINITION,
                project_id=self.project.pk,
                workspace_id=None,
                definition_version_id=self.project.pk,
            )
        viewer = StudioPrincipal.for_role(
            actor_identifier="viewer",
            role=StudioDefinitionRole.VIEWER,
        )
        with self.assertRaises(StudioAuthorizationDenied):
            require_studio_capability(viewer, StudioCapability.DEFINITION_PUBLISH)

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
        payload = {
            "id": str(uuid4()),
            "code": "HTTP-DRAFT",
            "version": "1.0.0",
            "manifest": self.manifest,
            "semantic_version": "1.0.0",
            "construct_version": "1.0.0",
        }
        self.assertEqual(
            self.client.post(
                self.create_url,
                payload,
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            ).status_code,
            401,
        )

        self.client.force_authenticate(self.player)
        self.assertEqual(
            self.client.post(
                self.create_url,
                payload,
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            ).status_code,
            403,
        )

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
                    "id": str(uuid4()),
                    "code": "CROSS-PROJECT-CREATE",
                    "version": "2.0.0",
                    "manifest": other_manifest,
                    "semantic_version": "1.0.0",
                    "construct_version": "1.0.0",
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
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
            "id": str(uuid4()),
            "code": "HTTP-ROLE-MATRIX-NEW",
            "version": "2.0.0",
            "manifest": self.manifest,
            "semantic_version": "1.0.0",
            "construct_version": "1.0.0",
        }
        mutation_count = ProjectDefinitionVersion.objects.count()

        cases = (
            (self.player, "GET", definition_url, None, {}, 403),
            (
                self.player,
                "POST",
                self.create_url,
                create_payload,
                {"HTTP_IDEMPOTENCY_KEY": str(uuid4())},
                403,
            ),
            (
                self.viewer_user,
                "POST",
                self.create_url,
                create_payload,
                {"HTTP_IDEMPOTENCY_KEY": str(uuid4())},
                403,
            ),
            (
                self.viewer_user,
                "POST",
                f"{definition_url}clone/",
                {
                    "id": str(uuid4()),
                    "code": "VIEWER-CLONE",
                    "version": "3.0.0",
                },
                {
                    "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
                    "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
                },
                403,
            ),
            (
                self.viewer_user,
                "PUT",
                f"{definition_url}draft/",
                {"manifest": self.manifest},
                {
                    "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
                    "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
                },
                403,
            ),
            (
                self.viewer_user,
                "POST",
                f"{definition_url}validate/",
                {},
                {
                    "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
                    "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
                },
                403,
            ),
            (
                self.viewer_user,
                "POST",
                f"{definition_url}publish-initial/",
                {"workspace": self.workspace_spec(), "locale": "en"},
                {},
                403,
            ),
            (
                self.editor_user,
                "POST",
                f"{definition_url}validate/",
                {},
                {
                    "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
                    "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
                },
                403,
            ),
            (
                self.editor_user,
                "POST",
                f"{definition_url}publish-initial/",
                {"workspace": self.workspace_spec(), "locale": "en"},
                {},
                403,
            ),
            (
                self.publisher_user,
                "POST",
                self.create_url,
                create_payload,
                {"HTTP_IDEMPOTENCY_KEY": str(uuid4())},
                403,
            ),
            (
                self.publisher_user,
                "POST",
                f"{definition_url}clone/",
                {
                    "id": str(uuid4()),
                    "code": "PUBLISHER-CLONE",
                    "version": "4.0.0",
                },
                {
                    "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
                    "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
                },
                403,
            ),
            (
                self.publisher_user,
                "PUT",
                f"{definition_url}draft/",
                {"manifest": self.manifest},
                {
                    "HTTP_IDEMPOTENCY_KEY": str(uuid4()),
                    "HTTP_IF_MATCH": f'"{definition.manifest_hash}"',
                },
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
        base = {
            "id": str(uuid4()),
            "code": "SPOOF-DRAFT",
            "version": "1.0.0",
            "manifest": self.manifest,
            "semantic_version": "1.0.0",
            "construct_version": "1.0.0",
        }
        body_spoof = self.client.post(
            self.create_url,
            {**base, "actor_identifier": "spoof", "role": "STUDIO_PUBLISHER"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        service_spoof = self.client.post(
            self.create_url,
            {
                **base,
                "service_context": {
                    "actor_identifier": "http-service",
                    "purpose": "HTTP must never construct SERVICE",
                    "capabilities": ["DRAFT_CREATE"],
                },
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        header_spoof = self.client.post(
            self.create_url,
            base,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_X_STUDIO_ROLE="STUDIO_EDITOR",
        )
        query_spoof = self.client.post(
            f"{self.create_url}?capability=DRAFT_CREATE",
            base,
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(
            [
                body_spoof.status_code,
                service_spoof.status_code,
                header_spoof.status_code,
                query_spoof.status_code,
            ],
            [400, 400, 400, 400],
        )
        self.assertEqual(ProjectDefinitionVersion.objects.count(), baseline)

    def test_editor_viewer_publisher_matrix_and_exact_routes(self):
        self.client.force_authenticate(self.editor_user)
        create_id = uuid4()
        create_response = self.client.post(
            self.create_url,
            {
                "id": str(create_id),
                "code": "HTTP-DRAFT",
                "version": "1.0.0",
                "manifest": self.manifest,
                "semantic_version": "1.0.0",
                "construct_version": "1.0.0",
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
        )
        self.assertEqual(create_response.status_code, 201, create_response.data)
        self.assertEqual(create_response.data["id"], str(create_id))
        self.assertEqual(create_response["ETag"], f'"{create_response.data["manifest_hash"]}"')
        definition_url = f"/api/foundation/definitions/{create_response.data['id']}/"

        clone_id = uuid4()
        clone_response = self.client.post(
            f"{definition_url}clone/",
            {"id": str(clone_id), "code": "HTTP-CLONE", "version": "2.0.0"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            HTTP_IF_MATCH=f'"{create_response.data["manifest_hash"]}"',
        )
        self.assertEqual(clone_response.status_code, 201, clone_response.data)
        self.assertEqual(clone_response.data["id"], str(clone_id))
        changed_manifest = copy.deepcopy(self.manifest)
        changed_manifest["project"]["name"] = "Changed snapshot description"
        save_response = self.client.put(
            f"/api/foundation/definitions/{clone_response.data['id']}/draft/",
            {"manifest": changed_manifest},
            format="json",
            HTTP_IF_MATCH=f'"{clone_response.data["manifest_hash"]}"',
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
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
                HTTP_IDEMPOTENCY_KEY=str(uuid4()),
            ).status_code,
            403,
        )

        self.client.force_authenticate(self.publisher_user)
        publication_operation_id = uuid4()
        response = self.client.post(
            f"{definition_url}publish-initial/",
            {"workspace": self.workspace_spec(), "locale": "en"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(publication_operation_id),
            HTTP_IF_MATCH=f'"{create_response.data["manifest_hash"]}"',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(ProjectPublication.objects.count(), 1)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.assertEqual(
            set(AuditEvent.objects.values_list("actor_identifier", flat=True)),
            {
                f"django-user:{self.editor_user.pk}",
                f"django-user:{self.publisher_user.pk}",
            },
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
            HTTP_IDEMPOTENCY_KEY=str(uuid4()),
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

import copy
import hashlib
import threading

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from domain.enums import (
    AuditAction,
    AuditActorType,
    AuditScope,
    HelpApplicationScope,
    ImportPackageScope,
    ImportRunStatus,
    PublicationStatus,
)
from domain.models import (
    AuditEvent,
    HelpTopic,
    ImportRun,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    ProjectWorkspace,
    UIHelpBinding,
)
from domain.policies import (
    bootstrap_initial_project_definition,
    publish_project_definition,
    validate_project_definition,
)
from domain.services.project_definitions import (
    clone_project_definition_draft,
    create_project_definition_draft,
)

def _legacy_manifest_hash(manifest: dict) -> str:
    import json

    return hashlib.sha256(
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


class FoundationStudioP0PersistenceIntegrityTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()

    def _bootstrap(self, *, code: str = "P0-INTEGRITY-INITIAL"):
        return bootstrap_initial_project_definition(
            definition=self.draft(code=code),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )

    def test_typed_definition_model_and_manager_paths_cannot_forge_lifecycle(self):
        direct = ProjectDefinitionVersion(
            project=self.project,
            code="P0-DIRECT-TYPED",
            version="2.0.0",
            manifest=copy.deepcopy(self.manifest),
        )
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            direct.save(force_insert=True)
        self.assertFalse(ProjectDefinitionVersion.objects.filter(pk=direct.pk).exists())
        with self.assertRaises(ValidationError):
            ProjectDefinitionVersion._base_manager.bulk_create([direct])

        forged_bulk = ProjectDefinitionVersion(
            project=self.project,
            code="P0-BULK-FORGED",
            version="3.0.0",
            publication_status=PublicationStatus.PUBLISHED,
            manifest=copy.deepcopy(self.manifest),
            manifest_hash="f" * 64,
            validated_at=timezone.now(),
            validated_by="caller",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="caller",
            is_current=True,
        )
        for conflict_kwargs in (
            {},
            {"ignore_conflicts": True},
            {
                "update_conflicts": True,
                "update_fields": ["manifest"],
                "unique_fields": ["id"],
            },
        ):
            with self.subTest(conflict_kwargs=conflict_kwargs):
                with self.assertRaises(ValidationError):
                    ProjectDefinitionVersion.objects.bulk_create(
                        [forged_bulk],
                        **conflict_kwargs,
                    )
                self.assertFalse(
                    ProjectDefinitionVersion.objects.filter(pk=forged_bulk.pk).exists()
                )

        draft = create_project_definition_draft(
            project=self.project,
            code="P0-SERVICE-DRAFT",
            version="4.0.0",
            manifest=self.manifest,
            principal=self.editor(),
        )
        draft.publication_status = PublicationStatus.VALIDATED
        draft.validated_at = timezone.now()
        draft.validated_by = "caller"
        draft.validation_result = {"valid": True}
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            draft.save()
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            ProjectDefinitionVersion.objects.filter(pk=draft.pk).update(
                is_current=False
            )
        draft.refresh_from_db()
        self.assertEqual(draft.publication_status, PublicationStatus.DRAFT)
        self.assertEqual(draft.validation_result, {})

    def test_workspace_save_and_bulk_recheck_published_project_and_hash(self):
        draft = self.draft(code="P0-WORKSPACE-DRAFT-PIN")
        draft_pin = ProjectWorkspace(
            project=self.project,
            definition_version=draft,
            definition_manifest_hash=draft.manifest_hash,
            code="P0-DRAFT-PIN",
            version="1.0.0",
            name="Invalid DRAFT pin",
        )
        with self.assertRaises(ValidationError):
            draft_pin.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([draft_pin])
        with self.assertRaises(ValidationError):
            ProjectWorkspace._base_manager.bulk_create([draft_pin])
        self.assertFalse(ProjectWorkspace.objects.filter(pk=draft_pin.pk).exists())

        result = bootstrap_initial_project_definition(
            definition=draft,
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        stale_hash = ProjectWorkspace(
            project=self.project,
            definition_version=result.definition,
            definition_manifest_hash="0" * 64,
            code="P0-STALE-HASH",
            version="1.0.0",
            name="Invalid stale checksum",
        )
        with self.assertRaises(ValidationError):
            stale_hash.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([stale_hash])

        foreign_project = Project.objects.create(
            code="P0-FOREIGN-PROJECT",
            version="1.0.0",
            name="Foreign project",
        )
        foreign_manifest = {"legacy": "published-definition"}
        foreign_definition = ProjectDefinitionVersion.objects.create(
            project=foreign_project,
            code="P0-FOREIGN-DEFINITION",
            version="1.0.0",
            publication_status=PublicationStatus.PUBLISHED,
            manifest=foreign_manifest,
            manifest_hash=_legacy_manifest_hash(foreign_manifest),
            validated_at=timezone.now(),
            validated_by="legacy",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="legacy",
            is_current=True,
        )
        foreign_pin = ProjectWorkspace(
            project=self.project,
            definition_version=foreign_definition,
            definition_manifest_hash=foreign_definition.manifest_hash,
            code="P0-FOREIGN-PIN",
            version="1.0.0",
            name="Invalid cross-project pin",
        )
        with self.assertRaises(ValidationError):
            foreign_pin.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([foreign_pin])
        with self.assertRaisesRegex(ValidationError, "project/definition pin"):
            ProjectWorkspace.objects.filter(pk=result.workspace.pk).update(
                project=foreign_project
            )
        result.workspace.project = foreign_project
        with self.assertRaisesRegex(ValidationError, "project/definition pin"):
            ProjectWorkspace.objects.bulk_update([result.workspace], ["project"])
        result.workspace.refresh_from_db()
        self.assertEqual(str(result.workspace.project_id), str(self.project.pk))

        duplicate_default = ProjectWorkspace(
            project=self.project,
            definition_version=result.definition,
            definition_manifest_hash=result.definition.manifest_hash,
            code="P0-SECOND-DEFAULT",
            version="1.0.0",
            name="Second default",
            is_default=True,
        )
        with self.assertRaises(ValidationError):
            ProjectWorkspace.objects.bulk_create([duplicate_default])
        with self.assertRaisesRegex(ValidationError, "identity conflicts"):
            ProjectWorkspace.objects.bulk_create(
                [duplicate_default],
                ignore_conflicts=True,
            )
        self.assertEqual(ProjectWorkspace.objects.count(), 1)

    def test_publication_direct_and_bulk_paths_cannot_forge_typed_receipts(self):
        result = self._bootstrap()
        forged = ProjectPublication(
            project=self.project,
            definition_version=result.definition,
            initial_workspace=None,
            code="P0-FORGED-PUBLICATION",
            version="1.0.0",
            locale="ru",
            actor_identifier="caller",
            validation_result=result.definition.validation_result,
        )
        with self.assertRaisesRegex(ValidationError, "canonical Studio service"):
            forged.save(force_insert=True)
        with self.assertRaisesRegex(ValidationError, "canonical Studio publication service"):
            ProjectPublication.objects.bulk_create([forged])
        with self.assertRaisesRegex(ValidationError, "canonical Studio publication service"):
            ProjectPublication._base_manager.bulk_create([forged])
        with self.assertRaisesRegex(ValidationError, "identity conflicts"):
            ProjectPublication.objects.bulk_create([forged], ignore_conflicts=True)
        self.assertEqual(ProjectPublication.objects.count(), 1)

        other_project = Project.objects.create(
            code="P0-PUBLICATION-FOREIGN",
            version="1.0.0",
            name="Other project",
        )
        foreign_manifest = {"legacy": "foreign-publication-definition"}
        foreign_definition = ProjectDefinitionVersion.objects.create(
            project=other_project,
            code="P0-PUBLICATION-FOREIGN-DEFINITION",
            version="1.0.0",
            publication_status=PublicationStatus.PUBLISHED,
            manifest=foreign_manifest,
            manifest_hash=_legacy_manifest_hash(foreign_manifest),
            validated_at=timezone.now(),
            validated_by="legacy",
            validation_result={"valid": True},
            published_at=timezone.now(),
            published_by="legacy",
            is_current=True,
        )
        foreign_workspace = ProjectWorkspace.objects.create(
            project=other_project,
            definition_version=foreign_definition,
            definition_manifest_hash=foreign_definition.manifest_hash,
            code="P0-MISMATCHED-INITIAL",
            version="1.0.0",
            name="Mismatched initial",
            is_default=True,
        )
        mismatched_publication = ProjectPublication(
            project=self.project,
            definition_version=result.definition,
            initial_workspace=foreign_workspace,
            code="P0-MISMATCHED-PUBLICATION",
            version="1.0.0",
            locale="ru",
            actor_identifier="caller",
            validation_result=result.definition.validation_result,
        )
        with self.assertRaises(ValidationError):
            mismatched_publication.full_clean()
        with self.assertRaises(ValidationError):
            mismatched_publication.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ProjectPublication.objects.bulk_create([mismatched_publication])

    def test_scoped_immutable_models_reject_bulk_bypass_and_conflict_flags(self):
        result = self._bootstrap(code="P0-SCOPED-INITIAL")
        workspace = result.workspace
        definition = result.definition

        invalid_audits = (
            AuditEvent(
                project=self.project,
                workspace=workspace,
                definition_version=definition,
                scope=AuditScope.DEFINITION,
                code="P0-AUDIT-DUAL",
                version="1.0.0",
                action=AuditAction.PUBLISH,
                actor_type=AuditActorType.HUMAN,
                actor_identifier="caller",
                entity_type="PROJECT_DEFINITION_VERSION",
                entity_id=definition.pk,
            ),
            AuditEvent(
                project=self.project,
                workspace=None,
                definition_version=None,
                scope=AuditScope.DEFINITION,
                code="P0-AUDIT-ZERO",
                version="1.0.0",
                action=AuditAction.PUBLISH,
                actor_type=AuditActorType.HUMAN,
                actor_identifier="caller",
                entity_type="PROJECT_DEFINITION_VERSION",
                entity_id=definition.pk,
            ),
        )
        for event in invalid_audits:
            with self.subTest(code=event.code):
                with self.assertRaises(ValidationError):
                    event.save(force_insert=True)
                with self.assertRaises(ValidationError):
                    AuditEvent.objects.bulk_create([event])
                with self.assertRaises(ValidationError):
                    AuditEvent._base_manager.bulk_create([event])
                self.assertFalse(AuditEvent.objects.filter(pk=event.pk).exists())

        duplicate_binding = UIHelpBinding(
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            code="P0-DUPLICATE-GLOBAL-HELP",
            version="1.0.0",
            ui_key="studio.welcome",
            locale="en",
            help_topic=self.topic,
        )
        with self.assertRaises(ValidationError):
            duplicate_binding.save(force_insert=True)
        with self.assertRaises(ValidationError):
            UIHelpBinding.objects.bulk_create([duplicate_binding])
        with self.assertRaises(ValidationError):
            UIHelpBinding._base_manager.bulk_create([duplicate_binding])

        player_html = "<p>Player-only help.</p>"
        player_topic = HelpTopic(
            code="P0-PLAYER-HELP",
            version="1.0.0",
            stable_key="player.only",
            title="Player help",
            application_scope=HelpApplicationScope.PLAYER,
            construct_version="1.0.0",
            term_version="1.0.0",
            locale="en",
            sanitized_html=player_html,
            content_sha256=hashlib.sha256(player_html.encode("utf-8")).hexdigest(),
            publication_status=PublicationStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        player_topic.save(force_insert=True)
        illegal_global_binding = UIHelpBinding(
            workspace=None,
            application_scope=HelpApplicationScope.PLAYER,
            code="P0-ILLEGAL-GLOBAL-HELP",
            version="1.0.0",
            ui_key="player.only",
            locale="en",
            help_topic=player_topic,
        )
        with self.assertRaises(ValidationError):
            illegal_global_binding.save(force_insert=True)
        with self.assertRaises(ValidationError):
            UIHelpBinding.objects.bulk_create([illegal_global_binding])

        invalid_receipt = ImportRun(
            project=self.project,
            workspace=workspace,
            definition_version=definition,
            package_scope=ImportPackageScope.PROJECT_DEFINITION,
            code="P0-ILLEGAL-DEFINITION-RECEIPT",
            version="2.1.0",
            package_format="conflict-analysis-foundation",
            package_id="P0-ILLEGAL-PACKAGE",
            package_version="2.1.0",
            schema_version="2.1.0",
            template_version="1.0.0",
            method_version="PROJECT_DEFINITION_MANIFEST_VALIDATION_V1",
            ontology_version="1.0.0",
            dataset_version="1.0.0",
            checksum="a" * 64,
            adapter="json",
            status=ImportRunStatus.REJECTED,
            actor_identifier="caller",
        )
        with self.assertRaises(ValidationError):
            invalid_receipt.save(force_insert=True)
        with self.assertRaises(ValidationError):
            ImportRun.objects.bulk_create([invalid_receipt])
        with self.assertRaises(ValidationError):
            ImportRun._base_manager.bulk_create([invalid_receipt])

        existing_audit = AuditEvent.objects.filter(scope=AuditScope.DEFINITION).first()
        existing_binding = UIHelpBinding.objects.filter(workspace__isnull=True).first()
        committed_receipt = ImportRun.objects.create(
            project=self.project,
            workspace=None,
            definition_version=definition,
            package_scope=ImportPackageScope.PROJECT_DEFINITION,
            code="P0-EXISTING-DEFINITION-RECEIPT",
            version="2.1.0",
            package_format="conflict-analysis-foundation",
            package_id="P0-EXISTING-PACKAGE",
            package_version="2.1.0",
            schema_version="2.1.0",
            template_version="1.0.0",
            method_version="PROJECT_DEFINITION_MANIFEST_VALIDATION_V1",
            ontology_version="1.0.0",
            dataset_version="1.0.0",
            checksum="b" * 64,
            adapter="json",
            status=ImportRunStatus.COMMITTED,
            actor_identifier="service",
            committed_at=timezone.now(),
        )
        for model, row in (
            (AuditEvent, existing_audit),
            (UIHelpBinding, existing_binding),
            (ImportRun, committed_receipt),
        ):
            assert row is not None
            with self.subTest(model=model.__name__, operation="ignore"):
                with self.assertRaisesRegex(ValidationError, "identity conflicts"):
                    model.objects.bulk_create([row], ignore_conflicts=True)
            with self.subTest(model=model.__name__, operation="update_conflicts"):
                with self.assertRaisesRegex(ValidationError, "identity conflicts"):
                    model.objects.bulk_create(
                        [row],
                        update_conflicts=True,
                        update_fields=["version"],
                        unique_fields=["id"],
                    )
            with self.subTest(model=model.__name__, operation="update"):
                with self.assertRaisesRegex(ValidationError, "append-only"):
                    model.objects.filter(pk=row.pk).update(version="9.9.9")


class FoundationStudioTypedSuccessorPublicationTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()
        self.initial = bootstrap_initial_project_definition(
            definition=self.draft(code="P0-SUCCESSOR-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )

    def _validated_successor(self, *, code: str, version: str):
        draft = clone_project_definition_draft(
            self.initial.definition,
            code=code,
            version=version,
            principal=self.editor(),
        )
        return validate_project_definition(
            draft,
            actor_identifier="publisher",
            principal=self.publisher(),
        )

    def test_successor_has_one_ordinary_receipt_and_preserves_old_workspace_pin(self):
        old_workspace_id = self.initial.workspace.pk
        old_definition_id = self.initial.workspace.definition_version_id
        old_hash = self.initial.workspace.definition_manifest_hash
        old_binding_ids = tuple(
            UIHelpBinding.objects.filter(workspace=self.initial.workspace)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
        old_workspace_audit_count = AuditEvent.objects.filter(
            scope=AuditScope.WORKSPACE
        ).count()
        successor = self._validated_successor(
            code="P0-SUCCESSOR-V2",
            version="2.0.0",
        )

        publication = publish_project_definition(
            successor,
            actor_identifier="publisher",
            principal=self.publisher(),
            workspace_spec=None,
            locale="en",
        )
        self.assertIsNone(publication.initial_workspace_id)
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(
            ProjectPublication.objects.filter(
                definition_version=successor
            ).count(),
            1,
        )
        self.assertEqual(ProjectWorkspace.objects.count(), 1)
        self.initial.workspace.refresh_from_db()
        self.initial.definition.refresh_from_db()
        successor.refresh_from_db()
        self.assertEqual(self.initial.workspace.pk, old_workspace_id)
        self.assertEqual(self.initial.workspace.definition_version_id, old_definition_id)
        self.assertEqual(self.initial.workspace.definition_manifest_hash, old_hash)
        self.assertEqual(
            tuple(
                UIHelpBinding.objects.filter(workspace=self.initial.workspace)
                .order_by("pk")
                .values_list("pk", flat=True)
            ),
            old_binding_ids,
        )
        self.assertEqual(
            AuditEvent.objects.filter(scope=AuditScope.WORKSPACE).count(),
            old_workspace_audit_count,
        )
        self.assertFalse(self.initial.definition.is_current)
        self.assertTrue(successor.is_current)

        with self.assertRaises(ValidationError):
            publish_project_definition(
                successor,
                actor_identifier="publisher",
                principal=self.publisher(),
                workspace_spec=None,
                locale="en",
            )
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(ProjectWorkspace.objects.count(), 1)

    def test_successor_rejects_workspace_recreation_and_noncurrent_lineage(self):
        successor = self._validated_successor(
            code="P0-SUCCESSOR-WORKSPACE-REJECT",
            version="2.0.0",
        )
        with self.assertRaises(ValidationError):
            publish_project_definition(
                successor,
                actor_identifier="publisher",
                principal=self.publisher(),
                workspace_spec={
                    **self.workspace_spec(),
                    "id": "26000000-0000-4000-8000-000000000001",
                    "code": "P0-SECOND-INITIAL",
                },
                locale="en",
            )
        successor.refresh_from_db()
        self.assertEqual(successor.publication_status, PublicationStatus.VALIDATED)
        self.assertEqual(ProjectPublication.objects.count(), 1)

        good_publication = publish_project_definition(
            successor,
            actor_identifier="publisher",
            principal=self.publisher(),
            workspace_spec=None,
            locale="en",
        )
        self.assertIsNone(good_publication.initial_workspace_id)

        stale_lineage = create_project_definition_draft(
            project=self.project,
            code="P0-STALE-LINEAGE",
            version="3.0.0",
            manifest=self.manifest,
            supersedes=self.initial.definition,
            principal=self.editor(),
        )
        stale_lineage = validate_project_definition(
            stale_lineage,
            actor_identifier="publisher",
            principal=self.publisher(),
        )
        with self.assertRaisesRegex(ValidationError, "exact current published"):
            publish_project_definition(
                stale_lineage,
                actor_identifier="publisher",
                principal=self.publisher(),
                workspace_spec=None,
                locale="en",
            )
        self.assertEqual(ProjectPublication.objects.count(), 2)

    def test_successor_failure_stages_roll_back_transition_receipt_and_audit(self):
        successor = self._validated_successor(
            code="P0-SUCCESSOR-ROLLBACK",
            version="2.0.0",
        )
        initial_audits = AuditEvent.objects.count()
        for stage in (
            "after_publication_transition",
            "after_project_publication",
            "after_definition_publish_audit",
        ):
            with self.subTest(stage=stage):
                with self.assertRaisesRegex(RuntimeError, stage):
                    publish_project_definition(
                        successor,
                        actor_identifier="publisher",
                        principal=self.publisher(),
                        workspace_spec=None,
                        locale="en",
                        inject_failure_at=stage,
                    )
                successor.refresh_from_db()
                self.initial.definition.refresh_from_db()
                self.assertEqual(
                    successor.publication_status,
                    PublicationStatus.VALIDATED,
                )
                self.assertFalse(successor.is_current)
                self.assertTrue(self.initial.definition.is_current)
                self.assertEqual(ProjectPublication.objects.count(), 1)
                self.assertEqual(ProjectWorkspace.objects.count(), 1)
                self.assertEqual(AuditEvent.objects.count(), initial_audits)


class FoundationStudioSuccessorConcurrencyTests(
    FoundationStudioBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self) -> None:
        self.make_contract()

    def test_postgresql_competing_successors_have_one_winner_and_preserve_old_pin(self):
        if connection.vendor != "postgresql":
            self.skipTest("Typed successor race gate is PostgreSQL-only.")
        initial = bootstrap_initial_project_definition(
            definition=self.draft(code="P0-RACE-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        old_pin = (
            initial.workspace.pk,
            initial.workspace.definition_version_id,
            initial.workspace.definition_manifest_hash,
        )
        successor_ids = []
        for index in (1, 2):
            draft = clone_project_definition_draft(
                initial.definition,
                code=f"P0-RACE-SUCCESSOR-{index}",
                version=f"{index + 1}.0.0",
                principal=self.editor(),
            )
            validated = validate_project_definition(
                draft,
                actor_identifier="publisher",
                principal=self.publisher(),
            )
            successor_ids.append(validated.pk)

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        errors: list[Exception] = []
        outcome_lock = threading.Lock()

        def worker(definition_id) -> None:
            close_old_connections()
            try:
                local = ProjectDefinitionVersion.objects.get(pk=definition_id)
                barrier.wait(timeout=10)
                publication = publish_project_definition(
                    local,
                    actor_identifier="publisher",
                    principal=self.publisher(),
                    workspace_spec=None,
                    locale="en",
                )
                with outcome_lock:
                    outcomes.append(str(publication.pk))
            except Exception as exc:
                with outcome_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(target=worker, args=(definition_id,))
            for definition_id in successor_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValidationError)
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
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(is_current=True).count(),
            1,
        )


class FoundationStudioLifecycleCompleteReadTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()
        self.viewer = StudioPrincipal.for_role(
            actor_identifier="lifecycle-viewer",
            role=StudioDefinitionRole.VIEWER,
        )

    def _definition_for_status(
        self,
        status: PublicationStatus,
        *,
        index: int,
    ) -> ProjectDefinitionVersion:
        now = timezone.now()
        lifecycle_fields = {}
        if status in {
            PublicationStatus.VALIDATED,
            PublicationStatus.PUBLISHED,
            PublicationStatus.RETIRED,
        }:
            lifecycle_fields.update(
                validated_at=now,
                validated_by="lifecycle-publisher",
                validation_result={"valid": True},
            )
        if status in {PublicationStatus.PUBLISHED, PublicationStatus.RETIRED}:
            lifecycle_fields.update(
                published_at=now,
                published_by="lifecycle-publisher",
            )
        definition = ProjectDefinitionVersion(
            project=self.project,
            code=f"LIFECYCLE-READ-{status}",
            version=f"1.0.{index}",
            manifest=copy.deepcopy(self.manifest),
            manifest_hash=hash_project_definition_manifest_v1(
                self.manifest,
                project=self.project,
            ),
            schema_version="1.0.0",
            semantic_version="1.0.0",
            construct_version="1.0.0",
            publication_status=status,
            **lifecycle_fields,
        )
        with _canonical_studio_write("definition"):
            definition.save(force_insert=True)
        return definition

    def test_canonical_read_accepts_every_lifecycle_state_with_read_capability(self):
        for index, status in enumerate(
            (
                PublicationStatus.DRAFT,
                PublicationStatus.VALIDATED,
                PublicationStatus.PUBLISHED,
                PublicationStatus.RETIRED,
            ),
            start=1,
        ):
            with self.subTest(status=status):
                definition = self._definition_for_status(status, index=index)
                opened = open_project_definition(
                    definition,
                    principal=self.viewer,
                )
                self.assertEqual(opened.pk, definition.pk)
                self.assertEqual(opened.publication_status, status)
                self.assertEqual(
                    opened.manifest_hash,
                    hash_project_definition_manifest_v1(
                        opened.manifest,
                        project=self.project,
                    ),
                )

    def test_legacy_draft_read_remains_draft_only(self):
        published = self._definition_for_status(
            PublicationStatus.PUBLISHED,
            index=1,
        )
        with self.assertRaises(ValidationError):
            open_project_definition_draft(published, principal=self.viewer)


class FoundationStudioFirstProjectDraftBootstrapTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="first-project-editor",
            password="foundation-studio-test",
        )
        permission = Permission.objects.get(
            content_type__app_label="domain",
            codename="studio_create_definition_draft",
        )
        self.user.user_permissions.add(permission)
        self.user = user_model.objects.get(pk=self.user.pk)
        self.principal = studio_principal_from_user(self.user)

    def _bootstrap_arguments(
        self,
        *,
        project_id: UUID | None = None,
        project_code: str | None = None,
        definition_id: UUID | None = None,
    ) -> dict:
        resolved_project_id = project_id or uuid4()
        resolved_project_code = project_code or f"NEW-PROJECT-{uuid4().hex[:12]}"
        resolved_definition_id = definition_id or uuid4()
        manifest = manifest_vector()
        manifest["project"].update(
            {
                "id": str(resolved_project_id),
                "code": resolved_project_code,
                "version": "1.0.0",
                "name": "First Project",
                "description": "Atomic first-Project bootstrap.",
                "metadata": {
                    "source": "first-project-test",
                    "nested": {"owner": "client"},
                },
            }
        )
        return {
            "project_id": resolved_project_id,
            "project_code": resolved_project_code,
            "project_version": "1.0.0",
            "project_name": "First Project",
            "project_description": "Atomic first-Project bootstrap.",
            "project_metadata": {
                "source": "first-project-test",
                "nested": {"owner": "client"},
            },
            "definition_id": resolved_definition_id,
            "definition_code": "FIRST-PROJECT-DRAFT",
            "definition_version": "1.0.0",
            "manifest": manifest,
            "principal": self.principal,
            "user": self.user,
        }

    def test_bootstrap_creates_exact_scope_draft_and_trusted_human_create_audit(self):
        arguments = self._bootstrap_arguments()
        supplied_metadata = arguments["project_metadata"]
        result = bootstrap_project_definition_draft(**arguments)

        expected_group = project_access_group_name(arguments["project_id"])
        self.assertEqual(result.project.pk, arguments["project_id"])
        self.assertEqual(result.scope_group.name, expected_group)
        self.assertTrue(self.user.groups.filter(name=expected_group).exists())
        self.assertEqual(result.definition.project_id, result.project.pk)
        self.assertEqual(
            result.definition.publication_status,
            PublicationStatus.DRAFT,
        )
        self.assertEqual(result.definition.manifest, arguments["manifest"])
        self.assertEqual(result.project.metadata, supplied_metadata)
        self.assertIsNot(result.project.metadata, supplied_metadata)
        self.assertIsNot(
            result.project.metadata["nested"],
            supplied_metadata["nested"],
        )
        supplied_metadata["nested"]["owner"] = "caller-mutated"
        supplied_metadata["new"] = "caller-only"
        self.assertEqual(
            result.project.metadata,
            {
                "source": "first-project-test",
                "nested": {"owner": "client"},
            },
        )
        result.project.refresh_from_db()
        self.assertEqual(
            result.project.metadata,
            {
                "source": "first-project-test",
                "nested": {"owner": "client"},
            },
        )
        self.assertFalse(ProjectWorkspace.objects.exists())
        self.assertFalse(ProjectPublication.objects.exists())

        event = AuditEvent.objects.get(pk=result.audit_event.pk)
        self.assertEqual(event.scope, AuditScope.DEFINITION)
        self.assertEqual(event.definition_version_id, result.definition.pk)
        self.assertEqual(event.action, AuditAction.CREATE)
        self.assertEqual(event.actor_type, AuditActorType.HUMAN)
        self.assertEqual(event.actor_identifier, f"django-user:{self.user.pk}")
        self.assertEqual(event.entity_type, "PROJECT_DEFINITION_VERSION")
        self.assertEqual(event.entity_id, result.definition.pk)
        self.assertIsNone(event.before)
        self.assertEqual(
            event.after,
            {
                "project_identity": {
                    "id": str(result.project.pk),
                    "code": result.project.code,
                    "version": result.project.version,
                },
                "object_scope_group": {"name": expected_group},
            },
        )

    def test_exact_definition_id_and_metadata_fail_before_any_domain_write(self):
        invalid_cases = (
            ("null-definition-id", "definition_id", None),
            ("malformed-definition-id", "definition_id", "not-a-uuid"),
            ("null-project-metadata", "project_metadata", None),
            ("list-project-metadata", "project_metadata", []),
        )
        for label, field, value in invalid_cases:
            with self.subTest(case=label):
                arguments = self._bootstrap_arguments()
                arguments[field] = value
                with self.assertRaises(ValidationError):
                    bootstrap_project_definition_draft(**arguments)
                self.assertFalse(Project.objects.exists())
                self.assertFalse(ProjectDefinitionVersion.objects.exists())
                self.assertFalse(AuditEvent.objects.exists())
                self.assertFalse(ProjectWorkspace.objects.exists())
                self.assertFalse(ProjectPublication.objects.exists())
                self.assertFalse(
                    Group.objects.filter(name__startswith="studio-project:").exists()
                )
                self.assertFalse(self.user.groups.exists())

        for missing_field in ("definition_id", "project_metadata"):
            with self.subTest(missing=missing_field):
                arguments = self._bootstrap_arguments()
                arguments.pop(missing_field)
                with self.assertRaises(TypeError):
                    bootstrap_project_definition_draft(**arguments)
                self.assertFalse(Project.objects.exists())
                self.assertFalse(ProjectDefinitionVersion.objects.exists())
                self.assertFalse(AuditEvent.objects.exists())
                self.assertFalse(
                    Group.objects.filter(name__startswith="studio-project:").exists()
                )
                self.assertFalse(self.user.groups.exists())

    def test_uuid_code_and_derived_group_collisions_are_typed_conflicts(self):
        id_arguments = self._bootstrap_arguments()
        Project.objects.create(
            id=id_arguments["project_id"],
            code="PREEXISTING-ID-OWNER",
            version="1.0.0",
            name="Existing Project by id",
        )
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            bootstrap_project_definition_draft(**id_arguments)
        self.assertEqual(caught.exception.conflict_code, "PROJECT_ID_CONFLICT")
        self.assertFalse(
            ProjectDefinitionVersion.objects.filter(
                pk=id_arguments["definition_id"]
            ).exists()
        )

        code_arguments = self._bootstrap_arguments()
        Project.objects.create(
            code=code_arguments["project_code"],
            version="1.0.0",
            name="Existing Project by code",
        )
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            bootstrap_project_definition_draft(**code_arguments)
        self.assertEqual(caught.exception.conflict_code, "PROJECT_CODE_CONFLICT")
        self.assertFalse(
            Group.objects.filter(
                name=project_access_group_name(code_arguments["project_id"])
            ).exists()
        )

        group_arguments = self._bootstrap_arguments()
        collision_group = Group.objects.create(
            name=project_access_group_name(group_arguments["project_id"])
        )
        with self.assertRaises(FoundationStudioApplicationConflict) as caught:
            bootstrap_project_definition_draft(**group_arguments)
        self.assertEqual(
            caught.exception.conflict_code,
            "PROJECT_SCOPE_GROUP_CONFLICT",
        )
        self.assertFalse(
            Project.objects.filter(pk=group_arguments["project_id"]).exists()
        )
        self.assertFalse(self.user.groups.filter(pk=collision_group.pk).exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_each_bootstrap_stage_failure_rolls_back_every_created_row(self):
        for stage in (
            "after_project",
            "after_scope_group",
            "after_scope_membership",
            "after_definition",
            "after_create_audit",
        ):
            with self.subTest(stage=stage):
                arguments = self._bootstrap_arguments()
                with self.assertRaisesRegex(RuntimeError, stage):
                    bootstrap_project_definition_draft(
                        **arguments,
                        inject_failure_at=stage,
                    )
                expected_group = project_access_group_name(arguments["project_id"])
                self.assertFalse(
                    Project.objects.filter(pk=arguments["project_id"]).exists()
                )
                self.assertFalse(Group.objects.filter(name=expected_group).exists())
                self.assertFalse(self.user.groups.filter(name=expected_group).exists())
                self.assertFalse(
                    ProjectDefinitionVersion.objects.filter(
                        pk=arguments["definition_id"]
                    ).exists()
                )
                self.assertFalse(
                    AuditEvent.objects.filter(
                        entity_id=arguments["definition_id"]
                    ).exists()
                )

    def test_audit_append_failure_rolls_back_project_group_membership_and_draft(self):
        arguments = self._bootstrap_arguments()
        with patch(
            "domain.policies.record_definition_audit",
            side_effect=RuntimeError("trusted CREATE audit unavailable"),
        ):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                bootstrap_project_definition_draft(**arguments)

        expected_group = project_access_group_name(arguments["project_id"])
        self.assertFalse(Project.objects.filter(pk=arguments["project_id"]).exists())
        self.assertFalse(Group.objects.filter(name=expected_group).exists())
        self.assertFalse(self.user.groups.filter(name=expected_group).exists())
        self.assertFalse(
            ProjectDefinitionVersion.objects.filter(
                pk=arguments["definition_id"]
            ).exists()
        )
        self.assertFalse(AuditEvent.objects.exists())

    def test_bootstrap_rejects_principal_from_a_different_human(self):
        user_model = get_user_model()
        other = user_model.objects.create_user(username="other-first-project-editor")
        permission = Permission.objects.get(
            content_type__app_label="domain",
            codename="studio_create_definition_draft",
        )
        other.user_permissions.add(permission)
        other = user_model.objects.get(pk=other.pk)
        arguments = self._bootstrap_arguments()
        arguments["principal"] = studio_principal_from_user(other)

        with self.assertRaises(StudioAuthorizationDenied):
            bootstrap_project_definition_draft(**arguments)
        self.assertFalse(Project.objects.filter(pk=arguments["project_id"]).exists())


class FoundationStudioTypedSuccessorConflictTests(
    FoundationStudioBootstrapMixin,
    TestCase,
):
    def setUp(self) -> None:
        self.make_contract()
        self.initial = bootstrap_initial_project_definition(
            definition=self.draft(code="APPLICATION-CONFLICT-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )

    def _validated_successor(self, *, code: str, version: str):
        draft = clone_project_definition_draft(
            self.initial.definition,
            code=code,
            version=version,
            principal=self.editor(),
        )
        return validate_project_definition(
            draft,
            actor_identifier="publisher",
            principal=self.publisher(),
        )

    def test_retry_and_competing_current_are_one_typed_application_conflict(self):
        winner = self._validated_successor(
            code="APPLICATION-CONFLICT-WINNER",
            version="2.0.0",
        )
        loser = self._validated_successor(
            code="APPLICATION-CONFLICT-LOSER",
            version="2.1.0",
        )
        publication = publish_successor_project_definition(
            winner,
            principal=self.publisher(),
        )
        self.assertEqual(publication.definition_version_id, winner.pk)

        for candidate in (winner, loser):
            with self.subTest(candidate=candidate.code):
                with self.assertRaises(FoundationStudioApplicationConflict) as caught:
                    publish_successor_project_definition(
                        candidate,
                        principal=self.publisher(),
                    )
                self.assertEqual(
                    caught.exception.conflict_code,
                    "SUCCESSOR_PUBLICATION_CONFLICT",
                )


class FoundationStudioApplicationSuccessorConcurrencyTests(
    FoundationStudioBootstrapMixin,
    TransactionTestCase,
):
    reset_sequences = True

    def setUp(self) -> None:
        self.make_contract()

    def test_postgresql_application_wrapper_has_one_success_and_one_typed_conflict(self):
        if connection.vendor != "postgresql":
            self.skipTest(
                "Application successor wrapper race gate is PostgreSQL-only."
            )
        initial = bootstrap_initial_project_definition(
            definition=self.draft(code="APPLICATION-RACE-INITIAL"),
            principal=self.publisher(),
            actor_identifier="publisher",
            workspace_spec=self.workspace_spec(),
            locale="en",
        )
        old_pin = (
            initial.workspace.pk,
            initial.workspace.definition_version_id,
            initial.workspace.definition_manifest_hash,
        )
        successor_ids = []
        for index in (1, 2):
            draft = clone_project_definition_draft(
                initial.definition,
                code=f"APPLICATION-RACE-SUCCESSOR-{index}",
                version=f"{index + 1}.0.0",
                principal=self.editor(),
            )
            successor = validate_project_definition(
                draft,
                actor_identifier="publisher",
                principal=self.publisher(),
            )
            successor_ids.append(successor.pk)

        barrier = threading.Barrier(2)
        outcomes: list[str] = []
        errors: list[Exception] = []
        outcome_lock = threading.Lock()

        def worker(definition_id: UUID) -> None:
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '20s'")
                local = ProjectDefinitionVersion.objects.get(pk=definition_id)
                barrier.wait(timeout=10)
                publication = publish_successor_project_definition(
                    local,
                    principal=self.publisher(),
                )
                with outcome_lock:
                    outcomes.append(str(publication.pk))
            except Exception as exc:
                with outcome_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(
                target=worker,
                args=(definition_id,),
                daemon=True,
            )
            for definition_id in successor_ids
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(
            any(thread.is_alive() for thread in threads),
            "Successor publication race exceeded its bounded join.",
        )
        self.assertFalse(
            any(isinstance(error, OperationalError) for error in errors),
            f"PostgreSQL successor race raised OperationalError: {errors!r}",
        )
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FoundationStudioApplicationConflict)
        self.assertEqual(
            errors[0].conflict_code,
            "SUCCESSOR_PUBLICATION_CONFLICT",
        )
        self.assertEqual(ProjectPublication.objects.count(), 2)
        self.assertEqual(
            ProjectPublication.objects.filter(
                initial_workspace__isnull=True,
            ).count(),
            1,
        )
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
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(
                pk__in=successor_ids,
                publication_status=PublicationStatus.PUBLISHED,
                is_current=True,
            ).count(),
            1,
        )
        self.assertEqual(
            ProjectDefinitionVersion.objects.filter(
                pk__in=successor_ids,
                publication_status=PublicationStatus.VALIDATED,
                is_current=False,
            ).count(),
            1,
        )


class FoundationStudioFirstProjectApplicationConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self) -> None:
        permission = Permission.objects.get(
            content_type__app_label="domain",
            codename="studio_create_definition_draft",
        )
        user_model = get_user_model()
        self.users = []
        self.principals = []
        for index in (1, 2):
            user = user_model.objects.create_user(
                username=f"first-project-race-editor-{index}",
                password="foundation-studio-test",
            )
            user.user_permissions.add(permission)
            user = user_model.objects.get(pk=user.pk)
            self.users.append(user)
            self.principals.append(studio_principal_from_user(user))

    def test_postgresql_application_bootstrap_has_one_complete_winner_and_no_orphans(self):
        if connection.vendor != "postgresql":
            self.skipTest(
                "First-Project application bootstrap race gate is PostgreSQL-only."
            )
        project_id = uuid4()
        definition_id = uuid4()
        project_code = "FIRST-PROJECT-APPLICATION-RACE"
        scope_group_name = project_access_group_name(project_id)
        manifest = manifest_vector()
        manifest["project"].update(
            {
                "id": str(project_id),
                "code": project_code,
                "version": "1.0.0",
                "name": "First Project Race",
                "description": "PostgreSQL atomic application race.",
                "metadata": {"source": "first-project-race"},
            }
        )
        barrier = threading.Barrier(2)
        outcomes: list[tuple[object, object, object, object]] = []
        errors: list[Exception] = []
        outcome_lock = threading.Lock()

        def worker(user: object, principal: StudioPrincipal) -> None:
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '20s'")
                barrier.wait(timeout=10)
                result = bootstrap_project_definition_draft(
                    project_id=project_id,
                    project_code=project_code,
                    project_version="1.0.0",
                    project_name="First Project Race",
                    project_description="PostgreSQL atomic application race.",
                    project_metadata={"source": "first-project-race"},
                    definition_id=definition_id,
                    definition_code="FIRST-PROJECT-APPLICATION-RACE-DRAFT",
                    definition_version="1.0.0",
                    manifest=copy.deepcopy(manifest),
                    principal=principal,
                    user=user,
                )
                with outcome_lock:
                    outcomes.append(
                        (
                            user.pk,
                            result.project.pk,
                            result.definition.pk,
                            result.audit_event.pk,
                        )
                    )
            except Exception as exc:
                with outcome_lock:
                    errors.append(exc)
            finally:
                close_old_connections()

        threads = [
            threading.Thread(
                target=worker,
                args=(user, principal),
                daemon=True,
            )
            for user, principal in zip(
                self.users,
                self.principals,
                strict=True,
            )
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(
            any(thread.is_alive() for thread in threads),
            "First-Project application race exceeded its bounded join.",
        )
        self.assertFalse(
            any(isinstance(error, OperationalError) for error in errors),
            f"PostgreSQL first-Project race raised OperationalError: {errors!r}",
        )
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FoundationStudioApplicationConflict)
        self.assertEqual(errors[0].conflict_code, "PROJECT_ID_CONFLICT")

        winner_user_id, winner_project_id, winner_definition_id, winner_audit_id = (
            outcomes[0]
        )
        self.assertEqual(winner_project_id, project_id)
        self.assertEqual(winner_definition_id, definition_id)
        self.assertEqual(Project.objects.count(), 1)
        self.assertEqual(ProjectDefinitionVersion.objects.count(), 1)
        self.assertEqual(
            ProjectDefinitionVersion.objects.get().publication_status,
            PublicationStatus.DRAFT,
        )
        self.assertEqual(
            Group.objects.filter(name__startswith="studio-project:").count(),
            1,
        )
        scope_group = Group.objects.get(name=scope_group_name)
        user_model = get_user_model()
        self.assertEqual(
            user_model.objects.filter(
                pk__in=[user.pk for user in self.users],
                groups=scope_group,
            ).count(),
            1,
        )
        self.assertTrue(
            user_model.objects.filter(
                pk=winner_user_id,
                groups=scope_group,
            ).exists()
        )
        self.assertEqual(AuditEvent.objects.count(), 1)
        audit = AuditEvent.objects.get(pk=winner_audit_id)
        self.assertEqual(audit.action, AuditAction.CREATE)
        self.assertEqual(audit.scope, AuditScope.DEFINITION)
        self.assertEqual(audit.definition_version_id, definition_id)
        self.assertEqual(audit.project_id, project_id)
        self.assertEqual(audit.actor_type, AuditActorType.HUMAN)
        self.assertEqual(
            audit.actor_identifier,
            f"django-user:{winner_user_id}",
        )
        self.assertEqual(
            audit.after,
            {
                "project_identity": {
                    "id": str(project_id),
                    "code": project_code,
                    "version": "1.0.0",
                },
                "object_scope_group": {"name": scope_group_name},
            },
        )
        self.assertFalse(ProjectWorkspace.objects.exists())
        self.assertFalse(ProjectPublication.objects.exists())
