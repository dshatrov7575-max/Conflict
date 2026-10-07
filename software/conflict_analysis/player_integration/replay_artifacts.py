"""Immutable companion replay artifacts for baseline calculations.

CalculationSnapshot / CalculationRun 1.0.0 bytes are never changed here.
New baseline receipts use a V2 companion-required contract; legacy V1 receipts
remain readable and are never silently upgraded.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import IntegrityError, transaction

from calculation import CalculationRun, CalculationSnapshot, calculate
from calculation.contracts import decimal_text
from calculation.foundation import BetaWeights
from domain.enums import (
    AssessmentTemporalStatus,
    AuditAction,
    AuditActorType,
    AuditScope,
)
from domain.models import AuditEvent
from domain.services.player_experiments import PlayerExperimentError, assessment_principal
from domain.services.player_workspaces import canonical_receipt_bytes

from .quality import (
    CalculationQuality,
    QUALITY_CONTRACT_V2,
    summarize_quality_for_contract,
)
from .receipts import (
    BASELINE_RECEIPT_CONTRACT_V1,
    BASELINE_RECEIPT_CONTRACT_V2,
    ReceiptResult,
    _validate_persisted,
)

REPLAY_ARTIFACT_CONTRACT_V1 = "PLAYER_CALCULATION_REPLAY_ARTIFACT_V1"
REPLAY_ARTIFACT_CONTRACT_V2 = "PLAYER_CALCULATION_REPLAY_ARTIFACT_V2"
REPLAY_ARTIFACT_CONTRACT = REPLAY_ARTIFACT_CONTRACT_V2
REPLAY_ARTIFACT_VERSION_V1 = "1.0.0"
REPLAY_ARTIFACT_VERSION_V2 = "2.0.0"
REPLAY_ARTIFACT_VERSION = REPLAY_ARTIFACT_VERSION_V2
REQUEST_CONTRACT = "PLAYER_CALCULATION_REQUEST_IDENTITY_V1"

_TEMPORAL_STATUSES = frozenset(AssessmentTemporalStatus.values)
_METADATA_KEYS = frozenset({
    "kind", "ptn_id", "actor_id", "source_id", "source_version",
    "value_status", "temporal_status",
})


@dataclass(frozen=True, slots=True)
class ReplayedCalculation:
    snapshot: CalculationSnapshot
    run: CalculationRun
    quality: CalculationQuality
    input_metadata: dict[str, object]
    receipt: ReceiptResult
    experiment_name: str
    experiment_status: str
    expert_name: str


def _sha(payload: object) -> str:
    return sha256(canonical_receipt_bytes(payload)).hexdigest()


def replay_artifact_id(operation_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"conflict-analysis:calculation-replay:{operation_id}")


def _input_payload(value) -> dict[str, object]:
    return {
        "status": value.status,
        "value": decimal_text(value.value) if value.known else None,
        "source_id": value.source_id,
        "source_version": value.source_version,
    }


def canonical_calculation_request_sha256(
    *,
    experiment_id: object,
    time_slice_id: object,
    beta_weights: BetaWeights | None,
) -> str:
    """Hash caller-controlled calculation semantics, never current DB values."""

    weights = None
    if beta_weights is not None:
        weights = {
            "experiment_id": beta_weights.experiment_id,
            "time_slice_id": beta_weights.time_slice_id,
            "rgu": [
                {"identity": identity, **_input_payload(value)}
                for identity, value in beta_weights.rgu
            ],
            "kvptn": [
                {"identity": identity, **_input_payload(value)}
                for identity, value in beta_weights.kvptn
            ],
        }
    return _sha({
        "contract": REQUEST_CONTRACT,
        "experiment_id": str(experiment_id),
        "time_slice_id": str(time_slice_id),
        "beta_weights": weights,
    })


def _snapshot_metadata_rows(snapshot: CalculationSnapshot) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ptn in snapshot.ptns:
        rows.append({
            "kind": "KVPTN",
            "ptn_id": ptn.ptn_id,
            "actor_id": None,
            "source_id": ptn.kvptn.source_id,
            "source_version": ptn.kvptn.source_version,
            "value_status": ptn.kvptn.status,
        })
        for actor in ptn.actors:
            rows.extend((
                {
                    "kind": "POS",
                    "ptn_id": ptn.ptn_id,
                    "actor_id": actor.actor_id,
                    "source_id": actor.attitude.source_id,
                    "source_version": actor.attitude.source_version,
                    "value_status": actor.attitude.status,
                },
                {
                    "kind": "KVS",
                    "ptn_id": ptn.ptn_id,
                    "actor_id": actor.actor_id,
                    "source_id": actor.kvs.source_id,
                    "source_version": actor.kvs.source_version,
                    "value_status": actor.kvs.status,
                },
                {
                    "kind": "RGU",
                    "ptn_id": ptn.ptn_id,
                    "actor_id": actor.actor_id,
                    "source_id": actor.rgu.source_id,
                    "source_version": actor.rgu.source_version,
                    "value_status": actor.rgu.status,
                },
            ))
    rows.sort(key=lambda item: (
        str(item["ptn_id"]),
        str(item["actor_id"] or ""),
        str(item["kind"]),
        str(item["source_id"]),
    ))
    return rows


def _is_uuid(value: object) -> bool:
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _validate_input_metadata(
    payload: object,
    snapshot: CalculationSnapshot,
) -> dict[str, object]:
    """Validate hash and exact one-to-one semantic binding to a snapshot."""

    if not isinstance(payload, dict):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    envelope = dict(payload)
    digest = envelope.pop("sha256", None)
    inputs = envelope.get("inputs")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or envelope.get("contract") != "PLAYER_INPUT_METADATA_ENVELOPE_V1"
        or envelope.get("snapshot_id") != snapshot.id
        or _sha(envelope) != digest
        or not isinstance(inputs, list)
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    expected = _snapshot_metadata_rows(snapshot)
    if len(inputs) != len(expected):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    normalized: list[dict[str, object]] = []
    for item in inputs:
        if not isinstance(item, dict) or set(item) != _METADATA_KEYS:
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        row = dict(item)
        kind = row.get("kind")
        temporal = row.get("temporal_status")
        source_id = str(row.get("source_id"))
        if kind in {"RGU", "KVPTN"}:
            if temporal is not None:
                raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        elif kind in {"POS", "KVS"}:
            if source_id == "ABSENT" or source_id.startswith("SCENARIO:"):
                if temporal is not None:
                    raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
            elif _is_uuid(source_id):
                if temporal not in _TEMPORAL_STATUSES:
                    raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
            else:
                raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        else:
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        normalized.append(row)

    normalized.sort(key=lambda item: (
        str(item["ptn_id"]),
        str(item["actor_id"] or ""),
        str(item["kind"]),
        str(item["source_id"]),
    ))
    for actual, target in zip(normalized, expected):
        for key in (
            "kind", "ptn_id", "actor_id", "source_id",
            "source_version", "value_status",
        ):
            if actual.get(key) != target.get(key):
                raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    if len({
        (
            row["kind"], row["ptn_id"], row["actor_id"], row["source_id"]
        )
        for row in normalized
    }) != len(normalized):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    return payload


def _validate_artifact(
    row: AuditEvent,
    *,
    receipt_row: AuditEvent,
    principal,
    experiment,
    request_sha256: str,
) -> ReplayedCalculation:
    payload = row.after
    if not isinstance(payload, dict):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    receipt_payload = _validate_persisted(receipt_row)
    receipt_contract = receipt_payload.get("contract")
    artifact_contract = payload.get("contract")
    if receipt_contract == BASELINE_RECEIPT_CONTRACT_V2:
        expected_artifact_contract = REPLAY_ARTIFACT_CONTRACT_V2
        expected_artifact_version = REPLAY_ARTIFACT_VERSION_V2
        request_field = "client_request_sha256"
    elif receipt_contract == BASELINE_RECEIPT_CONTRACT_V1:
        expected_artifact_contract = REPLAY_ARTIFACT_CONTRACT_V1
        expected_artifact_version = REPLAY_ARTIFACT_VERSION_V1
        request_field = "canonical_request_sha256"
    else:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    artifact_sha256 = payload.get("artifact_sha256")
    core = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    checks = {
        "contract": artifact_contract == expected_artifact_contract,
        "version": (
            row.version == expected_artifact_version == payload.get("version")
        ),
        "entity_type": row.entity_type == expected_artifact_contract,
        "artifact_pk": row.pk == replay_artifact_id(receipt_row.pk),
        "entity_id": str(row.entity_id) == str(receipt_row.pk),
        "code": row.code == f"CALC-REPLAY-{receipt_row.pk}",
        "action": row.action == AuditAction.CREATE,
        "scope": row.scope == AuditScope.WORKSPACE,
        "before": row.before is None,
        "parameter_value": row.parameter_value_id is None,
        "actor_identifier": row.actor_identifier == principal.actor_identifier,
        "actor_type": row.actor_type == AuditActorType.HUMAN,
        "project": row.project_id == experiment.workspace.project_id,
        "workspace": row.workspace_id == experiment.workspace_id,
        "assessment_set": row.assessment_set_id == experiment.assessment_set_id,
        "operation": payload.get("operation_id") == str(receipt_row.pk),
        "receipt_contract": payload.get("receipt_contract") in {
            None, receipt_contract
        },
        "receipt_sha": (
            payload.get("receipt_sha256") == receipt_payload.get("receipt_sha256")
        ),
        "request_sha": payload.get(request_field) == request_sha256,
        "artifact_sha": (
            isinstance(artifact_sha256, str) and _sha(core) == artifact_sha256
        ),
    }
    if receipt_contract == BASELINE_RECEIPT_CONTRACT_V2:
        companion = receipt_payload.get("companion")
        checks.update({
            "receipt_companion": (
                isinstance(companion, dict)
                and companion.get("contract") == expected_artifact_contract
                and companion.get("version") == expected_artifact_version
                and companion.get("id") == str(row.pk)
            ),
        })
    if not all(checks.values()):
        if checks.get("contract") and checks.get("operation") and not checks.get("request_sha"):
            raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    try:
        snapshot = CalculationSnapshot.from_json(str(payload["snapshot_json"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT") from exc
    run = calculate(snapshot)
    if (
        snapshot.id != receipt_payload.get("snapshot_id")
        or snapshot.input_digest != receipt_payload.get("input_digest")
        or run.result_digest != receipt_payload.get("result_digest")
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    input_metadata = _validate_input_metadata(payload.get("input_metadata"), snapshot)
    quality_payload = payload.get("quality")
    if not isinstance(quality_payload, dict):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    quality_contract = quality_payload.get("contract")
    try:
        quality = summarize_quality_for_contract(
            str(quality_contract), snapshot, run,
            input_metadata if quality_contract == QUALITY_CONTRACT_V2 else None,
        )
    except ValueError as exc:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT") from exc
    if quality.as_dict() != quality_payload:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    if receipt_contract == BASELINE_RECEIPT_CONTRACT_V2 and (
        receipt_payload.get("input_metadata_sha256") != input_metadata.get("sha256")
        or receipt_payload.get("quality_contract") != quality.contract
        or receipt_payload.get("quality_sha256") != _sha(quality.as_dict())
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    lane = payload.get("lane_display")
    if not isinstance(lane, dict) or set(lane) != {
        "experiment_name", "experiment_status", "expert_name"
    }:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    return ReplayedCalculation(
        snapshot=snapshot,
        run=run,
        quality=quality,
        input_metadata=input_metadata,
        receipt=ReceiptResult(receipt_payload, True),
        experiment_name=str(lane["experiment_name"]),
        experiment_status=str(lane["experiment_status"]),
        expert_name=str(lane["expert_name"]),
    )


def replay_baseline_if_present(
    *,
    user,
    experiment,
    operation_id: UUID,
    request_sha256: str,
) -> ReplayedCalculation | None:
    """Replay under the caller's already-held Project serialization lock."""

    principal = assessment_principal(user)
    receipt_row = AuditEvent.objects.select_for_update().filter(
        pk=operation_id
    ).first()
    artifact_row = AuditEvent.objects.select_for_update().filter(
        pk=replay_artifact_id(operation_id)
    ).first()

    if receipt_row is None and artifact_row is None:
        return None
    if receipt_row is None:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    if receipt_row.entity_type == BASELINE_RECEIPT_CONTRACT_V2:
        if artifact_row is None:
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        if (
            receipt_row.actor_identifier != principal.actor_identifier
            or receipt_row.project_id != experiment.workspace.project_id
            or receipt_row.workspace_id != experiment.workspace_id
            or receipt_row.assessment_set_id != experiment.assessment_set_id
        ):
            raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
        return _validate_artifact(
            artifact_row,
            receipt_row=receipt_row,
            principal=principal,
            experiment=experiment,
            request_sha256=request_sha256,
        )

    if receipt_row.entity_type == BASELINE_RECEIPT_CONTRACT_V1:
        if artifact_row is None:
            # Legacy V1 operation: preserve exact-current replay semantics.
            return None
        if artifact_row.entity_type != REPLAY_ARTIFACT_CONTRACT_V1:
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        if (
            receipt_row.actor_identifier != principal.actor_identifier
            or receipt_row.project_id != experiment.workspace.project_id
            or receipt_row.workspace_id != experiment.workspace_id
            or receipt_row.assessment_set_id != experiment.assessment_set_id
        ):
            raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
        return _validate_artifact(
            artifact_row,
            receipt_row=receipt_row,
            principal=principal,
            experiment=experiment,
            request_sha256=request_sha256,
        )

    raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")


