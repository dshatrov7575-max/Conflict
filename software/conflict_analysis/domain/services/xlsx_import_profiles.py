"""Checksum-bound G8 XLSX import profile and deterministic preview parser."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from importlib.resources import files
from typing import Any, Mapping

from domain.services.xlsx_adapter import FoundationXlsxAdapterError, read_xlsx_tables

PROFILE_FILENAME = "kz_zhanaozen_expert_v2_a5_v0_1.json"
PROFILE_ID = "KZ_ZHANAOZEN_EXPERT_V2_A5_0_1"
CONFIDENCE_MAP = {
    "Высокая": "HIGH", "Средняя": "MEDIUM", "Низкая": "LOW",
    "Неизвестно": "UNKNOWN", "": "UNKNOWN",
}
ABSENT_STATUSES = frozenset({"UNKNOWN", "INSUFFICIENT_DATA", "NOT_APPLICABLE", "OPEN_METHOD"})
_SECTION_RE = re.compile(r"^(?:ГЛАВА \d{4}:|\d{4}\.[0-9]+ )")


class XlsxImportProfileError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def load_profile() -> Mapping[str, Any]:
    base = files("domain").joinpath("import_profiles")
    raw = base.joinpath(PROFILE_FILENAME).read_bytes()
    sidecar = base.joinpath(PROFILE_FILENAME + ".sha256").read_text(encoding="ascii")
    digest = hashlib.sha256(raw).hexdigest()
    if sidecar != f"{digest}  {PROFILE_FILENAME}\n":
        raise XlsxImportProfileError("G8_PROFILE_HASH_MISMATCH", "Profile sidecar mismatch.")
    try:
        profile = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise XlsxImportProfileError("G8_PROFILE_INVALID", "Profile JSON is invalid.") from exc
    if profile.get("profile_id") != PROFILE_ID or profile.get("counts") != {
        "assessment_contexts": 144, "method_blocked": 18, "records": 330,
        "recoding_required": 24, "transfer_with_review": 288,
    }:
        raise XlsxImportProfileError("G8_PROFILE_INVALID", "Profile identity/counts drifted.")
    records = profile.get("records")
    if not isinstance(records, list) or len(records) != 330:
        raise XlsxImportProfileError("G8_PROFILE_INVALID", "Profile requires 330 records.")
    ids = [row.get("legacy_id") for row in records]
    if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != 330:
        raise XlsxImportProfileError("G8_PROFILE_INVALID", "Profile row identities are not exact.")
    required = {
        "ordinal", "legacy_id", "a5_v4_id", "migration_record_id",
        "source_time_slice", "time_slice_code", "cutoff_date",
        "source_manifest_actor_code", "source_manifest_actor_uuid",
        "source_manifest_element_code", "source_manifest_element_uuid",
        "source_manifest_role_code", "source_manifest_role_uuid",
        "canonical_parameter_code", "canonical_parameter_uuid",
        "assessment_code", "parameter_value_code", "migration_status", "transfer_rule",
    }
    for index, row in enumerate(records, 1):
        if type(row) is not dict or not required.issubset(row) or row["ordinal"] != index:
            raise XlsxImportProfileError("G8_PROFILE_INVALID", "Profile record shape/order drifted.")
        if row["migration_status"] == "TRANSFER_WITH_REVIEW":
            if any(row.get(key) in {None, ""} for key in (
                "source_manifest_actor_code", "source_manifest_actor_uuid",
                "source_manifest_element_code", "source_manifest_element_uuid",
                "source_manifest_role_code", "source_manifest_role_uuid",
                "canonical_parameter_code", "canonical_parameter_uuid",
                "assessment_code", "parameter_value_code",
            )) or row["canonical_parameter_code"] not in {"POS", "SAL"}:
                raise XlsxImportProfileError("G8_PROFILE_INVALID", "Transfer target is incomplete.")
    payload = dict(profile)
    payload_hash = payload.pop("profile_payload_sha256", None)
    if payload_hash != hashlib.sha256(_canonical(payload)).hexdigest():
        raise XlsxImportProfileError("G8_PROFILE_HASH_MISMATCH", "Profile payload hash mismatch.")
    return {**profile, "file_sha256": digest, "file_bytes": len(raw)}


def _number(value: str, parameter: str) -> int:
    if value.strip() != value or not value:
        raise XlsxImportProfileError("G8_XLSX_VALUE_INVALID", "Numeric value has invalid whitespace.")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise XlsxImportProfileError("G8_XLSX_VALUE_INVALID", "Value is not a finite number.") from exc
    if not number.is_finite() or number != number.to_integral_value():
        raise XlsxImportProfileError("G8_XLSX_VALUE_INVALID", "Profile requires an integer value.")
    result = int(number)
    if parameter == "POS" and not -10 <= result <= 10:
        raise XlsxImportProfileError("G8_XLSX_VALUE_OUT_OF_RANGE", "POS is outside -10..10.")
    if parameter == "SAL" and not 0 <= result <= 10:
        raise XlsxImportProfileError("G8_XLSX_VALUE_OUT_OF_RANGE", "SAL is outside 0..10.")
    return result


def preview_profile_xlsx(
    raw: bytes, *, profile_id: str, sheet: str, source_column: str,
) -> Mapping[str, Any]:
    profile = load_profile()
    if profile_id != PROFILE_ID or sheet != profile["input"]["sheet"]:
        raise XlsxImportProfileError("G8_XLSX_MAPPING_INVALID", "Exact profile and sheet are required.")
    allowed_columns = set(profile["input"]["source_columns"].values())
    if source_column not in allowed_columns:
        raise XlsxImportProfileError("G8_XLSX_MAPPING_INVALID", "Selected source column is not allowed.")
    try:
        tables = read_xlsx_tables(raw)
    except FoundationXlsxAdapterError as exc:
        raise XlsxImportProfileError("G8_XLSX_REJECTED", str(exc)) from exc
    sheet_rows = tables.get(sheet.strip().upper())
    if sheet_rows is None:
        raise XlsxImportProfileError("G8_XLSX_MAPPING_INVALID", "Exact selected sheet is absent.")
    headers = profile["input"]["headers"]
    expected = {index: value for index, value in enumerate(headers)}
    known = {row["legacy_id"]: row for row in profile["records"]}
    source_rows: dict[str, dict[str, Any]] = {}
    header_seen = False
    diagnostics: list[dict[str, Any]] = []
    for position, cells in enumerate(sheet_rows, 1):
        values = {index: cells.get(index, "") for index in range(len(headers))}
        if values == expected:
            header_seen = True
            continue
        nonempty = [value for value in values.values() if value != ""]
        first = values[0]
        if not header_seen or (len(nonempty) == 1 and first not in known):
            if (
                len(nonempty) == 1 and isinstance(first, str) and len(first) <= 500
                and (first.startswith("Экспертная форма оценки")
                     or first.startswith("Порядок работы:") or _SECTION_RE.match(first))
            ):
                continue
            diagnostics.append({"code": "G8_XLSX_PREAMBLE_INVALID", "row": position})
            continue
        if first == "ID параметра":
            diagnostics.append({"code": "G8_XLSX_HEADER_DRIFT", "row": position})
            continue
        if first not in known:
            diagnostics.append({"code": "G8_XLSX_UNKNOWN_ID", "row": position})
            continue
        if first in source_rows:
            diagnostics.append({"code": "G8_XLSX_DUPLICATE_ID", "row": position, "id": first})
            continue
        source_rows[first] = {
            "cells": {headers[index]: value for index, value in values.items()},
            "row_number": position,
        }
    if not header_seen:
        diagnostics.append({"code": "G8_XLSX_HEADER_MISSING"})
    missing = [value for value in known if value not in source_rows]
    creates: list[dict[str, Any]] = []
    snapshot: list[dict[str, Any]] = []
    counts = {"valid_numeric": 0, "explicit_unknown": 0, "empty": 0,
              "transfer_with_review": 288, "method_blocked": 18,
              "recoding_required": 24, "comments": 0, "urls": 0}
    for identity, mapped in known.items():
        source_record = source_rows.get(identity)
        source = source_record["cells"] if source_record else None
        selected = source.get(source_column, "") if source else ""
        source_status = source.get("Статус ИИ", "") if source and source_column == "ИИ_Значение" else ""
        confidence_source = source.get("Уверенность ИИ", "") if source and source_column == "ИИ_Значение" else ""
        rationale = source.get("Обоснование ИИ", "") if source and source_column == "ИИ_Значение" else ""
        note = source.get("Примечание эксперта", "") if source else ""
        confidence = CONFIDENCE_MAP.get(confidence_source)
        if confidence is None:
            diagnostics.append({"code": "G8_XLSX_CONFIDENCE_INVALID", "id": identity})
            confidence = "UNKNOWN"
        if note:
            counts["comments"] += 1
        if source_record is not None:
            column_index = headers.index(source_column) + 1
            letters, number = "", column_index
            while number:
                number, remainder = divmod(number - 1, 26)
                letters = chr(65 + remainder) + letters
            snapshot.append({
                "legacy_id": identity, "a5_v4_id": mapped["a5_v4_id"],
                "migration_status": mapped["migration_status"], "transfer_rule": mapped["transfer_rule"],
                "selected_value": selected if selected != "" else None,
                "source_status": source_status or None, "source_confidence": confidence,
                "rationale_candidate": rationale or None, "comment_candidate": note or None,
                "source_row": source_record["row_number"], "source_id_cell": f"A{source_record['row_number']}",
                "source_value_cell": f"{letters}{source_record['row_number']}",
                "candidate_class": "BETA_COMPATIBILITY_INPUT_ONLY"
                if mapped["migration_status"] != "TRANSFER_WITH_REVIEW" else "TRANSFER_WITH_REVIEW",
            })
        if mapped["migration_status"] != "TRANSFER_WITH_REVIEW" or source is None:
            continue
        if selected == "":
            if source_column == "ИИ_Значение" and source_status == "Неизвестно":
                value, status = None, "UNKNOWN"; counts["explicit_unknown"] += 1
            else:
                counts["empty"] += 1
                continue
        else:
            if source_column == "ИИ_Значение" and source_status != "Предварительная оценка ИИ":
                diagnostics.append({"code": "G8_XLSX_STATUS_INVALID", "id": identity})
                continue
            value = _number(selected, mapped["canonical_parameter_code"])
            status = "PROVISIONAL"; counts["valid_numeric"] += 1
        if status == "PROVISIONAL" and not rationale:
            rationale = (
                f"Numeric value imported from column {source_column}; "
                "no separate rationale was supplied in the source row."
            )
        creates.append({
            "profile": mapped, "status": status, "value": value,
            "confidence_category": confidence, "rationale": rationale, "note": note,
        })
    core = {
        "contract": "FOUNDATION_PLAYER_XLSX_PREVIEW_V1", "version": "1.0.0",
        "raw_file_sha256": hashlib.sha256(raw).hexdigest(), "byte_length": len(raw),
        "profile_id": profile_id, "profile_sha256": profile["file_sha256"],
        "sheet": sheet, "source_column": source_column,
        "counts": counts, "rows_to_create": len(creates),
        "assessment_contexts_to_create": len({row["profile"]["assessment_code"] for row in creates}),
        "missing_ids": missing,
        "diagnostics": sorted(diagnostics, key=lambda row: _canonical(row)),
        "request_plan_sha256": hashlib.sha256(_canonical(creates)).hexdigest(),
    }
    complete_file = len(source_rows) == 330 and not missing and not any(
        row["code"] in {"G8_XLSX_UNKNOWN_ID", "G8_XLSX_DUPLICATE_ID"}
        for row in diagnostics
    )
    snapshot_core = {
        "schema": "POLARIZATION_V1_IMPORT_SNAPSHOT_V1" if complete_file else None,
        "complete_file": complete_file, "source_row_count": len(snapshot),
        "raw_file_sha256": core["raw_file_sha256"], "byte_length": core["byte_length"],
        "profile_id": profile_id, "profile_sha256": profile["file_sha256"],
        "sheet": sheet, "source_column": source_column,
        "source_artifacts": profile["source_artifacts"],
        "time_slices": sorted({
            (row["source_time_slice"], row["time_slice_code"], row["cutoff_date"])
            for row in profile["records"]
        }),
        "classification": {"TRANSFER_WITH_REVIEW": 288, "METHOD_BLOCKED": 18,
                           "RECODING_REQUIRED": 24, "BETA_COMPATIBILITY_INPUT_ONLY": 42},
        "records": snapshot,
    }
    import_snapshot = {
        **snapshot_core,
        "snapshot_sha256": hashlib.sha256(_canonical(snapshot_core)).hexdigest(),
    }
    return {
        **core, "preview_sha256": hashlib.sha256(_canonical(core)).hexdigest(),
        "creates": creates, "import_snapshot": import_snapshot,
    }
