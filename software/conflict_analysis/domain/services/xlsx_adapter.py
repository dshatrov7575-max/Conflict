"""Layout-decoupled XLSX-to-Foundation DTO adapter.

Only stable technical sheet/header keys are interpreted.  Visible Russian labels,
column positions, formulas and workbook-calculated values are never identities.
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping
from xml.etree import ElementTree


_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CELL_REF_RE = re.compile(r"^([A-Z]+)[0-9]+$")
MAX_XLSX_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 512
MAX_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_SHEETS = 128
MAX_ROWS_PER_SHEET = 100_000
MAX_COLUMNS = 512
MAX_CELLS_PER_SHEET = 1_000_000
MAX_SHARED_STRINGS = 1_000_000

CANONICAL_SECTIONS = (
    "project_definition_versions",
    "time_slices",
    "actors",
    "actor_relations",
    "analytical_elements",
    "actor_element_roles",
    "expert_profiles",
    "experiments",
    "assessment_sets",
    "actor_element_assessments",
    "parameter_definitions",
    "parameter_values",
    "sources",
    "documents",
    "document_versions",
    "document_contents",
    "text_fragments",
    "facts",
    "fact_evidence_links",
    "assessment_fact_links",
    "parameter_value_fact_links",
    "power_profiles",
    "power_components",
    "power_component_fact_links",
    "chat_conversations",
    "chat_messages",
    "chat_citations",
    "gaps",
    "help_topics",
    "ui_help_bindings",
    "terminology_entries",
    "legacy_term_mappings",
    "compatibility_receipts",
)

PRE_FREEZE_PROFILE = "V4_EXPERT_XLS_IMPORT_CONTRACT_PRE_FREEZE_V1"
PRE_FREEZE_SHEETS = {
    "README",
    "META",
    "ACTORS",
    "ELEMENTS",
    "TIME_SLICES",
    "SOURCES",
    "DOCUMENTS",
    "FRAGMENTS",
    "FACTS",
    "FACT_EVIDENCE",
    "ASSESSMENTS",
    "ASSESSMENT_EVIDENCE",
    "POWER_PROFILE",
    "GAPS",
    "QA",
    "LISTS",
    "CHANGELOG",
}

STABLE_SHEET_ALIASES = {
    "ELEMENTS": "analytical_elements",
    "FRAGMENTS": "text_fragments",
    "FACT_EVIDENCE": "fact_evidence_links",
    "ASSESSMENTS": "actor_element_assessments",
    "ASSESSMENT_EVIDENCE": "assessment_fact_links",
    "POWER_PROFILE": "power_profiles",
}
for _section in CANONICAL_SECTIONS:
    STABLE_SHEET_ALIASES.setdefault(_section.upper(), _section)

_JSON_FIELDS = {
    "manifest",
    "metadata",
    "provenance",
    "scale_metadata",
    "selector",
    "selected_input",
    "range_min",
    "range_max",
    "value",
    "validation_result",
    "participants",
    "display_metadata",
    "scale_min",
    "scale_max",
    "confidence",
}
_BOOLEAN_FIELDS = {
    "independent",
    "is_current",
    "reference_statement_incomplete",
    "is_after_cutoff",
}
_INTEGER_FIELDS = {"order", "sequence", "quote_start", "quote_end", "start_offset", "end_offset"}
_PRESERVE_TEXT_FIELDS = {
    "content",
    "exact_text",
    "quote_text",
    "statement",
    "fact_statement",
    "reference_statement",
    "rationale",
    "sanitized_html",
    "description",
    "note",
    "source_notes",
    "fact_notes",
    "translation_text",
    "resolution",
    "required_behavior",
    "error",
}
_EMPTY_STRING_FIELDS = {
    "provider",
    "model_name",
    "provider_request_id",
    "title",
    "color",
    "method_version",
    "ontology_version",
    "dataset_version",
    "template_version",
    "publisher",
    "independence_group",
    "homepage_url",
    "canonical_url",
    "capture_url",
    "media_type",
    "page",
    "section",
    "label",
    "identity_key",
    "canonical_ru_acronym",
    "exact_en_acronym",
    "validated_by",
    "published_by",
}
_IGNORED_FORMULA_SHEETS = {"README", "QA", "LISTS", "CHANGELOG"}


class FoundationXlsxAdapterError(ValueError):
    pass


def adapt_foundation_xlsx(raw: Any) -> Mapping[str, Any]:
    """Read a technical-key XLSX workbook and return an unsealed canonical DTO."""

    path = Path(raw)
    if path.suffix.lower() != ".xlsx":
        raise FoundationXlsxAdapterError(
            "Only OOXML .xlsx is supported; legacy binary .xls must use an explicit adapter."
        )
    try:
        if path.stat().st_size > MAX_XLSX_BYTES:
            raise FoundationXlsxAdapterError("XLSX input exceeds the configured size limit.")
        with zipfile.ZipFile(path) as archive:
            _validate_archive(archive)
            sheets = _read_workbook(archive)
    except FoundationXlsxAdapterError:
        raise
    except (
        OSError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        ElementTree.ParseError,
        IndexError,
        KeyError,
        ValueError,
        OverflowError,
    ) as exc:
        raise FoundationXlsxAdapterError(f"Cannot parse XLSX input: {exc}.") from exc
    if "META" not in sheets:
        raise FoundationXlsxAdapterError("XLSX requires the stable technical META sheet.")
    meta = _meta_values(sheets["META"])
    if "workbook_schema_version" in meta:
        unknown_sheets = set(sheets) - PRE_FREEZE_SHEETS
        if unknown_sheets:
            raise FoundationXlsxAdapterError(
                f"{PRE_FREEZE_PROFILE} contains unknown technical sheets "
                f"{sorted(unknown_sheets)}."
            )
        required = {
            "package_id",
            "workbook_schema_version",
            "dataset_version",
            "case_id",
            "case_name",
            "coder_id",
            "coder_type",
            "assessment_set_id",
            "method_version",
            "ontology_version",
            "source_packet_hash",
            "cutoff_date",
            "created_at",
            "workbook_status",
        }
        missing = required - set(meta)
        if missing:
            raise FoundationXlsxAdapterError(
                f"{PRE_FREEZE_PROFILE} META is missing keys {sorted(missing)}."
            )
        return {
            "__xlsx_profile__": PRE_FREEZE_PROFILE,
            "meta": {key: meta[key] for key in sorted(meta)},
            "sheets": {
                key: _table_objects(key, rows)
                for key, rows in sheets.items()
                if key not in _IGNORED_FORMULA_SHEETS | {"META"}
            },
        }
    required_meta = {
        "format",
        "format_version",
        "package_id",
        "schema_version",
        "template_version",
        "method_version",
        "ontology_version",
        "dataset_version",
        "workspace",
    }
    missing = required_meta - set(meta)
    if missing:
        raise FoundationXlsxAdapterError(f"META is missing keys {sorted(missing)}.")
    package: dict[str, Any] = {
        key: _coerce_cell(key, meta[key])
        for key in required_meta
    }
    for section in CANONICAL_SECTIONS:
        package[section] = []
    seen_sections: set[str] = set()
    for sheet_key, rows in sheets.items():
        if sheet_key in {"README", "META", "QA", "LISTS", "CHANGELOG"}:
            continue
        section = STABLE_SHEET_ALIASES.get(sheet_key)
        if section is None:
            continue
        if section in seen_sections:
            raise FoundationXlsxAdapterError(
                f"Multiple sheets map to canonical section {section!r}."
            )
        seen_sections.add(section)
        package[section] = _table_objects(sheet_key, rows)
    return package


def _validate_archive(archive: zipfile.ZipFile) -> None:
    members = archive.infolist()
    if len(members) > MAX_ARCHIVE_ENTRIES:
        raise FoundationXlsxAdapterError("XLSX contains too many archive entries.")
    names = [member.filename for member in members]
    if len(names) != len(set(names)):
        raise FoundationXlsxAdapterError("XLSX contains duplicate archive member names.")
    total = sum(member.file_size for member in members)
    if total > MAX_UNCOMPRESSED_BYTES:
        raise FoundationXlsxAdapterError("XLSX uncompressed size exceeds the configured limit.")
    if any(member.file_size > MAX_MEMBER_BYTES for member in members):
        raise FoundationXlsxAdapterError("XLSX contains an oversized archive member.")
    required = {"xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
    missing = required - set(names)
    if missing:
        raise FoundationXlsxAdapterError(f"XLSX is missing required members {sorted(missing)}.")


def _read_workbook(archive: zipfile.ZipFile) -> dict[str, list[dict[int, str]]]:
    shared = _shared_strings(archive)
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {
        relation.attrib["Id"]: relation.attrib["Target"]
        for relation in relations.findall(f"{{{_PKG_REL_NS}}}Relationship")
    }
    sheet_nodes = workbook.findall(f".//{{{_MAIN_NS}}}sheet")
    if len(sheet_nodes) > MAX_SHEETS:
        raise FoundationXlsxAdapterError("XLSX contains too many sheets.")
    result: dict[str, list[dict[int, str]]] = {}
    for sheet in sheet_nodes:
        name = sheet.attrib["name"].strip().upper()
        if not name or name in result:
            raise FoundationXlsxAdapterError(f"XLSX contains duplicate/empty sheet key {name!r}.")
        relation_id = sheet.attrib[f"{{{_REL_NS}}}id"]
        if relation_id not in targets:
            raise FoundationXlsxAdapterError(
                f"Sheet {name!r} has an unresolved workbook relationship."
            )
        target = PurePosixPath(targets[relation_id])
        if target.is_absolute():
            member = str(target).lstrip("/")
        else:
            member = str(PurePosixPath("xl") / target)
        normalized = PurePosixPath(member)
        if ".." in normalized.parts or not str(normalized).startswith("xl/"):
            raise FoundationXlsxAdapterError(f"Sheet {name!r} has an unsafe relationship target.")
        if str(normalized) not in archive.namelist():
            raise FoundationXlsxAdapterError(f"Sheet {name!r} XML member is missing.")
        result[name] = _worksheet_rows(
            archive.read(str(normalized)),
            shared,
            reject_formulas=name not in _IGNORED_FORMULA_SHEETS,
        )
    return result


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    values = [
        "".join(node.text or "" for node in item.findall(f".//{{{_MAIN_NS}}}t"))
        for item in root.findall(f"{{{_MAIN_NS}}}si")
    ]
    if len(values) > MAX_SHARED_STRINGS:
        raise FoundationXlsxAdapterError("XLSX contains too many shared strings.")
    return values


def _column_index(cell_reference: str) -> int:
    match = _CELL_REF_RE.match(cell_reference)
    if match is None:
        raise FoundationXlsxAdapterError(f"Invalid cell reference {cell_reference!r}.")
    result = 0
    for char in match.group(1):
        result = result * 26 + ord(char) - ord("A") + 1
    index = result - 1
    if index >= MAX_COLUMNS:
        raise FoundationXlsxAdapterError("XLSX column limit exceeded.")
    return index


def _worksheet_rows(
    xml: bytes,
    shared: list[str],
    *,
    reject_formulas: bool = True,
) -> list[dict[int, str]]:
    root = ElementTree.fromstring(xml)
    result: list[dict[int, str]] = []
    rows = root.findall(f".//{{{_MAIN_NS}}}row")
    if len(rows) > MAX_ROWS_PER_SHEET:
        raise FoundationXlsxAdapterError("XLSX row limit exceeded.")
    cell_count = 0
    for row in rows:
        values: dict[int, str] = {}
        for cell in row.findall(f"{{{_MAIN_NS}}}c"):
            cell_count += 1
            if cell_count > MAX_CELLS_PER_SHEET:
                raise FoundationXlsxAdapterError("XLSX cell limit exceeded.")
            if reject_formulas and cell.find(f"{{{_MAIN_NS}}}f") is not None:
                raise FoundationXlsxAdapterError(
                    "Formula cells are forbidden in canonical import sheets."
                )
            index = _column_index(cell.attrib["r"])
            if index in values:
                raise FoundationXlsxAdapterError(
                    f"XLSX row contains duplicate cell reference {cell.attrib['r']!r}."
                )
            cell_type = cell.attrib.get("t")
            if cell_type == "inlineStr":
                value = "".join(
                    node.text or "" for node in cell.findall(f".//{{{_MAIN_NS}}}t")
                )
            else:
                node = cell.find(f"{{{_MAIN_NS}}}v")
                value = node.text if node is not None and node.text is not None else ""
                if cell_type == "s" and value:
                    shared_index = int(value)
                    if shared_index < 0 or shared_index >= len(shared):
                        raise FoundationXlsxAdapterError("Shared-string index is out of range.")
                    value = shared[shared_index]
                elif cell_type == "b":
                    if value not in {"0", "1"}:
                        raise FoundationXlsxAdapterError("Boolean cells must contain 0 or 1.")
                    value = "true" if value == "1" else "false"
            values[index] = value
        if any(value != "" for value in values.values()):
            result.append(values)
    return result


def _meta_values(rows: list[dict[int, str]]) -> dict[str, str]:
    if not rows:
        return {}
    headers = {
        column: value.strip().lower()
        for column, value in rows[0].items()
        if value.strip()
    }
    if set(headers.values()) != {"key", "value"} or len(headers) != 2:
        raise FoundationXlsxAdapterError("META headers must be KEY and VALUE.")
    key_column = next(column for column, header in headers.items() if header == "key")
    value_column = next(column for column, header in headers.items() if header == "value")
    result: dict[str, str] = {}
    for row in rows[1:]:
        key = row.get(key_column, "").strip().lower()
        if not key or key in result:
            raise FoundationXlsxAdapterError(f"META contains duplicate/empty key {key!r}.")
        result[key] = row.get(value_column, "")
    return result


def _table_objects(sheet_key: str, rows: list[dict[int, str]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    headers = {
        column: value.strip().lower()
        for column, value in rows[0].items()
        if value.strip()
    }
    if len(headers) != len(set(headers.values())):
        raise FoundationXlsxAdapterError(f"{sheet_key} has duplicate technical headers.")
    if not headers:
        return []
    result: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[1:], start=2):
        unknown_columns = set(row) - set(headers)
        if any(row[column] for column in unknown_columns):
            raise FoundationXlsxAdapterError(
                f"{sheet_key} row {row_number} has data under an empty header."
            )
        item = {
            header: _coerce_cell(header, row.get(column, ""), sheet_key=sheet_key)
            for column, header in headers.items()
        }
        if any(value not in (None, "") for value in item.values()):
            result.append(item)
    return result


def _coerce_cell(header: str, value: str, *, sheet_key: str | None = None) -> Any:
    stripped = value.strip()
    if sheet_key == "ASSESSMENTS" and header == "confidence":
        return stripped or None
    if stripped == "" and header in _EMPTY_STRING_FIELDS:
        return ""
    if stripped == "" and header not in _PRESERVE_TEXT_FIELDS:
        return None
    if header in _PRESERVE_TEXT_FIELDS:
        return value
    if header in _JSON_FIELDS or header == "workspace":
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise FoundationXlsxAdapterError(
                f"Technical field {header!r} must contain canonical JSON."
            ) from exc
    if header in _BOOLEAN_FIELDS:
        if stripped.lower() not in {"true", "false"}:
            raise FoundationXlsxAdapterError(f"Technical field {header!r} must be true/false.")
        return stripped.lower() == "true"
    if header in _INTEGER_FIELDS:
        try:
            return int(stripped)
        except ValueError as exc:
            raise FoundationXlsxAdapterError(f"Technical field {header!r} must be integer.") from exc
    if stripped.lower() == "null":
        return None
    return stripped
