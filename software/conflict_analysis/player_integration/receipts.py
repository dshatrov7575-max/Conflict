from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Mapping
from uuid import RFC_4122, UUID

from django.db import IntegrityError, transaction
from django.utils import timezone

from calculation import CalculationRun, CalculationSnapshot
from domain.enums import AuditAction, AuditActorType, AuditScope
from domain.models import AuditEvent
from domain.services.player_experiments import PlayerExperimentError, assessment_principal
from domain.services.player_workspaces import canonical_receipt_bytes

from .quality import (
    CalculationQuality,
    QUALITY_CONTRACT,
    QUALITY_CONTRACT_V2,
    summarize_quality,
    summarize_quality_for_contract,
)

RECEIPT_VERSION_V1 = "1.0.0"
RECEIPT_VERSION_V2 = "2.0.0"
RECEIPT_LIST_VERSION = "1.0.0"

BASELINE_RECEIPT_CONTRACT_V1 = "PLAYER_CALCULATION_RUN_RECEIPT_V1"
BASELINE_RECEIPT_CONTRACT_V2 = "PLAYER_CALCULATION_RUN_RECEIPT_V2"
# New baseline calculations use V2. Keep the conventional name for callers/tests.
BASELINE_RECEIPT_CONTRACT = BASELINE_RECEIPT_CONTRACT_V2
SCENARIO_RECEIPT_CONTRACT = "SCENARIO_CALCULATION_RUN_RECEIPT_V1"
RECEIPT_LIST_CONTRACT = "PLAYER_CALCULATION_RUN_RECEIPT_LIST_V1"
RECEIPT_CONTRACTS = frozenset({
    BASELINE_RECEIPT_CONTRACT_V1,
    BASELINE_RECEIPT_CONTRACT_V2,
    SCENARIO_RECEIPT_CONTRACT,
})
MAX_RECEIPTS = 200
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_PAYLOAD_KEYS = frozenset({
    "snapshot", "run", "ptns", "actors", "trace", "overrides", "values",
    "input_values", "parameter_values", "scenario_model", "snapshot_json",
})


@dataclass(frozen=True, slots=True)
class ReceiptResult:
    payload: Mapping[str, object]
    replayed: bool


def parse_operation_id(value: object) -> UUID:
    try:
        operation_id = UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400) from exc
    if (
        str(operation_id) != str(value)
        or operation_id.version != 4
        or operation_id.variant != RFC_4122
    ):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    return operation_id


def _sha(payload: object) -> str:
    return sha256(canonical_receipt_bytes(payload)).hexdigest()


def _forbidden_keys(payload: object) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _FORBIDDEN_PAYLOAD_KEYS:
                found.add(key)
            found.update(_forbidden_keys(value))
    elif isinstance(payload, list):
        for value in payload:
            found.update(_forbidden_keys(value))
    return found


