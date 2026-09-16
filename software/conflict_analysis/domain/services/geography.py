"""Foundation Project Geography V1: admitted, append-only location receipts.

The revision is itself the operation receipt (including actor, request digest
and predecessor). No synthetic workspace is created to attach a project write
to the existing workspace/definition-only AuditEvent contract.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from uuid import UUID, NAMESPACE_URL, uuid5

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, OperationalError, transaction

from domain.enums import LocationKind, LocationSourceKind
from domain.models import GeographicArea, Project, ProjectLocationHead, ProjectLocationRevision, _canonical_geography_write
from domain.services.analysis_admission import analysis_principal, analysis_location_editor_group_name
from domain.services.analysis_contracts import AnalysisError, METHOD_STATE, canonical_bytes, sha256

DATASET = "CA_CENTRAL_ASIA_POLITICAL_V1"
VERSION = "1.0.1"
POLICY = "CA_BOUNDARY_POLICY_V1"
CONTRACT = "FOUNDATION_PROJECT_LOCATION_V1"
CATALOG = (
    ("KAZ", "Казахстан", "Kazakhstan", "ADM0", None),
    # NE_ID from the pinned Admin 1 source; ISO KZ-MAN / ADM1_CODE KAZ-3236.
    ("1159314605", "Мангистауская область", "Mangghystau", "ADM1", "KAZ"),
)
MESSAGES = {
    "GEOGRAPHY_AUTHENTICATION_REQUIRED": "Требуется действующая сессия.",
    "GEOGRAPHY_NOT_FOUND": "Проект недоступен или не найден.",
    "GEOGRAPHY_REQUEST_INVALID": "Проверьте поля и заголовки запроса.",
    "GEOGRAPHY_PERMISSION_DENIED": "Изменение локализации не разрешено.",
    "GEOGRAPHY_ETAG_CONFLICT": "Локализация изменилась. Обновите данные и сравните версии.",
    "GEOGRAPHY_OPERATION_CONFLICT": "Идентификатор операции уже использован.",
    "GEOGRAPHY_INTEGRITY_CONFLICT": "Конфликт целостности локализации.",
    "GEOGRAPHY_OPERATION_FAILED": "Операция не завершена. Попробуйте повторить запрос.",
}


class GeographyError(RuntimeError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(MESSAGES[code])


def invalid():
    raise GeographyError("GEOGRAPHY_REQUEST_INVALID", 400)


def admit(*, user, project_id, write=False):
    try:
        principal, project = analysis_principal(user=user, project_id=project_id)
    except AnalysisError as exc:
        raise GeographyError(exc.code.replace("ANALYSIS_", "GEOGRAPHY_"), exc.status) from exc
    persisted = get_user_model().objects.get(pk=principal.user_id)
    group = persisted.groups.filter(name=analysis_location_editor_group_name(project.pk)).first()
    can_edit = bool(group and not group.permissions.exists())
    if write and not can_edit:
        raise GeographyError("GEOGRAPHY_PERMISSION_DENIED", 403)
    return principal, project, can_edit


def area_id(feature):
    return uuid5(NAMESPACE_URL, f"{DATASET}:{VERSION}:{feature}")


def install_pinned_geographic_areas():
    """Explicit deployment operation; GETs never seed or repair rows."""
    with transaction.atomic(), _canonical_geography_write():
        for feature, name_ru, name_local, level, parent in CATALOG:
            values = dict(code=f"GEO-{feature}", version=VERSION, dataset_code=DATASET,
                          dataset_version=VERSION, feature_id=feature, area_level=level,
                          name_ru=name_ru, name_local=name_local, iso_alpha2="KZ",
                          parent_id=area_id(parent) if parent else None,
                          boundary_policy_version=POLICY,
                          metadata={"source": "Natural Earth", "source_tag": "v5.1.2",
                                    "source_commit": "f1890d9f152c896d250a77557a5751a93d494776",
                                    "source_theme_version": "5.1.1", "license": "Public Domain",
                                    "source_path": "geojson/ne_10m_admin_0_countries.geojson" if level == "ADM0" else "geojson/ne_10m_admin_1_states_provinces.geojson",
                                    "geometry_in_database": False})
            existing = GeographicArea.objects.filter(pk=area_id(feature)).first()
            if existing:
                if any(getattr(existing, key) != value for key, value in values.items()):
                    raise GeographyError("GEOGRAPHY_INTEGRITY_CONFLICT")
            else:
                GeographicArea.objects.create(id=area_id(feature), **values)


def map_descriptor():
    descriptor = dict(dataset_code=DATASET, dataset_version=VERSION, boundary_policy_version=POLICY, manifest_sha256=None)
    manifest = files("analysis_dashboard").joinpath("static/analysis_dashboard/maps/MAP_DATASET_MANIFEST.json")
    if manifest.is_file():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        digest = payload.pop("manifest_sha256")
        if sha256(payload) != digest or any(payload[k] != descriptor[k] for k in ("dataset_code", "dataset_version", "boundary_policy_version")):
            raise GeographyError("GEOGRAPHY_INTEGRITY_CONFLICT")
        descriptor["manifest_sha256"] = digest
    return descriptor


def _decimal(value, bound):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)) or len(str(value)) > 40:
        invalid()
    try:
        result = Decimal(str(value))
        if not result.is_finite() or not -bound <= result <= bound or result != result.quantize(Decimal("0.0000001")):
            invalid()
        return result
    except (InvalidOperation, ValueError):
        invalid()


def decimal_string(value):
    if value == 0:
        return "0"
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def _uuid(value):
    try:
        parsed = UUID(str(value))
        if str(parsed) != str(value):
            invalid()
        return parsed
    except (ValueError, TypeError):
        invalid()


def validate_body(body):
    required = {"latitude", "longitude", "location_kind", "uncertainty_radius_m", "area_id", "label", "source_kind", "source_reference", "rationale", "supersedes_id", "boundary_dataset_code", "boundary_dataset_version", "boundary_policy_version"}
    if not isinstance(body, dict) or set(body) != required:
        invalid()
    result = dict(body)
    result["latitude"] = _decimal(body["latitude"], 90)
    result["longitude"] = _decimal(body["longitude"], 180)
    if body["location_kind"] not in LocationKind.values or body["source_kind"] not in LocationSourceKind.values:
        invalid()
    radius = body["uncertainty_radius_m"]
    if radius is not None and (type(radius) is not int or not 0 <= radius <= 20_000_000):
        invalid()
    if body["location_kind"] != "POINT" and not radius:
        invalid()
    for key, maximum in (("label", 255), ("source_reference", 1024), ("rationale", 4000)):
        if not isinstance(body[key], str) or len(body[key]) > maximum or "\x00" in body[key]:
            invalid()
        try:
            body[key].encode("utf-8")
        except UnicodeError:
            invalid()
    if not body["rationale"].strip():
        invalid()
    if (body["boundary_dataset_code"], body["boundary_dataset_version"], body["boundary_policy_version"]) != (DATASET, VERSION, POLICY):
        invalid()
    for key in ("area_id", "supersedes_id"):
        if body[key] is not None:
            result[key] = _uuid(body[key])
    return result


def revision_dto(row):
    if row is None:
        return None
    return {
        "id": str(row.pk), "project_id": str(row.project_id), "code": row.code, "version": row.version,
        "supersedes_id": str(row.supersedes_id) if row.supersedes_id else None,
        "latitude": decimal_string(row.latitude), "longitude": decimal_string(row.longitude),
        "location_kind": row.location_kind, "uncertainty_radius_m": row.uncertainty_radius_m,
        "area": {"id": str(row.area_id), "name_ru": row.area.name_ru, "feature_id": row.area.feature_id} if row.area_id else None,
        "label": row.label, "source_kind": row.source_kind, "source_reference": row.source_reference,
        "rationale": row.rationale, "actor_identifier": row.actor_identifier,
        "operation_id": str(row.operation_id), "request_sha256": row.request_sha256,
        "boundary_dataset_code": row.boundary_dataset_code, "boundary_dataset_version": row.boundary_dataset_version,
        "boundary_policy_version": row.boundary_policy_version, "created_at": row.created_at.isoformat(),
    }


def head_etag(project_id, row):
    return sha256({"project_id": str(project_id), "head": revision_dto(row)})


def _snapshot(**values):
    core = {"contract": CONTRACT, **values}
    return {**core, "response_sha256": sha256(core)}


def read_project_location(*, user, project_id):
    principal, project, can_edit = admit(user=user, project_id=project_id)
    head = ProjectLocationHead.objects.select_related("revision__area").filter(project=project).first()
    row = head.revision if head else None
    etag = head_etag(project.pk, row)
    if head and head.etag_sha256 != etag:
        raise GeographyError("GEOGRAPHY_INTEGRITY_CONFLICT")
    areas = [{"id": str(area_id(f)), "feature_id": f, "name_ru": ru} for f, ru, *_ in CATALOG]
    return _snapshot(project_id=str(project.pk), user_id=str(principal.user_id), can_edit=can_edit,
                     head=revision_dto(row), etag_sha256=etag, areas=areas, map=map_descriptor(), method_state=METHOD_STATE)


def read_project_location_history(*, user, project_id, limit=50):
    _, project, _ = admit(user=user, project_id=project_id)
    if type(limit) is not int or not 1 <= limit <= 100:
        invalid()
    # Follow the accepted chain. This stays newest-first even if two recorded
    # timestamps are equal or the host clock moves backwards.
    head = ProjectLocationHead.objects.filter(project=project).first()
    next_id = head.revision_id if head else None
    rows, seen = [], set()
    while next_id and len(rows) < limit:
        if next_id in seen:
            raise GeographyError("GEOGRAPHY_INTEGRITY_CONFLICT")
        seen.add(next_id)
        row = ProjectLocationRevision.objects.select_related("area").get(pk=next_id, project=project)
        rows.append(revision_dto(row))
        next_id = row.supersedes_id
    return _snapshot(project_id=str(project.pk), revisions=rows, has_more=bool(next_id), limit=limit)


def create_project_location_revision(*, user, project_id, body, if_match, operation_id):
    principal, project, _ = admit(user=user, project_id=project_id, write=True)
    values = validate_body(body)
    operation = _uuid(operation_id)
    canonical_request = {key: decimal_string(value) if isinstance(value, Decimal) else str(value) if isinstance(value, UUID) else value for key, value in values.items()}
    request_sha = sha256({"project_id": str(project.pk), "actor_identifier": principal.actor_identifier, "body": canonical_request})
    if not isinstance(if_match, str) or len(if_match) != 66 or if_match[0] != '"' or if_match[-1] != '"':
        invalid()
    try:
        with transaction.atomic(), _canonical_geography_write():
            Project.objects.select_for_update().get(pk=project.pk)
            # Lock only the head row. Joining the optional area would ask
            # PostgreSQL to lock the nullable side of an outer join.
            head = ProjectLocationHead.objects.select_for_update().filter(project=project).first()
            previous = head.revision if head else None
            # Exact retries are recognized before stale preconditions. The
            # receipt, not today's head, is returned for an accepted replay.
            receipt = ProjectLocationRevision.objects.select_related("area").filter(operation_id=operation).first()
            if receipt:
                if receipt.project_id != project.pk or receipt.request_sha256 != request_sha:
                    raise GeographyError("GEOGRAPHY_OPERATION_CONFLICT")
                return _snapshot(project_id=str(project.pk), head=revision_dto(receipt), etag_sha256=head_etag(project.pk, receipt)), True
            if if_match != f'"{head_etag(project.pk, previous)}"':
                raise GeographyError("GEOGRAPHY_ETAG_CONFLICT")
            if values["supersedes_id"] != (previous.pk if previous else None):
                raise GeographyError("GEOGRAPHY_INTEGRITY_CONFLICT")
            if values["area_id"] is not None:
                allowed = {area_id(item[0]) for item in CATALOG}
                if values["area_id"] not in allowed or not GeographicArea.objects.filter(pk=values["area_id"], dataset_code=DATASET, dataset_version=VERSION, boundary_policy_version=POLICY).exists():
                    invalid()
            row = ProjectLocationRevision.objects.create(
                id=uuid5(NAMESPACE_URL, f"geography:{operation}"), code=f"GEO-{operation}", version=VERSION,
                project=project, operation_id=operation, request_sha256=request_sha,
                actor_identifier=principal.actor_identifier, **values,
            )
            if head is None:
                head = ProjectLocationHead(project=project)
            head.revision = row
            head.etag_sha256 = head_etag(project.pk, row)
            head.save()
            return _snapshot(project_id=str(project.pk), head=revision_dto(row), etag_sha256=head.etag_sha256), False
    except OperationalError as exc:
        # SQLite serializes writers. A losing transaction never partially
        # publishes a receipt; clients reload before submitting a new revision.
        if "locked" in str(exc).lower() or "serializ" in str(exc).lower():
            raise GeographyError("GEOGRAPHY_ETAG_CONFLICT") from exc
        raise GeographyError("GEOGRAPHY_OPERATION_FAILED", 503) from exc
    except (IntegrityError, ValidationError) as exc:
        raise GeographyError("GEOGRAPHY_INTEGRITY_CONFLICT") from exc
