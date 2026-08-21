"""Deterministic, checksummed JSON project package import and export."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from domain.enums import (
    AssessmentKind,
    AuditAction,
    AuditActorType,
    EvidenceRelation,
    ParameterValueType,
    ScenarioStatus,
    StrategyStatus,
    TargetType,
    ValueStatus,
)
from domain.models import (
    AssessmentSet,
    AuditEvent,
    CalculationStrategyDefinition,
    EvidenceLink,
    EvidenceSource,
    GroupTensionRelation,
    ParameterDefinition,
    ParameterValue,
    ParticipantGroup,
    Project,
    ProjectLock,
    ProjectSchemaVersion,
    Scenario,
    ScenarioOverride,
    TensionPoint,
    TimeSlice,
)


PACKAGE_FORMAT = "conflict-analysis-project"
PACKAGE_VERSION = "1.0.0"
HASH_ALGORITHM = "sha256"
SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "project-package-1.0.0.schema.json"
)

with SCHEMA_PATH.open(encoding="utf-8") as _schema_file:
    PACKAGE_JSON_SCHEMA = json.load(_schema_file)
Draft202012Validator.check_schema(PACKAGE_JSON_SCHEMA)
_PACKAGE_VALIDATOR = Draft202012Validator(
    PACKAGE_JSON_SCHEMA,
    format_checker=FormatChecker(),
)

_LIST_SECTIONS = (
    "schema_versions",
    "time_slices",
    "tension_points",
    "participant_groups",
    "group_tension_relations",
    "assessment_sets",
    "parameter_definitions",
    "parameter_values",
    "evidence_sources",
    "evidence_links",
    "calculation_strategies",
    "scenarios",
    "scenario_overrides",
    "audit_events",
)

_BASE_KEYS = {"id", "code", "version"}
_SECTION_KEYS = {
    "schema_versions": _BASE_KEYS
    | {"is_current", "schema_manifest", "schema_manifest_hash"},
    "time_slices": _BASE_KEYS | {"name", "cutoff_date", "order"},
    "tension_points": _BASE_KEYS
    | {"name", "short_name", "definition", "order"},
    "participant_groups": _BASE_KEYS
    | {"name", "short_name", "definition", "order"},
    "group_tension_relations": _BASE_KEYS
    | {"participant_group_id", "tension_point_id"},
    "assessment_sets": _BASE_KEYS | {"kind", "name", "description"},
    "parameter_definitions": _BASE_KEYS
    | {
        "name",
        "description",
        "target_type",
        "value_type",
        "scale_min",
        "scale_max",
        "scale_metadata",
    },
    "parameter_values": _BASE_KEYS
    | {
        "time_slice_id",
        "assessment_set_id",
        "parameter_definition_id",
        "target_type",
        "target_id",
        "status",
        "value",
        "note",
        "confidence",
        "range_min",
        "range_max",
        "rationale",
    },
    "evidence_sources": _BASE_KEYS
    | {
        "title",
        "url",
        "additional_urls",
        "published_on",
        "accessed_on",
        "metadata",
    },
    "evidence_links": _BASE_KEYS
    | {"parameter_value_id", "source_id", "relation", "rationale"},
    "calculation_strategies": _BASE_KEYS
    | {
        "name",
        "description",
        "status",
        "input_schema",
        "output_schema",
        "metadata",
    },
    "scenarios": _BASE_KEYS
    | {
        "time_slice_id",
        "assessment_set_id",
        "base_assessment_set_id",
        "name",
        "description",
        "status",
    },
    "scenario_overrides": _BASE_KEYS
    | {
        "scenario_id",
        "parameter_definition_id",
        "target_type",
        "target_id",
        "status",
        "value",
        "note",
        "confidence",
        "range_min",
        "range_max",
        "rationale",
    },
    "audit_events": _BASE_KEYS
    | {
        "assessment_set_id",
        "parameter_value_id",
        "action",
        "actor_type",
        "actor_identifier",
        "entity_type",
        "entity_id",
        "before",
        "after",
        "occurred_at",
    },
}

_UNAVAILABLE_STATUSES = {
    ValueStatus.UNKNOWN,
    ValueStatus.NOT_APPLICABLE,
    ValueStatus.INSUFFICIENT_DATA,
    ValueStatus.OPEN_METHOD,
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProjectPackageError(ValueError):
    """Base exception for package validation and import failures."""


class ProjectPackageValidationError(ProjectPackageError):
    """The package is malformed, inconsistent, or fails its checksum."""


class ProjectPackageConflictError(ProjectPackageError):
    """A valid package conflicts with an existing project identity."""


def canonical_json(value: Any) -> str:
    """Serialize JSON with stable key ordering and no insignificant whitespace."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _base(obj: Any) -> dict[str, Any]:
    return {"id": str(obj.id), "code": obj.code, "version": obj.version}


def _date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _ordered(queryset: Any) -> Iterable[Any]:
    return queryset.order_by("code", "id")


