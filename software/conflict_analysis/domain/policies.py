"""Explicit authorization policy for project-structure mutations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
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


class StudioDefinitionRole(StrEnum):
    """Non-spoofable server-side Studio authorization classifications."""

    STUDIO_EDITOR = "STUDIO_EDITOR"
    STUDIO_PUBLISHER = "STUDIO_PUBLISHER"
    VIEWER = "VIEWER"
    PLAYER = "PLAYER"
    SERVICE = "SERVICE"


StudioRole = StudioDefinitionRole
"""Compatibility alias for the accepted ``StudioDefinitionRole`` contract."""


class StudioAuthorizationDenied(PermissionDenied):
    """Raised when a trusted Studio principal lacks an exact capability."""


class StudioCapability(StrEnum):
    DEFINITION_READ = "DEFINITION_READ"
    DRAFT_CREATE = "DRAFT_CREATE"
    DRAFT_CLONE = "DRAFT_CLONE"
    DRAFT_SAVE = "DRAFT_SAVE"
    DEFINITION_VALIDATE = "DEFINITION_VALIDATE"
    DEFINITION_PUBLISH = "DEFINITION_PUBLISH"
    FOUNDATION_IMPORT = "FOUNDATION_IMPORT"
    STRUCTURE_MUTATE = "STRUCTURE_MUTATE"


_ROLE_CAPABILITIES: Mapping[
    StudioDefinitionRole, frozenset[StudioCapability]
] = MappingProxyType(
    {
        StudioDefinitionRole.STUDIO_EDITOR: frozenset(
            {
                StudioCapability.DEFINITION_READ,
                StudioCapability.DRAFT_CREATE,
                StudioCapability.DRAFT_CLONE,
                StudioCapability.DRAFT_SAVE,
            }
        ),
        StudioDefinitionRole.STUDIO_PUBLISHER: frozenset(
            {
                StudioCapability.DEFINITION_READ,
                StudioCapability.DEFINITION_VALIDATE,
                StudioCapability.DEFINITION_PUBLISH,
            }
        ),
        StudioDefinitionRole.VIEWER: frozenset({StudioCapability.DEFINITION_READ}),
        StudioDefinitionRole.PLAYER: frozenset(),
        # SERVICE is deliberately empty unless a caller supplies a bounded
        # purpose and an explicit subset through ``StudioPrincipal.service``.
        StudioDefinitionRole.SERVICE: frozenset(),
    }
)


_SERVICE_CONTEXT_SEAL = object()
_MAX_ACTOR_IDENTIFIER_LENGTH = 255
_MAX_SERVICE_PURPOSE_LENGTH = 255


def _bounded_identity(value: object, *, label: str, maximum: int) -> str:
    """Normalize one server-side identity field and reject unbounded/control text."""

    if not isinstance(value, str):
        raise ValueError(f"{label} must be text.")
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{label} must contain 1..{maximum} characters.")
    if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
        raise ValueError(f"{label} must not contain control characters.")
    return normalized


@dataclass(frozen=True, slots=True, init=False)
class ServiceMutationContext:
    """Sealed, bounded SERVICE identity created only by a trusted server factory."""

    actor_identifier: str
    purpose: str
    capabilities: frozenset[StudioCapability]
    _trusted_seal: object = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        actor_identifier: str,
        purpose: str,
        capabilities: frozenset[StudioCapability | str],
        _seal: object | None = None,
    ) -> None:
        if _seal is not _SERVICE_CONTEXT_SEAL:
            raise ValueError(
                "ServiceMutationContext must be created by the trusted server factory."
            )
        actor = _bounded_identity(
            actor_identifier,
            label="SERVICE actor identifier",
            maximum=_MAX_ACTOR_IDENTIFIER_LENGTH,
        )
        bounded_purpose = _bounded_identity(
            purpose,
            label="SERVICE purpose",
            maximum=_MAX_SERVICE_PURPOSE_LENGTH,
        )
        try:
            resolved_capabilities = frozenset(
                StudioCapability(capability) for capability in capabilities
            )
        except (TypeError, ValueError):
            raise ValueError("SERVICE contains an unknown Studio capability.")
        if not resolved_capabilities:
            raise ValueError("SERVICE requires at least one explicit capability.")
        object.__setattr__(self, "actor_identifier", actor)
        object.__setattr__(self, "purpose", bounded_purpose)
        object.__setattr__(self, "capabilities", resolved_capabilities)
        object.__setattr__(self, "_trusted_seal", _SERVICE_CONTEXT_SEAL)

    @classmethod
    def _create(
        cls,
        *,
        actor_identifier: str,
        purpose: str,
        capabilities: frozenset[StudioCapability | str],
    ) -> "ServiceMutationContext":
        return cls(
            actor_identifier=actor_identifier,
            purpose=purpose,
            capabilities=capabilities,
            _seal=_SERVICE_CONTEXT_SEAL,
        )


@dataclass(frozen=True, slots=True)
class StudioPrincipal:
    """Immutable authorization fact created by a trusted server boundary."""

    actor_identifier: str
    role: StudioDefinitionRole
    capabilities: frozenset[StudioCapability]
    service_context: ServiceMutationContext | None = None

    def __post_init__(self) -> None:
        """Reject incoherent facts even when callers bypass trusted factories."""

        try:
            role = StudioDefinitionRole(self.role)
            capabilities = frozenset(
                StudioCapability(capability) for capability in self.capabilities
            )
        except (TypeError, ValueError):
            raise ValueError("StudioPrincipal contains an unknown role or capability.")
        actor_identifier = _bounded_identity(
            self.actor_identifier,
            label="StudioPrincipal actor identifier",
            maximum=_MAX_ACTOR_IDENTIFIER_LENGTH,
        )
        if role is StudioDefinitionRole.SERVICE:
            service_context = self.service_context
            if (
                not isinstance(service_context, ServiceMutationContext)
                or service_context._trusted_seal is not _SERVICE_CONTEXT_SEAL
                or service_context.actor_identifier != actor_identifier
                or service_context.capabilities != capabilities
            ):
                raise ValueError(
                    "SERVICE requires one exact trusted ServiceMutationContext."
                )
        else:
            unexpected = capabilities - _ROLE_CAPABILITIES[role]
            if unexpected:
                raise ValueError(
                    f"{role.value} contains capabilities outside its authorized role matrix."
                )
            if self.service_context is not None:
                raise ValueError("Only SERVICE may carry a ServiceMutationContext.")
        object.__setattr__(self, "actor_identifier", actor_identifier)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "capabilities", capabilities)

    @property
    def service_purpose(self) -> str:
        """Read-only compatibility view; purpose authority lives in the sealed context."""

        return self.service_context.purpose if self.service_context is not None else ""

    @classmethod
    def for_role(
        cls,
        *,
        actor_identifier: str,
        role: StudioDefinitionRole | str,
    ) -> "StudioPrincipal":
        resolved = StudioDefinitionRole(role)
        if resolved is StudioDefinitionRole.SERVICE:
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
        context = ServiceMutationContext._create(
            actor_identifier=actor_identifier,
            purpose=purpose,
            capabilities=capabilities,
        )
        return cls(
            actor_identifier=context.actor_identifier,
            role=StudioDefinitionRole.SERVICE,
            capabilities=context.capabilities,
            service_context=context,
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
        raise StudioAuthorizationDenied("Authenticated Studio access is required.")
    has_perm = getattr(user, "has_perm", None)
    if not callable(has_perm):
        raise StudioAuthorizationDenied(
            "The authenticated principal has no permission backend."
        )
    capabilities = frozenset(
        capability
        for permission, capability in _DJANGO_PERMISSION_CAPABILITIES.items()
        if has_perm(permission)
    )
    publisher_capabilities = _ROLE_CAPABILITIES[
        StudioDefinitionRole.STUDIO_PUBLISHER
    ]
    editor_capabilities = _ROLE_CAPABILITIES[StudioDefinitionRole.STUDIO_EDITOR]
    if capabilities <= publisher_capabilities and capabilities & {
        StudioCapability.DEFINITION_VALIDATE,
        StudioCapability.DEFINITION_PUBLISH,
    }:
        role = StudioDefinitionRole.STUDIO_PUBLISHER
    elif capabilities <= editor_capabilities and capabilities & (
        editor_capabilities - {StudioCapability.DEFINITION_READ}
    ):
        role = StudioDefinitionRole.STUDIO_EDITOR
    elif StudioCapability.DEFINITION_READ in capabilities:
        if capabilities == _ROLE_CAPABILITIES[StudioDefinitionRole.VIEWER]:
            role = StudioDefinitionRole.VIEWER
        else:
            raise StudioAuthorizationDenied(
                "Django Studio permissions span incompatible non-service roles."
            )
    elif capabilities:
        raise StudioAuthorizationDenied(
            "Django Studio permissions span incompatible non-service roles."
        )
    else:
        role = StudioDefinitionRole.PLAYER
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
        raise StudioAuthorizationDenied("A trusted StudioPrincipal is required.")
    if not principal.actor_identifier or required not in principal.capabilities:
        raise StudioAuthorizationDenied(
            f"{principal.role.value} is not allowed to perform {required.value}."
        )
    if (
        principal.role is StudioDefinitionRole.SERVICE
        and principal.service_context is None
    ):
        raise StudioAuthorizationDenied(
            "SERVICE authorization requires a trusted bounded context."
        )


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
            and service_principal.role is StudioDefinitionRole.SERVICE
            and service_principal.actor_identifier
            and service_principal.service_context is not None
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


_FOUNDATION_AUDIT_CONTEXT_SEAL = object()
_FOUNDATION_AUDIT_ATTRIBUTION_KEY = "foundation_audit_context"
FOUNDATION_HUMAN_OPERATION_AUDIT_KEY = "foundation_human_operation"
_FOUNDATION_HUMAN_RECEIPT_KEYS = frozenset(
    {
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
)
_FOUNDATION_HUMAN_REQUEST_KEYS = frozenset(
    {
        "contract",
        "sha256",
        "raw_input_sha256",
        "raw_input_byte_length",
        "if_match",
    }
)
_FOUNDATION_HUMAN_OPERATION_ACTIONS = MappingProxyType(
    {
        "BOOTSTRAP_DRAFT": AuditAction.CREATE,
        "CREATE_DRAFT": AuditAction.CREATE,
        "CLONE_DRAFT": AuditAction.CREATE,
        "SAVE_DRAFT": AuditAction.UPDATE,
        "VALIDATE_DEFINITION": AuditAction.VALIDATE,
    }
)
_FOUNDATION_HUMAN_OPERATION_STATUSES = MappingProxyType(
    {
        "BOOTSTRAP_DRAFT": 201,
        "CREATE_DRAFT": 201,
        "CLONE_DRAFT": 201,
        "SAVE_DRAFT": 200,
        "VALIDATE_DEFINITION": 200,
    }
)


@dataclass(frozen=True, slots=True, init=False)
class FoundationAuditContext:
    """Sealed actor and exact scope target consumed by audit insertion only."""

    actor_type: AuditActorType
    actor_identifier: str
    purpose: str
    scope: AuditScope
    project_id: UUID
    workspace_id: UUID | None
    definition_version_id: UUID | None
    _trusted_seal: object = field(repr=False, compare=False)

    def __init__(
        self,
        *,
        actor_type: AuditActorType | str,
        actor_identifier: str,
        purpose: str,
        scope: AuditScope | str,
        project_id: UUID,
        workspace_id: UUID | None,
        definition_version_id: UUID | None,
        _seal: object | None = None,
    ) -> None:
        if _seal is not _FOUNDATION_AUDIT_CONTEXT_SEAL:
            raise ValueError(
                "FoundationAuditContext must be created by the trusted server factory."
            )
        resolved_actor_type = AuditActorType(actor_type)
        if resolved_actor_type not in {
            AuditActorType.HUMAN,
            AuditActorType.SYSTEM,
        }:
            raise ValueError("Foundation audit attribution is HUMAN or SYSTEM only.")
        actor = _bounded_identity(
            actor_identifier,
            label="Foundation audit actor identifier",
            maximum=_MAX_ACTOR_IDENTIFIER_LENGTH,
        )
        resolved_scope = AuditScope(scope)
        bounded_purpose = purpose
        if resolved_actor_type == AuditActorType.SYSTEM:
            bounded_purpose = _bounded_identity(
                purpose,
                label="Foundation audit SERVICE purpose",
                maximum=_MAX_SERVICE_PURPOSE_LENGTH,
            )
        elif purpose:
            raise ValueError("HUMAN Foundation audit context cannot carry SERVICE purpose.")
        if resolved_scope == AuditScope.WORKSPACE:
            if workspace_id is None or definition_version_id is not None:
                raise ValueError("WORKSPACE audit context requires only a workspace target.")
        elif definition_version_id is None or workspace_id is not None:
            raise ValueError("DEFINITION audit context requires only a definition target.")
        object.__setattr__(self, "actor_type", resolved_actor_type)
        object.__setattr__(self, "actor_identifier", actor)
        object.__setattr__(self, "purpose", bounded_purpose)
        object.__setattr__(self, "scope", resolved_scope)
        object.__setattr__(self, "project_id", UUID(str(project_id)))
        object.__setattr__(
            self,
            "workspace_id",
            UUID(str(workspace_id)) if workspace_id is not None else None,
        )
        object.__setattr__(
            self,
            "definition_version_id",
            UUID(str(definition_version_id))
            if definition_version_id is not None
            else None,
        )
        object.__setattr__(self, "_trusted_seal", _FOUNDATION_AUDIT_CONTEXT_SEAL)

    @classmethod
    def _create(
        cls,
        *,
        actor_type: AuditActorType,
        actor_identifier: str,
        purpose: str,
        scope: AuditScope,
        project_id: UUID,
        workspace_id: UUID | None = None,
        definition_version_id: UUID | None = None,
    ) -> "FoundationAuditContext":
        return cls(
            actor_type=actor_type,
            actor_identifier=actor_identifier,
            purpose=purpose,
            scope=scope,
            project_id=project_id,
            workspace_id=workspace_id,
            definition_version_id=definition_version_id,
            _seal=_FOUNDATION_AUDIT_CONTEXT_SEAL,
        )

    @staticmethod
    def _principal_attribution(
        principal: StudioPrincipal,
    ) -> tuple[AuditActorType, str, str]:
        if not isinstance(principal, StudioPrincipal):
            raise StudioAuthorizationDenied(
                "A trusted StudioPrincipal is required for audit attribution."
            )
        if principal.role is StudioDefinitionRole.SERVICE:
            context = principal.service_context
            if (
                context is None
                or context._trusted_seal is not _SERVICE_CONTEXT_SEAL
            ):
                raise StudioAuthorizationDenied(
                    "SERVICE audit attribution requires a trusted bounded context."
                )
            return AuditActorType.SYSTEM, context.actor_identifier, context.purpose
        return AuditActorType.HUMAN, principal.actor_identifier, ""

    @classmethod
    def for_human_workspace(
        cls,
        *,
        workspace: ProjectWorkspace,
        actor_identifier: str,
    ) -> "FoundationAuditContext":
        """Create a HUMAN context from a server-owned workspace and identity."""

        if not isinstance(workspace, ProjectWorkspace) or workspace.pk is None:
            raise ValueError("A persisted ProjectWorkspace is required for audit context.")
        persisted = ProjectWorkspace.objects.only("id", "project_id").get(pk=workspace.pk)
        return cls._create(
            actor_type=AuditActorType.HUMAN,
            actor_identifier=actor_identifier,
            purpose="",
            scope=AuditScope.WORKSPACE,
            project_id=persisted.project_id,
            workspace_id=persisted.pk,
        )

    @classmethod
    def for_human_definition(
        cls,
        *,
        definition: ProjectDefinitionVersion,
        actor_identifier: str,
    ) -> "FoundationAuditContext":
        """Create a HUMAN context from a server-owned definition and identity."""

        if not isinstance(definition, ProjectDefinitionVersion) or definition.pk is None:
            raise ValueError(
                "A persisted ProjectDefinitionVersion is required for audit context."
            )
        persisted = ProjectDefinitionVersion.objects.only("id", "project_id").get(
            pk=definition.pk
        )
        return cls._create(
            actor_type=AuditActorType.HUMAN,
            actor_identifier=actor_identifier,
            purpose="",
            scope=AuditScope.DEFINITION,
            project_id=persisted.project_id,
            definition_version_id=persisted.pk,
        )

    @classmethod
    def for_principal_workspace(
        cls,
        *,
        workspace: ProjectWorkspace,
        principal: StudioPrincipal,
    ) -> "FoundationAuditContext":
        """Bind trusted HUMAN/SERVICE attribution to one persisted workspace."""

        if not isinstance(workspace, ProjectWorkspace) or workspace.pk is None:
            raise ValueError("A persisted ProjectWorkspace is required for audit context.")
        persisted = ProjectWorkspace.objects.only("id", "project_id").get(pk=workspace.pk)
        actor_type, actor_identifier, purpose = cls._principal_attribution(principal)
        return cls._create(
            actor_type=actor_type,
            actor_identifier=actor_identifier,
            purpose=purpose,
            scope=AuditScope.WORKSPACE,
            project_id=persisted.project_id,
            workspace_id=persisted.pk,
        )

    @classmethod
    def for_principal_definition(
        cls,
        *,
        definition: ProjectDefinitionVersion,
        principal: StudioPrincipal,
    ) -> "FoundationAuditContext":
        """Bind trusted HUMAN/SERVICE attribution to one persisted definition."""

        if not isinstance(definition, ProjectDefinitionVersion) or definition.pk is None:
            raise ValueError(
                "A persisted ProjectDefinitionVersion is required for audit context."
            )
        persisted = ProjectDefinitionVersion.objects.only("id", "project_id").get(
            pk=definition.pk
        )
        actor_type, actor_identifier, purpose = cls._principal_attribution(principal)
        return cls._create(
            actor_type=actor_type,
            actor_identifier=actor_identifier,
            purpose=purpose,
            scope=AuditScope.DEFINITION,
            project_id=persisted.project_id,
            definition_version_id=persisted.pk,
        )


def _audit_after_payload(
    context: FoundationAuditContext,
    after: dict | None,
) -> dict | None:
    """Persist exact SERVICE purpose without allowing payload provenance spoofing."""

    payload = dict(after) if after is not None else {}
    if _FOUNDATION_AUDIT_ATTRIBUTION_KEY in payload:
        raise ValidationError(
            {
                "after": (
                    f"{_FOUNDATION_AUDIT_ATTRIBUTION_KEY} is reserved for server attribution."
                )
            }
        )
    if context.actor_type == AuditActorType.SYSTEM:
        payload[_FOUNDATION_AUDIT_ATTRIBUTION_KEY] = {
            "actor_identifier": context.actor_identifier,
            "service_purpose": context.purpose,
        }
    return payload or None


def _require_audit_context(
    context: FoundationAuditContext,
    *,
    scope: AuditScope,
) -> FoundationAuditContext:
    if (
        not isinstance(context, FoundationAuditContext)
        or context._trusted_seal is not _FOUNDATION_AUDIT_CONTEXT_SEAL
        or context.scope != scope
    ):
        raise ValidationError(
            {"audit_context": f"A trusted {scope} FoundationAuditContext is required."}
        )
    return context


def record_foundation_audit(
    *,
    context: FoundationAuditContext,
    action: AuditAction | str,
    entity_type: str,
    entity_id: object,
    before: dict | None = None,
    after: dict | None = None,
    experiment: Experiment | None = None,
) -> AuditEvent:
    """Append one WORKSPACE event from a sealed, server-created context."""

    context = _require_audit_context(context, scope=AuditScope.WORKSPACE)
    workspace = ProjectWorkspace.objects.select_related("project").get(
        pk=context.workspace_id,
        project_id=context.project_id,
    )
    if experiment is not None:
        require_same_workspace(workspace, experiment)
    event = AuditEvent(
        project=workspace.project,
        workspace=workspace,
        assessment_set=experiment.assessment_set if experiment else None,
        code=_audit_code("AUD"),
        action=action,
        actor_type=context.actor_type,
        actor_identifier=context.actor_identifier,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=_audit_after_payload(context, after),
    )
    event.full_clean()
    event.save(force_insert=True)
    return event


def record_definition_audit(
    *,
    context: FoundationAuditContext,
    action: AuditAction | str,
    entity_type: str,
    entity_id: object,
    before: dict | None = None,
    after: dict | None = None,
    event_id: UUID | None = None,
    occurred_at: datetime | None = None,
    foundation_human_operation: Mapping[str, Any] | None = None,
) -> AuditEvent:
    """Append one DEFINITION event from a sealed, server-created context.

    ``event_id`` is optional for backwards compatibility.  Prospective FD05
    HUMAN writes bind it to the canonical idempotency UUID and persist their
    immutable reconciliation receipt under one reserved server-only key.
    """

    context = _require_audit_context(context, scope=AuditScope.DEFINITION)
    definition = ProjectDefinitionVersion.objects.select_related("project").get(
        pk=context.definition_version_id,
        project_id=context.project_id,
    )
    event_after = dict(after) if after is not None else {}
    if FOUNDATION_HUMAN_OPERATION_AUDIT_KEY in event_after:
        raise ValidationError(
            {
                "after": (
                    f"{FOUNDATION_HUMAN_OPERATION_AUDIT_KEY} is reserved for "
                    "server-authored HUMAN write receipts."
                )
            }
        )
    resolved_event_id: UUID | None = None
    if event_id is not None:
        resolved_event_id = UUID(str(event_id))
        if resolved_event_id.version != 4 or str(resolved_event_id) != str(event_id):
            raise ValidationError(
                {"event_id": "Definition operation id must be a canonical UUIDv4."}
            )
    if foundation_human_operation is not None:
        if resolved_event_id is None:
            raise ValidationError(
                {"event_id": "A HUMAN write receipt requires its operation UUID."}
            )
        if context.actor_type != AuditActorType.HUMAN:
            raise ValidationError(
                {"audit_context": "Public definition writes require HUMAN attribution."}
            )
        try:
            receipt = json.loads(
                json.dumps(
                    dict(foundation_human_operation),
                    ensure_ascii=False,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"foundation_human_operation": "Receipt must contain exact JSON values."}
            ) from exc
        operation = receipt.get("operation")
        expected_action = _FOUNDATION_HUMAN_OPERATION_ACTIONS.get(operation)
        expected_status = _FOUNDATION_HUMAN_OPERATION_STATUSES.get(operation)
        request_identity = receipt.get("request")
        after_definition = receipt.get("after_definition")
        if (
            set(receipt) != _FOUNDATION_HUMAN_RECEIPT_KEYS
            or receipt.get("contract") != "FOUNDATION_AUDITED_DEFINITION_WRITE_V1"
            or receipt.get("version") != "1.0.0"
            or expected_action is None
            or str(action) != expected_action
            or receipt.get("operation_id") != str(resolved_event_id)
            or receipt.get("audit_event_id") != str(resolved_event_id)
            or receipt.get("actor_type") != AuditActorType.HUMAN
            or receipt.get("actor_identifier") != context.actor_identifier
            or receipt.get("project_id") != str(definition.project_id)
            or receipt.get("before_definition") != before
            or not isinstance(after_definition, Mapping)
            or after_definition.get("id") != str(definition.pk)
            or after_definition.get("project_id") != str(definition.project_id)
            or str(entity_id) != str(definition.pk)
            or receipt.get("audit_action") != expected_action
            or isinstance(receipt.get("original_http_status"), bool)
            or receipt.get("original_http_status") != expected_status
            or not isinstance(request_identity, Mapping)
            or set(request_identity) != _FOUNDATION_HUMAN_REQUEST_KEYS
            or request_identity.get("contract")
            != "FOUNDATION_HUMAN_WRITE_REQUEST_IDENTITY_V1"
        ):
            raise ValidationError(
                {
                    "foundation_human_operation": (
                        "Receipt identity must equal its HUMAN audit context and UUID."
                    )
                }
            )
        event_after[FOUNDATION_HUMAN_OPERATION_AUDIT_KEY] = receipt
    event_kwargs: dict[str, Any] = {}
    if resolved_event_id is not None:
        event_kwargs["id"] = resolved_event_id
    if occurred_at is not None:
        event_kwargs["occurred_at"] = occurred_at
    event = AuditEvent(
        **event_kwargs,
        project=definition.project,
        workspace=None,
        definition_version=definition,
        scope=AuditScope.DEFINITION,
        assessment_set=None,
        parameter_value=None,
        code=(
            f"AUD-DEF-OP-{resolved_event_id.hex}"
            if resolved_event_id is not None
            else _audit_code("AUD-DEF")
        ),
        action=action,
        actor_type=context.actor_type,
        actor_identifier=context.actor_identifier,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=_audit_after_payload(context, event_after or None),
    )
    event.full_clean()
    event.save(force_insert=True)
    if foundation_human_operation is not None:
        # JSONB can normalize valid JSON values during persistence.  A fresh
        # FD05 response must use the same immutable receipt bytes as replay.
        event.refresh_from_db()
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


def validate_project_definition_manifest_policy(
    manifest: Mapping[str, Any],
    *,
    project: Project,
):
    """Run the sole typed-manifest validator with exact Foundation Help resolution.

    This policy composition is intentionally non-mutating.  Both HTTP preview
    and the lifecycle validator call this function so no API-local validator or
    Help resolver can become a second authority.
    """

    if not isinstance(project, Project) or project.pk is None:
        raise ValidationError({"project": "A persisted Project is required for validation."})
    from .services.project_definitions import validate_project_definition_manifest_v1

    return validate_project_definition_manifest_v1(
        manifest,
        project=project,
        help_topic_resolver=_typed_help_topic,
    )


def _lock_project_then_definition(
    definition: ProjectDefinitionVersion,
) -> tuple[Project, ProjectDefinitionVersion]:
    """Apply the canonical cross-path transition lock order.

    Every typed validation/publication/bootstrap path locks the owning
    ``Project`` first, then the exact ``ProjectDefinitionVersion``. Publication
    and workspace rows are locked/read only after this helper returns. Using
    the caller's project id solely to acquire the first lock, followed by an
    exact persisted row/hash recheck, fails closed on stale/reparented objects
    without ever locking a definition before its project.
    """

    if (
        not isinstance(definition, ProjectDefinitionVersion)
        or definition.pk is None
        or definition.project_id is None
    ):
        raise ValidationError(
            {"definition": "A persisted project definition is required."}
        )
    supplied_project_id = definition.project_id
    supplied_manifest_hash = definition.manifest_hash
    try:
        project = Project.objects.select_for_update().get(pk=supplied_project_id)
        current = (
            ProjectDefinitionVersion.objects.select_for_update()
            .select_related("project")
            .get(pk=definition.pk, project_id=project.pk)
        )
    except (Project.DoesNotExist, ProjectDefinitionVersion.DoesNotExist):
        raise ValidationError(
            {
                "definition": (
                    "The project/definition identity changed before the canonical lock."
                )
            }
        )
    if (
        current.project_id != supplied_project_id
        or current.manifest_hash != supplied_manifest_hash
    ):
        raise ValidationError(
            {
                "definition": (
                    "The project/definition snapshot changed before the canonical lock."
                )
            }
        )
    return project, current


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

    from .services.project_definitions import identify_typed_project_definition_manifest

    _, current = _lock_project_then_definition(definition)
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
        report = validate_project_definition_manifest_policy(
            current.manifest,
            project=current.project,
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
        _inject_bootstrap_failure(inject_failure_at, "after_canonical_validation")
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
            context=FoundationAuditContext.for_principal_definition(
                definition=current,
                principal=principal,
            ),
            action=AuditAction.VALIDATE,
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
        context=FoundationAuditContext.for_human_workspace(
            workspace=persisted_audit_workspace,
            actor_identifier=actor_identifier,
        ),
        action=AuditAction.VALIDATE,
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

    _, current = _lock_project_then_definition(definition)
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
            context=FoundationAuditContext.for_principal_definition(
                definition=current,
                principal=principal,
            ),
            action=AuditAction.PUBLISH,
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
                context=FoundationAuditContext.for_principal_workspace(
                    workspace=workspace,
                    principal=principal,
                ),
                action=AuditAction.BOOTSTRAP,
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
        context=FoundationAuditContext.for_human_workspace(
            workspace=persisted_audit_workspace,
            actor_identifier=actor_identifier,
        ),
        action=AuditAction.PUBLISH,
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
    _, locked = _lock_project_then_definition(definition)
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
        context=FoundationAuditContext.for_human_workspace(
            workspace=experiment.workspace,
            actor_identifier=actor_identifier,
        ),
        action=AuditAction.FREEZE,
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
