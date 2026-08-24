"""Explicit authorization policy for project-structure mutations."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .enums import AuditAction, AuditActorType, ExperimentStatus, PublicationStatus
from .models import (
    AuditEvent,
    Experiment,
    Project,
    ProjectDefinitionVersion,
    ProjectLock,
    ProjectPublication,
    ProjectWorkspace,
)


class StructureActor(StrEnum):
    """Policy roles intentionally decoupled from Django authentication models."""

    ORDINARY = "ORDINARY"
    STUDIO = "STUDIO"
    SERVICE = "SERVICE"


class StructureMutationDenied(PermissionDenied):
    """Raised when an actor attempts to mutate a locked project structure."""


def can_modify_project_structure(
    project: Project,
    *,
    actor: StructureActor | str = StructureActor.ORDINARY,
) -> bool:
    """Return whether ``actor`` may add, remove, or rename structural entities.

    A missing lock means that the project is editable.  The service role is
    reserved for controlled operations such as validated imports and seed
    installation; callers must opt into it explicitly.
    """

    actor = StructureActor(actor)
    if actor is StructureActor.SERVICE:
        return True

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
) -> None:
    """Raise a domain-specific permission error unless mutation is authorized."""

    if can_modify_project_structure(project, actor=actor):
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


@transaction.atomic
def validate_project_definition(
    definition: ProjectDefinitionVersion,
    *,
    audit_workspace: ProjectWorkspace,
    actor_identifier: str,
    validation_result: dict,
) -> ProjectDefinitionVersion:
    """Record an explicit successful DRAFT -> VALIDATED transition."""

    if definition.project_id != audit_workspace.project_id:
        raise WorkspaceBoundaryViolation(
            "Definition validation cannot be audited from another project."
        )
    if definition.publication_status != PublicationStatus.DRAFT:
        raise ValidationError(
            {"publication_status": "Only a DRAFT definition can be validated."}
        )
    if not actor_identifier.strip():
        raise ValidationError({"actor_identifier": "Validation actor is required."})
    if not isinstance(validation_result, dict) or validation_result.get("valid") is not True:
        raise ValidationError(
            {"validation_result": "A successful explicit validation result is required."}
        )
    before = {"publication_status": definition.publication_status}
    definition.manifest_hash = hashlib.sha256(
        json.dumps(
            definition.manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    definition.publication_status = PublicationStatus.VALIDATED
    definition.validated_at = timezone.now()
    definition.validated_by = actor_identifier.strip()
    definition.validation_result = validation_result
    definition.full_clean()
    definition.save(
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
        workspace=audit_workspace,
        action=AuditAction.VALIDATE,
        actor_identifier=actor_identifier.strip(),
        entity_type="PROJECT_DEFINITION_VERSION",
        entity_id=definition.pk,
        before=before,
        after={
            "publication_status": definition.publication_status,
            "manifest_hash": definition.manifest_hash,
            "validation_result": validation_result,
        },
    )
    return definition


@transaction.atomic
def publish_project_definition(
    definition: ProjectDefinitionVersion,
    *,
    audit_workspace: ProjectWorkspace,
    actor_identifier: str,
    locale: str = "en",
) -> ProjectPublication:
    """Publish an exact definition and append a publication/audit record."""

    if definition.project_id != audit_workspace.project_id:
        raise WorkspaceBoundaryViolation(
            "Definition publication cannot be audited from another project."
        )
    if definition.publication_status != PublicationStatus.VALIDATED:
        raise ValidationError(
            {"publication_status": "Publishing requires an explicit VALIDATED transition."}
        )
    if definition.validation_result.get("valid") is not True:
        raise ValidationError(
            {"validation_result": "Publishing requires a successful validation result."}
        )
    if not actor_identifier.strip():
        raise ValidationError({"actor_identifier": "Publication actor is required."})
    before = {
        "publication_status": definition.publication_status,
        "is_current": definition.is_current,
    }
    ProjectDefinitionVersion.objects.filter(
        project_id=definition.project_id,
        is_current=True,
    ).exclude(pk=definition.pk).update(is_current=False)
    definition.publication_status = PublicationStatus.PUBLISHED
    definition.published_at = definition.published_at or timezone.now()
    definition.published_by = actor_identifier.strip()
    definition.is_current = True
    definition.full_clean()
    definition.save()
    publication = ProjectPublication(
        project=definition.project,
        definition_version=definition,
        code=_audit_code("PUB"),
        locale=locale,
        actor_identifier=actor_identifier.strip(),
        validation_result=definition.validation_result,
    )
    publication.full_clean()
    publication.save(force_insert=True)
    record_foundation_audit(
        workspace=audit_workspace,
        action=AuditAction.PUBLISH,
        actor_identifier=actor_identifier,
        entity_type="PROJECT_DEFINITION_VERSION",
        entity_id=definition.pk,
        before=before,
        after={
            "publication_status": definition.publication_status,
            "is_current": definition.is_current,
            "manifest_hash": definition.manifest_hash,
        },
    )
    return publication


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
