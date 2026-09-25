"""Read one G8 assessment lane. Never import, write, or derive beta weights."""
from dataclasses import dataclass

from django.db import transaction

from domain.enums import ExperimentType, TargetType
from domain.models import (
    ActorElementAssessment, ActorElementRole, Experiment, ParameterDefinition,
    ParameterValue, Project, TimeSlice,
)
from domain.services.player_projection import require_complete_workspace_assessment_projection

from .contracts import (
    ActorInput, CalculationInputError, CalculationSnapshot, InputValue, PtnInput, _identity, _weight,
)


@dataclass(frozen=True, slots=True)
class BetaWeights:
    """Explicit beta-only values, scoped to one experiment and TimeSlice.

    Keys are projected Actor/AnalyticalElement primary keys. InputValue sources
    identify the caller's beta data. These values never become ParameterValue.
    Omitted keys are UNKNOWN; there is no import-receipt or Power fallback.
    """

    experiment_id: str
    time_slice_id: str
    rgu: tuple[tuple[str, InputValue], ...] = ()
    kvptn: tuple[tuple[str, InputValue], ...] = ()

    def __post_init__(self):
        _identity(self.experiment_id)
        _identity(self.time_slice_id)
        for name in ("rgu", "kvptn"):
            rows = tuple((key, value) for key, value in getattr(self, name))
            for key, value in rows:
                _identity(key)
                _weight(value)
                if value.known and value.source_id == "ABSENT":
                    raise CalculationInputError("Explicit beta weights require a source identity.")
            if len(dict(rows)) != len(rows):
                raise CalculationInputError("Duplicate beta weight identity.")
            object.__setattr__(self, name, tuple(sorted(rows)))


