"""Installation service for the versioned Zhanaozen demo seed."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any, TypeVar
from uuid import UUID

from django.db import models, transaction

from domain.demo_data import (
    ASSESSMENT_SETS,
    PARTICIPANT_GROUPS,
    PARAMETER_DEFINITIONS,
    GU_VERSION,
    PROJECT_CODE,
    PROJECT_NAME,
    PTN_VERSION,
    SCHEMA_VERSION,
    SEED_VERSION,
    TENSION_POINTS,
    TIME_SLICES,
    stable_demo_uuid,
)
from domain.models import (
    AssessmentSet,
    GroupTensionRelation,
    ParameterDefinition,
    ParticipantGroup,
    Project,
    ProjectLock,
    ProjectSchemaVersion,
    TensionPoint,
    TimeSlice,
)


class SeedConflictError(ValueError):
    """Existing data conflicts with the stable identity of the demo seed."""


ModelT = TypeVar("ModelT", bound=models.Model)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_manifest() -> tuple[dict[str, Any], str]:
    manifest = {
        "seed_version": SEED_VERSION,
        "schema_version": SCHEMA_VERSION,
        "project_code": PROJECT_CODE,
        "ptn_version": PTN_VERSION,
        "gu_version": GU_VERSION,
        "time_slices": [item["code"] for item in TIME_SLICES],
        "tension_points": [item["code"] for item in TENSION_POINTS],
        "participant_groups": [item["code"] for item in PARTICIPANT_GROUPS],
        "assessment_sets": [item["code"] for item in ASSESSMENT_SETS],
        "parameter_definitions": [
            {"code": item["code"], "version": item["version"]}
            for item in PARAMETER_DEFINITIONS
        ],
    }
    digest = hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
    return manifest, digest


def _assert_stable_identity(
    model: type[ModelT],
    *,
    object_id: UUID,
    code: str,
    project: Project | None = None,
) -> None:
    identity_match = model.objects.filter(pk=object_id).first()
    if identity_match is not None and identity_match.code != code:
        raise SeedConflictError(
            f"{model.__name__} id {object_id} already belongs to code "
            f"{identity_match.code!r}."
        )
    if (
        identity_match is not None
        and project is not None
        and getattr(identity_match, "project_id", project.id) != project.id
    ):
        raise SeedConflictError(
            f"{model.__name__} id {object_id} belongs to a different project."
        )

    code_query: dict[str, Any] = {"code": code}
    if project is not None:
        code_query["project"] = project
    code_match = model.objects.filter(**code_query).first()
    if code_match is not None and code_match.pk != object_id:
        raise SeedConflictError(
            f"{model.__name__} code {code!r} already has a different stable id."
        )


def _upsert(
    model: type[ModelT],
    *,
    object_id: UUID,
    code: str,
    defaults: dict[str, Any],
    project: Project | None = None,
) -> ModelT:
    _assert_stable_identity(
        model,
        object_id=object_id,
        code=code,
        project=project,
    )
    obj, _ = model.objects.update_or_create(
        pk=object_id,
        defaults={"code": code, **defaults},
    )
    return obj


def _require_exact_codes(
    model: type[ModelT], project: Project, expected_codes: set[str]
) -> None:
    actual_codes = set(model.objects.filter(project=project).values_list("code", flat=True))
    if actual_codes != expected_codes:
        unexpected = sorted(actual_codes - expected_codes)
        missing = sorted(expected_codes - actual_codes)
        raise SeedConflictError(
            f"{model.__name__} seed membership drift: unexpected={unexpected}, "
            f"missing={missing}."
        )


@transaction.atomic
def seed_zhanaozen_demo() -> Project:
    """Create or refresh the demo project without duplicating stable entities.

    The service never deletes or silently adopts unexpected structural rows.  A
    drifted demo project is rejected and the transaction rolls back, preserving
    the owner-approved seed membership.
    """

    project_id = stable_demo_uuid("project", PROJECT_CODE)
    _assert_stable_identity(Project, object_id=project_id, code=PROJECT_CODE)
    project = _upsert(
        Project,
        object_id=project_id,
        code=PROJECT_CODE,
        defaults={
            "version": SCHEMA_VERSION,
            "name": PROJECT_NAME,
            "description": "",
            "metadata": {"seed_version": SEED_VERSION},
        },
    )

    time_slices: dict[str, TimeSlice] = {}
    for item in TIME_SLICES:
        code = item["code"]
        time_slices[code] = _upsert(
            TimeSlice,
            object_id=stable_demo_uuid("time-slice", code),
            code=code,
            project=project,
            defaults={
                "project": project,
                "version": SCHEMA_VERSION,
                "name": code,
                "cutoff_date": date.fromisoformat(item["cutoff_date"]),
                "order": item["order"],
            },
        )

    tension_points: dict[str, TensionPoint] = {}
    for item in TENSION_POINTS:
        code = item["code"]
        tension_points[code] = _upsert(
            TensionPoint,
            object_id=stable_demo_uuid("tension-point", code),
            code=code,
            project=project,
            defaults={
                "project": project,
                "version": PTN_VERSION,
                "name": item["name"],
                "short_name": item["short_name"],
                "definition": item["definition"],
                "order": item["order"],
            },
        )

    participant_groups: dict[str, ParticipantGroup] = {}
    for item in PARTICIPANT_GROUPS:
        code = item["code"]
        participant_groups[code] = _upsert(
            ParticipantGroup,
            object_id=stable_demo_uuid("participant-group", code),
            code=code,
            project=project,
            defaults={
                "project": project,
                "version": GU_VERSION,
                "name": item["name"],
                "short_name": item["short_name"],
                "definition": item["definition"],
                "order": item["order"],
            },
        )

    relation_codes: set[str] = set()
    for group_code, group in participant_groups.items():
        for tension_code, tension in tension_points.items():
            code = f"{group_code}--{tension_code}"
            relation_codes.add(code)
            _upsert(
                GroupTensionRelation,
                object_id=stable_demo_uuid("group-tension-relation", code),
                code=code,
                project=project,
                defaults={
                    "project": project,
                    "version": SCHEMA_VERSION,
                    "participant_group": group,
                    "tension_point": tension,
                },
            )

    for item in ASSESSMENT_SETS:
        code = item["code"]
        _upsert(
            AssessmentSet,
            object_id=stable_demo_uuid("assessment-set", code),
            code=code,
            project=project,
            defaults={
                "project": project,
                "version": SCHEMA_VERSION,
                "kind": item["kind"],
                "name": item["name"],
                "description": "",
            },
        )

    for item in PARAMETER_DEFINITIONS:
        code = item["code"]
        _upsert(
            ParameterDefinition,
            object_id=stable_demo_uuid("parameter-definition", code),
            code=code,
            project=project,
            defaults={
                "project": project,
                "version": item["version"],
                "name": item["name"],
                "description": "",
                "target_type": item["target_type"],
                "value_type": item["value_type"],
                "scale_min": None,
                "scale_max": None,
                "scale_metadata": {"method_status": "OPEN_METHOD"},
            },
        )

    # Verify exact demo membership.  Unexpected structure is never pruned.
    _require_exact_codes(TimeSlice, project, set(time_slices))
    _require_exact_codes(TensionPoint, project, set(tension_points))
    _require_exact_codes(ParticipantGroup, project, set(participant_groups))
    _require_exact_codes(GroupTensionRelation, project, relation_codes)
    _require_exact_codes(
        AssessmentSet, project, {item["code"] for item in ASSESSMENT_SETS}
    )
    _require_exact_codes(
        ParameterDefinition,
        project,
        {item["code"] for item in PARAMETER_DEFINITIONS},
    )

    seed_manifest, seed_manifest_hash = _stable_manifest()
    schema_code = f"SCHEMA-{SCHEMA_VERSION}"
    schema_id = stable_demo_uuid("project-schema-version", schema_code)
    ProjectSchemaVersion.objects.filter(project=project).exclude(pk=schema_id).update(
        is_current=False
    )
    _upsert(
        ProjectSchemaVersion,
        object_id=schema_id,
        code=schema_code,
        project=project,
        defaults={
            "project": project,
            "version": SCHEMA_VERSION,
            "is_current": True,
            "manifest": seed_manifest,
            "manifest_hash": seed_manifest_hash,
        },
    )

    _upsert(
        ProjectLock,
        object_id=stable_demo_uuid("project-lock", "STRUCTURE-LOCK"),
        code="STRUCTURE-LOCK",
        project=project,
        defaults={
            "project": project,
            "version": SCHEMA_VERSION,
            "is_structure_locked": True,
            "ordinary_user_can_edit_structure": False,
            "studio_can_edit_structure": False,
            "reason": (
                "FROZEN_FOR_DEMO_V1: изменение состава требует отдельного прямого "
                "OWNER_DECISION и новой версии перечня."
            ),
        },
    )
    return project