def _payload_for_project(project: Project) -> dict[str, Any]:
    lock = ProjectLock.objects.filter(project=project).first()

    payload: dict[str, Any] = {
        "format": PACKAGE_FORMAT,
        "format_version": PACKAGE_VERSION,
        "project": {
            **_base(project),
            "name": project.name,
            "description": project.description,
            "metadata": project.metadata,
        },
        "project_lock": None,
        "schema_versions": [],
        "time_slices": [],
        "tension_points": [],
        "participant_groups": [],
        "group_tension_relations": [],
        "assessment_sets": [],
        "parameter_definitions": [],
        "parameter_values": [],
        "evidence_sources": [],
        "evidence_links": [],
        "calculation_strategies": [],
        "scenarios": [],
        "scenario_overrides": [],
        "audit_events": [],
    }

    if lock is not None:
        payload["project_lock"] = {
            **_base(lock),
            "is_structure_locked": lock.is_structure_locked,
            "ordinary_user_can_edit_structure": lock.ordinary_user_can_edit_structure,
            "studio_can_edit_structure": lock.studio_can_edit_structure,
            "reason": lock.reason,
        }

    for obj in _ordered(ProjectSchemaVersion.objects.filter(project=project)):
        payload["schema_versions"].append(
            {
                **_base(obj),
                "is_current": obj.is_current,
                "schema_manifest": obj.manifest,
                "schema_manifest_hash": obj.manifest_hash,
            }
        )

    for obj in _ordered(TimeSlice.objects.filter(project=project)):
        payload["time_slices"].append(
            {
                **_base(obj),
                "name": obj.name,
                "cutoff_date": _date(obj.cutoff_date),
                "order": obj.order,
            }
        )

    for section, model in (
        ("tension_points", TensionPoint),
        ("participant_groups", ParticipantGroup),
    ):
        for obj in _ordered(model.objects.filter(project=project)):
            payload[section].append(
                {
                    **_base(obj),
                    "name": obj.name,
                    "short_name": obj.short_name,
                    "definition": obj.definition,
                    "order": obj.order,
                }
            )

    for obj in _ordered(GroupTensionRelation.objects.filter(project=project)):
        payload["group_tension_relations"].append(
            {
                **_base(obj),
                "participant_group_id": str(obj.participant_group_id),
                "tension_point_id": str(obj.tension_point_id),
            }
        )

    for obj in _ordered(AssessmentSet.objects.filter(project=project)):
        payload["assessment_sets"].append(
            {
                **_base(obj),
                "kind": obj.kind,
                "name": obj.name,
                "description": obj.description,
            }
        )

    for obj in _ordered(ParameterDefinition.objects.filter(project=project)):
        payload["parameter_definitions"].append(
            {
                **_base(obj),
                "name": obj.name,
                "description": obj.description,
                "target_type": obj.target_type,
                "value_type": obj.value_type,
                "scale_min": _decimal(obj.scale_min),
                "scale_max": _decimal(obj.scale_max),
                "scale_metadata": obj.scale_metadata,
            }
        )

    for obj in _ordered(ParameterValue.objects.filter(project=project)):
        payload["parameter_values"].append(
            {
                **_base(obj),
                "time_slice_id": str(obj.time_slice_id),
                "assessment_set_id": str(obj.assessment_set_id),
                "parameter_definition_id": str(obj.parameter_definition_id),
                "target_type": obj.target_type,
                "target_id": str(obj.target_id),
                "status": obj.status,
                "value": obj.value,
                "note": obj.note,
                "confidence": _decimal(obj.confidence),
                "range_min": obj.range_min,
                "range_max": obj.range_max,
                "rationale": obj.rationale,
            }
        )

    for obj in _ordered(EvidenceSource.objects.filter(project=project)):
        payload["evidence_sources"].append(
            {
                **_base(obj),
                "title": obj.title,
                "url": obj.url,
                "additional_urls": obj.additional_urls,
                "published_on": _date(obj.published_on),
                "accessed_on": _date(obj.accessed_on),
                "metadata": obj.metadata,
            }
        )

    for obj in _ordered(EvidenceLink.objects.filter(project=project)):
        payload["evidence_links"].append(
            {
                **_base(obj),
                "parameter_value_id": str(obj.parameter_value_id),
                "source_id": str(obj.source_id),
                "relation": obj.relation,
                "rationale": obj.rationale,
            }
        )

    for obj in _ordered(
        CalculationStrategyDefinition.objects.filter(project=project)
    ):
        payload["calculation_strategies"].append(
            {
                **_base(obj),
                "name": obj.name,
                "description": obj.description,
                "status": obj.status,
                "input_schema": obj.input_schema,
                "output_schema": obj.output_schema,
                "metadata": obj.metadata,
            }
        )

    for obj in _ordered(Scenario.objects.filter(project=project)):
        payload["scenarios"].append(
            {
                **_base(obj),
                "time_slice_id": str(obj.time_slice_id),
                "assessment_set_id": str(obj.assessment_set_id),
                "base_assessment_set_id": str(obj.base_assessment_set_id),
                "name": obj.name,
                "description": obj.description,
                "status": obj.status,
            }
        )

    for obj in _ordered(ScenarioOverride.objects.filter(project=project)):
        payload["scenario_overrides"].append(
            {
                **_base(obj),
                "scenario_id": str(obj.scenario_id),
                "parameter_definition_id": str(obj.parameter_definition_id),
                "target_type": obj.target_type,
                "target_id": str(obj.target_id),
                "status": obj.status,
                "value": obj.value,
                "note": obj.note,
                "confidence": _decimal(obj.confidence),
                "range_min": obj.range_min,
                "range_max": obj.range_max,
                "rationale": obj.rationale,
            }
        )

    for obj in _ordered(AuditEvent.objects.filter(project=project)):
        payload["audit_events"].append(
            {
                **_base(obj),
                "assessment_set_id": (
                    str(obj.assessment_set_id) if obj.assessment_set_id else None
                ),
                "parameter_value_id": (
                    str(obj.parameter_value_id) if obj.parameter_value_id else None
                ),
                "action": obj.action,
                "actor_type": obj.actor_type,
                "actor_identifier": obj.actor_identifier,
                "entity_type": obj.entity_type,
                "entity_id": str(obj.entity_id),
                "before": obj.before,
                "after": obj.after,
                "occurred_at": _datetime(obj.occurred_at),
            }
        )
    return payload


