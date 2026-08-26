"""Authenticated HTTP boundary for the canonical Foundation definition services."""

from __future__ import annotations

from typing import Any, Callable

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import (
    HTTP_200_OK,
    HTTP_201_CREATED,
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
)

from domain.models import Project, ProjectDefinitionVersion, ProjectWorkspace
from domain.policies import (
    StudioCapability,
    bootstrap_initial_project_definition,
    publish_project_definition,
    require_studio_capability,
    studio_principal_from_user,
    validate_project_definition,
)
from domain.services.help_topics import HelpTopicResolutionError, resolve_help_topic
from domain.services.project_definitions import (
    ProjectDefinitionDraftConflict,
    clone_project_definition_draft,
    create_project_definition_draft,
    open_project_definition_draft,
    save_project_definition_draft,
)


def _definition_payload(definition: ProjectDefinitionVersion) -> dict[str, Any]:
    return {
        "id": str(definition.pk),
        "project_id": str(definition.project_id),
        "code": definition.code,
        "version": definition.version,
        "publication_status": definition.publication_status,
        "manifest": definition.manifest,
        "manifest_hash": definition.manifest_hash,
        "schema_version": definition.schema_version,
        "semantic_version": definition.semantic_version,
        "construct_version": definition.construct_version,
        "supersedes_id": (
            str(definition.supersedes_id) if definition.supersedes_id else None
        ),
    }


def _error_payload(exc: Exception) -> tuple[dict[str, Any], int]:
    if isinstance(exc, PermissionDenied):
        return {"code": "STUDIO_CAPABILITY_DENIED", "errors": [str(exc)]}, HTTP_403_FORBIDDEN
    if isinstance(exc, ProjectDefinitionDraftConflict):
        status = HTTP_409_CONFLICT
        code = "DRAFT_STALE"
    else:
        status = HTTP_400_BAD_REQUEST
        code = "STUDIO_DEFINITION_INVALID"
    if isinstance(exc, ValidationError):
        if hasattr(exc, "message_dict"):
            errors: Any = exc.message_dict
        else:
            errors = exc.messages
    else:
        errors = [str(exc)]
    return {"code": code, "errors": errors}, status


def _execute(operation: Callable[[], Any], *, success_status: int = HTTP_200_OK) -> Response:
    try:
        value = operation()
    except (Http404, ObjectDoesNotExist):
        return Response(
            {"code": "STUDIO_RESOURCE_NOT_FOUND", "errors": ["Resource not found."]},
            status=HTTP_404_NOT_FOUND,
        )
    except (PermissionDenied, ValidationError, ValueError, TypeError) as exc:
        payload, status = _error_payload(exc)
        return Response(payload, status=status)
    return Response(value, status=success_status)


def _principal(request: Request):
    # Body/header role or actor claims are deliberately ignored. Only the
    # authenticated Django permission backend creates this principal.
    return studio_principal_from_user(request.user)


def _definition_or_404(definition_id: str) -> ProjectDefinitionVersion:
    try:
        return ProjectDefinitionVersion.objects.select_related("project").get(
            pk=definition_id
        )
    except (ProjectDefinitionVersion.DoesNotExist, ValueError) as exc:
        raise Http404("Project definition not found.") from exc


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_definition_draft(request: Request) -> Response:
    def operation() -> dict[str, Any]:
        principal = _principal(request)
        project = Project.objects.get(pk=request.data.get("project_id"))
        definition = create_project_definition_draft(
            project=project,
            definition_id=request.data.get("id"),
            code=request.data.get("code", ""),
            version=request.data.get("version", ""),
            manifest=request.data.get("manifest"),
            semantic_version=request.data.get("semantic_version", "1.0.0"),
            construct_version=request.data.get("construct_version", "1.0.0"),
            principal=principal,
        )
        return _definition_payload(definition)

    return _execute(operation, success_status=HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def open_definition_draft(request: Request, definition_id: str) -> Response:
    def operation() -> dict[str, Any]:
        definition = open_project_definition_draft(
            _definition_or_404(definition_id),
            principal=_principal(request),
        )
        return _definition_payload(definition)

    return _execute(operation)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def clone_definition_draft(request: Request, definition_id: str) -> Response:
    def operation() -> dict[str, Any]:
        definition = clone_project_definition_draft(
            _definition_or_404(definition_id),
            definition_id=request.data.get("id"),
            code=request.data.get("code", ""),
            version=request.data.get("version", ""),
            principal=_principal(request),
        )
        return _definition_payload(definition)

    return _execute(operation, success_status=HTTP_201_CREATED)


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
def save_definition_draft(request: Request, definition_id: str) -> Response:
    def operation() -> dict[str, Any]:
        definition = save_project_definition_draft(
            _definition_or_404(definition_id),
            manifest=request.data.get("manifest"),
            expected_manifest_hash=request.data.get("expected_manifest_hash", ""),
            principal=_principal(request),
        )
        return _definition_payload(definition)

    return _execute(operation)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def validate_definition(request: Request, definition_id: str) -> Response:
    def operation() -> dict[str, Any]:
        principal = _principal(request)
        definition = validate_project_definition(
            _definition_or_404(definition_id),
            actor_identifier=principal.actor_identifier,
            principal=principal,
        )
        return _definition_payload(definition)

    return _execute(operation)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def publish_definition(request: Request, definition_id: str) -> Response:
    def operation() -> dict[str, Any]:
        principal = _principal(request)
        publication = publish_project_definition(
            _definition_or_404(definition_id),
            actor_identifier=principal.actor_identifier,
            principal=principal,
            workspace_spec=request.data.get("workspace"),
            locale=request.data.get("locale", "ru"),
        )
        return {
            "publication_id": str(publication.pk),
            "definition": _definition_payload(publication.definition_version),
            "initial_workspace_id": str(publication.initial_workspace_id),
        }

    return _execute(operation, success_status=HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def bootstrap_definition(request: Request, definition_id: str) -> Response:
    def operation() -> dict[str, Any]:
        principal = _principal(request)
        result = bootstrap_initial_project_definition(
            definition=_definition_or_404(definition_id),
            actor_identifier=principal.actor_identifier,
            principal=principal,
            workspace_spec=request.data.get("workspace"),
            locale=request.data.get("locale", "ru"),
        )
        return {
            "publication_id": str(result.publication.pk),
            "definition": _definition_payload(result.definition),
            "initial_workspace_id": str(result.workspace.pk),
            "help_binding_ids": [str(item.pk) for item in result.help_bindings],
        }

    return _execute(operation, success_status=HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def exact_help_topic(request: Request, ui_key: str) -> Response:
    def operation() -> dict[str, Any]:
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_READ)
        workspace = None
        workspace_id = request.query_params.get("workspace_id")
        if workspace_id:
            workspace = ProjectWorkspace.objects.get(pk=workspace_id)
        topic = resolve_help_topic(
            workspace=workspace,
            application_scope="STUDIO",
            ui_key=ui_key,
            locale=request.query_params.get("locale", ""),
            version=request.query_params.get("version", ""),
        )
        return {
            "stable_key": topic.stable_key,
            "version": topic.version,
            "locale": topic.locale,
            "title": topic.title,
            "sanitized_html": topic.sanitized_html,
            "content_sha256": topic.content_sha256,
        }

    try:
        return _execute(operation)
    except (HelpTopicResolutionError, ProjectWorkspace.DoesNotExist):
        return Response(
            {"code": "HELP_TOPIC_NOT_FOUND", "errors": ["No exact HelpTopic binding."]},
            status=HTTP_404_NOT_FOUND,
        )
