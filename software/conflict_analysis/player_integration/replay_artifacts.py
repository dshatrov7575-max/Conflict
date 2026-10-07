"""Immutable companion artifacts for exact baseline calculation replay.

This module does not change CalculationSnapshot / CalculationRun 1.0.0 bytes.
It persists the already-returned snapshot plus non-arithmetic metadata in a
separate append-only AuditEvent linked to the calculation receipt operation.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import IntegrityError, transaction

from calculation import CalculationRun, CalculationSnapshot, calculate
from calculation.contracts import decimal_text
from calculation.foundation import BetaWeights
from domain.enums import AuditAction, AuditActorType, AuditScope
from domain.models import AuditEvent
from domain.services.player_experiments import PlayerExperimentError, assessment_principal
from domain.services.player_workspaces import canonical_receipt_bytes

from .quality import CalculationQuality, summarize_quality
from .receipts import (
    BASELINE_RECEIPT_CONTRACT,
    ReceiptResult,
    _validate_persisted,
)

REPLAY_ARTIFACT_CONTRACT = "PLAYER_CALCULATION_REPLAY_ARTIFACT_V1"
REPLAY_ARTIFACT_VERSION = "1.0.0"
REQUEST_CONTRACT = "PLAYER_CALCULATION_REQUEST_IDENTITY_V1"


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


def _artifact_id(operation_id: UUID) -> UUID:
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
    """Hash caller-controlled calculation semantics, never mutable current DB values."""

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


def _validate_input_metadata(payload: object, snapshot_id: str) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    envelope = dict(payload)
    digest = envelope.pop("sha256", None)
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or envelope.get("contract") != "PLAYER_INPUT_METADATA_ENVELOPE_V1"
        or envelope.get("snapshot_id") != snapshot_id
        or _sha(envelope) != digest
        or not isinstance(envelope.get("inputs"), list)
    ):
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
    artifact_sha256 = payload.get("artifact_sha256")
    core = {key: value for key, value in payload.items() if key != "artifact_sha256"}
    receipt_payload = _validate_persisted(receipt_row)
    checks = {
        "contract": payload.get("contract") == REPLAY_ARTIFACT_CONTRACT,
        "version": row.version == REPLAY_ARTIFACT_VERSION == payload.get("version"),
        "entity_type": row.entity_type == REPLAY_ARTIFACT_CONTRACT,
        "artifact_pk": row.pk == _artifact_id(receipt_row.pk),
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
        "receipt_sha": payload.get("receipt_sha256") == receipt_payload.get("receipt_sha256"),
        "request_sha": payload.get("canonical_request_sha256") == request_sha256,
        "artifact_sha": isinstance(artifact_sha256, str) and _sha(core) == artifact_sha256,
    }
    if not all(checks.values()):
        if checks["contract"] and checks["operation"] and not checks["request_sha"]:
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
    input_metadata = _validate_input_metadata(payload.get("input_metadata"), snapshot.id)
    quality = summarize_quality(snapshot, run, input_metadata)
    if quality.as_dict() != payload.get("quality"):
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
    """Return the original immutable result before any mutable source recapture."""

    principal = assessment_principal(user)
    receipt_row = AuditEvent.objects.select_for_update().filter(pk=operation_id).first()
    artifact_row = AuditEvent.objects.select_for_update().filter(pk=_artifact_id(operation_id)).first()
    if receipt_row is None and artifact_row is None:
        return None
    if receipt_row is None or artifact_row is None:
        # A receipt without a companion is a legacy V1 operation. Let the legacy
        # path handle exact-current replay without rewriting history.
        if receipt_row is not None and artifact_row is None:
            return None
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    if receipt_row.entity_type != BASELINE_RECEIPT_CONTRACT:
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
    return _validate_artifact(
        artifact_row,
        receipt_row=receipt_row,
        principal=principal,
        experiment=experiment,
        request_sha256=request_sha256,
    )


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
    """Append or replay the exact companion artifact for one V1 receipt."""

    principal = assessment_principal(user)
    try:
        operation_id = UUID(str(receipt.payload["operation_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT") from exc
    if (
        receipt.payload.get("contract") != BASELINE_RECEIPT_CONTRACT
        or receipt.payload.get("snapshot_id") != snapshot.id
        or receipt.payload.get("input_digest") != snapshot.input_digest
        or quality != summarize_quality(snapshot, calculate(snapshot), input_metadata)
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    _validate_input_metadata(input_metadata, snapshot.id)
    core = {
        "contract": REPLAY_ARTIFACT_CONTRACT,
        "version": REPLAY_ARTIFACT_VERSION,
        "operation_id": str(operation_id),
        "receipt_sha256": receipt.payload["receipt_sha256"],
        "canonical_request_sha256": request_sha256,
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
    artifact_id = _artifact_id(operation_id)
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
                version=REPLAY_ARTIFACT_VERSION,
                project_id=experiment.workspace.project_id,
                workspace_id=experiment.workspace_id,
                definition_version=None,
                scope=AuditScope.WORKSPACE,
                assessment_set_id=experiment.assessment_set_id,
                parameter_value=None,
                action=AuditAction.CREATE,
                actor_type=AuditActorType.HUMAN,
                actor_identifier=principal.actor_identifier,
                entity_type=REPLAY_ARTIFACT_CONTRACT,
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