@transaction.atomic
def record_replay_artifact(
    *,
    user,
    experiment,
    snapshot: CalculationSnapshot,
    input_metadata: dict[str, object],
    quality: CalculationQuality,
    receipt: ReceiptResult,
    request_sha256: str,
    experiment_name: str,
    experiment_status: str,
    expert_name: str,
) -> dict[str, object]:
    """Append or validate the required V2 companion for a baseline V2 receipt."""

    principal = assessment_principal(user)
    try:
        operation_id = UUID(str(receipt.payload["operation_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT") from exc

    if receipt.payload.get("contract") != BASELINE_RECEIPT_CONTRACT_V2:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    artifact_id = replay_artifact_id(operation_id)
    companion = receipt.payload.get("companion")
    if (
        not isinstance(companion, dict)
        or companion.get("contract") != REPLAY_ARTIFACT_CONTRACT_V2
        or companion.get("version") != REPLAY_ARTIFACT_VERSION_V2
        or companion.get("id") != str(artifact_id)
        or receipt.payload.get("snapshot_id") != snapshot.id
        or receipt.payload.get("input_digest") != snapshot.input_digest
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    _validate_input_metadata(input_metadata, snapshot)
    try:
        expected_quality = summarize_quality_for_contract(
            quality.contract, snapshot, calculate(snapshot), input_metadata
        )
    except ValueError as exc:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT") from exc
    if quality != expected_quality:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    core = {
        "contract": REPLAY_ARTIFACT_CONTRACT_V2,
        "version": REPLAY_ARTIFACT_VERSION_V2,
        "operation_id": str(operation_id),
        "receipt_contract": BASELINE_RECEIPT_CONTRACT_V2,
        "receipt_sha256": receipt.payload["receipt_sha256"],
        "client_request_sha256": request_sha256,
        "snapshot_json": snapshot.to_json(),
        "input_metadata": input_metadata,
        "quality": quality.as_dict(),
        "lane_display": {
            "experiment_name": experiment_name,
            "experiment_status": experiment_status,
            "expert_name": expert_name,
        },
    }
    payload = {**core, "artifact_sha256": _sha(core)}

    existing = AuditEvent.objects.select_for_update().filter(pk=artifact_id).first()
    if existing is not None:
        return _validate_artifact(
            existing,
            receipt_row=AuditEvent.objects.get(pk=operation_id),
            principal=principal,
            experiment=experiment,
            request_sha256=request_sha256,
        ).input_metadata

    try:
        with transaction.atomic():
            row = AuditEvent.objects.create(
                id=artifact_id,
                code=f"CALC-REPLAY-{operation_id}",
                version=REPLAY_ARTIFACT_VERSION_V2,
                project_id=experiment.workspace.project_id,
                workspace_id=experiment.workspace_id,
                definition_version=None,
                scope=AuditScope.WORKSPACE,
                assessment_set_id=experiment.assessment_set_id,
                parameter_value=None,
                action=AuditAction.CREATE,
                actor_type=AuditActorType.HUMAN,
                actor_identifier=principal.actor_identifier,
                entity_type=REPLAY_ARTIFACT_CONTRACT_V2,
                entity_id=operation_id,
                before=None,
                after=payload,
            )
    except IntegrityError:
        row = AuditEvent.objects.select_for_update().filter(pk=artifact_id).first()
        if row is None:
            raise
        _validate_artifact(
            row,
            receipt_row=AuditEvent.objects.get(pk=operation_id),
            principal=principal,
            experiment=experiment,
            request_sha256=request_sha256,
        )
        return row.after
    _validate_artifact(
        row,
        receipt_row=AuditEvent.objects.get(pk=operation_id),
        principal=principal,
        experiment=experiment,
        request_sha256=request_sha256,
    )
    return payload
