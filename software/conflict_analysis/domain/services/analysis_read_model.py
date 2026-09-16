"""Method-safe POS/SAL read model. No writes, repairs or aggregate scores."""
from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from domain.enums import AssessmentKind, ExperimentStatus, ExperimentType, TargetType
from domain.models import (
    Actor,
    ActorElementRole,
    AnalyticalElement,
    Experiment,
    ParameterDefinition,
    ParameterValue,
    TimeSlice,
)
from domain.services.analysis_admission import (
    AnalysisWorkspace,
    admit_analysis_workspace,
    exact_uuid,
)
from domain.services.analysis_contracts import (
    ABSENT_STATUSES,
    COMPARISON_CONTRACT,
    CONTEXT_CONTRACT,
    MATRIX_CONTRACT,
    METHOD_STATE,
    PRESENT_STATUSES,
    TIMELINE_CONTRACT,
    AnalysisError,
    decimal_text,
    json_number,
    require_parameter_code,
    snapshot,
)

EXPERIMENT_CONTRACT = "FOUNDATION_PLAYER_EXPERIMENT_V1"
CONFIDENCE = frozenset({"LOW", "MEDIUM", "HIGH", "UNKNOWN"})
MAX_TIMELINE_POINTS = 5000
MAX_MATRIX_CELLS = 400
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_SAFE_COLORS = {
    AssessmentKind.HUMAN: "#255cca",
    AssessmentKind.AI: "#d05a35",
}


def _context(user, project_id, workspace_id):
    return admit_analysis_workspace(
        user=user,
        project_id=project_id,
        workspace_id=workspace_id,
    )


def _experiment(c: AnalysisWorkspace, identity) -> Experiment:
    row = (
        Experiment.objects.select_related("expert_profile", "assessment_set")
        .filter(
            pk=exact_uuid(identity),
            workspace=c.workspace,
            experiment_type=ExperimentType.ASSESSMENT,
            metadata__contract=EXPERIMENT_CONTRACT,
            expert_profile__kind__in=(AssessmentKind.HUMAN, AssessmentKind.AI),
            expert_profile__workspace=c.workspace,
            assessment_set__workspace=c.workspace,
            assessment_set__project=c.project,
        )
        .exclude(status=ExperimentStatus.ARCHIVED)
        .first()
    )
    if row is None:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    return row


def _definitions(c: AnalysisWorkspace) -> dict[str, ParameterDefinition]:
    rows = list(
        ParameterDefinition.objects.filter(
            project=c.project,
            definition_version=c.workspace.definition_version,
            source_manifest_parameter_id__isnull=False,
            code__in=("POS", "SAL"),
        ).order_by("code", "pk")
    )
    result = {row.code: row for row in rows}
    expected = {"POS": ("-10", "10"), "SAL": ("0", "10")}
    if len(rows) != 2 or set(result) != set(expected):
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    for code, row in result.items():
        if (
            row.target_type != TargetType.ACTOR_ELEMENT_ASSESSMENT
            or (decimal_text(row.scale_min), decimal_text(row.scale_max))
            != expected[code]
            or not isinstance(row.allowed_statuses, list)
            or not isinstance(row.applicability, dict)
        ):
            raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    return result


def _actor(c: AnalysisWorkspace, code: object) -> Actor:
    if not isinstance(code, str) or not code or len(code) > 128:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    row = Actor.objects.filter(
        workspace=c.workspace,
        code=code,
        source_manifest_entity_id__isnull=False,
    ).first()
    if row is None:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    return row


def _element(c: AnalysisWorkspace, code: object) -> AnalyticalElement:
    if not isinstance(code, str) or not code or len(code) > 128:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    row = AnalyticalElement.objects.filter(
        workspace=c.workspace,
        code=code,
        source_manifest_entity_id__isnull=False,
    ).first()
    if row is None:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    return row