def _validate_common_identity(*, principal, experiment, snapshot, run) -> None:
    workspace = experiment.workspace
    if (
        snapshot.experiment_id != str(experiment.pk)
        or snapshot.assessment_set_id != str(experiment.assessment_set_id)
        or snapshot.project_id != str(workspace.project_id)
        or snapshot.workspace_id != str(workspace.pk)
        or snapshot.definition_version_id != str(workspace.definition_version_id)
        or snapshot.definition_hash != workspace.definition_manifest_hash
        or run.snapshot_id != snapshot.id
        or (run.strategy_id, run.strategy_version) != (
            snapshot.strategy_id, snapshot.strategy_version,
        )
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")


def _receipt_core_v1(
    *,
    operation_id: UUID,
    contract: str,
    principal,
    experiment,
    snapshot: CalculationSnapshot,
    run: CalculationRun,
    quality: CalculationQuality,
    context_kind: str,
    occurred_at,
    scenario_id: str | None,
    baseline_snapshot_id: str | None,
    scenario_model_sha256: str | None,
) -> dict[str, object]:
    """Frozen V1 receipt bytes/semantics."""

    if context_kind not in {"BASELINE", "SCENARIO"}:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    if context_kind == "BASELINE" and contract != BASELINE_RECEIPT_CONTRACT_V1:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    if context_kind == "SCENARIO" and contract != SCENARIO_RECEIPT_CONTRACT:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    if context_kind == "BASELINE" and any(
        value is not None for value in (
            scenario_id, baseline_snapshot_id, scenario_model_sha256
        )
    ):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    if context_kind == "SCENARIO":
        try:
            scenario_uuid = UUID(str(scenario_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400) from exc
        if (
            str(scenario_uuid) != scenario_id
            or not isinstance(baseline_snapshot_id, str)
            or not baseline_snapshot_id.startswith("sha256:")
            or _SHA256.fullmatch(
                baseline_snapshot_id.removeprefix("sha256:")
            ) is None
            or not isinstance(scenario_model_sha256, str)
            or _SHA256.fullmatch(scenario_model_sha256) is None
        ):
            raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)

    _validate_common_identity(
        principal=principal, experiment=experiment, snapshot=snapshot, run=run
    )
    if quality != summarize_quality(snapshot, run):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    context = {
        "kind": context_kind,
        "scenario_id": scenario_id,
        "baseline_snapshot_id": baseline_snapshot_id,
        "scenario_model_sha256": scenario_model_sha256,
    }
    identity = {
        "contract": contract,
        "version": RECEIPT_VERSION_V1,
        "actor_identifier": principal.actor_identifier,
        "project_id": snapshot.project_id,
        "workspace_id": snapshot.workspace_id,
        "definition_version_id": snapshot.definition_version_id,
        "definition_manifest_hash": snapshot.definition_hash,
        "experiment_id": snapshot.experiment_id,
        "assessment_set_id": snapshot.assessment_set_id,
        "assessment_kind": experiment.assessment_set.kind,
        "expert_profile_id": str(experiment.expert_profile_id),
        "time_slice_id": snapshot.time_slice_id,
        "snapshot_id": snapshot.id,
        "input_digest": snapshot.input_digest,
        "strategy_id": run.strategy_id,
        "strategy_version": run.strategy_version,
        "result_digest": run.result_digest,
        "quality": quality.as_dict(),
        "context": context,
    }
    request_sha256 = _sha(identity)
    return {
        **identity,
        "operation_id": str(operation_id),
        "audit_event_id": str(operation_id),
        "actor_type": AuditActorType.HUMAN,
        "occurred_at": occurred_at.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "canonical_request_sha256": request_sha256,
        "payload_storage": {
            "snapshot_payload_stored": False,
            "run_payload_stored": False,
            "input_values_duplicated": False,
        },
    }


def _receipt_core_v2(
    *,
    operation_id: UUID,
    principal,
    experiment,
    snapshot: CalculationSnapshot,
    run: CalculationRun,
    quality: CalculationQuality,
    input_metadata: dict[str, object],
    client_request_sha256: str,
    companion_contract: str,
    companion_version: str,
    companion_id: UUID,
    occurred_at,
) -> dict[str, object]:
    """New baseline receipt. The row stays payload-light and binds its companion."""

    _validate_common_identity(
        principal=principal, experiment=experiment, snapshot=snapshot, run=run
    )
    if (
        quality.contract != QUALITY_CONTRACT_V2
        or quality != summarize_quality_for_contract(
            QUALITY_CONTRACT_V2, snapshot, run, input_metadata
        )
        or not isinstance(input_metadata.get("sha256"), str)
        or _SHA256.fullmatch(str(input_metadata["sha256"])) is None
        or _SHA256.fullmatch(client_request_sha256) is None
        or not companion_contract
        or not companion_version
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    context = {
        "kind": "BASELINE",
        "scenario_id": None,
        "baseline_snapshot_id": None,
        "scenario_model_sha256": None,
    }
    return {
        "contract": BASELINE_RECEIPT_CONTRACT_V2,
        "version": RECEIPT_VERSION_V2,
        "operation_id": str(operation_id),
        "audit_event_id": str(operation_id),
        "actor_type": AuditActorType.HUMAN,
        "actor_identifier": principal.actor_identifier,
        "project_id": snapshot.project_id,
        "workspace_id": snapshot.workspace_id,
        "definition_version_id": snapshot.definition_version_id,
        "definition_manifest_hash": snapshot.definition_hash,
        "experiment_id": snapshot.experiment_id,
        "assessment_set_id": snapshot.assessment_set_id,
        "assessment_kind": experiment.assessment_set.kind,
        "expert_profile_id": str(experiment.expert_profile_id),
        "time_slice_id": snapshot.time_slice_id,
        "snapshot_id": snapshot.id,
        "input_digest": snapshot.input_digest,
        "input_metadata_sha256": str(input_metadata["sha256"]),
        "strategy_id": run.strategy_id,
        "strategy_version": run.strategy_version,
        "result_digest": run.result_digest,
        "quality_contract": quality.contract,
        "quality_sha256": _sha(quality.as_dict()),
        "client_request_sha256": client_request_sha256,
        "companion": {
            "contract": companion_contract,
            "version": companion_version,
            "id": str(companion_id),
        },
        "context": context,
        "occurred_at": occurred_at.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "payload_storage": {
            "receipt_snapshot_payload_stored": False,
            "receipt_run_payload_stored": False,
            "receipt_input_values_duplicated": False,
            "companion_replay_payload_required": True,
        },
    }


def _validate_row_common(
    row: AuditEvent,
    payload: dict[str, object],
    *,
    expected_version: str,
) -> dict[str, bool]:
    return {
        "operation_id": payload.get("operation_id") == str(row.pk),
        "audit_event_id": payload.get("audit_event_id") == str(row.pk),
        "actor_identifier": payload.get("actor_identifier") == row.actor_identifier,
        "actor_type": payload.get("actor_type") == row.actor_type,
        "project_id": payload.get("project_id") == str(row.project_id),
        "workspace_id": payload.get("workspace_id") == str(row.workspace_id),
        "assessment_set_id": payload.get("assessment_set_id") == str(row.assessment_set_id),
        "occurred_at": payload.get("occurred_at") == row.occurred_at.isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"),
        "version": row.version == expected_version == payload.get("version"),
        "code": row.code == f"CALC-RUN-{row.pk}",
        "scope": row.scope == AuditScope.WORKSPACE,
        "action": row.action == AuditAction.CREATE,
        "before": row.before is None,
        "parameter_value": row.parameter_value_id is None,
        "entity_id": str(row.entity_id) == str(row.pk),
        "forbidden_keys": not _forbidden_keys(payload),
    }


def _validate_persisted_v1(row: AuditEvent, payload: dict[str, object]) -> dict[str, object]:
    receipt_sha256 = payload.get("receipt_sha256")
    core = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    checks = {
        "contract": payload.get("contract") in {
            BASELINE_RECEIPT_CONTRACT_V1, SCENARIO_RECEIPT_CONTRACT
        },
        "entity_type": row.entity_type == payload.get("contract"),
        **_validate_row_common(row, payload, expected_version=RECEIPT_VERSION_V1),
        "receipt_sha256": receipt_sha256 == _sha(core),
        "payload_storage": payload.get("payload_storage") == {
            "snapshot_payload_stored": False,
            "run_payload_stored": False,
            "input_values_duplicated": False,
        },
    }
    if not all(checks.values()):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    return payload


def _validate_persisted_v2(row: AuditEvent, payload: dict[str, object]) -> dict[str, object]:
    receipt_sha256 = payload.get("receipt_sha256")
    core = {key: value for key, value in payload.items() if key != "receipt_sha256"}
    companion = payload.get("companion")
    checks = {
        "contract": payload.get("contract") == BASELINE_RECEIPT_CONTRACT_V2,
        "entity_type": row.entity_type == BASELINE_RECEIPT_CONTRACT_V2,
        **_validate_row_common(row, payload, expected_version=RECEIPT_VERSION_V2),
        "receipt_sha256": receipt_sha256 == _sha(core),
        "client_request_sha256": (
            isinstance(payload.get("client_request_sha256"), str)
            and _SHA256.fullmatch(str(payload["client_request_sha256"])) is not None
        ),
        "input_metadata_sha256": (
            isinstance(payload.get("input_metadata_sha256"), str)
            and _SHA256.fullmatch(str(payload["input_metadata_sha256"])) is not None
        ),
        "quality_contract": payload.get("quality_contract") == QUALITY_CONTRACT_V2,
        "quality_sha256": (
            isinstance(payload.get("quality_sha256"), str)
            and _SHA256.fullmatch(str(payload["quality_sha256"])) is not None
        ),
        "companion": (
            isinstance(companion, dict)
            and set(companion) == {"contract", "version", "id"}
            and isinstance(companion.get("contract"), str)
            and bool(companion.get("contract"))
            and isinstance(companion.get("version"), str)
            and bool(companion.get("version"))
        ),
        "payload_storage": payload.get("payload_storage") == {
            "receipt_snapshot_payload_stored": False,
            "receipt_run_payload_stored": False,
            "receipt_input_values_duplicated": False,
            "companion_replay_payload_required": True,
        },
    }
    try:
        if isinstance(companion, dict):
            UUID(str(companion.get("id")))
        else:
            checks["companion"] = False
    except (ValueError, TypeError, AttributeError):
        checks["companion"] = False
    if not all(checks.values()):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    return payload


def _validate_persisted(row: AuditEvent) -> dict[str, object]:
    payload = row.after
    if not isinstance(payload, dict):
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    contract = payload.get("contract")
    if contract in {BASELINE_RECEIPT_CONTRACT_V1, SCENARIO_RECEIPT_CONTRACT}:
        return _validate_persisted_v1(row, payload)
    if contract == BASELINE_RECEIPT_CONTRACT_V2:
        return _validate_persisted_v2(row, payload)
    raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")


def _existing_or_conflict_v1(
    *,
    row: AuditEvent,
    contract: str,
    principal,
    experiment,
    expected_request_sha256: str,
) -> ReceiptResult:
    if (
        row.entity_type != contract
        or row.actor_identifier != principal.actor_identifier
        or row.project_id != experiment.workspace.project_id
        or row.workspace_id != experiment.workspace_id
        or row.assessment_set_id != experiment.assessment_set_id
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
    payload = _validate_persisted(row)
    if payload.get("canonical_request_sha256") != expected_request_sha256:
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
    return ReceiptResult(payload, True)


def _existing_or_conflict_v2(
    *,
    row: AuditEvent,
    principal,
    experiment,
    expected_client_request_sha256: str,
) -> ReceiptResult:
    if (
        row.entity_type != BASELINE_RECEIPT_CONTRACT_V2
        or row.actor_identifier != principal.actor_identifier
        or row.project_id != experiment.workspace.project_id
        or row.workspace_id != experiment.workspace_id
        or row.assessment_set_id != experiment.assessment_set_id
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
    payload = _validate_persisted(row)
    if payload.get("client_request_sha256") != expected_client_request_sha256:
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
    return ReceiptResult(payload, True)


@transaction.atomic
def record_calculation_receipt(
    *,
    user,
    experiment,
    snapshot: CalculationSnapshot,
    run: CalculationRun,
    quality: CalculationQuality,
    operation_id: object,
    context_kind: str = "BASELINE",
    scenario_id: str | None = None,
    baseline_snapshot_id: str | None = None,
    scenario_model_sha256: str | None = None,
) -> ReceiptResult:
    """Persist/replay the frozen V1 receipt contract.

    New baseline calculations use record_baseline_receipt_v2(). This function
    remains for scenario V1 and exact legacy baseline replay compatibility.
    """

    operation_uuid = parse_operation_id(operation_id)
    principal = assessment_principal(user)
    contract = (
        BASELINE_RECEIPT_CONTRACT_V1
        if context_kind == "BASELINE"
        else SCENARIO_RECEIPT_CONTRACT
    )
    now = timezone.now()
    core = _receipt_core_v1(
        operation_id=operation_uuid,
        contract=contract,
        principal=principal,
        experiment=experiment,
        snapshot=snapshot,
        run=run,
        quality=quality,
        context_kind=context_kind,
        occurred_at=now,
        scenario_id=scenario_id,
        baseline_snapshot_id=baseline_snapshot_id,
        scenario_model_sha256=scenario_model_sha256,
    )
    request_sha256 = str(core["canonical_request_sha256"])
    existing = AuditEvent.objects.select_for_update().filter(pk=operation_uuid).first()
    if existing is not None:
        return _existing_or_conflict_v1(
            row=existing,
            contract=contract,
            principal=principal,
            experiment=experiment,
            expected_request_sha256=request_sha256,
        )
    payload = {**core, "receipt_sha256": _sha(core)}
    try:
        with transaction.atomic():
            row = AuditEvent.objects.create(
                id=operation_uuid,
                code=f"CALC-RUN-{operation_uuid}",
                version=RECEIPT_VERSION_V1,
                project_id=experiment.workspace.project_id,
                workspace_id=experiment.workspace_id,
                definition_version=None,
                scope=AuditScope.WORKSPACE,
                assessment_set_id=experiment.assessment_set_id,
                parameter_value=None,
                action=AuditAction.CREATE,
                actor_type=AuditActorType.HUMAN,
                actor_identifier=principal.actor_identifier,
                entity_type=contract,
                entity_id=operation_uuid,
                before=None,
                after=payload,
                occurred_at=now,
            )
    except IntegrityError:
        row = AuditEvent.objects.select_for_update().filter(pk=operation_uuid).first()
        if row is None:
            raise
        return _existing_or_conflict_v1(
            row=row,
            contract=contract,
            principal=principal,
            experiment=experiment,
            expected_request_sha256=request_sha256,
        )
    return ReceiptResult(_validate_persisted(row), False)


@transaction.atomic
def record_baseline_receipt_v2(
    *,
    user,
    experiment,
    snapshot: CalculationSnapshot,
    run: CalculationRun,
    quality: CalculationQuality,
    input_metadata: dict[str, object],
    operation_id: object,
    client_request_sha256: str,
    companion_contract: str,
    companion_version: str,
    companion_id: UUID,
) -> ReceiptResult:
    """Create the new companion-required baseline receipt.

    If operation_id already belongs to a legacy V1 baseline receipt, preserve
    legacy exact-current replay semantics instead of rewriting history.
    """

    operation_uuid = parse_operation_id(operation_id)
    principal = assessment_principal(user)
    now = timezone.now()
    existing = AuditEvent.objects.select_for_update().filter(pk=operation_uuid).first()
    if existing is not None:
        if existing.entity_type == BASELINE_RECEIPT_CONTRACT_V2:
            return _existing_or_conflict_v2(
                row=existing,
                principal=principal,
                experiment=experiment,
                expected_client_request_sha256=client_request_sha256,
            )
        if existing.entity_type == BASELINE_RECEIPT_CONTRACT_V1:
            legacy_quality = summarize_quality(snapshot, run)
            legacy_core = _receipt_core_v1(
                operation_id=operation_uuid,
                contract=BASELINE_RECEIPT_CONTRACT_V1,
                principal=principal,
                experiment=experiment,
                snapshot=snapshot,
                run=run,
                quality=legacy_quality,
                context_kind="BASELINE",
                occurred_at=now,
                scenario_id=None,
                baseline_snapshot_id=None,
                scenario_model_sha256=None,
            )
            return _existing_or_conflict_v1(
                row=existing,
                contract=BASELINE_RECEIPT_CONTRACT_V1,
                principal=principal,
                experiment=experiment,
                expected_request_sha256=str(legacy_core["canonical_request_sha256"]),
            )
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")

    core = _receipt_core_v2(
        operation_id=operation_uuid,
        principal=principal,
        experiment=experiment,
        snapshot=snapshot,
        run=run,
        quality=quality,
        input_metadata=input_metadata,
        client_request_sha256=client_request_sha256,
        companion_contract=companion_contract,
        companion_version=companion_version,
        companion_id=companion_id,
        occurred_at=now,
    )
    payload = {**core, "receipt_sha256": _sha(core)}
    try:
        with transaction.atomic():
            row = AuditEvent.objects.create(
                id=operation_uuid,
                code=f"CALC-RUN-{operation_uuid}",
                version=RECEIPT_VERSION_V2,
                project_id=experiment.workspace.project_id,
                workspace_id=experiment.workspace_id,
                definition_version=None,
                scope=AuditScope.WORKSPACE,
                assessment_set_id=experiment.assessment_set_id,
                parameter_value=None,
                action=AuditAction.CREATE,
                actor_type=AuditActorType.HUMAN,
                actor_identifier=principal.actor_identifier,
                entity_type=BASELINE_RECEIPT_CONTRACT_V2,
                entity_id=operation_uuid,
                before=None,
                after=payload,
                occurred_at=now,
            )
    except IntegrityError:
        row = AuditEvent.objects.select_for_update().filter(pk=operation_uuid).first()
        if row is None:
            raise
        if row.entity_type == BASELINE_RECEIPT_CONTRACT_V2:
            return _existing_or_conflict_v2(
                row=row,
                principal=principal,
                experiment=experiment,
                expected_client_request_sha256=client_request_sha256,
            )
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
    return ReceiptResult(_validate_persisted(row), False)


def list_calculation_receipts(*, user, experiment) -> dict[str, object]:
    assessment_principal(user)
    rows = AuditEvent.objects.filter(
        workspace_id=experiment.workspace_id,
        assessment_set_id=experiment.assessment_set_id,
        entity_type__in=RECEIPT_CONTRACTS,
    ).order_by("-occurred_at", "-created_at", "pk")
    total = rows.count()
    payloads = []
    for row in rows[:MAX_RECEIPTS]:
        payload = _validate_persisted(row)
        if payload.get("experiment_id") != str(experiment.pk):
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        payloads.append(payload)
    return {
        "contract": RECEIPT_LIST_CONTRACT,
        "version": RECEIPT_LIST_VERSION,
        "experiment_id": str(experiment.pk),
        "total": total,
        "limit": MAX_RECEIPTS,
        "truncated": total > MAX_RECEIPTS,
        "receipts": payloads,
    }


def get_calculation_receipt(*, user, experiment, operation_id: object) -> dict[str, object]:
    assessment_principal(user)
    operation_uuid = parse_operation_id(operation_id)
    row = AuditEvent.objects.filter(
        pk=operation_uuid,
        workspace_id=experiment.workspace_id,
        assessment_set_id=experiment.assessment_set_id,
        entity_type__in=RECEIPT_CONTRACTS,
    ).first()
    if row is None:
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    payload = _validate_persisted(row)
    if payload.get("experiment_id") != str(experiment.pk):
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    return payload
