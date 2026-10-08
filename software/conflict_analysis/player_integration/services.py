from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import UUID

from django.db import transaction

from calculation import CalculationRun, CalculationSnapshot, calculate
from calculation.foundation import BetaWeights, capture_snapshot
from domain.models import ParameterValue, Project, TimeSlice
from domain.services.player_experiments import PlayerExperimentError, admit_assessment_scope
from domain.services.player_workspaces import canonical_receipt_bytes

from .quality import CalculationQuality, summarize_quality
from .receipts import (
    BASELINE_RECEIPT_CONTRACT_V1,
    BASELINE_RECEIPT_CONTRACT_V2,
    ReceiptResult,
    parse_operation_id,
    record_baseline_receipt_v2,
)
from .replay_artifacts import (
    REPLAY_ARTIFACT_CONTRACT_V2,
    REPLAY_ARTIFACT_VERSION_V2,
    canonical_calculation_request_sha256,
    record_replay_artifact,
    replay_artifact_id,
    replay_baseline_if_present,
)


def input_metadata_for_snapshot(snapshot: CalculationSnapshot) -> dict[str, object]:
    """Bind non-arithmetic Foundation metadata to the exact snapshot inputs."""

    rows: list[dict[str, object]] = []
    source_ids: set[UUID] = set()

    def append(kind, value, *, ptn_id, actor_id=None):
        source_id = str(value.source_id)
        try:
            source_uuid = UUID(source_id)
        except (ValueError, TypeError, AttributeError):
            source_uuid = None
        if kind in {"POS", "KVS"}:
            if source_uuid is not None:
                source_ids.add(source_uuid)
            elif source_id != "ABSENT" and not source_id.startswith("SCENARIO:"):
                raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        rows.append({
            "kind": kind,
            "ptn_id": ptn_id,
            "actor_id": actor_id,
            "source_id": value.source_id,
            "source_version": value.source_version,
            "value_status": value.status,
            "temporal_status": None,
        })

    for ptn in snapshot.ptns:
        append("KVPTN", ptn.kvptn, ptn_id=ptn.ptn_id)
        for actor in ptn.actors:
            append("POS", actor.attitude, ptn_id=ptn.ptn_id, actor_id=actor.actor_id)
            append("KVS", actor.kvs, ptn_id=ptn.ptn_id, actor_id=actor.actor_id)
            append("RGU", actor.rgu, ptn_id=ptn.ptn_id, actor_id=actor.actor_id)

    stored_rows = ParameterValue.objects.filter(
        pk__in=source_ids,
        project_id=snapshot.project_id,
        workspace_id=snapshot.workspace_id,
        time_slice_id=snapshot.time_slice_id,
        assessment_set_id=snapshot.assessment_set_id,
        actor_element_assessment__experiment_id=snapshot.experiment_id,
    ).select_related("parameter_definition", "actor_element_assessment")
    stored = {str(row.pk): row for row in stored_rows}
    if set(stored) != {str(identity) for identity in source_ids}:
        raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")

    for row in rows:
        value = stored.get(str(row["source_id"]))
        if value is None:
            # ABSENT and SCENARIO:* POS/KVS, plus all design/transient weights.
            continue
        expected_code = "POS" if row["kind"] == "POS" else "SAL"
        assessment = value.actor_element_assessment
        if (
            row["kind"] not in {"POS", "KVS"}
            or value.parameter_definition.code != expected_code
            or assessment is None
            or str(assessment.actor_id) != str(row["actor_id"])
            or str(assessment.element_id) != str(row["ptn_id"])
            or value.version != row["source_version"]
            or value.status != row["value_status"]
        ):
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        row["temporal_status"] = value.temporal_status

    rows.sort(key=lambda item: (
        str(item["ptn_id"]),
        str(item["actor_id"] or ""),
        str(item["kind"]),
        str(item["source_id"]),
    ))
    core = {
        "contract": "PLAYER_INPUT_METADATA_ENVELOPE_V1",
        "snapshot_id": snapshot.id,
        "inputs": rows,
    }
    return {
        **core,
        "sha256": sha256(canonical_receipt_bytes(core)).hexdigest(),
    }


def open_experiment(*, user, experiment_id):
    return admit_assessment_scope(user=user, kind="experiment", identity=experiment_id)