def _role_map(
    c: AnalysisWorkspace,
    actors: list[Actor],
    elements: list[AnalyticalElement],
    definition: ParameterDefinition,
) -> dict[tuple[object, object], ActorElementRole]:
    cell_count = len(actors) * len(elements)
    if cell_count > MAX_MATRIX_CELLS:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    expected_pairs = {
        (actor.pk, element.pk)
        for actor in actors
        for element in elements
    }
    allowed = {
        str(item)
        for item in definition.applicability.get("actor_element_role_ids", [])
    }
    rows = list(
        ActorElementRole.objects.filter(
            workspace=c.workspace,
            actor__in=actors,
            element__in=elements,
            source_manifest_entity_id__isnull=False,
        ).select_related("actor", "element")
    )
    result: dict[tuple[object, object], ActorElementRole] = {}
    for row in rows:
        key = (row.actor_id, row.element_id)
        if key in result or str(row.source_manifest_entity_id) not in allowed:
            raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
        result[key] = row
    if set(result) != expected_pairs:
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    return result


def _role(c, actor, element, definition):
    _role_map(c, [actor], [element], definition)


def _safe_color(row: Experiment) -> str:
    raw = row.color
    if isinstance(raw, str) and _COLOR.fullmatch(raw):
        return raw.lower()
    return _SAFE_COLORS.get(row.expert_profile.kind, "#596b7c")


def _experiment_dto(row: Experiment) -> dict[str, Any]:
    return {
        "id": str(row.pk),
        "name": row.name,
        "status": row.status,
        "color": _safe_color(row),
        "order": row.order,
        "kind": row.expert_profile.kind,
        "expert_name": row.expert_profile.display_name,
        "assessment_set_id": str(row.assessment_set_id),
        "method_version": row.method_version,
    }


def _validate_value(row: ParameterValue, definition: ParameterDefinition):
    if row.status in ABSENT_STATUSES:
        if row.value is not None:
            raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
        return None
    if row.status not in PRESENT_STATUSES or row.value is None:
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    value = json_number(row.value)
    number = Decimal(str(value))
    if (
        definition.scale_min is not None
        and number < definition.scale_min
        or definition.scale_max is not None
        and number > definition.scale_max
    ):
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    return value


def _validate_terminal_row(
    c: AnalysisWorkspace,
    experiment: Experiment,
    actor: Actor,
    element: AnalyticalElement,
    definition: ParameterDefinition,
    row: ParameterValue,
) -> None:
    assessment = row.actor_element_assessment
    if (
        row.target_id != row.actor_element_assessment_id
        or row.project_id != c.project.pk
        or row.workspace_id != c.workspace.pk
        or row.assessment_set_id != experiment.assessment_set_id
        or assessment.workspace_id != c.workspace.pk
        or assessment.experiment_id != experiment.pk
        or assessment.assessment_set_id != experiment.assessment_set_id
        or assessment.actor_id != actor.pk
        or assessment.element_id != element.pk
        or assessment.time_slice_id != row.time_slice_id
        or row.time_slice.workspace_id != c.workspace.pk
        or row.time_slice.project_id != c.project.pk
        or row.parameter_definition_id != definition.pk
        or row.status not in definition.allowed_statuses
    ):
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    _validate_value(row, definition)


def _terminal(c, experiment, actor, element, definition):
    rows = list(
        ParameterValue.objects.filter(
            project=c.project,
            workspace=c.workspace,
            assessment_set=experiment.assessment_set,
            actor_element_assessment__workspace=c.workspace,
            actor_element_assessment__experiment=experiment,
            actor_element_assessment__assessment_set=experiment.assessment_set,
            actor_element_assessment__actor=actor,
            actor_element_assessment__element=element,
            parameter_definition=definition,
            time_slice__workspace=c.workspace,
            time_slice__project=c.project,
            target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
            successor__isnull=True,
        )
        .select_related(
            "time_slice",
            "actor_element_assessment",
            "parameter_definition",
        )
        .order_by("time_slice__cutoff_date", "time_slice__order", "pk")
    )
    if len(rows) > MAX_TIMELINE_POINTS:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    result = {}
    for row in rows:
        _validate_terminal_row(c, experiment, actor, element, definition, row)
        if row.time_slice_id in result:
            raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
        result[row.time_slice_id] = row
    return result


