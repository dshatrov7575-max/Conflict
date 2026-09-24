"""Foundation-owned Player reads and atomic, scope-bound create/replay gateways.

The Product receives DTOs only. No read repairs projection, Help or topology.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from uuid import RFC_4122, UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from domain.enums import (
    AssessmentProjectionStatus, AuditAction, AuditActorType, AuditScope,
    ExperimentType, HelpApplicationScope, PublicationStatus,
)
from domain.models import (
    AuditEvent, Experiment, Project, ProjectDefinitionVersion, ProjectPublication,
    ProjectWorkspace, TimeSlice,
)
from domain.services.help_topics import HelpTopicResolutionError, resolve_help_topic
from domain.services.player_help_catalog import (
    PlayerHelpCatalogError, bind_player_help, require_player_help_catalog,
    verify_player_help_bindings,
)
from domain.services.player_projection import (
    AssessmentProjectionConflict, AssessmentProjectionError, WORKSPACE_CREATE_CONTRACT,
    materialize_workspace_assessment_projection,
    require_complete_workspace_assessment_projection,
    verify_workspace_assessment_projection,
)
from domain.services.project_definitions import (
    hash_project_definition_manifest_v1, project_access_group_name,
)


VERSION = "1.0.0"
SLICE_CREATE_CONTRACT = "FOUNDATION_PLAYER_TIME_SLICE_CREATE_V1"
PLAYER_REQUIRED_PERMISSIONS = frozenset({
    "domain.view_project", "domain.view_projectdefinitionversion",
    "domain.view_projectworkspace", "domain.view_timeslice", "domain.view_experiment",
    "domain.view_expertprofile", "domain.view_assessmentset", "domain.view_helptopic",
    "domain.add_projectworkspace", "domain.add_timeslice",
})
_FORBIDDEN_MUTABLE_MODELS = frozenset({
    "project", "projectdefinitionversion", "projectworkspace", "timeslice",
})
_FORBIDDEN_WRITE_MODELS = frozenset({
    "experiment", "expertprofile", "assessmentset", "parametervalue",
    "actorelementassessment", "assessmentconfidence", "assessmentvalue",
})
_WORKSPACE_KEYS = frozenset({
    "id", "code", "version", "name", "definition_id",
    "definition_manifest_hash", "is_default", "metadata",
})
_SLICE_KEYS = frozenset({"id", "code", "version", "name", "cutoff_date", "order", "metadata"})

PLAYER_ERROR_MESSAGES = {
    "PLAYER_AUTHENTICATION_REQUIRED": "Требуется действующая сессия пользователя.",
    "PLAYER_PERMISSION_DENIED": "Действие запрещено текущими правами доступа.",
    "PLAYER_NOT_FOUND": "Объект недоступен или не найден.",
    "PLAYER_REQUEST_INVALID": "Запрос не соответствует точному контракту Player.",
    "PLAYER_METHOD_NOT_ALLOWED": "Этот метод запроса недоступен.",
    "PLAYER_CSRF_FAILED": "Проверка защиты запроса не пройдена.",
    "PLAYER_STALE": "Контрольная сумма не совпадает с закреплённой версией.",
    "PLAYER_PROJECT_TOPOLOGY_INVALID": "Опубликованное состояние проекта не подтверждено.",
    "PLAYER_OPERATION_KEY_REUSE": "Идентификатор операции уже связан с другим запросом.",
    "PLAYER_IDENTITY_CONFLICT": "Запрошенная идентичность уже занята.",
    "PLAYER_OPERATION_RESULT_DRIFT": "Сохранённый результат операции не совпадает с исходным.",
    "PLAYER_HELP_CATALOG_CONFLICT": "Точный комплект справки не подтверждён.",
    "ASSESSMENT_PROJECTION_NOT_PROVEN": "Проекция рабочего пространства не подтверждена.",
    "ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT": "Целостность проекции рабочего пространства не подтверждена.",
    "PLAYER_OPERATION_FAILED": "Операция не завершена; автоматическое повторение запрещено.",
}


class PlayerError(RuntimeError):
    def __init__(self, code: str, status: int = 409):
        self.code = code
        self.status = status
        super().__init__(PLAYER_ERROR_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class PlayerPrincipal:
    user_id: object
    actor_identifier: str
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class PlayerOperationResult:
    receipt: AuditEvent
    body: bytes
    replayed: bool


def canonical_receipt_bytes(payload: object) -> bytes:
    """One serializer for fresh/replayed persisted JSON, independent of jsonb order."""
    return json.dumps(
        payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _sha(payload: object) -> str:
    return hashlib.sha256(canonical_receipt_bytes(payload)).hexdigest()


def _snapshot(contract: str, **payload) -> dict:
    core = {"contract": contract, "version": VERSION, **payload}
    return {**core, "response_sha256": _sha(core)}


def _uuid(value: object, *, operation: bool = False) -> UUID:
    try:
        result = UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400) from exc
    if str(result) != str(value) or (
        operation and (result.version != 4 or result.variant != RFC_4122)
    ):
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    return result


def _forbidden_permission(permission: str) -> bool:
    if not permission.startswith("domain."):
        return False
    code = permission.removeprefix("domain.")
    if code.startswith("studio_"):
        return True
    action, separator, model = code.partition("_")
    return bool(separator) and (
        (model in _FORBIDDEN_MUTABLE_MODELS and action in {"change", "delete"})
        or (model in _FORBIDDEN_WRITE_MODELS and action in {"add", "change", "delete"})
    )


def player_principal(user) -> PlayerPrincipal:
    if not getattr(user, "is_authenticated", False) or getattr(user, "pk", None) is None:
        raise PlayerError("PLAYER_AUTHENTICATION_REQUIRED", 401)
    # Discard Django's per-instance permission cache on every operation/replay.
    try:
        persisted = get_user_model()._default_manager.get(pk=user.pk)
    except get_user_model().DoesNotExist as exc:
        raise PlayerError("PLAYER_AUTHENTICATION_REQUIRED", 401) from exc
    if not persisted.is_active:
        raise PlayerError("PLAYER_AUTHENTICATION_REQUIRED", 401)
    permissions = frozenset(persisted.get_all_permissions())
    if (
        persisted.is_staff or persisted.is_superuser
        or not PLAYER_REQUIRED_PERMISSIONS.issubset(permissions)
        or any(_forbidden_permission(permission) for permission in permissions)
    ):
        raise PlayerError("PLAYER_PERMISSION_DENIED", 403)
    return PlayerPrincipal(persisted.pk, f"django-user:{persisted.pk}", permissions)


def _project(principal: PlayerPrincipal, project_id, *, lock: bool = False) -> Project:
    project_id = _uuid(project_id)
    try:
        user = get_user_model()._default_manager.get(pk=principal.user_id)
    except get_user_model().DoesNotExist as exc:
        raise PlayerError("PLAYER_AUTHENTICATION_REQUIRED", 401) from exc
    group = user.groups.filter(name=project_access_group_name(project_id)).first()
    if group is None or group.permissions.exists():
        raise PlayerError("PLAYER_NOT_FOUND", 404)
    rows = Project.objects.select_for_update() if lock else Project.objects
    try:
        return rows.get(pk=project_id)
    except Project.DoesNotExist as exc:
        raise PlayerError("PLAYER_NOT_FOUND", 404) from exc


def _definition(principal: PlayerPrincipal, definition_id, *, project=None, lock=False, verify_manifest=True):
    definition_id = _uuid(definition_id)
    if project is None:
        project_id = ProjectDefinitionVersion.objects.filter(pk=definition_id).values_list(
            "project_id", flat=True,
        ).first()
        if project_id is None:
            raise PlayerError("PLAYER_NOT_FOUND", 404)
        project = _project(principal, project_id, lock=lock)
    rows = ProjectDefinitionVersion.objects.select_for_update() if lock else ProjectDefinitionVersion.objects
    try:
        definition = rows.get(pk=definition_id, project=project)
    except ProjectDefinitionVersion.DoesNotExist as exc:
        raise PlayerError("PLAYER_NOT_FOUND", 404) from exc
    # Scope precedes any disclosure of lifecycle/manifest identity.
    if definition.publication_status != PublicationStatus.PUBLISHED:
        raise PlayerError("PLAYER_NOT_FOUND", 404)
    if verify_manifest:
        _verify_manifest(project, definition)
    return project, definition


def _verify_manifest(project, definition):
    try:
        exact = hash_project_definition_manifest_v1(definition.manifest, project=project)
    except (ValidationError, TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise PlayerError("PLAYER_PROJECT_TOPOLOGY_INVALID") from exc
    if exact != definition.manifest_hash:
        raise PlayerError("PLAYER_PROJECT_TOPOLOGY_INVALID")


def _workspace(principal: PlayerPrincipal, workspace_id, *, lock=False):
    workspace_id = _uuid(workspace_id)
    project_id = ProjectWorkspace.objects.filter(pk=workspace_id).values_list(
        "project_id", flat=True,
    ).first()
    if project_id is None:
        raise PlayerError("PLAYER_NOT_FOUND", 404)
    project = _project(principal, project_id, lock=lock)
    # Consistent global order: Project -> Definition -> Workspace.
    definition_id = ProjectWorkspace.objects.filter(
        pk=workspace_id, project=project,
    ).values_list("definition_version_id", flat=True).first()
    if definition_id is None:
        raise PlayerError("PLAYER_NOT_FOUND", 404)
    _, definition = _definition(
        principal, definition_id, project=project, lock=lock, verify_manifest=False,
    )
    rows = ProjectWorkspace.objects.select_for_update() if lock else ProjectWorkspace.objects
    try:
        workspace = rows.get(pk=workspace_id, project=project)
    except ProjectWorkspace.DoesNotExist as exc:
        raise PlayerError("PLAYER_NOT_FOUND", 404) from exc
    workspace.definition_version = definition
    workspace.project = project
    # Do not trust/short-circuit the stored pin: the frozen FD08 verifier exposes
    # drift as a non-analysis diagnostic Workspace, and guards all slice writes.
    return project, workspace


def admit_player_scope(*, user, kind: str, identity):
    """Authorization/object admission for the HTTP layer before CSRF/body/receipts."""
    principal = player_principal(user)
    if kind == "project":
        return _project(principal, identity)
    if kind == "definition":
        return _definition(principal, identity)[1]
    if kind == "workspace":
        return _workspace(principal, identity)[1]
    raise PlayerError("PLAYER_REQUEST_INVALID", 400)


def _project_dto(project):
    return {name: str(getattr(project, name)) for name in ("id", "code", "version", "name")}


def _definition_dto(definition):
    return {
        "id": str(definition.pk), "project_id": str(definition.project_id),
        "code": definition.code, "version": definition.version,
        "publication_status": definition.publication_status, "is_current": definition.is_current,
        "manifest": definition.manifest, "manifest_hash": definition.manifest_hash,
        "schema_version": definition.schema_version, "semantic_version": definition.semantic_version,
        "construct_version": definition.construct_version,
        "supersedes_id": str(definition.supersedes_id) if definition.supersedes_id else None,
        "published_at": definition.published_at.isoformat() if definition.published_at else None,
        "published_by": definition.published_by,
    }


def _workspace_dto(workspace):
    verification = verify_workspace_assessment_projection(workspace)
    return {
        "id": str(workspace.pk), "project_id": str(workspace.project_id),
        "code": workspace.code, "version": workspace.version, "name": workspace.name,
        "definition_id": str(workspace.definition_version_id),
        "definition_manifest_hash": workspace.definition_manifest_hash,
        "is_default": workspace.is_default,
        "assessment_projection_status": verification.status,
        "assessment_projection_sha256": verification.projection_sha256 if verification.complete else None,
    }


def _slice_dto(row):
    return {
        "id": str(row.pk), "project_id": str(row.project_id), "workspace_id": str(row.workspace_id),
        "code": row.code, "version": row.version, "name": row.name,
        "cutoff_date": row.cutoff_date.isoformat(), "order": row.order,
    }


def list_player_definitions(*, user, project_id):
    principal = player_principal(user)
    project = _project(principal, project_id)
    definitions = list(ProjectDefinitionVersion.objects.filter(
        project=project, publication_status=PublicationStatus.PUBLISHED,
    ).order_by("published_at", "version", "pk"))
    for definition in definitions:
        _verify_manifest(project, definition)
    return _snapshot("FOUNDATION_PLAYER_DEFINITIONS_V1", project=_project_dto(project),
                     definitions=[_definition_dto(row) for row in definitions])


def open_player_definition(*, user, definition_id):
    project, definition = _definition(player_principal(user), definition_id)
    return _snapshot("FOUNDATION_PLAYER_DEFINITION_V1", project=_project_dto(project),
                     definition=_definition_dto(definition))


def list_player_workspaces(*, user, project_id):
    project = _project(player_principal(user), project_id)
    workspaces = ProjectWorkspace.objects.filter(
        project=project, definition_version__project=project,
        definition_version__publication_status=PublicationStatus.PUBLISHED,
    ).select_related(
        "project", "definition_version",
    ).order_by("code", "pk")
    return _snapshot("FOUNDATION_PLAYER_WORKSPACES_V1", project=_project_dto(project),
                     workspaces=[_workspace_dto(row) for row in workspaces])


def open_player_workspace(*, user, workspace_id):
    project, workspace = _workspace(player_principal(user), workspace_id)
    payload = _workspace_dto(workspace)
    return _snapshot("FOUNDATION_PLAYER_WORKSPACE_V1", project=_project_dto(project),
                     workspace=payload, definition=(
                         None if payload["assessment_projection_status"] == AssessmentProjectionStatus.INTEGRITY_CONFLICT
                         else _definition_dto(workspace.definition_version)
                     ))


def list_player_time_slices(*, user, workspace_id):
    project, workspace = _workspace(player_principal(user), workspace_id)
    rows = TimeSlice.objects.filter(workspace=workspace, project=project).order_by("order", "cutoff_date", "pk")
    return _snapshot("FOUNDATION_PLAYER_TIME_SLICES_V1", workspace_id=str(workspace.pk),
                     time_slices=[_slice_dto(row) for row in rows])


def list_player_experiments(*, user, workspace_id):
    _, workspace = _workspace(player_principal(user), workspace_id)
    rows = Experiment.objects.filter(
        workspace=workspace, experiment_type=ExperimentType.ASSESSMENT,
    ).select_related("expert_profile", "assessment_set").order_by("order", "code", "pk")
    result = []
    for row in rows:
        if row.expert_profile.workspace_id != workspace.pk or row.assessment_set.workspace_id != workspace.pk:
            raise PlayerError("ASSESSMENT_PROJECTION_INTEGRITY_CONFLICT")
        result.append({
            "id": str(row.pk), "name": row.name, "status": row.status,
            "order": row.order, "color": row.color,
            "expert_profile": {"id": str(row.expert_profile_id), "code": row.expert_profile.code,
                               "version": row.expert_profile.version, "name": row.expert_profile.display_name},
            "assessment_set": {"id": str(row.assessment_set_id), "code": row.assessment_set.code,
                               "version": row.assessment_set.version},
        })
    return _snapshot("FOUNDATION_PLAYER_EXPERIMENTS_V1", workspace_id=str(workspace.pk), experiments=result)


def player_help(*, user, workspace_id, ui_key, locale, version):
    _, workspace = _workspace(player_principal(user), workspace_id)
    try:
        topic = resolve_help_topic(application_scope=HelpApplicationScope.PLAYER,
                                   workspace=workspace, ui_key=ui_key, locale=locale, version=version)
    except HelpTopicResolutionError as exc:
        raise PlayerError("PLAYER_NOT_FOUND", 404) from exc
    payload = {name: getattr(topic, name) for name in (
        "stable_key", "locale", "version", "title", "sanitized_html", "content_sha256",
        "construct_version", "term_version",
    )}
    payload["id"] = str(topic.pk)
    return _snapshot("FOUNDATION_PLAYER_HELP_V1", workspace_id=str(workspace.pk),
                     ui_key=ui_key, locale=locale, help_topic=payload)


def _validate_body(body, *, workspace: bool) -> dict:
    expected = _WORKSPACE_KEYS if workspace else _SLICE_KEYS
    if type(body) is not dict or set(body) != expected:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    if type(body["metadata"]) is not dict or body["metadata"] != {}:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    if type(body["id"]) is not str:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    _uuid(body["id"])
    for key, maximum in (("code", 128), ("version", 64), ("name", 255)):
        if type(body[key]) is not str or not body[key].strip() or len(body[key]) > maximum:
            raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    if workspace:
        if type(body["definition_id"]) is not str:
            raise PlayerError("PLAYER_REQUEST_INVALID", 400)
        _uuid(body["definition_id"])
        if body["is_default"] is not False or not isinstance(body["definition_manifest_hash"], str) or (
            re.fullmatch(r"[0-9a-f]{64}", body["definition_manifest_hash"]) is None
        ):
            raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    else:
        if type(body["order"]) is not int or not 0 <= body["order"] <= 2147483647:
            raise PlayerError("PLAYER_REQUEST_INVALID", 400)
        try:
            if type(body["cutoff_date"]) is not str or date.fromisoformat(body["cutoff_date"]).isoformat() != body["cutoff_date"]:
                raise ValueError("Non-canonical date")
        except (ValueError, TypeError) as exc:
            raise PlayerError("PLAYER_REQUEST_INVALID", 400) from exc
    return body


def _validator(if_match, exact_hash):
    if not isinstance(if_match, str) or re.fullmatch(r'"[0-9a-f]{64}"', if_match) is None:
        raise PlayerError("PLAYER_REQUEST_INVALID", 400)
    if if_match != f'"{exact_hash}"':
        raise PlayerError("PLAYER_STALE")


def _request_hash(*, contract, route, project_id, body, if_match):
    return _sha({"contract": contract, "version": VERSION, "method": "POST", "route": route,
                 "project_id": str(project_id), "body": body, "if_match": if_match})


def _require_topology(project, selected_definition):
    defaults = list(ProjectWorkspace.objects.select_for_update().filter(project=project, is_default=True))
    current = list(ProjectDefinitionVersion.objects.filter(project=project, is_current=True))
    initial = list(ProjectPublication.objects.filter(project=project, initial_workspace_id__isnull=False))
    if len(defaults) != 1 or len(current) != 1 or len(initial) != 1:
        raise PlayerError("PLAYER_PROJECT_TOPOLOGY_INVALID")
    default = defaults[0]
    try:
        default_definition = ProjectDefinitionVersion.objects.get(pk=default.definition_version_id, project=project)
    except ProjectDefinitionVersion.DoesNotExist as exc:
        raise PlayerError("PLAYER_PROJECT_TOPOLOGY_INVALID") from exc
    if (
        default_definition.publication_status != PublicationStatus.PUBLISHED
        or default.definition_manifest_hash != default_definition.manifest_hash
        or initial[0].initial_workspace_id != default.pk
        or initial[0].definition_version_id != default_definition.pk
        or current[0].publication_status != PublicationStatus.PUBLISHED
    ):
        raise PlayerError("PLAYER_PROJECT_TOPOLOGY_INVALID")
    # ProjectPublication is the accepted canonical publication receipt, whether
    # reached through Studio publication or the accepted package-bootstrap lane.
    for definition in {row.pk: row for row in (default_definition, current[0], selected_definition)}.values():
        _verify_manifest(project, definition)
        receipts = list(ProjectPublication.objects.filter(project=project, definition_version=definition))
        if len(receipts) != 1 or (
            not receipts[0].actor_identifier.strip()
            or not isinstance(receipts[0].validation_result, dict)
            or receipts[0].validation_result.get("valid") is not True
        ):
            raise PlayerError("PLAYER_PROJECT_TOPOLOGY_INVALID")


def _same_workspace_body(row, body):
    return (
        str(row.pk) == body["id"] and row.code == body["code"] and row.version == body["version"]
        and row.name == body["name"] and str(row.definition_version_id) == body["definition_id"]
        and row.definition_manifest_hash == body["definition_manifest_hash"]
        and row.is_default is False and row.metadata == body["metadata"]
    )


def _persisted_result(receipt, *, replayed):
    receipt.refresh_from_db()
    return PlayerOperationResult(receipt, canonical_receipt_bytes(receipt.after), replayed)


def create_player_workspace(*, user, project_id, operation_id, if_match, body):
    principal = player_principal(user)
    _project(principal, project_id)
    body = _validate_body(body, workspace=True)
    operation_id = _uuid(operation_id, operation=True)
    _validator(if_match, body["definition_manifest_hash"])
    request_sha = _request_hash(contract=WORKSPACE_CREATE_CONTRACT,
        route=f"/api/foundation/player/projects/{project_id}/workspaces/",
        project_id=project_id, body=body, if_match=if_match)
    with transaction.atomic():
        principal = player_principal(user)
        project = _project(principal, project_id, lock=True)
        _, definition = _definition(principal, body["definition_id"], project=project, lock=True)
        _validator(if_match, definition.manifest_hash)
        _require_topology(project, definition)
        require_player_help_catalog()
        # Authorized project/contract lane only: never disclose a foreign receipt.
        receipt = AuditEvent.objects.select_for_update().filter(
            pk=operation_id, project=project, entity_type=WORKSPACE_CREATE_CONTRACT,
        ).first()
        if receipt is not None:
            if (
                receipt.actor_identifier != principal.actor_identifier
                or not isinstance(receipt.after, dict)
                or receipt.after.get("canonical_request_sha256") != request_sha
            ):
                raise PlayerError("PLAYER_OPERATION_KEY_REUSE")
            row = ProjectWorkspace.objects.select_for_update().filter(
                pk=receipt.workspace_id, project=project,
            ).first()
            if row is None or not _same_workspace_body(row, body):
                raise PlayerError("PLAYER_OPERATION_RESULT_DRIFT")
            result = materialize_workspace_assessment_projection(
                row, operation_id, principal.actor_identifier,
                receipt_contract=WORKSPACE_CREATE_CONTRACT, canonical_request_sha256=request_sha,
            )
            verify_player_help_bindings(result.workspace)
            return _persisted_result(result.receipt, replayed=True)
        try:
            with transaction.atomic():
                row = ProjectWorkspace(
                    id=_uuid(body["id"]), project=project, definition_version=definition,
                    definition_manifest_hash=body["definition_manifest_hash"], code=body["code"],
                    version=body["version"], name=body["name"], is_default=False, metadata={},
                )
                row.save(force_insert=True)
        except (ValidationError, IntegrityError) as exc:
            occupied = ProjectWorkspace.objects.filter(
                Q(pk=_uuid(body["id"])) | Q(project=project, code=body["code"]),
            ).exists()
            if occupied:
                raise PlayerError("PLAYER_IDENTITY_CONFLICT") from exc
            if isinstance(exc, ValidationError):
                raise PlayerError("PLAYER_REQUEST_INVALID", 400) from exc
            raise
        try:
            result = materialize_workspace_assessment_projection(
                row, operation_id, principal.actor_identifier,
                receipt_contract=WORKSPACE_CREATE_CONTRACT, canonical_request_sha256=request_sha,
            )
        except AssessmentProjectionConflict as exc:
            # Only after the frozen projection transaction has failed: a
            # persisted operation occupancy proves bounded key reuse. Do not
            # inspect or return the foreign receipt, or parse exception text.
            if AuditEvent.objects.filter(pk=operation_id).exists():
                raise PlayerError("PLAYER_OPERATION_KEY_REUSE") from exc
            raise
        bind_player_help(result.workspace)
        return _persisted_result(result.receipt, replayed=False)


def _slice_receipt_core(*, row, workspace, operation_id, principal, request_sha, occurred_at):
    return {
        "contract": SLICE_CREATE_CONTRACT, "version": VERSION,
        "operation_id": str(operation_id), "audit_event_id": str(operation_id),
        "actor_type": AuditActorType.HUMAN, "actor_identifier": principal.actor_identifier,
        "project_id": str(workspace.project_id), "workspace_id": str(workspace.pk),
        "definition_id": str(workspace.definition_version_id),
        "manifest_sha256": workspace.definition_manifest_hash, "slice_id": str(row.pk),
        "canonical_request_sha256": request_sha,
        "created_slice": {**_slice_dto(row), "metadata": row.metadata},
        "occurred_at": occurred_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
        "original_http_status": 201,
    }


def create_player_time_slice(*, user, workspace_id, operation_id, if_match, body):
    principal = player_principal(user)
    project, workspace = _workspace(principal, workspace_id)
    body = _validate_body(body, workspace=False)
    operation_id = _uuid(operation_id, operation=True)
    _validator(if_match, workspace.definition_manifest_hash)
    request_sha = _request_hash(contract=SLICE_CREATE_CONTRACT,
        route=f"/api/foundation/player/workspaces/{workspace_id}/time-slices/",
        project_id=project.pk, body=body, if_match=if_match)
    with transaction.atomic():
        principal = player_principal(user)
        project, workspace = _workspace(principal, workspace_id, lock=True)
        _validator(if_match, workspace.definition_manifest_hash)
        # FD08's generic COMPLETE guard intentionally uses one conflict class.
        # G7 additionally exposes the frozen NOT_PROVEN diagnostic separately.
        verification = verify_workspace_assessment_projection(workspace)
        if verification.status == AssessmentProjectionStatus.NOT_PROVEN:
            raise PlayerError("ASSESSMENT_PROJECTION_NOT_PROVEN")
        require_complete_workspace_assessment_projection(workspace)
        receipt = AuditEvent.objects.select_for_update().filter(
            pk=operation_id, project=project, workspace=workspace, entity_type=SLICE_CREATE_CONTRACT,
        ).first()
        if receipt is not None:
            after = receipt.after
            if (
                receipt.actor_identifier != principal.actor_identifier
                or not isinstance(after, dict)
                or after.get("canonical_request_sha256") != request_sha
            ):
                raise PlayerError("PLAYER_OPERATION_KEY_REUSE")
            row = TimeSlice.objects.select_for_update().filter(
                pk=receipt.entity_id, workspace=workspace, project=project,
            ).first()
            if row is None:
                raise PlayerError("PLAYER_OPERATION_RESULT_DRIFT")
            expected_core = _slice_receipt_core(
                row=row, workspace=workspace, operation_id=operation_id, principal=principal,
                request_sha=request_sha, occurred_at=receipt.occurred_at,
            )
            expected = {**expected_core, "receipt_sha256": _sha(expected_core)}
            if (
                after != expected or receipt.scope != AuditScope.WORKSPACE
                or receipt.definition_version_id is not None or receipt.action != AuditAction.CREATE
                or receipt.actor_type != AuditActorType.HUMAN or receipt.before is not None
                or receipt.code != f"PLAYER-SLICE-{operation_id}" or receipt.version != VERSION
                or any(after["created_slice"].get(key) != value for key, value in body.items())
            ):
                raise PlayerError("PLAYER_OPERATION_RESULT_DRIFT")
            return _persisted_result(receipt, replayed=True)
        try:
            with transaction.atomic():
                row = TimeSlice(
                    id=_uuid(body["id"]), project=project, workspace=workspace,
                    code=body["code"], version=body["version"], name=body["name"],
                    cutoff_date=date.fromisoformat(body["cutoff_date"]), order=body["order"], metadata={},
                )
                # Canonical instance path only. No bulk/raw bypass of COMPLETE.
                row.save(force_insert=True)
        except (IntegrityError, ValidationError) as exc:
            occupied = TimeSlice.objects.filter(
                Q(pk=_uuid(body["id"])) | Q(workspace=workspace, code=body["code"])
                | Q(workspace=workspace, cutoff_date=body["cutoff_date"]),
            ).exists()
            if occupied:
                raise PlayerError("PLAYER_IDENTITY_CONFLICT") from exc
            if isinstance(exc, ValidationError):
                raise PlayerError("PLAYER_REQUEST_INVALID", 400) from exc
            raise
        occurred_at = timezone.now()
        core = _slice_receipt_core(row=row, workspace=workspace, operation_id=operation_id,
                                  principal=principal, request_sha=request_sha, occurred_at=occurred_at)
        payload = {**core, "receipt_sha256": _sha(core)}
        try:
            with transaction.atomic():
                receipt = AuditEvent.objects.create(
                    id=operation_id, code=f"PLAYER-SLICE-{operation_id}", version=VERSION,
                    project=project, workspace=workspace, scope=AuditScope.WORKSPACE,
                    action=AuditAction.CREATE, actor_type=AuditActorType.HUMAN,
                    actor_identifier=principal.actor_identifier, entity_type=SLICE_CREATE_CONTRACT,
                    entity_id=row.pk, before=None, after=payload, occurred_at=occurred_at,
                )
        except (IntegrityError, ValidationError) as exc:
            # After savepoint rollback, classify only proven operation occupancy.
            # The outer transaction rolls back the newly created slice in full.
            if AuditEvent.objects.filter(pk=operation_id).exists():
                raise PlayerError("PLAYER_OPERATION_KEY_REUSE") from exc
            raise
        return _persisted_result(receipt, replayed=False)
