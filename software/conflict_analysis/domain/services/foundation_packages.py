"""Canonical Foundation package boundary and atomic import service.

The version 2 boundary is deliberately independent from any JSON/XLS transport.
Adapters must produce the same canonical DTO before schema and semantic validation.
The legacy project-package 1.0.0 module remains immutable and available separately.
"""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol, TypeAlias
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from domain import models as domain_models


FOUNDATION_PACKAGE_FORMAT = "conflict-analysis-foundation"
FOUNDATION_PACKAGE_VERSION = "2.0.0"
FOUNDATION_PACKAGE_VERSION_2_1 = "2.1.0"
FOUNDATION_PACKAGE_SCOPES_2_1 = frozenset({"WORKSPACE", "PROJECT_DEFINITION"})
HASH_ALGORITHM = "sha256"
RAW_INPUT_KINDS = frozenset(
    {"PATH_BYTES", "BYTES", "TEXT", "CANONICAL_MAPPING"}
)
RAW_INPUT_PROVENANCE_KEYS = (
    "raw_input_kind",
    "raw_input_sha256",
    "raw_input_name",
)
SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "foundation-package-2.0.0.schema.json"
)
SCHEMA_PATH_2_1 = (
    Path(__file__).resolve().parent
    / "schemas"
    / "foundation-package-2.1.0.schema.json"
)
DEFINITION_MANIFEST_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "project-definition-manifest-1.0.0.schema.json"
)

with SCHEMA_PATH.open(encoding="utf-8") as _schema_file:
    FOUNDATION_PACKAGE_JSON_SCHEMA = json.load(_schema_file)
Draft202012Validator.check_schema(FOUNDATION_PACKAGE_JSON_SCHEMA)
_VALIDATOR = Draft202012Validator(
    FOUNDATION_PACKAGE_JSON_SCHEMA,
    format_checker=FormatChecker(),
)


def _load_foundation_2_1_validator() -> Draft202012Validator:
    """Load the 2.1 schema with its bundled typed-manifest dependency."""

    try:
        with SCHEMA_PATH_2_1.open(encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        with DEFINITION_MANIFEST_SCHEMA_PATH.open(encoding="utf-8") as manifest_file:
            manifest_schema = json.load(manifest_file)
    except OSError as exc:
        raise RuntimeError("Foundation 2.1 schemas are not installed.") from exc
    Draft202012Validator.check_schema(manifest_schema)
    Draft202012Validator.check_schema(schema)
    registry = Registry().with_resource(
        manifest_schema["$id"], Resource.from_contents(manifest_schema)
    )
    return Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
        registry=registry,
    )

ENTITY_SECTIONS = (
    "project_definition_versions",
    "time_slices",
    "actors",
    "actor_relations",
    "analytical_elements",
    "actor_element_roles",
    "expert_profiles",
    "experiments",
    "assessment_sets",
    "actor_element_assessments",
    "parameter_definitions",
    "parameter_values",
    "sources",
    "documents",
    "document_versions",
    "document_contents",
    "text_fragments",
    "facts",
    "fact_evidence_links",
    "assessment_fact_links",
    "parameter_value_fact_links",
    "power_profiles",
    "power_components",
    "power_component_fact_links",
    "chat_conversations",
    "chat_messages",
    "chat_citations",
    "gaps",
    "help_topics",
    "ui_help_bindings",
    "terminology_entries",
    "legacy_term_mappings",
)

POWER_COMPONENTS = ("FA", "ER", "OC", "CC", "AL", "IC", "NI", "EB")
RETROSPECTIVE_TEMPORAL_STATUSES = {
    "RETROSPECTIVE_KNOWLEDGE",
    "RETROSPECTIVE_CORROBORATION",
}
ABSENT_VALUE_STATUSES = {
    "UNKNOWN",
    "NOT_APPLICABLE",
    "INSUFFICIENT_DATA",
    "OPEN_METHOD",
}
FORBIDDEN_FIELDS = {
    "total_power",
    "scalar_power",
    "pow",
    "automatic_mean",
    "automatic_weights",
    "formula",
    "calculated_risk",
    "violence_probability",
    "early_warning_score",
}

JsonObject: TypeAlias = Mapping[str, Any]
Adapter: TypeAlias = Callable[[Any], Mapping[str, Any]]


class FoundationPackageError(ValueError):
    """Base error for the Foundation package boundary."""


class FoundationPackageValidationError(FoundationPackageError):
    """The external input cannot become a valid canonical package."""


class FoundationPackageConflictError(FoundationPackageError):
    """A valid package would overwrite or cross a workspace boundary."""


class FoundationPackageAdapter(Protocol):
    """Transport adapter; it must not touch the database."""

    def __call__(self, raw: Any) -> Mapping[str, Any]: ...


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_deep_freeze(item) for item in value)
    return value


def _deep_thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _deep_thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_deep_thaw(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class FoundationImportPreview:
    """Immutable, non-mutating result of canonical validation and DB preflight."""

    valid: bool
    canonical_payload: Mapping[str, Any]
    checksum: str
    counts: Mapping[str, int]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    workspace_id: str
    workspace_code: str
    adapter: str
    selected_input: Mapping[str, Any]
    source_identity_map: Mapping[str, Any]
    correction_lineage: tuple[Mapping[str, Any], ...]
    intended_changes: Mapping[str, Any]
    allow_nonempty: bool

    def payload_copy(self) -> dict[str, Any]:
        return _deep_thaw(self.canonical_payload)

    @property
    def raw_input_kind(self) -> str:
        return str(self.selected_input.get("raw_input_kind", ""))

    @property
    def raw_input_sha256(self) -> str:
        return str(self.selected_input.get("raw_input_sha256", ""))

    @property
    def raw_input_name(self) -> str:
        return str(self.selected_input.get("raw_input_name", ""))


@dataclass(frozen=True, slots=True)
class FoundationImportReceipt:
    """Read-only service view of the append-only ImportRun row."""

    id: str
    code: str
    workspace_id: str
    target_experiment_id: str | None
    target_assessment_set_id: str | None
    package_id: str
    package_format: str
    package_version: str
    schema_version: str
    template_version: str
    method_version: str
    ontology_version: str
    dataset_version: str
    checksum: str
    adapter: str
    selected_input: Mapping[str, Any]
    selected_source_column: str
    source_identity_map: Mapping[str, Any]
    correction_lineage: tuple[Mapping[str, Any], ...]
    intended_changes: Mapping[str, Any]
    row_counts: Mapping[str, int]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    allow_nonempty: bool
    actor_identifier: str
    committed_at: str | None

    @property
    def raw_input_kind(self) -> str:
        return str(self.selected_input.get("raw_input_kind", ""))

    @property
    def raw_input_sha256(self) -> str:
        return str(self.selected_input.get("raw_input_sha256", ""))

    @property
    def raw_input_name(self) -> str:
        return str(self.selected_input.get("raw_input_name", ""))


@dataclass(frozen=True, slots=True)
class FoundationValidationReport:
    """Structured, non-mutating result for UI/command preview orchestration."""

    valid: bool
    preview: FoundationImportPreview | None
    errors: tuple[Mapping[str, str], ...]


@dataclass(frozen=True, slots=True)
class FoundationImportAttemptResult:
    """One complete import attempt, including a durable rejection/failure receipt."""

    status: str
    report: FoundationValidationReport
    receipt: FoundationImportReceipt | None


@dataclass(frozen=True, slots=True)
class Foundation21Preview:
    """Non-mutating preflight for a Foundation 2.1 wrapper."""

    valid: bool
    package_scope: str
    checksum: str
    project_id: str
    project_code: str
    project_version: str
    selected_definition_id: str
    intended_action: str
    errors: tuple[str, ...] = ()
    _payload: Mapping[str, Any] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )
    _workspace_preview: FoundationImportPreview | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def payload_copy(self) -> dict[str, Any]:
        return _deep_thaw(self._payload)


@dataclass(frozen=True, slots=True)
class Foundation21CommitResult:
    """Immutable service result for one explicit 2.1 commit."""

    package_scope: str
    action: str
    definition_id: str
    workspace_id: str | None
    receipt_id: str | None
    checksum: str


_ADAPTERS: dict[str, Adapter] = {}


def register_foundation_adapter(
    name: str,
    adapter: Adapter,
    *,
    replace: bool = False,
) -> None:
    """Register an adapter without coupling canonical validation to its layout."""

    normalized = name.strip().lower()
    if not normalized:
        raise ValueError("Adapter name cannot be empty.")
    if normalized in _ADAPTERS and not replace:
        raise ValueError(f"Foundation adapter {normalized!r} is already registered.")
    _ADAPTERS[normalized] = adapter


