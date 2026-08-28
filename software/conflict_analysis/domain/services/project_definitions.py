"""Typed project-definition manifest and DRAFT authoring boundary.

This module is the only Studio-facing representation of a project definition.
It deliberately persists through :class:`ProjectDefinitionVersion.manifest`;
there are no Studio-local actor, element, parameter, or help-binding tables.

The V1 canonicalizer is opt-in: callers must present the exact typed envelope.
Legacy dictionaries and Foundation 2.0 payloads therefore keep their historical
serialization and checksum behavior.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Protocol
from uuid import UUID

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker

from domain.enums import AuditAction, AuditActorType, AuditScope, PublicationStatus
from domain.models import (
    AuditEvent,
    Project,
    ProjectDefinitionVersion,
    ProjectPublication,
    _canonical_studio_write,
)
from domain.services.foundation_packages import RawJSONError, parse_json_source


PROJECT_DEFINITION_MANIFEST_FORMAT: Final = "conflict-analysis-project-definition"
PROJECT_DEFINITION_MANIFEST_VERSION: Final = "1.0.0"
PROJECT_DEFINITION_MANIFEST_SCHEMA_ID: Final = (
    "https://conflictology.invalid/schemas/"
    "project-definition-manifest-1.0.0.schema.json"
)
PROJECT_DEFINITION_VALIDATION_CONTRACT: Final = (
    "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1"
)
PROJECT_ACCESS_GROUP_PREFIX: Final = "studio-project:"
FOUNDATION_HUMAN_WRITE_REQUEST_CONTRACT: Final = (
    "FOUNDATION_HUMAN_WRITE_REQUEST_IDENTITY_V1"
)
FOUNDATION_HUMAN_WRITE_RECEIPT_CONTRACT: Final = (
    "FOUNDATION_AUDITED_DEFINITION_WRITE_V1"
)
FOUNDATION_HUMAN_WRITE_RECEIPT_VERSION: Final = "1.0.0"
FOUNDATION_HUMAN_OPERATION_AUDIT_KEY: Final = "foundation_human_operation"

SCHEMA_PATH: Final = (
    Path(__file__).resolve().parent
    / "schemas"
    / "project-definition-manifest-1.0.0.schema.json"
)

with SCHEMA_PATH.open(encoding="utf-8") as _schema_file:
    PROJECT_DEFINITION_MANIFEST_JSON_SCHEMA = json.load(_schema_file)
Draft202012Validator.check_schema(PROJECT_DEFINITION_MANIFEST_JSON_SCHEMA)
_SCHEMA_VALIDATOR = Draft202012Validator(
    PROJECT_DEFINITION_MANIFEST_JSON_SCHEMA,
    format_checker=FormatChecker(),
)


MANIFEST_SECTIONS: Final = (
    "$schema",
    "format",
    "format_version",
    "project",
    "policies",
    "actors",
    "analytical_elements",
    "actor_element_roles",
    "parameter_definitions",
    "help_bindings",
)

_DIAGNOSTIC_LOCAL_SECTIONS: Final = MANIFEST_SECTIONS[3:]
_FORBIDDEN_KEYS: Final = frozenset(
    {
        "automatic_mean",
        "automatic_weights",
        "calculated_risk",
        "early_warning_score",
        "formula",
        "pow",
        "pow_sal",
        "prediction",
        "recommendation",
        "risk_score",
        "scalar_power",
        "total_power",
        "violence_probability",
    }
)
_DRAFT_BLOCKING_CODES: Final = frozenset(
    {
        "DUPLICATE_JSON_KEY",
        "FIELD_BLANK",
        "FIELD_REQUIRED",
        "FIELD_TYPE_INVALID",
        "FIELD_UNEXPECTED",
        "FIELD_VALUE_INVALID",
        "FORMAT_UNSUPPORTED",
        "JSON_INVALID",
        "PROJECT_IDENTITY_MISMATCH",
        "SCHEMA_VERSION_UNSUPPORTED",
        "UTF8_BOM_FORBIDDEN",
        "UTF8_INVALID",
        "FORBIDDEN_AGGREGATE_IDENTITY",
    }
)


class ProjectDefinitionManifestError(ValidationError):
    """The input is not an exact typed V1 manifest."""


class ProjectDefinitionDraftConflict(ValidationError):
    """Optimistic DRAFT save token does not match the stored manifest."""


class FoundationStudioApplicationConflict(ValidationError):
    """Stable, typed application conflict mapped to HTTP 409 by adapters."""

    def __init__(self, conflict_code: str, message: str) -> None:
        bounded_code = str(conflict_code).strip()
        if not bounded_code:
            raise ValueError("Foundation Studio conflict code must not be blank.")
        self.conflict_code = bounded_code
        super().__init__(
            {
                "conflict": ValidationError(
                    str(message),
                    code=bounded_code,
                )
            }
        )


class FoundationHumanWriteError(ValidationError):
    """Stable FD05 pre-commit error with an optional exact FD01 report."""

    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        report: Mapping[str, Any] | None = None,
    ) -> None:
        bounded_code = str(error_code).strip()
        if not bounded_code:
            raise ValueError("Foundation HUMAN write error code must not be blank.")
        self.error_code = bounded_code
        self.report = copy.deepcopy(dict(report)) if report is not None else None
        super().__init__(
            {
                "foundation_human_write": ValidationError(
                    str(message),
                    code=bounded_code,
                )
            }
        )


def project_access_group_name(project_id: object) -> str:
    """Return the sole derived object-scope group name for one Project."""

    return f"{PROJECT_ACCESS_GROUP_PREFIX}{UUID(str(project_id))}"


class HelpTopicReferenceResolver(Protocol):
    """Read-only exact HelpTopic lookup used during publish-grade validation."""

    def __call__(self, reference: Mapping[str, Any]) -> object | None: ...


@dataclass(frozen=True, slots=True)
class ProjectDefinitionManifestDiagnostic:
    """Stable machine-readable manifest diagnostic."""

    level: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "level": self.level,
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ProjectDefinitionManifestValidation:
    """Immutable validation result suitable for lifecycle audit storage."""

    valid: bool
    manifest_sha256: str
    diagnostics: tuple[ProjectDefinitionManifestDiagnostic, ...]
    contract: str = PROJECT_DEFINITION_VALIDATION_CONTRACT
    schema_id: str = PROJECT_DEFINITION_MANIFEST_SCHEMA_ID
    schema_version: str = PROJECT_DEFINITION_MANIFEST_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": self.contract,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "manifest_sha256": self.manifest_sha256,
            "valid": self.valid,
            "diagnostics": [diagnostic.as_dict() for diagnostic in self.diagnostics],
        }


@dataclass(frozen=True, slots=True)
class ProjectDefinitionManifestV1:
    """Deeply immutable typed DTO over the sole manifest authority."""

    manifest: Mapping[str, Any]
    canonical_json: str
    manifest_sha256: str
    validation: ProjectDefinitionManifestValidation

    def as_dict(self) -> dict[str, Any]:
        return _deep_thaw(self.manifest)


@dataclass(frozen=True, slots=True)
class ProjectDefinitionDraftBootstrapResult:
    """Exact rows created by the atomic first-Project application service."""

    project: Project
    scope_group: Group
    definition: ProjectDefinitionVersion
    audit_event: AuditEvent


class FoundationHumanWriteOperation(StrEnum):
    BOOTSTRAP_DRAFT = "BOOTSTRAP_DRAFT"
    CREATE_DRAFT = "CREATE_DRAFT"
    CLONE_DRAFT = "CLONE_DRAFT"
    SAVE_DRAFT = "SAVE_DRAFT"
    VALIDATE_DEFINITION = "VALIDATE_DEFINITION"


_HUMAN_WRITE_METHODS: Final = MappingProxyType(
    {
        FoundationHumanWriteOperation.BOOTSTRAP_DRAFT: "POST",
        FoundationHumanWriteOperation.CREATE_DRAFT: "POST",
        FoundationHumanWriteOperation.CLONE_DRAFT: "POST",
        FoundationHumanWriteOperation.SAVE_DRAFT: "PUT",
        FoundationHumanWriteOperation.VALIDATE_DEFINITION: "POST",
    }
)
_HUMAN_WRITE_ACTIONS: Final = MappingProxyType(
    {
        FoundationHumanWriteOperation.BOOTSTRAP_DRAFT: AuditAction.CREATE,
        FoundationHumanWriteOperation.CREATE_DRAFT: AuditAction.CREATE,
        FoundationHumanWriteOperation.CLONE_DRAFT: AuditAction.CREATE,
        FoundationHumanWriteOperation.SAVE_DRAFT: AuditAction.UPDATE,
        FoundationHumanWriteOperation.VALIDATE_DEFINITION: AuditAction.VALIDATE,
    }
)
_HUMAN_WRITE_HTTP_STATUSES: Final = MappingProxyType(
    {
        FoundationHumanWriteOperation.BOOTSTRAP_DRAFT: 201,
        FoundationHumanWriteOperation.CREATE_DRAFT: 201,
        FoundationHumanWriteOperation.CLONE_DRAFT: 201,
        FoundationHumanWriteOperation.SAVE_DRAFT: 200,
        FoundationHumanWriteOperation.VALIDATE_DEFINITION: 200,
    }
)
_HUMAN_WRITE_RECEIPT_KEYS: Final = frozenset(
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
_HUMAN_WRITE_REQUEST_KEYS: Final = frozenset(
    {
        "contract",
        "sha256",
        "raw_input_sha256",
        "raw_input_byte_length",
        "if_match",
    }
)
_DEFINITION_RECEIPT_IDENTITY_KEYS: Final = frozenset(
    {
        "contract",
        "id",
        "project_id",
        "code",
        "version",
        "publication_status",
        "manifest_hash",
        "schema_version",
        "semantic_version",
        "construct_version",
        "supersedes_id",
        "validated_at",
        "validated_by",
        "validation_result_sha256",
    }
)


def _exact_uuid(value: object, *, label: str, version: int | None = None) -> UUID:
    try:
        resolved = UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError({label: f"{label} must be a canonical UUID."}) from exc
    if str(resolved) != str(value) or (version is not None and resolved.version != version):
        suffix = f"v{version}" if version is not None else "UUID"
        raise ValidationError({label: f"{label} must be a canonical lowercase {suffix}."})
    return resolved


def _exact_sha256(value: object, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValidationError({label: f"{label} must be a lowercase SHA-256 digest."})
    return value


def _canonical_identity_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class FoundationHumanWriteRequestIdentity:
    """Server-built immutable correlation identity for one exact HTTP intent."""

    operation_id: UUID
    operation: FoundationHumanWriteOperation
    method: str
    route: str
    actor_identifier: str
    project_id: UUID
    source_definition_id: UUID | None
    target_definition_id: UUID | None
    content_type: str
    raw_input_sha256: str
    raw_input_byte_length: int
    if_match: str | None
    sha256: str

    @classmethod
    def build(
        cls,
        *,
        operation: FoundationHumanWriteOperation | str,
        operation_id: UUID | str,
        method: str,
        route: str,
        actor_identifier: str,
        project_id: UUID | str,
        source_definition_id: UUID | str | None,
        target_definition_id: UUID | str | None,
        content_type: str,
        raw_input_sha256: str,
        raw_input_byte_length: int,
        if_match: str | None,
    ) -> "FoundationHumanWriteRequestIdentity":
        resolved_operation = FoundationHumanWriteOperation(operation)
        resolved_operation_id = _exact_uuid(
            operation_id,
            label="operation_id",
            version=4,
        )
        resolved_method = str(method)
        if resolved_method != _HUMAN_WRITE_METHODS[resolved_operation]:
            raise ValidationError(
                {"method": "HTTP method does not match the Foundation write operation."}
            )
        if (
            not isinstance(route, str)
            or not route.startswith("/")
            or "?" in route
            or "#" in route
        ):
            raise ValidationError({"route": "A normalized absolute route is required."})
        actor_pk = (
            actor_identifier.removeprefix("django-user:")
            if isinstance(actor_identifier, str)
            else ""
        )
        if (
            not isinstance(actor_identifier, str)
            or not actor_identifier.startswith("django-user:")
            or not actor_pk.isdigit()
            or actor_pk == "0"
            or actor_pk.startswith("0")
        ):
            raise ValidationError(
                {"actor_identifier": "A persisted django-user HUMAN identity is required."}
            )
        resolved_project_id = _exact_uuid(project_id, label="project_id")
        source_id = (
            _exact_uuid(source_definition_id, label="source_definition_id")
            if source_definition_id is not None
            else None
        )
        target_id = (
            _exact_uuid(target_definition_id, label="target_definition_id")
            if target_definition_id is not None
            else None
        )
        if content_type != "application/json":
            raise ValidationError(
                {"content_type": "Normalized content type must be application/json."}
            )
        raw_sha256 = _exact_sha256(raw_input_sha256, label="raw_input_sha256")
        if (
            isinstance(raw_input_byte_length, bool)
            or not isinstance(raw_input_byte_length, int)
            or raw_input_byte_length < 0
        ):
            raise ValidationError(
                {"raw_input_byte_length": "Raw input byte length must be non-negative."}
            )
        if if_match is not None:
            if_match = _exact_sha256(if_match, label="if_match")
        if resolved_operation in {
            FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
            FoundationHumanWriteOperation.CREATE_DRAFT,
        }:
            if if_match is not None or source_id is not None or target_id is None:
                raise ValidationError(
                    {"request_identity": "Create operations require only a target UUID."}
                )
        elif resolved_operation is FoundationHumanWriteOperation.CLONE_DRAFT:
            if if_match is None or source_id is None or target_id is None:
                raise ValidationError(
                    {"request_identity": "Clone requires source, target and If-Match."}
                )
        elif source_id is not None or target_id is None or if_match is None:
            raise ValidationError(
                {"request_identity": "Target mutation requires target and If-Match."}
            )
        intent = {
            "contract": FOUNDATION_HUMAN_WRITE_REQUEST_CONTRACT,
            "operation_id": str(resolved_operation_id),
            "operation": resolved_operation.value,
            "method": resolved_method,
            "normalized_route": route,
            "actor_identifier": actor_identifier,
            "project_id": str(resolved_project_id),
            "source_definition_id": str(source_id) if source_id is not None else None,
            "target_definition_id": str(target_id) if target_id is not None else None,
            "normalized_content_type": content_type,
            "raw_input_sha256": raw_sha256,
            "raw_input_byte_length": raw_input_byte_length,
            "if_match": if_match,
        }
        return cls(
            operation_id=resolved_operation_id,
            operation=resolved_operation,
            method=resolved_method,
            route=route,
            actor_identifier=actor_identifier,
            project_id=resolved_project_id,
            source_definition_id=source_id,
            target_definition_id=target_id,
            content_type=content_type,
            raw_input_sha256=raw_sha256,
            raw_input_byte_length=raw_input_byte_length,
            if_match=if_match,
            sha256=_canonical_identity_sha256(intent),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": FOUNDATION_HUMAN_WRITE_REQUEST_CONTRACT,
            "sha256": self.sha256,
            "raw_input_sha256": self.raw_input_sha256,
            "raw_input_byte_length": self.raw_input_byte_length,
            "if_match": self.if_match,
        }


@dataclass(frozen=True, slots=True)
class FoundationHumanWriteReceipt:
    operation: FoundationHumanWriteOperation
    operation_id: UUID
    audit_action: str
    actor_identifier: str
    project_id: UUID
    source_definition: Mapping[str, Any] | None
    before_definition: Mapping[str, Any] | None
    after_definition: Mapping[str, Any]
    bootstrap_result: Mapping[str, Any] | None
    validation: Mapping[str, Any] | None
    request: Mapping[str, Any]
    occurred_at: str
    original_http_status: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract": FOUNDATION_HUMAN_WRITE_RECEIPT_CONTRACT,
            "version": FOUNDATION_HUMAN_WRITE_RECEIPT_VERSION,
            "operation": self.operation.value,
            "operation_id": str(self.operation_id),
            "audit_event_id": str(self.operation_id),
            "audit_action": self.audit_action,
            "actor_type": AuditActorType.HUMAN,
            "actor_identifier": self.actor_identifier,
            "project_id": str(self.project_id),
            "source_definition": copy.deepcopy(
                dict(self.source_definition) if self.source_definition is not None else None
            ),
            "before_definition": copy.deepcopy(
                dict(self.before_definition) if self.before_definition is not None else None
            ),
            "after_definition": copy.deepcopy(dict(self.after_definition)),
            "bootstrap_result": copy.deepcopy(
                dict(self.bootstrap_result) if self.bootstrap_result is not None else None
            ),
            "validation": copy.deepcopy(
                dict(self.validation) if self.validation is not None else None
            ),
            "request": copy.deepcopy(dict(self.request)),
            "occurred_at": self.occurred_at,
            "original_http_status": self.original_http_status,
        }

    @property
    def sha256(self) -> str:
        return _canonical_identity_sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class FoundationHumanWriteResult:
    audit_event: AuditEvent
    receipt: FoundationHumanWriteReceipt
    replayed: bool
    definition: ProjectDefinitionVersion | None = None
    project: Project | None = None
    scope_group: Group | None = None


class _DecodeFailure(Exception):
    def __init__(self, code: str, path: str, message: str):
        super().__init__(message)
        self.code = code
        self.path = path
        self.message = message


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _deep_freeze(item) for key, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return copy.deepcopy(value)


def _normalize_jsonb_negative_zero(value: Any) -> Any:
    """Match PostgreSQL JSONB's sole sign-losing numeric edge before hashing."""

    if (
        isinstance(value, float)
        and value == 0.0
        and math.copysign(1.0, value) < 0
    ):
        return 0.0
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_jsonb_negative_zero(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_normalize_jsonb_negative_zero(item) for item in value]
    return value


