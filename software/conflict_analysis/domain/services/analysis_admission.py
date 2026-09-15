"""Authorization-first admission for method-safe Analysis V1 reads."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.contrib.auth import get_user_model

from domain.enums import AssessmentProjectionStatus, PublicationStatus
from domain.models import Project, ProjectWorkspace
from domain.services.analysis_contracts import AnalysisError
from domain.services.player_projection import verify_workspace_assessment_projection
from domain.services.project_definitions import (
    hash_project_definition_manifest_v1,
    project_access_group_name,
)


ANALYSIS_READER_PREFIX = "analysis-reader:"
ANALYSIS_LOCATION_EDITOR_PREFIX = "analysis-location-editor:"


@dataclass(frozen=True, slots=True)
class AnalysisPrincipal:
    user_id: object
    actor_identifier: str
    project_id: UUID


@dataclass(frozen=True, slots=True)
class AnalysisWorkspace:
    principal: AnalysisPrincipal
    project: Project
    workspace: ProjectWorkspace
    projection_sha256: str


def analysis_reader_group_name(project_id: object) -> str:
    return f"{ANALYSIS_READER_PREFIX}{project_id}"


def analysis_location_editor_group_name(project_id: object) -> str:
    return f"{ANALYSIS_LOCATION_EDITOR_PREFIX}{project_id}"


def exact_uuid(value: object) -> UUID:
    try:
        resolved = UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404) from exc
    if str(resolved) != str(value):
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    return resolved


def _zero_permission_group(user: object, name: str) -> bool:
    group = user.groups.filter(name=name).first()
    return bool(group is not None and not group.permissions.exists())


def analysis_principal(*, user: object, project_id: object) -> tuple[AnalysisPrincipal, Project]:
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        raise AnalysisError("ANALYSIS_AUTHENTICATION_REQUIRED", 401)
    try:
        persisted = get_user_model()._default_manager.get(pk=user.pk)
    except get_user_model().DoesNotExist as exc:
        raise AnalysisError("ANALYSIS_AUTHENTICATION_REQUIRED", 401) from exc
    if not persisted.is_active:
        raise AnalysisError("ANALYSIS_AUTHENTICATION_REQUIRED", 401)
    if persisted.is_staff or persisted.is_superuser:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)

    project_uuid = exact_uuid(project_id)
    project = Project.objects.filter(pk=project_uuid).first()
    if project is None:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    if not _zero_permission_group(persisted, project_access_group_name(project_uuid)):
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    if not _zero_permission_group(persisted, analysis_reader_group_name(project_uuid)):
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    return (
        AnalysisPrincipal(
            user_id=persisted.pk,
            actor_identifier=f"django-user:{persisted.pk}",
            project_id=project_uuid,
        ),
        project,
    )


def admit_analysis_workspace(
    *, user: object, project_id: object, workspace_id: object,
) -> AnalysisWorkspace:
    principal, project = analysis_principal(user=user, project_id=project_id)
    workspace_uuid = exact_uuid(workspace_id)
    workspace = (
        ProjectWorkspace.objects.select_related("project", "definition_version")
        .filter(pk=workspace_uuid, project=project)
        .first()
    )
    if workspace is None:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    definition = workspace.definition_version
    if (
        definition.project_id != project.pk
        or definition.publication_status != PublicationStatus.PUBLISHED
        or workspace.definition_manifest_hash != definition.manifest_hash
    ):
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    try:
        manifest_hash = hash_project_definition_manifest_v1(
            definition.manifest,
            project=project,
        )
    except Exception as exc:
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT") from exc
    if manifest_hash != definition.manifest_hash:
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")

    verification = verify_workspace_assessment_projection(workspace)
    if verification.status == AssessmentProjectionStatus.NOT_PROVEN:
        raise AnalysisError("ANALYSIS_PROJECTION_NOT_PROVEN")
    if (
        verification.status != AssessmentProjectionStatus.COMPLETE
        or not verification.projection_sha256
    ):
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    return AnalysisWorkspace(
        principal=principal,
        project=project,
        workspace=workspace,
        projection_sha256=verification.projection_sha256,
    )
