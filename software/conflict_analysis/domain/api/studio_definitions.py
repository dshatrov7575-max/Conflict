"""Canonical Foundation HTTP boundary for typed project definitions.

Raw request bytes are parsed before DRF materializes JSON.  Django permissions
select capabilities, while an explicit project group grants object scope.  The
public adapter never accepts a serialized Studio role or SERVICE principal.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Callable, Mapping
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
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
    Foundation21CommitResult,
    Foundation21Preview,
    RawJSONError,
    attempt_foundation_import_2_1,
    canonical_json,
    capture_http_json,
    export_project_definition_package_2_1,
    foundation_import_service_capabilities_2_1,
    parse_strong_manifest_if_match,
    preview_foundation_package_2_1,
    read_http_json,
)
from domain.services.project_definitions import (
    FoundationStudioApplicationConflict,
    ProjectDefinitionDraftConflict,
    bootstrap_project_definition_draft,
    clone_project_definition_draft,
    create_project_definition_draft,
    open_project_definition,
    project_access_group_name as canonical_project_access_group_name,
    publish_successor_project_definition,
    save_project_definition_draft,
)




class _RawJSONSessionAuthentication(SessionAuthentication):
    """Run real session CSRF before the view admits or reads JSON bytes."""

    def authenticate(self, request: Request):
        user = getattr(request._request, "user", None)
        if (
            user is None
            or not bool(getattr(user, "is_active", False))
            or getattr(user, "pk", None) is None
        ):
            # Preserve Basic-first anonymous semantics without reading a body.
            return None
        # DRF's wrapper may parse ``request.POST`` while CSRF is evaluated.  The
        # underlying Django request performs the same real cookie/header check
        # without treating application/json as a form body.  Therefore missing
        # or invalid CSRF consumes zero body bytes, and the view remains the
        # single bounded transport-admission and capture boundary.
        self.enforce_csrf(request._request)
        return user, None


_PUBLIC_AUTHENTICATION = (BasicAuthentication, _RawJSONSessionAuthentication)
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
        "stale_token",
    }
)
_SPOOF_HEADERS = frozenset(
    {
        "HTTP_X_ACTOR",
        "HTTP_X_ACTOR_IDENTIFIER",
        "HTTP_X_ACTOR_TYPE",
        "HTTP_X_AUDIT_CONTEXT",
        "HTTP_X_CAPABILITIES",
        "HTTP_X_EXPECTED_MANIFEST_HASH",
        "HTTP_X_PROJECT_ID",
        "HTTP_X_SERVICE_CONTEXT",
        "HTTP_X_SERVICE_PURPOSE",
        "HTTP_X_STUDIO_CAPABILITY",
        "HTTP_X_STUDIO_CAPABILITIES",
        "HTTP_X_STUDIO_ROLE",
    }
)
_PACKAGE_BOOTSTRAP_QUERY_KEYS = frozenset(
    {
        "locale",
        "initial_workspace_id",
        "initial_workspace_code",
        "initial_workspace_version",
        "initial_workspace_name",
        "initial_workspace_is_default",
    }
)
_LOCALE_PATTERN = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")


def project_access_group_name(project_id: object) -> str:
    """Stable server-side object-scope grant used by the public adapter."""

    return canonical_project_access_group_name(project_id)


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
    if isinstance(exc, FoundationStudioApplicationConflict):
        return {
            "code": exc.conflict_code,
            "errors": ["The requested Foundation application transition conflicts with persisted state."],
        }, HTTP_409_CONFLICT
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


def _reject_spoofed_authority(
    request: Request,
    payload: Mapping[str, Any],
    *,
    allow_if_match: bool = False,
) -> None:
    if _SPOOF_FIELDS.intersection(payload):
        raise ValidationError(
            {"authority": "Actor, capability, role, project and stale-token authority are server-derived."}
        )
    if any(name in request.META for name in _SPOOF_HEADERS):
        raise ValidationError(
            {"authority": "Studio authority headers are forbidden on the public API."}
        )
    if not allow_if_match and "HTTP_IF_MATCH" in request.META:
        raise ValidationError(
            {"authority": "If-Match is accepted only by the canonical DRAFT-save route."}
        )
    if _SPOOF_FIELDS.intersection(request.query_params):
        raise ValidationError(
            {"authority": "Studio authority query parameters are forbidden on the public API."}
        )


def _json_payload(request: Request, *, allow_if_match: bool = False) -> dict[str, Any]:
    document = read_http_json(request)
    payload = dict(document.value)
    _reject_spoofed_authority(
        request,
        payload,
        allow_if_match=allow_if_match,
    )
    return payload


def _with_etag(response: Response, manifest_hash: str) -> Response:
    response["ETag"] = f'"{manifest_hash}"'
    return response


def _require_import_entry_permission(user: object) -> None:
    has_perm = getattr(user, "has_perm", None)
    if not callable(has_perm) or not has_perm("domain.add_importrun"):
        raise PermissionDenied("Foundation package admission requires add_importrun.")


def _require_human_capability(user: object, capability: StudioCapability) -> None:
    permission_by_capability = {
        StudioCapability.DEFINITION_READ: "domain.studio_read_definition",
        StudioCapability.DRAFT_CREATE: "domain.studio_create_definition_draft",
        StudioCapability.DEFINITION_VALIDATE: "domain.studio_validate_definition",
        StudioCapability.DEFINITION_PUBLISH: "domain.studio_publish_definition",
    }
    permission = permission_by_capability[capability]
    has_perm = getattr(user, "has_perm", None)
    if not callable(has_perm) or not has_perm(permission):
        raise PermissionDenied(
            "The authenticated human lacks an action-specific Studio capability."
        )


def _package_human_principal(request: Request, project: Project):
    """Authorize HUMAN entry and scope before any internal SERVICE is created."""

    _require_import_entry_permission(request.user)
    principal = _principal(request)
    require_studio_capability(principal, StudioCapability.DEFINITION_READ)
    # ``project`` is deliberately consumed here: callers must have resolved it
    # through _project_or_404 before this helper can run.
    if str(project.pk) == "":  # pragma: no cover - persisted Projects always have a pk
        raise Http404("Project not found.")
    return principal


def _bounded_locale(value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 32
        or _LOCALE_PATTERN.fullmatch(value) is None
    ):
        raise ValidationError(
            {"locale": "Locale must be one bounded BCP-47-style token."}
        )
    return value


def _require_no_query(request: Request) -> None:
    _reject_spoofed_authority(request, {})
    if request.query_params:
        raise ValidationError({"query": "This route accepts no query parameters."})


def _bootstrap_workspace_query(
    request: Request,
    *,
    intended_action: str | None,
) -> tuple[dict[str, Any] | None, str]:
    """Accept the exact workspace query only for a server-decided bootstrap."""

    _reject_spoofed_authority(request, {})
    keys = set(request.query_params)
    if intended_action != "BOOTSTRAP_PUBLISHED":
        if keys:
            raise ValidationError(
                {"query": "Initial workspace parameters are forbidden for this server plan."}
            )
        return None, "ru"
    if keys != _PACKAGE_BOOTSTRAP_QUERY_KEYS or any(
        len(request.query_params.getlist(key)) != 1
        for key in _PACKAGE_BOOTSTRAP_QUERY_KEYS
    ):
        raise ValidationError(
            {
                "query": (
                    "BOOTSTRAP_PUBLISHED requires exactly one value for the complete "
                    "initial workspace query set."
                )
            }
        )
    raw_default = request.query_params["initial_workspace_is_default"]
    if raw_default not in {"true", "false"}:
        raise ValidationError(
            {"initial_workspace_is_default": "Use exactly true or false."}
        )
    locale = _bounded_locale(request.query_params["locale"])
    workspace = {
        "id": request.query_params["initial_workspace_id"],
        "code": request.query_params["initial_workspace_code"],
        "version": request.query_params["initial_workspace_version"],
        "name": request.query_params["initial_workspace_name"],
        "is_default": raw_default == "true",
        "metadata": {},
    }
    return workspace, locale


def _preview_payload(preview: Foundation21Preview) -> dict[str, Any]:
    return {
        "valid": preview.valid,
        "package_scope": preview.package_scope,
        "checksum": preview.checksum,
        "project_id": preview.project_id,
        "project_code": preview.project_code,
        "project_version": preview.project_version,
        "selected_definition_id": preview.selected_definition_id,
        "intended_action": preview.intended_action,
        "raw_input_kind": preview.raw_input_kind,
        "raw_input_sha256": preview.raw_input_sha256,
        "raw_input_byte_length": preview.raw_input_byte_length,
        "raw_input_name": preview.raw_input_name,
        "errors": [str(item) for item in preview.errors],
    }


def _commit_payload(commit: Foundation21CommitResult) -> dict[str, Any]:
    return {
        "package_scope": commit.package_scope,
        "action": commit.action,
        "definition_id": commit.definition_id,
        "workspace_id": commit.workspace_id,
        "receipt_id": commit.receipt_id,
        "checksum": commit.checksum,
    }


def _receipt_payload(receipt_id: object) -> dict[str, Any]:
    from domain.models import ImportRun

    receipt = ImportRun.objects.filter(pk=receipt_id).first()
    if receipt is None:
        raise RuntimeError("Foundation attempt returned no durable ImportRun receipt.")
    committed_at = (
        receipt.committed_at.isoformat().replace("+00:00", "Z")
        if receipt.committed_at is not None
        else None
    )
    return {
        "id": str(receipt.pk),
        "status": receipt.status,
        "project_id": str(receipt.project_id),
        "definition_id": (
            str(receipt.definition_version_id)
            if receipt.definition_version_id is not None
            else None
        ),
        "package_scope": receipt.package_scope,
        "package_id": receipt.package_id,
        "package_version": receipt.package_version,
        "checksum": receipt.checksum,
        "adapter": receipt.adapter,
        "selected_input": receipt.selected_input,
        "warnings": receipt.warnings,
        "errors": receipt.errors,
        "actor_identifier": receipt.actor_identifier,
        "committed_at": committed_at,
    }


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
        definition = open_project_definition(
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
        payload = _json_payload(request, allow_if_match=True)
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


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def publish_successor_definition(request: Request, definition_id: object) -> Response:
    def operation() -> dict[str, Any]:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_PUBLISH)
        _require_no_query(request)
        payload = _json_payload(request)
        if set(payload) - {"locale"}:
            raise ValidationError(
                {"body": "Successor publication accepts only an optional locale."}
            )
        publication = publish_successor_project_definition(
            definition,
            principal=principal,
            locale=(
                _bounded_locale(payload["locale"])
                if "locale" in payload
                else "en"
            ),
        )
        return {
            "publication_id": str(publication.pk),
            "definition": _definition_payload(publication.definition_version),
            "initial_workspace_id": None,
        }

    response = _execute(operation, success_status=HTTP_201_CREATED)
    if response.status_code == HTTP_201_CREATED:
        return _with_etag(
            response,
            str(response.data["definition"]["manifest_hash"]),
        )
    return response


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def preview_definition_package_2_1(request: Request, project_id: object) -> Response:
    def operation() -> dict[str, Any]:
        project = _project_or_404(request.user, project_id)
        _package_human_principal(request, project)
        _require_no_query(request)
        captured = capture_http_json(request)
        return _preview_payload(
            preview_foundation_package_2_1(captured, project=project)
        )

    return _execute(operation)


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def attempt_definition_package_2_1(request: Request, project_id: object) -> Response:
    def operation() -> dict[str, Any]:
        project = _project_or_404(request.user, project_id)
        _package_human_principal(request, project)
        captured = capture_http_json(request)

        preview: Foundation21Preview | None
        try:
            preview = preview_foundation_package_2_1(captured, project=project)
        except (RawJSONError, ValidationError, ValueError, TypeError):
            preview = None

        intended_action = preview.intended_action if preview is not None else None
        initial_workspace, locale = _bootstrap_workspace_query(
            request,
            intended_action=intended_action,
        )
        if intended_action == "CREATE_DRAFT":
            _require_human_capability(request.user, StudioCapability.DRAFT_CREATE)
        elif intended_action == "BOOTSTRAP_PUBLISHED":
            _require_human_capability(
                request.user, StudioCapability.DEFINITION_VALIDATE
            )
            _require_human_capability(
                request.user, StudioCapability.DEFINITION_PUBLISH
            )
        elif intended_action in {None, "REUSE_EXACT"}:
            # Human DEFINITION_READ was already enforced before the preview.
            pass
        else:
            raise ValidationError(
                {"intended_action": "Unknown Foundation package action is denied."}
            )
        service_capabilities = foundation_import_service_capabilities_2_1(
            intended_action
        )

        from domain.policies import StudioPrincipal

        service_principal = StudioPrincipal.service(
            actor_identifier=(
                f"foundation-http-import:django-user:{getattr(request.user, 'pk', '')}"
            ),
            purpose="Foundation 2.1 PROJECT_DEFINITION HTTP attempt",
            capabilities=service_capabilities,
        )
        result = attempt_foundation_import_2_1(
            captured,
            project=project,
            principal=service_principal,
            actor_identifier=service_principal.actor_identifier,
            initial_workspace=initial_workspace,
            locale=locale,
        )
        return {
            "status": result.status,
            "receipt_id": result.receipt_id,
            "preview": (
                _preview_payload(result.preview)
                if result.preview is not None
                else None
            ),
            "commit": (
                _commit_payload(result.commit) if result.commit is not None else None
            ),
            "errors": [dict(item) for item in result.errors],
            "receipt": _receipt_payload(result.receipt_id),
        }

    return _execute(operation)


@api_view(["GET"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def export_definition_package_2_1(
    request: Request,
    definition_id: object,
) -> Response | HttpResponse:
    def operation() -> dict[str, Any]:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_READ)
        _require_no_query(request)
        # Existing package export is the sole package authority.  The HTTP
        # representation hash deliberately covers its canonical bytes+newline.
        return export_project_definition_package_2_1(definition)

    result = _execute(operation)
    if result.status_code != HTTP_200_OK:
        return result
    package = dict(result.data)
    response_bytes = (canonical_json(package) + "\n").encode("utf-8")
    representation_sha256 = hashlib.sha256(response_bytes).hexdigest()
    response = HttpResponse(
        response_bytes,
        status=HTTP_200_OK,
        content_type="application/json; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="foundation-definition-{definition_id}-2.1.json"'
    )
    response["ETag"] = f'"{representation_sha256}"'
    response["X-Foundation-Semantic-Payload-SHA256"] = str(
        package["manifest"]["payload_sha256"]
    )
    return response


@api_view(["POST"])
@authentication_classes(_PUBLIC_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def bootstrap_first_definition_draft(request: Request) -> Response:
    def operation() -> dict[str, Any]:
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_CREATE)
        _require_no_query(request)
        payload = _json_payload(request)
        if set(payload) != {"project", "definition"}:
            raise ValidationError(
                {"body": "Bootstrap requires exactly project and definition objects."}
            )
        project = payload["project"]
        definition = payload["definition"]
        project_keys = {
            "id",
            "code",
            "version",
            "name",
            "description",
            "metadata",
        }
        definition_keys = {
            "id",
            "code",
            "version",
            "manifest",
            "semantic_version",
            "construct_version",
        }
        if not isinstance(project, Mapping) or set(project) != project_keys:
            raise ValidationError({"project": "Exact Project envelope is required."})
        if not isinstance(definition, Mapping) or set(definition) != definition_keys:
            raise ValidationError(
                {"definition": "Exact first-definition envelope is required."}
            )
        for section_name, section, string_fields in (
            (
                "project",
                project,
                ("id", "code", "version", "name", "description"),
            ),
            (
                "definition",
                definition,
                (
                    "id",
                    "code",
                    "version",
                    "semantic_version",
                    "construct_version",
                ),
            ),
        ):
            for field_name in string_fields:
                if not isinstance(section[field_name], str):
                    raise ValidationError(
                        {
                            f"{section_name}.{field_name}": (
                                "The exact bootstrap DTO requires a JSON string."
                            )
                        }
                    )
        if not isinstance(project["metadata"], Mapping):
            raise ValidationError(
                {"project.metadata": "Project metadata must be one exact JSON object."}
            )
        if not isinstance(definition["manifest"], Mapping):
            raise ValidationError(
                {"definition.manifest": "Definition manifest must be one exact JSON object."}
            )
        project_id = project["id"]
        definition_id = definition["id"]
        for field_name, value in (
            ("project.id", project_id),
            ("definition.id", definition_id),
        ):
            try:
                UUID(value)
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError(
                    {field_name: "A valid UUID string is required."}
                ) from exc
        result = bootstrap_project_definition_draft(
            project_id=project_id,
            project_code=project["code"],
            project_version=project["version"],
            project_name=project["name"],
            project_description=project["description"],
            project_metadata=project["metadata"],
            definition_id=definition_id,
            definition_code=definition["code"],
            definition_version=definition["version"],
            manifest=definition["manifest"],
            semantic_version=definition["semantic_version"],
            construct_version=definition["construct_version"],
            principal=principal,
            user=request.user,
        )
        return {
            "project": {
                "id": str(result.project.pk),
                "code": result.project.code,
                "version": result.project.version,
                "name": result.project.name,
                "description": result.project.description,
                "metadata": result.project.metadata,
            },
            "definition": _definition_payload(result.definition),
            "object_scope_group": result.scope_group.name,
            "audit_event_id": str(result.audit_event.pk),
        }

    response = _execute(operation, success_status=HTTP_201_CREATED)
    if response.status_code == HTTP_201_CREATED:
        return _with_etag(
            response,
            str(response.data["definition"]["manifest_hash"]),
        )
    return response


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
