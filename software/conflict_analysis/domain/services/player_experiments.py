"""Foundation-owned G8 assessment experiments and atomic XLSX import."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping
from uuid import UUID, uuid5

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from domain.enums import (
    AssessmentKind, AssessmentRecordStatus, AssessmentTemporalStatus,
    AuditAction, AuditActorType, AuditScope, ConfidenceLevel, ExperimentStatus,
    ExperimentType, ImportPackageScope, ImportRunStatus, TargetType, ValueStatus,
)
from domain.models import (
    Actor, ActorElementAssessment, ActorElementRole, AnalyticalElement,
    AssessmentSet, AuditEvent, Experiment, ExpertProfile, ImportRun,
    ParameterDefinition, ParameterValue, TimeSlice,
)
from domain.services.player_projection import require_complete_workspace_assessment_projection
from domain.services.player_workspaces import (
    PLAYER_REQUIRED_PERMISSIONS, PlayerError, PlayerOperationResult, PlayerPrincipal,
    _project, _sha, _uuid, _validator, _workspace, canonical_receipt_bytes,
)
from domain.services.xlsx_import_profiles import (
    PROFILE_ID, XlsxImportProfileError, load_profile, preview_profile_xlsx,
)

VERSION = "1.0.0"
EXPERIMENT_CONTRACT = "FOUNDATION_PLAYER_EXPERIMENT_V1"
VALUE_CONTRACT = "FOUNDATION_PLAYER_PARAMETER_VALUE_V1"
IMPORT_CONTRACT = "FOUNDATION_PLAYER_XLSX_IMPORT_V1"
PROFILE_CONTRACT = "FOUNDATION_PLAYER_EXPERT_PROFILE_V1"
G8_REQUIRED_PERMISSIONS = PLAYER_REQUIRED_PERMISSIONS | frozenset({
    "domain.add_expertprofile", "domain.view_expertprofile",
    "domain.add_experiment", "domain.change_experiment", "domain.view_experiment",
    "domain.add_assessmentset", "domain.view_assessmentset",
    "domain.add_actorelementassessment", "domain.view_actorelementassessment",
    "domain.add_parametervalue", "domain.view_parametervalue",
    "domain.add_importrun", "domain.view_importrun",
})


class PlayerExperimentError(RuntimeError):
    def __init__(self, code: str, status: int = 409, detail: str = "Request cannot be completed."):
        self.code, self.status, self.detail = code, status, detail
        super().__init__(detail)


@dataclass(frozen=True, slots=True)
class PreviewResult:
    payload: Mapping[str, Any]


def _canonical(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _request_hash(contract: str, **payload: object) -> str:
    return hashlib.sha256(_canonical({"contract": contract, "version": VERSION, **payload})).hexdigest()


def assessment_principal(user) -> PlayerPrincipal:
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        raise PlayerExperimentError("PLAYER_AUTHENTICATION_REQUIRED", 401)
    try:
        persisted = get_user_model()._default_manager.get(pk=user.pk)
    except get_user_model().DoesNotExist as exc:
        raise PlayerExperimentError("PLAYER_AUTHENTICATION_REQUIRED", 401) from exc
    permissions = frozenset(persisted.get_all_permissions())
    if (
        not persisted.is_active or persisted.is_staff or persisted.is_superuser
        or permissions != G8_REQUIRED_PERMISSIONS
    ):
        raise PlayerExperimentError("PLAYER_PERMISSION_DENIED", 403)
    return PlayerPrincipal(persisted.pk, f"django-user:{persisted.pk}", permissions)


def _projection_workspace(principal, workspace_id, *, lock=False):
    try:
        project, workspace = _workspace(principal, workspace_id, lock=lock)
        require_complete_workspace_assessment_projection(workspace)
    except Exception as exc:
        if isinstance(exc, (PlayerExperimentError, PlayerError)):
            raise
        code = getattr(exc, "code", "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT")
        if code not in {"ASSESSMENT_PROJECTION_NOT_PROVEN", "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT"}:
            code = "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT"
        raise PlayerExperimentError(code) from exc
    return project, workspace


def _experiment_scope(principal, experiment_id, *, lock=False):
    experiment_id = _uuid(experiment_id)
    workspace_id = Experiment.objects.filter(pk=experiment_id).values_list("workspace_id", flat=True).first()
    if workspace_id is None:
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    project, workspace = _projection_workspace(principal, workspace_id, lock=lock)
    rows = Experiment.objects.select_for_update() if lock else Experiment.objects
    experiment = rows.select_related("expert_profile", "assessment_set").filter(
        pk=experiment_id, workspace=workspace, experiment_type=ExperimentType.ASSESSMENT,
        metadata__contract=EXPERIMENT_CONTRACT,
    ).first()
    if experiment is None:
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    return project, workspace, experiment


def admit_assessment_scope(*, user, kind: str, identity):
    principal = assessment_principal(user)
    if kind == "workspace":
        return _projection_workspace(principal, identity)[1]
    if kind == "experiment":
        return _experiment_scope(principal, identity)[2]
    if kind == "import":
        operation_id = _uuid(identity)
        workspace_id = ImportRun.objects.filter(pk=operation_id).values_list("workspace_id", flat=True).first()
        if workspace_id is None:
            raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
        _, workspace = _projection_workspace(principal, workspace_id)
        row = ImportRun.objects.filter(pk=operation_id, workspace=workspace).first()
        if row is None:
            raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
        return row
    raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)


def _profile_dto(row: ExpertProfile) -> dict[str, Any]:
    core = {
        "id": str(row.pk), "workspace_id": str(row.workspace_id), "code": row.code,
        "version": row.version, "kind": row.kind, "display_name": row.display_name,
        "identity_key": row.identity_key, "provider": row.provider,
        "model_name": row.model_name, "metadata": row.metadata,
        "used": Experiment.objects.filter(expert_profile=row).exists(),
    }
    return {**core, "etag": hashlib.sha256(_canonical(core)).hexdigest()}


def _require_profile_contract(profile: Mapping[str, Any]) -> None:
    """Admit only the frozen bounded HUMAN/AI G8 profile wire shapes."""

    kind = profile.get("kind")
    provider = profile.get("provider")
    model_name = profile.get("model_name")
    metadata = profile.get("metadata")
    marker = {"contract": PROFILE_CONTRACT}
    if kind == AssessmentKind.AI:
        valid = (
            isinstance(provider, str) and bool(provider.strip()) and len(provider) <= 128
            and isinstance(model_name, str) and bool(model_name.strip()) and len(model_name) <= 255
            and metadata == marker
        )
    elif kind == AssessmentKind.HUMAN:
        valid = (
            provider == "" and model_name == "" and type(metadata) is dict
            and set(metadata) == {"contract", "organization", "role", "description"}
            and metadata.get("contract") == PROFILE_CONTRACT
            and isinstance(metadata.get("organization"), str)
            and len(metadata["organization"]) <= 255
            and isinstance(metadata.get("role"), str)
            and len(metadata["role"]) <= 255
            and isinstance(metadata.get("description"), str)
            and len(metadata["description"]) <= 2000
        )
    else:
        valid = False
    if not valid:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)


def _experiment_dto(row: Experiment) -> dict[str, Any]:
    core = {
        "id": str(row.pk), "workspace_id": str(row.workspace_id), "code": row.code,
        "version": row.version, "name": row.name, "experiment_type": row.experiment_type,
        "status": row.status, "color": row.color, "order": row.order,
        "method_version": row.method_version,
        "frozen_at": row.frozen_at.isoformat() if row.frozen_at else None,
        "expert_profile": _profile_dto(row.expert_profile),
        "assessment_set": {
            "id": str(row.assessment_set_id), "code": row.assessment_set.code,
            "version": row.assessment_set.version, "kind": row.assessment_set.kind,
            "name": row.assessment_set.name, "description": row.assessment_set.description,
        },
    }
    return {**core, "etag": hashlib.sha256(_canonical(core)).hexdigest()}


def list_expert_profiles(*, user, workspace_id):
    principal = assessment_principal(user)
    _, workspace = _projection_workspace(principal, workspace_id)
    return {"profiles": [_profile_dto(row) for row in ExpertProfile.objects.filter(workspace=workspace)]}


def create_or_update_expert_profile(
    *, user, workspace_id, operation_id, if_match, body,
):
    """Create or edit one profile before its first experiment uses it."""

    principal = assessment_principal(user)
    project, workspace = _projection_workspace(principal, workspace_id)
    expected = {
        "id", "code", "version", "kind", "display_name", "identity_key",
        "provider", "model_name", "metadata",
    }
    _require_keys(body, expected)
    _require_profile_contract(body)
    profile_id = _uuid(body["id"])
    operation_id = _uuid(operation_id, operation=True)
    request_sha = _request_hash(
        PROFILE_CONTRACT, workspace_id=str(workspace.pk), body=body, if_match=if_match,
    )
    with transaction.atomic():
        principal = assessment_principal(user)
        project, workspace = _projection_workspace(principal, workspace_id, lock=True)
        receipt = _existing_receipt(
            operation_id=operation_id, project=project, workspace=workspace,
            contract=PROFILE_CONTRACT, principal=principal, request_sha=request_sha,
        )
        if receipt is not None:
            return _operation_result(receipt, True)
        profile = ExpertProfile.objects.select_for_update().filter(
            pk=profile_id, workspace=workspace,
        ).first()
        collision = ExpertProfile.objects.select_for_update().filter(
            workspace=workspace,
        ).filter(Q(code=body["code"]) | Q(identity_key=body["identity_key"])).exclude(
            pk=profile_id,
        ).exists()
        if collision:
            raise PlayerExperimentError("PLAYER_IDENTITY_CONFLICT")
        if profile is None:
            _validator(if_match, workspace.definition_manifest_hash)
            profile = ExpertProfile(
                id=profile_id, workspace=workspace, code=body["code"],
                version=body["version"], kind=body["kind"],
                display_name=body["display_name"], identity_key=body["identity_key"],
                provider=body["provider"], model_name=body["model_name"],
                metadata=body["metadata"],
            )
            profile.save(force_insert=True)
            action = AuditAction.CREATE
        else:
            _validator(if_match, _profile_dto(profile)["etag"])
            if Experiment.objects.filter(expert_profile=profile).exists():
                raise PlayerExperimentError("PLAYER_IDENTITY_CONFLICT")
            for field in (
                "code", "version", "kind", "display_name", "identity_key",
                "provider", "model_name", "metadata",
            ):
                setattr(profile, field, body[field])
            profile.save(update_fields=[
                "code", "version", "kind", "display_name", "identity_key",
                "provider", "model_name", "metadata", "updated_at",
            ])
            action = AuditAction.UPDATE
        dto = _profile_dto(profile)
        receipt = _audit(
            operation_id=operation_id, project=project, workspace=workspace,
            principal=principal, contract=PROFILE_CONTRACT, entity_id=profile.pk,
            action=action, request_sha=request_sha, payload={"expert_profile": dto},
        )
        return _operation_result(receipt, False)


def list_experiments(*, user, workspace_id, include_archived=False):
    principal = assessment_principal(user)
    _, workspace = _projection_workspace(principal, workspace_id)
    verification = require_complete_workspace_assessment_projection(workspace)
    rows = Experiment.objects.filter(
        workspace=workspace, experiment_type=ExperimentType.ASSESSMENT,
        metadata__contract=EXPERIMENT_CONTRACT,
    ).select_related("expert_profile", "assessment_set")
    if not include_archived:
        rows = rows.exclude(status=ExperimentStatus.ARCHIVED)
    roles = ActorElementRole.objects.filter(workspace=workspace).select_related(
        "actor", "element",
    ).order_by("actor__code", "element__code", "code")
    return {
        "workspace": {
            "id": str(workspace.pk), "project_id": str(workspace.project_id),
            "name": workspace.name, "code": workspace.code,
            "definition_id": str(workspace.definition_version_id),
            "definition_manifest_hash": workspace.definition_manifest_hash,
            "assessment_projection_status": verification.status,
            "assessment_projection_sha256": verification.projection_sha256,
        },
        "experiments": [_experiment_dto(row) for row in rows],
        "manual_targets": {
            "time_slices": [
                {"id": str(row.pk), "code": row.code, "cutoff_date": row.cutoff_date.isoformat()}
                for row in TimeSlice.objects.filter(workspace=workspace).order_by("cutoff_date", "code")
            ],
            "actor_element_roles": [
                {
                    "actor_code": row.actor.code,
                    "element_code": row.element.code,
                    "role_code": row.code,
                    "role_uuid": str(row.source_manifest_entity_id),
                }
                for row in roles
            ],
            "parameter_codes": ["POS", "SAL"],
        },
    }


def open_experiment(*, user, experiment_id):
    principal = assessment_principal(user)
    _, _, row = _experiment_scope(principal, experiment_id)
    return _experiment_dto(row)


def _operation_result(receipt: AuditEvent, replayed: bool):
    receipt.refresh_from_db()
    return PlayerOperationResult(receipt, canonical_receipt_bytes(receipt.after), replayed)


def _existing_receipt(*, operation_id, project, workspace, contract, principal, request_sha):
    receipt = AuditEvent.objects.select_for_update().filter(
        pk=operation_id, project=project, workspace=workspace, entity_type=contract,
    ).first()
    if receipt is None:
        return None
    if (
        receipt.actor_identifier != principal.actor_identifier
        or not isinstance(receipt.after, dict)
        or receipt.after.get("canonical_request_sha256") != request_sha
    ):
        raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
    return receipt


def _audit(*, operation_id, project, workspace, principal, contract, entity_id,
           action, request_sha, payload, assessment_set=None, parameter_value=None):
    occurred_at = timezone.now()
    core = {
        "contract": contract, "version": VERSION, "operation_id": str(operation_id),
        "audit_event_id": str(operation_id), "actor_type": AuditActorType.HUMAN,
        "actor_identifier": principal.actor_identifier, "project_id": str(project.pk),
        "workspace_id": str(workspace.pk), "definition_id": str(workspace.definition_version_id),
        "manifest_sha256": workspace.definition_manifest_hash,
        "canonical_request_sha256": request_sha, **payload,
        "occurred_at": occurred_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "original_http_status": 201,
    }
    after = {**core, "receipt_sha256": _sha(core)}
    receipt = AuditEvent.objects.create(
        id=operation_id, code=f"G8-{contract}-{operation_id}", version=VERSION,
        project=project, workspace=workspace, scope=AuditScope.WORKSPACE,
        assessment_set=assessment_set, parameter_value=parameter_value,
        action=action, actor_type=AuditActorType.HUMAN,
        actor_identifier=principal.actor_identifier, entity_type=contract,
        entity_id=entity_id, before=None, after=after, occurred_at=occurred_at,
    )
    return receipt


def _require_keys(body, expected):
    if type(body) is not dict or set(body) != set(expected):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)


def create_experiment(*, user, workspace_id, operation_id, if_match, body):
    principal = assessment_principal(user)
    project, workspace = _projection_workspace(principal, workspace_id)
    _validator(if_match, workspace.definition_manifest_hash)
    _require_keys(body, {"experiment", "assessment_set", "expert_profile"})
    experiment_body, set_body, profile_body = body["experiment"], body["assessment_set"], body["expert_profile"]
    _require_keys(experiment_body, {"id","code","version","name","color","order","method_version"})
    _require_keys(set_body, {"id","code","version","kind","name","description"})
    _require_keys(profile_body, {"id","code","version","kind","display_name","identity_key","provider","model_name","metadata"})
    _require_profile_contract(profile_body)
    if set_body["kind"] not in {AssessmentKind.HUMAN, AssessmentKind.AI} or profile_body["kind"] != set_body["kind"]:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    operation_id = _uuid(operation_id, operation=True)
    request_sha = _request_hash(EXPERIMENT_CONTRACT, workspace_id=str(workspace.pk), body=body,
                                if_match=if_match)
    with transaction.atomic():
        principal = assessment_principal(user)
        project, workspace = _projection_workspace(principal, workspace_id, lock=True)
        _validator(if_match, workspace.definition_manifest_hash)
        receipt = _existing_receipt(operation_id=operation_id, project=project, workspace=workspace,
                                    contract=EXPERIMENT_CONTRACT, principal=principal, request_sha=request_sha)
        if receipt is not None:
            return _operation_result(receipt, True)
        profile = ExpertProfile.objects.select_for_update().filter(
            workspace=workspace, identity_key=profile_body["identity_key"]
        ).first()
        if profile is None:
            profile = ExpertProfile(
                id=_uuid(profile_body["id"]), workspace=workspace,
                code=profile_body["code"], version=profile_body["version"],
                kind=profile_body["kind"], display_name=profile_body["display_name"],
                identity_key=profile_body["identity_key"], provider=profile_body["provider"],
                model_name=profile_body["model_name"], metadata=profile_body["metadata"],
            ); profile.save(force_insert=True)
        elif any(getattr(profile, key) != profile_body[key] for key in (
            "code","version","kind","display_name","identity_key","provider","model_name","metadata"
        )) or str(profile.pk) != profile_body["id"]:
            raise PlayerExperimentError("PLAYER_IDENTITY_CONFLICT")
        assessment_set = AssessmentSet(
            id=_uuid(set_body["id"]), project=project, workspace=workspace,
            code=set_body["code"], version=set_body["version"], kind=set_body["kind"],
            name=set_body["name"], description=set_body["description"],
        ); assessment_set.save(force_insert=True)
        experiment = Experiment(
            id=_uuid(experiment_body["id"]), workspace=workspace, expert_profile=profile,
            assessment_set=assessment_set, code=experiment_body["code"],
            version=experiment_body["version"], name=experiment_body["name"],
            experiment_type=ExperimentType.ASSESSMENT, status=ExperimentStatus.DRAFT,
            color=experiment_body["color"], order=experiment_body["order"],
            method_version=experiment_body["method_version"], frozen_at=None,
            metadata={"contract": EXPERIMENT_CONTRACT},
        ); experiment.save(force_insert=True)
        dto = _experiment_dto(experiment)
        receipt = _audit(
            operation_id=operation_id, project=project, workspace=workspace,
            principal=principal, contract=EXPERIMENT_CONTRACT, entity_id=experiment.pk,
            action=AuditAction.CREATE, request_sha=request_sha,
            payload={"created_experiment": dto}, assessment_set=assessment_set,
        )
        return _operation_result(receipt, False)


def mutate_experiment(*, user, experiment_id, operation_id, if_match, action, body=None):
    principal = assessment_principal(user)
    project, workspace, current = _experiment_scope(principal, experiment_id)
    operation_id = _uuid(operation_id, operation=True)
    if action == "update":
        _require_keys(body, {"name","color","order","description"})
    elif body not in ({}, None):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    contract = f"{EXPERIMENT_CONTRACT}_{action.upper()}"
    request_sha = _request_hash(contract, experiment_id=str(current.pk), body=body or {}, if_match=if_match)
    with transaction.atomic():
        principal = assessment_principal(user)
        project, workspace, row = _experiment_scope(principal, experiment_id, lock=True)
        receipt = _existing_receipt(operation_id=operation_id, project=project, workspace=workspace,
                                    contract=contract, principal=principal, request_sha=request_sha)
        if receipt is not None:
            return _operation_result(receipt, True)
        _validator(if_match, _experiment_dto(row)["etag"])
        if action == "update":
            if row.status != ExperimentStatus.DRAFT:
                raise PlayerExperimentError("G8_EXPERIMENT_NOT_DRAFT")
            row.name, row.color, row.order = body["name"], body["color"], body["order"]
            row.assessment_set.description = body["description"]
            row.assessment_set.save(update_fields=["description","updated_at"])
            row.save(update_fields=["name","color","order","updated_at"])
            audit_action = AuditAction.UPDATE
        elif action == "freeze":
            if row.status != ExperimentStatus.DRAFT:
                raise PlayerExperimentError("G8_EXPERIMENT_TRANSITION_FORBIDDEN")
            row.status, row.frozen_at = ExperimentStatus.FROZEN, timezone.now()
            row.save(update_fields=["status","frozen_at","updated_at"]); audit_action = AuditAction.FREEZE
        elif action == "archive":
            if row.status not in {ExperimentStatus.DRAFT, ExperimentStatus.FROZEN}:
                raise PlayerExperimentError("G8_EXPERIMENT_TRANSITION_FORBIDDEN")
            row.status = ExperimentStatus.ARCHIVED
            row.save(update_fields=["status","updated_at"]); audit_action = AuditAction.UPDATE
        else:
            raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
        receipt = _audit(operation_id=operation_id, project=project, workspace=workspace,
                         principal=principal, contract=contract, entity_id=row.pk,
                         action=audit_action, request_sha=request_sha,
                         payload={"experiment": _experiment_dto(row)}, assessment_set=row.assessment_set)
        return _operation_result(receipt, False)


def _value_dto(row: ParameterValue) -> dict[str, Any]:
    provenance = row.actor_element_assessment.provenance
    confidence_categories = provenance.get("parameter_confidence", {})
    review_flags = provenance.get("review_flags", {})
    parameter_code = row.parameter_definition.code
    core = {
        "id": str(row.pk), "code": row.code, "version": row.version,
        "experiment_id": str(row.actor_element_assessment.experiment_id),
        "assessment_id": str(row.actor_element_assessment_id),
        "assessment_code": row.actor_element_assessment.code,
        "actor_code": row.actor_element_assessment.actor.code,
        "element_code": row.actor_element_assessment.element.code,
        "parameter_code": parameter_code,
        "time_slice_id": str(row.time_slice_id), "status": row.status,
        "temporal_status": row.temporal_status, "value": row.value,
        "confidence": str(row.confidence) if row.confidence is not None else None,
        "confidence_category": confidence_categories.get(parameter_code, "UNKNOWN"),
        "review_flags": review_flags,
        "review_flag": review_flags.get(parameter_code),
        "rationale": row.rationale, "note": row.note,
        "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None,
        "focus": {"kind": "parameter-value", "id": str(row.pk)},
    }
    return {**core, "etag": hashlib.sha256(_canonical(core)).hexdigest()}


def list_values(*, user, experiment_id):
    principal = assessment_principal(user)
    _, _, experiment = _experiment_scope(principal, experiment_id)
    rows = ParameterValue.objects.filter(
        actor_element_assessment__experiment=experiment,
    ).select_related(
        "actor_element_assessment__actor", "actor_element_assessment__element",
        "parameter_definition", "time_slice",
    ).order_by(
        "actor_element_assessment__code", "parameter_definition__code", "created_at"
    )
    return {"experiment": _experiment_dto(experiment), "values": [_value_dto(row) for row in rows]}


def _exact_targets(workspace, experiment, *, time_slice_id, actor_code, element_code, parameter_code):
    time_slice = TimeSlice.objects.filter(pk=_uuid(time_slice_id), workspace=workspace).first()
    actor = Actor.objects.filter(workspace=workspace, code=actor_code,
                                 source_manifest_entity_id__isnull=False).first()
    element = AnalyticalElement.objects.filter(workspace=workspace, code=element_code,
                                               source_manifest_entity_id__isnull=False).first()
    definition = ParameterDefinition.objects.filter(
        project=workspace.project, definition_version=workspace.definition_version,
        code=parameter_code,
    ).first()
    if not all((time_slice, actor, element, definition)) or parameter_code not in {"POS","SAL"}:
        raise PlayerExperimentError("PLAYER_NOT_FOUND", 404)
    roles = list(ActorElementRole.objects.filter(workspace=workspace, actor=actor, element=element))
    if len(roles) != 1 or str(roles[0].source_manifest_entity_id) not in {
        str(value) for value in definition.applicability.get("actor_element_role_ids", [])
    }:
        raise PlayerExperimentError("G8_TARGET_MAPPING_MISMATCH")
    return time_slice, actor, element, definition, roles[0]


def create_manual_value(*, user, experiment_id, operation_id, if_match, body):
    principal = assessment_principal(user)
    project, workspace, experiment = _experiment_scope(principal, experiment_id)
    expected={"id","code","version","assessment_id","assessment_code","time_slice_id",
              "actor_code","element_code","parameter_code","status","value","temporal_status",
              "confidence_category","rationale","note","supersedes_id"}
    _require_keys(body, expected)
    if (
        body["confidence_category"] not in {"LOW", "MEDIUM", "HIGH", "UNKNOWN"}
        or body["status"] not in {ValueStatus.PROVISIONAL, ValueStatus.UNKNOWN}
        or body["temporal_status"] not in set(AssessmentTemporalStatus.values)
        or (body["status"] == ValueStatus.UNKNOWN and body["value"] is not None)
        or (body["status"] == ValueStatus.PROVISIONAL and type(body["value"]) not in {int, float})
    ):
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
    operation_id=_uuid(operation_id,operation=True)
    predecessor=None
    if body["supersedes_id"]:
        predecessor=ParameterValue.objects.select_related("actor_element_assessment","parameter_definition").filter(
            pk=_uuid(body["supersedes_id"]), actor_element_assessment__experiment=experiment
        ).first()
        if predecessor is None: raise PlayerExperimentError("PLAYER_NOT_FOUND",404)
    request_sha=_request_hash(VALUE_CONTRACT,experiment_id=str(experiment.pk),body=body,if_match=if_match)
    with transaction.atomic():
        principal=assessment_principal(user); project,workspace,experiment=_experiment_scope(principal,experiment_id,lock=True)
        receipt=_existing_receipt(operation_id=operation_id,project=project,workspace=workspace,
                                  contract=VALUE_CONTRACT,principal=principal,request_sha=request_sha)
        if receipt is not None: return _operation_result(receipt,True)
        if predecessor is None: _validator(if_match,_experiment_dto(experiment)["etag"])
        if experiment.status!=ExperimentStatus.DRAFT: raise PlayerExperimentError("G8_EXPERIMENT_NOT_DRAFT")
        if predecessor is not None:
            predecessor=ParameterValue.objects.select_for_update().filter(
                pk=predecessor.pk,actor_element_assessment__experiment=experiment,
            ).first()
            if predecessor is None: raise PlayerExperimentError("PLAYER_NOT_FOUND",404)
            _validator(if_match,_value_dto(predecessor)["etag"])
            if hasattr(predecessor,"successor"): raise PlayerExperimentError("PLAYER_STALE")
        ts,actor,element,definition,role=_exact_targets(workspace,experiment,time_slice_id=body["time_slice_id"],actor_code=body["actor_code"],element_code=body["element_code"],parameter_code=body["parameter_code"])
        context = {
            "workspace": workspace, "actor": actor, "element": element, "time_slice": ts,
            "experiment": experiment, "assessment_set": experiment.assessment_set,
        }
        assessment=ActorElementAssessment.objects.select_for_update(of=("self",)).filter(
            **context, successor__isnull=True,
        ).first()
        if assessment is None:
            confidence={"POS":"UNKNOWN","SAL":"UNKNOWN"}; confidence[definition.code]=body["confidence_category"]
            assessment=ActorElementAssessment(
                id=_uuid(body["assessment_id"]),workspace=workspace,actor=actor,element=element,
                time_slice=ts,experiment=experiment,assessment_set=experiment.assessment_set,
                code=body["assessment_code"],version="1.0.0",reference_statement="",
                reference_statement_incomplete=True,
                status=AssessmentRecordStatus.UNKNOWN if body["status"]==ValueStatus.UNKNOWN else AssessmentRecordStatus.PROVISIONAL_PRE_METHOD_FREEZE,
                confidence_level=ConfidenceLevel.UNKNOWN,knowledge_cutoff=ts.cutoff_date,
                method_version=experiment.method_version,
                provenance={"contract":VALUE_CONTRACT,"role_code":role.code,"role_uuid":str(role.source_manifest_entity_id),"parameter_confidence":confidence,"review_flags":{"POS":"REFERENCE_STATEMENT_REVIEW_REQUIRED","SAL":"SCALE_CONSTRUCT_REVIEW_REQUIRED"}},
            ); assessment.save(force_insert=True)
        elif predecessor is None:
            if ParameterValue.objects.filter(
                actor_element_assessment__workspace=workspace,
                actor_element_assessment__actor=actor,
                actor_element_assessment__element=element,
                actor_element_assessment__time_slice=ts,
                actor_element_assessment__experiment=experiment,
                actor_element_assessment__assessment_set=experiment.assessment_set,
                parameter_definition=definition, successor__isnull=True,
            ).exists():
                raise PlayerExperimentError("PLAYER_STALE")
            provenance = dict(assessment.provenance)
            confidence = dict(provenance.get("parameter_confidence", {}))
            if set(confidence) != {"POS", "SAL"}:
                confidence = {"POS": "UNKNOWN", "SAL": "UNKNOWN"}
            confidence[definition.code] = body["confidence_category"]
            provenance["parameter_confidence"] = confidence
            has_numeric = (
                body["status"] == ValueStatus.PROVISIONAL
                or ParameterValue.objects.filter(
                    actor_element_assessment__workspace=workspace,
                    actor_element_assessment__actor=actor,
                    actor_element_assessment__element=element,
                    actor_element_assessment__time_slice=ts,
                    actor_element_assessment__experiment=experiment,
                    actor_element_assessment__assessment_set=experiment.assessment_set,
                    status=ValueStatus.PROVISIONAL, successor__isnull=True,
                ).exists()
            )
            version_parts = assessment.version.split(".")
            if len(version_parts) != 3 or not all(part.isdigit() for part in version_parts):
                raise PlayerExperimentError("PLAYER_OPERATION_FAILED", 503)
            assessment = ActorElementAssessment(
                id=_uuid(body["assessment_id"]), code=body["assessment_code"],
                version=f"{version_parts[0]}.{version_parts[1]}.{int(version_parts[2]) + 1}",
                supersedes=assessment, reference_statement=assessment.reference_statement,
                reference_statement_incomplete=assessment.reference_statement_incomplete,
                status=(
                    AssessmentRecordStatus.PROVISIONAL_PRE_METHOD_FREEZE
                    if has_numeric else AssessmentRecordStatus.UNKNOWN
                ),
                confidence_level=ConfidenceLevel.UNKNOWN, knowledge_cutoff=assessment.knowledge_cutoff,
                method_version=assessment.method_version, provenance=provenance, **context,
            )
            assessment.save(force_insert=True)
        else:
            predecessor_assessment = predecessor.actor_element_assessment
            if (
                predecessor.workspace_id != workspace.pk
                or predecessor.time_slice_id != ts.pk
                or predecessor.assessment_set_id != experiment.assessment_set_id
                or predecessor.parameter_definition_id != definition.pk
                or predecessor.target_type != TargetType.ACTOR_ELEMENT_ASSESSMENT
                or predecessor.target_id != predecessor.actor_element_assessment_id
                or predecessor_assessment.actor_id != actor.pk
                or predecessor_assessment.element_id != element.pk
                or predecessor_assessment.experiment_id != experiment.pk
            ):
                raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)
            lineage = set()
            cursor = assessment
            while cursor is not None and cursor.pk not in lineage:
                lineage.add(cursor.pk)
                if cursor.pk == predecessor_assessment.pk:
                    break
                cursor = (
                    ActorElementAssessment.objects.select_for_update(of=("self",))
                    .filter(pk=cursor.supersedes_id).first()
                    if cursor.supersedes_id else None
                )
            if predecessor_assessment.pk not in lineage:
                raise PlayerExperimentError("PLAYER_REQUEST_INVALID", 400)

            provenance = json.loads(_canonical(assessment.provenance))
            confidence = dict(provenance.get("parameter_confidence", {}))
            if set(confidence) != {"POS", "SAL"}:
                raise PlayerExperimentError("PLAYER_OPERATION_FAILED", 503)
            confidence[definition.code] = body["confidence_category"]
            provenance["parameter_confidence"] = confidence
            other_numeric = ParameterValue.objects.filter(
                actor_element_assessment__workspace=workspace,
                actor_element_assessment__actor=actor,
                actor_element_assessment__element=element,
                actor_element_assessment__time_slice=ts,
                actor_element_assessment__experiment=experiment,
                actor_element_assessment__assessment_set=experiment.assessment_set,
                parameter_definition__code__in={"POS", "SAL"},
                status=ValueStatus.PROVISIONAL, successor__isnull=True,
            ).exclude(parameter_definition=definition).exists()
            next_status = (
                AssessmentRecordStatus.PROVISIONAL_PRE_METHOD_FREEZE
                if body["status"] == ValueStatus.PROVISIONAL or other_numeric
                else AssessmentRecordStatus.UNKNOWN
            )
            if (
                provenance != assessment.provenance
                or next_status != assessment.status
            ):
                version_parts = assessment.version.split(".")
                if len(version_parts) != 3 or not all(part.isdigit() for part in version_parts):
                    raise PlayerExperimentError("PLAYER_OPERATION_FAILED", 503)
                assessment = ActorElementAssessment(
                    id=_uuid(body["assessment_id"]), code=body["assessment_code"],
                    version=f"{version_parts[0]}.{version_parts[1]}.{int(version_parts[2]) + 1}",
                    supersedes=assessment,
                    reference_statement=assessment.reference_statement,
                    reference_statement_incomplete=assessment.reference_statement_incomplete,
                    status=next_status, confidence_level=ConfidenceLevel.UNKNOWN,
                    knowledge_cutoff=assessment.knowledge_cutoff,
                    method_version=assessment.method_version, provenance=provenance,
                    **context,
                )
                assessment.save(force_insert=True)
        value=ParameterValue(
            id=_uuid(body["id"]),project=project,workspace=workspace,time_slice=ts,
            assessment_set=experiment.assessment_set,actor_element_assessment=assessment,
            supersedes=predecessor,parameter_definition=definition,
            target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,target_id=assessment.pk,
            code=body["code"],version=body["version"],status=body["status"],
            temporal_status=body["temporal_status"],value=body["value"],note=body["note"],
            confidence=None,range_min=None,range_max=None,rationale=body["rationale"],
        ); value.save(force_insert=True)
        receipt=_audit(operation_id=operation_id,project=project,workspace=workspace,principal=principal,
                       contract=VALUE_CONTRACT,entity_id=value.pk,action=AuditAction.CREATE,
                       request_sha=request_sha,payload={"value":_value_dto(value)},
                       assessment_set=experiment.assessment_set,parameter_value=value)
        return _operation_result(receipt,False)


def _raw_body(body):
    _require_keys(body,{"raw_file","profile_id","sheet","source_column"})
    if type(body["raw_file"]) is not bytes:
        raise PlayerExperimentError("PLAYER_REQUEST_INVALID",400)
    return body["raw_file"]


def _validated_import_projection(project, workspace, parsed):
    """Resolve every portable row against the live accepted projection before admission."""

    profile = load_profile()
    accepted = profile["accepted_manifest"]
    if (
        str(workspace.pk) != accepted["workspace_id"]
        or str(workspace.definition_version_id) != accepted["definition_id"]
        or workspace.definition_manifest_hash != accepted["sha256"]
        or accepted["head"] != "f2255b6d76cf8efa46b5bea5756e09af4273b46a"
        or accepted["tree"] != "249b5e826511072c6fbcb0ea3cb7441d83c25faf"
    ):
        raise PlayerExperimentError("G8_TARGET_MAPPING_MISMATCH")
    actors = {row.code: row for row in Actor.objects.filter(workspace=workspace)}
    elements = {row.code: row for row in AnalyticalElement.objects.filter(workspace=workspace)}
    times = {row.code: row for row in TimeSlice.objects.filter(workspace=workspace)}
    definitions = {
        row.code: row for row in ParameterDefinition.objects.filter(
            project=project, definition_version=workspace.definition_version,
            code__in=("POS", "SAL"),
        )
    }
    if set(definitions) != {"POS", "SAL"}:
        raise PlayerExperimentError("G8_TARGET_MAPPING_MISMATCH")
    roles_by_pair: dict[tuple[object, object], list[ActorElementRole]] = {}
    for role in ActorElementRole.objects.filter(workspace=workspace):
        roles_by_pair.setdefault((role.actor_id, role.element_id), []).append(role)
    role_cache: dict[tuple[object, object], ActorElementRole] = {}
    for item in parsed["creates"]:
        mapped = item["profile"]
        actor = actors.get(mapped["source_manifest_actor_code"])
        element = elements.get(mapped["source_manifest_element_code"])
        time_slice = times.get(mapped["time_slice_code"])
        definition = definitions.get(mapped["canonical_parameter_code"])
        roles = roles_by_pair.get((actor.pk, element.pk), []) if actor and element else []
        if (
            actor is None or element is None or time_slice is None or definition is None
            or len(roles) != 1
            or str(actor.source_manifest_entity_id) != mapped["source_manifest_actor_uuid"]
            or str(element.source_manifest_entity_id) != mapped["source_manifest_element_uuid"]
            or str(time_slice.pk) != mapped["time_slice_manifest_uuid"]
            or time_slice.cutoff_date.isoformat() != mapped["cutoff_date"]
            or str(definition.source_manifest_parameter_id) != mapped["canonical_parameter_uuid"]
            or roles[0].code != mapped["source_manifest_role_code"]
            or str(roles[0].source_manifest_entity_id) != mapped["source_manifest_role_uuid"]
            or mapped["source_manifest_role_uuid"] not in {
                str(value) for value in definition.applicability.get("actor_element_role_ids", [])
            }
        ):
            raise PlayerExperimentError("G8_TARGET_MAPPING_MISMATCH")
        role_cache[(actor.pk, element.pk)] = roles[0]
    return profile, actors, elements, times, definitions, role_cache


def preview_xlsx(*, user, experiment_id, body):
    principal=assessment_principal(user); project,workspace,experiment=_experiment_scope(principal,experiment_id)
    raw=_raw_body(body)
    try: parsed=preview_profile_xlsx(raw,profile_id=body["profile_id"],sheet=body["sheet"],source_column=body["source_column"])
    except XlsxImportProfileError as exc: raise PlayerExperimentError(exc.code,400,exc.detail) from exc
    _validated_import_projection(project, workspace, parsed)
    public={key:value for key,value in parsed.items() if key not in {"creates","import_snapshot"}}
    public["experiment_id"]=str(experiment.pk); public["experiment_etag"]=_experiment_dto(experiment)["etag"]
    public["commit_allowed"]=(
        experiment.status == ExperimentStatus.DRAFT
        and not parsed["diagnostics"]
        and parsed["rows_to_create"] > 0
        and not ActorElementAssessment.objects.filter(experiment=experiment).exists()
        and not ParameterValue.objects.filter(actor_element_assessment__experiment=experiment).exists()
        and not ImportRun.objects.filter(
            target_experiment=experiment, status=ImportRunStatus.COMMITTED,
        ).exists()
    )
    return public


def import_xlsx(*, user, experiment_id, operation_id, if_match, body):
    principal=assessment_principal(user); project,workspace,experiment=_experiment_scope(principal,experiment_id)
    _require_keys(body,{"raw_file","profile_id","sheet","source_column","preview_sha256","excluded_42_acknowledged","ticket"})
    if body["excluded_42_acknowledged"] is not True or type(body["ticket"]) is not dict:
        raise PlayerExperimentError("G8_IMPORT_ACK_REQUIRED",400)
    raw_body={k:body[k] for k in ("raw_file","profile_id","sheet","source_column")}; raw=_raw_body(raw_body)
    operation_id=_uuid(operation_id,operation=True)
    submitted_raw_sha256=hashlib.sha256(raw).hexdigest()

    def existing_result(existing):
        selected_input = dict(existing.selected_input)
        stored_request_sha = selected_input.pop("canonical_request_sha256", None)
        sealed_if_match = selected_input.pop("sealed_if_match", None)
        submitted_ticket = body["ticket"]
        exact_request = (
            existing.actor_identifier == principal.actor_identifier
            and if_match == sealed_if_match
            and type(submitted_ticket) is dict
            and submitted_ticket == selected_input
            and submitted_ticket.get("operation_id") == str(operation_id)
            and submitted_ticket.get("workspace_id") == str(workspace.pk)
            and submitted_ticket.get("experiment_id") == str(experiment.pk)
            and submitted_ticket.get("raw_file_sha256") == submitted_raw_sha256
            and submitted_ticket.get("byte_length") == len(raw)
            and submitted_ticket.get("profile_id") == body["profile_id"]
            and submitted_ticket.get("sheet") == body["sheet"]
            and submitted_ticket.get("source_column") == body["source_column"]
            and submitted_ticket.get("preview_sha256") == body["preview_sha256"]
        )
        request_sha = _request_hash(
            IMPORT_CONTRACT, experiment_id=str(experiment.pk),
            ticket=selected_input, ack=True, if_match=if_match,
        )
        if not exact_request or stored_request_sha != request_sha:
            raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
        receipt=existing.intended_changes.get("receipt")
        if type(receipt) is not dict: raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
        return PlayerOperationResult(existing,canonical_receipt_bytes(receipt),True)

    with transaction.atomic():
        principal=assessment_principal(user); project,workspace,experiment=_experiment_scope(principal,experiment_id,lock=True)
        existing=ImportRun.objects.select_for_update().filter(pk=operation_id,workspace=workspace,target_experiment=experiment).first()
        if existing is not None:
            return existing_result(existing)
        if ImportRun.objects.filter(pk=operation_id).exists() or AuditEvent.objects.filter(pk=operation_id).exists():
            raise PlayerExperimentError("PLAYER_OPERATION_KEY_REUSE")
        if experiment.status!=ExperimentStatus.DRAFT: raise PlayerExperimentError("G8_EXPERIMENT_NOT_DRAFT")
        if (
            ActorElementAssessment.objects.filter(experiment=experiment).exists()
            or ParameterValue.objects.filter(actor_element_assessment__experiment=experiment).exists()
            or ImportRun.objects.filter(target_experiment=experiment,status=ImportRunStatus.COMMITTED).exists()
        ): raise PlayerExperimentError("G8_IMPORT_NONEMPTY_EXPERIMENT")
        _validator(if_match,body["preview_sha256"])
        try:
            reparsed=preview_profile_xlsx(raw,profile_id=body["profile_id"],sheet=body["sheet"],source_column=body["source_column"])
        except XlsxImportProfileError as exc:
            raise PlayerExperimentError(exc.code,400,exc.detail) from exc
        ticket_expected={"contract":"FOUNDATION_PLAYER_XLSX_IMPORT_TICKET_V1","contract_version":VERSION,"workspace_id":str(workspace.pk),"experiment_id":str(experiment.pk),"operation_id":str(operation_id),"raw_file_sha256":reparsed["raw_file_sha256"],"byte_length":reparsed["byte_length"],"profile_id":body["profile_id"],"profile_sha256":reparsed["profile_sha256"],"sheet":body["sheet"],"source_column":body["source_column"],"crosswalk_lineage":reparsed["crosswalk_lineage"],"preview_sha256":body["preview_sha256"],"request_plan_sha256":reparsed["request_plan_sha256"]}
        if body["ticket"]!=ticket_expected or reparsed["preview_sha256"]!=body["preview_sha256"]:
            raise PlayerExperimentError("G8_IMPORT_PRECONDITION_FAILED",412)
        request_sha=_request_hash(
            IMPORT_CONTRACT, experiment_id=str(experiment.pk), ticket=ticket_expected,
            ack=True, if_match=if_match,
        )
        if reparsed["diagnostics"] or not reparsed["creates"]:
            raise PlayerExperimentError("G8_IMPORT_PRECONDITION_FAILED",412)
        profile,actors,elements,times,definitions,roles=_validated_import_projection(
            project, workspace, reparsed,
        )
        grouped: dict[str,list[dict[str,Any]]]={}
        for item in reparsed["creates"]: grouped.setdefault(item["profile"]["assessment_code"],[]).append(item)
        assessments={}
        for base_code,items in grouped.items():
            p=items[0]["profile"]; actor=actors.get(p["source_manifest_actor_code"]); element=elements.get(p["source_manifest_element_code"]); ts=times.get(p["time_slice_code"])
            role=[roles[(actor.pk,element.pk)]] if actor and element and (actor.pk,element.pk) in roles else []
            if (
                not actor or not element or not ts or len(role)!=1
                or str(actor.source_manifest_entity_id)!=p["source_manifest_actor_uuid"]
                or str(element.source_manifest_entity_id)!=p["source_manifest_element_uuid"]
                or str(ts.pk)!=p["time_slice_manifest_uuid"]
                or ts.cutoff_date.isoformat()!=p["cutoff_date"]
                or role[0].code!=p["source_manifest_role_code"]
                or str(role[0].source_manifest_entity_id)!=p["source_manifest_role_uuid"]
            ):
                raise PlayerExperimentError("G8_TARGET_MAPPING_MISMATCH")
            confidence={"POS":"UNKNOWN","SAL":"UNKNOWN"}
            for item in items: confidence[item["profile"]["canonical_parameter_code"]]=item["confidence_category"]
            assessment=ActorElementAssessment(
                id=uuid5(operation_id,"assessment:"+base_code),workspace=workspace,actor=actor,element=element,time_slice=ts,experiment=experiment,assessment_set=experiment.assessment_set,
                code=f"G8-{experiment.pk.hex[:12]}-{base_code}",version="1.0.0",reference_statement="",reference_statement_incomplete=True,
                status=AssessmentRecordStatus.PROVISIONAL_PRE_METHOD_FREEZE if any(i["status"]==ValueStatus.PROVISIONAL for i in items) else AssessmentRecordStatus.UNKNOWN,
                confidence_level=ConfidenceLevel.UNKNOWN,knowledge_cutoff=date.fromisoformat(p["cutoff_date"]),method_version=experiment.method_version,
                provenance={"contract":IMPORT_CONTRACT,"profile_id":PROFILE_ID,"raw_file_sha256":reparsed["raw_file_sha256"],"role_code":p["source_manifest_role_code"],"role_uuid":p["source_manifest_role_uuid"],"parameter_confidence":confidence,"review_flags":{"POS":"REFERENCE_STATEMENT_REVIEW_REQUIRED","SAL":"SCALE_CONSTRUCT_REVIEW_REQUIRED"}},
            ); assessment.save(force_insert=True); assessments[base_code]=assessment
        values=[]
        for item in reparsed["creates"]:
            p=item["profile"]; assessment=assessments[p["assessment_code"]]; definition=definitions.get(p["canonical_parameter_code"])
            if (
                definition is None
                or str(definition.source_manifest_parameter_id)!=p["canonical_parameter_uuid"]
                or p["source_manifest_role_uuid"] not in {
                    str(value) for value in definition.applicability.get("actor_element_role_ids", [])
                }
            ): raise PlayerExperimentError("G8_TARGET_MAPPING_MISMATCH")
            value=ParameterValue(
                id=uuid5(operation_id,"value:"+p["parameter_value_code"]),project=project,workspace=workspace,time_slice=assessment.time_slice,
                assessment_set=experiment.assessment_set,actor_element_assessment=assessment,parameter_definition=definition,target_type=TargetType.ACTOR_ELEMENT_ASSESSMENT,target_id=assessment.pk,
                code=f"G8-{experiment.pk.hex[:12]}-{p['parameter_value_code']}",version="1.0.0",status=item["status"],temporal_status=AssessmentTemporalStatus.UNKNOWN,
                value=item["value"],note=item["note"],confidence=None,range_min=None,range_max=None,rationale=item["rationale"],
            ); value.save(force_insert=True); values.append(value)
        snapshot=reparsed["import_snapshot"]
        response_core={"contract":IMPORT_CONTRACT,"version":VERSION,"operation_id":str(operation_id),"project_id":str(project.pk),"workspace_id":str(workspace.pk),"experiment_id":str(experiment.pk),"assessment_set_id":str(experiment.assessment_set_id),"raw_file_sha256":reparsed["raw_file_sha256"],"byte_length":reparsed["byte_length"],"profile_sha256":reparsed["profile_sha256"],"preview_sha256":reparsed["preview_sha256"],"request_plan_sha256":reparsed["request_plan_sha256"],"snapshot_contract":snapshot["schema"],"snapshot_sha256":snapshot["snapshot_sha256"],"snapshot_source_rows":snapshot["source_row_count"],"created_assessments":len(assessments),"created_values":len(values),"row_counts":reparsed["counts"],"excluded_rows":{"METHOD_BLOCKED":18,"RECODING_REQUIRED":24,"classification":"BETA_COMPATIBILITY_INPUT_ONLY"},"canonical_request_sha256":request_sha,"original_http_status":201}
        response={**response_core,"receipt_sha256":hashlib.sha256(_canonical(response_core)).hexdigest()}
        run=ImportRun(
            id=operation_id,code=f"G8-IMPORT-{operation_id}",version=VERSION,project=project,workspace=workspace,definition_version=workspace.definition_version,package_scope=ImportPackageScope.WORKSPACE,target_experiment=experiment,target_assessment_set=experiment.assessment_set,
            package_format="XLSX",package_id=PROFILE_ID,package_version=VERSION,schema_version=VERSION,template_version="2.0",method_version=experiment.method_version or "UNSPECIFIED",ontology_version="V4-TERM-2.0",dataset_version="A5-v0.1",checksum=reparsed["raw_file_sha256"],adapter="domain.services.xlsx_adapter",
            selected_input={**ticket_expected,"sealed_if_match":if_match,"canonical_request_sha256":request_sha},selected_source_column=body["source_column"],source_identity_map={"profile_sha256":profile["file_sha256"],"source_artifacts":profile["source_artifacts"],"accepted_manifest":profile["accepted_manifest"]},correction_lineage=[],
            intended_changes={"source_snapshot":snapshot,"receipt":response},row_counts=reparsed["counts"],warnings=reparsed["missing_ids"],errors=[],allow_nonempty=False,status=ImportRunStatus.COMMITTED,actor_identifier=principal.actor_identifier,committed_at=timezone.now(),
        ); run.save(force_insert=True)
        _audit(operation_id=operation_id,project=project,workspace=workspace,principal=principal,contract=IMPORT_CONTRACT,entity_id=run.pk,action=AuditAction.IMPORT,request_sha=request_sha,payload={"import":response},assessment_set=experiment.assessment_set)
        return PlayerOperationResult(run,canonical_receipt_bytes(response),False)


def recover_import(*, user, experiment_id, operation_id):
    principal=assessment_principal(user); _,workspace,experiment=_experiment_scope(principal,experiment_id)
    row=ImportRun.objects.filter(pk=_uuid(operation_id),workspace=workspace,target_experiment=experiment).first()
    if row is None: raise PlayerExperimentError("PLAYER_NOT_FOUND",404)
    receipt=row.intended_changes.get("receipt")
    if type(receipt) is not dict: raise PlayerExperimentError("PLAYER_OPERATION_RESULT_DRIFT")
    return receipt


def comparison(*, user, workspace_id, include_archived=False):
    principal=assessment_principal(user); project,workspace=_projection_workspace(principal,workspace_id)
    experiments=Experiment.objects.filter(workspace=workspace,experiment_type=ExperimentType.ASSESSMENT,metadata__contract=EXPERIMENT_CONTRACT).select_related("expert_profile","assessment_set")
    if not include_archived:
        experiments=experiments.exclude(status=ExperimentStatus.ARCHIVED)
    values=ParameterValue.objects.filter(actor_element_assessment__experiment__in=experiments).select_related("actor_element_assessment__actor","actor_element_assessment__element","actor_element_assessment__experiment__expert_profile","parameter_definition","time_slice")
    return {"contract":"FOUNDATION_PLAYER_EXPERIMENT_COMPARISON_V1","project_id":str(project.pk),"workspace_id":str(workspace.pk),"aggregation":None,"values":[{**_value_dto(row),"actor_code":row.actor_element_assessment.actor.code,"element_code":row.actor_element_assessment.element.code,"experiment_name":row.actor_element_assessment.experiment.name,"expert_name":row.actor_element_assessment.experiment.expert_profile.display_name,"color":row.actor_element_assessment.experiment.color} for row in values]}
