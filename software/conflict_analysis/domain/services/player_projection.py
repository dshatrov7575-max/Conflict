"""Deterministic, receipt-bound assessment projection for one workspace.

This module is deliberately Foundation-only: it creates no workspace, exposes
no HTTP surface, imports no values, and never tries to repair a projection.
The source of truth is the exact published definition manifest pinned by the
workspace.  Projected identities are a deterministic read-model for the sole
``ParameterValue`` numeric lane.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from domain.enums import (
    AssessmentProjectionStatus,
    AuditAction,
    AuditActorType,
    AuditScope,
    PublicationStatus,
)
from domain.models import (
    Actor,
    ActorElementRole,
    AnalyticalElement,
    AuditEvent,
    ParameterDefinition,
    ProjectDefinitionVersion,
    ProjectWorkspace,
    _canonical_assessment_projection_write,
)
from domain.services.project_definitions import parse_project_definition_manifest_v1
from domain.services import zhanaozen_typed_manifest as zhanaozen


PROJECTION_CONTRACT = "FOUNDATION_WORKSPACE_ASSESSMENT_PROJECTION_V1"
WORKSPACE_CREATE_CONTRACT = "FOUNDATION_PLAYER_WORKSPACE_CREATE_V1"
_IDENTITY_PREFIX = "PROJECT_DEFINITION_MANIFEST_V1"
_PROJECTION_RECEIPT_CONTRACTS = (
    PROJECTION_CONTRACT, WORKSPACE_CREATE_CONTRACT, zhanaozen.SYSTEM_CONTRACT,
)
_CANONICAL_REQUEST_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class AssessmentProjectionError(RuntimeError):
    """Stable failure that leaves no silently repaired canonical projection."""

    code = "ASSESSMENT_PROJECTION_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code or self.code
        super().__init__(f"{self.code}: {message}")


class AssessmentProjectionConflict(AssessmentProjectionError):
    code = "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT"


@dataclass(frozen=True, slots=True)
class AssessmentProjectionVerification:
    status: str
    projection_sha256: str | None
    receipt: AuditEvent | None
    reason: str = ""

    @property
    def complete(self) -> bool:
        return self.status == AssessmentProjectionStatus.COMPLETE


@dataclass(frozen=True, slots=True)
class AssessmentProjectionResult:
    workspace: ProjectWorkspace
    receipt: AuditEvent
    projection_sha256: str
    replayed: bool


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _decimal_text(value: Any) -> str | None:
    """Use one non-exponent decimal representation on both sides of replay."""

    if value is None:
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise AssessmentProjectionConflict(
            "A canonical parameter scale is not a finite decimal."
        ) from exc
    if not decimal.is_finite():
        raise AssessmentProjectionConflict("A canonical parameter scale is not finite.")
    text = format(decimal.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _exact_uuid(value: object, *, field: str) -> uuid.UUID:
    try:
        resolved = uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise AssessmentProjectionError(
            f"{field} must be an exact UUID.", code="ASSESSMENT_PROJECTION_IDENTITY_INVALID"
        ) from exc
    if str(resolved) != str(value):
        raise AssessmentProjectionError(
            f"{field} must use canonical lowercase UUID text.",
            code="ASSESSMENT_PROJECTION_IDENTITY_INVALID",
        )
    return resolved


def _source_hash(item: Mapping[str, Any]) -> str:
    return _sha256(dict(item))


def _derived_id(workspace_id: uuid.UUID, kind: str, source_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(
        workspace_id,
        f"{_IDENTITY_PREFIX}:{kind}:{source_id}",
    )


def _parameter_id(definition_id: uuid.UUID, source_id: uuid.UUID) -> uuid.UUID:
    return uuid.uuid5(
        definition_id,
        f"{_IDENTITY_PREFIX}:PARAMETER:{source_id}",
    )


def _projection_receipts(workspace: ProjectWorkspace) -> list[AuditEvent]:
    return list(
        AuditEvent.objects.filter(
            workspace=workspace,
            entity_type__in=_PROJECTION_RECEIPT_CONTRACTS,
        ).order_by("occurred_at", "created_at", "pk")
    )


def _projection_receipt(workspace: ProjectWorkspace) -> AuditEvent | None:
    receipts = _projection_receipts(workspace)
    return receipts[0] if len(receipts) == 1 else None


def _canonical_request_sha256(value: object) -> str:
    """Accept only the opaque caller-owned combined-operation request digest."""

    if not isinstance(value, str) or _CANONICAL_REQUEST_SHA256.fullmatch(value) is None:
        raise AssessmentProjectionError(
            "canonical_request_sha256 must be exactly 64 lowercase hexadecimal characters.",
            code="ASSESSMENT_PROJECTION_REQUEST_SHA256_INVALID",
        )
    return value


def _canonical_occurred_at(value: datetime) -> str:
    if timezone.is_naive(value):
        raise AssessmentProjectionConflict("Combined receipt time must be timezone-aware.")
    return (
        value.astimezone(datetime_timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _parse_canonical_occurred_at(value: object) -> datetime:
    if not isinstance(value, str):
        raise AssessmentProjectionConflict("Combined receipt time is not canonical text.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AssessmentProjectionConflict("Combined receipt time cannot be parsed.") from exc
    if timezone.is_naive(parsed) or _canonical_occurred_at(parsed) != value:
        raise AssessmentProjectionConflict("Combined receipt time is not canonical UTC text.")
    return parsed.astimezone(datetime_timezone.utc)


def _projection_counts(expected: Mapping[str, Any]) -> dict[str, int]:
    return {
        section: len(expected[section])
        for section in (
            "actors",
            "analytical_elements",
            "actor_element_roles",
            "parameter_definitions",
        )
    }


def _combined_receipt_core(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    *,
    operation_id: uuid.UUID,
    principal: str,
    canonical_request_sha256: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    """Return the immutable, independently hashable combined-operation evidence."""

    projection_request = _projection_request(
        workspace,
        expected,
        operation_id=operation_id,
        principal=principal,
    )
    counts = _projection_counts(expected)
    return {
        "contract": WORKSPACE_CREATE_CONTRACT,
        "version": "1.0.0",
        "operation_id": str(operation_id),
        "audit_event_id": str(operation_id),
        "actor_type": AuditActorType.HUMAN,
        "actor_identifier": principal,
        "project_id": str(workspace.project_id),
        "workspace_id": str(workspace.pk),
        "definition_id": str(workspace.definition_version_id),
        "manifest_sha256": workspace.definition_manifest_hash,
        "canonical_request_sha256": canonical_request_sha256,
        "projection_request": projection_request,
        "projection_request_sha256": _sha256(projection_request),
        "source_mapping_sha256": expected["source_mapping_sha256"],
        "snapshot_sha256": expected["snapshot_sha256"],
        "projection_sha256": expected["projection_sha256"],
        "source_counts": counts,
        "projected_counts": counts,
        "occurred_at": _canonical_occurred_at(occurred_at),
        "original_http_status": 201,
    }


def _combined_receipt_payload(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    *,
    operation_id: uuid.UUID,
    principal: str,
    canonical_request_sha256: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    core = _combined_receipt_core(
        workspace,
        expected,
        operation_id=operation_id,
        principal=principal,
        canonical_request_sha256=canonical_request_sha256,
        occurred_at=occurred_at,
    )
    return {**core, "receipt_sha256": _sha256(core)}


def _standalone_receipt_matches_expected_projection(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    receipt: AuditEvent,
) -> bool:
    """Check immutable receipt provenance independently of current graph rows."""

    after = dict(receipt.after) if isinstance(receipt.after, Mapping) else {}
    try:
        operation_id = _exact_uuid(after.get("operation_id"), field="receipt.operation_id")
        principal = str(after.get("actor_identifier", "")).strip()
        if not principal:
            return False
        expected_receipt = _projection_receipt_payload(
            workspace,
            expected,
            operation_id=operation_id,
            principal=principal,
            receipt_id=receipt.pk,
        )
    except AssessmentProjectionError:
        return False
    return not (
        receipt.project_id != workspace.project_id
        or receipt.workspace_id != workspace.pk
        or receipt.definition_version_id is not None
        or receipt.scope != AuditScope.WORKSPACE
        or receipt.action != AuditAction.CREATE
        or receipt.actor_type != AuditActorType.HUMAN
        or receipt.actor_identifier != principal
        or receipt.entity_type != PROJECTION_CONTRACT
        or receipt.entity_id != workspace.pk
        or receipt.before is not None
        or receipt.code != f"ASSESSMENT-PROJECTION-{operation_id}"
        or receipt.version != "1.0.0"
        or after != expected_receipt
    )


def _combined_receipt_matches_expected_projection(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    receipt: AuditEvent,
) -> bool:
    """Verify combined evidence from its immutable payload alone.

    This deliberately never consumes a caller request: a later verifier has
    only the persisted audit event and current pinned graph to inspect.
    """

    after = dict(receipt.after) if isinstance(receipt.after, Mapping) else {}
    try:
        operation_id = _exact_uuid(after.get("operation_id"), field="receipt.operation_id")
        canonical_request_sha256 = _canonical_request_sha256(
            after.get("canonical_request_sha256")
        )
        principal = str(after.get("actor_identifier", "")).strip()
        if not principal:
            return False
        occurred_at = _parse_canonical_occurred_at(after.get("occurred_at"))
        expected_receipt = _combined_receipt_payload(
            workspace,
            expected,
            operation_id=operation_id,
            principal=principal,
            canonical_request_sha256=canonical_request_sha256,
            occurred_at=occurred_at,
        )
    except AssessmentProjectionError:
        return False
    return not (
        receipt.pk != operation_id
        or receipt.project_id != workspace.project_id
        or receipt.workspace_id != workspace.pk
        or receipt.definition_version_id is not None
        or receipt.scope != AuditScope.WORKSPACE
        or receipt.action != AuditAction.CREATE
        or receipt.actor_type != AuditActorType.HUMAN
        or receipt.actor_identifier != principal
        or receipt.entity_type != WORKSPACE_CREATE_CONTRACT
        or receipt.entity_id != workspace.pk
        or receipt.before is not None
        or receipt.code != f"WORKSPACE-CREATE-PROJECTION-{operation_id}"
        or receipt.version != "1.0.0"
        or _canonical_occurred_at(receipt.occurred_at) != after.get("occurred_at")
        or after != expected_receipt
    )


def _combined_receipt_matches_materialize_request(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    receipt: AuditEvent,
    *,
    operation_id: uuid.UUID,
    principal: str,
    canonical_request_sha256: str,
) -> bool:
    """Require exact persisted combined evidence for a caller-owned replay."""

    after = dict(receipt.after) if isinstance(receipt.after, Mapping) else {}
    return (
        receipt.pk == operation_id
        and after.get("operation_id") == str(operation_id)
        and after.get("canonical_request_sha256") == canonical_request_sha256
        and after.get("actor_identifier") == principal
        and _combined_receipt_matches_expected_projection(workspace, expected, receipt)
    )


def _receipt_matches_expected_projection(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    receipt: AuditEvent,
) -> bool:
    if receipt.entity_type == PROJECTION_CONTRACT:
        return _standalone_receipt_matches_expected_projection(workspace, expected, receipt)
    if receipt.entity_type == WORKSPACE_CREATE_CONTRACT:
        return _combined_receipt_matches_expected_projection(workspace, expected, receipt)
    if receipt.entity_type == zhanaozen.SYSTEM_CONTRACT:
        return _system_receipt_matches_expected_projection(workspace, expected, receipt)
    return False


def _definition_snapshot_is_receipt_proven(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
) -> bool:
    """Prove shared definition snapshots without treating another graph as repairable.

    Parameter snapshots are definition-scoped, while actors/elements/roles are
    workspace-scoped.  A later drift in a sibling graph must fail that sibling's
    own reconciliation, but it cannot erase the original immutable receipt that
    proved the shared snapshots were created by the projection service.
    """

    try:
        sibling_expected = _expected_projection(workspace)
    except AssessmentProjectionError:
        return False
    if (
        sibling_expected["parameter_definitions"]
        != expected["parameter_definitions"]
        or sibling_expected["snapshot_sha256"] != expected["snapshot_sha256"]
    ):
        return False
    receipt = _projection_receipt(workspace)
    return receipt is not None and _receipt_matches_expected_projection(
        workspace,
        sibling_expected,
        receipt,
    )


def _manifest_for_workspace(workspace: ProjectWorkspace) -> dict[str, Any]:
    if workspace.pk is None:
        raise AssessmentProjectionError(
            "A persisted workspace is required.", code="ASSESSMENT_PROJECTION_WORKSPACE_REQUIRED"
        )
    definition = workspace.definition_version
    if definition.project_id != workspace.project_id:
        raise AssessmentProjectionConflict("Workspace definition belongs to another project.")
    if definition.publication_status != PublicationStatus.PUBLISHED:
        raise AssessmentProjectionConflict("Workspace definition is not published.")
    if definition.manifest_hash != workspace.definition_manifest_hash:
        raise AssessmentProjectionConflict("Workspace manifest pin has drifted.")
    try:
        parsed = parse_project_definition_manifest_v1(
            definition.manifest,
            project=workspace.project,
        )
    except Exception as exc:  # parser returns a stable public error shape
        raise AssessmentProjectionConflict(
            "The exact published definition manifest cannot be parsed."
        ) from exc
    if parsed.manifest_sha256 != definition.manifest_hash:
        raise AssessmentProjectionConflict("Published definition manifest hash has drifted.")
    return parsed.as_dict()


def _source_items(manifest: Mapping[str, Any], section: str) -> list[dict[str, Any]]:
    value = manifest.get(section)
    if not isinstance(value, list):
        raise AssessmentProjectionConflict(f"Manifest {section} is not an exact ordered list.")
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise AssessmentProjectionConflict(f"Manifest {section} contains a non-object item.")
        items.append(dict(item))
    return items


def _expected_projection(workspace: ProjectWorkspace) -> dict[str, Any]:
    manifest = _manifest_for_workspace(workspace)
    definition = workspace.definition_version
    actors = _source_items(manifest, "actors")
    elements = _source_items(manifest, "analytical_elements")
    roles = _source_items(manifest, "actor_element_roles")
    parameters = _source_items(manifest, "parameter_definitions")

    def actor_item(item: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _exact_uuid(item.get("id"), field="actor.id")
        parent_value = item.get("parent_id")
        parent_source_id = (
            _exact_uuid(parent_value, field="actor.parent_id")
            if parent_value is not None
            else None
        )
        return {
            "id": str(_derived_id(workspace.pk, "ACTOR", source_id)),
            "source_manifest_entity_id": str(source_id),
            "source_manifest_entity_sha256": _source_hash(item),
            "source_manifest_parent_id": str(parent_source_id) if parent_source_id else None,
            "parent_id": str(_derived_id(workspace.pk, "ACTOR", parent_source_id))
            if parent_source_id
            else None,
            "code": str(item["code"]),
            "version": str(item["version"]),
            "actor_type": str(item["actor_type"]),
            "label": str(item["label"]),
            "description": str(item["description"]),
            "order": int(item["order"]),
            "metadata": {},
        }

    def element_item(item: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _exact_uuid(item.get("id"), field="analytical_element.id")
        parent_value = item.get("parent_id")
        parent_source_id = (
            _exact_uuid(parent_value, field="analytical_element.parent_id")
            if parent_value is not None
            else None
        )
        return {
            "id": str(_derived_id(workspace.pk, "ANALYTICAL_ELEMENT", source_id)),
            "source_manifest_entity_id": str(source_id),
            "source_manifest_entity_sha256": _source_hash(item),
            "source_manifest_parent_id": str(parent_source_id) if parent_source_id else None,
            "parent_id": str(
                _derived_id(workspace.pk, "ANALYTICAL_ELEMENT", parent_source_id)
            )
            if parent_source_id
            else None,
            "code": str(item["code"]),
            "version": str(item["version"]),
            "element_type": str(item["element_type"]),
            "label": str(item["label"]),
            "reference_statement": str(item["reference_statement"]),
            "description": str(item["description"]),
            "order": int(item["order"]),
            "metadata": {},
        }

    def role_item(item: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _exact_uuid(item.get("id"), field="actor_element_role.id")
        actor_source = _exact_uuid(item.get("actor_id"), field="actor_element_role.actor_id")
        element_source = _exact_uuid(item.get("element_id"), field="actor_element_role.element_id")
        return {
            "id": str(_derived_id(workspace.pk, "ACTOR_ELEMENT_ROLE", source_id)),
            "source_manifest_entity_id": str(source_id),
            "source_manifest_entity_sha256": _source_hash(item),
            "actor_source_manifest_entity_id": str(actor_source),
            "element_source_manifest_entity_id": str(element_source),
            "actor_id": str(_derived_id(workspace.pk, "ACTOR", actor_source)),
            "element_id": str(
                _derived_id(workspace.pk, "ANALYTICAL_ELEMENT", element_source)
            ),
            "code": str(item["code"]),
            "version": str(item["version"]),
            "role": str(item["role"]),
            "note": str(item["note"]),
            "order": int(item["order"]),
        }

    def parameter_item(item: Mapping[str, Any]) -> dict[str, Any]:
        source_id = _exact_uuid(item.get("id"), field="parameter_definition.id")
        scale = item.get("scale")
        applicability = item.get("applicability")
        if not isinstance(scale, Mapping) or not isinstance(applicability, Mapping):
            raise AssessmentProjectionConflict(
                "Parameter definition snapshot is missing exact scale or applicability."
            )
        snapshot = {
            "name": str(item["name"]),
            "description": str(item["description"]),
            "target_type": str(item["target_type"]),
            "value_type": str(item["value_type"]),
            "scale_min": _decimal_text(scale.get("minimum")),
            "scale_max": _decimal_text(scale.get("maximum")),
            "scale_step": _decimal_text(scale.get("step")),
            "scale_metadata": {},
            "allowed_statuses": list(item.get("allowed_statuses", [])),
            "applicability": {
                "actor_ids": list(applicability.get("actor_ids", [])),
                "analytical_element_ids": list(
                    applicability.get("analytical_element_ids", [])
                ),
                "actor_element_role_ids": list(
                    applicability.get("actor_element_role_ids", [])
                ),
            },
            "reference_statement": str(item["reference_statement"]),
        }
        return {
            "id": str(_parameter_id(definition.pk, source_id)),
            "definition_version_id": str(definition.pk),
            "source_manifest_parameter_id": str(source_id),
            "manifest_snapshot_sha256": _source_hash(item),
            "code": str(item["code"]),
            "version": str(item["version"]),
            **snapshot,
        }

    expected = {
        "contract": PROJECTION_CONTRACT,
        "workspace": {
            "id": str(workspace.pk),
            "project_id": str(workspace.project_id),
            "definition_id": str(definition.pk),
            "manifest_sha256": workspace.definition_manifest_hash,
        },
        "actors": [actor_item(item) for item in actors],
        "analytical_elements": [element_item(item) for item in elements],
        "actor_element_roles": [role_item(item) for item in roles],
        "parameter_definitions": [parameter_item(item) for item in parameters],
    }
    # The manifest's semantic ordering is its explicit ``order`` field (and
    # source UUID as a deterministic tie-breaker), never incidental JSON list
    # position.  The same canonical order is persisted and replayed below.
    for section in ("actors", "analytical_elements", "actor_element_roles"):
        expected[section] = sorted(
            expected[section],
            key=lambda item: (item["order"], item["source_manifest_entity_id"]),
        )
    expected["parameter_definitions"] = sorted(
        expected["parameter_definitions"],
        key=lambda item: (item["code"], item["source_manifest_parameter_id"]),
    )
    source_mapping = {
        section: [
            {
                "source_manifest_id": item["source_manifest_entity_id"],
                "derived_id": item["id"],
            }
            for item in expected[section]
        ]
        for section in ("actors", "analytical_elements", "actor_element_roles")
    }
    source_mapping["parameter_definitions"] = [
        {
            "source_manifest_id": item["source_manifest_parameter_id"],
            "derived_id": item["id"],
        }
        for item in expected["parameter_definitions"]
    ]
    expected["source_mapping_sha256"] = _sha256(source_mapping)
    expected["snapshot_sha256"] = _sha256(expected["parameter_definitions"])
    expected["projection_sha256"] = _sha256(
        {
            key: value
            for key, value in expected.items()
            if key != "projection_sha256"
        }
    )
    return expected


def _actual_projection(workspace: ProjectWorkspace) -> dict[str, Any]:
    actors = []
    for row in Actor.objects.filter(
        workspace=workspace, source_manifest_entity_id__isnull=False
    ).order_by("order", "source_manifest_entity_id"):
        actors.append(
            {
                "id": str(row.pk),
                "source_manifest_entity_id": str(row.source_manifest_entity_id),
                "source_manifest_entity_sha256": row.source_manifest_entity_sha256,
                "source_manifest_parent_id": None,
                "parent_id": str(row.parent_id) if row.parent_id else None,
                "code": row.code,
                "version": row.version,
                "actor_type": row.actor_type,
                "label": row.label,
                "description": row.description,
                "order": row.order,
                "metadata": row.metadata,
            }
        )
    # Parent source ids are intentionally reconstructed from persisted rows,
    # not the manifest, so a wrong parent is detectable.
    actor_by_id = {item["id"]: item for item in actors}
    for item in actors:
        parent_id = item["parent_id"]
        item["source_manifest_parent_id"] = (
            actor_by_id[parent_id]["source_manifest_entity_id"]
            if parent_id in actor_by_id
            else None
        )

    elements = []
    for row in AnalyticalElement.objects.filter(
        workspace=workspace, source_manifest_entity_id__isnull=False
    ).order_by("order", "source_manifest_entity_id"):
        elements.append(
            {
                "id": str(row.pk),
                "source_manifest_entity_id": str(row.source_manifest_entity_id),
                "source_manifest_entity_sha256": row.source_manifest_entity_sha256,
                "source_manifest_parent_id": None,
                "parent_id": str(row.parent_id) if row.parent_id else None,
                "code": row.code,
                "version": row.version,
                "element_type": row.element_type,
                "label": row.label,
                "reference_statement": row.reference_statement,
                "description": row.description,
                "order": row.order,
                "metadata": row.metadata,
            }
        )
    element_by_id = {item["id"]: item for item in elements}
    for item in elements:
        parent_id = item["parent_id"]
        item["source_manifest_parent_id"] = (
            element_by_id[parent_id]["source_manifest_entity_id"]
            if parent_id in element_by_id
            else None
        )

    roles = []
    for row in ActorElementRole.objects.filter(
        workspace=workspace, source_manifest_entity_id__isnull=False
    ).select_related("actor", "element").order_by("order", "source_manifest_entity_id"):
        roles.append(
            {
                "id": str(row.pk),
                "source_manifest_entity_id": str(row.source_manifest_entity_id),
                "source_manifest_entity_sha256": row.source_manifest_entity_sha256,
                "actor_source_manifest_entity_id": str(row.actor.source_manifest_entity_id)
                if row.actor.source_manifest_entity_id
                else None,
                "element_source_manifest_entity_id": str(
                    row.element.source_manifest_entity_id
                )
                if row.element.source_manifest_entity_id
                else None,
                "actor_id": str(row.actor_id),
                "element_id": str(row.element_id),
                "code": row.code,
                "version": row.version,
                "role": row.role,
                "note": row.note,
                "order": row.order,
            }
        )

    parameters = []
    for row in ParameterDefinition.objects.filter(
        definition_version=workspace.definition_version,
        source_manifest_parameter_id__isnull=False,
    ).order_by("code", "source_manifest_parameter_id"):
        parameters.append(
            {
                "id": str(row.pk),
                "definition_version_id": str(row.definition_version_id),
                "source_manifest_parameter_id": str(row.source_manifest_parameter_id),
                "manifest_snapshot_sha256": row.manifest_snapshot_sha256,
                "code": row.code,
                "version": row.version,
                "name": row.name,
                "description": row.description,
                "target_type": row.target_type,
                "value_type": row.value_type,
                "scale_min": _decimal_text(row.scale_min),
                "scale_max": _decimal_text(row.scale_max),
                "scale_step": _decimal_text(row.scale_step),
                "scale_metadata": row.scale_metadata,
                "allowed_statuses": row.allowed_statuses,
                "applicability": row.applicability,
                "reference_statement": row.reference_statement,
            }
        )
    return {
        "actors": actors,
        "analytical_elements": elements,
        "actor_element_roles": roles,
        "parameter_definitions": parameters,
    }


def _same_projection(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    return all(
        expected[section] == actual[section]
        for section in (
            "actors",
            "analytical_elements",
            "actor_element_roles",
            "parameter_definitions",
        )
    )


def _projection_request(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    *,
    operation_id: uuid.UUID,
    principal: str,
) -> dict[str, Any]:
    return {
        "operation_id": str(operation_id),
        "human_principal": principal,
        "project_id": str(workspace.project_id),
        "workspace_id": str(workspace.pk),
        "definition_id": str(workspace.definition_version_id),
        "manifest_sha256": workspace.definition_manifest_hash,
        "source_mapping_sha256": expected["source_mapping_sha256"],
        "snapshot_sha256": expected["snapshot_sha256"],
        "projection_sha256": expected["projection_sha256"],
    }


def _projection_receipt_payload(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    *,
    operation_id: uuid.UUID,
    principal: str,
    receipt_id: uuid.UUID,
) -> dict[str, Any]:
    request = _projection_request(
        workspace,
        expected,
        operation_id=operation_id,
        principal=principal,
    )
    counts = {
        section: len(expected[section])
        for section in (
            "actors",
            "analytical_elements",
            "actor_element_roles",
            "parameter_definitions",
        )
    }
    return {
        "contract": PROJECTION_CONTRACT,
        "version": "1.0.0",
        "operation_id": str(operation_id),
        "audit_event_id": str(receipt_id),
        "actor_type": AuditActorType.HUMAN,
        "actor_identifier": principal,
        "project_id": str(workspace.project_id),
        "workspace_id": str(workspace.pk),
        "definition_id": str(workspace.definition_version_id),
        "manifest_sha256": workspace.definition_manifest_hash,
        "request": request,
        "request_sha256": _sha256(request),
        "source_mapping_sha256": expected["source_mapping_sha256"],
        "snapshot_sha256": expected["snapshot_sha256"],
        "projection_sha256": expected["projection_sha256"],
        "source_counts": counts,
        "projected_counts": counts,
        "original_http_status": 201,
    }


def verify_workspace_assessment_projection(
    workspace: ProjectWorkspace,
) -> AssessmentProjectionVerification:
    """Purely verify persisted receipt and rows; never create or repair data."""

    # Verification is evidence-based: callers frequently retain the workspace
    # object that existed before materialization, so its in-memory status/hash
    # can be stale even though the committed database state is complete.  Read
    # the persisted pin and evidence rather than letting a caller-owned object
    # change the result of an otherwise read-only replay check.
    if workspace.pk is None:
        return AssessmentProjectionVerification(
            AssessmentProjectionStatus.INTEGRITY_CONFLICT,
            None,
            None,
            "A persisted workspace is required for projection verification.",
        )
    try:
        workspace = ProjectWorkspace.objects.select_related(
            "project", "definition_version"
        ).get(pk=workspace.pk)
    except ProjectWorkspace.DoesNotExist:
        return AssessmentProjectionVerification(
            AssessmentProjectionStatus.INTEGRITY_CONFLICT,
            None,
            None,
            "The workspace no longer exists for projection verification.",
        )
    try:
        expected = _expected_projection(workspace)
    except AssessmentProjectionError as exc:
        return AssessmentProjectionVerification(
            AssessmentProjectionStatus.INTEGRITY_CONFLICT,
            None,
            None,
            str(exc),
        )
    receipts = _projection_receipts(workspace)
    receipt = receipts[0] if len(receipts) == 1 else None
    actual = _actual_projection(workspace)
    has_workspace_rows = any(
        actual[section]
        for section in ("actors", "analytical_elements", "actor_element_roles")
    )
    if receipt is None:
        status_is_initial = (
            workspace.assessment_projection_status
            == AssessmentProjectionStatus.NOT_PROVEN
            and workspace.assessment_projection_sha256 is None
        )
        return AssessmentProjectionVerification(
            AssessmentProjectionStatus.INTEGRITY_CONFLICT
            if len(receipts) > 1 or has_workspace_rows or not status_is_initial
            else AssessmentProjectionStatus.NOT_PROVEN,
            None,
            None,
            "No single exact persisted projection receipt exists.",
        )
    if (
        not _receipt_matches_expected_projection(workspace, expected, receipt)
        or not _same_projection(expected, actual)
        or workspace.assessment_projection_status != AssessmentProjectionStatus.COMPLETE
        or workspace.assessment_projection_sha256 != expected["projection_sha256"]
    ):
        return AssessmentProjectionVerification(
            AssessmentProjectionStatus.INTEGRITY_CONFLICT,
            None,
            receipt,
            "The persisted receipt, manifest pin, or canonical rows do not exactly replay.",
        )
    return AssessmentProjectionVerification(
        AssessmentProjectionStatus.COMPLETE,
        expected["projection_sha256"],
        receipt,
    )


def _create_ordered_tree(
    *,
    workspace: ProjectWorkspace,
    expected: list[Mapping[str, Any]],
    model: type[Any],
    kind: str,
) -> None:
    pending = {item["source_manifest_entity_id"]: dict(item) for item in expected}
    while pending:
        ready = [
            item
            for item in pending.values()
            if item["source_manifest_parent_id"] is None
            or item["source_manifest_parent_id"] not in pending
        ]
        if not ready:
            raise AssessmentProjectionConflict(
                f"{kind} manifest hierarchy cannot be materialized deterministically."
            )
        for item in ready:
            model.objects.create(
                id=uuid.UUID(item["id"]),
                code=item["code"],
                version=item["version"],
                workspace=workspace,
                parent_id=uuid.UUID(item["parent_id"]) if item["parent_id"] else None,
                source_manifest_entity_id=uuid.UUID(item["source_manifest_entity_id"]),
                source_manifest_entity_sha256=item["source_manifest_entity_sha256"],
                **(
                    {
                        "actor_type": item["actor_type"],
                        "label": item["label"],
                        "description": item["description"],
                        "order": item["order"],
                        "metadata": {},
                    }
                    if kind == "ACTOR"
                    else {
                        "element_type": item["element_type"],
                        "label": item["label"],
                        "reference_statement": item["reference_statement"],
                        "description": item["description"],
                        "order": item["order"],
                        "metadata": {},
                    }
                ),
            )
            del pending[item["source_manifest_entity_id"]]


def _materialize_expected(
    workspace: ProjectWorkspace,
    expected: Mapping[str, Any],
    *,
    create_parameter_snapshots: bool,
    inject_failure_at: str | None,
) -> None:
    _create_ordered_tree(
        workspace=workspace,
        expected=expected["actors"],
        model=Actor,
        kind="ACTOR",
    )
    if inject_failure_at == "after_actors":
        raise AssessmentProjectionError("Injected failure after actors.")
    _create_ordered_tree(
        workspace=workspace,
        expected=expected["analytical_elements"],
        model=AnalyticalElement,
        kind="ANALYTICAL_ELEMENT",
    )
    if inject_failure_at == "after_elements":
        raise AssessmentProjectionError("Injected failure after elements.")
    for item in expected["actor_element_roles"]:
        ActorElementRole.objects.create(
            id=uuid.UUID(item["id"]),
            code=item["code"],
            version=item["version"],
            workspace=workspace,
            actor_id=uuid.UUID(item["actor_id"]),
            element_id=uuid.UUID(item["element_id"]),
            role=item["role"],
            note=item["note"],
            order=item["order"],
            source_manifest_entity_id=uuid.UUID(item["source_manifest_entity_id"]),
            source_manifest_entity_sha256=item["source_manifest_entity_sha256"],
        )
    if inject_failure_at == "after_roles":
        raise AssessmentProjectionError("Injected failure after roles.")
    if create_parameter_snapshots:
        for item in expected["parameter_definitions"]:
            ParameterDefinition.objects.create(
                id=uuid.UUID(item["id"]),
                project=workspace.project,
                code=item["code"],
                version=item["version"],
                name=item["name"],
                description=item["description"],
                target_type=item["target_type"],
                value_type=item["value_type"],
                scale_min=Decimal(item["scale_min"]) if item["scale_min"] is not None else None,
                scale_max=Decimal(item["scale_max"]) if item["scale_max"] is not None else None,
                scale_step=Decimal(item["scale_step"]) if item["scale_step"] is not None else None,
                scale_metadata=item["scale_metadata"],
                allowed_statuses=item["allowed_statuses"],
                applicability=item["applicability"],
                reference_statement=item["reference_statement"],
                definition_version=workspace.definition_version,
                source_manifest_parameter_id=uuid.UUID(
                    item["source_manifest_parameter_id"]
                ),
                manifest_snapshot_sha256=item["manifest_snapshot_sha256"],
            )
    if inject_failure_at == "after_parameters":
        raise AssessmentProjectionError("Injected failure after parameters.")


def _require_zhanaozen_workspace(workspace):
    pin = zhanaozen.workspace()
    definition = workspace.definition_version
    facts = {
        "id": str(workspace.pk), "code": workspace.code,
        "version": workspace.version, "label": workspace.name,
        "metadata": workspace.metadata,
        "project_definition_version_id": str(workspace.definition_version_id),
        "project_definition_hash": workspace.definition_manifest_hash,
    }
    if (facts != pin or workspace.is_default
        or str(workspace.project_id) != zhanaozen.PROJECT_ID
        or workspace.project.code != "KZ-ZHANAOZEN-DEMO"
        or workspace.project.version != "1.0.0"
        or definition.code != zhanaozen.DEFINITION_CODE
        or definition.version != zhanaozen.DEFINITION_ROW_VERSION
        or definition.schema_version != "1.0.0"
        or definition.semantic_version != "1.0.0"
        or definition.construct_version != "V4-TERM-2.0"
        or str(definition.supersedes_id) != zhanaozen.LEGACY_DEFINITION_ID):
        raise AssessmentProjectionConflict("SYSTEM installation identity/pin mismatch.")


def _require_zhanaozen_system_authority(workspace, principal):
    from domain.policies import (
        FoundationAuditContext, StudioPrincipal, StudioDefinitionRole,
        StructureActor, require_project_structure_mutation,
    )
    if (not isinstance(principal, StudioPrincipal)
        or principal.role != StudioDefinitionRole.SERVICE
        or principal.actor_identifier != zhanaozen.SYSTEM_ACTOR
        or principal.service_purpose != zhanaozen.SYSTEM_PURPOSE
        or principal.capabilities != zhanaozen.SYSTEM_CAPABILITIES):
        raise AssessmentProjectionConflict("Exact bounded Zhanaozen SERVICE required.")
    # This existing authority checks the unforgeable SERVICE context seal.
    FoundationAuditContext.for_principal_workspace(workspace=workspace, principal=principal)
    _require_zhanaozen_workspace(workspace)
    require_project_structure_mutation(
        workspace.project, actor=StructureActor.SERVICE, service_principal=principal,
    )


def _system_receipt_payload(workspace, expected):
    _require_zhanaozen_workspace(workspace)
    payload = zhanaozen.system_audit()["after"]
    accepted = zhanaozen.system_audit()["after"]
    for key in ("source_mapping_sha256", "snapshot_sha256", "projection_sha256"):
        payload[key] = payload["request"][key] = expected[key]
    payload["source_counts"] = payload["projected_counts"] = _projection_counts(expected)
    payload["request_sha256"] = _sha256(payload["request"])
    if payload != accepted:
        raise AssessmentProjectionConflict("SYSTEM graph differs from the exact V3 receipt.")
    return payload


def _system_receipt_matches_expected_projection(workspace, expected, receipt):
    try:
        payload = _system_receipt_payload(workspace, expected)
    except AssessmentProjectionError:
        return False
    row = zhanaozen.system_audit()
    for key, value in row.items():
        actual = getattr(receipt, key)
        if isinstance(actual, uuid.UUID):
            actual = str(actual)
        if actual != (payload if key == "after" else value):
            return False
    return all(getattr(receipt, key) is None for key in (
        "definition_version_id", "assessment_set_id", "parameter_value_id",
    ))


def _materialize_zhanaozen_system_projection(workspace, *, principal, inject_failure_at=None):
    """Private seed lane: no caller-selected identity, contract or graph facts."""
    _require_zhanaozen_system_authority(workspace, principal)
    return _materialize_projection_core(
        workspace, uuid.UUID(zhanaozen.PROJECTION_OPERATION_ID), zhanaozen.SYSTEM_ACTOR,
        receipt_contract=zhanaozen.SYSTEM_CONTRACT, system_principal=principal,
        inject_failure_at=inject_failure_at,
    )


def materialize_workspace_assessment_projection(
    workspace: ProjectWorkspace,
    operation_identity: uuid.UUID | str,
    human_principal: str,
    *,
    receipt_contract: str = PROJECTION_CONTRACT,
    canonical_request_sha256: str | None = None,
    inject_failure_at: str | None = None,
    **caller_projection_facts: Any,
) -> AssessmentProjectionResult:
    """Create one all-or-nothing projection or return its exact immutable replay."""

    operation_id = _exact_uuid(operation_identity, field="operation_identity")
    principal = str(human_principal).strip()
    if not principal:
        raise AssessmentProjectionError(
            "A HUMAN principal is required.", code="ASSESSMENT_PROJECTION_PRINCIPAL_REQUIRED"
        )
    if caller_projection_facts:
        raise AssessmentProjectionError(
            "Projection facts are server-derived and cannot be supplied by a caller.",
            code="ASSESSMENT_PROJECTION_CALLER_FACTS_FORBIDDEN",
        )
    if receipt_contract == PROJECTION_CONTRACT:
        if canonical_request_sha256 is not None:
            raise AssessmentProjectionError(
                "Standalone projection receipts do not accept a caller request hash.",
                code="ASSESSMENT_PROJECTION_CONTRACT_INVALID",
            )
        is_combined_receipt = False
    elif receipt_contract == WORKSPACE_CREATE_CONTRACT:
        canonical_request_sha256 = _canonical_request_sha256(canonical_request_sha256)
        is_combined_receipt = True
        if not transaction.get_connection().in_atomic_block:
            raise AssessmentProjectionError(
                "Combined workspace creation requires a caller-owned outer transaction.",
                code="ASSESSMENT_PROJECTION_COMBINED_TRANSACTION_REQUIRED",
            )
    else:
        raise AssessmentProjectionError(
            "The projection receipt contract is not recognized.",
            code="ASSESSMENT_PROJECTION_CONTRACT_INVALID",
        )
    return _materialize_projection_core(
        workspace, operation_id, principal, receipt_contract=receipt_contract,
        is_combined_receipt=is_combined_receipt,
        canonical_request_sha256=canonical_request_sha256,
        inject_failure_at=inject_failure_at,
    )


def _materialize_projection_core(
    workspace, operation_id, principal, *, receipt_contract,
    is_combined_receipt=False, canonical_request_sha256=None,
    inject_failure_at=None, system_principal=None,
):
    """Shared graph/locking/replay engine; public receipt semantics stay unchanged."""
    is_system = system_principal is not None
    with transaction.atomic():
        locked = (
            ProjectWorkspace.objects.select_for_update()
            .select_related("project", "definition_version")
            .get(pk=workspace.pk)
        )
        locked_definition = ProjectDefinitionVersion.objects.select_for_update().get(
            pk=locked.definition_version_id
        )
        locked.definition_version = locked_definition
        if is_system:
            _require_zhanaozen_system_authority(locked, system_principal)
        expected = _expected_projection(locked)
        request = _projection_request(
            locked,
            expected,
            operation_id=operation_id,
            principal=principal,
        )
        if is_system:
            request = _system_receipt_payload(locked, expected)["request"]
        request_sha256 = _sha256(request)
        operation_receipt = (
            AuditEvent.objects.select_for_update().filter(pk=operation_id).first()
            if is_combined_receipt
            else (AuditEvent.objects.select_for_update().filter(
                pk=zhanaozen.PROJECTION_RECEIPT_ID
            ).first() if is_system else None)
        )
        receipts = _projection_receipts(locked)
        if len(receipts) > 1:
            raise AssessmentProjectionConflict(
                "More than one projection receipt exists for this workspace."
            )
        receipt = receipts[0] if receipts else None
        actual = _actual_projection(locked)
        if receipt is not None:
            if receipt.entity_type != receipt_contract:
                raise AssessmentProjectionConflict(
                    "A different immutable projection receipt contract already exists for this workspace."
                )
            if is_combined_receipt:
                if not _combined_receipt_matches_materialize_request(
                    locked,
                    expected,
                    receipt,
                    operation_id=operation_id,
                    principal=principal,
                    canonical_request_sha256=canonical_request_sha256,
                ) or operation_receipt is None:
                    raise AssessmentProjectionConflict(
                        "A different immutable combined workspace receipt already exists."
                    )
            else:
                persisted = receipt.after if isinstance(receipt.after, Mapping) else {}
                if (
                    persisted.get("operation_id") != str(operation_id)
                    or persisted.get("request_sha256") != request_sha256
                ):
                    raise AssessmentProjectionConflict(
                        "A different immutable projection receipt already exists for this workspace."
                    )
            verification = verify_workspace_assessment_projection(locked)
            if not verification.complete:
                raise AssessmentProjectionConflict(verification.reason)
            return AssessmentProjectionResult(
                workspace=locked,
                receipt=receipt,
                projection_sha256=verification.projection_sha256 or "",
                replayed=True,
            )
        # The operation UUID is the combined AuditEvent primary key.  Classify a
        # foreign/malformed occupancy before any projection row or workspace
        # status can be written; a late occupancy is classified after the inner
        # receipt savepoint has rolled back.
        if (is_combined_receipt or is_system) and operation_receipt is not None:
            raise AssessmentProjectionConflict(
                "The combined operation UUID is already bound to another immutable audit event."
            )
        if (
            locked.assessment_projection_status
            != AssessmentProjectionStatus.NOT_PROVEN
            or locked.assessment_projection_sha256 is not None
            or any(
            actual[section]
            for section in ("actors", "analytical_elements", "actor_element_roles")
            )
        ):
            raise AssessmentProjectionConflict(
                "Existing canonical rows or non-initial evidence without an exact receipt cannot be repaired."
            )
        if actual["parameter_definitions"] and (
            actual["parameter_definitions"]
            != expected["parameter_definitions"]
        ):
            raise AssessmentProjectionConflict(
                "Existing definition-bound parameter snapshots have drifted and cannot be repaired."
            )
        if actual["parameter_definitions"]:
            # Definition-bound snapshots are shared by sibling workspaces, but
            # they are never sufficient evidence on their own.  Reuse is safe
            # only when another workspace on this exact definition already
            # proves the same immutable snapshots with its sole receipt.
            snapshot_is_receipt_proven = any(
                _definition_snapshot_is_receipt_proven(candidate, expected)
                for candidate in ProjectWorkspace.objects.select_related(
                    "project", "definition_version"
                )
                .filter(definition_version_id=locked.definition_version_id)
                .exclude(pk=locked.pk)
            )
            if not snapshot_is_receipt_proven:
                raise AssessmentProjectionConflict(
                    "Unreceipted definition snapshots cannot be adopted or repaired."
                )
        if is_combined_receipt:
            occurred_at = timezone.now()
            receipt_payload = _combined_receipt_payload(
                locked,
                expected,
                operation_id=operation_id,
                principal=principal,
                canonical_request_sha256=canonical_request_sha256,
                occurred_at=occurred_at,
            )
            try:
                # Insert immutable combined evidence before any projection/status
                # mutation.  The surrounding outer transaction makes receipt,
                # graph, and status one rollback unit for the workspace caller.
                with transaction.atomic():
                    receipt = AuditEvent.objects.create(
                        id=operation_id,
                        code=f"WORKSPACE-CREATE-PROJECTION-{operation_id}",
                        version="1.0.0",
                        project=locked.project,
                        workspace=locked,
                        scope=AuditScope.WORKSPACE,
                        action=AuditAction.CREATE,
                        actor_type=AuditActorType.HUMAN,
                        actor_identifier=principal,
                        entity_type=WORKSPACE_CREATE_CONTRACT,
                        entity_id=locked.pk,
                        before=None,
                        after=receipt_payload,
                        occurred_at=occurred_at,
                    )
            except (IntegrityError, ValidationError) as exc:
                # The inner savepoint has rolled back.  A row that appeared only
                # now proves a late identity collision; absence preserves an
                # unrelated model/database validation failure unchanged.
                late_operation_receipt = (
                    AuditEvent.objects.select_for_update().filter(pk=operation_id).first()
                )
                if late_operation_receipt is not None:
                    raise AssessmentProjectionConflict(
                        "The combined operation UUID collides with immutable audit evidence."
                    ) from exc
                raise
        with _canonical_assessment_projection_write("projection"):
            _materialize_expected(
                locked,
                expected,
                create_parameter_snapshots=not actual["parameter_definitions"],
                inject_failure_at=inject_failure_at,
            )
            if inject_failure_at == "before_receipt":
                raise AssessmentProjectionError("Injected failure before receipt.")
            if is_system:
                from domain.policies import FoundationAuditContext, _audit_after_payload
                context = FoundationAuditContext.for_principal_workspace(
                    workspace=locked, principal=system_principal,
                )
                payload = _system_receipt_payload(locked, expected)
                payload.pop("foundation_audit_context")
                row = zhanaozen.system_audit()
                row["after"] = _audit_after_payload(context, payload)
                receipt = AuditEvent.objects.create(**row)
            elif not is_combined_receipt:
                receipt_id = uuid.uuid4()
                receipt_payload = _projection_receipt_payload(
                    locked,
                    expected,
                    operation_id=operation_id,
                    principal=principal,
                    receipt_id=receipt_id,
                )
                receipt = AuditEvent.objects.create(
                    id=receipt_id,
                    code=f"ASSESSMENT-PROJECTION-{operation_id}",
                    version="1.0.0",
                    project=locked.project,
                    workspace=locked,
                    scope=AuditScope.WORKSPACE,
                    action=AuditAction.CREATE,
                    actor_type=AuditActorType.HUMAN,
                    actor_identifier=principal,
                    entity_type=PROJECTION_CONTRACT,
                    entity_id=locked.pk,
                    before=None,
                    after=receipt_payload,
                )
            locked.assessment_projection_status = AssessmentProjectionStatus.COMPLETE
            locked.assessment_projection_sha256 = expected["projection_sha256"]
            locked.save()
        return AssessmentProjectionResult(
            workspace=locked,
            receipt=receipt,
            projection_sha256=expected["projection_sha256"],
            replayed=False,
        )


def require_complete_workspace_assessment_projection(
    workspace: ProjectWorkspace,
) -> AssessmentProjectionVerification:
    """Read-only gate used by Foundation callers such as new TimeSlice creation."""

    verification = verify_workspace_assessment_projection(workspace)
    if not verification.complete:
        raise AssessmentProjectionConflict(verification.reason or "Workspace projection is not complete.")
    return verification