def canonical_json(value: Any) -> str:
    """Return deterministic UTF-8 JSON text without insignificant whitespace."""

    return json.dumps(
        _deep_thaw(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _capture_json_input(raw: Any) -> tuple[Any, dict[str, str]]:
    """Freeze exact JSON input provenance before transport adaptation.

    A ``Path`` is read exactly once and its captured bytes are passed to the JSON
    adapter.  A mapping has no original transport bytes, so its fingerprint is
    explicitly over deterministic canonical JSON rather than an invented source
    representation.
    """

    input_name = ""
    if isinstance(raw, Path):
        try:
            snapshot: Any = raw.read_bytes()
        except OSError as exc:
            raise FoundationPackageValidationError(
                f"Cannot read JSON input: {exc}."
            ) from exc
        kind = "PATH_BYTES"
        digest_bytes = snapshot
        input_name = raw.name
    elif isinstance(raw, bytes):
        snapshot = bytes(raw)
        kind = "BYTES"
        digest_bytes = snapshot
    elif isinstance(raw, str):
        if raw.lstrip().startswith(("{", "[")):
            snapshot = raw
            kind = "TEXT"
            digest_bytes = raw.encode("utf-8")
        else:
            path = Path(raw)
            try:
                snapshot = path.read_bytes()
            except OSError as exc:
                raise FoundationPackageValidationError(
                    f"Cannot read JSON input: {exc}."
                ) from exc
            kind = "PATH_BYTES"
            digest_bytes = snapshot
            input_name = path.name
    elif isinstance(raw, Mapping):
        snapshot = copy.deepcopy(dict(raw))
        kind = "CANONICAL_MAPPING"
        digest_bytes = canonical_json(snapshot).encode("utf-8")
    else:
        return raw, {}
    provenance = {
        "raw_input_kind": kind,
        "raw_input_sha256": hashlib.sha256(digest_bytes).hexdigest(),
    }
    if input_name:
        provenance["raw_input_name"] = input_name
    return snapshot, provenance


def _payload_without_manifest(package: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(package))
    payload.pop("manifest", None)
    return payload


def _manifest_for(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical = canonical_json(payload).encode("utf-8")
    counts = {section: len(payload.get(section, [])) for section in ENTITY_SECTIONS}
    counts["compatibility_receipts"] = len(payload.get("compatibility_receipts", []))
    counts["workspace"] = 1
    return {
        "hash_algorithm": HASH_ALGORITHM,
        "payload_sha256": hashlib.sha256(canonical).hexdigest(),
        "entity_counts": counts,
    }


def seal_foundation_package(package: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with the deterministic manifest for its canonical payload."""

    payload = _payload_without_manifest(package)
    payload["manifest"] = _manifest_for(payload)
    return payload


def _json_adapter(raw: Any) -> Mapping[str, Any]:
    if isinstance(raw, Mapping):
        return copy.deepcopy(dict(raw))
    if isinstance(raw, Path):
        try:
            raw = raw.read_text(encoding="utf-8")
        except OSError as exc:
            raise FoundationPackageValidationError(f"Cannot read JSON input: {exc}.") from exc
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise FoundationPackageValidationError("JSON input must be UTF-8.") from exc
    if isinstance(raw, str):
        candidate = raw.lstrip()
        if not candidate.startswith(("{", "[")):
            path = Path(raw)
            try:
                raw = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise FoundationPackageValidationError(f"Cannot read JSON input: {exc}.") from exc
        try:
            decoded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FoundationPackageValidationError(
                f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}."
            ) from exc
        if not isinstance(decoded, Mapping):
            raise FoundationPackageValidationError("Canonical JSON root must be an object.")
        return decoded
    raise FoundationPackageValidationError(
        f"Unsupported JSON input type {type(raw).__name__}."
    )


register_foundation_adapter("json", _json_adapter)


def _xlsx_adapter(raw: Any) -> Mapping[str, Any]:
    from domain.services.xlsx_adapter import (
        FoundationXlsxAdapterError,
        adapt_foundation_xlsx,
    )

    try:
        adapted = adapt_foundation_xlsx(raw)
        if adapted.get("__xlsx_profile__"):
            return adapted
        return seal_foundation_package(adapted)
    except FoundationXlsxAdapterError as exc:
        raise FoundationPackageValidationError(str(exc)) from exc


register_foundation_adapter("xlsx", _xlsx_adapter)


def adapt_foundation_input(raw: Any, *, adapter: str = "json") -> dict[str, Any]:
    """Convert external input to a mutable canonical DTO without DB access."""

    normalized = adapter.strip().lower()
    try:
        adapted = _ADAPTERS[normalized](raw)
    except KeyError as exc:
        raise FoundationPackageValidationError(
            f"Unknown Foundation adapter {normalized!r}; registered={sorted(_ADAPTERS)}."
        ) from exc
    if not isinstance(adapted, Mapping):
        raise FoundationPackageValidationError("Adapter output must be a JSON object.")
    return copy.deepcopy(dict(adapted))


def _reject(message: str) -> None:
    raise FoundationPackageValidationError(message)


def _schema_validate(package: Mapping[str, Any]) -> None:
    errors = sorted(
        _VALIDATOR.iter_errors(package),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    error = errors[0]
    path = ".".join(str(part) for part in error.absolute_path) or "package"
    _reject(f"JSON Schema validation failed at {path}: {error.message}")


def _by_code(package: Mapping[str, Any], section: str) -> dict[str, Mapping[str, Any]]:
    found: dict[str, Mapping[str, Any]] = {}
    ids: set[str] = set()
    for index, item in enumerate(package[section]):
        code = item["code"]
        stable_id = item.get("id")
        if code in found:
            _reject(f"{section}[{index}].code duplicates {code!r}.")
        if stable_id is not None and stable_id in ids:
            _reject(f"{section}[{index}].id duplicates {stable_id!r}.")
        found[code] = item
        if stable_id is not None:
            ids.add(stable_id)
    return found


def _ref(
    item: Mapping[str, Any],
    field: str,
    index: Mapping[str, Any],
    path: str,
    *,
    nullable: bool = False,
) -> str | None:
    value = item.get(field)
    if value is None and nullable:
        return None
    if not isinstance(value, str) or value not in index:
        _reject(f"{path}.{field} references an unknown package-local stable code {value!r}.")
    return value


def _parse_date(value: Any, path: str) -> date:
    if not isinstance(value, str):
        _reject(f"{path} must be an ISO date.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FoundationPackageValidationError(f"{path} must be an ISO date.") from exc


def _date_or_none(value: Any, path: str) -> date | None:
    return None if value is None else _parse_date(value, path)


def _parse_datetime(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        _reject(f"{path} must be an ISO datetime.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FoundationPackageValidationError(f"{path} must be an ISO datetime.") from exc
    if parsed.tzinfo is None:
        _reject(f"{path} must include a timezone.")
    return parsed


def _datetime_or_none(value: Any, path: str) -> datetime | None:
    return None if value is None else _parse_datetime(value, path)


def _decimal_or_none(value: Any, path: str) -> Decimal | None:
    return None if value is None else _number(value, path)


def _number(value: Any, path: str) -> Decimal:
    if isinstance(value, bool):
        _reject(f"{path} must be numeric.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FoundationPackageValidationError(f"{path} must be numeric.") from exc
    if not parsed.is_finite():
        _reject(f"{path} must be finite.")
    return parsed


def _decode_content(item: Mapping[str, Any], path: str) -> bytes:
    encoding = item.get("encoding", "UTF8")
    content = item.get("content")
    if not isinstance(content, str):
        _reject(f"{path}.content must be text.")
    if encoding == "UTF8":
        return content.encode("utf-8")
    if encoding == "BASE64":
        try:
            return base64.b64decode(content, validate=True)
        except ValueError as exc:
            raise FoundationPackageValidationError(f"{path}.content is not valid base64.") from exc
    _reject(f"{path}.encoding must be UTF8 or BASE64.")
    raise AssertionError("unreachable")


def _scan_forbidden_fields(value: Any, path: str = "package") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = key.lower()
            if normalized in FORBIDDEN_FIELDS:
                _reject(f"{path}.{key} is forbidden by the Foundation contract.")
            _scan_forbidden_fields(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _scan_forbidden_fields(item, f"{path}[{index}]")


def _validate_semantics(package: Mapping[str, Any]) -> tuple[str, ...]:
    """Validate identities, references, anchors, cutoff and orthogonal values."""

    _scan_forbidden_fields(package)
    indices = {section: _by_code(package, section) for section in ENTITY_SECTIONS}
    warnings: list[str] = []
    forbidden_numeric_identities = {
        "TOTAL_POWER",
        "POW",
        "SCALAR_POWER",
        "AUTOMATIC_MEAN",
        "AUTOMATIC_WEIGHTS",
    }
    for index, item in enumerate(package["parameter_definitions"]):
        if item["code"].upper() in forbidden_numeric_identities:
            _reject(
                f"parameter_definitions[{index}].code {item['code']!r} is a forbidden "
                "scalar/automatic Power numeric lane."
            )

    for section in ("actors", "analytical_elements"):
        for index, item in enumerate(package[section]):
            _ref(
                item,
                "parent_code",
                indices[section],
                f"{section}[{index}]",
                nullable=True,
            )

    for index, item in enumerate(package["actor_relations"]):
        path = f"actor_relations[{index}]"
        source_code = _ref(item, "source_actor_code", indices["actors"], path)
        target_code = _ref(item, "target_actor_code", indices["actors"], path)
        if source_code == target_code:
            _reject(f"{path} requires distinct source and target actors.")

    for index, item in enumerate(package["actor_element_roles"]):
        path = f"actor_element_roles[{index}]"
        _ref(item, "actor_code", indices["actors"], path)
        _ref(item, "element_code", indices["analytical_elements"], path)

    for index, item in enumerate(package["experiments"]):
        path = f"experiments[{index}]"
        profile_code = _ref(item, "expert_profile_code", indices["expert_profiles"], path)
        set_code = _ref(item, "assessment_set_code", indices["assessment_sets"], path)
        if item["experiment_type"] == "MODELING" and item["status"] != "DRAFT":
            _reject(f"{path} MODELING is reserved but disabled outside DRAFT metadata.")
        if item["experiment_type"] == "ASSESSMENT":
            if indices["expert_profiles"][profile_code]["kind"] != indices["assessment_sets"][set_code]["kind"]:
                _reject(f"{path} ExpertProfile and AssessmentSet HUMAN/AI lanes differ.")

    for index, item in enumerate(package["actor_element_assessments"]):
        path = f"actor_element_assessments[{index}]"
        _ref(item, "assessment_set_code", indices["assessment_sets"], path)
        experiment_code = _ref(item, "experiment_code", indices["experiments"], path)
        if indices["experiments"][experiment_code]["assessment_set_code"] != item["assessment_set_code"]:
            _reject(f"{path}.assessment_set_code differs from its independent Experiment binding.")
        _ref(item, "actor_code", indices["actors"], path)
        _ref(item, "element_code", indices["analytical_elements"], path)
        _ref(item, "time_slice_code", indices["time_slices"], path)
        _parse_date(item.get("knowledge_cutoff"), f"{path}.knowledge_cutoff")
        supersedes_code = _ref(
            item,
            "supersedes_code",
            indices["actor_element_assessments"],
            path,
            nullable=True,
        )
        if supersedes_code is not None:
            previous = indices["actor_element_assessments"][supersedes_code]
            context_fields = (
                "actor_code",
                "element_code",
                "time_slice_code",
                "assessment_set_code",
            )
            if any(previous[field] != item[field] for field in context_fields):
                _reject(f"{path}.supersedes_code must preserve the exact assessment context.")
            if previous["version"] == item["version"]:
                _reject(f"{path} successor requires a distinct version.")

    for index, item in enumerate(package["parameter_values"]):
        path = f"parameter_values[{index}]"
        _ref(item, "assessment_code", indices["actor_element_assessments"], path)
        _ref(item, "assessment_set_code", indices["assessment_sets"], path)
        _ref(item, "parameter_definition_code", indices["parameter_definitions"], path)
        supersedes_code = _ref(
            item,
            "supersedes_code",
            indices["parameter_values"],
            path,
            nullable=True,
        )
        if supersedes_code is not None:
            previous = indices["parameter_values"][supersedes_code]
            context_fields = (
                "assessment_code",
                "assessment_set_code",
                "parameter_definition_code",
            )
            if any(previous[field] != item[field] for field in context_fields):
                _reject(f"{path}.supersedes_code must preserve the exact value context.")
            if previous["version"] == item["version"]:
                _reject(f"{path} successor requires a distinct version.")
        status = item.get("status")
        value = item.get("value")
        temporal_status = item.get("temporal_status")
        if status in ABSENT_VALUE_STATUSES and value is not None:
            _reject(f"{path}.value must be null for status {status}; UNKNOWN is not zero.")
        if status not in ABSENT_VALUE_STATUSES and value is None:
            _reject(f"{path}.value is required for present status {status!r}.")
        if temporal_status == "NO_DIRECT_POSITION" and status != "UNKNOWN":
            _reject(f"{path}.temporal_status NO_DIRECT_POSITION requires explicit UNKNOWN/null.")
        # DISPUTED is still a per-assessment value lane.  Independent numeric
        # records remain intact; this service never computes consensus/averages.
        confidence = item.get("confidence")
        if confidence is not None:
            parsed = _number(confidence, f"{path}.confidence")
            if parsed < 0 or parsed > 100:
                _reject(f"{path}.confidence must be in the canonical 0..100 coder scale.")

        definition = indices["parameter_definitions"][item["parameter_definition_code"]]
        if (
            value is not None
            and definition["value_type"] in {"INTEGER", "DECIMAL"}
            and not any(
                link.get("parameter_value_code") == item["code"]
                for link in package["parameter_value_fact_links"]
            )
        ):
            numeric_value = _number(value, f"{path}.value")
            boundaries = {
                _number(boundary, f"{path}.definition_boundary")
                for boundary in (definition.get("scale_min"), definition.get("scale_max"))
                if boundary is not None
            }
            if numeric_value in boundaries and "STRONG_VALUE_LOW_EVIDENCE" not in warnings:
                # This is a non-mutating quality flag, not a weighting rule or formula.
                warnings.append("STRONG_VALUE_LOW_EVIDENCE")

    for index, item in enumerate(package["documents"]):
        _ref(item, "source_code", indices["sources"], f"documents[{index}]")

    for index, item in enumerate(package["document_versions"]):
        path = f"document_versions[{index}]"
        document_code = _ref(item, "document_code", indices["documents"], path)
        supersedes_code = _ref(
            item,
            "supersedes_code",
            indices["document_versions"],
            path,
            nullable=True,
        )
        if supersedes_code and indices["document_versions"][supersedes_code]["document_code"] != document_code:
            _reject(f"{path}.supersedes_code cannot cross Documents.")

    content_by_version: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(package["document_contents"]):
        path = f"document_contents[{index}]"
        version_code = _ref(item, "document_version_code", indices["document_versions"], path)
        if version_code in content_by_version:
            _reject(f"{path}.document_version_code duplicates immutable content.")
        content = _decode_content(item, path)
        digest = hashlib.sha256(content).hexdigest()
        if item.get("checksum") != digest:
            _reject(f"{path}.checksum does not match the immutable content bytes.")
        version = indices["document_versions"][version_code]
        if version.get("checksum") != digest:
            _reject(f"{path} does not match its DocumentVersion checksum.")
        content_by_version[version_code] = item

    gaps_by_version = {
        item.get("document_version_code")
        for item in package["gaps"]
        if item.get("type") == "FULL_DOCUMENT_BYTES_NOT_INGESTED"
        and item.get("status") == "OPEN"
    }
    for index, item in enumerate(package["gaps"]):
        if item.get("status") != "OPEN" or item.get("type") != "FULL_DOCUMENT_BYTES_NOT_INGESTED":
            continue
        affected = item.get("metadata", {}).get("affected_document_version_codes", [])
        if not isinstance(affected, list):
            _reject(f"gaps[{index}].metadata.affected_document_version_codes must be an array.")
        for version_code in affected:
            if not isinstance(version_code, str) or version_code not in indices["document_versions"]:
                _reject(f"gaps[{index}] names an unknown affected DocumentVersion {version_code!r}.")
            gaps_by_version.add(version_code)
    for code, item in indices["document_versions"].items():
        checksum = item.get("checksum")
        if checksum is None and code not in gaps_by_version:
            _reject(
                f"document_versions[{code!r}] lacks immutable bytes/checksum and an explicit gap."
            )
        if checksum is not None and (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(char not in "0123456789abcdef" for char in checksum)
        ):
            _reject(f"document_versions[{code!r}].checksum must be a SHA-256 digest or null.")

    for index, item in enumerate(package["gaps"]):
        path = f"gaps[{index}]"
        version_code = _ref(
            item,
            "document_version_code",
            indices["document_versions"],
            path,
            nullable=True,
        )
        if item["status"] == "RESOLVED":
            if not item["resolution"].strip():
                _reject(f"{path}.resolution is required for a resolved gap.")
            if (
                item["type"] == "FULL_DOCUMENT_BYTES_NOT_INGESTED"
                and version_code is not None
                and (
                    not indices["document_versions"][version_code].get("checksum")
                    or version_code not in content_by_version
                )
            ):
                _reject(f"{path} cannot resolve missing bytes until immutable content is ingested.")

    fragment_version: dict[str, str] = {}
    for index, item in enumerate(package["text_fragments"]):
        path = f"text_fragments[{index}]"
        version_code = _ref(item, "document_version_code", indices["document_versions"], path)
        anchor_status = item["anchor_status"]
        exact_text = item.get("exact_text")
        if not isinstance(exact_text, str):
            _reject(f"{path}.exact_text must be text.")
        start = item.get("start_offset")
        end = item.get("end_offset")
        if anchor_status == "EXACT":
            digest = hashlib.sha256(exact_text.encode("utf-8")).hexdigest()
            if item.get("exact_text_sha256") != digest:
                _reject(f"{path}.exact_text_sha256 does not match exact_text.")
            if not isinstance(start, int) or isinstance(start, bool) or start < 0:
                _reject(f"{path}.start_offset must be a non-negative integer.")
            if not isinstance(end, int) or isinstance(end, bool) or end <= start:
                _reject(f"{path}.end_offset must be greater than start_offset.")
            content_item = content_by_version.get(version_code)
            if content_item is None or content_item.get("encoding", "UTF8") != "UTF8":
                _reject(f"{path} exact anchor requires immutable normalized UTF-8 content.")
            if content_item["content"][start:end] != exact_text:
                _reject(f"{path} anchor does not resolve exactly; silent re-anchoring is forbidden.")
        elif anchor_status == "HASH_RECORDED_PENDING_INGEST":
            recorded = item.get("exact_text_sha256")
            if not recorded:
                _reject(f"{path} pending-ingest anchor requires the recorded fragment hash.")
            if any(value not in (None, "", {}) for value in (start, end, item["selector"])):
                _reject(
                    f"{path} pending-ingest fragment cannot claim an exact anchor "
                    "before ingest (offsets/selector are forbidden)."
                )
            if exact_text and hashlib.sha256(exact_text.encode("utf-8")).hexdigest() != recorded:
                _reject(f"{path}.exact_text_sha256 does not match the captured fragment text.")
            if version_code not in gaps_by_version:
                _reject(f"{path} pending-ingest hash requires an explicit document-bytes gap.")
        elif anchor_status in {"URL_ONLY", "UNRESOLVED"}:
            if any(
                value not in (None, "", {})
                for value in (start, end, item["selector"], exact_text, item.get("exact_text_sha256"))
            ):
                _reject(f"{path} unresolved anchor cannot claim offsets/text/hash.")
        else:
            _reject(f"{path}.anchor_status {anchor_status!r} is not importable.")
        fragment_version[item["code"]] = version_code

    for index, item in enumerate(package["fact_evidence_links"]):
        path = f"fact_evidence_links[{index}]"
        _ref(item, "fact_code", indices["facts"], path)
        _ref(item, "fragment_code", indices["text_fragments"], path)

    for index, item in enumerate(package["facts"]):
        path = f"facts[{index}]"
        _ref(
            item,
            "experiment_code",
            indices["experiments"],
            path,
            nullable=True,
        )
        confidence = item.get("confidence")
        if confidence is not None:
            parsed = _number(confidence, f"{path}.confidence")
            if parsed < 0 or parsed > 100:
                _reject(f"{path}.confidence must be in the canonical 0..100 coder scale.")

    exact_fact_chain = {
        link["fact_code"]
        for link in package["fact_evidence_links"]
        if indices["text_fragments"][link["fragment_code"]]["anchor_status"] == "EXACT"
    }
    for section in (
        "facts",
        "actor_element_assessments",
        "parameter_values",
    ):
        for item in package[section]:
            if item.get("status") != "CONFIRMED":
                continue
            if section == "facts":
                complete = item["code"] in exact_fact_chain
            elif section == "actor_element_assessments":
                complete = any(
                    link["assessment_code"] == item["code"]
                    and link["fact_code"] in exact_fact_chain
                    and link["role"]
                    in {
                        "PRIMARY_SUPPORT",
                        "SECONDARY_SUPPORT",
                        "SUPPORTS_POSITION",
                        "SUPPORTS_SALIENCE",
                        "SUPPORTS_POSITION_AND_SALIENCE",
                    }
                    for link in package["assessment_fact_links"]
                )
            else:
                complete = any(
                    link["parameter_value_code"] == item["code"]
                    and link["fact_code"] in exact_fact_chain
                    and link["role"]
                    in {
                        "PRIMARY_SUPPORT",
                        "SECONDARY_SUPPORT",
                        "SUPPORTS_POSITION",
                        "SUPPORTS_SALIENCE",
                        "SUPPORTS_POSITION_AND_SALIENCE",
                    }
                    for link in package["parameter_value_fact_links"]
                )
            if not complete:
                _reject(
                    "CONFIRMED_EVIDENCE_CHAIN_INCOMPLETE:"
                    f"{section}:{item['code']}"
                )

    for index, item in enumerate(package["assessment_fact_links"]):
        path = f"assessment_fact_links[{index}]"
        assessment_code = _ref(
            item, "assessment_code", indices["actor_element_assessments"], path
        )
        fact_code = _ref(item, "fact_code", indices["facts"], path)
        cutoff = _parse_date(
            indices["actor_element_assessments"][assessment_code]["knowledge_cutoff"],
            f"{path}.knowledge_cutoff",
        )
        temporal_status = item.get("temporal_status", "UNKNOWN")
        linked_fragments = [
            link["fragment_code"]
            for link in package["fact_evidence_links"]
            if link.get("fact_code") == fact_code
        ]
        for fragment_code in linked_fragments:
            version = indices["document_versions"][fragment_version[fragment_code]]
            document = indices["documents"][version["document_code"]]
            published_on = document.get("published_on")
            if published_on is not None and _parse_date(published_on, f"{path}.published_on") > cutoff:
                if temporal_status not in RETROSPECTIVE_TEMPORAL_STATUSES:
                    _reject(
                        f"{path} uses post-cutoff evidence without explicit retrospective provenance."
                    )

    for index, item in enumerate(package["parameter_value_fact_links"]):
        path = f"parameter_value_fact_links[{index}]"
        value_code = _ref(item, "parameter_value_code", indices["parameter_values"], path)
        fact_code = _ref(item, "fact_code", indices["facts"], path)
        assessment_code = indices["parameter_values"][value_code]["assessment_code"]
        cutoff = _parse_date(
            indices["actor_element_assessments"][assessment_code]["knowledge_cutoff"],
            f"{path}.knowledge_cutoff",
        )
        temporal_status = item.get("temporal_status", "UNKNOWN")
        linked_fragments = [
            link["fragment_code"]
            for link in package["fact_evidence_links"]
            if link.get("fact_code") == fact_code
        ]
        for fragment_code in linked_fragments:
            version = indices["document_versions"][fragment_version[fragment_code]]
            document = indices["documents"][version["document_code"]]
            published_on = document.get("published_on")
            if published_on is not None and _parse_date(published_on, f"{path}.published_on") > cutoff:
                if temporal_status not in RETROSPECTIVE_TEMPORAL_STATUSES:
                    _reject(
                        f"{path} uses post-cutoff evidence without explicit retrospective provenance."
                    )

    allowed_power_fields = {
        "id",
        "code",
        "version",
        "metadata",
        "assessment_code",
        "method_version",
        "note",
    }
    for index, item in enumerate(package["power_profiles"]):
        path = f"power_profiles[{index}]"
        _ref(item, "assessment_code", indices["actor_element_assessments"], path)
        unexpected = set(item) - allowed_power_fields
        if unexpected:
            _reject(f"{path} contains non-vector Power fields {sorted(unexpected)}.")
    components_by_profile: dict[str, set[str]] = {}
    for index, item in enumerate(package["power_components"]):
        path = f"power_components[{index}]"
        profile_code = _ref(item, "profile_code", indices["power_profiles"], path)
        dimension = item.get("dimension")
        if dimension not in POWER_COMPONENTS:
            _reject(f"{path}.dimension must be one of the eight separate Power dimensions.")
        if dimension in components_by_profile.setdefault(profile_code, set()):
            _reject(f"{path}.dimension duplicates {dimension} within one profile.")
        components_by_profile[profile_code].add(dimension)
        status = item.get("status")
        value = item.get("value")
        if status in ABSENT_VALUE_STATUSES and value is not None:
            _reject(f"{path}.value must be null for status {status}.")
        if status not in ABSENT_VALUE_STATUSES and value is None:
            _reject(f"{path}.value is required for present status {status!r}.")
        confidence = item.get("confidence")
        if confidence is not None:
            parsed = _number(confidence, f"{path}.confidence")
            if parsed < 0 or parsed > 100:
                _reject(f"{path}.confidence must be in the canonical 0..100 coder scale.")
    for profile_code in indices["power_profiles"]:
        if components_by_profile.get(profile_code, set()) != set(POWER_COMPONENTS):
            _reject(f"power_profiles[{profile_code!r}] must have exactly eight separate components.")

    for index, item in enumerate(package["power_component_fact_links"]):
        path = f"power_component_fact_links[{index}]"
        _ref(item, "component_code", indices["power_components"], path)
        _ref(item, "fact_code", indices["facts"], path)

    for index, item in enumerate(package["chat_messages"]):
        path = f"chat_messages[{index}]"
        _ref(item, "conversation_code", indices["chat_conversations"], path)
        if item["status"] == "ERROR" and not item["error"].strip():
            _reject(f"{path}.error is required when status is ERROR.")
        if item["status"] == "COMPLETE" and item["error"]:
            _reject(f"{path}.error must be empty when status is COMPLETE.")

    fact_fragment_pairs = {
        (item["fact_code"], item["fragment_code"])
        for item in package["fact_evidence_links"]
    }
    for index, item in enumerate(package["chat_citations"]):
        path = f"chat_citations[{index}]"
        _ref(item, "message_code", indices["chat_messages"], path)
        fact_code = _ref(item, "fact_code", indices["facts"], path, nullable=True)
        fragment_code = _ref(
            item, "fragment_code", indices["text_fragments"], path, nullable=True
        )
        version_code = _ref(
            item,
            "document_version_code",
            indices["document_versions"],
            path,
            nullable=True,
        )
        if fragment_code is None:
            if fact_code is None or any(
                item[field] is not None
                for field in ("document_version_code", "quote_start", "quote_end")
            ) or item["quote_text"]:
                _reject(f"{path} fact-only citation cannot carry a fragment quote span.")
            continue
        if version_code is None:
            _reject(f"{path} fragment citation requires its exact DocumentVersion.")
        if fragment_version[fragment_code] != version_code:
            _reject(f"{path}.document_version_code must be the fragment's exact immutable version.")
        start, end = item["quote_start"], item["quote_end"]
        exact_text = indices["text_fragments"][fragment_code]["exact_text"]
        if start >= end or end > len(exact_text):
            _reject(f"{path} quote span is outside the exact TextFragment.")
        if exact_text[start:end] != item["quote_text"]:
            _reject(f"{path}.quote_text does not match the exact fragment span.")
        if fact_code is not None and (fact_code, fragment_code) not in fact_fragment_pairs:
            _reject(f"{path}.fact_code requires an explicit FactEvidence link to the fragment.")

    for index, item in enumerate(package["legacy_term_mappings"]):
        _ref(
            item,
            "terminology_entry_code",
            indices["terminology_entries"],
            f"legacy_term_mappings[{index}]",
            nullable=True,
        )

    for index, item in enumerate(package["ui_help_bindings"]):
        path = f"ui_help_bindings[{index}]"
        topic_code = _ref(item, "help_topic_code", indices["help_topics"], path)
        if not item.get("ui_key") or not item.get("locale") or not item.get("topic_version"):
            _reject(f"{path} requires stable ui_key, locale and exact topic_version.")
        topic = indices["help_topics"][topic_code]
        if topic["locale"] != item["locale"] or topic["version"] != item["topic_version"]:
            _reject(f"{path} must bind the exact HelpTopic locale/version.")

    from domain.services.help_topics import sanitize_help_html

    for index, item in enumerate(package["help_topics"]):
        path = f"help_topics[{index}]"
        html = item["sanitized_html"]
        if sanitize_help_html(html) != html:
            _reject(f"{path}.sanitized_html contains markup outside the allowlist.")
        if hashlib.sha256(html.encode("utf-8")).hexdigest() != item["content_sha256"]:
            _reject(f"{path}.content_sha256 does not match sanitized_html.")

    warnings.extend(
        f"LEGACY_MAPPING_UNRESOLVED:{item['legacy_model']}:{item['legacy_code']}"
        for item in package["compatibility_receipts"]
        if item["status"] == "UNRESOLVED"
    )
    receipt_ids: set[str] = set()
    receipt_codes: set[str] = set()
    for index, item in enumerate(package["compatibility_receipts"]):
        path = f"compatibility_receipts[{index}]"
        if item["id"] in receipt_ids or item["code"] in receipt_codes:
            _reject(f"{path} duplicates a compatibility receipt identity.")
        receipt_ids.add(item["id"])
        receipt_codes.add(item["code"])
        has_canonical = bool(
            item["canonical_model"] and item["canonical_id"] and item["canonical_code"]
        )
        if item["status"] == "MIGRATED" and not has_canonical:
            _reject(f"{path} MIGRATED receipt requires the exact canonical identity.")
        if item["status"] == "UNRESOLVED" and has_canonical:
            _reject(f"{path} UNRESOLVED receipt cannot claim a canonical migration.")
    return tuple(warnings)


def validate_foundation_package(package: Mapping[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Validate and return an isolated canonical copy plus compatibility warnings."""

    canonical = copy.deepcopy(dict(package))
    _schema_validate(canonical)
    expected_manifest = _manifest_for(_payload_without_manifest(canonical))
    if canonical["manifest"] != expected_manifest:
        _reject("Package manifest, entity counts or SHA-256 checksum is invalid.")
    warnings = _validate_semantics(canonical)
    return canonical, warnings


def _payload_without_manifest_2_1(package: Mapping[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(dict(package))
    payload.pop("manifest", None)
    return payload


def _manifest_for_2_1(payload: Mapping[str, Any]) -> dict[str, str]:
    return {
        "hash_algorithm": HASH_ALGORITHM,
        "payload_sha256": hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest(),
    }


def seal_foundation_package_2_1(package: Mapping[str, Any]) -> dict[str, Any]:
    """Seal one explicit 2.1 scope without altering a nested 2.0 package."""

    payload = _payload_without_manifest_2_1(package)
    payload["manifest"] = _manifest_for_2_1(payload)
    return payload


def _schema_error_message_2_1(error: Any) -> str:
    path = ".".join(str(part) for part in error.absolute_path) or "package"
    return f"JSON Schema 2.1 validation failed at {path}: {error.message}"


def validate_foundation_package_2_1(package: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the typed 2.1 envelope with strict legacy dispatch."""

    canonical = copy.deepcopy(dict(package))
    validator = _load_foundation_2_1_validator()
    errors = sorted(
        validator.iter_errors(canonical),
        key=lambda error: (
            tuple(str(part) for part in error.absolute_path),
            error.message,
        ),
    )
    if errors:
        raise FoundationPackageValidationError(_schema_error_message_2_1(errors[0]))
    expected_manifest = _manifest_for_2_1(_payload_without_manifest_2_1(canonical))
    if canonical["manifest"] != expected_manifest:
        raise FoundationPackageValidationError(
            "Foundation 2.1 manifest SHA-256 does not match its exact payload."
        )

    scope = canonical["package_scope"]
    if scope == "WORKSPACE":
        nested, _warnings = validate_foundation_package(canonical["workspace_package"])
        if nested["format_version"] != FOUNDATION_PACKAGE_VERSION:
            raise FoundationPackageValidationError(
                "A 2.1 WORKSPACE wrapper must preserve one exact Foundation 2.0.0 payload."
            )
        if canonical["workspace"] != nested["workspace"]:
            raise FoundationPackageValidationError(
                "The 2.1 workspace identity must equal the nested canonical workspace."
            )
        if (
            canonical["selected_definition_id"]
            != nested["workspace"]["project_definition_version_id"]
        ):
            raise FoundationPackageValidationError(
                "selected_definition_id must equal the nested workspace definition pin."
            )
        return canonical

    definition = canonical["project_definition"]
    if definition["id"] != canonical["selected_definition_id"]:
        raise FoundationPackageValidationError(
            "selected_definition_id must equal the exact project definition identity."
        )
    from domain.services.project_definitions import (
        hash_project_definition_manifest_v1,
        identify_typed_project_definition_manifest,
    )

    if not identify_typed_project_definition_manifest(definition["manifest"]):
        raise FoundationPackageValidationError(
            "PROJECT_DEFINITION scope requires the exact typed V1 manifest envelope."
        )
    actual_hash = hash_project_definition_manifest_v1(definition["manifest"])
    if actual_hash != definition["manifest_hash"]:
        raise FoundationPackageValidationError(
            "Project definition manifest_hash does not match canonical typed bytes."
        )
    status = definition["publication_status"]
    if status == "DRAFT":
        if any(
            (
                definition["validated_at"] is not None,
                bool(definition["validated_by"]),
                bool(definition["validation_result"]),
                definition["published_at"] is not None,
                bool(definition["published_by"]),
                definition["is_current"],
            )
        ):
            raise FoundationPackageValidationError(
                "A DRAFT definition cannot claim validation or publication state."
            )
    elif status == "VALIDATED":
        if (
            definition["validated_at"] is None
            or not definition["validated_by"]
            or definition["validation_result"].get("valid") is not True
            or definition["published_at"] is not None
            or definition["published_by"]
        ):
            raise FoundationPackageValidationError(
                "A VALIDATED definition requires exact successful validation metadata only."
            )
    else:
        if (
            definition["validated_at"] is None
            or not definition["validated_by"]
            or definition["validation_result"].get("valid") is not True
            or definition["published_at"] is None
            or not definition["published_by"]
        ):
            raise FoundationPackageValidationError(
                "A published definition requires exact validation and publication metadata."
            )
    return canonical


def _workspace_identity(workspace: Any) -> tuple[str, str]:
    if workspace is None or getattr(workspace, "pk", None) is None:
        raise FoundationPackageConflictError("A persisted target workspace is required.")
    if workspace.__class__.__name__ != "ProjectWorkspace":
        raise FoundationPackageConflictError("Target must be a ProjectWorkspace instance.")
    return str(workspace.pk), str(workspace.code)


def _validate_workspace_definition(package: Mapping[str, Any], workspace: Any) -> None:
    declared = package["workspace"]
    definition = workspace.definition_version
    if len(package["project_definition_versions"]) != 1:
        raise FoundationPackageConflictError(
            "A workspace package must contain exactly its pinned ProjectDefinitionVersion; "
            "additional definition rows cannot be silently ignored."
        )
    if declared["project_definition_version_id"] != str(definition.pk):
        raise FoundationPackageConflictError(
            "Package pins a different ProjectDefinitionVersion UUID."
        )
    if declared["project_definition_hash"] != workspace.definition_manifest_hash:
        raise FoundationPackageConflictError(
            "Package ProjectDefinitionVersion checksum differs from the exact workspace pin."
        )
    matching = [
        item
        for item in package["project_definition_versions"]
        if item["id"] == str(definition.pk)
    ]
    if len(matching) != 1 or matching[0]["manifest_hash"] != definition.manifest_hash:
        raise FoundationPackageConflictError(
            "Canonical package must contain the exact pinned ProjectDefinitionVersion/hash."
        )
    expected = _export_definition(definition)
    supplied = dict(matching[0])
    supplied_published = supplied.pop("published_at")
    expected_published = expected.pop("published_at")
    if (
        supplied != expected
        or _parse_datetime(supplied_published, "project_definition_versions.published_at")
        != _parse_datetime(expected_published, "project_definition_versions.published_at")
    ):
        raise FoundationPackageConflictError(
            "Canonical ProjectDefinitionVersion differs from the exact pinned row."
        )


def _resolve_selected_lane(
    package: Mapping[str, Any],
    *,
    workspace: Any,
    selected_input: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Resolve an explicit existing lane without treating display labels as identity.

    A selected lane is an append target, never an update instruction.  The package
    must repeat the exact stable UUID/code/version and immutable lane metadata so a
    stale selection cannot silently bind to a different coder or AssessmentSet.
    """

    experiment_raw = selected_input.get("target_experiment_id")
    set_raw = selected_input.get("target_assessment_set_id")
    if experiment_raw is None and set_raw is None:
        return {}, dict(selected_input)
    if experiment_raw is None or set_raw is None:
        raise FoundationPackageConflictError(
            "selected_input must provide target_experiment_id and "
            "target_assessment_set_id together."
        )
    try:
        experiment_id = UUID(str(experiment_raw))
        assessment_set_id = UUID(str(set_raw))
    except (TypeError, ValueError) as exc:
        raise FoundationPackageConflictError(
            "Selected Experiment and AssessmentSet identities must be UUIDs."
        ) from exc

    Experiment = _model("Experiment")
    AssessmentSet = _model("AssessmentSet")
    experiment = (
        Experiment.objects.select_related("expert_profile", "assessment_set")
        .filter(pk=experiment_id, workspace=workspace)
        .first()
    )
    assessment_set = AssessmentSet.objects.filter(
        pk=assessment_set_id, workspace=workspace
    ).first()
    if experiment is None or assessment_set is None:
        raise FoundationPackageConflictError(
            "Selected Experiment/AssessmentSet does not exist in the exact target workspace."
        )
    if experiment.assessment_set_id != assessment_set.pk:
        raise FoundationPackageConflictError(
            "Selected Experiment is not bound to the selected AssessmentSet."
        )

    selected_rows = {
        "experiments": experiment,
        "assessment_sets": assessment_set,
        "expert_profiles": experiment.expert_profile,
    }
    expected_lane_ids = {
        "experiments": {str(experiment.pk)},
        "assessment_sets": {str(assessment_set.pk)},
        "expert_profiles": {str(experiment.expert_profile_id)},
    }
    for section, expected_ids in expected_lane_ids.items():
        supplied_ids = {item["id"] for item in package[section]}
        if supplied_ids != expected_ids:
            raise FoundationPackageConflictError(
                f"Selected-lane package must contain only the exact target {section} row."
            )
    target_assessment_codes = {
        item["code"]
        for item in package["actor_element_assessments"]
        if item["experiment_code"] == experiment.code
        and item["assessment_set_code"] == assessment_set.code
    }
    if len(target_assessment_codes) != len(package["actor_element_assessments"]):
        raise FoundationPackageConflictError(
            "Selected-lane package contains an assessment owned by another lane."
        )
    if any(
        item["assessment_code"] not in target_assessment_codes
        or item["assessment_set_code"] != assessment_set.code
        for item in package["parameter_values"]
    ):
        raise FoundationPackageConflictError(
            "Selected-lane package contains a ParameterValue owned by another lane."
        )
    if any(
        item["experiment_code"] not in {None, experiment.code}
        for item in package["facts"]
    ):
        raise FoundationPackageConflictError(
            "Selected-lane package contains a Fact owned by another Experiment."
        )
    package_indices = {
        section: {item["id"]: item for item in package[section]}
        for section in selected_rows
    }
    reusable: dict[str, dict[str, Any]] = {}
    for section, existing in selected_rows.items():
        item = package_indices[section].get(str(existing.pk))
        if item is None or not _matches_reusable(section, item, existing):
            raise FoundationPackageConflictError(
                f"Selected {section} identity is absent, stale, or differs from the exact package row."
            )
        reusable[section] = {item["code"]: existing}

    # The canonical DTO is post-selection and may repeat exact workspace master
    # rows needed by the chosen lane.  Reuse is permitted only after an explicit
    # lane selection and only when the complete export representation is equal.
    for spec in _materialization_specs():
        section = spec["section"]
        for item in package[section]:
            existing = _existing_for_item(spec["model"], item, workspace, spec)
            if existing is not None and _matches_reusable(section, item, existing):
                reusable.setdefault(section, {})[item["code"]] = existing

    if experiment.status == "FROZEN":
        # A selected frozen lane is read-only.  Reject every would-be insertion,
        # including facts and transitive evidence/link rows, before materializing.
        for spec in _materialization_specs():
            section = spec["section"]
            for item in package[section]:
                if _existing_for_item(spec["model"], item, workspace, spec) is None:
                    raise FoundationPackageConflictError(
                        "Selected Experiment is FROZEN; package additions and links are forbidden."
                    )

    normalized = dict(selected_input)
    normalized.update(
        {
            "target_experiment_id": str(experiment.pk),
            "target_experiment_code": experiment.code,
            "target_experiment_version": experiment.version,
            "target_assessment_set_id": str(assessment_set.pk),
            "target_assessment_set_code": assessment_set.code,
            "target_assessment_set_version": assessment_set.version,
        }
    )
    return reusable, normalized


def _source_identity_map(package: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Bind every external stable code to the verified internal package UUID."""

    return {
        section: {item["code"]: item["id"] for item in package[section]}
        for section in ENTITY_SECTIONS
        if package[section]
    }


def _correction_lineage(package: Mapping[str, Any]) -> tuple[dict[str, str], ...]:
    result: list[dict[str, str]] = []
    for section in ("actor_element_assessments", "parameter_values"):
        index = {item["code"]: item for item in package[section]}
        for item in package[section]:
            predecessor = item.get("supersedes_code")
            if predecessor:
                result.append(
                    {
                        "section": section,
                        "code": item["code"],
                        "id": item["id"],
                        "supersedes_code": predecessor,
                        "supersedes_id": index[predecessor]["id"],
                    }
                )
    return tuple(result)


def _intended_changes(
    package: Mapping[str, Any],
    *,
    workspace: Any,
    selected_existing: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, list[str]]]:
    create: dict[str, list[str]] = {}
    reuse: dict[str, list[str]] = {}
    for spec in _materialization_specs():
        section = spec["section"]
        for item in package[section]:
            existing = _existing_for_item(spec["model"], item, workspace, spec)
            can_reuse = existing is not None and (
                spec.get("allow_exact_reuse")
                or item["code"] in selected_existing.get(section, {})
            )
            target = reuse if can_reuse else create
            target.setdefault(section, []).append(item["code"])
    return {"create": create, "reuse": reuse}


def _profile_row_identity(
    raw_code: Any,
    *,
    workspace: Any,
    section: str,
) -> tuple[str, str]:
    code = str(raw_code or "").strip()
    if not code:
        raise FoundationPackageValidationError(
            f"{section} requires a stable external identity."
        )
    try:
        internal_id = UUID(code)
    except ValueError:
        internal_id = uuid5(
            NAMESPACE_URL,
            f"{FOUNDATION_PACKAGE_FORMAT}:{workspace.pk}:{section}:{code}",
        )
    return str(internal_id), code


def _profile_document_version_identity(raw_code: Any) -> str:
    """Project one exact external DocumentVersion identity into model version space."""

    external_id = str(raw_code or "").strip()
    if not external_id or not _ASCII_CODE_PATTERN.fullmatch(external_id):
        raise FoundationPackageValidationError(
            "DOCUMENTS document_version_id must be a stable ASCII technical identity."
        )
    if len(external_id) <= 64:
        return external_id
    if len(external_id) > 128:
        raise FoundationPackageValidationError(
            "DOCUMENTS document_version_id exceeds the canonical 128-character limit."
        )
    # The external code and UUID remain untouched.  Only the model's bounded
    # semantic-version lane receives a deterministic full-digest projection.
    return hashlib.sha256(external_id.encode("ascii")).hexdigest()


def _resolve_profile_object(model: type[Any], raw_id: Any, workspace: Any, section: str) -> Any:
    stable_id, stable_code = _profile_row_identity(
        raw_id, workspace=workspace, section=section
    )
    obj = model.objects.filter(workspace=workspace).filter(
        Q(pk=UUID(stable_id)) | Q(code=stable_code)
    ).first()
    if obj is None:
        raise FoundationPackageConflictError(
            f"{section} external identity {raw_id!r} is not defined in the target workspace."
        )
    return obj


def _map_pre_freeze_xlsx_profile(
    adapted: Mapping[str, Any],
    *,
    workspace: Any,
    selected_input: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map the accepted pre-freeze Assessment workbook to canonical V4 DTO rows.

    The profile is deliberately explicit and versioned.  It imports only one
    selected Experiment/AssessmentSet lane and materializes POS/SAL through the
    sole numeric lane, ParameterValue.  It never infers a coder lane from labels.
    """

    from domain.services.xlsx_adapter import PRE_FREEZE_PROFILE

    if adapted.get("__xlsx_profile__") != PRE_FREEZE_PROFILE:
        raise FoundationPackageValidationError("Unknown XLSX workbook profile.")
    meta = dict(adapted["meta"])
    sheets = dict(adapted["sheets"])
    selected = dict(selected_input)

    set_selector = selected.get("target_assessment_set_id", meta["assessment_set_id"])
    try:
        set_uuid = UUID(str(set_selector))
        assessment_set = _model("AssessmentSet").objects.filter(
            workspace=workspace, pk=set_uuid
        ).first()
    except ValueError:
        assessment_set = _model("AssessmentSet").objects.filter(
            workspace=workspace, code=str(set_selector)
        ).first()
    if assessment_set is None:
        raise FoundationPackageConflictError(
            "PRE_FREEZE META assessment_set_id does not resolve in the exact workspace."
        )
    experiment_selector = selected.get("target_experiment_id")
    experiments = _model("Experiment").objects.select_related(
        "assessment_set", "expert_profile"
    ).filter(workspace=workspace, assessment_set=assessment_set)
    if experiment_selector is not None:
        try:
            experiment = experiments.filter(pk=UUID(str(experiment_selector))).first()
        except ValueError as exc:
            raise FoundationPackageConflictError(
                "target_experiment_id must be the exact Experiment UUID."
            ) from exc
    else:
        experiment = experiments.first() if experiments.count() == 1 else None
    if experiment is None:
        raise FoundationPackageConflictError(
            "PRE_FREEZE import requires one unambiguous target Experiment."
        )
    if experiment.status == "FROZEN":
        raise FoundationPackageConflictError(
            "Selected Experiment is FROZEN; PRE_FREEZE Assessment import is read-only."
        )
    if meta["coder_type"].strip().upper() != assessment_set.kind:
        raise FoundationPackageConflictError(
            "Workbook coder_type differs from the selected HUMAN/AI AssessmentSet lane."
        )

    assessment_rows = list(sheets.get("ASSESSMENTS", []))
    if not assessment_rows:
        raise FoundationPackageValidationError(
            "PRE_FREEZE workbook requires at least one ASSESSMENTS row."
        )
    selected_source_column = "ASSESSMENTS.pos|sal"
    claimed_source_column = selected.get("selected_source_column")
    if claimed_source_column not in (None, selected_source_column):
        raise FoundationPackageValidationError(
            "PRE_FREEZE selected_source_column is fixed to ASSESSMENTS.pos|sal; "
            "the HUMAN/AI lane is selected by exact META/target UUID identity."
        )

    payload: dict[str, Any] = {
        "format": FOUNDATION_PACKAGE_FORMAT,
        "format_version": FOUNDATION_PACKAGE_VERSION,
        "package_id": meta["package_id"],
        "schema_version": meta["workbook_schema_version"],
        "template_version": meta["workbook_schema_version"],
        "method_version": meta["method_version"],
        "ontology_version": meta["ontology_version"],
        "dataset_version": meta["dataset_version"],
        "workspace": {
            "id": str(workspace.pk),
            "code": workspace.code,
            "version": workspace.version,
            "project_definition_version_id": str(workspace.definition_version_id),
            "project_definition_hash": workspace.definition_manifest_hash,
            "label": workspace.name,
            "metadata": copy.deepcopy(workspace.metadata),
        },
        "project_definition_versions": [_export_definition(workspace.definition_version)],
        "compatibility_receipts": [],
    }
    for section in ENTITY_SECTIONS:
        if section != "project_definition_versions":
            payload[section] = []
    payload["assessment_sets"] = [_export_item("assessment_sets", assessment_set)]
    payload["expert_profiles"] = [
        _export_item("expert_profiles", experiment.expert_profile)
    ]
    payload["experiments"] = [_export_item("experiments", experiment)]

    definitions: dict[str, Any] = {}
    for code in ("POS", "SAL"):
        definition = _model("ParameterDefinition").objects.filter(
            project=workspace.project, code__iexact=code
        ).first()
        if definition is None:
            raise FoundationPackageConflictError(
                f"PRE_FREEZE {code} requires an existing canonical ParameterDefinition."
            )
        definitions[code] = definition
        payload["parameter_definitions"].append(
            _export_item("parameter_definitions", definition)
        )

    identity_map: dict[str, dict[str, str]] = {}
    source_lookup: dict[str, dict[str, Any]] = {}
    for row in sheets.get("SOURCES", []):
        for field in ("source_id", "publisher_or_origin", "source_type", "jurisdiction", "language", "url_or_locator", "accessed_at", "independence_group", "source_notes"):
            if field not in row:
                raise FoundationPackageValidationError(f"SOURCES lacks {field!r}.")
        internal_id, code = _profile_row_identity(
            row["source_id"], workspace=workspace, section="sources"
        )
        locator = str(row["url_or_locator"] or "")
        homepage_url = locator if locator.startswith(("http://", "https://")) else ""
        item = {
            "id": internal_id,
            "code": code,
            "version": meta["workbook_schema_version"],
            "metadata": {
                "source_type": row["source_type"],
                "jurisdiction": row["jurisdiction"],
                "language": row["language"],
                "url_or_locator": locator,
                "accessed_at": row["accessed_at"],
                "source_notes": row["source_notes"],
            },
            "name": row["publisher_or_origin"],
            "publisher": row["publisher_or_origin"],
            "independence_group": row["independence_group"] or code,
            "independence_status": "UNVERIFIED",
            "homepage_url": homepage_url,
        }
        payload["sources"].append(item)
        source_lookup[str(row["source_id"])] = item
        identity_map.setdefault("sources", {})[code] = internal_id

    document_lookup: dict[str, dict[str, Any]] = {}
    version_lookup: dict[str, dict[str, Any]] = {}
    version_identity_sources: dict[str, str] = {}
    pending_version_codes: set[str] = set()
    after_cutoff_version_codes: set[str] = set()
    for row in sheets.get("DOCUMENTS", []):
        for field in ("document_id", "source_id", "title", "document_type", "document_version_id", "publication_date", "captured_at", "content_hash", "content_type", "language", "archive_or_local_locator", "is_after_cutoff"):
            if field not in row:
                raise FoundationPackageValidationError(f"DOCUMENTS lacks {field!r}.")
        source = source_lookup.get(str(row["source_id"]))
        if source is None:
            raise FoundationPackageValidationError("DOCUMENTS references an unknown source_id.")
        document_id, document_code = _profile_row_identity(
            row["document_id"], workspace=workspace, section="documents"
        )
        source_locator = source["metadata"]["url_or_locator"]
        canonical_url = source_locator if str(source_locator).startswith(("http://", "https://")) else ""
        accessed_at = next(
            (
                source_row["accessed_at"]
                for source_row in sheets.get("SOURCES", [])
                if str(source_row["source_id"]) == str(row["source_id"])
            ),
            "",
        )
        document = {
            "id": document_id,
            "code": document_code,
            "version": meta["workbook_schema_version"],
            "metadata": {
                "document_type": row["document_type"],
                "language": row["language"],
            },
            "source_code": source["code"],
            "title": row["title"],
            "canonical_url": canonical_url,
            "published_on": row["publication_date"],
            "accessed_on": str(accessed_at)[:10] or None,
        }
        external_document_id = str(row["document_id"])
        previous_document = document_lookup.get(external_document_id)
        if previous_document is None:
            payload["documents"].append(document)
            document_lookup[external_document_id] = document
            identity_map.setdefault("documents", {})[document_code] = document_id
        elif previous_document != document:
            raise FoundationPackageValidationError(
                "DOCUMENTS repeats document_id with conflicting immutable Document fields."
            )
        else:
            document = previous_document
        version_id, version_code = _profile_row_identity(
            row["document_version_id"], workspace=workspace, section="document_versions"
        )
        external_version_id = str(row["document_version_id"]).strip()
        captured_version = _profile_document_version_identity(external_version_id)
        previous_version_source = version_identity_sources.get(captured_version)
        if (
            previous_version_source is not None
            and previous_version_source != external_version_id
        ):
            raise FoundationPackageValidationError(
                "DOCUMENTS document_version_id values collide after bounded semantic "
                "version projection."
            )
        version_identity_sources[captured_version] = external_version_id
        locator = str(row["archive_or_local_locator"] or "")
        capture_url = locator if locator.startswith(("http://", "https://")) else canonical_url
        version = {
            "id": version_id,
            "code": version_code,
            "version": captured_version,
            "metadata": {
                "archive_or_local_locator": row["archive_or_local_locator"],
                "is_after_cutoff": row["is_after_cutoff"],
                "recorded_content_hash": row["content_hash"] or None,
            },
            "document_code": document_code,
            "supersedes_code": None,
            "status": "URL_CAPTURED_FULL_CONTENT_HASH_PENDING_INGEST",
            "capture_url": capture_url,
            "captured_at": row["captured_at"],
            "checksum": None,
            "media_type": row["content_type"] or "application/octet-stream",
        }
        pending_version_codes.add(version_code)
        if row["is_after_cutoff"] is True:
            after_cutoff_version_codes.add(version_code)
        payload["document_versions"].append(version)
        version_lookup[str(row["document_version_id"])] = version
        identity_map.setdefault("document_versions", {})[version_code] = version_id

    fragment_lookup: dict[str, dict[str, Any]] = {}
    for row in sheets.get("FRAGMENTS", []):
        for field in ("fragment_id", "document_version_id", "exact_text", "fragment_hash", "start_offset", "end_offset", "page", "section", "translation_text", "translation_language"):
            if field not in row:
                raise FoundationPackageValidationError(f"FRAGMENTS lacks {field!r}.")
        version = version_lookup.get(str(row["document_version_id"]))
        if version is None:
            raise FoundationPackageValidationError("FRAGMENTS references an unknown DocumentVersion.")
        fragment_id, fragment_code = _profile_row_identity(
            row["fragment_id"], workspace=workspace, section="text_fragments"
        )
        item = {
            "id": fragment_id,
            "code": fragment_code,
            "version": meta["workbook_schema_version"],
            "document_version_code": version["code"],
            "anchor_status": "HASH_RECORDED_PENDING_INGEST",
            "metadata": {
                "translation_text": row["translation_text"],
                "translation_language": row["translation_language"],
                "unverified_start_offset": row["start_offset"],
                "unverified_end_offset": row["end_offset"],
            },
            "start_offset": None,
            "end_offset": None,
            "selector": {},
            "page": str(row["page"] or ""),
            "section": row["section"] or "",
            "exact_text": row["exact_text"],
            "exact_text_sha256": row["fragment_hash"],
        }
        pending_version_codes.add(version["code"])
        payload["text_fragments"].append(item)
        fragment_lookup[str(row["fragment_id"])] = item
        identity_map.setdefault("text_fragments", {})[fragment_code] = fragment_id

    fact_lookup: dict[str, dict[str, Any]] = {}
    for row in sheets.get("FACTS", []):
        for field in ("fact_id", "fact_statement", "fact_type", "fact_status", "time_start", "time_end", "geography", "fact_notes"):
            if field not in row:
                raise FoundationPackageValidationError(f"FACTS lacks {field!r}.")
        fact_id, fact_code = _profile_row_identity(
            row["fact_id"], workspace=workspace, section="facts"
        )
        item = {
            "id": fact_id,
            "code": fact_code,
            "version": meta["workbook_schema_version"],
            "metadata": {
                "time_start": row["time_start"],
                "time_end": row["time_end"],
                "geography": row["geography"],
                "fact_notes": row["fact_notes"],
            },
            "experiment_code": experiment.code,
            "fact_type": str(row["fact_type"]).upper(),
            "statement": row["fact_statement"],
            "origin": (
                "AI_ASSERTION"
                if meta["coder_type"].strip().upper() == "AI"
                else "HUMAN_EXPERT_ASSERTION"
            ),
            "directness": "UNKNOWN",
            "visibility": "EXPERIMENT_PRIVATE",
            "status": str(row["fact_status"]).upper(),
            "confidence": None,
            "temporal_status": "UNKNOWN",
            "coder_identifier": meta["coder_id"],
        }
        payload["facts"].append(item)
        fact_lookup[str(row["fact_id"])] = item
        identity_map.setdefault("facts", {})[fact_code] = fact_id

    for row in sheets.get("FACT_EVIDENCE", []):
        for field in ("fact_fragment_link_id", "fact_id", "fragment_id", "evidence_relation"):
            if field not in row:
                raise FoundationPackageValidationError(f"FACT_EVIDENCE lacks {field!r}.")
        fact = fact_lookup.get(str(row["fact_id"]))
        fragment = fragment_lookup.get(str(row["fragment_id"]))
        if fact is None or fragment is None:
            raise FoundationPackageValidationError("FACT_EVIDENCE contains an orphan reference.")
        link_id, link_code = _profile_row_identity(
            row["fact_fragment_link_id"], workspace=workspace, section="fact_evidence_links"
        )
        payload["fact_evidence_links"].append(
            {
                "id": link_id,
                "code": link_code,
                "version": meta["workbook_schema_version"],
                "fact_code": fact["code"],
                "fragment_code": fragment["code"],
                "relation": str(row["evidence_relation"]).upper(),
                "temporal_status": (
                    "RETROSPECTIVE_KNOWLEDGE"
                    if fragment["document_version_code"] in after_cutoff_version_codes
                    else "CONTEMPORANEOUS"
                ),
                "learned_on": None,
                "rationale": "",
            }
        )
        identity_map.setdefault("fact_evidence_links", {})[link_code] = link_id

    fact_temporal: dict[str, list[str]] = {}
    for link in payload["fact_evidence_links"]:
        fact_temporal.setdefault(link["fact_code"], []).append(link["temporal_status"])
    for fact in payload["facts"]:
        statuses = fact_temporal.get(fact["code"], [])
        if statuses:
            fact["origin"] = "DOCUMENT_DERIVED"
        if "CONTEMPORANEOUS" in statuses:
            fact["temporal_status"] = "CONTEMPORANEOUS"
        elif "RETROSPECTIVE_KNOWLEDGE" in statuses:
            fact["temporal_status"] = "RETROSPECTIVE_KNOWLEDGE"

    actor_cache: dict[str, dict[str, Any]] = {}
    actor_lookup: dict[str, dict[str, Any]] = {}
    actor_rows = list(sheets.get("ACTORS", []))
    for order, row in enumerate(actor_rows):
        for field in ("actor_id", "actor_code", "actor_name_ru", "actor_type", "parent_actor_id", "aliases", "record_status"):
            if field not in row:
                raise FoundationPackageValidationError(f"ACTORS lacks {field!r}.")
        internal_id, fallback_code = _profile_row_identity(
            row["actor_id"], workspace=workspace, section="actors"
        )
        try:
            UUID(str(row["actor_id"]))
            code = str(row["actor_code"] or fallback_code)
        except ValueError:
            code = fallback_code
        item = {
            "id": internal_id,
            "code": code,
            "version": meta["workbook_schema_version"],
            "metadata": {
                "actor_code": row["actor_code"],
                "aliases": row["aliases"],
                "record_status": row["record_status"],
            },
            "parent_code": None,
            "actor_type": str(row["actor_type"]).upper(),
            "label": row["actor_name_ru"],
            "description": "",
            "order": order,
        }
        actor_cache[code] = item
        actor_lookup[str(row["actor_id"])] = item
        actor_lookup[str(row["actor_code"])] = item
        identity_map.setdefault("actors", {})[code] = internal_id
    for row in actor_rows:
        if row["parent_actor_id"]:
            parent = actor_lookup.get(str(row["parent_actor_id"]))
            if parent is None:
                raise FoundationPackageValidationError("ACTORS contains an orphan parent_actor_id.")
            actor_lookup[str(row["actor_id"])]["parent_code"] = parent["code"]

    element_cache: dict[str, dict[str, Any]] = {}
    element_lookup: dict[str, dict[str, Any]] = {}
    element_rows = list(sheets.get("ELEMENTS", []))
    for order, row in enumerate(element_rows):
        for field in ("element_id", "element_code", "element_name_ru", "element_type", "reference_statement", "parent_element_id", "record_status"):
            if field not in row:
                raise FoundationPackageValidationError(f"ELEMENTS lacks {field!r}.")
        internal_id, fallback_code = _profile_row_identity(
            row["element_id"], workspace=workspace, section="analytical_elements"
        )
        try:
            UUID(str(row["element_id"]))
            code = str(row["element_code"] or fallback_code)
        except ValueError:
            code = fallback_code
        item = {
            "id": internal_id,
            "code": code,
            "version": meta["workbook_schema_version"],
            "metadata": {"record_status": row["record_status"]},
            "parent_code": None,
            "element_type": str(row["element_type"]).upper(),
            "label": row["element_name_ru"],
            "reference_statement": row["reference_statement"],
            "description": "",
            "order": order,
        }
        element_cache[code] = item
        element_lookup[str(row["element_id"])] = item
        element_lookup[str(row["element_code"])] = item
        identity_map.setdefault("analytical_elements", {})[code] = internal_id
    for row in element_rows:
        if row["parent_element_id"]:
            parent = element_lookup.get(str(row["parent_element_id"]))
            if parent is None:
                raise FoundationPackageValidationError("ELEMENTS contains an orphan parent_element_id.")
            element_lookup[str(row["element_id"])]["parent_code"] = parent["code"]

    slice_cache: dict[str, dict[str, Any]] = {}
    slice_lookup: dict[str, dict[str, Any]] = {}
    slice_knowledge_mode: dict[str, str] = {}
    for order, row in enumerate(sheets.get("TIME_SLICES", [])):
        for field in ("time_slice_id", "time_slice_label", "start_date", "end_date", "cutoff_date", "knowledge_mode", "snapshot_or_packet_hash"):
            if field not in row:
                raise FoundationPackageValidationError(f"TIME_SLICES lacks {field!r}.")
        internal_id, code = _profile_row_identity(
            row["time_slice_id"], workspace=workspace, section="time_slices"
        )
        item = {
            "id": internal_id,
            "code": code,
            "version": meta["workbook_schema_version"],
            "metadata": {
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "knowledge_mode": row["knowledge_mode"],
                "snapshot_or_packet_hash": row["snapshot_or_packet_hash"],
            },
            "name": row["time_slice_label"],
            "cutoff_date": row["cutoff_date"],
            "order": order,
        }
        slice_cache[code] = item
        slice_lookup[str(row["time_slice_id"])] = item
        slice_knowledge_mode[code] = str(row["knowledge_mode"] or "").upper()
        identity_map.setdefault("time_slices", {})[code] = internal_id
    assessment_lookup: dict[str, dict[str, Any]] = {}
    value_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row_number, row in enumerate(assessment_rows, start=2):
        for field in ("assessment_id", "assessment_set_id", "actor_id", "element_id", "time_slice_id", "assessment_status", "confidence", "reference_statement", "pos", "sal", "rationale"):
            if field not in row:
                raise FoundationPackageValidationError(
                    f"ASSESSMENTS row {row_number} lacks technical field {field!r}."
                )
        if str(row["assessment_set_id"]) not in {assessment_set.code, str(assessment_set.pk)}:
            raise FoundationPackageConflictError(
                f"ASSESSMENTS row {row_number} crosses the selected AssessmentSet lane."
            )
        actor = actor_lookup.get(str(row["actor_id"]))
        element = element_lookup.get(str(row["element_id"]))
        time_slice = slice_lookup.get(str(row["time_slice_id"]))
        if actor is None:
            existing = _resolve_profile_object(
                _model("Actor"), row["actor_id"], workspace, "actors"
            )
            actor = _export_item("actors", existing)
            actor_cache[actor["code"]] = actor
        if element is None:
            existing = _resolve_profile_object(
                _model("AnalyticalElement"),
                row["element_id"],
                workspace,
                "analytical_elements",
            )
            element = _export_item("analytical_elements", existing)
            element_cache[element["code"]] = element
        if time_slice is None:
            existing = _resolve_profile_object(
                _model("TimeSlice"), row["time_slice_id"], workspace, "time_slices"
            )
            time_slice = _export_item("time_slices", existing)
            slice_cache[time_slice["code"]] = time_slice
        assessment_id, assessment_code = _profile_row_identity(
            row["assessment_id"], workspace=workspace, section="actor_element_assessments"
        )
        confidence_level = str(row["confidence"] or "UNKNOWN").strip().upper()
        if confidence_level not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH"}:
            raise FoundationPackageValidationError(
                "PRE_FREEZE categorical confidence must be UNKNOWN/LOW/MEDIUM/HIGH; "
                "no numeric rescaling is allowed."
            )
        source_status = str(row["assessment_status"] or "UNKNOWN").strip().upper()
        accepted_source_statuses = {
            "UNKNOWN",
            "NOT_APPLICABLE",
            "INSUFFICIENT_DATA",
            "PROVISIONAL",
            "PROVISIONAL_PRE_METHOD_FREEZE",
            "CONFIRMED",
            "OPEN_METHOD",
            "DISPUTED",
            "RETROSPECTIVE_KNOWLEDGE",
        }
        if source_status not in accepted_source_statuses:
            raise FoundationPackageValidationError(
                f"ASSESSMENTS row {row_number} has unsupported assessment_status "
                f"{source_status!r}."
            )
        normalized_value_status = (
            "PROVISIONAL"
            if source_status == "PROVISIONAL_PRE_METHOD_FREEZE"
            else source_status
        )
        if (
            normalized_value_status not in ABSENT_VALUE_STATUSES
            and row["pos"] in (None, "")
            and row["sal"] in (None, "")
        ):
            raise FoundationPackageValidationError(
                f"ASSESSMENTS row {row_number} has blank POS/SAL for present status "
                f"{source_status}; no UNKNOWN fill-across is permitted."
            )
        header_status = (
            source_status
            if source_status
            in {
                "UNKNOWN",
                "PROVISIONAL",
                "PROVISIONAL_PRE_METHOD_FREEZE",
                "CONFIRMED",
                "DISPUTED",
            }
            else "UNKNOWN"
        )
        no_direct_position = False
        knowledge_mode = slice_knowledge_mode.get(time_slice["code"], "")
        value_temporal_status = (
            "RETROSPECTIVE_KNOWLEDGE"
            if knowledge_mode == "RETROSPECTIVE"
            else "CONTEMPORANEOUS"
            if knowledge_mode in {"CONTEMPORANEOUS", "AS_OF_CUTOFF"}
            else "UNKNOWN"
        )
        assessment = {
            "id": assessment_id,
            "code": assessment_code,
            "version": meta["workbook_schema_version"],
            "assessment_set_code": assessment_set.code,
            "experiment_code": experiment.code,
            "actor_code": actor["code"],
            "element_code": element["code"],
            "time_slice_code": time_slice["code"],
            "supersedes_code": None,
            "reference_statement": row["reference_statement"] or "",
            "reference_statement_incomplete": not bool(row["reference_statement"]),
            "status": header_status,
            "confidence_level": confidence_level,
            "knowledge_cutoff": meta["cutoff_date"],
            "method_version": meta["method_version"],
            "provenance": {
                "adapter_profile": PRE_FREEZE_PROFILE,
                "coder_id": meta["coder_id"],
                "source_packet_hash": meta["source_packet_hash"],
                "source_assessment_status": source_status,
            },
        }
        payload["actor_element_assessments"].append(assessment)
        assessment_lookup[str(row["assessment_id"])] = assessment
        identity_map.setdefault("actor_element_assessments", {})[assessment_code] = assessment_id
        for dimension in ("POS", "SAL"):
            raw_value = row[dimension.lower()]
            present = raw_value not in (None, "")
            value_status = normalized_value_status
            if present and value_status not in {
                "PROVISIONAL", "CONFIRMED", "DISPUTED", "RETROSPECTIVE_KNOWLEDGE"
            }:
                raise FoundationPackageValidationError(
                    f"ASSESSMENTS row {row_number} has {dimension} with absent status {source_status}."
                )
            if not present and value_status not in ABSENT_VALUE_STATUSES:
                raise FoundationPackageValidationError(
                    f"ASSESSMENTS row {row_number} has null {dimension} with present "
                    f"status {source_status}; the adapter cannot silently rewrite it UNKNOWN."
                )
            definition = definitions[dimension]
            if present and definition.value_type == "INTEGER":
                try:
                    value: Any = int(str(raw_value))
                except ValueError as exc:
                    raise FoundationPackageValidationError(
                        f"ASSESSMENTS row {row_number} {dimension} must be an integer."
                    ) from exc
            else:
                value = raw_value if present else None
            value_id, value_code = _profile_row_identity(
                f"{assessment_code}:{dimension}",
                workspace=workspace,
                section="parameter_values",
            )
            value_item = {
                    "id": value_id,
                    "code": value_code,
                    "version": meta["workbook_schema_version"],
                    "assessment_code": assessment_code,
                    "assessment_set_code": assessment_set.code,
                    "parameter_definition_code": definition.code,
                    "supersedes_code": None,
                    "status": value_status,
                    "temporal_status": value_temporal_status,
                    "value": value,
                    "note": "",
                    "confidence": None,
                    "range_min": None,
                    "range_max": None,
                    "rationale": row["rationale"] or "",
                }
            payload["parameter_values"].append(value_item)
            value_lookup[(str(row["assessment_id"]), dimension)] = value_item
            identity_map.setdefault("parameter_values", {})[value_code] = value_id

    fact_after_cutoff = {
        link["fact_code"]
        for link in payload["fact_evidence_links"]
        if link["temporal_status"] == "RETROSPECTIVE_KNOWLEDGE"
    }
    for row in sheets.get("ASSESSMENT_EVIDENCE", []):
        for field in ("assessment_fact_link_id", "assessment_id", "fact_id", "evidence_role"):
            if field not in row:
                raise FoundationPackageValidationError(f"ASSESSMENT_EVIDENCE lacks {field!r}.")
        assessment = assessment_lookup.get(str(row["assessment_id"]))
        fact = fact_lookup.get(str(row["fact_id"]))
        if assessment is None or fact is None:
            raise FoundationPackageValidationError("ASSESSMENT_EVIDENCE contains an orphan reference.")
        link_id, link_code = _profile_row_identity(
            row["assessment_fact_link_id"], workspace=workspace, section="assessment_fact_links"
        )
        role = str(row["evidence_role"]).upper()
        temporal = (
            "RETROSPECTIVE_KNOWLEDGE"
            if fact["code"] in fact_after_cutoff
            else "CONTEMPORANEOUS"
        )
        payload["assessment_fact_links"].append(
            {
                "id": link_id,
                "code": link_code,
                "version": meta["workbook_schema_version"],
                "assessment_code": assessment["code"],
                "fact_code": fact["code"],
                "role": role,
                "temporal_status": temporal,
                "learned_on": None,
                "rationale": "",
            }
        )
        identity_map.setdefault("assessment_fact_links", {})[link_code] = link_id
        # The PRE_FREEZE ASSESSMENT_EVIDENCE sheet identifies an Assessment and
        # a Fact, but it has no POS/SAL dimension selector.  It therefore cannot
        # truthfully create ParameterValueEvidence for either numeric lane.
        # Dimension-specific value evidence belongs in a separately versioned
        # adapter profile with an explicit parameter-value identity.

    payload["actors"] = list(actor_cache.values())
    payload["analytical_elements"] = list(element_cache.values())
    payload["time_slices"] = list(slice_cache.values())

    bytes_gap: dict[str, Any] | None = None
    for row in sheets.get("GAPS", []):
        for field in ("gap_id", "target_type", "target_id", "gap_type", "description", "owner_or_next_action", "status"):
            if field not in row:
                raise FoundationPackageValidationError(f"GAPS lacks {field!r}.")
        gap_id, gap_code = _profile_row_identity(
            row["gap_id"], workspace=workspace, section="gaps"
        )
        target_type = str(row["target_type"] or "").upper()
        target_id = str(row["target_id"] or "")
        target_version = version_lookup.get(target_id)
        item = {
            "id": gap_id,
            "code": gap_code,
            "version": meta["workbook_schema_version"],
            "metadata": {
                "target_type": target_type,
                "target_id": target_id,
                "description": row["description"],
                "owner_or_next_action": row["owner_or_next_action"],
            },
            "type": str(row["gap_type"]).upper(),
            "document_version_code": (
                target_version["code"]
                if target_version is not None
                and target_type in {"DOCUMENTVERSION", "DOCUMENT_VERSION"}
                else None
            ),
            "status": str(row["status"]).upper(),
            "required_behavior": row["owner_or_next_action"] or row["description"],
            "resolution": (
                row["description"] if str(row["status"]).upper() == "RESOLVED" else ""
            ),
        }
        payload["gaps"].append(item)
        identity_map.setdefault("gaps", {})[gap_code] = gap_id
        if item["type"] == "FULL_DOCUMENT_BYTES_NOT_INGESTED" and item["status"] == "OPEN":
            bytes_gap = item
    if pending_version_codes:
        if bytes_gap is None:
            gap_seed = hashlib.sha256(
                f"{workspace.pk}:{meta['package_id']}:document-bytes".encode("utf-8")
            ).hexdigest()
            gap_code = f"GAP-DOCUMENT-BYTES-{gap_seed}"
            gap_id, _ = _profile_row_identity(
                gap_code, workspace=workspace, section="gaps"
            )
            bytes_gap = {
                "id": gap_id,
                "code": gap_code,
                "version": meta["workbook_schema_version"],
                "metadata": {},
                "type": "FULL_DOCUMENT_BYTES_NOT_INGESTED",
                "document_version_code": None,
                "status": "OPEN",
                "required_behavior": (
                    "Do not fabricate a DocumentVersion checksum; preserve the gap "
                    "until immutable content bytes are ingested."
                ),
                "resolution": "",
            }
            payload["gaps"].append(bytes_gap)
            identity_map.setdefault("gaps", {})[gap_code] = gap_id
        bytes_gap["metadata"]["affected_document_version_codes"] = sorted(
            pending_version_codes
        )
        bytes_gap["metadata"]["recorded_content_hashes"] = {
            version["code"]: version.get("metadata", {}).get("recorded_content_hash")
            for version in payload["document_versions"]
            if version["code"] in pending_version_codes
            and version.get("metadata", {}).get("recorded_content_hash")
        }

    power_profiles: dict[str, dict[str, Any]] = {}
    for row_number, row in enumerate(sheets.get("POWER_PROFILE", []), start=2):
        assessment_external = row.get("assessment_id")
        assessment = assessment_lookup.get(str(assessment_external))
        if assessment is None:
            raise FoundationPackageValidationError(
                f"POWER_PROFILE row {row_number} references an unknown assessment_id."
            )
        profile = power_profiles.get(assessment["code"])
        if profile is None:
            profile_id, profile_code = _profile_row_identity(
                f"{assessment['code']}:POWER",
                workspace=workspace,
                section="power_profiles",
            )
            profile = {
                "id": profile_id,
                "code": profile_code,
                "version": meta["workbook_schema_version"],
                "assessment_code": assessment["code"],
                "method_version": meta["method_version"],
                "note": "",
            }
            power_profiles[assessment["code"]] = profile
            payload["power_profiles"].append(profile)
            identity_map.setdefault("power_profiles", {})[profile_code] = profile_id
        for dimension in POWER_COMPONENTS:
            prefix = dimension.lower()
            required_fields = tuple(
                f"{prefix}_{suffix}"
                for suffix in ("value", "status", "confidence", "rationale", "provenance")
            )
            if not all(field in row for field in required_fields):
                raise FoundationPackageValidationError(
                    f"POWER_PROFILE row {row_number} lacks component fields for {dimension}."
                )
            provenance = row[f"{prefix}_provenance"]
            if provenance is None or (
                isinstance(provenance, str) and not provenance.strip()
            ):
                provenance = {}
            elif isinstance(provenance, str):
                try:
                    provenance = json.loads(provenance)
                except json.JSONDecodeError as exc:
                    raise FoundationPackageValidationError(
                        f"POWER_PROFILE {dimension} provenance must be JSON."
                    ) from exc
            if not isinstance(provenance, Mapping):
                raise FoundationPackageValidationError(
                    f"POWER_PROFILE {dimension} provenance must be a JSON object."
                )
            component_id, component_code = _profile_row_identity(
                f"{profile['code']}:{dimension}",
                workspace=workspace,
                section="power_components",
            )
            payload["power_components"].append(
                {
                    "id": component_id,
                    "code": component_code,
                    "version": meta["workbook_schema_version"],
                    "profile_code": profile["code"],
                    "dimension": dimension,
                    "status": str(row[f"{prefix}_status"]).upper(),
                    "value": row[f"{prefix}_value"],
                    "confidence": row[f"{prefix}_confidence"],
                    "rationale": row[f"{prefix}_rationale"] or "",
                    "provenance": copy.deepcopy(dict(provenance)),
                }
            )
            identity_map.setdefault("power_components", {})[component_code] = component_id
    selected.update(
        {
            "adapter_profile": PRE_FREEZE_PROFILE,
            "target_experiment_id": str(experiment.pk),
            "target_assessment_set_id": str(assessment_set.pk),
            "selected_source_column": selected_source_column,
            "profile_identity_map": identity_map,
        }
    )
    return seal_foundation_package(payload), selected


def preview_foundation_package(
    raw: Any,
    *,
    workspace: Any,
    adapter: str = "json",
    selected_input: Mapping[str, Any] | None = None,
    allow_nonempty: bool = False,
) -> FoundationImportPreview:
    """Validate transport, schema, semantics and conflicts without any DB writes."""

    workspace_id, workspace_code = _workspace_identity(workspace)
    normalized_adapter = adapter.strip().lower()
    selected = dict(selected_input or {})
    for reserved_key in RAW_INPUT_PROVENANCE_KEYS:
        selected.pop(reserved_key, None)
    adapted_raw = raw
    raw_input_provenance: dict[str, str] = {}
    if normalized_adapter == "json":
        adapted_raw, raw_input_provenance = _capture_json_input(raw)
    package = adapt_foundation_input(adapted_raw, adapter=normalized_adapter)
    if package.get("__xlsx_profile__"):
        package, selected = _map_pre_freeze_xlsx_profile(
            package,
            workspace=workspace,
            selected_input=selected,
        )
    canonical, warnings = validate_foundation_package(package)
    if canonical["workspace"]["code"] != workspace_code:
        raise FoundationPackageConflictError(
            "Package workspace code differs from the explicit target workspace."
        )
    if str(canonical["workspace"].get("id")) != workspace_id:
        raise FoundationPackageConflictError(
            "Package workspace UUID differs from the explicit target workspace."
        )
    _validate_workspace_definition(canonical, workspace)
    try:
        json.dumps(selected, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise FoundationPackageValidationError(
            "selected_input must be a finite JSON object."
        ) from exc
    selected_existing, selected = _resolve_selected_lane(
        canonical,
        workspace=workspace,
        selected_input=selected,
    )
    selected.update(raw_input_provenance)
    if normalized_adapter == "xlsx" and isinstance(raw, Path):
        try:
            workbook_bytes = raw.read_bytes()
        except OSError as exc:
            raise FoundationPackageValidationError(f"Cannot checksum XLSX input: {exc}.") from exc
        selected["input_name"] = raw.name
        selected["input_sha256"] = hashlib.sha256(workbook_bytes).hexdigest()
    counts = canonical["manifest"]["entity_counts"]
    source_identity_map = _source_identity_map(canonical)
    correction_lineage = _correction_lineage(canonical)
    intended_changes = _intended_changes(
        canonical,
        workspace=workspace,
        selected_existing=selected_existing,
    )
    try:
        with transaction.atomic():
            _materialize_foundation_rows(
                canonical,
                workspace=workspace,
                allow_nonempty=allow_nonempty,
                inject_failure_after=None,
                selected_existing=selected_existing,
            )
            transaction.set_rollback(True)
    except FoundationPackageError:
        raise
    except (ValidationError, IntegrityError, KeyError, ValueError) as exc:
        raise FoundationPackageValidationError(
            f"Canonical package fails domain-model validation: {exc}."
        ) from exc
    return FoundationImportPreview(
        valid=True,
        canonical_payload=_deep_freeze(canonical),
        checksum=canonical["manifest"]["payload_sha256"],
        counts=_deep_freeze(counts),
        warnings=warnings,
        errors=(),
        workspace_id=workspace_id,
        workspace_code=workspace_code,
        adapter=normalized_adapter,
        selected_input=_deep_freeze(selected),
        source_identity_map=_deep_freeze(source_identity_map),
        correction_lineage=tuple(_deep_freeze(item) for item in correction_lineage),
        intended_changes=_deep_freeze(intended_changes),
        allow_nonempty=allow_nonempty,
    )


def _structured_error(exc: Exception) -> Mapping[str, str]:
    message = str(exc)
    if "CONFIRMED_EVIDENCE_CHAIN_INCOMPLETE" in message:
        code = "CONFIRMED_EVIDENCE_CHAIN_INCOMPLETE"
    elif "parameter_definition_code" in message:
        code = "UNKNOWN_REFERENCE"
    elif "duplicates" in message or "already exists" in message or "checksum" in message:
        code = "DUPLICATE_OR_CONFLICT"
    elif "unknown package-local stable code" in message or "orphan" in message:
        code = "UNKNOWN_REFERENCE"
    elif "workspace" in message.lower():
        code = "WORKSPACE_CONFLICT"
    elif "anchor" in message.lower() or "fragment" in message.lower():
        code = "ANCHOR_VALIDATION_FAILED"
    elif "JSON Schema" in message:
        code = "SCHEMA_VALIDATION_FAILED"
    elif "status" in message.lower() or "UNKNOWN is not zero" in message:
        code = "STATUS_VALUE_INVALID"
    else:
        code = "FOUNDATION_IMPORT_INVALID"
    return MappingProxyType(
        {
            "code": code,
            "message": message,
            "exception": type(exc).__name__,
        }
    )


def inspect_foundation_package(
    raw: Any,
    *,
    workspace: Any,
    adapter: str = "json",
    selected_input: Mapping[str, Any] | None = None,
    allow_nonempty: bool = False,
) -> FoundationValidationReport:
    """Return a structured valid/invalid preview without mutating database state."""

    try:
        preview = preview_foundation_package(
            raw,
            workspace=workspace,
            adapter=adapter,
            selected_input=selected_input,
            allow_nonempty=allow_nonempty,
        )
    except FoundationPackageError as exc:
        return FoundationValidationReport(
            valid=False,
            preview=None,
            errors=(_structured_error(exc),),
        )
    return FoundationValidationReport(valid=True, preview=preview, errors=())


def _model(name: str) -> type[Any]:
    model = getattr(domain_models, name, None)
    if model is None:
        raise FoundationPackageValidationError(
            f"Foundation model {name} is unavailable; apply the Foundation migrations first."
        )
    return model


def _field_names(model: type[Any]) -> set[str]:
    return {field.name for field in model._meta.get_fields() if getattr(field, "concrete", False)}


def _new(model: type[Any], values: Mapping[str, Any]) -> Any:
    fields = _field_names(model)
    unknown = set(values) - fields
    if unknown:
        raise FoundationPackageValidationError(
            f"Importer/model contract drift for {model.__name__}: {sorted(unknown)}."
        )
    obj = model(**values)
    obj.full_clean()
    obj.save(force_insert=True)
    return obj


def _receipt_view(run: Any) -> FoundationImportReceipt:
    selected_input = dict(run.selected_input)
    return FoundationImportReceipt(
        id=str(run.pk),
        code=run.code,
        workspace_id=str(run.workspace_id),
        target_experiment_id=(
            str(run.target_experiment_id) if run.target_experiment_id else None
        ),
        target_assessment_set_id=(
            str(run.target_assessment_set_id) if run.target_assessment_set_id else None
        ),
        package_id=run.package_id,
        package_format=run.package_format,
        package_version=run.package_version,
        schema_version=run.schema_version,
        template_version=run.template_version,
        method_version=run.method_version,
        ontology_version=run.ontology_version,
        dataset_version=run.dataset_version,
        checksum=run.checksum,
        adapter=run.adapter,
        selected_input=_deep_freeze(selected_input),
        selected_source_column=run.selected_source_column,
        source_identity_map=_deep_freeze(run.source_identity_map),
        correction_lineage=tuple(_deep_freeze(item) for item in run.correction_lineage),
        intended_changes=_deep_freeze(run.intended_changes),
        row_counts=_deep_freeze(run.row_counts),
        warnings=tuple(run.warnings),
        errors=tuple(run.errors),
        allow_nonempty=run.allow_nonempty,
        actor_identifier=run.actor_identifier,
        committed_at=(
            run.committed_at.astimezone(timezone.utc).isoformat()
            if run.committed_at is not None
            else None
        ),
    )


@transaction.atomic
def commit_foundation_package(
    preview: FoundationImportPreview,
    *,
    workspace: Any,
    allow_nonempty: bool = False,
    actor_identifier: str,
    inject_failure_after: int | None = None,
) -> FoundationImportReceipt:
    """Atomically materialize a validated preview and append one ImportRun receipt.

    The materializer is completed by per-model specifications below; every row is
    force-inserted and therefore can never silently update an existing identity.
    ``inject_failure_after`` is an explicit rollback test seam, not product logic.
    """

    workspace_id, workspace_code = _workspace_identity(workspace)
    if not isinstance(preview, FoundationImportPreview) or not preview.valid:
        raise FoundationPackageValidationError("Commit requires a valid immutable preview.")
    if preview.workspace_id != workspace_id or preview.workspace_code != workspace_code:
        raise FoundationPackageConflictError("Preview belongs to a different workspace.")
    if allow_nonempty != preview.allow_nonempty:
        raise FoundationPackageConflictError(
            "Commit allow_nonempty must exactly match the immutable preview policy."
        )
    if not actor_identifier.strip():
        raise FoundationPackageValidationError("actor_identifier is required for the receipt.")

    Workspace = _model("ProjectWorkspace")
    locked_workspace = Workspace.objects.select_for_update().get(pk=workspace.pk)
    locked_workspace_id, locked_workspace_code = _workspace_identity(locked_workspace)
    if (
        locked_workspace_id != preview.workspace_id
        or locked_workspace_code != preview.workspace_code
    ):
        raise FoundationPackageConflictError(
            "Locked workspace identity differs from the immutable preview."
        )
    package, repeated_warnings = validate_foundation_package(preview.payload_copy())
    if package["manifest"]["payload_sha256"] != preview.checksum:
        raise FoundationPackageValidationError("Preview payload was changed after validation.")
    _validate_workspace_definition(package, locked_workspace)

    selected_existing, normalized_selected = _resolve_selected_lane(
        package,
        workspace=locked_workspace,
        selected_input=_deep_thaw(preview.selected_input),
    )
    if preview.adapter == "json":
        committed_kind = normalized_selected.get("raw_input_kind")
        committed_sha256 = normalized_selected.get("raw_input_sha256")
        committed_name = normalized_selected.get("raw_input_name", "")
        if (
            committed_kind not in RAW_INPUT_KINDS
            or committed_kind != preview.raw_input_kind
            or committed_sha256 != preview.raw_input_sha256
            or committed_name != preview.raw_input_name
        ):
            raise FoundationPackageValidationError(
                "Preview raw input provenance was changed after validation."
            )
    verified_identity_map = _source_identity_map(package)
    verified_lineage = _correction_lineage(package)
    verified_changes = _intended_changes(
        package,
        workspace=locked_workspace,
        selected_existing=selected_existing,
    )
    if (
        verified_identity_map != _deep_thaw(preview.source_identity_map)
        or list(verified_lineage) != _deep_thaw(preview.correction_lineage)
        or verified_changes != _deep_thaw(preview.intended_changes)
    ):
        raise FoundationPackageValidationError(
            "Preview identity/change report was changed after validation."
        )
    selected_source_column = normalized_selected.get("selected_source_column", "")
    if not isinstance(selected_source_column, str):
        raise FoundationPackageValidationError("selected_source_column must be text.")
    target_experiment = None
    target_assessment_set = None
    if normalized_selected.get("target_experiment_id"):
        target_experiment = _model("Experiment").objects.get(
            pk=UUID(normalized_selected["target_experiment_id"]),
            workspace=locked_workspace,
        )
        target_assessment_set = _model("AssessmentSet").objects.get(
            pk=UUID(normalized_selected["target_assessment_set_id"]),
            workspace=locked_workspace,
        )

    ImportRun = _model("ImportRun")
    receipt_code = f"IMPORT-{preview.checksum}"
    if ImportRun.objects.filter(
        workspace=locked_workspace,
        checksum=preview.checksum,
        status="COMMITTED",
    ).exists():
        raise FoundationPackageConflictError(
            "This exact package checksum already has an import receipt; replay is forbidden."
        )
    materialized = _materialize_foundation_rows(
        package,
        workspace=locked_workspace,
        allow_nonempty=allow_nonempty,
        inject_failure_after=inject_failure_after,
        selected_existing=selected_existing,
    )
    run = _new(
        ImportRun,
        {
            "code": receipt_code,
            "version": FOUNDATION_PACKAGE_VERSION,
            "workspace": locked_workspace,
            "target_experiment": target_experiment,
            "target_assessment_set": target_assessment_set,
            "package_format": FOUNDATION_PACKAGE_FORMAT,
            "package_id": package["package_id"],
            "package_version": FOUNDATION_PACKAGE_VERSION,
            "schema_version": package["schema_version"],
            "template_version": package["template_version"],
            "method_version": package["method_version"],
            "ontology_version": package["ontology_version"],
            "dataset_version": package["dataset_version"],
            "checksum": preview.checksum,
            "adapter": preview.adapter,
            "selected_input": normalized_selected,
            "selected_source_column": selected_source_column.strip(),
            "source_identity_map": verified_identity_map,
            "correction_lineage": list(verified_lineage),
            "intended_changes": verified_changes,
            "row_counts": {**dict(preview.counts), "materialized": materialized},
            "warnings": list(dict.fromkeys((*preview.warnings, *repeated_warnings))),
            "errors": [],
            "allow_nonempty": allow_nonempty,
            "status": "COMMITTED",
            "actor_identifier": actor_identifier.strip(),
            "committed_at": datetime.now(timezone.utc),
        },
    )
    from domain.policies import record_foundation_audit

    record_foundation_audit(
        workspace=locked_workspace,
        action="IMPORT",
        actor_identifier=actor_identifier.strip(),
        entity_type="IMPORT_RUN",
        entity_id=run.pk,
        after={
            "package_id": package["package_id"],
            "checksum": preview.checksum,
            "schema_version": package["schema_version"],
            "materialized_rows": materialized,
        },
    )
    return _receipt_view(run)


def _raw_input_checksum(raw: Any, *, adapter: str | None = None) -> str:
    if (adapter or "").strip().lower() == "json":
        try:
            _, provenance = _capture_json_input(raw)
        except FoundationPackageError:
            provenance = {}
        if provenance:
            return provenance["raw_input_sha256"]
    if isinstance(raw, Path):
        try:
            value = raw.read_bytes()
        except OSError as exc:
            value = str(exc).encode("utf-8")
    elif isinstance(raw, bytes):
        value = raw
    elif isinstance(raw, str):
        value = raw.encode("utf-8")
    elif isinstance(raw, Mapping):
        value = canonical_json(raw).encode("utf-8")
    else:
        value = repr(raw).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


_ASCII_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _receipt_json_snapshot(value: Any, *, depth: int = 0) -> Any:
    """Create a bounded JSON-safe forensic snapshot for an invalid attempt."""

    if depth > 8:
        return {"truncated": True, "reason": "maximum nesting depth"}
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) <= 4096:
            return value
        encoded = value.encode("utf-8")
        return {
            "prefix": value[:4096],
            "original_length": len(value),
            "sha256": hashlib.sha256(encoded).hexdigest(),
            "truncated": True,
        }
    if isinstance(value, Mapping):
        items = list(value.items())
        result = {
            str(key)[:255]: _receipt_json_snapshot(item, depth=depth + 1)
            for key, item in items[:256]
        }
        if len(items) > 256:
            result["__truncated_entries__"] = len(items) - 256
        return result
    if isinstance(value, (list, tuple, set)):
        items = list(value)
        result = [_receipt_json_snapshot(item, depth=depth + 1) for item in items[:256]]
        if len(items) > 256:
            result.append({"truncated_entries": len(items) - 256})
        return result
    if isinstance(value, (UUID, Path, date, datetime, Decimal)):
        return str(value)
    return _receipt_json_snapshot(repr(value), depth=depth + 1)


def _safe_receipt_text(value: Any, *, max_length: int, label: str) -> str:
    """Keep model strings bounded/ASCII without silently truncating identity."""

    raw = str(value or "").strip()
    if raw and raw.isascii() and len(raw) <= max_length:
        return raw
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prefix = f"INVALID-{label}-"
    if len(prefix) + len(digest) <= max_length:
        return f"{prefix}{digest}"
    return digest[:max_length]


def _safe_receipt_code(value: Any, *, max_length: int, label: str) -> str:
    raw = str(value or "").strip()
    if len(raw) <= max_length and _ASCII_CODE_PATTERN.fullmatch(raw):
        return raw
    return _safe_receipt_text(raw, max_length=max_length, label=label)


@transaction.atomic
def _record_unsuccessful_import(
    *,
    workspace: Any,
    raw: Any,
    adapter: str,
    selected_input: Mapping[str, Any] | None,
    allow_nonempty: bool,
    actor_identifier: str,
    errors: tuple[Mapping[str, str], ...],
    status: str,
    checksum: str | None = None,
    preserve_captured_provenance: bool = False,
) -> FoundationImportReceipt:
    """Append one rejected/failed attempt after materialization rollback has ended."""

    if status not in {"REJECTED", "FAILED"}:
        raise ValueError("Unsuccessful import status must be REJECTED or FAILED.")
    if not actor_identifier.strip():
        raise FoundationPackageValidationError(
            "actor_identifier is required for an unsuccessful import receipt."
        )
    raw_selected = dict(selected_input or {})
    selected = _receipt_json_snapshot(raw_selected)
    assert isinstance(selected, dict)
    captured_kind = selected.get("raw_input_kind")
    captured_sha256 = selected.get("raw_input_sha256")
    captured_name = selected.get("raw_input_name", "")
    has_captured_provenance = (
        preserve_captured_provenance
        and captured_kind in RAW_INPUT_KINDS
        and isinstance(captured_sha256, str)
        and _SHA256_PATTERN.fullmatch(captured_sha256) is not None
        and isinstance(captured_name, str)
    )
    if isinstance(raw, Path):
        selected["input_name"] = raw.name
        selected["input_sha256"] = (
            captured_sha256
            if has_captured_provenance
            else _raw_input_checksum(raw, adapter=adapter)
        )
    target_experiment = None
    target_assessment_set = None
    experiment_raw = selected.get("target_experiment_id")
    set_raw = selected.get("target_assessment_set_id")
    if experiment_raw is not None and set_raw is not None:
        try:
            target_experiment = _model("Experiment").objects.filter(
                workspace=workspace, pk=UUID(str(experiment_raw))
            ).first()
            target_assessment_set = _model("AssessmentSet").objects.filter(
                workspace=workspace, pk=UUID(str(set_raw))
            ).first()
        except ValueError:
            target_experiment = None
            target_assessment_set = None
        if (
            target_experiment is None
            or target_assessment_set is None
            or target_experiment.assessment_set_id != target_assessment_set.pk
        ):
            target_experiment = None
            target_assessment_set = None

    checksum_candidate = str(
        checksum or _raw_input_checksum(raw, adapter=adapter)
    ).strip().lower()
    raw_checksum = (
        checksum_candidate
        if _SHA256_PATTERN.fullmatch(checksum_candidate)
        else hashlib.sha256(checksum_candidate.encode("utf-8")).hexdigest()
    )
    package_meta: Mapping[str, Any] = {}
    try:
        adapted = adapt_foundation_input(raw, adapter=adapter)
        package_meta = adapted.get("meta", adapted)
    except FoundationPackageError:
        package_meta = {}
    raw_receipt_metadata = {
        "package_id": package_meta.get("package_id"),
        "schema_version": package_meta.get("schema_version"),
        "workbook_schema_version": package_meta.get("workbook_schema_version"),
        "template_version": package_meta.get("template_version"),
        "method_version": package_meta.get("method_version"),
        "ontology_version": package_meta.get("ontology_version"),
        "dataset_version": package_meta.get("dataset_version"),
        "adapter": adapter,
        "actor_identifier": actor_identifier,
    }
    selected["raw_receipt_metadata"] = _receipt_json_snapshot(raw_receipt_metadata)
    if not has_captured_provenance:
        fallback_provenance: dict[str, str] = {}
        if adapter.strip().lower() == "json":
            try:
                _, fallback_provenance = _capture_json_input(raw)
            except FoundationPackageError:
                fallback_provenance = {}
        if fallback_provenance:
            captured_kind = fallback_provenance["raw_input_kind"]
            captured_sha256 = fallback_provenance["raw_input_sha256"]
            captured_name = fallback_provenance.get("raw_input_name", "")
        else:
            if isinstance(raw, Path):
                captured_kind = "PATH_BYTES"
                captured_name = raw.name
            elif isinstance(raw, bytes):
                captured_kind = "BYTES"
                captured_name = ""
            elif isinstance(raw, str) and raw.lstrip().startswith(("{", "[")):
                captured_kind = "TEXT"
                captured_name = ""
            elif isinstance(raw, Mapping):
                captured_kind = "CANONICAL_MAPPING"
                captured_name = ""
            else:
                captured_kind = ""
                captured_name = ""
            captured_sha256 = (
                _raw_input_checksum(raw, adapter=adapter) if captured_kind else ""
            )
    selected["raw_input_kind"] = captured_kind
    selected["raw_input_sha256"] = captured_sha256
    if captured_name:
        selected["raw_input_name"] = captured_name
    else:
        selected.pop("raw_input_name", None)
    package_id = _safe_receipt_code(
        package_meta.get("package_id") or f"INVALID-{raw_checksum}",
        max_length=128,
        label="PACKAGE",
    )
    version_raw = str(
        package_meta.get("workbook_schema_version")
        or package_meta.get("schema_version")
        or "UNKNOWN"
    )
    version = _safe_receipt_text(version_raw, max_length=64, label="SCHEMA")
    safe_actor_identifier = _safe_receipt_text(
        actor_identifier, max_length=255, label="ACTOR"
    )
    safe_adapter = _safe_receipt_text(
        adapter.strip().lower(), max_length=255, label="ADAPTER"
    )
    selected_source_column = _safe_receipt_text(
        selected.get("selected_source_column") or "",
        max_length=255,
        label="SOURCE-COLUMN",
    ) if selected.get("selected_source_column") else ""
    attempt_code = f"IMPORT-{status}-{raw_checksum}-{uuid4().hex}"
    run = _new(
        _model("ImportRun"),
        {
            "code": attempt_code,
            "version": FOUNDATION_PACKAGE_VERSION,
            "workspace": workspace,
            "target_experiment": target_experiment,
            "target_assessment_set": target_assessment_set,
            "package_format": FOUNDATION_PACKAGE_FORMAT,
            "package_id": package_id,
            "package_version": FOUNDATION_PACKAGE_VERSION,
            "schema_version": version,
            "template_version": _safe_receipt_text(
                package_meta.get("template_version") or version,
                max_length=64,
                label="TEMPLATE",
            ),
            "method_version": _safe_receipt_text(
                package_meta.get("method_version") or "UNKNOWN",
                max_length=64,
                label="METHOD",
            ),
            "ontology_version": _safe_receipt_text(
                package_meta.get("ontology_version") or "UNKNOWN",
                max_length=64,
                label="ONTOLOGY",
            ),
            "dataset_version": _safe_receipt_text(
                package_meta.get("dataset_version") or "UNKNOWN",
                max_length=64,
                label="DATASET",
            ),
            "checksum": raw_checksum,
            "adapter": safe_adapter,
            "selected_input": selected,
            "selected_source_column": selected_source_column,
            "source_identity_map": {},
            "correction_lineage": [],
            "intended_changes": {},
            "row_counts": {},
            "warnings": [],
            "errors": [dict(item) for item in errors],
            "allow_nonempty": allow_nonempty,
            "status": status,
            "actor_identifier": safe_actor_identifier,
            "committed_at": None,
        },
    )
    from domain.policies import record_foundation_audit

    record_foundation_audit(
        workspace=workspace,
        action="IMPORT",
        actor_identifier=safe_actor_identifier,
        entity_type="IMPORT_RUN",
        entity_id=run.pk,
        after={
            "status": status,
            "checksum": raw_checksum,
            "errors": [dict(item) for item in errors],
        },
    )
    return _receipt_view(run)


def attempt_foundation_import(
    raw: Any,
    *,
    workspace: Any,
    adapter: str = "json",
    selected_input: Mapping[str, Any] | None = None,
    allow_nonempty: bool = False,
    actor_identifier: str,
    inject_failure_after: int | None = None,
) -> FoundationImportAttemptResult:
    """Orchestrate preview/commit and persist a post-rollback attempt receipt."""

    report = inspect_foundation_package(
        raw,
        workspace=workspace,
        adapter=adapter,
        selected_input=selected_input,
        allow_nonempty=allow_nonempty,
    )
    if not report.valid:
        receipt = _record_unsuccessful_import(
            workspace=workspace,
            raw=raw,
            adapter=adapter,
            selected_input=selected_input,
            allow_nonempty=allow_nonempty,
            actor_identifier=actor_identifier,
            errors=report.errors,
            status="REJECTED",
        )
        return FoundationImportAttemptResult("REJECTED", report, receipt)
    assert report.preview is not None
    try:
        receipt = commit_foundation_package(
            report.preview,
            workspace=workspace,
            allow_nonempty=allow_nonempty,
            actor_identifier=actor_identifier,
            inject_failure_after=inject_failure_after,
        )
    except FoundationPackageError as exc:
        rejected_report = FoundationValidationReport(
            valid=False,
            preview=report.preview,
            errors=(_structured_error(exc),),
        )
        receipt = _record_unsuccessful_import(
            workspace=workspace,
            raw=raw,
            adapter=adapter,
            selected_input=_deep_thaw(report.preview.selected_input),
            allow_nonempty=allow_nonempty,
            actor_identifier=actor_identifier,
            errors=rejected_report.errors,
            status="REJECTED",
            checksum=report.preview.checksum,
            preserve_captured_provenance=True,
        )
        return FoundationImportAttemptResult("REJECTED", rejected_report, receipt)
    except Exception as exc:
        failed_report = FoundationValidationReport(
            valid=False,
            preview=report.preview,
            errors=(_structured_error(exc),),
        )
        receipt = _record_unsuccessful_import(
            workspace=workspace,
            raw=raw,
            adapter=adapter,
            selected_input=_deep_thaw(report.preview.selected_input),
            allow_nonempty=allow_nonempty,
            actor_identifier=actor_identifier,
            errors=failed_report.errors,
            status="FAILED",
            checksum=report.preview.checksum,
            preserve_captured_provenance=True,
        )
        return FoundationImportAttemptResult("FAILED", failed_report, receipt)
    return FoundationImportAttemptResult("COMMITTED", report, receipt)


def _materialize_foundation_rows(
    package: Mapping[str, Any],
    *,
    workspace: Any,
    allow_nonempty: bool,
    inject_failure_after: int | None,
    selected_existing: Mapping[str, Mapping[str, Any]] | None = None,
) -> int:
    """Materialize package rows from stable codes without update-or-create paths."""

    specs = _materialization_specs()
    selected_existing = selected_existing or {}
    _validate_workspace_definition(package, workspace)
    if not allow_nonempty:
        for spec in specs:
            model = spec["model"]
            if spec.get("workspace_bound", True) and model.objects.filter(workspace=workspace).exists():
                raise FoundationPackageConflictError(
                    "Target workspace is non-empty; import will not overwrite or merge it."
                )

    created: dict[str, dict[str, Any]] = {section: {} for section in ENTITY_SECTIONS}
    created["compatibility_receipts"] = {}
    definition = workspace.definition_version
    created["project_definition_versions"][definition.code] = definition
    count = 0
    for spec in specs:
        section = spec["section"]
        model = spec["model"]
        items = _dependency_order(
            package[section],
            spec.get("dependency_field"),
            section,
        )
        for item in items:
            existing = _existing_for_item(model, item, workspace, spec)
            if existing is not None:
                selected = selected_existing.get(section, {}).get(item["code"])
                if (
                    (spec.get("allow_exact_reuse") or selected is not None)
                    and (selected is None or selected.pk == existing.pk)
                    and _matches_reusable(section, item, existing)
                ):
                    created[section][item["code"]] = existing
                    continue
                raise FoundationPackageConflictError(
                    f"{section} stable UUID/code already exists; overwrite is forbidden."
                )
            values = _values_for_section(section, item, created, workspace)
            obj = _new(model, values)
            created[section][item["code"]] = obj
            count += 1
            if inject_failure_after is not None and count >= inject_failure_after:
                raise FoundationPackageValidationError("Injected mid-import rollback test failure.")
    return count


def _materialization_specs() -> list[dict[str, Any]]:
    """Central model ordering for the adapter-independent canonical DTO."""

    rows = (
        ("time_slices", "TimeSlice", None, True, False),
        ("actors", "Actor", "parent_code", True, False),
        ("analytical_elements", "AnalyticalElement", "parent_code", True, False),
        ("actor_relations", "ActorRelation", None, True, False),
        ("assessment_sets", "AssessmentSet", None, True, False),
        ("expert_profiles", "ExpertProfile", None, True, False),
        ("experiments", "Experiment", None, True, False),
        ("actor_element_roles", "ActorElementRole", None, True, False),
        ("actor_element_assessments", "ActorElementAssessment", "supersedes_code", True, False),
        ("parameter_definitions", "ParameterDefinition", None, False, True),
        ("parameter_values", "ParameterValue", "supersedes_code", True, False),
        ("sources", "Source", None, True, False),
        ("documents", "Document", None, True, False),
        ("document_versions", "DocumentVersion", "supersedes_code", True, False),
        ("document_contents", "DocumentContent", None, True, False),
        ("text_fragments", "TextFragment", None, True, False),
        ("facts", "Fact", None, True, False),
        ("fact_evidence_links", "FactEvidence", None, True, False),
        ("assessment_fact_links", "AssessmentEvidence", None, True, False),
        ("parameter_value_fact_links", "ParameterValueEvidence", None, True, False),
        ("gaps", "DataGap", None, True, False),
        ("help_topics", "HelpTopic", None, False, True),
        ("ui_help_bindings", "UIHelpBinding", None, True, False),
        ("power_profiles", "PowerProfile", None, True, False),
        ("power_components", "PowerComponent", None, True, False),
        ("power_component_fact_links", "PowerComponentEvidence", None, True, False),
        ("chat_conversations", "ChatConversation", None, True, False),
        ("chat_messages", "ChatMessage", None, True, False),
        ("chat_citations", "ChatCitation", None, True, False),
        ("terminology_entries", "TerminologyEntry", None, True, False),
        ("legacy_term_mappings", "LegacyTermMapping", None, True, False),
        ("compatibility_receipts", "LegacyCompatibilityReceipt", None, True, False),
    )
    return [
        {
            "section": section,
            "model": _model(model_name),
            "dependency_field": dependency_field,
            "workspace_bound": workspace_bound,
            "allow_exact_reuse": allow_exact_reuse,
        }
        for section, model_name, dependency_field, workspace_bound, allow_exact_reuse in rows
    ]


def _dependency_order(
    items: Any,
    dependency_field: str | None,
    section: str,
) -> list[Mapping[str, Any]]:
    pending = list(items)
    if dependency_field is None:
        return sorted(pending, key=lambda item: (item["code"], item["id"]))
    known = {item["code"] for item in pending}
    ordered: list[Mapping[str, Any]] = []
    emitted: set[str] = set()
    while pending:
        ready = [
            item
            for item in pending
            if item.get(dependency_field) is None
            or item.get(dependency_field) in emitted
            or item.get(dependency_field) not in known
        ]
        if not ready:
            _reject(f"{section} contains a cyclic {dependency_field} lineage.")
        for item in sorted(ready, key=lambda candidate: (candidate["code"], candidate["id"])):
            pending.remove(item)
            ordered.append(item)
            emitted.add(item["code"])
    return ordered


def _existing_for_item(
    model: type[Any],
    item: Mapping[str, Any],
    workspace: Any,
    spec: Mapping[str, Any],
) -> Any | None:
    query = Q(pk=UUID(item["id"]))
    if spec.get("workspace_bound", True):
        query |= Q(workspace=workspace, code=item["code"])
    elif model.__name__ == "ParameterDefinition":
        query |= Q(project=workspace.project, code=item["code"])
    elif model.__name__ == "HelpTopic":
        query |= Q(
            stable_key=item["stable_key"],
            locale=item["locale"],
            version=item["version"],
        )
    return model.objects.filter(query).first()


def _matches_reusable(section: str, item: Mapping[str, Any], existing: Any) -> bool:
    if str(existing.pk) != item["id"] or existing.code != item["code"] or existing.version != item["version"]:
        return False
    if section == "parameter_definitions":
        return (
            existing.name == item["name"]
            and existing.description == item["description"]
            and existing.target_type == item["target_type"]
            and existing.value_type == item["value_type"]
            and (str(existing.scale_min) if existing.scale_min is not None else None)
            == (str(item["scale_min"]) if item["scale_min"] is not None else None)
            and (str(existing.scale_max) if existing.scale_max is not None else None)
            == (str(item["scale_max"]) if item["scale_max"] is not None else None)
            and existing.scale_metadata == item["scale_metadata"]
        )
    if section == "help_topics":
        return (
            existing.stable_key == item["stable_key"]
            and existing.title == item["title"]
            and existing.application_scope == item["application_scope"]
            and existing.construct_version == item["construct_version"]
            and existing.term_version == item["term_version"]
            and existing.locale == item["locale"]
            and existing.sanitized_html == item["sanitized_html"]
            and existing.content_sha256 == item["content_sha256"]
            and existing.publication_status == item["publication_status"]
            and _iso_datetime(existing.published_at) == (
                _iso_datetime(_parse_datetime(item["published_at"], "help_topics.published_at"))
                if item["published_at"] is not None
                else None
            )
        )
    try:
        return _export_item(section, existing) == copy.deepcopy(dict(item))
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def _common_values(
    item: Mapping[str, Any],
    model: type[Any],
    workspace: Any,
) -> dict[str, Any]:
    fields = _field_names(model)
    values: dict[str, Any] = {
        "id": UUID(item["id"]),
        "code": item["code"],
        "version": item["version"],
    }
    if "workspace" in fields:
        values["workspace"] = workspace
    if "project" in fields:
        values["project"] = workspace.project
    if "metadata" in fields:
        values["metadata"] = copy.deepcopy(item.get("metadata", {}))
    elif item.get("metadata"):
        _reject(f"{model.__name__} cannot persist non-empty canonical metadata.")
    return values


def _direct(values: dict[str, Any], item: Mapping[str, Any], *fields: str) -> None:
    for field in fields:
        values[field] = copy.deepcopy(item[field])


def _values_for_section(
    section: str,
    item: Mapping[str, Any],
    created: Mapping[str, Mapping[str, Any]],
    workspace: Any,
) -> dict[str, Any]:
    model = next(spec["model"] for spec in _materialization_specs() if spec["section"] == section)
    values = _common_values(item, model, workspace)
    if section == "time_slices":
        _direct(values, item, "name", "order")
        values["cutoff_date"] = _parse_date(item["cutoff_date"], f"{section}.cutoff_date")
    elif section == "actors":
        _direct(values, item, "actor_type", "label", "description", "order")
        values["parent"] = created[section].get(item["parent_code"])
    elif section == "analytical_elements":
        _direct(values, item, "element_type", "label", "reference_statement", "description", "order")
        values["parent"] = created[section].get(item["parent_code"])
    elif section == "actor_relations":
        _direct(values, item, "relation_type", "description")
        values["source_actor"] = created["actors"][item["source_actor_code"]]
        values["target_actor"] = created["actors"][item["target_actor_code"]]
    elif section == "assessment_sets":
        _direct(values, item, "kind", "name", "description")
    elif section == "expert_profiles":
        _direct(values, item, "kind", "display_name", "identity_key", "provider", "model_name")
    elif section == "experiments":
        _direct(values, item, "experiment_type", "name", "status", "color", "order", "method_version")
        values["expert_profile"] = created["expert_profiles"][item["expert_profile_code"]]
        values["assessment_set"] = created["assessment_sets"][item["assessment_set_code"]]
        values["frozen_at"] = (
            None if item["frozen_at"] is None else _parse_datetime(item["frozen_at"], f"{section}.frozen_at")
        )
    elif section == "actor_element_roles":
        _direct(values, item, "role", "note")
        values["actor"] = created["actors"][item["actor_code"]]
        values["element"] = created["analytical_elements"][item["element_code"]]
    elif section == "actor_element_assessments":
        _direct(values, item, "reference_statement", "reference_statement_incomplete", "status", "confidence_level", "method_version", "provenance")
        values["actor"] = created["actors"][item["actor_code"]]
        values["element"] = created["analytical_elements"][item["element_code"]]
        values["time_slice"] = created["time_slices"][item["time_slice_code"]]
        values["experiment"] = created["experiments"][item["experiment_code"]]
        values["assessment_set"] = created["assessment_sets"][item["assessment_set_code"]]
        values["supersedes"] = created[section].get(item["supersedes_code"])
        values["knowledge_cutoff"] = _parse_date(item["knowledge_cutoff"], f"{section}.knowledge_cutoff")
    elif section == "parameter_definitions":
        _direct(values, item, "name", "description", "target_type", "value_type", "scale_metadata")
        values["scale_min"] = _decimal_or_none(item["scale_min"], f"{section}.scale_min")
        values["scale_max"] = _decimal_or_none(item["scale_max"], f"{section}.scale_max")
    elif section == "parameter_values":
        assessment = created["actor_element_assessments"][item["assessment_code"]]
        _direct(values, item, "status", "temporal_status", "value", "note", "range_min", "range_max", "rationale")
        values["time_slice"] = assessment.time_slice
        values["assessment_set"] = created["assessment_sets"][item["assessment_set_code"]]
        values["actor_element_assessment"] = assessment
        values["parameter_definition"] = created["parameter_definitions"][item["parameter_definition_code"]]
        values["supersedes"] = created[section].get(item["supersedes_code"])
        values["target_type"] = "ACTOR_ELEMENT_ASSESSMENT"
        values["target_id"] = assessment.pk
        values["confidence"] = _decimal_or_none(item["confidence"], f"{section}.confidence")
    elif section == "sources":
        _direct(values, item, "name", "publisher", "independence_group", "independence_status", "homepage_url")
    elif section == "documents":
        _direct(values, item, "title", "canonical_url")
        values["source"] = created["sources"][item["source_code"]]
        values["publication_date"] = _date_or_none(item["published_on"], f"{section}.published_on")
        values["accessed_on"] = _date_or_none(item["accessed_on"], f"{section}.accessed_on")
    elif section == "document_versions":
        _direct(values, item, "status", "capture_url", "media_type")
        values["document"] = created["documents"][item["document_code"]]
        values["supersedes"] = created[section].get(item.get("supersedes_code"))
        values["captured_at"] = _parse_datetime(item["captured_at"], f"{section}.captured_at")
        values["content_sha256"] = item["checksum"] or ""
    elif section == "document_contents":
        values["document_version"] = created["document_versions"][item["document_version_code"]]
        values["content_sha256"] = item["checksum"]
        values["normalization_version"] = item["normalization_version"]
        if item["encoding"] == "UTF8":
            values.update(normalized_text=item["content"], original_bytes=None, encoding="utf-8")
        else:
            values.update(normalized_text="", original_bytes=_decode_content(item, section), encoding="binary")
    elif section == "text_fragments":
        _direct(values, item, "anchor_status", "start_offset", "end_offset", "selector", "page", "section", "exact_text")
        values["document_version"] = created["document_versions"][item["document_version_code"]]
        values["text_sha256"] = item["exact_text_sha256"] or ""
    elif section == "facts":
        _direct(values, item, "fact_type", "statement", "origin", "directness", "visibility", "status", "temporal_status", "coder_identifier")
        values["confidence"] = _decimal_or_none(item["confidence"], f"{section}.confidence")
        values["experiment"] = created["experiments"].get(item["experiment_code"])
    elif section == "fact_evidence_links":
        _direct(values, item, "relation", "temporal_status", "rationale")
        values["fact"] = created["facts"][item["fact_code"]]
        values["fragment"] = created["text_fragments"][item["fragment_code"]]
        values["learned_on"] = _date_or_none(item["learned_on"], f"{section}.learned_on")
    elif section == "assessment_fact_links":
        _direct(values, item, "role", "temporal_status", "rationale")
        values["assessment"] = created["actor_element_assessments"][item["assessment_code"]]
        values["fact"] = created["facts"][item["fact_code"]]
        values["learned_on"] = _date_or_none(item["learned_on"], f"{section}.learned_on")
    elif section == "parameter_value_fact_links":
        _direct(values, item, "role", "temporal_status", "rationale")
        values["parameter_value"] = created["parameter_values"][item["parameter_value_code"]]
        values["fact"] = created["facts"][item["fact_code"]]
        values["learned_on"] = _date_or_none(item["learned_on"], f"{section}.learned_on")
    elif section == "gaps":
        values.update(
            gap_type=item["type"],
            entity_type="DocumentVersion" if item["document_version_code"] else "Workspace",
            entity_code=item["document_version_code"] or workspace.code,
            required_behavior=item["required_behavior"],
            resolved=item["status"] == "RESOLVED",
            resolution=item["resolution"],
        )
    elif section == "help_topics":
        _direct(values, item, "stable_key", "title", "application_scope", "construct_version", "term_version", "locale", "sanitized_html", "content_sha256", "publication_status")
        values["published_at"] = (
            None if item["published_at"] is None else _parse_datetime(item["published_at"], f"{section}.published_at")
        )
    elif section == "ui_help_bindings":
        _direct(values, item, "ui_key", "locale")
        values["help_topic"] = created["help_topics"][item["help_topic_code"]]
    elif section == "power_profiles":
        _direct(values, item, "method_version", "note")
        values["assessment"] = created["actor_element_assessments"][item["assessment_code"]]
    elif section == "power_components":
        _direct(values, item, "dimension", "status", "value", "rationale", "provenance")
        values["profile"] = created["power_profiles"][item["profile_code"]]
        values["confidence"] = _decimal_or_none(item["confidence"], f"{section}.confidence")
    elif section == "power_component_fact_links":
        _direct(values, item, "role")
        values["component"] = created["power_components"][item["component_code"]]
        values["fact"] = created["facts"][item["fact_code"]]
    elif section == "chat_conversations":
        _direct(
            values,
            item,
            "channel_type",
            "owner_identifier",
            "participants",
            "title",
            "provider",
            "model_name",
        )
        values["archived_at"] = _datetime_or_none(
            item["archived_at"], f"{section}.archived_at"
        )
    elif section == "chat_messages":
        _direct(
            values,
            item,
            "sequence",
            "role",
            "content",
            "provider",
            "model_name",
            "provider_request_id",
            "status",
            "error",
        )
        values["conversation"] = created["chat_conversations"][item["conversation_code"]]
    elif section == "chat_citations":
        _direct(values, item, "quote_start", "quote_end", "quote_text", "label")
        values["message"] = created["chat_messages"][item["message_code"]]
        values["fact"] = created["facts"].get(item["fact_code"])
        values["fragment"] = created["text_fragments"].get(item["fragment_code"])
        values["document_version"] = created["document_versions"].get(item["document_version_code"])
    elif section == "terminology_entries":
        _direct(values, item, "canonical_ru_name", "canonical_ru_acronym", "exact_en_term", "exact_en_acronym", "source_framework", "source_citation", "construct_version", "locale", "display_metadata")
    elif section == "legacy_term_mappings":
        _direct(values, item, "legacy_code", "legacy_label", "source_version", "mapping_status", "notes")
        values["terminology_entry"] = created["terminology_entries"].get(item["terminology_entry_code"])
    elif section == "compatibility_receipts":
        _direct(values, item, "legacy_model", "legacy_code", "canonical_model", "canonical_code", "status", "reason", "migration_version")
        values["legacy_id"] = UUID(item["legacy_id"])
        values["canonical_id"] = UUID(item["canonical_id"]) if item["canonical_id"] else None
    else:
        raise AssertionError(f"Unmapped Foundation section {section}.")
    return values


def export_foundation_package(workspace: Any) -> dict[str, Any]:
    """Export the exact canonical graph for one strict workspace boundary."""

    _workspace_identity(workspace)
    definition = workspace.definition_version
    ImportRun = _model("ImportRun")
    last_run = ImportRun.objects.filter(
        workspace=workspace,
        status="COMMITTED",
    ).order_by("-committed_at", "-created_at").first()
    payload: dict[str, Any] = {
        "format": FOUNDATION_PACKAGE_FORMAT,
        "format_version": FOUNDATION_PACKAGE_VERSION,
        "package_id": last_run.package_id if last_run else f"EXPORT-{workspace.code}",
        "schema_version": last_run.schema_version if last_run else definition.version,
        "template_version": last_run.template_version if last_run else "UNSPECIFIED",
        "method_version": last_run.method_version if last_run else "UNSPECIFIED",
        "ontology_version": last_run.ontology_version if last_run else "UNSPECIFIED",
        "dataset_version": last_run.dataset_version if last_run else "UNSPECIFIED",
        "workspace": {
            "id": str(workspace.pk),
            "code": workspace.code,
            "version": workspace.version,
            "project_definition_version_id": str(definition.pk),
            "project_definition_hash": workspace.definition_manifest_hash,
            "label": workspace.name,
            "metadata": workspace.metadata,
        },
        "project_definition_versions": [_export_definition(definition)],
        "compatibility_receipts": [],
    }
    for section in ENTITY_SECTIONS:
        if section == "project_definition_versions":
            continue
        payload[section] = [
            _export_item(section, obj)
            for obj in _query_for_export(section, workspace)
        ]
    payload["compatibility_receipts"] = [
        _export_item("compatibility_receipts", obj)
        for obj in _query_for_export("compatibility_receipts", workspace)
    ]
    package = seal_foundation_package(payload)
    validate_foundation_package(package)
    return package


def export_foundation_json(workspace: Any) -> str:
    return canonical_json(export_foundation_package(workspace)) + "\n"


def _project_identity_2_1(project: Any) -> dict[str, str]:
    if project is None or getattr(project, "pk", None) is None:
        raise FoundationPackageValidationError("A persisted Project is required.")
    return {
        "id": str(project.pk),
        "code": str(project.code),
        "version": str(project.version),
    }


def _bounded_package_id_2_1(prefix: str, value: object) -> str:
    """Keep derived 2.1 package identities valid without truncating identity."""

    raw_value = str(value)
    candidate = f"{prefix}-{raw_value}"
    if len(candidate) <= 128 and _ASCII_CODE_PATTERN.fullmatch(candidate):
        return candidate
    return f"{prefix}-{hashlib.sha256(raw_value.encode('utf-8')).hexdigest()}"


def export_workspace_package_2_1(workspace: Any) -> dict[str, Any]:
    """Wrap an unchanged canonical 2.0 workspace graph in a typed 2.1 scope."""

    nested = export_foundation_package(workspace)
    package = {
        "format": FOUNDATION_PACKAGE_FORMAT,
        "format_version": FOUNDATION_PACKAGE_VERSION_2_1,
        "package_scope": "WORKSPACE",
        "package_id": _bounded_package_id_2_1("V21", nested["package_id"]),
        "project": _project_identity_2_1(workspace.project),
        "selected_definition_id": nested["workspace"][
            "project_definition_version_id"
        ],
        "workspace": copy.deepcopy(nested["workspace"]),
        "workspace_package": nested,
        "project_definition": None,
    }
    sealed = seal_foundation_package_2_1(package)
    return validate_foundation_package_2_1(sealed)


def export_project_definition_package_2_1(definition: Any) -> dict[str, Any]:
    """Export one exact typed definition without requiring a workspace."""

    if definition is None or getattr(definition, "pk", None) is None:
        raise FoundationPackageValidationError(
            "A persisted ProjectDefinitionVersion is required."
        )
    from domain.services.project_definitions import (
        hash_project_definition_manifest_v1,
        identify_typed_project_definition_manifest,
    )

    if not identify_typed_project_definition_manifest(definition.manifest):
        raise FoundationPackageValidationError(
            "Only an explicitly typed V1 manifest can use PROJECT_DEFINITION scope."
        )
    actual_hash = hash_project_definition_manifest_v1(definition.manifest)
    if definition.manifest_hash != actual_hash:
        raise FoundationPackageValidationError(
            "Stored definition hash does not match the exact typed manifest."
        )
    package = {
        "format": FOUNDATION_PACKAGE_FORMAT,
        "format_version": FOUNDATION_PACKAGE_VERSION_2_1,
        "package_scope": "PROJECT_DEFINITION",
        "package_id": _bounded_package_id_2_1("DEFINITION", definition.code),
        "project": _project_identity_2_1(definition.project),
        "selected_definition_id": str(definition.pk),
        "workspace": None,
        "workspace_package": None,
        "project_definition": _export_definition(definition),
    }
    sealed = seal_foundation_package_2_1(package)
    return validate_foundation_package_2_1(sealed)


def export_project_definition_json_2_1(definition: Any) -> str:
    return canonical_json(export_project_definition_package_2_1(definition)) + "\n"


def _require_exact_project_2_1(package: Mapping[str, Any], project: Any) -> None:
    expected = _project_identity_2_1(project)
    if package["project"] != expected:
        raise FoundationPackageConflictError(
            "Foundation 2.1 project id/code/version differs from the explicit target Project."
        )


def _definition_plan_2_1(
    package: Mapping[str, Any],
    *,
    project: Any,
) -> tuple[str, Any | None]:
    """Resolve one stable definition identity without repair or retargeting."""

    definition_data = package["project_definition"]
    definition_id = UUID(definition_data["id"])
    Definition = _model("ProjectDefinitionVersion")
    by_id = Definition.objects.filter(pk=definition_id).first()
    by_code = Definition.objects.filter(
        project=project,
        code=definition_data["code"],
    ).first()
    by_version = Definition.objects.filter(
        project=project,
        version=definition_data["version"],
    ).first()
    identities = {row.pk for row in (by_id, by_code, by_version) if row is not None}
    if len(identities) > 1:
        raise FoundationPackageConflictError(
            "Project-definition id/code/version resolve to different persisted rows."
        )
    existing = by_id or by_code or by_version
    if existing is not None:
        if (
            str(existing.project_id) != str(project.pk)
            or str(existing.pk) != definition_data["id"]
            or existing.code != definition_data["code"]
            or existing.version != definition_data["version"]
        ):
            raise FoundationPackageConflictError(
                "Persisted project-definition stable identity differs from the package."
            )
        if _export_definition(existing) != definition_data:
            raise FoundationPackageConflictError(
                "Persisted project-definition bytes or lifecycle state differ from the package."
            )
        return "REUSE_EXACT", existing

    status = definition_data["publication_status"]
    if status == "DRAFT":
        return "CREATE_DRAFT", None
    if status == "PUBLISHED" and definition_data["is_current"]:
        return "BOOTSTRAP_PUBLISHED", None
    raise FoundationPackageConflictError(
        "Absent VALIDATED/RETIRED/non-current PUBLISHED snapshots cannot bypass the canonical lifecycle."
    )


def preview_foundation_package_2_1(
    raw: Mapping[str, Any],
    *,
    project: Any,
    workspace: Any | None = None,
    selected_input: Mapping[str, Any] | None = None,
    allow_nonempty: bool = False,
) -> Foundation21Preview:
    """Validate one typed 2.1 scope and derive an immutable DB plan."""

    canonical = validate_foundation_package_2_1(raw)
    _require_exact_project_2_1(canonical, project)
    checksum = canonical["manifest"]["payload_sha256"]
    if canonical["package_scope"] == "WORKSPACE":
        if workspace is None:
            raise FoundationPackageValidationError(
                "A 2.1 WORKSPACE package requires an explicit target workspace."
            )
        if str(workspace.project_id) != str(project.pk):
            raise FoundationPackageConflictError(
                "The target workspace belongs to a different Project."
            )
        nested_preview = preview_foundation_package(
            canonical["workspace_package"],
            workspace=workspace,
            adapter="json",
            selected_input=selected_input,
            allow_nonempty=allow_nonempty,
        )
        action = "IMPORT_WORKSPACE_2_0_PAYLOAD"
    else:
        from domain.services.project_definitions import (
            parse_project_definition_manifest_v1,
        )

        definition_data = canonical["project_definition"]
        if definition_data.get("metadata") not in ({}, None):
            raise FoundationPackageValidationError(
                "ProjectDefinitionVersion has no parallel metadata authority; "
                "definition metadata must remain inside the typed manifest project object."
            )
        dto = parse_project_definition_manifest_v1(
            definition_data["manifest"],
            project=project,
        )
        if dto.manifest_sha256 != definition_data["manifest_hash"]:
            raise FoundationPackageConflictError(
                "Typed manifest hash differs after exact persisted-Project validation."
            )
        action, _existing = _definition_plan_2_1(canonical, project=project)
        nested_preview = None
    return Foundation21Preview(
        valid=True,
        package_scope=canonical["package_scope"],
        checksum=checksum,
        project_id=str(project.pk),
        project_code=str(project.code),
        project_version=str(project.version),
        selected_definition_id=canonical["selected_definition_id"],
        intended_action=action,
        errors=(),
        _payload=_deep_freeze(canonical),
        _workspace_preview=nested_preview,
    )


def _locked_project_for_preview_2_1(
    preview: Foundation21Preview,
    project: Any,
) -> Any:
    Project = _model("Project")
    locked = Project.objects.select_for_update().get(pk=project.pk)
    locked_identity = _project_identity_2_1(locked)
    expected = {
        "id": preview.project_id,
        "code": preview.project_code,
        "version": preview.project_version,
    }
    if locked_identity != expected:
        raise FoundationPackageConflictError(
            "Locked Project identity differs from the immutable Foundation 2.1 preview."
        )
    return locked


def _create_definition_import_receipt_2_1(
    *,
    package: Mapping[str, Any],
    project: Any,
    definition: Any,
    action: str,
    actor_identifier: str,
) -> Any:
    from domain.enums import ImportPackageScope

    ImportRun = _model("ImportRun")
    checksum = package["manifest"]["payload_sha256"]
    if ImportRun.objects.filter(
        project=project,
        package_scope=ImportPackageScope.PROJECT_DEFINITION,
        checksum=checksum,
        status="COMMITTED",
    ).exists():
        raise FoundationPackageConflictError(
            "This exact project-definition package already has a committed receipt."
        )
    source = package["project_definition"]
    return _new(
        ImportRun,
        {
            "project": project,
            "workspace": None,
            "definition_version": definition,
            "package_scope": ImportPackageScope.PROJECT_DEFINITION,
            "code": f"IMPORT-{checksum}",
            "version": FOUNDATION_PACKAGE_VERSION_2_1,
            "package_format": FOUNDATION_PACKAGE_FORMAT,
            "package_id": package["package_id"],
            "package_version": FOUNDATION_PACKAGE_VERSION_2_1,
            "schema_version": source["schema_version"],
            "template_version": "1.0.0",
            "method_version": "PROJECT_DEFINITION_MANIFEST_VALIDATION_V1",
            "ontology_version": source["construct_version"],
            "dataset_version": source["version"],
            "checksum": checksum,
            "adapter": "json",
            "selected_input": {
                "package_scope": "PROJECT_DEFINITION",
                "intended_action": action,
                "source_definition_id": source["id"],
                "source_publication_status": source["publication_status"],
                "source_validated_at": source["validated_at"],
                "source_validated_by": source["validated_by"],
                "source_validation_result": copy.deepcopy(source["validation_result"]),
                "source_published_at": source["published_at"],
                "source_published_by": source["published_by"],
                "source_is_current": source["is_current"],
            },
            "selected_source_column": "",
            "source_identity_map": {
                "project_definition": {source["code"]: source["id"]},
            },
            "correction_lineage": (
                [
                    {
                        "code": source["code"],
                        "supersedes_code": source["supersedes_code"],
                    }
                ]
                if source["supersedes_code"]
                else []
            ),
            "intended_changes": {"project_definition": action},
            "row_counts": {"project_definition_versions": 1},
            "warnings": [],
            "errors": [],
            "allow_nonempty": False,
            "status": "COMMITTED",
            "actor_identifier": actor_identifier,
            "committed_at": datetime.now(timezone.utc),
        },
    )


@transaction.atomic
def commit_foundation_package_2_1(
    preview: Foundation21Preview,
    *,
    project: Any,
    principal: object,
    actor_identifier: str,
    workspace: Any | None = None,
    initial_workspace: Mapping[str, Any] | None = None,
    locale: str = "ru",
    allow_nonempty: bool = False,
    inject_failure_at: str | None = None,
) -> Foundation21CommitResult:
    """Commit exactly one 2.1 plan through existing canonical authorities."""

    if not isinstance(preview, Foundation21Preview) or not preview.valid:
        raise FoundationPackageValidationError("Commit requires a valid 2.1 preview.")
    if not actor_identifier.strip():
        raise FoundationPackageValidationError("actor_identifier is required.")
    from domain.policies import (
        StudioCapability,
        StudioPrincipal,
        require_studio_capability,
    )

    require_studio_capability(principal, StudioCapability.FOUNDATION_IMPORT)
    if (
        not isinstance(principal, StudioPrincipal)
        or actor_identifier.strip() != principal.actor_identifier
    ):
        raise FoundationPackageValidationError(
            "actor_identifier must equal the trusted Foundation import principal."
        )
    locked_project = _locked_project_for_preview_2_1(preview, project)
    package = validate_foundation_package_2_1(preview.payload_copy())
    if package["manifest"]["payload_sha256"] != preview.checksum:
        raise FoundationPackageConflictError(
            "Foundation 2.1 preview payload changed after validation."
        )
    _require_exact_project_2_1(package, locked_project)

    if package["package_scope"] == "WORKSPACE":
        if workspace is None or preview._workspace_preview is None:
            raise FoundationPackageValidationError(
                "A WORKSPACE commit requires its explicit target and nested preview."
            )
        receipt = commit_foundation_package(
            preview._workspace_preview,
            workspace=workspace,
            allow_nonempty=allow_nonempty,
            actor_identifier=actor_identifier,
        )
        return Foundation21CommitResult(
            package_scope="WORKSPACE",
            action=preview.intended_action,
            definition_id=preview.selected_definition_id,
            workspace_id=str(workspace.pk),
            receipt_id=receipt.id,
            checksum=preview.checksum,
        )

    action, existing = _definition_plan_2_1(package, project=locked_project)
    if action != preview.intended_action:
        raise FoundationPackageConflictError(
            "Project-definition import plan changed after preview."
        )
    source = package["project_definition"]
    if existing is not None:
        definition = existing
        initial_workspace_id = None
    else:
        from domain.services.project_definitions import create_project_definition_draft

        supersedes = None
        if source["supersedes_code"]:
            supersedes = _model("ProjectDefinitionVersion").objects.filter(
                project=locked_project,
                code=source["supersedes_code"],
            ).first()
            if supersedes is None:
                raise FoundationPackageConflictError(
                    "The package supersedes_code is not an exact persisted definition."
                )
        definition = create_project_definition_draft(
            project=locked_project,
            definition_id=UUID(source["id"]),
            code=source["code"],
            version=source["version"],
            manifest=source["manifest"],
            metadata=source.get("metadata", {}),
            semantic_version=source["semantic_version"],
            construct_version=source["construct_version"],
            supersedes=supersedes,
            principal=principal,
        )
        initial_workspace_id = None
        if action == "BOOTSTRAP_PUBLISHED":
            if initial_workspace is None:
                raise FoundationPackageValidationError(
                    "A published definition import requires an explicit initial workspace specification."
                )
            from domain.policies import bootstrap_initial_project_definition

            bootstrap = bootstrap_initial_project_definition(
                definition=definition,
                principal=principal,
                actor_identifier=actor_identifier,
                workspace_spec=initial_workspace,
                locale=locale,
                inject_failure_at=inject_failure_at,
            )
            definition = bootstrap.definition
            initial_workspace_id = str(bootstrap.workspace.pk)
    run = _create_definition_import_receipt_2_1(
        package=package,
        project=locked_project,
        definition=definition,
        action=action,
        actor_identifier=actor_identifier.strip(),
    )
    if inject_failure_at == "after_definition_import_receipt":
        raise RuntimeError(
            "Injected Foundation 2.1 failure at after_definition_import_receipt."
        )
    from domain.policies import record_definition_audit

    record_definition_audit(
        definition=definition,
        action="IMPORT",
        actor_identifier=actor_identifier.strip(),
        entity_type="IMPORT_RUN",
        entity_id=run.pk,
        after={
            "package_id": package["package_id"],
            "checksum": preview.checksum,
            "action": action,
        },
    )
    if inject_failure_at == "after_definition_import_audit":
        raise RuntimeError(
            "Injected Foundation 2.1 failure at after_definition_import_audit."
        )
    return Foundation21CommitResult(
        package_scope="PROJECT_DEFINITION",
        action=action,
        definition_id=str(definition.pk),
        workspace_id=initial_workspace_id,
        receipt_id=str(run.pk),
        checksum=preview.checksum,
    )


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _export_base(obj: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": str(obj.pk),
        "code": obj.code,
        "version": obj.version,
        "metadata": (
            copy.deepcopy(obj.metadata)
            if "metadata" in _field_names(obj.__class__)
            else {}
        ),
    }
    return item


def _export_definition(obj: Any) -> dict[str, Any]:
    return {
        **_export_base(obj),
        "is_current": obj.is_current,
        "publication_status": obj.publication_status,
        "manifest": obj.manifest,
        "manifest_hash": obj.manifest_hash,
        "published_at": _iso_datetime(obj.published_at),
        "schema_version": obj.schema_version,
        "semantic_version": obj.semantic_version,
        "construct_version": obj.construct_version,
        "validated_at": _iso_datetime(obj.validated_at),
        "validated_by": obj.validated_by,
        "validation_result": copy.deepcopy(obj.validation_result),
        "published_by": obj.published_by,
        "supersedes_code": obj.supersedes.code if obj.supersedes_id else None,
    }


def _query_for_export(section: str, workspace: Any) -> list[Any]:
    spec = next(spec for spec in _materialization_specs() if spec["section"] == section)
    model = spec["model"]
    if section == "parameter_definitions":
        query = model.objects.filter(project=workspace.project)
    elif section == "help_topics":
        query = model.objects.filter(ui_bindings__workspace=workspace).distinct()
    elif section == "parameter_values":
        query = model.objects.filter(
            workspace=workspace,
            actor_element_assessment__isnull=False,
        )
    else:
        query = model.objects.filter(workspace=workspace)
    return list(query.order_by("code", "id"))


def _export_item(section: str, obj: Any) -> dict[str, Any]:
    item = _export_base(obj)
    if section == "time_slices":
        item.update(name=obj.name, cutoff_date=_iso_date(obj.cutoff_date), order=obj.order)
    elif section == "actors":
        item.update(parent_code=obj.parent.code if obj.parent_id else None, actor_type=obj.actor_type, label=obj.label, description=obj.description, order=obj.order)
    elif section == "actor_relations":
        item.update(source_actor_code=obj.source_actor.code, target_actor_code=obj.target_actor.code, relation_type=obj.relation_type, description=obj.description)
    elif section == "analytical_elements":
        item.update(parent_code=obj.parent.code if obj.parent_id else None, element_type=obj.element_type, label=obj.label, reference_statement=obj.reference_statement, description=obj.description, order=obj.order)
    elif section == "actor_element_roles":
        item.update(actor_code=obj.actor.code, element_code=obj.element.code, role=obj.role, note=obj.note)
    elif section == "expert_profiles":
        item.update(kind=obj.kind, display_name=obj.display_name, identity_key=obj.identity_key, provider=obj.provider, model_name=obj.model_name)
    elif section == "assessment_sets":
        item.update(kind=obj.kind, name=obj.name, description=obj.description, independent=True)
    elif section == "experiments":
        item.update(expert_profile_code=obj.expert_profile.code, assessment_set_code=obj.assessment_set.code, experiment_type=obj.experiment_type, name=obj.name, status=obj.status, color=obj.color, order=obj.order, method_version=obj.method_version, frozen_at=_iso_datetime(obj.frozen_at))
    elif section == "actor_element_assessments":
        item.update(assessment_set_code=obj.assessment_set.code, experiment_code=obj.experiment.code, actor_code=obj.actor.code, element_code=obj.element.code, time_slice_code=obj.time_slice.code, supersedes_code=obj.supersedes.code if obj.supersedes_id else None, reference_statement=obj.reference_statement, reference_statement_incomplete=obj.reference_statement_incomplete, status=obj.status, confidence_level=obj.confidence_level, knowledge_cutoff=_iso_date(obj.knowledge_cutoff), method_version=obj.method_version, provenance=obj.provenance)
    elif section == "parameter_definitions":
        item.update(name=obj.name, description=obj.description, target_type=obj.target_type, value_type=obj.value_type, scale_min=str(obj.scale_min) if obj.scale_min is not None else None, scale_max=str(obj.scale_max) if obj.scale_max is not None else None, scale_metadata=obj.scale_metadata)
    elif section == "parameter_values":
        item.update(assessment_code=obj.actor_element_assessment.code, assessment_set_code=obj.assessment_set.code, parameter_definition_code=obj.parameter_definition.code, supersedes_code=obj.supersedes.code if obj.supersedes_id else None, status=obj.status, temporal_status=obj.temporal_status, value=obj.value, note=obj.note, confidence=str(obj.confidence) if obj.confidence is not None else None, range_min=obj.range_min, range_max=obj.range_max, rationale=obj.rationale)
    elif section == "sources":
        item.update(name=obj.name, publisher=obj.publisher, independence_group=obj.independence_group, independence_status=obj.independence_status, homepage_url=obj.homepage_url)
    elif section == "documents":
        item.update(source_code=obj.source.code, title=obj.title, canonical_url=obj.canonical_url, published_on=_iso_date(obj.publication_date), accessed_on=_iso_date(obj.accessed_on))
    elif section == "document_versions":
        item.update(document_code=obj.document.code, supersedes_code=obj.supersedes.code if obj.supersedes_id else None, status=obj.status, capture_url=obj.capture_url, captured_at=_iso_datetime(obj.captured_at), checksum=obj.content_sha256 or None, media_type=obj.media_type)
    elif section == "document_contents":
        if obj.original_bytes is not None:
            encoding = "BASE64"
            content = base64.b64encode(bytes(obj.original_bytes)).decode("ascii")
        else:
            encoding = "UTF8"
            content = obj.normalized_text
        item.update(document_version_code=obj.document_version.code, encoding=encoding, normalization_version=obj.normalization_version, content=content, checksum=obj.content_sha256)
    elif section == "text_fragments":
        item.update(document_version_code=obj.document_version.code, anchor_status=obj.anchor_status, start_offset=obj.start_offset, end_offset=obj.end_offset, selector=obj.selector, page=obj.page, section=obj.section, exact_text=obj.exact_text, exact_text_sha256=obj.text_sha256 or None)
    elif section == "facts":
        item.update(experiment_code=obj.experiment.code if obj.experiment_id else None, fact_type=obj.fact_type, statement=obj.statement, origin=obj.origin, directness=obj.directness, visibility=obj.visibility, status=obj.status, confidence=str(obj.confidence) if obj.confidence is not None else None, temporal_status=obj.temporal_status, coder_identifier=obj.coder_identifier)
    elif section == "fact_evidence_links":
        item.update(fact_code=obj.fact.code, fragment_code=obj.fragment.code, relation=obj.relation, temporal_status=obj.temporal_status, learned_on=_iso_date(obj.learned_on), rationale=obj.rationale)
    elif section == "assessment_fact_links":
        item.update(assessment_code=obj.assessment.code, fact_code=obj.fact.code, role=obj.role, temporal_status=obj.temporal_status, learned_on=_iso_date(obj.learned_on), rationale=obj.rationale)
    elif section == "parameter_value_fact_links":
        item.update(parameter_value_code=obj.parameter_value.code, fact_code=obj.fact.code, role=obj.role, temporal_status=obj.temporal_status, learned_on=_iso_date(obj.learned_on), rationale=obj.rationale)
    elif section == "gaps":
        item.update(type=obj.gap_type, document_version_code=obj.entity_code if obj.entity_type == "DocumentVersion" else None, status="RESOLVED" if obj.resolved else "OPEN", required_behavior=obj.required_behavior, resolution=obj.resolution)
    elif section == "help_topics":
        item.update(stable_key=obj.stable_key, title=obj.title, application_scope=obj.application_scope, construct_version=obj.construct_version, term_version=obj.term_version, locale=obj.locale, sanitized_html=obj.sanitized_html, content_sha256=obj.content_sha256, publication_status=obj.publication_status, published_at=_iso_datetime(obj.published_at))
    elif section == "ui_help_bindings":
        item.update(ui_key=obj.ui_key, locale=obj.locale, topic_version=obj.help_topic.version, help_topic_code=obj.help_topic.code)
    elif section == "power_profiles":
        item.update(assessment_code=obj.assessment.code, method_version=obj.method_version, note=obj.note)
    elif section == "power_components":
        item.update(profile_code=obj.profile.code, dimension=obj.dimension, status=obj.status, value=obj.value, confidence=str(obj.confidence) if obj.confidence is not None else None, rationale=obj.rationale, provenance=obj.provenance)
    elif section == "power_component_fact_links":
        item.update(component_code=obj.component.code, fact_code=obj.fact.code, role=obj.role)
    elif section == "chat_conversations":
        item.update(channel_type=obj.channel_type, owner_identifier=obj.owner_identifier, participants=copy.deepcopy(obj.participants), title=obj.title, provider=obj.provider, model_name=obj.model_name, archived_at=_iso_datetime(obj.archived_at))
    elif section == "chat_messages":
        item.update(conversation_code=obj.conversation.code, sequence=obj.sequence, role=obj.role, content=obj.content, provider=obj.provider, model_name=obj.model_name, provider_request_id=obj.provider_request_id, status=obj.status, error=obj.error)
    elif section == "chat_citations":
        item.update(message_code=obj.message.code, fact_code=obj.fact.code if obj.fact_id else None, fragment_code=obj.fragment.code if obj.fragment_id else None, document_version_code=obj.document_version.code if obj.document_version_id else None, quote_start=obj.quote_start, quote_end=obj.quote_end, quote_text=obj.quote_text, label=obj.label)
    elif section == "terminology_entries":
        item.update(canonical_ru_name=obj.canonical_ru_name, canonical_ru_acronym=obj.canonical_ru_acronym, exact_en_term=obj.exact_en_term, exact_en_acronym=obj.exact_en_acronym, source_framework=obj.source_framework, source_citation=obj.source_citation, construct_version=obj.construct_version, locale=obj.locale, display_metadata=obj.display_metadata)
    elif section == "legacy_term_mappings":
        item.update(terminology_entry_code=obj.terminology_entry.code if obj.terminology_entry_id else None, legacy_code=obj.legacy_code, legacy_label=obj.legacy_label, source_version=obj.source_version, mapping_status=obj.mapping_status, notes=obj.notes)
    elif section == "compatibility_receipts":
        # The v2 compatibility receipt schema deliberately has no metadata lane:
        # it is an explicit migration/data-gap record, not a generic entity DTO.
        item.pop("metadata", None)
        item.update(legacy_model=obj.legacy_model, legacy_id=str(obj.legacy_id), legacy_code=obj.legacy_code, canonical_model=obj.canonical_model, canonical_id=str(obj.canonical_id) if obj.canonical_id else None, canonical_code=obj.canonical_code, status=obj.status, reason=obj.reason, migration_version=obj.migration_version)
    else:
        raise AssertionError(f"Unmapped Foundation export section {section}.")
    return item
