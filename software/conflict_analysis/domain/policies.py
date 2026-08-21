"""Explicit authorization policy for project-structure mutations."""

from __future__ import annotations

from enum import StrEnum

from django.core.exceptions import PermissionDenied

from .models import Project, ProjectLock


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