def _time_slices(c: AnalysisWorkspace) -> list[TimeSlice]:
    rows = list(
        TimeSlice.objects.filter(
            workspace=c.workspace,
            project=c.project,
        ).order_by("cutoff_date", "order", "pk")
    )
    if len(rows) > MAX_TIMELINE_POINTS:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    return rows


def _point(row: ParameterValue) -> dict[str, Any]:
    provenance = row.actor_element_assessment.provenance
    if not isinstance(provenance, dict):
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    categories = provenance.get("parameter_confidence", {})
    flags = provenance.get("review_flags", {})
    code = row.parameter_definition.code
    confidence = (
        categories.get(code, "UNKNOWN")
        if isinstance(categories, dict)
        else None
    )
    if confidence not in CONFIDENCE or not isinstance(flags, dict):
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    return {
        "record_state": "PERSISTED",
        "time_slice_id": str(row.time_slice_id),
        "cutoff_date": row.time_slice.cutoff_date.isoformat(),
        "parameter_value_id": str(row.pk),
        "assessment_id": str(row.actor_element_assessment_id),
        "value": _validate_value(row, row.parameter_definition),
        "status": row.status,
        "temporal_status": row.temporal_status,
        "confidence_category": confidence,
        "review_flag": flags.get(code),
        "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None,
        "evidence_target": {
            "kind": "parameter-value",
            "id": str(row.pk),
        },
    }


def _no_record_point(row: TimeSlice) -> dict[str, Any]:
    return {
        "record_state": "NO_RECORD",
        "time_slice_id": str(row.pk),
        "cutoff_date": row.cutoff_date.isoformat(),
        "parameter_value_id": None,
        "assessment_id": None,
        "value": None,
        "status": None,
        "temporal_status": None,
        "confidence_category": None,
        "review_flag": None,
        "supersedes_id": None,
        "evidence_target": None,
    }


def _series(c, experiment_id, actor_code, element_code, parameter_code):
    experiment = _experiment(c, experiment_id)
    actor = _actor(c, actor_code)
    element = _element(c, element_code)
    code = require_parameter_code(parameter_code)
    definition = _definitions(c)[code]
    _role(c, actor, element, definition)
    rows = _terminal(c, experiment, actor, element, definition)
    slices = _time_slices(c)
    points = [
        _point(rows[item.pk]) if item.pk in rows else _no_record_point(item)
        for item in slices
    ]
    return {
        "experiment": _experiment_dto(experiment),
        "actor": {
            "id": str(actor.pk),
            "code": actor.code,
            "label": actor.label,
        },
        "analytical_element": {
            "id": str(element.pk),
            "code": element.code,
            "label": element.label,
            "element_type": element.element_type,
            "reference_statement": element.reference_statement,
        },
        "parameter": {
            "id": str(definition.pk),
            "code": code,
            "name": definition.name,
            "scale_min": decimal_text(definition.scale_min),
            "scale_max": decimal_text(definition.scale_max),
        },
        "points": points,
    }


