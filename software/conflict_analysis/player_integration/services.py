"""Authorization and orchestration only: no formulas or persistence writes."""
from dataclasses import dataclass
import json
from uuid import UUID

from django.db import transaction

from calculation import CalculationRun, CalculationSnapshot, calculate
from calculation.foundation import BetaWeights, capture_snapshot
from domain.models import Project, TimeSlice
from domain.services.player_experiments import PlayerExperimentError, admit_assessment_scope


def open_experiment(*, user, experiment_id):
    return admit_assessment_scope(user=user, kind="experiment", identity=experiment_id)


def time_slices(*, user, experiment_id):
    experiment = open_experiment(user=user, experiment_id=experiment_id)
    return experiment, list(TimeSlice.objects.filter(
        workspace_id=experiment.workspace_id, project_id=experiment.workspace.project_id,
    ).order_by("order", "pk"))


@transaction.atomic
def capture_for_player(*, user, experiment_id, time_slice_id, beta_weights=None):
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

    def as_dict(self):
        # Core serialization owns numeric precision, nulls, trace and warnings.
        return {
            "contract": "PLAYER_CALCULATION_RESULT_V1",
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
            "result_digest": self.run.result_digest,
        }


def calculate_experiment(*, user, experiment_id, time_slice_id,
                         beta_weights: BetaWeights | None = None) -> ResultView:
    experiment, snapshot = capture_for_player(
        user=user, experiment_id=experiment_id, time_slice_id=time_slice_id,
        beta_weights=beta_weights,
    )
    return ResultView(
        experiment.name, experiment.status, experiment.assessment_set.kind,
        str(experiment.expert_profile_id), experiment.expert_profile.display_name,
        snapshot, calculate(snapshot),
    )
