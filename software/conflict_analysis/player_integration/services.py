"""Authorization/orchestration plus durable digest-only run receipts."""
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
from .receipts import ReceiptResult, parse_operation_id, record_calculation_receipt
from .replay_artifacts import (
    canonical_calculation_request_sha256,
    record_replay_artifact,
    replay_baseline_if_present,
)




def _input_metadata(snapshot: CalculationSnapshot) -> dict[str, object]:
    """Preserve non-arithmetic Foundation metadata without changing snapshot 1.0.0."""

    rows: list[dict[str, object]] = []
    source_ids: set[UUID] = set()

    def append(kind, value, *, ptn_id, actor_id=None):
        try:
            source_uuid = UUID(str(value.source_id))
        except (ValueError, TypeError, AttributeError):
            source_uuid = None
        if source_uuid is not None and kind in {"POS", "KVS"}:
            source_ids.add(source_uuid)
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

    stored = {
        str(row.pk): row
        for row in ParameterValue.objects.filter(pk__in=source_ids).only(
            "id", "version", "status", "temporal_status"
        )
    }
    for row in rows:
        value = stored.get(str(row["source_id"]))
        if value is None:
            continue
        if value.version != row["source_version"] or value.status != row["value_status"]:
            raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        row["temporal_status"] = value.temporal_status

    rows.sort(key=lambda item: (
        str(item["ptn_id"]), str(item["actor_id"] or ""), str(item["kind"]), str(item["source_id"])
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
        workspace_id=experiment.workspace_id, project_id=experiment.workspace.project_id,
    ).order_by("order", "pk"))


@transaction.atomic
def capture_for_player(*, user, experiment_id, time_slice_id, beta_weights=None,
                       include_metadata=False):
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
        pk=time_id, workspace_id=experiment.workspace_id,
        project_id=experiment.workspace.project_id,
    ).exists():
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    snapshot = capture_snapshot(
        experiment_id=experiment.pk, time_slice_id=time_id, beta_weights=beta_weights,
    )
    if include_metadata:
        return experiment, snapshot, _input_metadata(snapshot)
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

    def as_dict(self, *, receipt: ReceiptResult | None = None):
        # Core serialization owns numeric precision, nulls, trace and warnings.
        payload = {
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
            "input_metadata": self.input_metadata,
            "quality": self.quality.as_dict(),
            "result_digest": self.run.result_digest,
        }
        if receipt is None:
            return payload
        return {
            **payload,
            "contract": "PLAYER_CALCULATION_RESULT_V3",
            "receipt": dict(receipt.payload),
            "receipt_replayed": receipt.replayed,
        }


def calculate_experiment(*, user, experiment_id, time_slice_id,
                         beta_weights: BetaWeights | None = None) -> ResultView:
    """Pure composition path used by Python callers and offline verification."""

    experiment, snapshot, input_metadata = capture_for_player(
        user=user, experiment_id=experiment_id, time_slice_id=time_slice_id,
        beta_weights=beta_weights, include_metadata=True,
    )
    return ResultView(
        experiment.name, experiment.status, experiment.assessment_set.kind,
        str(experiment.expert_profile_id), experiment.expert_profile.display_name,
        snapshot, calculate(snapshot), input_metadata,
    )


@transaction.atomic
def calculate_and_record_experiment(
    *, user, experiment_id, time_slice_id, operation_id,
    beta_weights: BetaWeights | None = None,
) -> tuple[ResultView, ReceiptResult]:
    """Calculate once; exact idempotent retries replay the immutable first result."""

    experiment = open_experiment(user=user, experiment_id=experiment_id)
    try:
        time_id = UUID(str(time_slice_id))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400) from exc
    if not TimeSlice.objects.filter(
        pk=time_id, workspace_id=experiment.workspace_id,
        project_id=experiment.workspace.project_id,
    ).exists():
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    if beta_weights is not None and (
        beta_weights.experiment_id != str(experiment.pk)
        or beta_weights.time_slice_id != str(time_id)
    ):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)

    operation_uuid = parse_operation_id(operation_id)
    request_sha256 = canonical_calculation_request_sha256(
        experiment_id=experiment.pk,
        time_slice_id=time_id,
        beta_weights=beta_weights,
    )
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

    experiment, snapshot, input_metadata = capture_for_player(
        user=user, experiment_id=experiment_id, time_slice_id=time_id,
        beta_weights=beta_weights, include_metadata=True,
    )
    view = ResultView(
        experiment.name, experiment.status, experiment.assessment_set.kind,
        str(experiment.expert_profile_id), experiment.expert_profile.display_name,
        snapshot, calculate(snapshot), input_metadata,
    )
    # Preserve the V1 receipt contract byte-for-byte. The V2 temporal quality and
    # full replay material live in the immutable companion artifact.
    receipt = record_calculation_receipt(
        user=user,
        experiment=experiment,
        snapshot=view.snapshot,
        run=view.run,
        quality=summarize_quality(view.snapshot, view.run),
        operation_id=operation_uuid,
        context_kind="BASELINE",
    )
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