def time_slices(*, user, experiment_id):
    experiment = open_experiment(user=user, experiment_id=experiment_id)
    return experiment, list(TimeSlice.objects.filter(
        workspace_id=experiment.workspace_id,
        project_id=experiment.workspace.project_id,
    ).order_by("order", "pk"))


@transaction.atomic
def capture_for_player(
    *,
    user,
    experiment_id,
    time_slice_id,
    beta_weights=None,
    include_metadata=False,
):
    # Admission precedes Core reads. Re-admit under the same Project lock used
    # by G8 mutations and Core capture, so lane metadata and inputs agree.
    experiment = open_experiment(user=user, experiment_id=experiment_id)
    Project.objects.select_for_update().get(pk=experiment.workspace.project_id)
    experiment = open_experiment(user=user, experiment_id=experiment_id)
    try:
        time_id = UUID(str(time_slice_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400) from exc
    if not TimeSlice.objects.filter(
        pk=time_id,
        workspace_id=experiment.workspace_id,
        project_id=experiment.workspace.project_id,
    ).exists():
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    snapshot = capture_snapshot(
        experiment_id=experiment.pk,
        time_slice_id=time_id,
        beta_weights=beta_weights,
    )
    if include_metadata:
        return experiment, snapshot, input_metadata_for_snapshot(snapshot)
    return experiment, snapshot


@dataclass(frozen=True, slots=True)
class ResultView:
    """An ephemeral result bound to one admitted HUMAN or AI lane."""

    experiment_name: str
    experiment_status: str
    assessment_kind: str
    expert_profile_id: str
    expert_name: str
    snapshot: CalculationSnapshot
    run: CalculationRun
    input_metadata: dict[str, object]

    @property
    def quality(self) -> CalculationQuality:
        return summarize_quality(self.snapshot, self.run, self.input_metadata)

    @property
    def legacy_quality(self) -> CalculationQuality:
        return summarize_quality(self.snapshot, self.run)

    def _legacy_payload(self) -> dict[str, object]:
        # Frozen PLAYER_CALCULATION_RESULT_V2 bytes/shape.
        return {
            "contract": "PLAYER_CALCULATION_RESULT_V2",
            "lane": {
                "experiment_id": self.snapshot.experiment_id,
                "experiment_name": self.experiment_name,
                "experiment_status": self.experiment_status,
                "assessment_kind": self.assessment_kind,
                "assessment_set_id": self.snapshot.assessment_set_id,
                "expert_profile_id": self.expert_profile_id,
                "expert_name": self.expert_name,
            },
            "snapshot": json.loads(self.snapshot.to_json()),
            "run": json.loads(self.run.to_json()),
            "quality": self.legacy_quality.as_dict(),
            "result_digest": self.run.result_digest,
        }

    def as_dict(self, *, receipt: ReceiptResult | None = None):
        if receipt is None:
            return self._legacy_payload()
        if receipt.payload.get("contract") == BASELINE_RECEIPT_CONTRACT_V1:
            return {
                **self._legacy_payload(),
                "contract": "PLAYER_CALCULATION_RESULT_V3",
                "receipt": dict(receipt.payload),
                "receipt_replayed": receipt.replayed,
            }
        if receipt.payload.get("contract") != BASELINE_RECEIPT_CONTRACT_V2:
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        return {
            "contract": "PLAYER_CALCULATION_RESULT_V4",
            "lane": {
                "experiment_id": self.snapshot.experiment_id,
                "experiment_name": self.experiment_name,
                "experiment_status": self.experiment_status,
                "assessment_kind": self.assessment_kind,
                "assessment_set_id": self.snapshot.assessment_set_id,
                "expert_profile_id": self.expert_profile_id,
                "expert_name": self.expert_name,
            },
            "snapshot": json.loads(self.snapshot.to_json()),
            "run": json.loads(self.run.to_json()),
            "input_metadata": self.input_metadata,
            "quality": self.quality.as_dict(),
            "result_digest": self.run.result_digest,
            "receipt": dict(receipt.payload),
            "receipt_replayed": receipt.replayed,
        }


def calculate_experiment(
    *,
    user,
    experiment_id,
    time_slice_id,
    beta_weights: BetaWeights | None = None,
) -> ResultView:
    """Pure composition path used by Python callers and offline verification."""

    experiment, snapshot, input_metadata = capture_for_player(
        user=user,
        experiment_id=experiment_id,
        time_slice_id=time_slice_id,
        beta_weights=beta_weights,
        include_metadata=True,
    )
    return ResultView(
        experiment.name,
        experiment.status,
        experiment.assessment_set.kind,
        str(experiment.expert_profile_id),
        experiment.expert_profile.display_name,
        snapshot,
        calculate(snapshot),
        input_metadata,
    )


@transaction.atomic
def calculate_and_record_experiment(
    *,
    user,
    experiment_id,
    time_slice_id,
    operation_id,
    beta_weights: BetaWeights | None = None,
) -> tuple[ResultView, ReceiptResult]:
    """Serialize mutable capture and exact replay behind one Project lock."""

    # Current authorization is checked before any operation replay.
    experiment = open_experiment(user=user, experiment_id=experiment_id)
    try:
        time_id = UUID(str(time_slice_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400) from exc
    operation_uuid = parse_operation_id(operation_id)

    # Caller-controlled request identity is stable across source corrections.
    request_sha256 = canonical_calculation_request_sha256(
        experiment_id=experiment.pk,
        time_slice_id=time_id,
        beta_weights=beta_weights,
    )

    # Global lock order: Project first, then receipt/artifact AuditEvent rows.
    Project.objects.select_for_update().get(pk=experiment.workspace.project_id)
    experiment = open_experiment(user=user, experiment_id=experiment_id)

    replayed = replay_baseline_if_present(
        user=user,
        experiment=experiment,
        operation_id=operation_uuid,
        request_sha256=request_sha256,
    )
    if replayed is not None:
        receipt_payload = replayed.receipt.payload
        view = ResultView(
            replayed.experiment_name,
            replayed.experiment_status,
            str(receipt_payload["assessment_kind"]),
            str(receipt_payload["expert_profile_id"]),
            replayed.expert_name,
            replayed.snapshot,
            replayed.run,
            replayed.input_metadata,
        )
        return view, replayed.receipt

    # Fresh path: route existence/scope is authoritative before body binding.
    if not TimeSlice.objects.filter(
        pk=time_id,
        workspace_id=experiment.workspace_id,
        project_id=experiment.workspace.project_id,
    ).exists():
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    if beta_weights is not None and (
        beta_weights.experiment_id != str(experiment.pk)
        or beta_weights.time_slice_id != str(time_id)
    ):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)

    # capture_for_player re-enters the same transaction/Project lock; no new
    # lock order is introduced and the mutable source cannot pass this barrier.
    experiment, snapshot, input_metadata = capture_for_player(
        user=user,
        experiment_id=experiment_id,
        time_slice_id=time_id,
        beta_weights=beta_weights,
        include_metadata=True,
    )
    view = ResultView(
        experiment.name,
        experiment.status,
        experiment.assessment_set.kind,
        str(experiment.expert_profile_id),
        experiment.expert_profile.display_name,
        snapshot,
        calculate(snapshot),
        input_metadata,
    )

    artifact_id = replay_artifact_id(operation_uuid)
    receipt = record_baseline_receipt_v2(
        user=user,
        experiment=experiment,
        snapshot=view.snapshot,
        run=view.run,
        quality=view.quality,
        input_metadata=view.input_metadata,
        operation_id=operation_uuid,
        client_request_sha256=request_sha256,
        companion_contract=REPLAY_ARTIFACT_CONTRACT_V2,
        companion_version=REPLAY_ARTIFACT_VERSION_V2,
        companion_id=artifact_id,
    )

    # A legacy V1 operation is never upgraded or retrofitted with a companion.
    if receipt.payload.get("contract") == BASELINE_RECEIPT_CONTRACT_V2:
        record_replay_artifact(
            user=user,
            experiment=experiment,
            snapshot=view.snapshot,
            input_metadata=view.input_metadata,
            quality=view.quality,
            receipt=receipt,
            request_sha256=request_sha256,
            experiment_name=view.experiment_name,
            experiment_status=view.experiment_status,
            expert_name=view.expert_name,
        )
    return view, receipt
