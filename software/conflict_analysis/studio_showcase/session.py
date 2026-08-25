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


def _text(value: Any) -> str:
    """Match JavaScript's empty handling for JSON null in authored text fields."""

    return "" if value is None else str(value)


def validate_session(payload: Any) -> list[dict[str, str]]:
    """Return stable, plain-language diagnostics without mutating input."""

    diagnostics: list[dict[str, str]] = []
    if not isinstance(payload, Mapping):
        return [_diagnostic("SESSION_NOT_OBJECT", "$", "Файл сессии должен содержать JSON-объект.")]

    if payload.get("format") != SHOWCASE_FORMAT:
        diagnostics.append(
            _diagnostic(
                "FORMAT_MISMATCH",
                "format",
                f"Ожидается маркировка {SHOWCASE_FORMAT}; Foundation package здесь не принимается.",
            )
        )
    if payload.get("version") != SHOWCASE_VERSION:
        diagnostics.append(
            _diagnostic(
                "VERSION_MISMATCH",
                "version",
                f"Поддерживается версия showcase-сессии {SHOWCASE_VERSION}.",
            )
        )

    project = payload.get("project")
    if not isinstance(project, Mapping) or not _text(project.get("name", "")).strip():
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
            row_id = _text(row.get("id", "")).strip()
            code = _text(row.get("code", "")).strip()
            name = _text(row.get("name", "")).strip()
            if not row_id:
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
            if not code:
                diagnostics.append(_diagnostic("CODE_BLANK", f"{path}.code", "Укажите код записи."))
            else:
                normalized_code = code.lower()
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
            if not name:
                diagnostics.append(
                    _diagnostic("NAME_BLANK", f"{path}.name", f"Укажите название {label}.")
                )
            if needs_definition and not _text(row.get("definition", "")).strip():
                diagnostics.append(
                    _diagnostic(
                        "DEFINITION_BLANK",
                        f"{path}.definition",
                        "Добавьте рабочее определение проблемной темы.",
                    )
                )
            if not needs_definition and not _text(row.get("description", "")).strip():
                diagnostics.append(
                    _diagnostic(
                        "DESCRIPTION_BLANK",
                        f"{path}.description",
                        "Добавьте краткое описание группы или организации.",
                    )
                )

        for index, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            parent_id = row.get("parentId")
            if parent_id not in (None, "") and _text(parent_id) not in row_ids:
                diagnostics.append(
                    _diagnostic(
                        "PARENT_REFERENCE_MISSING",
                        f"{collection_name}[{index}].parentId",
                        f"Ссылка на родительскую запись «{parent_id}» не найдена.",
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
