"""Canonical Foundation HTTP boundary for typed project definitions.

Raw request bytes are parsed before DRF materializes JSON.  Django permissions
select capabilities, while an explicit project group grants object scope.  The
public adapter never accepts a serialized Studio role or SERVICE principal.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Mapping

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404
from django.middleware.csrf import get_token
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
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

from domain.models import Project, ProjectDefinitionVersion
from domain.policies import (
    StudioCapability,
    bootstrap_initial_project_definition,
    require_studio_capability,
    studio_principal_from_user,
    validate_project_definition,
)
from domain.services.help_topics import HelpTopicResolutionError, resolve_help_topic
from domain.services.foundation_packages import (
    RawJSONError,
    parse_strong_manifest_if_match,
    read_http_json,
)
from domain.services.project_definitions import (
    ProjectDefinitionDraftConflict,
    clone_project_definition_draft,
    create_project_definition_draft,
    open_project_definition_draft,
    save_project_definition_draft,
)


PROJECT_ACCESS_GROUP_PREFIX = "studio-project:"
_PUBLIC_AUTHENTICATION = (BasicAuthentication, SessionAuthentication)
_SPOOF_FIELDS = frozenset(
    {
        "actor",
        "actor_identifier",
        "actor_type",
        "audit_context",
        "capabilities",
        "capability",
        "expected_manifest_hash",
        "project_id",
        "role",
        "service_context",
        "service_purpose",
    }
)
_SPOOF_HEADERS = frozenset(
    {
        "HTTP_X_ACTOR",
        "HTTP_X_ACTOR_IDENTIFIER",
        "HTTP_X_EXPECTED_MANIFEST_HASH",
        "HTTP_X_STUDIO_CAPABILITY",
        "HTTP_X_STUDIO_ROLE",
    }
)


def project_access_group_name(project_id: object) -> str:
    """Stable server-side object-scope grant used by the public adapter."""

    return f"{PROJECT_ACCESS_GROUP_PREFIX}{project_id}"


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
    if isinstance(exc, RawJSONError):
        return dict(exc.as_dict()), HTTP_400_BAD_REQUEST
    if isinstance(exc, PermissionDenied):
        return {
            "code": "STUDIO_CAPABILITY_DENIED",
            "errors": ["The authenticated principal lacks the required Studio capability."],
        }, HTTP_403_FORBIDDEN
    if isinstance(exc, ProjectDefinitionDraftConflict):
        status = HTTP_409_CONFLICT
        code = "DRAFT_STALE"
        message = "The exact DRAFT validator is stale; reload before saving."
    else:
        status = HTTP_400_BAD_REQUEST
        code = "STUDIO_DEFINITION_INVALID"
        message = "The request failed canonical Foundation validation."
    detail_sha256 = hashlib.sha256(str(exc).encode("utf-8")).hexdigest()
    return {
        "code": code,
        "errors": [message],
        "detail_sha256": detail_sha256,
    }, status


def _execute(operation: Callable[[], Any], *, success_status: int = HTTP_200_OK) -> Response:
    try:
        value = operation()
    except (Http404, ObjectDoesNotExist):
        return Response(
            {"code": "STUDIO_RESOURCE_NOT_FOUND", "errors": ["Resource not found."]},
            status=HTTP_404_NOT_FOUND,
        )
    except (
        PermissionDenied,
        ProjectDefinitionDraftConflict,
        RawJSONError,
        ValidationError,
        ValueError,
        TypeError,
    ) as exc:
        payload, status = _error_payload(exc)
        return Response(payload, status=status)
    return Response(value, status=success_status)


def _principal(request: Request):
    return studio_principal_from_user(request.user)


def _has_project_access(user: object, project: Project) -> bool:
    if bool(getattr(user, "is_superuser", False)):
        return True
    groups = getattr(user, "groups", None)
    return bool(
        groups is not None
        and groups.filter(name=project_access_group_name(project.pk)).exists()
    )


def _project_or_404(user: object, project_id: object) -> Project:
    try:
        project = Project.objects.get(pk=project_id)
    except (Project.DoesNotExist, ValueError) as exc:
        raise Http404("Project not found.") from exc
    if not _has_project_access(user, project):
        raise Http404("Project not found.")
    return project


def _definition_or_404(user: object, definition_id: object) -> ProjectDefinitionVersion:
    try:
        definition = ProjectDefinitionVersion.objects.select_related("project").get(
            pk=definition_id
        )
    except (ProjectDefinitionVersion.DoesNotExist, ValueError) as exc:
        raise Http404("Project definition not found.") from exc
    if not _has_project_access(user, definition.project):
        raise Http404("Project definition not found.")
    return definition


def _reject_spoofed_authority(request: Request, payload: Mapping[str, Any]) -> None:
    if _SPOOF_FIELDS.intersection(payload):
        raise ValidationError(
            {"authority": "Actor, capability, role, project and stale-token authority are server-derived."}
        )
    if any(name in request.META for name in _SPOOF_HEADERS):
        raise ValidationError(
            {"authority": "Studio authority headers are forbidden on the public API."}
        )
    if _SPOOF_FIELDS.intersection(request.query_params):
        raise ValidationError(
            {"authority": "Studio authority query parameters are forbidden on the public API."}
        )


def _json_payload(request: Request) -> dict[str, Any]:
    document = read_http_json(request)
    payload = dict(document.value)
    _reject_spoofed_authority(request, payload)
    return payload


def _with_etag(response: Response, manifest_hash: str) -> Response:
    response["ETag"] = f'"{manifest_hash}"'
    return response


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def create_definition_draft(request: Request, project_id: object) -> Response:
    def operation() -> dict[str, Any]:
        project = _project_or_404(request.user, project_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_CREATE)
        payload = _json_payload(request)
        definition = create_project_definition_draft(
            project=project,
            definition_id=payload.get("id"),
            code=payload.get("code", ""),
            version=payload.get("version", ""),
            manifest=payload.get("manifest"),
            semantic_version=payload.get("semantic_version", "1.0.0"),
            construct_version=payload.get("construct_version", "1.0.0"),
            principal=principal,
        )
        return _definition_payload(definition)

    response = _execute(operation, success_status=HTTP_201_CREATED)
    if response.status_code == HTTP_201_CREATED:
        return _with_etag(response, str(response.data["manifest_hash"]))
    return response


@ensure_csrf_cookie
@api_view(["GET"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def open_definition(request: Request, definition_id: object) -> Response:
    def operation() -> dict[str, Any]:
        definition = open_project_definition_draft(
            _definition_or_404(request.user, definition_id),
            principal=_principal(request),
        )
        get_token(request._request)
        return _definition_payload(definition)

    response = _execute(operation)
    if response.status_code == HTTP_200_OK:
        return _with_etag(response, str(response.data["manifest_hash"]))
    return response


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def clone_definition(request: Request, definition_id: object) -> Response:
    def operation() -> dict[str, Any]:
        source = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_CLONE)
        payload = _json_payload(request)
        definition = clone_project_definition_draft(
            source,
            definition_id=payload.get("id"),
            code=payload.get("code", ""),
            version=payload.get("version", ""),
            principal=principal,
        )
        return _definition_payload(definition)

    response = _execute(operation, success_status=HTTP_201_CREATED)
    if response.status_code == HTTP_201_CREATED:
        return _with_etag(response, str(response.data["manifest_hash"]))
    return response


@api_view(["PUT"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def save_definition_draft(request: Request, definition_id: object) -> Response:
    def operation() -> dict[str, Any]:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_SAVE)
        expected_hash = parse_strong_manifest_if_match(
            request.META.get("HTTP_IF_MATCH")
        )
        payload = _json_payload(request)
        if set(payload) != {"manifest"}:
            raise ValidationError(
                {"body": "Draft save accepts exactly one manifest object; If-Match is the sole stale token."}
            )
        saved = save_project_definition_draft(
            definition,
            manifest=payload["manifest"],
            expected_manifest_hash=expected_hash,
            principal=principal,
        )
        return _definition_payload(saved)

    response = _execute(operation)
    if response.status_code == HTTP_200_OK:
        return _with_etag(response, str(response.data["manifest_hash"]))
    return response


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def validate_definition(request: Request, definition_id: object) -> Response:
    def operation() -> dict[str, Any]:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_VALIDATE)
        payload = _json_payload(request)
        _reject_spoofed_authority(request, payload)
        if payload:
            raise ValidationError({"body": "Validation accepts an empty JSON object only."})
        validated = validate_project_definition(
            definition,
            actor_identifier=principal.actor_identifier,
            principal=principal,
        )
        return _definition_payload(validated)

    return _execute(operation)


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def publish_initial_definition(request: Request, definition_id: object) -> Response:
    def operation() -> dict[str, Any]:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_VALIDATE)
        require_studio_capability(principal, StudioCapability.DEFINITION_PUBLISH)
        payload = _json_payload(request)
        result = bootstrap_initial_project_definition(
            definition=definition,
            actor_identifier=principal.actor_identifier,
            principal=principal,
            workspace_spec=payload.get("workspace"),
            locale=payload.get("locale", "ru"),
        )
        return {
            "publication_id": str(result.publication.pk),
            "definition": _definition_payload(result.definition),
            "initial_workspace_id": str(result.workspace.pk),
            "help_binding_ids": [str(item.pk) for item in result.help_bindings],
        }

    return _execute(operation, success_status=HTTP_201_CREATED)


@ensure_csrf_cookie
@api_view(["GET"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def exact_help_topic(request: Request, ui_key: str) -> Response:
    def operation() -> dict[str, Any]:
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_READ)
        application = request.query_params.get("application", "")
        locale = request.query_params.get("locale", "")
        version = request.query_params.get("version", "")
        if application != "STUDIO":
            raise Http404("Help topic not found.")
        expected_query = {"application", "locale", "version"}
        if set(request.query_params) != expected_query or any(
            len(request.query_params.getlist(key)) != 1 for key in expected_query
        ):
            raise Http404("Help topic not found.")
        topic = resolve_help_topic(
            workspace=None,
            application_scope=application,
            ui_key=ui_key,
            locale=locale,
            version=version,
        )
        get_token(request._request)
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
    except HelpTopicResolutionError:
        return Response(
            {"code": "HELP_TOPIC_NOT_FOUND", "errors": ["No exact HelpTopic binding."]},
            status=HTTP_404_NOT_FOUND,
        )
