"""Pure, session-only showcase data helpers.

The structures in this module are presentation view-models.  They are not
Foundation packages, ORM entities, or an alternative publication authority.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


SHOWCASE_FORMAT = "SHOWCASE_SESSION_V1"
SHOWCASE_VERSION = "1.0.0"
MAX_ITEMS_PER_COLLECTION = 500
MAX_PREVIEW_CELLS = 10_000
ECMASCRIPT_TRIM_CHARACTERS = (
    "\u0009\u000a\u000b\u000c\u000d\u0020\u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029\u202f\u205f\u3000\ufeff"
)
_MISSING = object()


def _element(index: int) -> dict[str, Any]:
    return {
        "id": f"element-{index:02d}",
        "code": f"CI-{index:02d}",
        "name": f"Проблемная тема {index}",
        "definition": f"Рабочее определение проблемной темы {index}.",
        "parentId": None,
    }


def _actor(index: int) -> dict[str, Any]:
    return {
        "id": f"actor-{index:02d}",
        "code": f"ACT-{index:02d}",
        "name": f"Группа или организация {index}",
        "description": f"Краткое описание участника {index}.",
        "parentId": None,
    }


def build_fixture(element_count: int, actor_count: int) -> dict[str, Any]:
    """Build an arbitrary-cardinality, deterministic showcase session."""

    if element_count < 0 or actor_count < 0:
        raise ValueError("Fixture cardinality cannot be negative.")
    return {
        "format": SHOWCASE_FORMAT,
        "version": SHOWCASE_VERSION,
        "project": {
            "id": "showcase-project",
            "code": "SHOWCASE-PROJECT",
            "name": "Партнёрский исследовательский проект",
            "description": (
                "Структура для демонстрации: проблемные темы и группы людей "
                "или организаций. Данные живут только в этой showcase-сессии."
            ),
        },
        "analyticalElements": [_element(index) for index in range(1, element_count + 1)],
        "actors": [_actor(index) for index in range(1, actor_count + 1)],
        "meta": {
            "presentationOnly": True,
            "fixture": f"{element_count}x{actor_count}",
        },
    }


FIXTURES = {
    "6x8": build_fixture(6, 8),
    "3x4": build_fixture(3, 4),
}


def fixture(name: str) -> dict[str, Any]:
    try:
        return deepcopy(FIXTURES[name])
    except KeyError as error:
        raise ValueError(f"Unknown showcase fixture: {name}") from error


def _diagnostic(code: str, path: str, message: str) -> dict[str, str]:
    return {"level": "error", "code": code, "path": path, "message": message}


def _trim_text(value: str) -> str:
    """Apply the explicit ECMAScript TrimString whitespace contract."""

    return value.strip(ECMASCRIPT_TRIM_CHARACTERS)


def _normalize_code(value: str) -> str:
    """Fold only stable ASCII and Cyrillic uppercase ranges."""

    normalized: list[str] = []
    for character in value:
        point = ord(character)
        if 0x41 <= point <= 0x5A or 0x410 <= point <= 0x42F:
            normalized.append(chr(point + 0x20))
        elif character == "Ё":
            normalized.append("ё")
        else:
            normalized.append(character)
    return "".join(normalized)


def _field_not_string(path: str) -> dict[str, str]:
    return _diagnostic(
        "FIELD_NOT_STRING",
        path,
        "Поле должно быть JSON-строкой.",
    )


def validate_session(payload: Any) -> list[dict[str, str]]:
    """Return stable, plain-language diagnostics without mutating input."""

    diagnostics: list[dict[str, str]] = []
    if not isinstance(payload, Mapping):
        return [_diagnostic("SESSION_NOT_OBJECT", "$", "Файл сессии должен содержать JSON-объект.")]

    format_value = payload.get("format", _MISSING)
    if format_value is not _MISSING and not isinstance(format_value, str):
        diagnostics.append(_field_not_string("format"))
    elif format_value != SHOWCASE_FORMAT:
        diagnostics.append(
            _diagnostic(
                "FORMAT_MISMATCH",
                "format",
                f"Ожидается маркировка {SHOWCASE_FORMAT}; Foundation package здесь не принимается.",
            )
        )
    version_value = payload.get("version", _MISSING)
    if version_value is not _MISSING and not isinstance(version_value, str):
        diagnostics.append(_field_not_string("version"))
    elif version_value != SHOWCASE_VERSION:
        diagnostics.append(
            _diagnostic(
                "VERSION_MISMATCH",
                "version",
                f"Поддерживается версия showcase-сессии {SHOWCASE_VERSION}.",
            )
        )

    project = payload.get("project")
    project_name = project.get("name", _MISSING) if isinstance(project, Mapping) else _MISSING
    if project_name is not _MISSING and not isinstance(project_name, str):
        diagnostics.append(_field_not_string("project.name"))
    elif project_name is _MISSING or not _trim_text(project_name):
        diagnostics.append(
            _diagnostic("PROJECT_NAME_BLANK", "project.name", "Укажите название проекта.")
        )

    collections = (
        ("analyticalElements", "проблемной темы", True),
        ("actors", "группы или организации", False),
    )
    all_ids: dict[str, str] = {}
    for collection_name, label, needs_definition in collections:
        rows = payload.get(collection_name)
        if not isinstance(rows, list):
            diagnostics.append(
                _diagnostic(
                    "COLLECTION_NOT_ARRAY",
                    collection_name,
                    f"Список «{collection_name}» должен быть массивом.",
                )
            )
            continue
        if len(rows) > MAX_ITEMS_PER_COLLECTION:
            diagnostics.append(
                _diagnostic(
                    "COLLECTION_TOO_LARGE",
                    collection_name,
                    (
                        f"Список «{collection_name}» содержит {len(rows)} записей; "
                        f"максимум — {MAX_ITEMS_PER_COLLECTION}."
                    ),
                )
            )
            continue

        codes: dict[str, int] = {}
        row_ids: set[str] = set()
        for index, row in enumerate(rows):
            path = f"{collection_name}[{index}]"
            if not isinstance(row, Mapping):
                diagnostics.append(
                    _diagnostic("ROW_NOT_OBJECT", path, f"Запись {label} должна быть объектом.")
                )
                continue
            raw_id = row.get("id", _MISSING)
            raw_code = row.get("code", _MISSING)
            raw_name = row.get("name", _MISSING)
            row_id = _trim_text(raw_id) if isinstance(raw_id, str) else ""
            code = _trim_text(raw_code) if isinstance(raw_code, str) else ""
            name = _trim_text(raw_name) if isinstance(raw_name, str) else ""
            if raw_id is not _MISSING and not isinstance(raw_id, str):
                diagnostics.append(_field_not_string(f"{path}.id"))
            elif not row_id:
                diagnostics.append(_diagnostic("ID_BLANK", f"{path}.id", "У записи отсутствует ID."))
            elif row_id in all_ids:
                diagnostics.append(
                    _diagnostic(
                        "ID_DUPLICATE",
                        f"{path}.id",
                        f"ID «{row_id}» уже используется в {all_ids[row_id]}.",
                    )
                )
            else:
                all_ids[row_id] = path
                row_ids.add(row_id)
            if raw_code is not _MISSING and not isinstance(raw_code, str):
                diagnostics.append(_field_not_string(f"{path}.code"))
            elif not code:
                diagnostics.append(_diagnostic("CODE_BLANK", f"{path}.code", "Укажите код записи."))
            else:
                normalized_code = _normalize_code(code)
                if normalized_code in codes:
                    diagnostics.append(
                        _diagnostic(
                            "CODE_DUPLICATE",
                            f"{path}.code",
                            f"Код «{code}» уже используется в этой таблице.",
                        )
                    )
                else:
                    codes[normalized_code] = index
            if raw_name is not _MISSING and not isinstance(raw_name, str):
                diagnostics.append(_field_not_string(f"{path}.name"))
            elif not name:
                diagnostics.append(
                    _diagnostic("NAME_BLANK", f"{path}.name", f"Укажите название {label}.")
                )
            detail_name = "definition" if needs_definition else "description"
            detail_value = row.get(detail_name, _MISSING)
            detail_path = f"{path}.{detail_name}"
            if detail_value is not _MISSING and not isinstance(detail_value, str):
                diagnostics.append(_field_not_string(detail_path))
            elif detail_value is _MISSING or not _trim_text(detail_value):
                diagnostics.append(
                    _diagnostic(
                        "DEFINITION_BLANK" if needs_definition else "DESCRIPTION_BLANK",
                        detail_path,
                        (
                            "Добавьте рабочее определение проблемной темы."
                            if needs_definition
                            else "Добавьте краткое описание группы или организации."
                        ),
                    )
                )

        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            parent_id = row.get("parentId", _MISSING)
            parent_path = f"{collection_name}[{index}].parentId"
            if parent_id is not _MISSING and parent_id is not None and not isinstance(parent_id, str):
                diagnostics.append(_field_not_string(parent_path))
            elif isinstance(parent_id, str) and _trim_text(parent_id) and _trim_text(parent_id) not in row_ids:
                diagnostics.append(
                    _diagnostic(
                        "PARENT_REFERENCE_MISSING",
                        parent_path,
                        f"Ссылка на родительскую запись «{_trim_text(parent_id)}» не найдена.",
                    )
                )

    analytical_elements = payload.get("analyticalElements")
    actors = payload.get("actors")
    if isinstance(analytical_elements, list) and isinstance(actors, list):
        preview_cells = len(analytical_elements) * len(actors)
        if preview_cells > MAX_PREVIEW_CELLS:
            diagnostics.append(
                _diagnostic(
                    "PREVIEW_CELL_BUDGET_EXCEEDED",
                    "analyticalElements×actors",
                    (
                        f"Preview содержит {preview_cells} ячеек; "
                        f"безопасный максимум — {MAX_PREVIEW_CELLS}."
                    ),
                )
            )

    return diagnostics


def validated_copy(payload: Any) -> dict[str, Any]:
    diagnostics = validate_session(payload)
    if diagnostics:
        raise ValueError(diagnostics[0]["message"])
    return deepcopy(dict(payload))