def _decode_manifest(raw: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    try:
        return dict(_normalize_jsonb_negative_zero(parse_json_source(raw).value))
    except RawJSONError as exc:
        code = {
            "RAW_JSON_BOM_FORBIDDEN": "UTF8_BOM_FORBIDDEN",
            "RAW_JSON_INVALID_UTF8": "UTF8_INVALID",
            "RAW_JSON_DUPLICATE_KEY": "DUPLICATE_JSON_KEY",
            "RAW_JSON_OBJECT_REQUIRED": "FIELD_TYPE_INVALID",
            "RAW_JSON_INPUT_UNSUPPORTED": "FIELD_TYPE_INVALID",
            "RAW_JSON_NON_FINITE_NUMBER": "FIELD_TYPE_INVALID",
            "RAW_JSON_MAPPING_NOT_SERIALIZABLE": "FIELD_TYPE_INVALID",
        }.get(exc.code, "JSON_INVALID")
        raise _DecodeFailure(code, "/", exc.message) from exc


def identify_typed_project_definition_manifest(value: object) -> bool:
    """Return true only for the exact V1 envelope; never guess legacy input."""

    return bool(
        isinstance(value, Mapping)
        and value.get("$schema") == PROJECT_DEFINITION_MANIFEST_SCHEMA_ID
        and value.get("format") == PROJECT_DEFINITION_MANIFEST_FORMAT
        and value.get("format_version") == PROJECT_DEFINITION_MANIFEST_VERSION
    )


def _canonical_json(manifest: Mapping[str, Any]) -> str:
    return json.dumps(
        _deep_thaw(manifest),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _pointer(parts: Sequence[object]) -> str:
    if not parts:
        return "/"
    escaped = [str(part).replace("~", "~0").replace("/", "~1") for part in parts]
    return "/" + "/".join(escaped)


def _deduplicate_diagnostics(
    diagnostics: Sequence[ProjectDefinitionManifestDiagnostic],
) -> tuple[ProjectDefinitionManifestDiagnostic, ...]:
    ordered: list[ProjectDefinitionManifestDiagnostic] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in diagnostics:
        identity = (item.level, item.code, item.path, item.message)
        if identity in seen:
            continue
        seen.add(identity)
        ordered.append(item)
    return tuple(ordered)


def _diagnostic_local_section(
    diagnostic: ProjectDefinitionManifestDiagnostic,
) -> str | None:
    if diagnostic.path == "/":
        return None
    raw = diagnostic.path.lstrip("/").split("/", 1)[0]
    section = raw.replace("~1", "/").replace("~0", "~")
    if section in _DIAGNOSTIC_LOCAL_SECTIONS:
        return section
    return None


def _section_ordered_diagnostics(
    passes: Sequence[Sequence[ProjectDefinitionManifestDiagnostic]],
) -> list[ProjectDefinitionManifestDiagnostic]:
    """Keep validation-pass order inside each authoritative manifest section."""

    ordered: list[ProjectDefinitionManifestDiagnostic] = []
    for section in (None, *_DIAGNOSTIC_LOCAL_SECTIONS):
        for diagnostic_pass in passes:
            ordered.extend(
                diagnostic
                for diagnostic in diagnostic_pass
                if _diagnostic_local_section(diagnostic) == section
            )
    return ordered


def _diagnostic(code: str, path: str, message: str) -> ProjectDefinitionManifestDiagnostic:
    return ProjectDefinitionManifestDiagnostic(
        level="ERROR",
        code=code,
        path=path,
        message=message,
    )


def _envelope_diagnostics(manifest: Mapping[str, Any]) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    if manifest.get("$schema") != PROJECT_DEFINITION_MANIFEST_SCHEMA_ID:
        diagnostics.append(
            _diagnostic(
                "SCHEMA_VERSION_UNSUPPORTED",
                "/$schema",
                f"$schema must equal {PROJECT_DEFINITION_MANIFEST_SCHEMA_ID!r}.",
            )
        )
    if manifest.get("format") != PROJECT_DEFINITION_MANIFEST_FORMAT:
        diagnostics.append(
            _diagnostic(
                "FORMAT_UNSUPPORTED",
                "/format",
                f"format must equal {PROJECT_DEFINITION_MANIFEST_FORMAT!r}.",
            )
        )
    if manifest.get("format_version") != PROJECT_DEFINITION_MANIFEST_VERSION:
        diagnostics.append(
            _diagnostic(
                "SCHEMA_VERSION_UNSUPPORTED",
                "/format_version",
                f"format_version must equal {PROJECT_DEFINITION_MANIFEST_VERSION!r}.",
            )
        )
    return diagnostics


def _schema_diagnostics(manifest: Mapping[str, Any]) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    for error in _SCHEMA_VALIDATOR.iter_errors(manifest):
        path_parts = tuple(error.absolute_path)
        path = _pointer(path_parts)
        if error.validator == "required":
            missing = [
                field for field in error.validator_value if field not in error.instance
            ]
            for field in missing:
                diagnostics.append(
                    _diagnostic(
                        "FIELD_REQUIRED",
                        _pointer((*path_parts, field)),
                        f"Required field {field!r} is missing.",
                    )
                )
        elif error.validator == "additionalProperties":
            allowed = set(error.schema.get("properties", {}))
            unexpected = sorted(set(error.instance) - allowed)
            if unexpected:
                diagnostics.append(
                    _diagnostic(
                        "FIELD_UNEXPECTED",
                        _pointer((*path_parts, "*")),
                        "Object contains a field outside the typed manifest contract.",
                    )
                )
        elif error.validator == "type":
            diagnostics.append(
                _diagnostic(
                    "FIELD_TYPE_INVALID",
                    path,
                    "Field has the wrong JSON type.",
                )
            )
        elif error.validator == "minLength" and isinstance(error.instance, str):
            diagnostics.append(
                _diagnostic("FIELD_BLANK", path, "Field must not be blank.")
            )
        elif error.validator == "const":
            if path == "/format":
                code = "FORMAT_UNSUPPORTED"
            elif path in {"/$schema", "/format_version"}:
                code = "SCHEMA_VERSION_UNSUPPORTED"
            else:
                code = "FIELD_VALUE_INVALID"
            diagnostics.append(
                _diagnostic(code, path, "Field does not match the required contract value.")
            )
        else:
            diagnostics.append(
                _diagnostic(
                    "FIELD_VALUE_INVALID",
                    path,
                    "Field value does not satisfy the typed manifest contract.",
                )
            )
    return diagnostics


def _walk_forbidden_keys(
    value: Any,
    *,
    parts: tuple[object, ...] = (),
) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    if isinstance(value, Mapping):
        for key in sorted(value, key=lambda item: str(item)):
            item = value[key]
            normalized = str(key).strip().lower().replace("×", "_").replace("*", "_")
            normalized = normalized.replace("-", "_").replace(" ", "_")
            if normalized in _FORBIDDEN_KEYS:
                diagnostics.append(
                    _diagnostic(
                        "FORBIDDEN_AGGREGATE_IDENTITY",
                        _pointer((*parts, key)),
                        "Calculated aggregate, prediction, risk, and recommendation fields are forbidden.",
                    )
                )
            diagnostics.extend(_walk_forbidden_keys(item, parts=(*parts, key)))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            diagnostics.extend(_walk_forbidden_keys(item, parts=(*parts, index)))
    return diagnostics


def _project_identity_diagnostics(
    manifest: Mapping[str, Any],
    project: Project | None,
) -> list[ProjectDefinitionManifestDiagnostic]:
    if project is None or not isinstance(manifest.get("project"), Mapping):
        return []
    project_manifest = manifest["project"]
    expected = {
        "id": str(project.pk),
        "code": project.code,
        "version": project.version,
    }
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    for field, expected_value in expected.items():
        if project_manifest.get(field) != expected_value:
            diagnostics.append(
                _diagnostic(
                    "PROJECT_IDENTITY_MISMATCH",
                    f"/project/{field}",
                    f"Manifest project.{field} must match the persisted Project exactly.",
                )
            )
    return diagnostics


def _items(manifest: Mapping[str, Any], section: str) -> list[Mapping[str, Any]]:
    value = manifest.get(section)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _identity_diagnostics(manifest: Mapping[str, Any]) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    globally_seen_ids: dict[str, tuple[str, int]] = {}
    for section in (
        "actors",
        "analytical_elements",
        "actor_element_roles",
        "parameter_definitions",
        "help_bindings",
    ):
        seen_codes: dict[str, int] = {}
        for index, item in enumerate(_items(manifest, section)):
            stable_id = item.get("id")
            code = item.get("code")
            if isinstance(stable_id, str):
                previous = globally_seen_ids.get(stable_id)
                if previous is not None:
                    diagnostics.append(
                        _diagnostic(
                            "ID_DUPLICATE",
                            f"/{section}/{index}/id",
                            f"Stable id duplicates /{previous[0]}/{previous[1]}/id.",
                        )
                    )
                else:
                    globally_seen_ids[stable_id] = (section, index)
            if isinstance(code, str):
                previous_index = seen_codes.get(code)
                if previous_index is not None:
                    diagnostics.append(
                        _diagnostic(
                            "CODE_DUPLICATE",
                            f"/{section}/{index}/code",
                            f"Code duplicates /{section}/{previous_index}/code.",
                        )
                    )
                else:
                    seen_codes[code] = index
    return diagnostics


def _hierarchy_diagnostics(
    manifest: Mapping[str, Any], section: str
) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    items = _items(manifest, section)
    index_by_id = {
        str(item["id"]): index
        for index, item in enumerate(items)
        if isinstance(item.get("id"), str)
    }
    parent_by_id: dict[str, str] = {}
    orders: dict[tuple[str | None, int], int] = {}
    for index, item in enumerate(items):
        stable_id = item.get("id")
        parent_id = item.get("parent_id")
        order = item.get("order")
        if isinstance(stable_id, str) and isinstance(parent_id, str):
            if parent_id == stable_id:
                diagnostics.append(
                    _diagnostic(
                        "SELF_PARENT_REFERENCE",
                        f"/{section}/{index}/parent_id",
                        "An item cannot be its own parent.",
                    )
                )
            elif parent_id not in index_by_id:
                diagnostics.append(
                    _diagnostic(
                        "BROKEN_PARENT_REFERENCE",
                        f"/{section}/{index}/parent_id",
                        f"parent_id does not reference an item in {section}.",
                    )
                )
            else:
                parent_by_id[stable_id] = parent_id
        if isinstance(order, int) and not isinstance(order, bool):
            key = (parent_id if isinstance(parent_id, str) else None, order)
            previous_index = orders.get(key)
            if previous_index is not None:
                diagnostics.append(
                    _diagnostic(
                        "ORDER_DUPLICATE",
                        f"/{section}/{index}/order",
                        f"Sibling order duplicates /{section}/{previous_index}/order.",
                    )
                )
            else:
                orders[key] = index

    cyclic_ids: set[str] = set()
    for stable_id in index_by_id:
        chain: list[str] = []
        positions: dict[str, int] = {}
        current = stable_id
        while current in parent_by_id:
            if current in positions:
                cyclic_ids.update(chain[positions[current] :])
                break
            positions[current] = len(chain)
            chain.append(current)
            current = parent_by_id[current]
    for stable_id in sorted(cyclic_ids, key=lambda value: index_by_id[value]):
        diagnostics.append(
            _diagnostic(
                "HIERARCHY_CYCLE",
                f"/{section}/{index_by_id[stable_id]}/parent_id",
                f"{section} hierarchy contains a cycle.",
            )
        )
    return diagnostics


def _cross_reference_diagnostics(
    manifest: Mapping[str, Any],
) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    actor_ids = {str(item.get("id")) for item in _items(manifest, "actors")}
    element_ids = {
        str(item.get("id")) for item in _items(manifest, "analytical_elements")
    }
    role_ids = {
        str(item.get("id")) for item in _items(manifest, "actor_element_roles")
    }
    seen_roles: dict[tuple[object, object, object], int] = {}
    for index, item in enumerate(_items(manifest, "actor_element_roles")):
        for field, valid_ids in (
            ("actor_id", actor_ids),
            ("element_id", element_ids),
        ):
            value = item.get(field)
            if isinstance(value, str) and value not in valid_ids:
                diagnostics.append(
                    _diagnostic(
                        "BROKEN_CROSS_REFERENCE",
                        f"/actor_element_roles/{index}/{field}",
                        f"{field} does not reference the required manifest section.",
                    )
                )
        key = (item.get("actor_id"), item.get("element_id"), item.get("role"))
        previous_index = seen_roles.get(key)
        if previous_index is not None:
            diagnostics.append(
                _diagnostic(
                    "CROSS_REFERENCE_DUPLICATE",
                    f"/actor_element_roles/{index}",
                    f"Actor-element role duplicates /actor_element_roles/{previous_index}.",
                )
            )
        else:
            seen_roles[key] = index

    for index, item in enumerate(_items(manifest, "parameter_definitions")):
        applicability = item.get("applicability")
        if not isinstance(applicability, Mapping):
            continue
        for field, valid_ids in (
            ("actor_ids", actor_ids),
            ("analytical_element_ids", element_ids),
            ("actor_element_role_ids", role_ids),
        ):
            values = applicability.get(field)
            if not isinstance(values, list):
                continue
            seen_values: set[str] = set()
            for value_index, value in enumerate(values):
                if not isinstance(value, str):
                    continue
                path = f"/parameter_definitions/{index}/applicability/{field}/{value_index}"
                if value in seen_values:
                    diagnostics.append(
                        _diagnostic(
                            "APPLICABILITY_INVALID",
                            path,
                            "Applicability reference is duplicated.",
                        )
                    )
                elif value not in valid_ids:
                    diagnostics.append(
                        _diagnostic(
                            "BROKEN_CROSS_REFERENCE",
                            path,
                            "Applicability reference does not resolve in this manifest.",
                        )
                    )
                seen_values.add(value)
    return diagnostics


def _scale_diagnostics(manifest: Mapping[str, Any]) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    for index, item in enumerate(_items(manifest, "parameter_definitions")):
        scale = item.get("scale")
        if not isinstance(scale, Mapping):
            continue
        parsed: dict[str, Decimal] = {}
        for field in ("minimum", "maximum", "step"):
            value = scale.get(field)
            if value is None:
                continue
            try:
                decimal = Decimal(value)
            except (InvalidOperation, TypeError, ValueError):
                diagnostics.append(
                    _diagnostic(
                        "SCALE_INVALID",
                        f"/parameter_definitions/{index}/scale/{field}",
                        "Scale values must be finite canonical decimal strings.",
                    )
                )
                continue
            if not decimal.is_finite():
                diagnostics.append(
                    _diagnostic(
                        "SCALE_INVALID",
                        f"/parameter_definitions/{index}/scale/{field}",
                        "Scale values must be finite canonical decimal strings.",
                    )
                )
            else:
                parsed[field] = decimal
        if "minimum" in parsed and "maximum" in parsed:
            if parsed["minimum"] > parsed["maximum"]:
                diagnostics.append(
                    _diagnostic(
                        "SCALE_INVALID",
                        f"/parameter_definitions/{index}/scale",
                        "Scale minimum must be less than or equal to maximum.",
                    )
                )
        if "step" in parsed and parsed["step"] <= 0:
            diagnostics.append(
                _diagnostic(
                    "SCALE_INVALID",
                    f"/parameter_definitions/{index}/scale/step",
                    "Scale step must be positive.",
                )
            )
    return diagnostics


def _content_diagnostics(manifest: Mapping[str, Any]) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    for path, value in (
        ("/project/name", manifest.get("project", {}).get("name") if isinstance(manifest.get("project"), Mapping) else None),
    ):
        if isinstance(value, str) and not value.strip():
            diagnostics.append(_diagnostic("FIELD_BLANK", path, "Field must not be blank."))
    for section in ("actors", "analytical_elements"):
        for index, item in enumerate(_items(manifest, section)):
            label = item.get("label")
            if isinstance(label, str) and not label.strip():
                diagnostics.append(
                    _diagnostic(
                        "FIELD_BLANK",
                        f"/{section}/{index}/label",
                        "Field must not be blank.",
                    )
                )
            if section == "analytical_elements":
                statement = item.get("reference_statement")
                if isinstance(statement, str) and not statement.strip():
                    diagnostics.append(
                        _diagnostic(
                            "REFERENCE_STATEMENT_REQUIRED",
                            f"/{section}/{index}/reference_statement",
                            "Analytical elements require a reference statement.",
                        )
                    )
    for index, item in enumerate(_items(manifest, "parameter_definitions")):
        statement = item.get("reference_statement")
        if isinstance(statement, str) and not statement.strip():
            diagnostics.append(
                _diagnostic(
                    "REFERENCE_STATEMENT_REQUIRED",
                    f"/parameter_definitions/{index}/reference_statement",
                    "Parameter definitions require a reference statement.",
                )
            )
        statuses = item.get("allowed_statuses")
        if isinstance(statuses, list):
            for status_index, status in enumerate(statuses):
                if status in statuses[:status_index]:
                    diagnostics.append(
                        _diagnostic(
                            "STATUS_INVALID",
                            f"/parameter_definitions/{index}/allowed_statuses/{status_index}",
                            "Allowed status is duplicated.",
                        )
                    )
    return diagnostics


def _help_diagnostics(
    manifest: Mapping[str, Any],
    resolver: HelpTopicReferenceResolver | None,
) -> list[ProjectDefinitionManifestDiagnostic]:
    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    seen: dict[tuple[object, object, object, object], int] = {}
    for index, item in enumerate(_items(manifest, "help_bindings")):
        if item.get("version") != item.get("topic_version"):
            diagnostics.append(
                _diagnostic(
                    "HELP_TOPIC_VERSION_MISMATCH",
                    f"/help_bindings/{index}/topic_version",
                    "Help binding version must equal the exact HelpTopic version.",
                )
            )
        key = (
            item.get("application_scope"),
            item.get("ui_key"),
            item.get("locale"),
            item.get("topic_version"),
        )
        previous_index = seen.get(key)
        if previous_index is not None:
            diagnostics.append(
                _diagnostic(
                    "HELP_BINDING_DUPLICATE",
                    f"/help_bindings/{index}",
                    f"Help binding duplicates /help_bindings/{previous_index}.",
                )
            )
        else:
            seen[key] = index
        if resolver is not None:
            try:
                topic = resolver(MappingProxyType(dict(item)))
            except (LookupError, ValidationError):
                topic = None
            if topic is None:
                diagnostics.append(
                    _diagnostic(
                        "HELP_TOPIC_UNAVAILABLE",
                        f"/help_bindings/{index}",
                        "The exact published, sanitized HelpTopic is unavailable.",
                    )
                )
                continue
            expected_stable_key = item.get("topic_stable_key")
            actual_stable_key = getattr(topic, "stable_key", None)
            if (
                isinstance(expected_stable_key, str)
                and actual_stable_key != expected_stable_key
            ):
                diagnostics.append(
                    _diagnostic(
                        "HELP_TOPIC_STABLE_KEY_MISMATCH",
                        f"/help_bindings/{index}/topic_stable_key",
                        "HelpTopic stable key does not match the exact manifest reference.",
                    )
                )
            expected_hash = item.get("topic_sha256")
            actual_hash = getattr(topic, "sanitized_html_hash", None)
            if actual_hash is None:
                actual_hash = getattr(topic, "content_hash", None)
            if actual_hash is None:
                actual_hash = getattr(topic, "content_sha256", None)
            if isinstance(expected_hash, str) and actual_hash != expected_hash:
                diagnostics.append(
                    _diagnostic(
                        "HELP_TOPIC_HASH_MISMATCH",
                        f"/help_bindings/{index}/topic_sha256",
                        "HelpTopic checksum does not match the exact manifest reference.",
                    )
                )
    return diagnostics


def validate_project_definition_manifest_v1(
    raw: Mapping[str, Any] | str | bytes,
    *,
    project: Project | None = None,
    help_topic_resolver: HelpTopicReferenceResolver | None = None,
) -> ProjectDefinitionManifestValidation:
    """Return complete ordered diagnostics without mutating input or Project."""

    try:
        manifest = _decode_manifest(raw)
    except _DecodeFailure as exc:
        diagnostic = _diagnostic(exc.code, exc.path, exc.message)
        return ProjectDefinitionManifestValidation(
            valid=False,
            manifest_sha256="",
            diagnostics=(diagnostic,),
        )

    local_passes = (
        _schema_diagnostics(manifest),
        _walk_forbidden_keys(manifest),
        _project_identity_diagnostics(manifest, project),
        _identity_diagnostics(manifest),
        _scale_diagnostics(manifest),
        _content_diagnostics(manifest),
        _help_diagnostics(manifest, help_topic_resolver),
    )
    diagnostics = _envelope_diagnostics(manifest)
    diagnostics.extend(_section_ordered_diagnostics(local_passes))
    # Cross-reference and hierarchy checks are deliberately final passes. Their
    # row paths must never be sorted back into the earlier section-local output.
    diagnostics.extend(_cross_reference_diagnostics(manifest))
    diagnostics.extend(_hierarchy_diagnostics(manifest, "actors"))
    diagnostics.extend(_hierarchy_diagnostics(manifest, "analytical_elements"))
    ordered = _deduplicate_diagnostics(diagnostics)
    manifest_sha256 = ""
    blocking = any(
        diagnostic.code in _DRAFT_BLOCKING_CODES for diagnostic in ordered
    )
    if identify_typed_project_definition_manifest(manifest) and not blocking:
        manifest_sha256 = hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
    return ProjectDefinitionManifestValidation(
        valid=not ordered,
        manifest_sha256=manifest_sha256,
        diagnostics=ordered,
    )


def parse_project_definition_manifest_v1(
    raw: Mapping[str, Any] | str | bytes,
    *,
    project: Project | None = None,
    help_topic_resolver: HelpTopicReferenceResolver | None = None,
) -> ProjectDefinitionManifestV1:
    """Parse an exact V1 envelope into an immutable DTO.

    Semantic diagnostics (for example a broken parent reference) are retained in
    the DTO so an incomplete DRAFT can be opened and corrected. Envelope, JSON
    type, project-identity, forbidden-field, and schema-shape errors fail closed.
    """

    try:
        manifest = _decode_manifest(raw)
    except _DecodeFailure as exc:
        raise ProjectDefinitionManifestError(
            {"manifest": f"{exc.code} at {exc.path}: {exc.message}"}
        ) from exc
    validation = validate_project_definition_manifest_v1(
        manifest,
        project=project,
        help_topic_resolver=help_topic_resolver,
    )
    blocking = [
        diagnostic
        for diagnostic in validation.diagnostics
        if diagnostic.code in _DRAFT_BLOCKING_CODES
    ]
    if blocking:
        raise ProjectDefinitionManifestError(
            {
                "manifest": json.dumps(
                    [diagnostic.as_dict() for diagnostic in blocking],
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            }
        )
    canonical = _canonical_json(manifest)
    return ProjectDefinitionManifestV1(
        manifest=_deep_freeze(manifest),
        canonical_json=canonical,
        manifest_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        validation=validation,
    )


def canonicalize_project_definition_manifest_v1(
    raw: Mapping[str, Any] | str | bytes,
    *,
    project: Project | None = None,
) -> bytes:
    """Return exact canonical UTF-8 bytes for an explicitly typed V1 manifest."""

    dto = parse_project_definition_manifest_v1(raw, project=project)
    return dto.canonical_json.encode("utf-8")


def hash_project_definition_manifest_v1(
    raw: Mapping[str, Any] | str | bytes,
    *,
    project: Project | None = None,
) -> str:
    """Hash canonical bytes; this function never dispatches legacy manifests."""

    return hashlib.sha256(
        canonicalize_project_definition_manifest_v1(raw, project=project)
    ).hexdigest()


def _require_capability(principal: object, capability_name: str) -> None:
    # Lazy import avoids a domain.policies -> services import cycle while keeping
    # authorization mandatory at the service boundary.
    from domain.policies import StudioCapability, require_studio_capability

    capability = getattr(StudioCapability, capability_name)
    require_studio_capability(principal, capability)


def _fresh_typed_definition(
    definition: ProjectDefinitionVersion,
    *,
    for_update: bool = False,
) -> ProjectDefinitionVersion:
    queryset = ProjectDefinitionVersion.objects.select_related("project")
    if for_update:
        queryset = queryset.select_for_update()
    current = queryset.get(pk=definition.pk)
    if not identify_typed_project_definition_manifest(current.manifest):
        raise ProjectDefinitionManifestError(
            {"manifest": "Legacy definitions are not accepted by the typed V1 service."}
        )
    return current


@transaction.atomic
def create_project_definition_draft(
    *,
    project: Project,
    code: str,
    version: str,
    manifest: Mapping[str, Any] | str | bytes,
    principal: object,
    definition_id: UUID | None = None,
    metadata: Mapping[str, Any] | None = None,
    supersedes: ProjectDefinitionVersion | None = None,
    semantic_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
    construct_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
) -> ProjectDefinitionVersion:
    """Create one typed DRAFT in the canonical ProjectDefinitionVersion table."""

    _require_capability(principal, "DRAFT_CREATE")
    persisted_project = Project.objects.select_for_update().get(pk=project.pk)
    if metadata:
        raise ValidationError(
            {
                "metadata": (
                    "ProjectDefinitionVersion has no separate metadata column; "
                    "definition metadata belongs in the typed manifest snapshot."
                )
            }
        )
    persisted_supersedes = None
    if supersedes is not None:
        persisted_supersedes = ProjectDefinitionVersion.objects.select_for_update().get(
            pk=supersedes.pk
        )
        if persisted_supersedes.project_id != persisted_project.pk:
            raise ValidationError(
                {"supersedes": "A definition can supersede only within its exact project."}
            )
    dto = parse_project_definition_manifest_v1(manifest, project=persisted_project)
    kwargs: dict[str, Any] = {
        "project": persisted_project,
        "code": code,
        "version": version,
        "manifest": dto.as_dict(),
        "manifest_hash": dto.manifest_sha256,
        "schema_version": PROJECT_DEFINITION_MANIFEST_VERSION,
        "semantic_version": semantic_version,
        "construct_version": construct_version,
        "publication_status": PublicationStatus.DRAFT,
        "supersedes": persisted_supersedes,
    }
    if definition_id is not None:
        kwargs["id"] = definition_id
    definition = ProjectDefinitionVersion(**kwargs)
    definition.full_clean()
    with _canonical_studio_write("definition"):
        definition.save(force_insert=True)
    return definition


def _first_project_identity_conflict(
    *,
    project_id: UUID,
    project_code: str,
    scope_group_name: str,
    definition_id: UUID,
) -> FoundationStudioApplicationConflict | None:
    """Classify only persisted identity collisions, never exception prose."""

    if Project.objects.filter(pk=project_id).exists():
        return FoundationStudioApplicationConflict(
            "PROJECT_ID_CONFLICT",
            "The requested Project UUID is already persisted.",
        )
    if Project.objects.filter(code=project_code).exists():
        return FoundationStudioApplicationConflict(
            "PROJECT_CODE_CONFLICT",
            "The requested Project code is already persisted.",
        )
    if Group.objects.filter(name=scope_group_name).exists():
        return FoundationStudioApplicationConflict(
            "PROJECT_SCOPE_GROUP_CONFLICT",
            "The derived Project object-scope group is already persisted.",
        )
    if ProjectDefinitionVersion.objects.filter(pk=definition_id).exists():
        return FoundationStudioApplicationConflict(
            "DEFINITION_ID_CONFLICT",
            "The requested first-definition UUID is already persisted.",
        )
    return None


def _inject_first_project_failure(requested_stage: str | None, stage: str) -> None:
    if requested_stage == stage:
        raise RuntimeError(f"Injected first-Project bootstrap failure at {stage}.")


def _exact_first_definition_id(value: object) -> UUID:
    if value is None:
        raise ValidationError(
            {"definition_id": "First-Project bootstrap requires a non-null UUID."}
        )
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValidationError(
            {"definition_id": "First-Project bootstrap requires a valid UUID."}
        ) from exc


def _copy_project_metadata(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError(
            {"project_metadata": "Project metadata must be a JSON object."}
        )
    if any(not isinstance(key, str) for key in value):
        raise ValidationError(
            {"project_metadata": "Project metadata object keys must be strings."}
        )
    try:
        copied = copy.deepcopy(dict(value))
        json.dumps(
            copied,
            ensure_ascii=False,
            allow_nan=False,
        )
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValidationError(
            {"project_metadata": "Project metadata must contain only JSON values."}
        ) from exc
    return copied


def _trusted_human_bootstrap_user(*, principal: object, user: object) -> object:
    """Bind a sealed HUMAN principal to the exact persisted Django user."""

    from domain.policies import (
        StudioAuthorizationDenied,
        StudioDefinitionRole,
        StudioPrincipal,
    )

    _require_capability(principal, "DRAFT_CREATE")
    user_model = get_user_model()
    if (
        not isinstance(principal, StudioPrincipal)
        or principal.role is StudioDefinitionRole.SERVICE
        or not isinstance(user, user_model)
        or getattr(user, "pk", None) is None
        or not bool(getattr(user, "is_authenticated", False))
    ):
        raise StudioAuthorizationDenied(
            "First-Project bootstrap requires one trusted authenticated HUMAN principal."
        )
    expected_actor = f"django-user:{user.pk}"
    if principal.actor_identifier != expected_actor:
        raise StudioAuthorizationDenied(
            "First-Project bootstrap principal does not match the authenticated user."
        )
    try:
        return user_model._default_manager.get(pk=user.pk)
    except user_model.DoesNotExist as exc:
        raise StudioAuthorizationDenied(
            "First-Project bootstrap user is no longer persisted."
        ) from exc


def bootstrap_project_definition_draft(
    *,
    project_id: UUID | str,
    project_code: str,
    project_version: str,
    project_name: str,
    project_description: str = "",
    project_metadata: Mapping[str, Any],
    definition_id: UUID | str,
    definition_code: str,
    definition_version: str,
    manifest: Mapping[str, Any] | str | bytes,
    principal: object,
    user: object,
    semantic_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
    construct_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
    request_identity: FoundationHumanWriteRequestIdentity | None = None,
    inject_failure_at: str | None = None,
) -> ProjectDefinitionDraftBootstrapResult:
    """Atomically create the first Project, scope grant, DRAFT and CREATE audit."""

    resolved_project_id = UUID(str(project_id))
    resolved_definition_id = _exact_first_definition_id(definition_id)
    resolved_project_metadata = _copy_project_metadata(project_metadata)
    persisted_user = _trusted_human_bootstrap_user(principal=principal, user=user)
    scope_group_name = project_access_group_name(resolved_project_id)
    if request_identity is not None:
        _require_human_write_request(
            request_identity,
            operation=FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
            principal=principal,
            project_id=resolved_project_id,
            target_definition_id=resolved_definition_id,
        )

    try:
        with transaction.atomic():
            user_model = get_user_model()
            persisted_user = user_model._default_manager.select_for_update().get(
                pk=persisted_user.pk
            )
            conflict = _first_project_identity_conflict(
                project_id=resolved_project_id,
                project_code=project_code,
                scope_group_name=scope_group_name,
                definition_id=resolved_definition_id,
            )
            if conflict is not None:
                raise conflict

            project = Project(
                id=resolved_project_id,
                code=project_code,
                version=project_version,
                name=project_name,
                description=project_description,
                metadata=resolved_project_metadata,
            )
            project.full_clean()
            project.save(force_insert=True)
            _inject_first_project_failure(inject_failure_at, "after_project")

            scope_group = Group.objects.create(name=scope_group_name)
            _inject_first_project_failure(inject_failure_at, "after_scope_group")

            persisted_user.groups.add(scope_group)
            _inject_first_project_failure(inject_failure_at, "after_scope_membership")

            definition = create_project_definition_draft(
                project=project,
                definition_id=resolved_definition_id,
                code=definition_code,
                version=definition_version,
                manifest=manifest,
                semantic_version=semantic_version,
                construct_version=construct_version,
                principal=principal,
            )
            _inject_first_project_failure(inject_failure_at, "after_definition")
            _inject_human_write_failure(inject_failure_at, "after_domain_mutation")

            from domain.enums import AuditAction
            from domain.policies import (
                FoundationAuditContext,
                record_definition_audit,
            )

            context = FoundationAuditContext.for_principal_definition(
                definition=definition,
                principal=principal,
            )
            if request_identity is None:
                audit_event = record_definition_audit(
                    context=context,
                    action=AuditAction.CREATE,
                    entity_type="PROJECT_DEFINITION_VERSION",
                    entity_id=definition.pk,
                    after={
                        "project_identity": {
                            "id": str(project.pk),
                            "code": project.code,
                            "version": project.version,
                        },
                        "object_scope_group": {
                            "name": scope_group.name,
                        },
                    },
                )
            else:
                occurred_at = timezone.now()
                receipt = _human_write_receipt(
                    request=request_identity,
                    after_definition=_definition_receipt_identity(definition),
                    bootstrap_result=_bootstrap_receipt_identity(
                        project=project,
                        scope_group=scope_group,
                        user=persisted_user,
                    ),
                    occurred_at=occurred_at,
                    original_http_status=201,
                )
                _inject_human_write_failure(inject_failure_at, "before_audit_insert")
                audit_event = record_definition_audit(
                    context=context,
                    action=AuditAction.CREATE,
                    entity_type="PROJECT_DEFINITION_VERSION",
                    entity_id=definition.pk,
                    before=None,
                    event_id=request_identity.operation_id,
                    occurred_at=occurred_at,
                    foundation_human_operation=receipt.as_dict(),
                )
                _inject_human_write_failure(inject_failure_at, "after_audit_insert")
            _inject_first_project_failure(inject_failure_at, "after_create_audit")

            return ProjectDefinitionDraftBootstrapResult(
                project=project,
                scope_group=scope_group,
                definition=definition,
                audit_event=audit_event,
            )
    except FoundationStudioApplicationConflict:
        raise
    except (IntegrityError, ValidationError) as exc:
        conflict = _first_project_identity_conflict(
            project_id=resolved_project_id,
            project_code=project_code,
            scope_group_name=scope_group_name,
            definition_id=resolved_definition_id,
        )
        if conflict is not None:
            raise conflict from exc
        raise


def _is_successor_application_conflict(definition_id: object) -> bool:
    """Classify retry/stale-lineage state from rows, without message matching."""

    candidate = (
        ProjectDefinitionVersion.objects.filter(pk=definition_id)
        .values(
            "id",
            "project_id",
            "publication_status",
            "supersedes_id",
        )
        .first()
    )
    if candidate is None:
        return False
    if (
        candidate["publication_status"] == PublicationStatus.PUBLISHED
        or ProjectPublication.objects.filter(definition_version_id=definition_id).exists()
    ):
        return True
    if not ProjectPublication.objects.filter(project_id=candidate["project_id"]).exists():
        return False
    exact_current = (
        ProjectDefinitionVersion.objects.filter(
            project_id=candidate["project_id"],
            is_current=True,
        )
        .values("id", "publication_status")
        .first()
    )
    return bool(
        exact_current is None
        or exact_current["publication_status"] != PublicationStatus.PUBLISHED
        or candidate["supersedes_id"] != exact_current["id"]
    )


def publish_successor_project_definition(
    definition: ProjectDefinitionVersion,
    *,
    principal: object,
    locale: str = "en",
    inject_failure_at: str | None = None,
) -> ProjectPublication:
    """Delegate successor publication while typing only retry/race conflicts."""

    from domain.policies import (
        StudioAuthorizationDenied,
        StudioDefinitionRole,
        StudioPrincipal,
        publish_project_definition,
    )

    _require_capability(principal, "DEFINITION_PUBLISH")
    if (
        not isinstance(principal, StudioPrincipal)
        or principal.role is StudioDefinitionRole.SERVICE
    ):
        raise StudioAuthorizationDenied(
            "Public successor publication requires a trusted HUMAN principal."
        )
    if _is_successor_application_conflict(definition.pk):
        raise FoundationStudioApplicationConflict(
            "SUCCESSOR_PUBLICATION_CONFLICT",
            "The successor was already published or no longer supersedes the exact current definition.",
        )
    try:
        return publish_project_definition(
            definition,
            actor_identifier=principal.actor_identifier,
            principal=principal,
            workspace_spec=None,
            locale=locale,
            inject_failure_at=inject_failure_at,
        )
    except (IntegrityError, ValidationError) as exc:
        if _is_successor_application_conflict(definition.pk):
            raise FoundationStudioApplicationConflict(
                "SUCCESSOR_PUBLICATION_CONFLICT",
                "The successor was already published or lost the exact-current race.",
            ) from exc
        raise


def open_project_definition(
    definition: ProjectDefinitionVersion,
    *,
    principal: object,
) -> ProjectDefinitionVersion:
    """Read one exact typed definition through every accepted lifecycle state."""

    _require_capability(principal, "DEFINITION_READ")
    current = _fresh_typed_definition(definition)
    if current.publication_status not in {
        PublicationStatus.DRAFT,
        PublicationStatus.VALIDATED,
        PublicationStatus.PUBLISHED,
        PublicationStatus.RETIRED,
    }:
        raise ValidationError(
            {
                "publication_status": (
                    "Definition lifecycle is outside the canonical Studio read contract."
                )
            }
        )
    dto = parse_project_definition_manifest_v1(
        current.manifest,
        project=current.project,
    )
    if current.manifest_hash != dto.manifest_sha256:
        raise ProjectDefinitionManifestError(
            {"manifest_hash": "Stored definition checksum does not match typed bytes."}
        )
    return current


def open_project_definition_draft(
    definition: ProjectDefinitionVersion,
    *,
    principal: object,
) -> ProjectDefinitionVersion:
    """Compatibility boundary that deliberately remains DRAFT-only."""

    current = open_project_definition(definition, principal=principal)
    if current.publication_status != PublicationStatus.DRAFT:
        raise ValidationError(
            {"publication_status": "Only a DRAFT can be opened by the DRAFT service."}
        )
    return current


@transaction.atomic
def clone_project_definition_draft(
    source: ProjectDefinitionVersion,
    *,
    code: str,
    version: str,
    principal: object,
    definition_id: UUID | None = None,
) -> ProjectDefinitionVersion:
    """Create a successor DRAFT without changing the source snapshot."""

    _require_capability(principal, "DRAFT_CLONE")
    current = _fresh_typed_definition(source, for_update=True)
    dto = parse_project_definition_manifest_v1(current.manifest, project=current.project)
    if current.manifest_hash and current.manifest_hash != dto.manifest_sha256:
        raise ProjectDefinitionManifestError(
            {"manifest_hash": "Source definition checksum does not match typed bytes."}
        )
    kwargs: dict[str, Any] = {
        "project": current.project,
        "code": code,
        "version": version,
        "manifest": dto.as_dict(),
        "manifest_hash": dto.manifest_sha256,
        "schema_version": PROJECT_DEFINITION_MANIFEST_VERSION,
        "semantic_version": current.semantic_version,
        "construct_version": current.construct_version,
        "publication_status": PublicationStatus.DRAFT,
        "supersedes": current,
    }
    if definition_id is not None:
        kwargs["id"] = definition_id
    successor = ProjectDefinitionVersion(**kwargs)
    successor.full_clean()
    with _canonical_studio_write("definition"):
        successor.save(force_insert=True)
    return successor


@transaction.atomic
def save_project_definition_draft(
    definition: ProjectDefinitionVersion,
    *,
    manifest: Mapping[str, Any] | str | bytes,
    expected_manifest_hash: str,
    principal: object,
) -> ProjectDefinitionVersion:
    """Save typed bytes only when the caller presents the exact optimistic token."""

    _require_capability(principal, "DRAFT_SAVE")
    current = _fresh_typed_definition(definition, for_update=True)
    if current.publication_status != PublicationStatus.DRAFT:
        raise ValidationError(
            {"publication_status": "Validated definition bytes are immutable; clone a successor."}
        )
    stored_hash = hash_project_definition_manifest_v1(
        current.manifest,
        project=current.project,
    )
    if current.manifest_hash and current.manifest_hash != stored_hash:
        raise ProjectDefinitionManifestError(
            {"manifest_hash": "Stored DRAFT checksum does not match typed bytes."}
        )
    if not expected_manifest_hash or expected_manifest_hash != stored_hash:
        raise ProjectDefinitionDraftConflict(
            {
                "expected_manifest_hash": (
                    "DRAFT changed after it was opened; reload before saving."
                )
            }
        )
    dto = parse_project_definition_manifest_v1(manifest, project=current.project)
    current.manifest = dto.as_dict()
    current.manifest_hash = dto.manifest_sha256
    current.schema_version = PROJECT_DEFINITION_MANIFEST_VERSION
    current.full_clean()
    with _canonical_studio_write("definition"):
        current.save(
            update_fields=("manifest", "manifest_hash", "schema_version", "updated_at")
        )
    return current


def _utc_z(value: datetime) -> str:
    return value.astimezone(datetime_timezone.utc).isoformat().replace("+00:00", "Z")


def _definition_receipt_identity(
    definition: ProjectDefinitionVersion,
) -> dict[str, Any]:
    validation_sha256 = (
        _canonical_identity_sha256(definition.validation_result)
        if definition.validation_result
        else None
    )
    return {
        "contract": "FOUNDATION_DEFINITION_IDENTITY_V1",
        "id": str(definition.pk),
        "project_id": str(definition.project_id),
        "code": definition.code,
        "version": definition.version,
        "publication_status": definition.publication_status,
        "manifest_hash": definition.manifest_hash,
        "schema_version": definition.schema_version,
        "semantic_version": definition.semantic_version,
        "construct_version": definition.construct_version,
        "supersedes_id": (
            str(definition.supersedes_id) if definition.supersedes_id else None
        ),
        "validated_at": (
            _utc_z(definition.validated_at) if definition.validated_at else None
        ),
        "validated_by": definition.validated_by or None,
        "validation_result_sha256": validation_sha256,
    }


def _bootstrap_receipt_identity(
    *,
    project: Project,
    scope_group: Group,
    user: object,
) -> dict[str, Any]:
    return {
        "project": {
            "id": str(project.pk),
            "code": project.code,
            "version": project.version,
            "name": project.name,
            "description": project.description,
            "metadata": copy.deepcopy(project.metadata),
        },
        "object_scope_group": {"name": scope_group.name},
        "membership": {
            "actor_identifier": f"django-user:{getattr(user, 'pk', '')}",
            "group": scope_group.name,
        },
    }


def _human_write_receipt(
    *,
    request: FoundationHumanWriteRequestIdentity,
    after_definition: Mapping[str, Any],
    occurred_at: datetime,
    original_http_status: int,
    source_definition: Mapping[str, Any] | None = None,
    before_definition: Mapping[str, Any] | None = None,
    bootstrap_result: Mapping[str, Any] | None = None,
    validation: Mapping[str, Any] | None = None,
) -> FoundationHumanWriteReceipt:
    return FoundationHumanWriteReceipt(
        operation=request.operation,
        operation_id=request.operation_id,
        audit_action=str(_HUMAN_WRITE_ACTIONS[request.operation]),
        actor_identifier=request.actor_identifier,
        project_id=request.project_id,
        source_definition=copy.deepcopy(
            dict(source_definition) if source_definition is not None else None
        ),
        before_definition=copy.deepcopy(
            dict(before_definition) if before_definition is not None else None
        ),
        after_definition=copy.deepcopy(dict(after_definition)),
        bootstrap_result=copy.deepcopy(
            dict(bootstrap_result) if bootstrap_result is not None else None
        ),
        validation=copy.deepcopy(dict(validation) if validation is not None else None),
        request=request.as_dict(),
        occurred_at=_utc_z(occurred_at),
        original_http_status=original_http_status,
    )


def _receipt_from_audit(audit_event: AuditEvent) -> FoundationHumanWriteReceipt:
    after = audit_event.after
    payload = (
        after.get(FOUNDATION_HUMAN_OPERATION_AUDIT_KEY)
        if isinstance(after, Mapping)
        else None
    )
    if (
        not isinstance(after, Mapping)
        or set(after) != {FOUNDATION_HUMAN_OPERATION_AUDIT_KEY}
        or not isinstance(payload, Mapping)
        or set(payload) != _HUMAN_WRITE_RECEIPT_KEYS
    ):
        raise FoundationStudioApplicationConflict(
            "WRITE_OPERATION_KEY_REUSED",
            "The operation UUID is already owned by another immutable audit event.",
        )
    request_payload = payload.get("request")
    source_definition = payload.get("source_definition")
    before_definition = payload.get("before_definition")
    after_definition = payload.get("after_definition")
    bootstrap_result = payload.get("bootstrap_result")
    validation = payload.get("validation")
    try:
        operation = FoundationHumanWriteOperation(payload["operation"])
        operation_id = _exact_uuid(
            payload["operation_id"],
            label="operation_id",
            version=4,
        )
        project_id = _exact_uuid(payload["project_id"], label="project_id")
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise FoundationStudioApplicationConflict(
            "WRITE_OPERATION_KEY_REUSED",
            "The operation UUID has an unreadable immutable receipt.",
        ) from exc

    def exact_definition_identity(value: object) -> bool:
        if not isinstance(value, Mapping) or set(value) != _DEFINITION_RECEIPT_IDENTITY_KEYS:
            return False
        try:
            identity_id = _exact_uuid(value.get("id"), label="definition_id")
            identity_project_id = _exact_uuid(
                value.get("project_id"),
                label="definition_project_id",
            )
            _exact_sha256(value.get("manifest_hash"), label="manifest_hash")
            validation_sha256 = value.get("validation_result_sha256")
            if validation_sha256 is not None:
                _exact_sha256(
                    validation_sha256,
                    label="validation_result_sha256",
                )
            supersedes_id = value.get("supersedes_id")
            if supersedes_id is not None:
                _exact_uuid(supersedes_id, label="supersedes_id")
        except (TypeError, ValueError, ValidationError):
            return False
        return (
            value.get("contract") == "FOUNDATION_DEFINITION_IDENTITY_V1"
            and identity_project_id == project_id
            and isinstance(value.get("code"), str)
            and isinstance(value.get("version"), str)
            and value.get("publication_status") in PublicationStatus.values
            and isinstance(value.get("schema_version"), str)
            and isinstance(value.get("semantic_version"), str)
            and isinstance(value.get("construct_version"), str)
            and (
                value.get("validated_at") is None
                or isinstance(value.get("validated_at"), str)
            )
            and (
                value.get("validated_by") is None
                or isinstance(value.get("validated_by"), str)
            )
            and identity_id is not None
        )

    definition_mappings = tuple(
        item
        for item in (source_definition, before_definition, after_definition)
        if item is not None
    )
    expected_action = str(_HUMAN_WRITE_ACTIONS[operation])
    expected_status = _HUMAN_WRITE_HTTP_STATUSES[operation]
    expected_audit_id = str(operation_id)
    expected_code = f"AUD-DEF-OP-{operation_id.hex}"
    expected_after_id = str(audit_event.definition_version_id)
    request_if_match = (
        request_payload.get("if_match")
        if isinstance(request_payload, Mapping)
        else None
    )
    operation_shape_is_exact = {
        FoundationHumanWriteOperation.BOOTSTRAP_DRAFT: (
            source_definition is None
            and before_definition is None
            and isinstance(bootstrap_result, Mapping)
            and validation is None
        ),
        FoundationHumanWriteOperation.CREATE_DRAFT: (
            source_definition is None
            and before_definition is None
            and bootstrap_result is None
            and validation is None
        ),
        FoundationHumanWriteOperation.CLONE_DRAFT: (
            isinstance(source_definition, Mapping)
            and before_definition is None
            and bootstrap_result is None
            and validation is None
        ),
        FoundationHumanWriteOperation.SAVE_DRAFT: (
            source_definition is None
            and isinstance(before_definition, Mapping)
            and bootstrap_result is None
            and validation is None
        ),
        FoundationHumanWriteOperation.VALIDATE_DEFINITION: (
            source_definition is None
            and isinstance(before_definition, Mapping)
            and bootstrap_result is None
            and isinstance(validation, Mapping)
        ),
    }[operation]
    if (
        payload.get("contract") != FOUNDATION_HUMAN_WRITE_RECEIPT_CONTRACT
        or payload.get("version") != FOUNDATION_HUMAN_WRITE_RECEIPT_VERSION
        or audit_event.pk != operation_id
        or audit_event.scope != AuditScope.DEFINITION
        or audit_event.definition_version_id is None
        or audit_event.workspace_id is not None
        or audit_event.entity_type != "PROJECT_DEFINITION_VERSION"
        or audit_event.entity_id != audit_event.definition_version_id
        or audit_event.code != expected_code
        or audit_event.actor_type != AuditActorType.HUMAN
        or payload.get("actor_type") != AuditActorType.HUMAN
        or payload.get("operation_id") != expected_audit_id
        or payload.get("audit_event_id") != expected_audit_id
        or payload.get("actor_identifier") != audit_event.actor_identifier
        or payload.get("project_id") != str(audit_event.project_id)
        or project_id != audit_event.project_id
        or payload.get("audit_action") != expected_action
        or audit_event.action != expected_action
        or payload.get("before_definition") != audit_event.before
        or payload.get("occurred_at") != _utc_z(audit_event.occurred_at)
        or isinstance(payload.get("original_http_status"), bool)
        or payload.get("original_http_status") != expected_status
        or (
            operation
            in {
                FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
                FoundationHumanWriteOperation.CREATE_DRAFT,
            }
            and request_if_match is not None
        )
        or (
            operation
            in {
                FoundationHumanWriteOperation.CLONE_DRAFT,
                FoundationHumanWriteOperation.SAVE_DRAFT,
                FoundationHumanWriteOperation.VALIDATE_DEFINITION,
            }
            and request_if_match is None
        )
        or not operation_shape_is_exact
        or not exact_definition_identity(after_definition)
        or after_definition.get("id") != expected_after_id
        or (
            operation
            in {
                FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
                FoundationHumanWriteOperation.CREATE_DRAFT,
                FoundationHumanWriteOperation.CLONE_DRAFT,
                FoundationHumanWriteOperation.SAVE_DRAFT,
            }
            and after_definition.get("publication_status") != PublicationStatus.DRAFT
        )
        or (
            operation is FoundationHumanWriteOperation.VALIDATE_DEFINITION
            and after_definition.get("publication_status")
            != PublicationStatus.VALIDATED
        )
        or any(not exact_definition_identity(item) for item in definition_mappings)
        or (
            isinstance(before_definition, Mapping)
            and before_definition.get("id") != expected_after_id
        )
        or (
            isinstance(before_definition, Mapping)
            and before_definition.get("publication_status") != PublicationStatus.DRAFT
        )
        or (
            isinstance(source_definition, Mapping)
            and operation is FoundationHumanWriteOperation.CLONE_DRAFT
            and after_definition.get("supersedes_id") != source_definition.get("id")
        )
        or (
            operation is FoundationHumanWriteOperation.VALIDATE_DEFINITION
            and isinstance(validation, Mapping)
            and after_definition.get("validation_result_sha256")
            != _canonical_identity_sha256(validation)
        )
        or not isinstance(request_payload, Mapping)
        or set(request_payload) != _HUMAN_WRITE_REQUEST_KEYS
        or request_payload.get("contract") != FOUNDATION_HUMAN_WRITE_REQUEST_CONTRACT
        or not isinstance(request_payload.get("raw_input_byte_length"), int)
        or isinstance(request_payload.get("raw_input_byte_length"), bool)
        or request_payload.get("raw_input_byte_length") < 0
    ):
        raise FoundationStudioApplicationConflict(
            "WRITE_OPERATION_KEY_REUSED",
            "The operation UUID has an incompatible immutable receipt.",
        )
    try:
        _exact_sha256(request_payload.get("sha256"), label="request_sha256")
        _exact_sha256(
            request_payload.get("raw_input_sha256"),
            label="raw_input_sha256",
        )
        if request_payload.get("if_match") is not None:
            _exact_sha256(request_payload.get("if_match"), label="if_match")
        return FoundationHumanWriteReceipt(
            operation=operation,
            operation_id=operation_id,
            audit_action=str(payload["audit_action"]),
            actor_identifier=str(payload["actor_identifier"]),
            project_id=project_id,
            source_definition=copy.deepcopy(source_definition),
            before_definition=copy.deepcopy(before_definition),
            after_definition=copy.deepcopy(after_definition),
            bootstrap_result=copy.deepcopy(bootstrap_result),
            validation=copy.deepcopy(validation),
            request=copy.deepcopy(request_payload),
            occurred_at=str(payload["occurred_at"]),
            original_http_status=expected_status,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise FoundationStudioApplicationConflict(
            "WRITE_OPERATION_KEY_REUSED",
            "The operation UUID has an unreadable immutable receipt.",
        ) from exc


def _require_human_write_request(
    request: FoundationHumanWriteRequestIdentity,
    *,
    operation: FoundationHumanWriteOperation,
    principal: object,
    project_id: object,
    target_definition_id: object,
    source_definition_id: object | None = None,
) -> None:
    from domain.policies import (
        StudioAuthorizationDenied,
        StudioDefinitionRole,
        StudioPrincipal,
    )

    if not isinstance(request, FoundationHumanWriteRequestIdentity):
        raise ValidationError(
            {"request_identity": "A server-built Foundation request identity is required."}
        )
    try:
        canonical_request = FoundationHumanWriteRequestIdentity.build(
            operation=request.operation,
            operation_id=request.operation_id,
            method=request.method,
            route=request.route,
            actor_identifier=request.actor_identifier,
            project_id=request.project_id,
            source_definition_id=request.source_definition_id,
            target_definition_id=request.target_definition_id,
            content_type=request.content_type,
            raw_input_sha256=request.raw_input_sha256,
            raw_input_byte_length=request.raw_input_byte_length,
            if_match=request.if_match,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValidationError(
            {"request_identity": "Foundation request identity is not canonical."}
        ) from exc
    if (
        request != canonical_request
        or request.operation is not operation
        or request.project_id != UUID(str(project_id))
        or request.target_definition_id != UUID(str(target_definition_id))
        or request.source_definition_id
        != (UUID(str(source_definition_id)) if source_definition_id is not None else None)
    ):
        raise ValidationError(
            {"request_identity": "Request identity does not match the domain target."}
        )
    if (
        not isinstance(principal, StudioPrincipal)
        or principal.role is StudioDefinitionRole.SERVICE
        or request.actor_identifier != principal.actor_identifier
    ):
        raise StudioAuthorizationDenied(
            "Public Foundation definition writes require the exact trusted HUMAN principal."
        )
    actor_pk = request.actor_identifier.removeprefix("django-user:")
    user_model = get_user_model()
    if not user_model._default_manager.filter(pk=actor_pk, is_active=True).exists():
        raise StudioAuthorizationDenied(
            "Public Foundation definition writes require a persisted active HUMAN user."
        )


def _inject_human_write_failure(requested_stage: str | None, stage: str) -> None:
    if requested_stage == stage:
        raise RuntimeError(f"Injected Foundation HUMAN write failure at {stage}.")


def _locked_project(project_id: object) -> Project:
    return Project.objects.select_for_update().get(pk=project_id)


def _locked_definition(
    *,
    project: Project,
    definition_id: object,
) -> ProjectDefinitionVersion:
    return (
        ProjectDefinitionVersion.objects.select_for_update()
        .select_related("project")
        .get(pk=definition_id, project_id=project.pk)
    )


def _existing_human_write_result(
    request: FoundationHumanWriteRequestIdentity,
) -> FoundationHumanWriteResult | None:
    audit_event = (
        AuditEvent.objects.select_related("project", "definition_version")
        .filter(pk=request.operation_id)
        .first()
    )
    if audit_event is None:
        return None
    receipt = _receipt_from_audit(audit_event)
    request_payload = receipt.request
    if (
        receipt.operation is not request.operation
        or receipt.operation_id != request.operation_id
        or receipt.actor_identifier != request.actor_identifier
        or receipt.project_id != request.project_id
        or request_payload.get("sha256") != request.sha256
        or request_payload.get("raw_input_sha256") != request.raw_input_sha256
        or request_payload.get("raw_input_byte_length") != request.raw_input_byte_length
        or request_payload.get("if_match") != request.if_match
    ):
        raise FoundationStudioApplicationConflict(
            "WRITE_OPERATION_KEY_REUSED",
            "The operation UUID is already bound to different HUMAN intent.",
        )
    return FoundationHumanWriteResult(
        audit_event=audit_event,
        receipt=receipt,
        replayed=True,
    )


def _definition_identity_conflict(
    *,
    project_id: object,
    definition_id: object,
    code: str,
    version: str,
) -> FoundationStudioApplicationConflict | None:
    if ProjectDefinitionVersion.objects.filter(pk=definition_id).exists():
        return FoundationStudioApplicationConflict(
            "DEFINITION_ID_CONFLICT",
            "The requested definition UUID is already persisted.",
        )
    if ProjectDefinitionVersion.objects.filter(
        project_id=project_id,
        code=code,
    ).exists():
        return FoundationStudioApplicationConflict(
            "DEFINITION_CODE_CONFLICT",
            "The requested definition code is already persisted in this Project.",
        )
    if ProjectDefinitionVersion.objects.filter(
        project_id=project_id,
        version=version,
    ).exists():
        return FoundationStudioApplicationConflict(
            "DEFINITION_VERSION_CONFLICT",
            "The requested definition version is already persisted in this Project.",
        )
    return None


def _require_expected_hash(
    *,
    request: FoundationHumanWriteRequestIdentity,
    expected_manifest_hash: str,
) -> str:
    expected = _exact_sha256(expected_manifest_hash, label="expected_manifest_hash")
    if request.if_match != expected:
        raise ValidationError(
            {"expected_manifest_hash": "If-Match and request identity must be identical."}
        )
    return expected


def _stored_definition_hash(definition: ProjectDefinitionVersion) -> str:
    stored = hash_project_definition_manifest_v1(
        definition.manifest,
        project=definition.project,
    )
    if definition.manifest_hash and definition.manifest_hash != stored:
        raise ProjectDefinitionManifestError(
            {"manifest_hash": "Stored definition checksum does not match typed bytes."}
        )
    return stored


def _record_human_write_audit(
    *,
    definition: ProjectDefinitionVersion,
    principal: object,
    request: FoundationHumanWriteRequestIdentity,
    receipt: FoundationHumanWriteReceipt,
    before: Mapping[str, Any] | None,
    occurred_at: datetime,
) -> AuditEvent:
    from domain.policies import FoundationAuditContext, record_definition_audit

    return record_definition_audit(
        context=FoundationAuditContext.for_principal_definition(
            definition=definition,
            principal=principal,
        ),
        action=_HUMAN_WRITE_ACTIONS[request.operation],
        entity_type="PROJECT_DEFINITION_VERSION",
        entity_id=definition.pk,
        before=copy.deepcopy(dict(before) if before is not None else None),
        event_id=request.operation_id,
        occurred_at=occurred_at,
        foundation_human_operation=receipt.as_dict(),
    )


def _fresh_human_result(
    *,
    audit_event: AuditEvent,
    receipt: FoundationHumanWriteReceipt,
    definition: ProjectDefinitionVersion,
    project: Project | None = None,
    scope_group: Group | None = None,
) -> FoundationHumanWriteResult:
    # Return committed database truth.  PostgreSQL JSONB may normalize values
    # such as ``-0.0`` in Project metadata or Definition manifests, and the
    # operation payload must agree exactly with its persisted audit receipt.
    definition.refresh_from_db()
    if project is not None:
        project.refresh_from_db()
    if scope_group is not None:
        scope_group.refresh_from_db()
    return FoundationHumanWriteResult(
        audit_event=audit_event,
        receipt=receipt,
        replayed=False,
        definition=definition,
        project=project,
        scope_group=scope_group,
    )


def _bootstrap_existing_project_access(user: object, project_id: object) -> None:
    """Enforce current scope before inspecting any key for an existing Project."""

    project = Project.objects.filter(pk=project_id).first()
    if project is None:
        return
    if bool(getattr(user, "is_superuser", False)):
        return
    groups = getattr(user, "groups", None)
    if groups is None or not groups.filter(
        name=project_access_group_name(project.pk)
    ).exists():
        from domain.policies import StudioAuthorizationDenied

        raise StudioAuthorizationDenied(
            "Bootstrap requires current Project object scope before operation-key lookup."
        )


def _existing_bootstrap_human_write_result(
    request: FoundationHumanWriteRequestIdentity,
    *,
    user: object,
) -> FoundationHumanWriteResult | None:
    """Recheck current scope after a raced key appears, before receipt comparison."""

    if not AuditEvent.objects.filter(pk=request.operation_id).exists():
        return None
    _bootstrap_existing_project_access(user, request.project_id)
    return _existing_human_write_result(request)


def bootstrap_project_definition_draft_human_write(
    *,
    request_identity: FoundationHumanWriteRequestIdentity,
    project_id: UUID | str,
    project_code: str,
    project_version: str,
    project_name: str,
    project_description: str = "",
    project_metadata: Mapping[str, Any],
    definition_id: UUID | str,
    definition_code: str,
    definition_version: str,
    manifest: Mapping[str, Any] | str | bytes,
    principal: object,
    user: object,
    semantic_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
    construct_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
    inject_failure_at: str | None = None,
) -> FoundationHumanWriteResult:
    _require_capability(principal, "DRAFT_CREATE")
    resolved_project_id = _exact_uuid(project_id, label="project_id")
    resolved_definition_id = _exact_uuid(definition_id, label="definition_id")
    _require_human_write_request(
        request_identity,
        operation=FoundationHumanWriteOperation.BOOTSTRAP_DRAFT,
        principal=principal,
        project_id=resolved_project_id,
        target_definition_id=resolved_definition_id,
    )
    persisted_user = _trusted_human_bootstrap_user(principal=principal, user=user)
    _bootstrap_existing_project_access(persisted_user, resolved_project_id)
    existing = _existing_bootstrap_human_write_result(
        request_identity,
        user=persisted_user,
    )
    if existing is not None:
        return existing
    try:
        result = bootstrap_project_definition_draft(
            project_id=resolved_project_id,
            project_code=project_code,
            project_version=project_version,
            project_name=project_name,
            project_description=project_description,
            project_metadata=project_metadata,
            definition_id=resolved_definition_id,
            definition_code=definition_code,
            definition_version=definition_version,
            manifest=manifest,
            principal=principal,
            user=persisted_user,
            semantic_version=semantic_version,
            construct_version=construct_version,
            request_identity=request_identity,
            inject_failure_at=inject_failure_at,
        )
    except (IntegrityError, ValidationError):
        _bootstrap_existing_project_access(persisted_user, resolved_project_id)
        existing = _existing_bootstrap_human_write_result(
            request_identity,
            user=persisted_user,
        )
        if existing is not None:
            return existing
        raise
    receipt = _receipt_from_audit(result.audit_event)
    return _fresh_human_result(
        audit_event=result.audit_event,
        receipt=receipt,
        definition=result.definition,
        project=result.project,
        scope_group=result.scope_group,
    )


def create_project_definition_draft_human_write(
    *,
    request_identity: FoundationHumanWriteRequestIdentity,
    project: Project,
    definition_id: UUID | str,
    code: str,
    version: str,
    manifest: Mapping[str, Any] | str | bytes,
    principal: object,
    semantic_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
    construct_version: str = PROJECT_DEFINITION_MANIFEST_VERSION,
    inject_failure_at: str | None = None,
) -> FoundationHumanWriteResult:
    _require_capability(principal, "DRAFT_CREATE")
    resolved_definition_id = _exact_uuid(definition_id, label="definition_id")
    _require_human_write_request(
        request_identity,
        operation=FoundationHumanWriteOperation.CREATE_DRAFT,
        principal=principal,
        project_id=project.pk,
        target_definition_id=resolved_definition_id,
    )
    try:
        with transaction.atomic():
            locked_project = _locked_project(request_identity.project_id)
            existing = _existing_human_write_result(request_identity)
            if existing is not None:
                return existing
            conflict = _definition_identity_conflict(
                project_id=locked_project.pk,
                definition_id=resolved_definition_id,
                code=code,
                version=version,
            )
            if conflict is not None:
                raise conflict
            definition = create_project_definition_draft(
                project=locked_project,
                definition_id=resolved_definition_id,
                code=code,
                version=version,
                manifest=manifest,
                semantic_version=semantic_version,
                construct_version=construct_version,
                principal=principal,
            )
            _inject_human_write_failure(inject_failure_at, "after_domain_mutation")
            occurred_at = timezone.now()
            receipt = _human_write_receipt(
                request=request_identity,
                after_definition=_definition_receipt_identity(definition),
                occurred_at=occurred_at,
                original_http_status=201,
            )
            _inject_human_write_failure(inject_failure_at, "before_audit_insert")
            audit_event = _record_human_write_audit(
                definition=definition,
                principal=principal,
                request=request_identity,
                receipt=receipt,
                before=None,
                occurred_at=occurred_at,
            )
            _inject_human_write_failure(inject_failure_at, "after_audit_insert")
            persisted_receipt = _receipt_from_audit(audit_event)
            return _fresh_human_result(
                audit_event=audit_event,
                receipt=persisted_receipt,
                definition=definition,
            )
    except (IntegrityError, ValidationError) as exc:
        existing = _existing_human_write_result(request_identity)
        if existing is not None:
            return existing
        if isinstance(exc, FoundationStudioApplicationConflict):
            raise
        conflict = _definition_identity_conflict(
            project_id=request_identity.project_id,
            definition_id=resolved_definition_id,
            code=code,
            version=version,
        )
        if conflict is not None:
            raise conflict
        raise


def clone_project_definition_draft_human_write(
    source: ProjectDefinitionVersion,
    *,
    request_identity: FoundationHumanWriteRequestIdentity,
    expected_manifest_hash: str,
    definition_id: UUID | str,
    code: str,
    version: str,
    principal: object,
    inject_failure_at: str | None = None,
) -> FoundationHumanWriteResult:
    _require_capability(principal, "DRAFT_CLONE")
    resolved_definition_id = _exact_uuid(definition_id, label="definition_id")
    expected = _require_expected_hash(
        request=request_identity,
        expected_manifest_hash=expected_manifest_hash,
    )
    _require_human_write_request(
        request_identity,
        operation=FoundationHumanWriteOperation.CLONE_DRAFT,
        principal=principal,
        project_id=source.project_id,
        source_definition_id=source.pk,
        target_definition_id=resolved_definition_id,
    )
    try:
        with transaction.atomic():
            project = _locked_project(request_identity.project_id)
            locked_source = _locked_definition(project=project, definition_id=source.pk)
            existing = _existing_human_write_result(request_identity)
            if existing is not None:
                return existing
            if _stored_definition_hash(locked_source) != expected:
                raise FoundationStudioApplicationConflict(
                    "CLONE_SOURCE_STALE",
                    "Clone source changed after it was opened.",
                )
            conflict = _definition_identity_conflict(
                project_id=project.pk,
                definition_id=resolved_definition_id,
                code=code,
                version=version,
            )
            if conflict is not None:
                raise conflict
            source_identity = _definition_receipt_identity(locked_source)
            definition = clone_project_definition_draft(
                locked_source,
                definition_id=resolved_definition_id,
                code=code,
                version=version,
                principal=principal,
            )
            _inject_human_write_failure(inject_failure_at, "after_domain_mutation")
            occurred_at = timezone.now()
            receipt = _human_write_receipt(
                request=request_identity,
                source_definition=source_identity,
                after_definition=_definition_receipt_identity(definition),
                occurred_at=occurred_at,
                original_http_status=201,
            )
            _inject_human_write_failure(inject_failure_at, "before_audit_insert")
            audit_event = _record_human_write_audit(
                definition=definition,
                principal=principal,
                request=request_identity,
                receipt=receipt,
                before=None,
                occurred_at=occurred_at,
            )
            _inject_human_write_failure(inject_failure_at, "after_audit_insert")
            persisted_receipt = _receipt_from_audit(audit_event)
            return _fresh_human_result(
                audit_event=audit_event,
                receipt=persisted_receipt,
                definition=definition,
            )
    except (IntegrityError, ValidationError) as exc:
        existing = _existing_human_write_result(request_identity)
        if existing is not None:
            return existing
        if isinstance(exc, FoundationStudioApplicationConflict):
            raise
        conflict = _definition_identity_conflict(
            project_id=request_identity.project_id,
            definition_id=resolved_definition_id,
            code=code,
            version=version,
        )
        if conflict is not None:
            raise conflict
        raise


def save_project_definition_draft_human_write(
    definition: ProjectDefinitionVersion,
    *,
    request_identity: FoundationHumanWriteRequestIdentity,
    expected_manifest_hash: str,
    manifest: Mapping[str, Any] | str | bytes,
    principal: object,
    inject_failure_at: str | None = None,
) -> FoundationHumanWriteResult:
    _require_capability(principal, "DRAFT_SAVE")
    expected = _require_expected_hash(
        request=request_identity,
        expected_manifest_hash=expected_manifest_hash,
    )
    _require_human_write_request(
        request_identity,
        operation=FoundationHumanWriteOperation.SAVE_DRAFT,
        principal=principal,
        project_id=definition.project_id,
        target_definition_id=definition.pk,
    )
    try:
        with transaction.atomic():
            project = _locked_project(request_identity.project_id)
            current = _locked_definition(project=project, definition_id=definition.pk)
            existing = _existing_human_write_result(request_identity)
            if existing is not None:
                return existing
            if current.publication_status != PublicationStatus.DRAFT:
                raise FoundationStudioApplicationConflict(
                    "DEFINITION_NOT_DRAFT",
                    "Only an exact DRAFT can be saved.",
                )
            if _stored_definition_hash(current) != expected:
                raise FoundationStudioApplicationConflict(
                    "DRAFT_STALE",
                    "DRAFT changed after it was opened.",
                )
            before = _definition_receipt_identity(current)
            saved = save_project_definition_draft(
                current,
                manifest=manifest,
                expected_manifest_hash=expected,
                principal=principal,
            )
            _inject_human_write_failure(inject_failure_at, "after_domain_mutation")
            occurred_at = timezone.now()
            receipt = _human_write_receipt(
                request=request_identity,
                before_definition=before,
                after_definition=_definition_receipt_identity(saved),
                occurred_at=occurred_at,
                original_http_status=200,
            )
            _inject_human_write_failure(inject_failure_at, "before_audit_insert")
            audit_event = _record_human_write_audit(
                definition=saved,
                principal=principal,
                request=request_identity,
                receipt=receipt,
                before=before,
                occurred_at=occurred_at,
            )
            _inject_human_write_failure(inject_failure_at, "after_audit_insert")
            persisted_receipt = _receipt_from_audit(audit_event)
            return _fresh_human_result(
                audit_event=audit_event,
                receipt=persisted_receipt,
                definition=saved,
            )
    except (IntegrityError, ValidationError):
        existing = _existing_human_write_result(request_identity)
        if existing is not None:
            return existing
        raise


def validate_project_definition_human_write(
    definition: ProjectDefinitionVersion,
    *,
    request_identity: FoundationHumanWriteRequestIdentity,
    expected_manifest_hash: str,
    principal: object,
    inject_failure_at: str | None = None,
) -> FoundationHumanWriteResult:
    _require_capability(principal, "DEFINITION_VALIDATE")
    expected = _require_expected_hash(
        request=request_identity,
        expected_manifest_hash=expected_manifest_hash,
    )
    _require_human_write_request(
        request_identity,
        operation=FoundationHumanWriteOperation.VALIDATE_DEFINITION,
        principal=principal,
        project_id=definition.project_id,
        target_definition_id=definition.pk,
    )
    try:
        with transaction.atomic():
            project = _locked_project(request_identity.project_id)
            current = _locked_definition(project=project, definition_id=definition.pk)
            existing = _existing_human_write_result(request_identity)
            if existing is not None:
                return existing
            if current.publication_status == PublicationStatus.VALIDATED:
                raise FoundationStudioApplicationConflict(
                    "DEFINITION_ALREADY_VALIDATED",
                    "Definition is already VALIDATED under another operation UUID.",
                )
            if current.publication_status != PublicationStatus.DRAFT:
                raise FoundationStudioApplicationConflict(
                    "DEFINITION_NOT_DRAFT",
                    "Only an exact DRAFT can be validated.",
                )
            if _stored_definition_hash(current) != expected:
                raise FoundationStudioApplicationConflict(
                    "DRAFT_STALE",
                    "DRAFT changed after it was opened.",
                )
            from domain.policies import validate_project_definition_manifest_policy

            report = validate_project_definition_manifest_policy(
                current.manifest,
                project=project,
            )
            report_payload = report.as_dict()
            if not report.valid:
                raise FoundationHumanWriteError(
                    "DEFINITION_VALIDATION_FAILED",
                    "Definition failed canonical FD01 validation.",
                    report=report_payload,
                )
            before = _definition_receipt_identity(current)
            occurred_at = timezone.now()
            current.manifest_hash = report.manifest_sha256
            current.publication_status = PublicationStatus.VALIDATED
            current.validated_at = occurred_at
            current.validated_by = request_identity.actor_identifier
            current.validation_result = report_payload
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
            _inject_human_write_failure(inject_failure_at, "after_domain_mutation")
            receipt = _human_write_receipt(
                request=request_identity,
                before_definition=before,
                after_definition=_definition_receipt_identity(current),
                validation=report_payload,
                occurred_at=occurred_at,
                original_http_status=200,
            )
            _inject_human_write_failure(inject_failure_at, "before_audit_insert")
            audit_event = _record_human_write_audit(
                definition=current,
                principal=principal,
                request=request_identity,
                receipt=receipt,
                before=before,
                occurred_at=occurred_at,
            )
            _inject_human_write_failure(inject_failure_at, "after_audit_insert")
            persisted_receipt = _receipt_from_audit(audit_event)
            return _fresh_human_result(
                audit_event=audit_event,
                receipt=persisted_receipt,
                definition=current,
            )
    except (IntegrityError, ValidationError):
        existing = _existing_human_write_result(request_identity)
        if existing is not None:
            return existing
        raise