def context_snapshot(*, user, project_id, workspace_id):
    c = _context(user, project_id, workspace_id)
    actors = list(
        Actor.objects.filter(
            workspace=c.workspace,
            source_manifest_entity_id__isnull=False,
        ).order_by("order", "code", "pk")
    )
    elements = list(
        AnalyticalElement.objects.filter(
            workspace=c.workspace,
            source_manifest_entity_id__isnull=False,
        ).order_by("order", "code", "pk")
    )
    definitions = _definitions(c)
    slices = _time_slices(c)
    experiments = list(
        Experiment.objects.filter(
            workspace=c.workspace,
            experiment_type=ExperimentType.ASSESSMENT,
            metadata__contract=EXPERIMENT_CONTRACT,
            expert_profile__kind__in=(AssessmentKind.HUMAN, AssessmentKind.AI),
            expert_profile__workspace=c.workspace,
            assessment_set__workspace=c.workspace,
            assessment_set__project=c.project,
        )
        .exclude(status=ExperimentStatus.ARCHIVED)
        .select_related("expert_profile", "assessment_set")
        .order_by("order", "code", "pk")
    )
    return snapshot(
        CONTEXT_CONTRACT,
        project={
            "id": str(c.project.pk),
            "code": c.project.code,
            "name": c.project.name,
        },
        workspace={
            "id": str(c.workspace.pk),
            "code": c.workspace.code,
            "name": c.workspace.name,
            "definition_id": str(c.workspace.definition_version_id),
            "definition_manifest_hash": c.workspace.definition_manifest_hash,
            "assessment_projection_status": "COMPLETE",
            "assessment_projection_sha256": c.projection_sha256,
        },
        actors=[
            {
                "id": str(row.pk),
                "code": row.code,
                "label": row.label,
                "order": row.order,
            }
            for row in actors
        ],
        analytical_elements=[
            {
                "id": str(row.pk),
                "code": row.code,
                "label": row.label,
                "element_type": row.element_type,
                "reference_statement": row.reference_statement,
                "order": row.order,
            }
            for row in elements
        ],
        parameters=[
            {
                "id": str(row.pk),
                "code": code,
                "name": row.name,
                "value_type": row.value_type,
                "scale_min": decimal_text(row.scale_min),
                "scale_max": decimal_text(row.scale_max),
                "allowed_statuses": list(row.allowed_statuses),
            }
            for code, row in sorted(definitions.items())
        ],
        time_slices=[
            {
                "id": str(row.pk),
                "code": row.code,
                "cutoff_date": row.cutoff_date.isoformat(),
                "order": row.order,
            }
            for row in slices
        ],
        experiments=[_experiment_dto(row) for row in experiments],
        method_state=dict(METHOD_STATE),
    )


def timeline_snapshot(
    *,
    user,
    project_id,
    workspace_id,
    experiment_id,
    actor_code,
    element_code,
    parameter_code,
):
    c = _context(user, project_id, workspace_id)
    return snapshot(
        TIMELINE_CONTRACT,
        project_id=str(c.project.pk),
        workspace_id=str(c.workspace.pk),
        series=_series(
            c,
            experiment_id,
            actor_code,
            element_code,
            parameter_code,
        ),
        method_state=dict(METHOD_STATE),
    )


def comparison_snapshot(
    *,
    user,
    project_id,
    workspace_id,
    experiment_ids: Iterable,
    actor_code,
    element_code,
    parameter_code,
):
    ids = list(experiment_ids)
    if len(ids) != 2 or ids[0] == ids[1]:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    c = _context(user, project_id, workspace_id)
    series = [
        _series(c, item, actor_code, element_code, parameter_code)
        for item in ids
    ]
    if {
        item["experiment"]["kind"]
        for item in series
    } != {AssessmentKind.HUMAN, AssessmentKind.AI}:
        raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
    return snapshot(
        COMPARISON_CONTRACT,
        project_id=str(c.project.pk),
        workspace_id=str(c.workspace.pk),
        aggregation=None,
        series=series,
        method_state=dict(METHOD_STATE),
    )