def capture_snapshot(*, experiment_id, time_slice_id, beta_weights: BetaWeights | None = None):
    """Capture current terminal ParameterValues in one existing Foundation lane.

    Internal service, not an HTTP authorization boundary. The caller must apply
    its Foundation access policy before invoking this reader. Shared Project
    locking serializes capture with G8's guarded writes on PostgreSQL.
    """
    with transaction.atomic():
        initial = Experiment.objects.select_related("workspace").get(pk=experiment_id)
        Project.objects.select_for_update().get(pk=initial.workspace.project_id)
        experiment = Experiment.objects.select_related(
            "workspace__definition_version", "assessment_set", "expert_profile",
        ).get(pk=experiment_id)
        workspace = experiment.workspace
        time_slice = TimeSlice.objects.get(pk=time_slice_id, workspace=workspace)
        if (experiment.experiment_type != ExperimentType.ASSESSMENT or
                experiment.assessment_set.workspace_id != workspace.pk or
                experiment.assessment_set.project_id != workspace.project_id or
                experiment.expert_profile.kind != experiment.assessment_set.kind or
                experiment.assessment_set.kind not in {"HUMAN", "AI"}):
            raise CalculationInputError("Calculation requires one exact HUMAN/AI assessment lane.")
        if (time_slice.project_id != workspace.project_id or
                workspace.definition_manifest_hash != workspace.definition_version.manifest_hash):
            raise CalculationInputError("Snapshot definition/time/project pin mismatch.")
        require_complete_workspace_assessment_projection(workspace)
        definitions = {row.code: row for row in ParameterDefinition.objects.filter(
            project_id=workspace.project_id, definition_version_id=workspace.definition_version_id,
            code__in=("POS", "SAL"),
        )}
        if set(definitions) != {"POS", "SAL"} or any(
            row.target_type != TargetType.ACTOR_ELEMENT_ASSESSMENT or
            row.scale_min != (-10 if code == "POS" else 0) or row.scale_max != 10
            for code, row in definitions.items()
        ):
            raise CalculationInputError("Beta requires exact G8 POS -10..10 and SAL 0..10 definitions.")
        pos_roles = set(definitions["POS"].applicability.get("actor_element_role_ids", []))
        sal_roles = set(definitions["SAL"].applicability.get("actor_element_role_ids", []))
        if not pos_roles or pos_roles != sal_roles:
            raise CalculationInputError("POS/SAL must bind the same explicit topology.")
        roles = list(ActorElementRole.objects.filter(
            workspace=workspace, source_manifest_entity_id__in=pos_roles,
        ).select_related("actor", "element").order_by("pk"))
        pairs = {(row.actor_id, row.element_id): row for row in roles}
        if len(pairs) != len(roles) or len(roles) != len(pos_roles):
            raise CalculationInputError("Ambiguous or incomplete actor/PTN topology.")
        actor_ids = {str(row.actor_id) for row in roles}
        ptn_ids = {str(row.element_id) for row in roles}
        if beta_weights is None:
            beta_weights = BetaWeights(str(experiment.pk), str(time_slice.pk))
        if (beta_weights.experiment_id, beta_weights.time_slice_id) != (str(experiment.pk), str(time_slice.pk)):
            raise CalculationInputError("Beta weights belong to another experiment or TimeSlice.")
        rgu, kvptn = dict(beta_weights.rgu), dict(beta_weights.kvptn)
        if set(rgu) - actor_ids or set(kvptn) - ptn_ids:
            raise CalculationInputError("Beta weight identity lies outside the selected topology.")

        assessments = {}
        for row in ActorElementAssessment.objects.filter(
            experiment=experiment, time_slice=time_slice, successor__isnull=True,
        ):
            pair = (row.actor_id, row.element_id)
            if (row.workspace_id != workspace.pk or row.assessment_set_id != experiment.assessment_set_id
                    or pair not in pairs or pair in assessments):
                raise CalculationInputError("Assessment identity is ambiguous or outside the selected lane.")
            assessments[pair] = row

        values = {}
        # Select terminal values across the entire assessment revision lineage:
        # POS can still refer to an earlier header after a SAL correction.
        for value in ParameterValue.objects.filter(
            assessment_set_id=experiment.assessment_set_id, time_slice=time_slice,
            parameter_definition_id__in=[row.pk for row in definitions.values()],
            successor__isnull=True,
        ).select_related("actor_element_assessment", "parameter_definition"):
            header = value.actor_element_assessment
            if (header is None or header.experiment_id != experiment.pk or
                    header.workspace_id != workspace.pk or header.time_slice_id != time_slice.pk or
                    header.assessment_set_id != experiment.assessment_set_id or
                    value.workspace_id != workspace.pk or value.project_id != workspace.project_id or
                    value.target_type != TargetType.ACTOR_ELEMENT_ASSESSMENT or value.target_id != header.pk):
                raise CalculationInputError("ParameterValue is outside the selected assessment lane.")
            pair = (header.actor_id, header.element_id)
            key = (*pair, value.parameter_definition.code)
            if pair not in pairs or pair not in assessments or key in values:
                raise CalculationInputError("ParameterValue has no unique current topology/assessment identity.")
            values[key] = InputValue(value.status, value.value, str(value.pk), value.version)

        ptns = {}
        for pair, role in pairs.items():
            actor_id, ptn_id = str(role.actor_id), str(role.element_id)
            header = assessments.get(pair)
            ptns.setdefault(ptn_id, []).append(ActorInput(
                actor_id, str(role.pk), str(header.pk) if header else "ABSENT",
                values.get((*pair, "POS"), InputValue()),
                values.get((*pair, "SAL"), InputValue()), rgu.get(actor_id, InputValue()),
            ))
        return CalculationSnapshot(
            experiment_id=str(experiment.pk), assessment_set_id=str(experiment.assessment_set_id),
            project_id=str(workspace.project_id), time_slice_id=str(time_slice.pk),
            workspace_id=str(workspace.pk), definition_version_id=str(workspace.definition_version_id),
            definition_hash=workspace.definition_manifest_hash, time_slice_version=time_slice.version,
            cutoff_date=time_slice.cutoff_date.isoformat(),
            ptns=tuple(PtnInput(ptn_id, kvptn.get(ptn_id, InputValue()), tuple(rows))
                       for ptn_id, rows in ptns.items()),
        )
