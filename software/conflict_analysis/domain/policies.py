"""Explicit authorization policy for project-structure mutations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .enums import (
    AuditAction,
    AuditActorType,
    AuditScope,
    ExperimentStatus,
    HelpApplicationScope,
    PublicationStatus,
)
from .models import (
    AuditEvent,
    Experiment,
    HelpTopic,
    Project,
    ProjectDefinitionVersion,
    ProjectLock,
    ProjectPublication,
    ProjectWorkspace,
    UIHelpBinding,
    _canonical_studio_write,
)


class StructureActor(StrEnum):
    """Policy roles intentionally decoupled from Django authentication models."""

    ORDINARY = "ORDINARY"
    STUDIO = "STUDIO"
    SERVICE = "SERVICE"


class StructureMutationDenied(PermissionDenied):
    """Raised when an actor attempts to mutate a locked project structure."""


class StudioRole(StrEnum):
    """Non-spoofable server-side Studio authorization classifications."""

    STUDIO_EDITOR = "STUDIO_EDITOR"
    STUDIO_PUBLISHER = "STUDIO_PUBLISHER"
    VIEWER = "VIEWER"
    PLAYER = "PLAYER"
    SERVICE = "SERVICE"


class StudioCapability(StrEnum):
    DEFINITION_READ = "DEFINITION_READ"
    DRAFT_CREATE = "DRAFT_CREATE"
    DRAFT_CLONE = "DRAFT_CLONE"
    DRAFT_SAVE = "DRAFT_SAVE"
    DEFINITION_VALIDATE = "DEFINITION_VALIDATE"
    DEFINITION_PUBLISH = "DEFINITION_PUBLISH"
    FOUNDATION_IMPORT = "FOUNDATION_IMPORT"
    STRUCTURE_MUTATE = "STRUCTURE_MUTATE"


_ROLE_CAPABILITIES: Mapping[StudioRole, frozenset[StudioCapability]] = MappingProxyType(
    {
        StudioRole.STUDIO_EDITOR: frozenset(
            {
                StudioCapability.DEFINITION_READ,
                StudioCapability.DRAFT_CREATE,
                StudioCapability.DRAFT_CLONE,
                StudioCapability.DRAFT_SAVE,
            }
        ),
        StudioRole.STUDIO_PUBLISHER: frozenset(
            {
                StudioCapability.DEFINITION_READ,
                StudioCapability.DEFINITION_VALIDATE,
                StudioCapability.DEFINITION_PUBLISH,
            }
        ),
        StudioRole.VIEWER: frozenset({StudioCapability.DEFINITION_READ}),
        StudioRole.PLAYER: frozenset(),
        # SERVICE is deliberately empty unless a caller supplies a bounded
        # purpose and an explicit subset through ``StudioPrincipal.service``.
        StudioRole.SERVICE: frozenset(),
    }
)


@dataclass(frozen=True, slots=True)
class StudioPrincipal:
    """Immutable authorization fact created by a trusted server boundary."""

    actor_identifier: str
    role: StudioRole
    capabilities: frozenset[StudioCapability]
    service_purpose: str = ""

    def __post_init__(self) -> None:
        """Reject incoherent facts even when callers bypass trusted factories."""

        try:
            role = StudioRole(self.role)
            capabilities = frozenset(
                StudioCapability(capability) for capability in self.capabilities
            )
        except (TypeError, ValueError):
            raise ValueError("StudioPrincipal contains an unknown role or capability.")
        actor_identifier = self.actor_identifier.strip()
        service_purpose = self.service_purpose.strip()
        if not actor_identifier:
            raise ValueError("StudioPrincipal requires an actor identifier.")
        if role is StudioRole.SERVICE:
            if not service_purpose or not capabilities:
                raise ValueError(
                    "SERVICE requires an actor, a bounded purpose, and explicit capabilities."
                )
        else:
            unexpected = capabilities - _ROLE_CAPABILITIES[role]
            if unexpected:
                raise ValueError(
                    f"{role.value} contains capabilities outside its authorized role matrix."
                )
            if service_purpose:
                raise ValueError("Only SERVICE may carry a bounded service purpose.")
        object.__setattr__(self, "actor_identifier", actor_identifier)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "service_purpose", service_purpose)

    @classmethod
    def for_role(
        cls,
        *,
        actor_identifier: str,
        role: StudioRole | str,
    ) -> "StudioPrincipal":
        resolved = StudioRole(role)
        if resolved is StudioRole.SERVICE:
            raise ValueError("SERVICE requires an explicit bounded purpose/capability set.")
        return cls(
            actor_identifier=actor_identifier.strip(),
            role=resolved,
            capabilities=_ROLE_CAPABILITIES[resolved],
        )

    @classmethod
    def service(
        cls,
        *,
        actor_identifier: str,
        purpose: str,
        capabilities: frozenset[StudioCapability | str],
    ) -> "StudioPrincipal":
        if not actor_identifier.strip() or not purpose.strip() or not capabilities:
            raise ValueError(
                "SERVICE requires an actor, a bounded purpose, and explicit capabilities."
            )
        try:
            resolved_capabilities = frozenset(
                StudioCapability(capability) for capability in capabilities
            )
        except ValueError:
            raise ValueError("SERVICE contains an unknown Studio capability.")
        return cls(
            actor_identifier=actor_identifier.strip(),
            role=StudioRole.SERVICE,
            capabilities=resolved_capabilities,
            service_purpose=purpose.strip(),
        )


_DJANGO_PERMISSION_CAPABILITIES: Mapping[str, StudioCapability] = MappingProxyType(
    {
        "domain.studio_read_definition": StudioCapability.DEFINITION_READ,
        "domain.studio_create_definition_draft": StudioCapability.DRAFT_CREATE,
        "domain.studio_clone_definition_draft": StudioCapability.DRAFT_CLONE,
        "domain.studio_save_definition_draft": StudioCapability.DRAFT_SAVE,
        "domain.studio_validate_definition": StudioCapability.DEFINITION_VALIDATE,
        "domain.studio_publish_definition": StudioCapability.DEFINITION_PUBLISH,
    }
)


def studio_principal_from_user(user: object) -> StudioPrincipal:
    """Derive capabilities only from authenticated Django permissions."""

    if not bool(getattr(user, "is_authenticated", False)):
        raise PermissionDenied("Authenticated Studio access is required.")
    has_perm = getattr(user, "has_perm", None)
    if not callable(has_perm):
        raise PermissionDenied("The authenticated principal has no permission backend.")
    capabilities = frozenset(
        capability
        for permission, capability in _DJANGO_PERMISSION_CAPABILITIES.items()
        if has_perm(permission)
    )
    publisher_capabilities = _ROLE_CAPABILITIES[StudioRole.STUDIO_PUBLISHER]
    editor_capabilities = _ROLE_CAPABILITIES[StudioRole.STUDIO_EDITOR]
    if capabilities <= publisher_capabilities and capabilities & {
        StudioCapability.DEFINITION_VALIDATE,
        StudioCapability.DEFINITION_PUBLISH,
    }:
        role = StudioRole.STUDIO_PUBLISHER
    elif capabilities <= editor_capabilities and capabilities & (
        editor_capabilities - {StudioCapability.DEFINITION_READ}
    ):
        role = StudioRole.STUDIO_EDITOR
    elif StudioCapability.DEFINITION_READ in capabilities:
        if capabilities == _ROLE_CAPABILITIES[StudioRole.VIEWER]:
            role = StudioRole.VIEWER
        else:
            raise PermissionDenied(
                "Django Studio permissions span incompatible non-service roles."
            )
    elif capabilities:
        raise PermissionDenied(
            "Django Studio permissions span incompatible non-service roles."
        )
    else:
        role = StudioRole.PLAYER
    return StudioPrincipal(
        actor_identifier=f"django-user:{getattr(user, 'pk', '')}",
        role=role,
        capabilities=capabilities,
    )


def require_studio_capability(
    principal: object,
    capability: StudioCapability | str,
) -> None:
    """Enforce one capability at every canonical service mutation boundary."""

    required = StudioCapability(capability)
    if not isinstance(principal, StudioPrincipal):
        raise PermissionDenied("A trusted StudioPrincipal is required.")
    if not principal.actor_identifier or required not in principal.capabilities:
        raise PermissionDenied(
            f"{principal.role.value} is not allowed to perform {required.value}."
        )
    if principal.role is StudioRole.SERVICE and not principal.service_purpose:
        raise PermissionDenied("SERVICE authorization requires a bounded purpose.")


def can_modify_project_structure(
    project: Project,
    *,
    actor: StructureActor | str = StructureActor.ORDINARY,
    service_principal: StudioPrincipal | None = None,
) -> bool:
    """Return whether ``actor`` may add, remove, or rename structural entities.

    A missing lock means that the project is editable.  The service role is
    reserved for controlled operations such as validated imports and seed
    installation; callers must opt into it explicitly.
    """

    actor = StructureActor(actor)
    if actor is StructureActor.SERVICE:
        return bool(
            isinstance(service_principal, StudioPrincipal)
            and service_principal.role is StudioRole.SERVICE
            and service_principal.actor_identifier
            and service_principal.service_purpose
            and StudioCapability.STRUCTURE_MUTATE in service_principal.capabilities
        )

    lock = ProjectLock.objects.filter(project=project).first()
    if lock is None or not lock.is_structure_locked:
        return True
    if actor is StructureActor.STUDIO:
        return lock.studio_can_edit_structure
    return lock.ordinary_user_can_edit_structure


def require_project_structure_mutation(
    project: Project,
    *,
    actor: StructureActor | str = StructureActor.ORDINARY,
    service_principal: StudioPrincipal | None = None,
) -> None:
    """Raise a domain-specific permission error unless mutation is authorized."""

    if can_modify_project_structure(
        project,
        actor=actor,
        service_principal=service_principal,
    ):
        return
    raise StructureMutationDenied(
        f"Project {project.code!r} is locked for {StructureActor(actor).value} actors."
    )


# Friendly alias for callers that phrase authorization as an assertion.
assert_can_modify_project_structure = require_project_structure_mutation


class WorkspaceBoundaryViolation(ValidationError):
    """Raised before a transaction can create a cross-workspace link."""


def require_same_workspace(
    workspace: ProjectWorkspace,
    *objects: object,
) -> None:
    """Fail closed when any supplied canonical object is outside ``workspace``."""

    for obj in objects:
        object_workspace_id = getattr(obj, "workspace_id", None)
        if object_workspace_id != workspace.pk:
            raise WorkspaceBoundaryViolation(
                f"{type(obj).__name__} belongs to a different workspace."
            )


def _audit_code(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def record_foundation_audit(
    *,
    workspace: ProjectWorkspace,
    action: AuditAction | str,
    actor_identifier: str,
    entity_type: str,
    entity_id: object,
    before: dict | None = None,
    after: dict | None = None,
    experiment: Experiment | None = None,
) -> AuditEvent:
    """Append one attributed event for create/import/publish/freeze paths."""

    if not actor_identifier.strip():
        raise ValidationError({"actor_identifier": "Audit actor is required."})
    if experiment is not None:
        require_same_workspace(workspace, experiment)
    event = AuditEvent(
        project=workspace.project,
        workspace=workspace,
        assessment_set=experiment.assessment_set if experiment else None,
        code=_audit_code("AUD"),
        action=action,
        actor_type=AuditActorType.HUMAN,
        actor_identifier=actor_identifier,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    event.full_clean()
    event.save(force_insert=True)
    return event


def record_definition_audit(
    *,
    definition: ProjectDefinitionVersion,
    action: AuditAction | str,
    actor_identifier: str,
    entity_type: str,
    entity_id: object,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditEvent:
    """Append one project/definition-scoped event without borrowing a workspace."""

    if not actor_identifier.strip():
        raise ValidationError({"actor_identifier": "Audit actor is required."})
    event = AuditEvent(
        project=definition.project,
        workspace=None,
        definition_version=definition,
        scope=AuditScope.DEFINITION,
        assessment_set=None,
        parameter_value=None,
        code=_audit_code("AUD-DEF"),
        action=action,
        actor_type=AuditActorType.HUMAN,
        actor_identifier=actor_identifier.strip(),
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
    )
    event.full_clean()
    event.save(force_insert=True)
    return event


@dataclass(frozen=True, slots=True)
class ProjectDefinitionBootstrapResult:
    definition: ProjectDefinitionVersion
    workspace: ProjectWorkspace
    publication: ProjectPublication
    help_bindings: tuple[UIHelpBinding, ...]


def _inject_bootstrap_failure(
    requested_stage: str | None,
    stage: str,
) -> None:
    if requested_stage == stage:
        raise RuntimeError(f"Injected Foundation bootstrap failure at {stage}.")


def _typed_help_topic(reference: Mapping[str, Any]) -> HelpTopic | None:
    """Resolve the exact published global Studio binding used before a workspace."""

    from .services.help_topics import HelpTopicResolutionError, resolve_help_topic

    try:
        return resolve_help_topic(
            workspace=None,
            application_scope=HelpApplicationScope.STUDIO,
            ui_key=str(reference.get("ui_key", "")),
            locale=str(reference.get("locale", "")),
            version=str(reference.get("topic_version", "")),
        )
    except HelpTopicResolutionError:
        return None


@transaction.atomic
def validate_project_definition(
    definition: ProjectDefinitionVersion,
    *,
    audit_workspace: ProjectWorkspace | None = None,
    actor_identifier: str,
    validation_result: dict | None = None,
    principal: StudioPrincipal | None = None,
    inject_failure_at: str | None = None,
) -> ProjectDefinitionVersion:
    """Record one explicit DRAFT -> VALIDATED transition.

    Exact typed V1 manifests always use computed canonical diagnostics and a
    definition-scoped audit. Historical manifests retain the pre-2.1 API and
    checksum behavior so their bytes and receipts are never reinterpreted.
    """

    from .services.project_definitions import (
        identify_typed_project_definition_manifest,
        validate_project_definition_manifest_v1,
    )

    current = ProjectDefinitionVersion.objects.select_for_update().select_related(
        "project"
    ).get(pk=definition.pk)
    is_typed = identify_typed_project_definition_manifest(current.manifest)

    if is_typed:
        require_studio_capability(principal, StudioCapability.DEFINITION_VALIDATE)
        assert principal is not None
        if audit_workspace is not None:
            raise WorkspaceBoundaryViolation(
                "Typed definition validation is definition-scoped and cannot borrow a workspace."
            )
        if validation_result is not None:
            raise ValidationError(
                {
                    "validation_result": (
                        "Typed validation is computed by the canonical validator; "
                        "caller-supplied valid:true is forbidden."
                    )
                }
            )
        if actor_identifier.strip() != principal.actor_identifier:
            raise ValidationError(
                {"actor_identifier": "Validation actor must equal the trusted principal."}
            )
        if current.publication_status != PublicationStatus.DRAFT:
            raise ValidationError(
                {"publication_status": "Only a DRAFT definition can be validated."}
            )
        report = validate_project_definition_manifest_v1(
            current.manifest,
            project=current.project,
            help_topic_resolver=_typed_help_topic,
        )
        if not report.valid:
            raise ValidationError(
                {
                    "validation_result": json.dumps(
                        report.as_dict(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                }
            )
        before = {"publication_status": current.publication_status}
        current.manifest_hash = report.manifest_sha256
        current.publication_status = PublicationStatus.VALIDATED
        current.validated_at = timezone.now()
        current.validated_by = principal.actor_identifier
        current.validation_result = report.as_dict()
        current.full_clean()
        with _canonical_studio_write("definition"):
            current.save(
                update_fields=(
                    "publication_status",
                    "validated_at",
                    "validated_by",
                    "validation_result",
                    "manifest_hash",
                    "updated_at",
                )
            )
        _inject_bootstrap_failure(inject_failure_at, "after_validation_transition")
        record_definition_audit(
            definition=current,
            action=AuditAction.VALIDATE,
            actor_identifier=principal.actor_identifier,
            entity_type="PROJECT_DEFINITION_VERSION",
            entity_id=current.pk,
            before=before,
            after={
                "publication_status": current.publication_status,
                "manifest_hash": current.manifest_hash,
                "validation_result": report.as_dict(),
            },
        )
        _inject_bootstrap_failure(inject_failure_at, "after_validation_audit")
        return current

    if audit_workspace is None:
        raise ValidationError(
            {"audit_workspace": "Historical definition validation requires its workspace audit."}
        )
    persisted_audit_workspace = ProjectWorkspace.objects.select_related("project").get(
        pk=audit_workspace.pk
    )
    if current.project_id != persisted_audit_workspace.project_id:
        raise WorkspaceBoundaryViolation(
            "Definition validation cannot be audited from another project."
        )
    if current.publication_status != PublicationStatus.DRAFT:
        raise ValidationError(
            {"publication_status": "Only a DRAFT definition can be validated."}
        )
    if not actor_identifier.strip():
        raise ValidationError({"actor_identifier": "Validation actor is required."})
    if not isinstance(validation_result, dict) or validation_result.get("valid") is not True:
        raise ValidationError(
            {"validation_result": "A successful explicit validation result is required."}
        )
    before = {"publication_status": current.publication_status}
    current.manifest_hash = hashlib.sha256(
        json.dumps(
            current.manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    current.publication_status = PublicationStatus.VALIDATED
    current.validated_at = timezone.now()
    current.validated_by = actor_identifier.strip()
    current.validation_result = validation_result
    current.full_clean()
    current.save(
        update_fields=(
            "publication_status",
            "validated_at",
            "validated_by",
            "validation_result",
            "manifest_hash",
            "updated_at",
        )
    )
    record_foundation_audit(
        workspace=persisted_audit_workspace,
        action=AuditAction.VALIDATE,
        actor_identifier=actor_identifier.strip(),
        entity_type="PROJECT_DEFINITION_VERSION",
        entity_id=current.pk,
        before=before,
        after={
            "publication_status": current.publication_status,
            "manifest_hash": current.manifest_hash,
            "validation_result": validation_result,
        },
    )
    return current


@transaction.atomic
def publish_project_definition(
    definition: ProjectDefinitionVersion,
    *,
    audit_workspace: ProjectWorkspace | None = None,
    actor_identifier: str,
    locale: str = "en",
    principal: StudioPrincipal | None = None,
    workspace_spec: Mapping[str, Any] | None = None,
    inject_failure_at: str | None = None,
) -> ProjectPublication:
    """Publish through the sole Foundation authority.

    Typed V1 publication owns every PUBLISHED transition.  The first
    transition additionally creates the exact initial workspace and its help
    bindings; a successor creates only its ordinary publication receipt and
    never mutates an existing workspace pin.  Historical manifests retain the
    earlier workspace-audited publication path.
    """

    from .services.project_definitions import identify_typed_project_definition_manifest

    current = ProjectDefinitionVersion.objects.select_for_update().select_related(
        "project"
    ).get(pk=definition.pk)
    is_typed = identify_typed_project_definition_manifest(current.manifest)

    if is_typed:
        require_studio_capability(principal, StudioCapability.DEFINITION_PUBLISH)
        assert principal is not None
        if audit_workspace is not None:
            raise WorkspaceBoundaryViolation(
                "Typed publication is definition-scoped and cannot borrow a workspace."
            )
        if actor_identifier.strip() != principal.actor_identifier:
            raise ValidationError(
                {"actor_identifier": "Publication actor must equal the trusted principal."}
            )
        Project.objects.select_for_update().get(pk=current.project_id)
        if current.publication_status != PublicationStatus.VALIDATED:
            raise ValidationError(
                {"publication_status": "Publishing requires an explicit VALIDATED transition."}
            )
        if current.validation_result.get("valid") is not True:
            raise ValidationError(
                {"validation_result": "Publishing requires canonical successful validation."}
            )

        prior_publications = ProjectPublication.objects.select_for_update().filter(
            project_id=current.project_id
        )
        is_initial_publication = not prior_publications.exists()
        previous_current = (
            ProjectDefinitionVersion.objects.select_for_update()
            .filter(project_id=current.project_id, is_current=True)
            .exclude(pk=current.pk)
            .first()
        )
        if is_initial_publication:
            if not isinstance(workspace_spec, Mapping):
                raise ValidationError(
                    {
                        "workspace_spec": (
                            "Typed initial publication requires an exact initial workspace."
                        )
                    }
                )
            if ProjectWorkspace.objects.filter(project=current.project).exists():
                raise ValidationError(
                    {
                        "workspace_spec": (
                            "Initial publication requires a project with no workspace."
                        )
                    }
                )
            if previous_current is not None:
                raise ValidationError(
                    {
                        "publication": (
                            "Initial publication cannot replace an unreceipted current definition."
                        )
                    }
                )
        else:
            if workspace_spec is not None:
                raise ValidationError(
                    {
                        "workspace_spec": (
                            "A successor publication cannot create a second initial workspace."
                        )
                    }
                )
            if prior_publications.filter(initial_workspace_id__isnull=False).count() != 1:
                raise ValidationError(
                    {
                        "publication": (
                            "A typed successor requires exactly one initial publication receipt."
                        )
                    }
                )
            if (
                previous_current is None
                or previous_current.publication_status != PublicationStatus.PUBLISHED
                or current.supersedes_id != previous_current.pk
            ):
                raise ValidationError(
                    {
                        "supersedes": (
                            "A typed successor must supersede the exact current published definition."
                        )
                    }
                )

        before = {
            "publication_status": current.publication_status,
            "is_current": current.is_current,
        }
        with _canonical_studio_write("definition"):
            ProjectDefinitionVersion.objects.filter(
                project_id=current.project_id,
                is_current=True,
            ).exclude(pk=current.pk).update(is_current=False)
            current.publication_status = PublicationStatus.PUBLISHED
            current.published_at = timezone.now()
            current.published_by = principal.actor_identifier
            current.is_current = True
            current.full_clean()
            current.save()
        _inject_bootstrap_failure(inject_failure_at, "after_publication_transition")

        workspace: ProjectWorkspace | None = None
        created_bindings: list[UIHelpBinding] = []
        if is_initial_publication:
            assert isinstance(workspace_spec, Mapping)
            workspace_kwargs: dict[str, Any] = {
                "project": current.project,
                "definition_version": current,
                "definition_manifest_hash": current.manifest_hash,
                "code": str(workspace_spec.get("code", "")),
                "version": str(workspace_spec.get("version", "")),
                "name": str(workspace_spec.get("name", "")),
                "is_default": bool(workspace_spec.get("is_default", True)),
                "metadata": dict(workspace_spec.get("metadata", {})),
            }
            if workspace_spec.get("id") is not None:
                workspace_kwargs["id"] = UUID(str(workspace_spec["id"]))
            workspace = ProjectWorkspace(**workspace_kwargs)
            workspace.full_clean()
            workspace.save(force_insert=True)
            _inject_bootstrap_failure(inject_failure_at, "after_initial_workspace")

            for reference in current.manifest.get("help_bindings", []):
                topic = _typed_help_topic(reference)
                if (
                    topic is None
                    or topic.stable_key != reference["topic_stable_key"]
                    or topic.content_sha256 != reference["topic_sha256"]
                ):
                    raise ValidationError(
                        {
                            "help_bindings": (
                                "An exact published, sanitized pre-workspace HelpTopic "
                                "binding disappeared after validation."
                            )
                        }
                    )
                binding = UIHelpBinding(
                    id=UUID(reference["id"]),
                    workspace=workspace,
                    application_scope=HelpApplicationScope.STUDIO,
                    code=reference["code"],
                    version=reference["version"],
                    ui_key=reference["ui_key"],
                    locale=reference["locale"],
                    help_topic=topic,
                )
                binding.full_clean()
                binding.save(force_insert=True)
                created_bindings.append(binding)
            _inject_bootstrap_failure(
                inject_failure_at, "after_workspace_help_bindings"
            )

        publication = ProjectPublication(
            project=current.project,
            definition_version=current,
            initial_workspace=workspace,
            code=_audit_code("PUB"),
            locale=locale,
            actor_identifier=principal.actor_identifier,
            validation_result=current.validation_result,
        )
        publication.full_clean()
        with _canonical_studio_write("publication"):
            publication.save(force_insert=True)
        _inject_bootstrap_failure(inject_failure_at, "after_project_publication")

        record_definition_audit(
            definition=current,
            action=AuditAction.PUBLISH,
            actor_identifier=principal.actor_identifier,
            entity_type="PROJECT_DEFINITION_VERSION",
            entity_id=current.pk,
            before=before,
            after={
                "publication_status": current.publication_status,
                "is_current": current.is_current,
                "manifest_hash": current.manifest_hash,
                "initial_workspace_id": str(workspace.pk) if workspace else None,
            },
        )
        _inject_bootstrap_failure(inject_failure_at, "after_definition_publish_audit")
        if workspace is not None:
            record_foundation_audit(
                workspace=workspace,
                action=AuditAction.BOOTSTRAP,
                actor_identifier=principal.actor_identifier,
                entity_type="PROJECT_WORKSPACE",
                entity_id=workspace.pk,
                after={
                    "definition_id": str(current.pk),
                    "manifest_hash": current.manifest_hash,
                    "publication_id": str(publication.pk),
                    "help_binding_ids": [str(item.pk) for item in created_bindings],
                },
            )
            _inject_bootstrap_failure(
                inject_failure_at, "after_workspace_bootstrap_audit"
            )
        return publication

    if audit_workspace is None:
        raise ValidationError(
            {"audit_workspace": "Historical publication requires its workspace audit."}
        )
    persisted_audit_workspace = ProjectWorkspace.objects.select_related("project").get(
        pk=audit_workspace.pk
    )
    if current.project_id != persisted_audit_workspace.project_id:
        raise WorkspaceBoundaryViolation(
            "Definition publication cannot be audited from another project."
        )
    if current.publication_status != PublicationStatus.VALIDATED:
        raise ValidationError(
            {"publication_status": "Publishing requires an explicit VALIDATED transition."}
        )
    if current.validation_result.get("valid") is not True:
        raise ValidationError(
            {"validation_result": "Publishing requires a successful validation result."}
        )
    if not actor_identifier.strip():
        raise ValidationError({"actor_identifier": "Publication actor is required."})
    before = {
        "publication_status": current.publication_status,
        "is_current": current.is_current,
    }
    # This historical path is still the canonical publication authority.  It
    # may legitimately demote an existing typed current pointer, but it never
    # receives authority to rewrite the typed snapshot itself.
    with _canonical_studio_write("definition"):
        ProjectDefinitionVersion.objects.filter(
            project_id=current.project_id,
            is_current=True,
        ).exclude(pk=current.pk).update(is_current=False)
    current.publication_status = PublicationStatus.PUBLISHED
    current.published_at = current.published_at or timezone.now()
    current.published_by = actor_identifier.strip()
    current.is_current = True
    current.full_clean()
    current.save()
    publication = ProjectPublication(
        project=current.project,
        definition_version=current,
        code=_audit_code("PUB"),
        locale=locale,
        actor_identifier=actor_identifier.strip(),
        validation_result=current.validation_result,
    )
    publication.full_clean()
    publication.save(force_insert=True)
    record_foundation_audit(
        workspace=persisted_audit_workspace,
        action=AuditAction.PUBLISH,
        actor_identifier=actor_identifier,
        entity_type="PROJECT_DEFINITION_VERSION",
        entity_id=current.pk,
        before=before,
        after={
            "publication_status": current.publication_status,
            "is_current": current.is_current,
            "manifest_hash": current.manifest_hash,
        },
    )
    return publication


@transaction.atomic
def bootstrap_initial_project_definition(
    *,
    definition: ProjectDefinitionVersion,
    principal: StudioPrincipal,
    actor_identifier: str,
    workspace_spec: Mapping[str, Any],
    locale: str = "ru",
    inject_failure_at: str | None = None,
) -> ProjectDefinitionBootstrapResult:
    """Atomically validate and first-publish one typed definition exactly once."""

    require_studio_capability(principal, StudioCapability.DEFINITION_VALIDATE)
    require_studio_capability(principal, StudioCapability.DEFINITION_PUBLISH)
    locked = ProjectDefinitionVersion.objects.select_for_update().select_related(
        "project"
    ).get(pk=definition.pk)
    Project.objects.select_for_update().get(pk=locked.project_id)
    if ProjectWorkspace.objects.filter(project=locked.project).exists():
        raise ValidationError(
            {"workspace_spec": "Bootstrap requires a project with no workspace."}
        )
    if ProjectPublication.objects.filter(project=locked.project).exists():
        raise ValidationError(
            {"publication": "Bootstrap has already been completed for this project."}
        )
    _inject_bootstrap_failure(inject_failure_at, "after_bootstrap_lock")
    validated = validate_project_definition(
        locked,
        audit_workspace=None,
        actor_identifier=actor_identifier,
        validation_result=None,
        principal=principal,
        inject_failure_at=inject_failure_at,
    )
    publication = publish_project_definition(
        validated,
        audit_workspace=None,
        actor_identifier=actor_identifier,
        locale=locale,
        principal=principal,
        workspace_spec=workspace_spec,
        inject_failure_at=inject_failure_at,
    )
    workspace = publication.initial_workspace
    if workspace is None:  # defensive: model contract requires it on this path
        raise ValidationError(
            {"initial_workspace": "Typed bootstrap did not create its exact workspace pin."}
        )
    return ProjectDefinitionBootstrapResult(
        definition=publication.definition_version,
        workspace=workspace,
        publication=publication,
        help_bindings=tuple(
            UIHelpBinding.objects.filter(workspace=workspace).order_by("code", "id")
        ),
    )


@transaction.atomic
def freeze_experiment(
    experiment: Experiment,
    *,
    actor_identifier: str,
) -> Experiment:
    """Freeze an experiment without mutating or aggregating its values."""

    before = {"status": experiment.status, "frozen_at": None}
    experiment.status = ExperimentStatus.FROZEN
    experiment.frozen_at = timezone.now()
    experiment.full_clean()
    experiment.save(update_fields=("status", "frozen_at", "updated_at"))
    record_foundation_audit(
        workspace=experiment.workspace,
        action=AuditAction.FREEZE,
        actor_identifier=actor_identifier,
        entity_type="EXPERIMENT",
        entity_id=experiment.pk,
        before=before,
        after={
            "status": experiment.status,
            "frozen_at": experiment.frozen_at.isoformat(),
        },
        experiment=experiment,
    )
    return experiment
