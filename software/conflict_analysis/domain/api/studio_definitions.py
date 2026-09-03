"""Canonical Foundation HTTP boundary for typed project definitions.

Raw request bytes are parsed before DRF materializes JSON.  Django permissions
select capabilities, while an explicit project group grants object scope.  The
public adapter never accepts a serialized Studio role or SERVICE principal.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import wraps
from typing import Any, Callable, Mapping
from uuid import RFC_4122, UUID

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.middleware.csrf import get_token
from django.utils.cache import patch_vary_headers
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.exceptions import AuthenticationFailed, ParseError
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
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

from domain.models import Project, ProjectDefinitionVersion, ProjectPublication
from domain.policies import (
    StudioCapability,
    require_studio_capability,
    studio_principal_from_user,
    validate_project_definition_manifest_policy,
)
from domain.services.help_topics import HelpTopicResolutionError, resolve_help_topic
from domain.services.language_tags import LanguageTagValidationError
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
    validate_json_content_type,
)
from domain.services.project_definitions import (
    FoundationHumanWriteError,
    FoundationHumanWriteOperation,
    FoundationHumanWriteRequestIdentity,
    FoundationHumanWriteResult,
    FoundationStudioApplicationConflict,
    ProjectDefinitionDraftConflict,
    bootstrap_project_definition_draft_human_write,
    canonical_bootstrap_envelope_identity,
    clone_project_definition_draft_human_write,
    create_project_definition_draft_human_write,
    find_publication_operation,
    open_project_definition,
    project_access_group_name as canonical_project_access_group_name,
    publication_operation_receipt,
    publication_operation_request_sha256,
    publication_readiness_snapshot,
    reconcile_publication_operation,
    save_project_definition_draft_human_write,
    validate_project_definition_human_write,
)


class _RawJSONSessionAuthentication(SessionAuthentication):
    """Admit JSON headers without body I/O before running real session CSRF."""

    def authenticate(self, request: Request):
        user = getattr(request._request, "user", None)
        if (
            user is None
            or not bool(getattr(user, "is_active", False))
            or getattr(user, "pk", None) is None
        ):
            # Preserve Basic-first anonymous semantics without reading a body.
            return None
        if request.method not in SAFE_METHODS:
            try:
                validate_json_content_type(
                    str(request._request.META.get("CONTENT_TYPE", ""))
                )
            except RawJSONError as exc:
                # Authentication runs outside the view's `_execute` wrapper.
                # Translate the fixed, bounded transport diagnostic to a DRF
                # response instead of allowing a raw ValueError to become 500.
                raise ParseError(detail=dict(exc.as_dict())) from exc
        # Unsupported form/multipart media has already failed without touching
        # request.POST. The underlying Django request now performs the real
        # cookie/header check for admitted JSON, which Django does not parse as
        # a form body. The view remains the sole body capture/parser authority.
        self.enforce_csrf(request._request)
        return user, None


class _ReadOnlyBasicAuthentication(BasicAuthentication):
    """Authenticate preview credentials without a password-upgrade write path."""

    _failure = "Invalid username/password."

    def authenticate_credentials(self, userid, password, request=None):
        user_model = get_user_model()
        try:
            user = user_model._default_manager.get_by_natural_key(userid)
        except user_model.DoesNotExist:
            # Match the current-hasher work factor without creating a row.
            dummy = user_model()
            dummy.set_password(password)
            raise AuthenticationFailed(self._failure)
        if not check_password(password, user.password, setter=None):
            raise AuthenticationFailed(self._failure)
        if not user.is_active:
            raise AuthenticationFailed(self._failure)
        return user, None


class _PublicationSessionAuthentication(_RawJSONSessionAuthentication):
    """Keep pre-CSRF media rejection on the fixed FD06 envelope DTO."""

    def authenticate(self, request: Request):
        try:
            return super().authenticate(request)
        except ParseError as exc:
            raise ParseError(
                detail={
                    "code": "PUBLICATION_ENVELOPE_INVALID",
                    "errors": [
                        "The request must match the exact publication envelope."
                    ],
                }
            ) from exc


_PUBLIC_AUTHENTICATION = (BasicAuthentication, _RawJSONSessionAuthentication)
_VALIDATION_PREVIEW_AUTHENTICATION = (
    _ReadOnlyBasicAuthentication,
    _RawJSONSessionAuthentication,
)
_HUMAN_WRITE_AUTHENTICATION = _VALIDATION_PREVIEW_AUTHENTICATION
_PUBLICATION_AUTHENTICATION = (
    _ReadOnlyBasicAuthentication,
    _PublicationSessionAuthentication,
)
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
_CANONICAL_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)

_HUMAN_WRITE_ERROR_MESSAGES = {
    "WRITE_OPERATION_KEY_REQUIRED": "Idempotency-Key is required for Foundation authoring.",
    "WRITE_OPERATION_KEY_INVALID": (
        "Idempotency-Key must be one canonical lowercase RFC 4122 UUIDv4."
    ),
    "AUTHORING_ENVELOPE_INVALID": (
        "The request must match the exact Foundation authoring envelope."
    ),
    "IF_MATCH_REQUIRED": "This Foundation operation requires one strong If-Match validator.",
    "IF_MATCH_INVALID": (
        "If-Match must contain exactly one strong quoted lowercase SHA-256 validator."
    ),
    "DEFINITION_VALIDATION_FAILED": (
        "The DRAFT failed canonical Foundation definition validation."
    ),
    "PROJECT_PRIMARY_LANGUAGE_REQUIRED": (
        "project_primary_language is required for Project bootstrap."
    ),
    "PROJECT_PRIMARY_LANGUAGE_INVALID": (
        "project_primary_language must be one well-formed RFC 5646 language tag."
    ),
    "PROJECT_PRIMARY_LANGUAGE_UND_FORBIDDEN": (
        "The runtime Project primary language must not be und."
    ),
}
_PUBLICATION_ERROR_MESSAGES = {
    "PUBLICATION_OPERATION_KEY_REQUIRED": "Idempotency-Key is required.",
    "PUBLICATION_OPERATION_KEY_INVALID": "Idempotency-Key must be one canonical lowercase RFC 4122 UUIDv4.",
    "PUBLICATION_IF_MATCH_REQUIRED": "If-Match is required.",
    "PUBLICATION_IF_MATCH_INVALID": "If-Match must be one strong quoted lowercase SHA-256.",
    "PUBLICATION_ENVELOPE_INVALID": "The request must match the exact publication envelope.",
}
_PUBLICATION_CONFLICT_CODES = frozenset(
    {
        "PUBLICATION_OPERATION_KEY_REUSE",
        "PUBLICATION_STALE",
        "PUBLICATION_TARGET_STATE_CONFLICT",
        "PUBLICATION_ALREADY_COMMITTED",
        "PUBLICATION_ID_CONFLICT",
        "PUBLICATION_WORKSPACE_CONFLICT",
        "PUBLICATION_OPERATION_IDENTITY_CORRUPT",
    }
)
_PUBLICATION_CONFLICT_MESSAGE = (
    "The requested Foundation publication operation conflicts with persisted state."
)
_PUBLICATION_READINESS_ERROR = {
    "code": "PUBLICATION_READINESS_REQUEST_INVALID",
    "errors": [
        "Publication readiness requires an empty query and no operation headers."
    ],
}


def project_access_group_name(project_id: object) -> str:
    """Stable server-side object-scope grant used by the public adapter."""

    return canonical_project_access_group_name(project_id)


def _persisted_datetime(value: Any) -> str | None:
    return (
        value.isoformat().replace("+00:00", "Z")
        if value is not None
        else None
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


def _open_definition_payload(
    definition: ProjectDefinitionVersion,
) -> dict[str, Any]:
    payload = _definition_payload(definition)
    payload.update(
        {
            "is_current": definition.is_current,
            "validation_result": definition.validation_result,
            "validated_at": _persisted_datetime(definition.validated_at),
            "validated_by": definition.validated_by,
            "published_at": _persisted_datetime(definition.published_at),
            "published_by": definition.published_by,
        }
    )
    return payload


def _publication_result_payload(publication: ProjectPublication) -> dict[str, Any]:
    definition = publication.definition_version
    workspace = publication.initial_workspace
    return {
        "publication_id": str(publication.pk),
        "project_id": str(publication.project_id),
        "definition_id": str(definition.pk),
        "definition_manifest_hash": definition.manifest_hash,
        "definition_publication_status": definition.publication_status,
        "definition_is_current": definition.is_current,
        "initial_workspace_id": str(workspace.pk) if workspace is not None else None,
        "initial_workspace_definition_id": (
            str(workspace.definition_version_id) if workspace is not None else None
        ),
        "initial_workspace_definition_manifest_hash": (
            workspace.definition_manifest_hash if workspace is not None else None
        ),
        "locale": publication.locale,
        "actor_identifier": publication.actor_identifier,
        "validation_result": publication.validation_result,
        "published_at": _persisted_datetime(publication.published_at),
    }


def _get_only_http_boundary(view):
    """Reject every non-GET method before DRF authentication or body access."""

    @wraps(view)
    def boundary(request, *args, **kwargs):
        if request.method != "GET":
            response = HttpResponseNotAllowed(["GET"])
            response["Content-Length"] = "0"
            return response
        return view(request, *args, **kwargs)

    return boundary


def _post_only_http_boundary(view):
    """Reject every non-POST method before authentication or body access."""

    @wraps(view)
    def boundary(request, *args, **kwargs):
        if request.method != "POST":
            response = HttpResponseNotAllowed(["POST"])
            response["Content-Length"] = "0"
            return response
        return view(request, *args, **kwargs)

    return boundary


def _suppress_publication_readiness_cookie_mutation(request, response=None) -> None:
    """Keep every FD07 response free of session and CSRF cookie mutation."""

    # SessionMiddleware bound its SessionStore before URL dispatch. Removing
    # only the raw cookie here therefore preserves authentication while keeping
    # its response phase from deleting or refreshing an incoming session key.
    request.COOKIES.pop(settings.SESSION_COOKIE_NAME, None)
    request.META["CSRF_COOKIE_NEEDS_UPDATE"] = False
    session = getattr(request, "session", None)
    if session is not None:
        session.accessed = False
        session.modified = False
    if response is not None:
        response.cookies.clear()
        if response.has_header("Set-Cookie"):
            del response["Set-Cookie"]


def _publication_readiness_cache_boundary(view):
    """Apply the route-wide FD07 cache and cookie privacy barrier."""

    @wraps(view)
    def boundary(request, *args, **kwargs):
        response = None
        _suppress_publication_readiness_cookie_mutation(request)
        try:
            response = view(request, *args, **kwargs)
            return response
        finally:
            if response is not None:
                response["Cache-Control"] = "no-store"
                response["Vary"] = "Cookie, Authorization"
            _suppress_publication_readiness_cookie_mutation(request, response)

    return boundary


class ValidationPreviewEnvelopeError(ValidationError):
    """Fixed public contract error for FD01 envelope/header/query drift."""


class FoundationHumanWriteAdmissionError(ValidationError):
    """Fixed public failure raised before an FD05 body is captured."""

    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__({"request": _HUMAN_WRITE_ERROR_MESSAGES[error_code]})


class FoundationPublicationAdmissionError(ValidationError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__({"request": _PUBLICATION_ERROR_MESSAGES[error_code]})


class FoundationPublicationReadinessAdmissionError(ValidationError):
    """Fixed FD07 request-metadata failure after scope and capability."""

    def __init__(self) -> None:
        super().__init__({"request": _PUBLICATION_READINESS_ERROR["errors"][0]})


def _error_payload(exc: Exception) -> tuple[dict[str, Any], int]:
    if isinstance(exc, RawJSONError):
        return dict(exc.as_dict()), HTTP_400_BAD_REQUEST
    if isinstance(exc, (FoundationHumanWriteAdmissionError, FoundationHumanWriteError)):
        error_code = exc.error_code
        payload: dict[str, Any] = {
            "code": error_code,
            "errors": [_HUMAN_WRITE_ERROR_MESSAGES[error_code]],
        }
        return payload, HTTP_400_BAD_REQUEST
    if isinstance(exc, FoundationPublicationAdmissionError):
        return {
            "code": exc.error_code,
            "errors": [_PUBLICATION_ERROR_MESSAGES[exc.error_code]],
        }, HTTP_400_BAD_REQUEST
    if isinstance(exc, FoundationPublicationReadinessAdmissionError):
        return dict(_PUBLICATION_READINESS_ERROR), HTTP_400_BAD_REQUEST
    if isinstance(exc, ValidationPreviewEnvelopeError):
        return {
            "code": "VALIDATION_PREVIEW_ENVELOPE_INVALID",
            "errors": ["Validation preview requires the exact FD01 request contract."],
        }, HTTP_400_BAD_REQUEST
    if isinstance(exc, PermissionDenied):
        return {
            "code": "STUDIO_CAPABILITY_DENIED",
            "errors": ["The authenticated principal lacks the required Studio capability."],
        }, HTTP_403_FORBIDDEN
    if isinstance(exc, FoundationStudioApplicationConflict):
        if exc.conflict_code in _PUBLICATION_CONFLICT_CODES:
            return {
                "code": exc.conflict_code,
                "errors": [_PUBLICATION_CONFLICT_MESSAGE],
            }, HTTP_409_CONFLICT
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


def _execute(
    operation: Callable[[], Any],
    *,
    success_status: int = HTTP_200_OK,
) -> Response:
    try:
        value = operation()
    except (Http404, ObjectDoesNotExist):
        return Response(
            {"code": "STUDIO_RESOURCE_NOT_FOUND", "errors": ["Resource not found."]},
            status=HTTP_404_NOT_FOUND,
        )
    except (
        PermissionDenied,
        FoundationPublicationAdmissionError,
        FoundationHumanWriteError,
        ProjectDefinitionDraftConflict,
        RawJSONError,
        ValidationError,
        ValueError,
        TypeError,
    ) as exc:
        payload, status = _error_payload(exc)
        return Response(payload, status=status)
    if isinstance(value, HttpResponse):
        return value
    return Response(value, status=success_status)


def _execute_publication(operation: Callable[[], Any]) -> Response:
    """Keep every FD06 failure on its fixed, non-fingerprinting public surface."""

    try:
        value = operation()
    except (Http404, ObjectDoesNotExist):
        return Response(
            {"code": "STUDIO_RESOURCE_NOT_FOUND", "errors": ["Resource not found."]},
            status=HTTP_404_NOT_FOUND,
        )
    except PermissionDenied as exc:
        payload, status = _error_payload(exc)
        return Response(payload, status=status)
    except FoundationPublicationAdmissionError as exc:
        payload, status = _error_payload(exc)
        return Response(payload, status=status)
    except FoundationStudioApplicationConflict as exc:
        code = (
            exc.conflict_code
            if exc.conflict_code in _PUBLICATION_CONFLICT_CODES
            else "PUBLICATION_TARGET_STATE_CONFLICT"
        )
        return Response(
            {"code": code, "errors": [_PUBLICATION_CONFLICT_MESSAGE]},
            status=HTTP_409_CONFLICT,
        )
    except (RawJSONError, FoundationHumanWriteError):
        return Response(
            {
                "code": "PUBLICATION_ENVELOPE_INVALID",
                "errors": [_PUBLICATION_ERROR_MESSAGES["PUBLICATION_ENVELOPE_INVALID"]],
            },
            status=HTTP_400_BAD_REQUEST,
        )
    except (IntegrityError, ValidationError, ValueError, TypeError, AttributeError, KeyError):
        return Response(
            {
                "code": "PUBLICATION_TARGET_STATE_CONFLICT",
                "errors": [_PUBLICATION_CONFLICT_MESSAGE],
            },
            status=HTTP_409_CONFLICT,
        )
    if isinstance(value, HttpResponse):
        return value
    return Response(value, status=HTTP_200_OK)


def _principal(request: Request):
    return studio_principal_from_user(request.user)


def _current_publication_user(request: Request):
    """Re-read the authenticated HUMAN before object scope or capability checks."""

    user = request.user
    user_model = get_user_model()
    try:
        current_user = user_model._default_manager.get(pk=getattr(user, "pk", None))
    except (user_model.DoesNotExist, TypeError, ValueError) as exc:
        raise PermissionDenied("The authenticated principal is no longer persisted.") from exc
    if not bool(getattr(current_user, "is_active", False)):
        raise PermissionDenied("The authenticated principal is no longer active.")
    return current_user


def _current_publication_principal(user: object):
    """Derive current capabilities without reusing an authenticator permission cache."""

    return studio_principal_from_user(user)


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


def _canonical_entity_uuid(value: object) -> UUID:
    if not isinstance(value, str) or _CANONICAL_UUID_PATTERN.fullmatch(value) is None:
        raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
    try:
        resolved = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise FoundationHumanWriteAdmissionError(
            "AUTHORING_ENVELOPE_INVALID"
        ) from exc
    if str(resolved) != value:
        raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
    return resolved


def _foundation_operation_id(request: Request) -> UUID:
    value = request.META.get("HTTP_IDEMPOTENCY_KEY")
    if value is None or value == "":
        raise FoundationHumanWriteAdmissionError("WRITE_OPERATION_KEY_REQUIRED")
    if not isinstance(value, str) or _CANONICAL_UUID_PATTERN.fullmatch(value) is None:
        raise FoundationHumanWriteAdmissionError("WRITE_OPERATION_KEY_INVALID")
    try:
        operation_id = UUID(value)
    except (AttributeError, TypeError, ValueError) as exc:
        raise FoundationHumanWriteAdmissionError(
            "WRITE_OPERATION_KEY_INVALID"
        ) from exc
    if (
        str(operation_id) != value
        or operation_id.version != 4
        or operation_id.variant != RFC_4122
    ):
        raise FoundationHumanWriteAdmissionError("WRITE_OPERATION_KEY_INVALID")
    return operation_id


def _human_write_admission(
    request: Request,
    *,
    operation: FoundationHumanWriteOperation,
    allow_if_match: bool,
) -> tuple[UUID, str | None, Any, dict[str, Any]]:
    """Admit metadata/key/token before one authoritative HTTP body capture."""

    try:
        _reject_spoofed_authority(request, {}, allow_if_match=allow_if_match)
    except ValidationError as exc:
        raise FoundationHumanWriteAdmissionError(
            "AUTHORING_ENVELOPE_INVALID"
        ) from exc
    if request.query_params:
        raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")

    operation_id = _foundation_operation_id(request)
    if allow_if_match:
        if_match = parse_strong_manifest_if_match(
            request.META.get("HTTP_IF_MATCH"),
            operation=operation.value,
        )
    else:
        if_match = None

    captured = capture_http_json(request)
    payload = dict(read_http_json(request).value)
    try:
        _reject_spoofed_authority(
            request,
            payload,
            allow_if_match=allow_if_match,
        )
    except ValidationError as exc:
        raise FoundationHumanWriteAdmissionError(
            "AUTHORING_ENVELOPE_INVALID"
        ) from exc
    _require_human_write_unicode_scalars(payload)
    return operation_id, if_match, captured, payload


def _human_write_request_identity(
    *,
    operation: FoundationHumanWriteOperation,
    operation_id: UUID,
    request: Request,
    principal: object,
    captured: Any,
    project_id: UUID | None,
    source_definition_id: UUID | None,
    target_definition_id: UUID | None,
    if_match: str | None,
    canonical_envelope_sha256: str | None = None,
    project_primary_language: str | None = None,
) -> FoundationHumanWriteRequestIdentity:
    return FoundationHumanWriteRequestIdentity.build(
        operation=operation,
        operation_id=operation_id,
        method=request.method,
        route=request.path,
        actor_identifier=principal.actor_identifier,
        project_id=project_id,
        source_definition_id=source_definition_id,
        target_definition_id=target_definition_id,
        content_type="application/json",
        raw_input_sha256=captured.identity.sha256,
        raw_input_byte_length=captured.identity.byte_length,
        if_match=if_match,
        canonical_envelope_sha256=canonical_envelope_sha256,
        project_primary_language=project_primary_language,
    )


def _human_write_response(
    result: FoundationHumanWriteResult,
    *,
    fresh_payload: Mapping[str, Any] | None,
    fresh_status: int,
) -> Response:
    receipt = result.receipt.as_dict()
    if result.replayed:
        payload: dict[str, Any] = {
            "code": "WRITE_OPERATION_RECONCILED",
            "write_receipt": receipt,
        }
        status = HTTP_200_OK
    else:
        if fresh_payload is None:
            raise RuntimeError("A fresh Foundation HUMAN write requires its operation payload.")
        payload = {**dict(fresh_payload), "write_receipt": receipt}
        status = fresh_status

    response = Response(payload, status=status)
    response["X-Foundation-Operation-Replayed"] = (
        "true" if result.replayed else "false"
    )
    response["X-Foundation-Receipt-SHA256"] = result.receipt.sha256
    response["ETag"] = f'"{result.receipt.after_definition["manifest_hash"]}"'
    return response


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


def _publication_admission(
    request: Request,
    *,
    definition: ProjectDefinitionVersion,
    principal: object,
    operation_kind: str,
) -> tuple[UUID, str, str, dict[str, Any] | None, str]:
    """Admit key/token and one sealed body before publication domain work."""

    if request.query_params:
        raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID")
    key = request.META.get("HTTP_IDEMPOTENCY_KEY")
    if key is None or key == "":
        raise FoundationPublicationAdmissionError("PUBLICATION_OPERATION_KEY_REQUIRED")
    try:
        operation_id = UUID(key)
    except (AttributeError, TypeError, ValueError) as exc:
        raise FoundationPublicationAdmissionError("PUBLICATION_OPERATION_KEY_INVALID") from exc
    if (
        not isinstance(key, str)
        or str(operation_id) != key
        or operation_id.version != 4
        or operation_id.variant != RFC_4122
    ):
        raise FoundationPublicationAdmissionError("PUBLICATION_OPERATION_KEY_INVALID")
    raw_if_match = request.META.get("HTTP_IF_MATCH")
    if raw_if_match is None or raw_if_match == "":
        raise FoundationPublicationAdmissionError("PUBLICATION_IF_MATCH_REQUIRED")
    matched = re.fullmatch(r'"([0-9a-f]{64})"', str(raw_if_match))
    if matched is None:
        raise FoundationPublicationAdmissionError("PUBLICATION_IF_MATCH_INVALID")
    expected_hash = matched.group(1)
    try:
        _reject_spoofed_authority(request, {}, allow_if_match=True)
        capture_http_json(request)
        payload = dict(read_http_json(request).value)
        _reject_spoofed_authority(request, payload, allow_if_match=True)
        _require_human_write_unicode_scalars(payload)
    except (RawJSONError, ValidationError, ValueError, TypeError) as exc:
        raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID") from exc

    workspace: dict[str, Any] | None
    if operation_kind == "INITIAL":
        if set(payload) != {"locale", "workspace"} or not isinstance(payload["workspace"], Mapping):
            raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID")
        workspace = dict(payload["workspace"])
        if set(workspace) != {"id", "code", "version", "name", "is_default", "metadata"}:
            raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID")
        if (
            any(not isinstance(workspace[field], str) for field in ("id", "code", "version", "name"))
            or workspace["is_default"] is not True
            or not isinstance(workspace["metadata"], Mapping)
        ):
            raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID")
        try:
            workspace_id = UUID(workspace["id"])
        except ValueError as exc:
            raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID") from exc
        if str(workspace_id) != workspace["id"]:
            raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID")
        workspace["metadata"] = dict(workspace["metadata"])
    else:
        if set(payload) != {"locale"}:
            raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID")
        workspace = None
    try:
        locale = _bounded_locale(payload["locale"])
    except (KeyError, ValidationError) as exc:
        raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID") from exc
    request_hash = publication_operation_request_sha256(
        operation_kind=operation_kind,
        project_id=definition.project_id,
        definition_id=definition.pk,
        expected_manifest_hash=expected_hash,
        actor_identifier=principal.actor_identifier,
        locale=locale,
        initial_workspace=workspace,
    )
    return operation_id, expected_hash, locale, workspace, request_hash


def _publication_recovery_admission(request: Request) -> None:
    """Admit the exact bodyless recovery envelope after scope and capability."""

    if (
        request.query_params
        or "HTTP_IDEMPOTENCY_KEY" in request.META
        or "HTTP_IF_MATCH" in request.META
        or any(name in request.META for name in _SPOOF_HEADERS)
    ):
        raise FoundationPublicationAdmissionError("PUBLICATION_ENVELOPE_INVALID")


def _publication_readiness_admission(request: Request) -> None:
    """Admit the exact bodyless FD07 envelope after scope and capability."""

    if (
        request.query_params
        or "HTTP_IDEMPOTENCY_KEY" in request.META
        or "HTTP_IF_MATCH" in request.META
        or any(name in request.META for name in _SPOOF_HEADERS)
    ):
        raise FoundationPublicationReadinessAdmissionError()


def _publication_operation_response(
    publication: ProjectPublication,
    *,
    replayed: bool,
    status: int,
    recovery_cache_barrier: bool = False,
) -> HttpResponse:
    body = json.dumps(
        publication_operation_receipt(publication),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    response = HttpResponse(body, status=status, content_type="application/json")
    response["ETag"] = f'"{hashlib.sha256(body).hexdigest()}"'
    response["Location"] = (
        f"/api/foundation/projects/{publication.project_id}/"
        f"publication-results/{publication.pk}/"
    )
    response["Idempotency-Replayed"] = "true" if replayed else "false"
    if recovery_cache_barrier:
        response["Cache-Control"] = "no-store"
        patch_vary_headers(response, ("Cookie", "Authorization"))
    return response


def _publication_readiness_response(snapshot: Mapping[str, Any]) -> HttpResponse:
    body = json.dumps(
        snapshot,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8") + b"\n"
    response = HttpResponse(body, status=HTTP_200_OK, content_type="application/json")
    response["ETag"] = f'"{snapshot["readiness_sha256"]}"'
    response["Cache-Control"] = "no-store"
    patch_vary_headers(response, ("Cookie", "Authorization"))
    return response


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


_VALIDATION_PREVIEW_MAX_DIAGNOSTICS = 1000
_VALIDATION_PREVIEW_TEXT_MAX_BYTES = 512
_VALIDATION_PREVIEW_TRUNCATED_TEXT = "<TRUNCATED>"
_VALIDATION_PREVIEW_UNICODE_ERROR = (
    "JSON object keys and string values must contain only Unicode scalar values."
)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _bounded_preview_text(value: str) -> str:
    return (
        value
        if len(value.encode("utf-8")) <= _VALIDATION_PREVIEW_TEXT_MAX_BYTES
        else _VALIDATION_PREVIEW_TRUNCATED_TEXT
    )


def _validation_preview_metadata_admission(request: Request) -> None:
    if (
        request.query_params
        or "HTTP_IF_MATCH" in request.META
        or "HTTP_IDEMPOTENCY_KEY" in request.META
        or any(name in request.META for name in _SPOOF_HEADERS)
    ):
        raise ValidationPreviewEnvelopeError(
            {"request": "Query, authority, If-Match and Idempotency-Key are forbidden."}
        )


def _contains_lone_unicode_surrogate(value: Any) -> bool:
    if isinstance(value, str):
        return any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    if isinstance(value, Mapping):
        return any(
            _contains_lone_unicode_surrogate(key)
            or _contains_lone_unicode_surrogate(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_lone_unicode_surrogate(item) for item in value)
    return False


def _require_validation_preview_unicode_scalars(value: Any) -> None:
    if _contains_lone_unicode_surrogate(value):
        raise RawJSONError(
            "RAW_JSON_UNICODE_SCALAR_INVALID",
            _VALIDATION_PREVIEW_UNICODE_ERROR,
            path="$",
        )


def _require_human_write_unicode_scalars(value: Any) -> None:
    if _contains_lone_unicode_surrogate(value):
        raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")


def _suppress_validation_preview_cookie_mutation(request, response=None) -> None:
    # SessionMiddleware has already bound the SessionStore before view dispatch.
    # Removing only the raw cookie prevents its response phase from emitting a
    # deletion for malformed/expired keys without weakening valid-session auth.
    request.COOKIES.pop(settings.SESSION_COOKIE_NAME, None)
    request.META["CSRF_COOKIE_NEEDS_UPDATE"] = False
    session = getattr(request, "session", None)
    if session is not None:
        session.accessed = False
        session.modified = False
    if response is not None:
        response.cookies.clear()


def _validation_preview_http_boundary(view):
    """Run the exact method/cookie boundary before DRF authentication."""

    @wraps(view)
    def boundary(request, *args, **kwargs):
        response = None
        _suppress_validation_preview_cookie_mutation(request)
        try:
            if request.method != "POST":
                response = HttpResponseNotAllowed(["POST"])
                response["Content-Length"] = "0"
                return response
            response = view(request, *args, **kwargs)
            return response
        finally:
            _suppress_validation_preview_cookie_mutation(request, response)

    return boundary


def _validation_report_projection(
    *,
    definition: ProjectDefinitionVersion,
    manifest: Mapping[str, Any],
    request_sha256: str,
    request_byte_length: int,
    report: Any,
) -> dict[str, Any]:
    """Build the sole bounded FD01 report identity for public HTTP responses."""

    if isinstance(report, Mapping):
        raw_diagnostics = report["diagnostics"]
        schema_id = report["schema_id"]
        schema_version = report["schema_version"]
        manifest_sha256 = report["manifest_sha256"]
        valid = report["valid"]
    else:
        raw_diagnostics = report.diagnostics
        schema_id = report.schema_id
        schema_version = report.schema_version
        manifest_sha256 = report.manifest_sha256
        valid = report.valid
    complete_diagnostics = [
        dict(item) if isinstance(item, Mapping) else item.as_dict()
        for item in raw_diagnostics
    ]
    diagnostics_sha256 = _sha256_bytes(_canonical_json_bytes(complete_diagnostics))
    projected: list[dict[str, Any]] = []
    for ordinal, diagnostic in enumerate(complete_diagnostics[:_VALIDATION_PREVIEW_MAX_DIAGNOSTICS]):
        path = str(diagnostic["path"])
        message = str(diagnostic["message"])
        projected.append(
            {
                "ordinal": ordinal,
                "level": str(diagnostic["level"]),
                "code": str(diagnostic["code"]),
                "path": _bounded_preview_text(path),
                "path_sha256": _sha256_text(path),
                "message": _bounded_preview_text(message),
                "message_sha256": _sha256_text(message),
            }
        )
    candidate_sha256 = _sha256_bytes(_canonical_json_bytes(manifest))
    response_core: dict[str, Any] = {
        "contract": "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1",
        "contract_version": "1.0.0",
        "schema_id": str(schema_id),
        "schema_version": str(schema_version),
        "definition_id": str(definition.pk),
        "project_id": str(definition.project_id),
        "base_manifest_sha256": definition.manifest_hash,
        "request_sha256": request_sha256,
        "request_byte_length": request_byte_length,
        "candidate_sha256": candidate_sha256,
        "manifest_sha256": str(manifest_sha256),
        "valid": bool(valid),
        "diagnostics_total": len(complete_diagnostics),
        "diagnostics_returned": len(projected),
        "diagnostics_truncated": len(complete_diagnostics) > len(projected),
        "diagnostics_sha256": diagnostics_sha256,
        "diagnostics": projected,
    }
    validation_report_sha256 = _sha256_bytes(_canonical_json_bytes(response_core))
    return {**response_core, "validation_report_sha256": validation_report_sha256}


def _validation_preview_response(
    *,
    definition: ProjectDefinitionVersion,
    manifest: Mapping[str, Any],
    request_sha256: str,
    request_byte_length: int,
    report: Any,
) -> HttpResponse:
    payload = _validation_report_projection(
        definition=definition,
        manifest=manifest,
        request_sha256=request_sha256,
        request_byte_length=request_byte_length,
        report=report,
    )
    response_bytes = _canonical_json_bytes(payload) + b"\n"
    representation_sha256 = _sha256_bytes(response_bytes)
    response = HttpResponse(
        response_bytes,
        status=HTTP_200_OK,
        content_type="application/json; charset=utf-8",
    )
    response["Content-Length"] = str(len(response_bytes))
    response["ETag"] = f'"{representation_sha256}"'
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@api_view(["POST"])
@authentication_classes(_HUMAN_WRITE_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def create_definition_draft(request: Request, project_id: object) -> Response:
    def operation() -> Response:
        project = _project_or_404(request.user, project_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_CREATE)
        operation_name = FoundationHumanWriteOperation.CREATE_DRAFT
        operation_id, if_match, captured, payload = _human_write_admission(
            request,
            operation=operation_name,
            allow_if_match=False,
        )
        expected_keys = {
            "id",
            "code",
            "version",
            "manifest",
            "semantic_version",
            "construct_version",
        }
        if (
            set(payload) != expected_keys
            or not isinstance(payload["manifest"], Mapping)
            or any(
                not isinstance(payload[field], str)
                for field in (
                    "id",
                    "code",
                    "version",
                    "semantic_version",
                    "construct_version",
                )
            )
        ):
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        definition_id = _canonical_entity_uuid(payload["id"])
        request_identity = _human_write_request_identity(
            operation=operation_name,
            operation_id=operation_id,
            request=request,
            principal=principal,
            captured=captured,
            project_id=project.pk,
            source_definition_id=None,
            target_definition_id=definition_id,
            if_match=if_match,
        )
        result = create_project_definition_draft_human_write(
            request_identity=request_identity,
            project=project,
            definition_id=definition_id,
            code=payload["code"],
            version=payload["version"],
            manifest=payload["manifest"],
            semantic_version=payload["semantic_version"],
            construct_version=payload["construct_version"],
            principal=principal,
        )
        return _human_write_response(
            result,
            fresh_payload=(
                _definition_payload(result.definition)
                if result.definition is not None
                else None
            ),
            fresh_status=HTTP_201_CREATED,
        )

    return _execute(operation)


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
        return _open_definition_payload(definition)

    response = _execute(operation)
    if response.status_code == HTTP_200_OK:
        return _with_etag(response, str(response.data["manifest_hash"]))
    return response


@_publication_readiness_cache_boundary
@_get_only_http_boundary
@api_view(["GET"])
@authentication_classes(_VALIDATION_PREVIEW_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def open_publication_readiness(
    request: Request,
    definition_id: object,
) -> Response:
    def operation() -> HttpResponse:
        current_user = _current_publication_user(request)
        admitted_definition = _definition_or_404(current_user, definition_id)
        principal = _current_publication_principal(current_user)
        require_studio_capability(principal, StudioCapability.DEFINITION_READ)
        _publication_readiness_admission(request)
        snapshot = publication_readiness_snapshot(
            definition_id=definition_id,
            scoped_project_id=admitted_definition.project_id,
        )
        return _publication_readiness_response(snapshot)

    return _execute(operation)


@_get_only_http_boundary
@api_view(["GET"])
@authentication_classes(_VALIDATION_PREVIEW_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def open_publication_result(
    request: Request,
    project_id: object,
    publication_id: object,
) -> Response:
    def operation() -> dict[str, Any]:
        project = _project_or_404(request.user, project_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_READ)
        try:
            publication = ProjectPublication.objects.select_related(
                "definition_version",
                "initial_workspace",
            ).get(
                pk=publication_id,
                project_id=project.pk,
            )
        except (ProjectPublication.DoesNotExist, ValueError) as exc:
            raise Http404("Publication result not found.") from exc
        return _publication_result_payload(publication)

    return _execute(operation)


@api_view(["POST"])
@authentication_classes(_HUMAN_WRITE_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def clone_definition(request: Request, definition_id: object) -> Response:
    def operation() -> Response:
        source = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_CLONE)
        operation_name = FoundationHumanWriteOperation.CLONE_DRAFT
        operation_id, if_match, captured, payload = _human_write_admission(
            request,
            operation=operation_name,
            allow_if_match=True,
        )
        if (
            set(payload) != {"id", "code", "version"}
            or any(
                not isinstance(payload[field], str)
                for field in ("id", "code", "version")
            )
        ):
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        successor_id = _canonical_entity_uuid(payload["id"])
        request_identity = _human_write_request_identity(
            operation=operation_name,
            operation_id=operation_id,
            request=request,
            principal=principal,
            captured=captured,
            project_id=source.project_id,
            source_definition_id=source.pk,
            target_definition_id=successor_id,
            if_match=if_match,
        )
        result = clone_project_definition_draft_human_write(
            request_identity=request_identity,
            source=source,
            definition_id=successor_id,
            code=payload["code"],
            version=payload["version"],
            expected_manifest_hash=if_match,
            principal=principal,
        )
        return _human_write_response(
            result,
            fresh_payload=(
                _definition_payload(result.definition)
                if result.definition is not None
                else None
            ),
            fresh_status=HTTP_201_CREATED,
        )

    return _execute(operation)


@api_view(["PUT"])
@authentication_classes(_HUMAN_WRITE_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def save_definition_draft(request: Request, definition_id: object) -> Response:
    def operation() -> Response:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_SAVE)
        operation_name = FoundationHumanWriteOperation.SAVE_DRAFT
        operation_id, if_match, captured, payload = _human_write_admission(
            request,
            operation=operation_name,
            allow_if_match=True,
        )
        if set(payload) != {"manifest"} or not isinstance(
            payload["manifest"], Mapping
        ):
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        request_identity = _human_write_request_identity(
            operation=operation_name,
            operation_id=operation_id,
            request=request,
            principal=principal,
            captured=captured,
            project_id=definition.project_id,
            source_definition_id=None,
            target_definition_id=definition.pk,
            if_match=if_match,
        )
        result = save_project_definition_draft_human_write(
            request_identity=request_identity,
            definition=definition,
            manifest=payload["manifest"],
            expected_manifest_hash=if_match,
            principal=principal,
        )
        return _human_write_response(
            result,
            fresh_payload=(
                _definition_payload(result.definition)
                if result.definition is not None
                else None
            ),
            fresh_status=HTTP_200_OK,
        )

    return _execute(operation)


@_validation_preview_http_boundary
@api_view(["POST"])
@authentication_classes(_VALIDATION_PREVIEW_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def validation_preview(
    request: Request,
    definition_id: object,
) -> Response | HttpResponse:
    try:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_SAVE)
        if definition.publication_status != "DRAFT":
            raise FoundationStudioApplicationConflict(
                "DEFINITION_NOT_DRAFT",
                "Validation preview accepts an exact DRAFT definition only.",
            )
        _validation_preview_metadata_admission(request)
        captured = capture_http_json(request)
        document = read_http_json(request)
        payload = dict(document.value)
        if (
            set(payload) != {"manifest"}
            or not isinstance(payload["manifest"], Mapping)
            or _SPOOF_FIELDS.intersection(payload["manifest"])
        ):
            raise ValidationPreviewEnvelopeError(
                {"body": "Exactly one manifest object is required."}
            )
        _require_validation_preview_unicode_scalars(payload["manifest"])
        report = validate_project_definition_manifest_policy(
            payload["manifest"],
            project=definition.project,
        )
        return _validation_preview_response(
            definition=definition,
            manifest=payload["manifest"],
            request_sha256=captured.identity.sha256,
            request_byte_length=captured.identity.byte_length,
            report=report,
        )
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
        error, status = _error_payload(exc)
        return Response(error, status=status)


@api_view(["POST"])
@authentication_classes(_HUMAN_WRITE_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def validate_definition(request: Request, definition_id: object) -> Response:
    def operation() -> Response:
        definition = _definition_or_404(request.user, definition_id)
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DEFINITION_VALIDATE)
        operation_name = FoundationHumanWriteOperation.VALIDATE_DEFINITION
        operation_id, if_match, captured, payload = _human_write_admission(
            request,
            operation=operation_name,
            allow_if_match=True,
        )
        if payload:
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        request_identity = _human_write_request_identity(
            operation=operation_name,
            operation_id=operation_id,
            request=request,
            principal=principal,
            captured=captured,
            project_id=definition.project_id,
            source_definition_id=None,
            target_definition_id=definition.pk,
            if_match=if_match,
        )
        try:
            result = validate_project_definition_human_write(
                request_identity=request_identity,
                definition=definition,
                expected_manifest_hash=if_match,
                principal=principal,
            )
        except FoundationHumanWriteError as exc:
            if (
                exc.error_code != "DEFINITION_VALIDATION_FAILED"
                or not isinstance(exc.report, Mapping)
            ):
                raise
            return Response(
                {
                    "code": exc.error_code,
                    "validation": _validation_report_projection(
                        definition=definition,
                        manifest=definition.manifest,
                        request_sha256=captured.identity.sha256,
                        request_byte_length=captured.identity.byte_length,
                        report=exc.report,
                    ),
                },
                status=HTTP_400_BAD_REQUEST,
            )
        return _human_write_response(
            result,
            fresh_payload=(
                _definition_payload(result.definition)
                if result.definition is not None
                else None
            ),
            fresh_status=HTTP_200_OK,
        )

    return _execute(operation)


@_post_only_http_boundary
@api_view(["POST"])
@authentication_classes(_PUBLICATION_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def publish_initial_definition(request: Request, definition_id: object) -> Response:
    def operation() -> HttpResponse:
        current_user = _current_publication_user(request)
        definition = _definition_or_404(current_user, definition_id)
        principal = _current_publication_principal(current_user)
        require_studio_capability(principal, StudioCapability.DEFINITION_VALIDATE)
        require_studio_capability(principal, StudioCapability.DEFINITION_PUBLISH)
        operation_id, expected_hash, locale, workspace, request_hash = _publication_admission(
            request, definition=definition, principal=principal, operation_kind="INITIAL"
        )
        result = reconcile_publication_operation(
            definition=definition, operation_id=operation_id,
            request_sha256=request_hash, operation_kind="INITIAL",
            principal=principal, locale=locale, workspace_spec=workspace,
            expected_manifest_hash=expected_hash,
        )
        return _publication_operation_response(
            result.publication, replayed=result.replayed,
            status=HTTP_200_OK if result.replayed else HTTP_201_CREATED,
        )

    return _execute_publication(operation)


@_post_only_http_boundary
@api_view(["POST"])
@authentication_classes(_PUBLICATION_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def publish_successor_definition(request: Request, definition_id: object) -> Response:
    def operation() -> HttpResponse:
        current_user = _current_publication_user(request)
        definition = _definition_or_404(current_user, definition_id)
        principal = _current_publication_principal(current_user)
        require_studio_capability(principal, StudioCapability.DEFINITION_PUBLISH)
        operation_id, expected_hash, locale, _, request_hash = _publication_admission(
            request, definition=definition, principal=principal, operation_kind="SUCCESSOR"
        )
        result = reconcile_publication_operation(
            definition=definition, operation_id=operation_id,
            request_sha256=request_hash, operation_kind="SUCCESSOR",
            principal=principal, locale=locale, workspace_spec=None,
            expected_manifest_hash=expected_hash,
        )
        return _publication_operation_response(
            result.publication, replayed=result.replayed,
            status=HTTP_200_OK if result.replayed else HTTP_201_CREATED,
        )

    return _execute_publication(operation)


@_get_only_http_boundary
@api_view(["GET"])
@authentication_classes(_PUBLICATION_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def open_publication_operation(
    request: Request, project_id: object, operation_id: object
) -> Response:
    def operation() -> HttpResponse:
        current_user = _current_publication_user(request)
        project = _project_or_404(current_user, project_id)
        principal = _current_publication_principal(current_user)
        require_studio_capability(principal, StudioCapability.DEFINITION_READ)
        _publication_recovery_admission(request)
        publication = find_publication_operation(
            project=project,
            operation_id=operation_id,
        )
        if publication is None:
            raise Http404("Publication operation not found.")
        return _publication_operation_response(
            publication,
            replayed=True,
            status=HTTP_200_OK,
            recovery_cache_barrier=True,
        )

    return _execute_publication(operation)


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
@authentication_classes(_HUMAN_WRITE_AUTHENTICATION)
@permission_classes([IsAuthenticated])
def bootstrap_first_definition_draft(request: Request) -> Response:
    def operation() -> Response:
        principal = _principal(request)
        require_studio_capability(principal, StudioCapability.DRAFT_CREATE)
        operation_name = FoundationHumanWriteOperation.BOOTSTRAP_DRAFT
        operation_id, if_match, captured, payload = _human_write_admission(
            request,
            operation=operation_name,
            allow_if_match=False,
        )
        if "project_primary_language" not in payload:
            raise FoundationHumanWriteAdmissionError(
                "PROJECT_PRIMARY_LANGUAGE_REQUIRED"
            )
        if set(payload) != {
            "project_primary_language",
            "project",
            "definition",
        }:
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
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
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        if not isinstance(definition, Mapping) or set(definition) != definition_keys:
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        for section, string_fields in (
            (
                project,
                ("id", "code", "version", "name", "description"),
            ),
            (
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
                    raise FoundationHumanWriteAdmissionError(
                        "AUTHORING_ENVELOPE_INVALID"
                    )
        if not isinstance(project["metadata"], Mapping):
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        if not isinstance(definition["manifest"], Mapping):
            raise FoundationHumanWriteAdmissionError("AUTHORING_ENVELOPE_INVALID")
        try:
            (
                project_primary_language,
                canonical_envelope_sha256,
            ) = canonical_bootstrap_envelope_identity(payload)
        except (LanguageTagValidationError, ValidationError, TypeError) as exc:
            language_error_codes = {
                "required": "PROJECT_PRIMARY_LANGUAGE_REQUIRED",
                "und_forbidden": "PROJECT_PRIMARY_LANGUAGE_UND_FORBIDDEN",
            }
            error_code = (
                language_error_codes.get(
                    exc.code,
                    "PROJECT_PRIMARY_LANGUAGE_INVALID",
                )
                if isinstance(exc, LanguageTagValidationError)
                else "PROJECT_PRIMARY_LANGUAGE_INVALID"
            )
            raise FoundationHumanWriteAdmissionError(error_code) from exc
        project_id = _canonical_entity_uuid(project["id"])
        definition_id = _canonical_entity_uuid(definition["id"])
        request_identity = _human_write_request_identity(
            operation=operation_name,
            operation_id=operation_id,
            request=request,
            principal=principal,
            captured=captured,
            project_id=project_id,
            source_definition_id=None,
            target_definition_id=definition_id,
            if_match=if_match,
            canonical_envelope_sha256=canonical_envelope_sha256,
            project_primary_language=project_primary_language,
        )
        result = bootstrap_project_definition_draft_human_write(
            request_identity=request_identity,
            project_id=project_id,
            project_code=project["code"],
            project_version=project["version"],
            project_name=project["name"],
            project_description=project["description"],
            project_metadata=project["metadata"],
            project_primary_language=project_primary_language,
            definition_id=definition_id,
            definition_code=definition["code"],
            definition_version=definition["version"],
            manifest=definition["manifest"],
            semantic_version=definition["semantic_version"],
            construct_version=definition["construct_version"],
            principal=principal,
            user=request.user,
        )
        fresh_payload = None
        if (
            result.project is not None
            and result.definition is not None
            and result.scope_group is not None
        ):
            fresh_payload = {
                "project": {
                    "id": str(result.project.pk),
                    "code": result.project.code,
                    "version": result.project.version,
                    "name": result.project.name,
                    "description": result.project.description,
                    "metadata": result.project.metadata,
                    "primary_language_tag": result.project.primary_language_tag,
                    "primary_language_assignment": (
                        result.project.primary_language_assignment
                    ),
                },
                "definition": _definition_payload(result.definition),
                "object_scope_group": result.scope_group.name,
                "audit_event_id": str(result.audit_event.pk),
            }
        return _human_write_response(
            result,
            fresh_payload=fresh_payload,
            fresh_status=HTTP_201_CREATED,
        )

    return _execute(operation)


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