def _build_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical_payload = canonical_json(payload).encode("utf-8")
    counts = {section: len(payload[section]) for section in _LIST_SECTIONS}
    counts["project"] = 1
    counts["project_lock"] = 0 if payload["project_lock"] is None else 1
    ptn_versions = sorted({item["version"] for item in payload["tension_points"]})
    gu_versions = sorted(
        {item["version"] for item in payload["participant_groups"]}
    )
    return {
        "hash_algorithm": HASH_ALGORITHM,
        "payload_sha256": hashlib.sha256(canonical_payload).hexdigest(),
        "entity_counts": counts,
        "ptn_version": ptn_versions[0] if len(ptn_versions) == 1 else None,
        "gu_version": gu_versions[0] if len(gu_versions) == 1 else None,
    }


def seal_project_package(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-copied payload with a freshly calculated stable manifest."""

    sealed = copy.deepcopy(dict(payload))
    sealed.pop("manifest", None)
    sealed["manifest"] = _build_manifest(sealed)
    return sealed


def export_project_package(project: Project) -> dict[str, Any]:
    """Build a deterministic package that the matching importer accepts."""

    package = seal_project_package(_payload_for_project(project))
    # Database rows can be inserted outside the domain services.  Refuse to
    # emit a checksummed but non-importable artifact (for example, a present
    # assessment with no evidence) instead of discovering the problem later.
    _validate_and_normalize_package(package)
    return package


def export_project_json(project: Project) -> str:
    """Return canonical UTF-8 JSON with one trailing newline."""

    return canonical_json(export_project_package(project)) + "\n"


def _reject(message: str) -> None:
    raise ProjectPackageValidationError(message)


def _validate_json_schema(raw_package: Any) -> None:
    errors = sorted(
        _PACKAGE_VALIDATOR.iter_errors(raw_package),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if not errors:
        return
    error = errors[0]
    path = ".".join(str(part) for part in error.absolute_path) or "package"
    _reject(f"JSON Schema validation failed at {path}: {error.message}")


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    actual = set(value)
    if actual != expected:
        _reject(
            f"{path} keys differ from package schema: "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}."
        )


def _uuid(value: Any, path: str) -> str:
    if not isinstance(value, str):
        _reject(f"{path} must be a UUID string.")
    try:
        return str(UUID(value))
    except (ValueError, AttributeError, TypeError):
        _reject(f"{path} is not a valid UUID.")
    raise AssertionError("unreachable")


def _choice(value: Any, choices: Any, path: str) -> None:
    if value not in choices.values:
        _reject(f"{path} has unsupported value {value!r}.")


def _date_value(value: Any, path: str, *, nullable: bool = False) -> date | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _reject(f"{path} must be an ISO date string.")
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        _reject(f"{path} is not a valid ISO date.")
    raise AssertionError("unreachable")


def _datetime_value(value: Any, path: str) -> datetime:
    if not isinstance(value, str):
        _reject(f"{path} must be an ISO datetime string.")
    parsed = parse_datetime(value)
    if parsed is None:
        _reject(f"{path} is not a valid ISO datetime.")
    return parsed


def _decimal_value(value: Any, path: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str):
        _reject(f"{path} must be a decimal string or null.")
    try:
        return Decimal(value)
    except InvalidOperation:
        _reject(f"{path} is not a valid decimal string.")
    raise AssertionError("unreachable")


def _json_decimal(value: Any, path: str) -> Decimal:
    if isinstance(value, bool):
        _reject(f"{path} must be numeric.")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        _reject(f"{path} must be a finite numeric value.")
    if not parsed.is_finite():
        _reject(f"{path} must be a finite numeric value.")
    return parsed


def _validate_assessment_metadata(
    item: Mapping[str, Any],
    definition: Mapping[str, Any],
    path: str,
) -> None:
    status = item["status"]
    if status in _UNAVAILABLE_STATUSES:
        if item["confidence"] is not None:
            _reject(f"{path}.confidence must be null for status {status}.")
        if item["range_min"] is not None or item["range_max"] is not None:
            _reject(f"{path} range must be null for status {status}.")
        return

    confidence = _decimal_value(item["confidence"], f"{path}.confidence")
    if confidence is None or not Decimal("0") <= confidence <= Decimal("1"):
        _reject(f"{path}.confidence must be between 0 and 1.")
    if not item["rationale"].strip():
        _reject(f"{path}.rationale is required for a present assessment.")
    if item["range_min"] is None or item["range_max"] is None:
        _reject(f"{path} requires both range_min and range_max.")

    if definition["value_type"] not in {
        ParameterValueType.DECIMAL,
        ParameterValueType.INTEGER,
    }:
        return
    minimum = _json_decimal(item["range_min"], f"{path}.range_min")
    maximum = _json_decimal(item["range_max"], f"{path}.range_max")
    actual = _json_decimal(item["value"], f"{path}.value")
    if minimum > maximum:
        _reject(f"{path}.range_max must be greater than or equal to range_min.")
    if not minimum <= actual <= maximum:
        _reject(f"{path}.value must fall inside its admissible range.")


def _validate_typed_value(
    item: Mapping[str, Any],
    definition: Mapping[str, Any],
    path: str,
) -> None:
    value = item["value"]
    if value is None:
        return
    value_type = definition["value_type"]
    numeric: Decimal | None = None
    if value_type == ParameterValueType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            _reject(f"{path}.value must be an integer.")
        numeric = Decimal(value)
    elif value_type == ParameterValueType.DECIMAL:
        numeric = _json_decimal(value, f"{path}.value")
    elif value_type == ParameterValueType.BOOLEAN:
        if not isinstance(value, bool):
            _reject(f"{path}.value must be a boolean.")
    elif value_type == ParameterValueType.TEXT and not isinstance(value, str):
        _reject(f"{path}.value must be text.")

    if numeric is None:
        return
    minimum = _decimal_value(definition["scale_min"], f"{path}.scale_min")
    maximum = _decimal_value(definition["scale_max"], f"{path}.scale_max")
    if minimum is not None and numeric < minimum:
        _reject(f"{path}.value is below the parameter scale minimum.")
    if maximum is not None and numeric > maximum:
        _reject(f"{path}.value is above the parameter scale maximum.")


def _require_reference(value: Any, valid_ids: set[str], path: str) -> str:
    normalized = _uuid(value, path)
    if normalized not in valid_ids:
        _reject(f"{path} references an entity outside the package.")
    return normalized


def _target_ids_by_type(package: Mapping[str, Any]) -> dict[str, set[str]]:
    return {
        TargetType.PROJECT: {str(UUID(package["project"]["id"]))},
        TargetType.TIME_SLICE: {item["id"] for item in package["time_slices"]},
        TargetType.TENSION_POINT: {
            item["id"] for item in package["tension_points"]
        },
        TargetType.PARTICIPANT_GROUP: {
            item["id"] for item in package["participant_groups"]
        },
        TargetType.GROUP_TENSION_RELATION: {
            item["id"] for item in package["group_tension_relations"]
        },
    }


def _validate_and_normalize_package(raw_package: Mapping[str, Any]) -> dict[str, Any]:
    _validate_json_schema(raw_package)
    if not isinstance(raw_package, Mapping):
        _reject("Package root must be a JSON object.")
    package = copy.deepcopy(dict(raw_package))
    expected_root = {
        "format",
        "format_version",
        "manifest",
        "project",
        "project_lock",
        *_LIST_SECTIONS,
    }
    _require_exact_keys(package, expected_root, "package")
    if package["format"] != PACKAGE_FORMAT:
        _reject(f"Unsupported package format {package['format']!r}.")
    if package["format_version"] != PACKAGE_VERSION:
        _reject(
            f"Incompatible package version {package['format_version']!r}; "
            f"expected {PACKAGE_VERSION!r}."
        )

    supplied_manifest = package.pop("manifest")
    if not isinstance(supplied_manifest, Mapping):
        _reject("manifest must be an object.")
    expected_manifest = _build_manifest(package)
    if dict(supplied_manifest) != expected_manifest:
        _reject("Package manifest or SHA-256 payload hash does not match its content.")
    if not _SHA256_RE.fullmatch(supplied_manifest["payload_sha256"]):
        _reject("manifest.payload_sha256 is not a lowercase SHA-256 digest.")
    package["manifest"] = dict(supplied_manifest)

    project = package["project"]
    if not isinstance(project, Mapping):
        _reject("project must be an object.")
    _require_exact_keys(
        project,
        _BASE_KEYS | {"name", "description", "metadata"},
        "project",
    )
    project["id"] = _uuid(project["id"], "project.id")
    if not isinstance(project["code"], str) or not project["code"]:
        _reject("project.code must be a non-empty string.")
    if not isinstance(project["metadata"], dict):
        _reject("project.metadata must be an object.")

    lock = package["project_lock"]
    if lock is not None:
        if not isinstance(lock, Mapping):
            _reject("project_lock must be an object or null.")
        lock_keys = _BASE_KEYS | {
            "is_structure_locked",
            "ordinary_user_can_edit_structure",
            "studio_can_edit_structure",
            "reason",
        }
        _require_exact_keys(lock, lock_keys, "project_lock")
        lock["id"] = _uuid(lock["id"], "project_lock.id")
        if lock["is_structure_locked"] and lock["ordinary_user_can_edit_structure"]:
            _reject("A locked project cannot permit ordinary structure edits.")

    for section in _LIST_SECTIONS:
        items = package[section]
        if not isinstance(items, list):
            _reject(f"{section} must be an array.")
        ids: set[str] = set()
        codes: set[str] = set()
        for index, item in enumerate(items):
            path = f"{section}[{index}]"
            if not isinstance(item, Mapping):
                _reject(f"{path} must be an object.")
            _require_exact_keys(item, _SECTION_KEYS[section], path)
            item["id"] = _uuid(item["id"], f"{path}.id")
            if item["id"] in ids:
                _reject(f"{section} contains duplicate id {item['id']!r}.")
            ids.add(item["id"])
            if not isinstance(item["code"], str) or not item["code"]:
                _reject(f"{path}.code must be a non-empty string.")
            if item["code"] in codes:
                _reject(f"{section} contains duplicate code {item['code']!r}.")
            codes.add(item["code"])

    current_versions = sum(item["is_current"] for item in package["schema_versions"])
    if current_versions > 1:
        _reject("schema_versions contains more than one current version.")

    for index, item in enumerate(package["time_slices"]):
        item["cutoff_date"] = _date_value(
            item["cutoff_date"], f"time_slices[{index}].cutoff_date"
        ).isoformat()

    for section in ("tension_points", "participant_groups"):
        orders: set[int] = set()
        for index, item in enumerate(package[section]):
            if item["order"] in orders:
                _reject(f"{section}[{index}].order duplicates another row.")
            orders.add(item["order"])

    group_ids = {item["id"] for item in package["participant_groups"]}
    tension_ids = {item["id"] for item in package["tension_points"]}
    relation_pairs: set[tuple[str, str]] = set()
    for index, item in enumerate(package["group_tension_relations"]):
        group_id = _require_reference(
            item["participant_group_id"],
            group_ids,
            f"group_tension_relations[{index}].participant_group_id",
        )
        tension_id = _require_reference(
            item["tension_point_id"],
            tension_ids,
            f"group_tension_relations[{index}].tension_point_id",
        )
        item["participant_group_id"] = group_id
        item["tension_point_id"] = tension_id
        pair = (group_id, tension_id)
        if pair in relation_pairs:
            _reject("group_tension_relations contains a duplicate GU–PTN pair.")
        relation_pairs.add(pair)

    assessment_ids = {item["id"] for item in package["assessment_sets"]}
    assessment_kinds: dict[str, str] = {}
    for index, item in enumerate(package["assessment_sets"]):
        _choice(item["kind"], AssessmentKind, f"assessment_sets[{index}].kind")
        assessment_kinds[item["id"]] = item["kind"]

    definitions: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(package["parameter_definitions"]):
        _choice(
            item["target_type"],
            TargetType,
            f"parameter_definitions[{index}].target_type",
        )
        _choice(
            item["value_type"],
            ParameterValueType,
            f"parameter_definitions[{index}].value_type",
        )
        scale_min = _decimal_value(
            item["scale_min"], f"parameter_definitions[{index}].scale_min"
        )
        scale_max = _decimal_value(
            item["scale_max"], f"parameter_definitions[{index}].scale_max"
        )
        if scale_min is not None and scale_max is not None and scale_min > scale_max:
            _reject(f"parameter_definitions[{index}] has a reversed scale.")
        if item["value_type"] not in {
            ParameterValueType.DECIMAL,
            ParameterValueType.INTEGER,
        } and (scale_min is not None or scale_max is not None):
            _reject(
                f"parameter_definitions[{index}] defines a scale for a nonnumeric type."
            )
        definitions[item["id"]] = item

    time_ids = {item["id"] for item in package["time_slices"]}
    target_ids = _target_ids_by_type(package)
    value_ids = {item["id"] for item in package["parameter_values"]}
    value_keys: set[tuple[str, ...]] = set()
    for index, item in enumerate(package["parameter_values"]):
        path = f"parameter_values[{index}]"
        item["time_slice_id"] = _require_reference(
            item["time_slice_id"], time_ids, f"{path}.time_slice_id"
        )
        item["assessment_set_id"] = _require_reference(
            item["assessment_set_id"], assessment_ids, f"{path}.assessment_set_id"
        )
        definition_id = _require_reference(
            item["parameter_definition_id"],
            set(definitions),
            f"{path}.parameter_definition_id",
        )
        item["parameter_definition_id"] = definition_id
        _choice(item["target_type"], TargetType, f"{path}.target_type")
        if item["target_type"] != definitions[definition_id]["target_type"]:
            _reject(f"{path}.target_type differs from its parameter definition.")
        item["target_id"] = _require_reference(
            item["target_id"], target_ids[item["target_type"]], f"{path}.target_id"
        )
        _choice(item["status"], ValueStatus, f"{path}.status")
        if item["status"] in _UNAVAILABLE_STATUSES and item["value"] is not None:
            _reject(f"{path}.value must be null for status {item['status']}.")
        if item["status"] not in _UNAVAILABLE_STATUSES and item["value"] is None:
            _reject(f"{path}.value is required for status {item['status']}.")
        _validate_typed_value(item, definitions[definition_id], path)
        _validate_assessment_metadata(item, definitions[definition_id], path)
        unique_key = (
            item["time_slice_id"],
            item["assessment_set_id"],
            definition_id,
            item["target_type"],
            item["target_id"],
        )
        if unique_key in value_keys:
            _reject(f"{path} duplicates another assessment value identity.")
        value_keys.add(unique_key)

    source_ids = {item["id"] for item in package["evidence_sources"]}
    for index, item in enumerate(package["evidence_sources"]):
        path = f"evidence_sources[{index}]"
        if not isinstance(item["additional_urls"], list):
            _reject(f"{path}.additional_urls must be an array.")
        if not isinstance(item["metadata"], dict):
            _reject(f"{path}.metadata must be an object.")
        if item["published_on"] is not None:
            published_on = _date_value(
                item["published_on"], f"{path}.published_on", nullable=True
            )
        else:
            published_on = None
        if item["accessed_on"] is not None:
            accessed_on = _date_value(
                item["accessed_on"], f"{path}.accessed_on", nullable=True
            )
        else:
            accessed_on = None
        if published_on and accessed_on and accessed_on < published_on:
            _reject(f"{path}.accessed_on precedes published_on.")

    link_pairs: set[tuple[str, str]] = set()
    linked_value_ids: set[str] = set()
    for index, item in enumerate(package["evidence_links"]):
        path = f"evidence_links[{index}]"
        item["parameter_value_id"] = _require_reference(
            item["parameter_value_id"], value_ids, f"{path}.parameter_value_id"
        )
        item["source_id"] = _require_reference(
            item["source_id"], source_ids, f"{path}.source_id"
        )
        _choice(item["relation"], EvidenceRelation, f"{path}.relation")
        pair = (item["parameter_value_id"], item["source_id"])
        if pair in link_pairs:
            _reject(f"{path} duplicates another evidence/value link.")
        link_pairs.add(pair)
        linked_value_ids.add(item["parameter_value_id"])

    for index, item in enumerate(package["parameter_values"]):
        if item["status"] in {ValueStatus.PROVISIONAL, ValueStatus.CONFIRMED}:
            if item["id"] not in linked_value_ids:
                _reject(
                    f"parameter_values[{index}] is present but has no evidence link."
                )

    for index, item in enumerate(package["calculation_strategies"]):
        _choice(
            item["status"], StrategyStatus, f"calculation_strategies[{index}].status"
        )

    scenario_ids = {item["id"] for item in package["scenarios"]}
    scenario_assessment_ids: set[str] = set()
    for index, item in enumerate(package["scenarios"]):
        path = f"scenarios[{index}]"
        item["time_slice_id"] = _require_reference(
            item["time_slice_id"], time_ids, f"{path}.time_slice_id"
        )
        item["assessment_set_id"] = _require_reference(
            item["assessment_set_id"], assessment_ids, f"{path}.assessment_set_id"
        )
        item["base_assessment_set_id"] = _require_reference(
            item["base_assessment_set_id"],
            assessment_ids,
            f"{path}.base_assessment_set_id",
        )
        if assessment_kinds[item["assessment_set_id"]] != AssessmentKind.SCENARIO:
            _reject(f"{path}.assessment_set_id is not a SCENARIO assessment set.")
        if item["assessment_set_id"] == item["base_assessment_set_id"]:
            _reject(f"{path} uses the same scenario and base assessment set.")
        if item["assessment_set_id"] in scenario_assessment_ids:
            _reject(f"{path}.assessment_set_id is already used by another scenario.")
        scenario_assessment_ids.add(item["assessment_set_id"])
        _choice(item["status"], ScenarioStatus, f"{path}.status")

    override_keys: set[tuple[str, ...]] = set()
    for index, item in enumerate(package["scenario_overrides"]):
        path = f"scenario_overrides[{index}]"
        item["scenario_id"] = _require_reference(
            item["scenario_id"], scenario_ids, f"{path}.scenario_id"
        )
        definition_id = _require_reference(
            item["parameter_definition_id"],
            set(definitions),
            f"{path}.parameter_definition_id",
        )
        item["parameter_definition_id"] = definition_id
        _choice(item["target_type"], TargetType, f"{path}.target_type")
        if item["target_type"] != definitions[definition_id]["target_type"]:
            _reject(f"{path}.target_type differs from its parameter definition.")
        item["target_id"] = _require_reference(
            item["target_id"], target_ids[item["target_type"]], f"{path}.target_id"
        )
        _choice(item["status"], ValueStatus, f"{path}.status")
        if item["status"] in _UNAVAILABLE_STATUSES and item["value"] is not None:
            _reject(f"{path}.value must be null for status {item['status']}.")
        if item["status"] not in _UNAVAILABLE_STATUSES and item["value"] is None:
            _reject(f"{path}.value is required for status {item['status']}.")
        _validate_typed_value(item, definitions[definition_id], path)
        _validate_assessment_metadata(item, definitions[definition_id], path)
        key = (
            item["scenario_id"],
            definition_id,
            item["target_type"],
            item["target_id"],
        )
        if key in override_keys:
            _reject(f"{path} duplicates another scenario override identity.")
        override_keys.add(key)

    auditable_ids = {
        "PROJECT": {project["id"]},
        "PROJECT_SCHEMA_VERSION": {
            item["id"] for item in package["schema_versions"]
        },
        "PROJECT_LOCK": ({lock["id"]} if lock is not None else set()),
        "TIME_SLICE": {item["id"] for item in package["time_slices"]},
        "TENSION_POINT": {item["id"] for item in package["tension_points"]},
        "PARTICIPANT_GROUP": {
            item["id"] for item in package["participant_groups"]
        },
        "GROUP_TENSION_RELATION": {
            item["id"] for item in package["group_tension_relations"]
        },
        "ASSESSMENT_SET": assessment_ids,
        "PARAMETER_DEFINITION": set(definitions),
        "PARAMETER_VALUE": value_ids,
        "EVIDENCE_SOURCE": source_ids,
        "EVIDENCE_LINK": {item["id"] for item in package["evidence_links"]},
        "CALCULATION_STRATEGY_DEFINITION": {
            item["id"] for item in package["calculation_strategies"]
        },
        "SCENARIO": scenario_ids,
        "SCENARIO_OVERRIDE": {
            item["id"] for item in package["scenario_overrides"]
        },
        "AUDIT_EVENT": {item["id"] for item in package["audit_events"]},
    }
    for index, item in enumerate(package["audit_events"]):
        path = f"audit_events[{index}]"
        if item["assessment_set_id"] is not None:
            item["assessment_set_id"] = _require_reference(
                item["assessment_set_id"], assessment_ids, f"{path}.assessment_set_id"
            )
        if item["parameter_value_id"] is not None:
            item["parameter_value_id"] = _require_reference(
                item["parameter_value_id"], value_ids, f"{path}.parameter_value_id"
            )
        if item["assessment_set_id"] is not None and item["parameter_value_id"] is not None:
            value_set_id = next(
                value["assessment_set_id"]
                for value in package["parameter_values"]
                if value["id"] == item["parameter_value_id"]
            )
            if value_set_id != item["assessment_set_id"]:
                _reject(f"{path}.assessment_set_id differs from its parameter value.")
        _choice(item["action"], AuditAction, f"{path}.action")
        _choice(item["actor_type"], AuditActorType, f"{path}.actor_type")
        item["entity_id"] = _require_reference(
            item["entity_id"], auditable_ids[item["entity_type"]], f"{path}.entity_id"
        )
        _datetime_value(item["occurred_at"], f"{path}.occurred_at")

    return package


def _prevalidate_database_conflicts(package: Mapping[str, Any]) -> None:
    project = package["project"]
    if Project.objects.filter(Q(pk=project["id"]) | Q(code=project["code"])).exists():
        raise ProjectPackageConflictError(
            "A project with the package UUID or code already exists; import will not overwrite it."
        )

    section_models = {
        "project_lock": ProjectLock,
        "schema_versions": ProjectSchemaVersion,
        "time_slices": TimeSlice,
        "tension_points": TensionPoint,
        "participant_groups": ParticipantGroup,
        "group_tension_relations": GroupTensionRelation,
        "assessment_sets": AssessmentSet,
        "parameter_definitions": ParameterDefinition,
        "parameter_values": ParameterValue,
        "evidence_sources": EvidenceSource,
        "evidence_links": EvidenceLink,
        "calculation_strategies": CalculationStrategyDefinition,
        "scenarios": Scenario,
        "scenario_overrides": ScenarioOverride,
        "audit_events": AuditEvent,
    }
    for section, model in section_models.items():
        items = (
            []
            if section == "project_lock" and package[section] is None
            else [package[section]]
            if section == "project_lock"
            else package[section]
        )
        ids = [item["id"] for item in items]
        if ids and model.objects.filter(pk__in=ids).exists():
            raise ProjectPackageConflictError(
                f"{section} contains a UUID already used in the database."
            )

    for item in package["calculation_strategies"]:
        if CalculationStrategyDefinition.objects.filter(
            code=item["code"], version=item["version"]
        ).exists():
            raise ProjectPackageConflictError(
                "A calculation strategy with the package code/version already exists."
            )


def _create(model: Any, **kwargs: Any) -> Any:
    obj = model(**kwargs)
    obj.full_clean()
    obj.save(force_insert=True)
    return obj


def _common(item: Mapping[str, Any], project: Project | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {
        "id": UUID(item["id"]),
        "code": item["code"],
        "version": item["version"],
    }
    if project is not None:
        values["project"] = project
    return values


@transaction.atomic
def import_project_package(raw_package: Mapping[str, Any] | str) -> Project:
    """Validate a whole package, then create it in one database transaction."""

    if isinstance(raw_package, str):
        try:
            decoded = json.loads(raw_package)
        except json.JSONDecodeError as exc:
            raise ProjectPackageValidationError(f"Invalid JSON: {exc.msg}.") from exc
    else:
        decoded = raw_package

    package = _validate_and_normalize_package(decoded)
    _prevalidate_database_conflicts(package)
    project_data = package["project"]

    try:
        project = _create(
            Project,
            **_common(project_data),
            name=project_data["name"],
            description=project_data["description"],
            metadata=project_data["metadata"],
        )

        time_slices: dict[str, TimeSlice] = {}
        groups: dict[str, ParticipantGroup] = {}
        tensions: dict[str, TensionPoint] = {}
        relations: dict[str, GroupTensionRelation] = {}
        assessment_sets: dict[str, AssessmentSet] = {}
        definitions: dict[str, ParameterDefinition] = {}
        values: dict[str, ParameterValue] = {}
        sources: dict[str, EvidenceSource] = {}
        scenarios: dict[str, Scenario] = {}

        for item in package["time_slices"]:
            obj = _create(
                TimeSlice,
                **_common(item, project),
                name=item["name"],
                cutoff_date=_date_value(item["cutoff_date"], "cutoff_date"),
                order=item["order"],
            )
            time_slices[item["id"]] = obj

        for section, model, destination in (
            ("tension_points", TensionPoint, tensions),
            ("participant_groups", ParticipantGroup, groups),
        ):
            for item in package[section]:
                obj = _create(
                    model,
                    **_common(item, project),
                    name=item["name"],
                    short_name=item["short_name"],
                    definition=item["definition"],
                    order=item["order"],
                )
                destination[item["id"]] = obj

        for item in package["group_tension_relations"]:
            obj = _create(
                GroupTensionRelation,
                **_common(item, project),
                participant_group=groups[item["participant_group_id"]],
                tension_point=tensions[item["tension_point_id"]],
            )
            relations[item["id"]] = obj

        for item in package["assessment_sets"]:
            obj = _create(
                AssessmentSet,
                **_common(item, project),
                kind=item["kind"],
                name=item["name"],
                description=item["description"],
            )
            assessment_sets[item["id"]] = obj

        for item in package["parameter_definitions"]:
            obj = _create(
                ParameterDefinition,
                **_common(item, project),
                name=item["name"],
                description=item["description"],
                target_type=item["target_type"],
                value_type=item["value_type"],
                scale_min=_decimal_value(item["scale_min"], "scale_min"),
                scale_max=_decimal_value(item["scale_max"], "scale_max"),
                scale_metadata=item["scale_metadata"],
            )
            definitions[item["id"]] = obj

        target_maps: dict[str, Mapping[str, Any]] = {
            TargetType.PROJECT: {str(project.id): project},
            TargetType.TIME_SLICE: time_slices,
            TargetType.TENSION_POINT: tensions,
            TargetType.PARTICIPANT_GROUP: groups,
            TargetType.GROUP_TENSION_RELATION: relations,
        }

        for item in package["parameter_values"]:
            # Resolve the target before validation, even though target_id itself
            # remains a stable UUID rather than a generic foreign key.
            target_maps[item["target_type"]][item["target_id"]]
            obj = _create(
                ParameterValue,
                **_common(item, project),
                time_slice=time_slices[item["time_slice_id"]],
                assessment_set=assessment_sets[item["assessment_set_id"]],
                parameter_definition=definitions[item["parameter_definition_id"]],
                target_type=item["target_type"],
                target_id=UUID(item["target_id"]),
                status=item["status"],
                value=item["value"],
                note=item["note"],
                confidence=_decimal_value(item["confidence"], "confidence"),
                range_min=item["range_min"],
                range_max=item["range_max"],
                rationale=item["rationale"],
            )
            values[item["id"]] = obj

        for item in package["evidence_sources"]:
            obj = _create(
                EvidenceSource,
                **_common(item, project),
                title=item["title"],
                url=item["url"],
                additional_urls=item["additional_urls"],
                published_on=_date_value(
                    item["published_on"], "published_on", nullable=True
                ),
                accessed_on=_date_value(item["accessed_on"], "accessed_on", nullable=True),
                metadata=item["metadata"],
            )
            sources[item["id"]] = obj

        for item in package["evidence_links"]:
            _create(
                EvidenceLink,
                **_common(item, project),
                parameter_value=values[item["parameter_value_id"]],
                source=sources[item["source_id"]],
                relation=item["relation"],
                rationale=item["rationale"],
            )

        for item in package["calculation_strategies"]:
            _create(
                CalculationStrategyDefinition,
                **_common(item, project),
                name=item["name"],
                description=item["description"],
                status=item["status"],
                input_schema=item["input_schema"],
                output_schema=item["output_schema"],
                metadata=item["metadata"],
            )

        for item in package["scenarios"]:
            obj = _create(
                Scenario,
                **_common(item, project),
                time_slice=time_slices[item["time_slice_id"]],
                assessment_set=assessment_sets[item["assessment_set_id"]],
                base_assessment_set=assessment_sets[item["base_assessment_set_id"]],
                name=item["name"],
                description=item["description"],
                status=item["status"],
            )
            scenarios[item["id"]] = obj

        for item in package["scenario_overrides"]:
            target_maps[item["target_type"]][item["target_id"]]
            _create(
                ScenarioOverride,
                **_common(item, project),
                scenario=scenarios[item["scenario_id"]],
                parameter_definition=definitions[item["parameter_definition_id"]],
                target_type=item["target_type"],
                target_id=UUID(item["target_id"]),
                status=item["status"],
                value=item["value"],
                note=item["note"],
                confidence=_decimal_value(item["confidence"], "confidence"),
                range_min=item["range_min"],
                range_max=item["range_max"],
                rationale=item["rationale"],
            )

        for item in package["schema_versions"]:
            _create(
                ProjectSchemaVersion,
                **_common(item, project),
                is_current=item["is_current"],
                manifest=item["schema_manifest"],
                manifest_hash=item["schema_manifest_hash"],
            )

        lock = package["project_lock"]
        if lock is not None:
            _create(
                ProjectLock,
                **_common(lock, project),
                is_structure_locked=lock["is_structure_locked"],
                ordinary_user_can_edit_structure=lock[
                    "ordinary_user_can_edit_structure"
                ],
                studio_can_edit_structure=lock["studio_can_edit_structure"],
                reason=lock["reason"],
            )

        for item in package["audit_events"]:
            _create(
                AuditEvent,
                **_common(item, project),
                assessment_set=(
                    assessment_sets[item["assessment_set_id"]]
                    if item["assessment_set_id"]
                    else None
                ),
                parameter_value=(
                    values[item["parameter_value_id"]]
                    if item["parameter_value_id"]
                    else None
                ),
                action=item["action"],
                actor_type=item["actor_type"],
                actor_identifier=item["actor_identifier"],
                entity_type=item["entity_type"],
                entity_id=UUID(item["entity_id"]),
                before=item["before"],
                after=item["after"],
                occurred_at=_datetime_value(item["occurred_at"], "occurred_at"),
            )
        return project
    except (ValidationError, IntegrityError) as exc:
        raise ProjectPackageValidationError(
            f"Package violates the domain model: {exc}."
        ) from exc
