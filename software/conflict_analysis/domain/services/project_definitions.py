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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, Protocol
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import transaction
from jsonschema import Draft202012Validator, FormatChecker

from domain.enums import PublicationStatus
from domain.models import (
    Project,
    ProjectDefinitionVersion,
    _canonical_studio_write,
)
from domain.services.raw_ingest import RawJSONError, parse_json_source


PROJECT_DEFINITION_MANIFEST_FORMAT: Final = "conflict-analysis-project-definition"
PROJECT_DEFINITION_MANIFEST_VERSION: Final = "1.0.0"
PROJECT_DEFINITION_MANIFEST_SCHEMA_ID: Final = (
    "https://conflictology.invalid/schemas/"
    "project-definition-manifest-1.0.0.schema.json"
)
PROJECT_DEFINITION_VALIDATION_CONTRACT: Final = (
    "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1"
)

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

_SECTION_RANK: Final = {name: index for index, name in enumerate(MANIFEST_SECTIONS)}
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


def _decode_manifest(raw: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    try:
        return dict(parse_json_source(raw).value)
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


def _path_parts(path: str) -> tuple[tuple[int, object], ...]:
    if path == "/":
        return ()
    result: list[tuple[int, object]] = []
    for raw in path.lstrip("/").split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if token.isdigit():
            result.append((0, int(token)))
        else:
            result.append((1, token))
    return tuple(result)


def _diagnostic_sort_key(
    diagnostic: ProjectDefinitionManifestDiagnostic,
) -> tuple[Any, ...]:
    first = diagnostic.path.lstrip("/").split("/", 1)[0]
    return (
        _SECTION_RANK.get(first, len(_SECTION_RANK)),
        _path_parts(diagnostic.path),
        diagnostic.code,
        diagnostic.message,
    )


def _deduplicate_diagnostics(
    diagnostics: Sequence[ProjectDefinitionManifestDiagnostic],
) -> tuple[ProjectDefinitionManifestDiagnostic, ...]:
    unique = {
        (item.level, item.code, item.path, item.message): item for item in diagnostics
    }
    return tuple(sorted(unique.values(), key=_diagnostic_sort_key))


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
    errors = sorted(
        _SCHEMA_VALIDATOR.iter_errors(manifest),
        key=lambda error: (_pointer(tuple(error.absolute_path)), error.validator or ""),
    )
    for error in errors:
        path_parts = tuple(error.absolute_path)
        path = _pointer(path_parts)
        if error.validator == "required":
            missing = sorted(set(error.validator_value) - set(error.instance))
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
        for key, item in value.items():
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

    diagnostics: list[ProjectDefinitionManifestDiagnostic] = []
    diagnostics.extend(_envelope_diagnostics(manifest))
    diagnostics.extend(_schema_diagnostics(manifest))
    diagnostics.extend(_walk_forbidden_keys(manifest))
    diagnostics.extend(_project_identity_diagnostics(manifest, project))
    diagnostics.extend(_identity_diagnostics(manifest))
    diagnostics.extend(_hierarchy_diagnostics(manifest, "actors"))
    diagnostics.extend(_hierarchy_diagnostics(manifest, "analytical_elements"))
    diagnostics.extend(_cross_reference_diagnostics(manifest))
    diagnostics.extend(_scale_diagnostics(manifest))
    diagnostics.extend(_content_diagnostics(manifest))
    diagnostics.extend(_help_diagnostics(manifest, help_topic_resolver))
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


def open_project_definition_draft(
    definition: ProjectDefinitionVersion,
    *,
    principal: object,
) -> ProjectDefinitionVersion:
    """Open an exact typed DRAFT after server-side read authorization."""

    _require_capability(principal, "DEFINITION_READ")
    current = _fresh_typed_definition(definition)
    if current.publication_status != PublicationStatus.DRAFT:
        raise ValidationError(
            {"publication_status": "Only a DRAFT can be opened by the DRAFT service."}
        )
    parse_project_definition_manifest_v1(current.manifest, project=current.project)
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