def matrix_snapshot(
    *,
    user,
    project_id,
    workspace_id,
    experiment_id,
    time_slice_id,
    parameter_code,
):
    c = _context(user, project_id, workspace_id)
    experiment = _experiment(c, experiment_id)
    code = require_parameter_code(parameter_code)
    definition = _definitions(c)[code]
    time_slice = TimeSlice.objects.filter(
        pk=exact_uuid(time_slice_id),
        workspace=c.workspace,
        project=c.project,
    ).first()
    if time_slice is None:
        raise AnalysisError("ANALYSIS_NOT_FOUND", 404)
    actors = list(
        Actor.objects.filter(
            workspace=c.workspace,
            source_manifest_entity_id__isnull=False,
        ).order_by("order", "code", "pk")
    )
    elements = list(
        AnalyticalElement.objects.filter(
            workspace=c.workspace,
            source_manifest_entity_id__isnull=False,
        ).order_by("order", "code", "pk")
    )
    _role_map(c, actors, elements, definition)

    rows = list(
        ParameterValue.objects.filter(
            project=c.project,
            workspace=c.workspace,
            assessment_set=experiment.assessment_set,
            actor_element_assessment__workspace=c.workspace,
            actor_element_assessment__experiment=experiment,
            actor_element_assessment__assessment_set=experiment.assessment_set,
            actor_element_assessment__actor__in=actors,
            actor_element_assessment__element__in=elements,
            parameter_definition=definition,
            time_slice=time_slice,
            target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,
            successor__isnull=True,
        )
        .select_related(
            "time_slice",
            "actor_element_assessment__actor",
            "actor_element_assessment__element",
            "parameter_definition",
        )
        .order_by(
            "actor_element_assessment__actor__order",
            "actor_element_assessment__element__order",
            "pk",
        )
    )
    if len(rows) > MAX_MATRIX_CELLS:
        raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
    by_pair: dict[tuple[object, object], ParameterValue] = {}
    actors_by_id = {row.pk: row for row in actors}
    elements_by_id = {row.pk: row for row in elements}
    for row in rows:
        assessment = row.actor_element_assessment
        actor = actors_by_id.get(assessment.actor_id)
        element = elements_by_id.get(assessment.element_id)
        if actor is None or element is None:
            raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
        _validate_terminal_row(c, experiment, actor, element, definition, row)
        key = (actor.pk, element.pk)
        if key in by_pair:
            raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
        by_pair[key] = row

    cells = []
    for actor in actors:
        for element in elements:
            row = by_pair.get((actor.pk, element.pk))
            point = _point(row) if row is not None else None
            cells.append(
                {
                    "actor_code": actor.code,
                    "element_code": element.code,
                    "record_state": "PERSISTED" if row else "NO_RECORD",
                    "parameter_value_id": str(row.pk) if row else None,
                    "assessment_id": (
                        str(row.actor_element_assessment_id) if row else None
                    ),
                    "value": (
                        _validate_value(row, definition) if row else None
                    ),
                    "status": row.status if row else None,
                    "confidence_category": (
                        point["confidence_category"] if point else None
                    ),
                    "evidence_target": (
                        {
                            "kind": "parameter-value",
                            "id": str(row.pk),
                        }
                        if row
                        else None
                    ),
                }
            )
    return snapshot(
        MATRIX_CONTRACT,
        project_id=str(c.project.pk),
        workspace_id=str(c.workspace.pk),
        experiment=_experiment_dto(experiment),
        time_slice={
            "id": str(time_slice.pk),
            "code": time_slice.code,
            "cutoff_date": time_slice.cutoff_date.isoformat(),
        },
        parameter={
            "id": str(definition.pk),
            "code": code,
            "name": definition.name,
            "scale_min": decimal_text(definition.scale_min),
            "scale_max": decimal_text(definition.scale_max),
        },
        actors=[
            {"code": row.code, "label": row.label, "order": row.order}
            for row in actors
        ],
        analytical_elements=[
            {"code": row.code, "label": row.label, "order": row.order}
            for row in elements
        ],
        cells=cells,
        aggregation=None,
        method_state=dict(METHOD_STATE),
    )


def select_unique_terminal_rows(
    rows: Iterable[dict[str, object]],
) -> list[dict[str, object]]:
    """Pure oracle for successor selection and duplicate-terminal rejection."""
    selected = {}
    for row in rows:
        if row.get("successor_id") is not None:
            continue
        key = row.get("context")
        if key is None:
            raise AnalysisError("ANALYSIS_REQUEST_INVALID", 400)
        if key in selected:
            raise AnalysisError("ANALYSIS_INTEGRITY_CONFLICT")
        selected[key] = row
    return list(selected.values())
