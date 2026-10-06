"""One immutable PLAYER Help catalog; explicit provisioning, never lazy repair."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q

from domain.enums import HelpApplicationScope, PublicationStatus
from domain.models import HelpTopic, ProjectWorkspace, UIHelpBinding
from domain.services.help_topics import sanitize_help_html, sanitized_help_checksum


CATALOG_ID = "FOUNDATION_PLAYER_HELP_G7_V1"
CATALOG_VERSION = "1.0.0"
CATALOG_LOCALE = "ru"
CATALOG_SHA256 = "0b1ea9759f1ae52430630326da3e9d3fa317914dbd6fbe259afd19389d37f27e"
_PUBLISHED_AT = datetime(2026, 9, 8, tzinfo=timezone.utc)
_TOPICS = (
    ("player.welcome", "Анализ конфликтов",
     "<h2>Анализ конфликтов</h2><p>Опубликованная версия проекта задаёт неизменяемую структуру. "
     "Рабочее пространство закрепляет одну точную версию. Временной срез фиксирует календарную дату анализа.</p>"),
    ("player.published_definition", "Опубликованная версия проекта",
     "<h2>Опубликованная версия проекта</h2><p>Доступна только опубликованная структура. "
     "Номер версии и контрольная сумма определяют точную структуру; выбор не заменяется текущей версией автоматически.</p>"),
    ("player.workspace", "Рабочее пространство",
     "<h2>Рабочее пространство</h2><p>Рабочее пространство изолирует данные и закрепляет опубликованную версию. "
     "Создание доступно только явной командой. Неподтверждённая или противоречивая проекция не допускает анализа.</p>"),
    ("player.time_slice", "Временной срез",
     "<h2>Временной срез</h2><p>Дата среза — календарная дата, а не часовой пояс и не граница знания отдельной оценки. "
     "Сохранённый срез неизменяем. Для другой даты создайте новый срез; переименование и удаление недоступны.</p>"),
    ("player.experiments_locked", "Эксперименты",
     "<h2>Эксперименты</h2><p>Доступно после этапа экспериментов.</p>"
     "<p>Существующие эксперименты показываются только как сведения. Значения и расчёты здесь не создаются.</p>"),
    ("player.document_locked", "Документ",
     "<h2>Документ</h2><p>Доступно после этапа доказательств.</p>"),
    ("player.chat_locked", "Чат",
     "<h2>Чат</h2><p>Доступно после этапа чата.</p>"),
    ("player.method_unavailable", "Методика",
     "<h2>Методика</h2><p>Расчётная стратегия не активирована. "
     "Расчёт, графики, рейтинг, прогноз и рекомендации в этом этапе недоступны.</p>"),
)
PLAYER_HELP_KEYS = tuple(item[0] for item in _TOPICS)


class PlayerHelpCatalogError(RuntimeError):
    code = "PLAYER_HELP_CATALOG_CONFLICT"


def _catalog_bytes() -> bytes:
    return json.dumps(
        {"catalog": CATALOG_ID, "version": CATALOG_VERSION, "locale": CATALOG_LOCALE,
         "published_at": "2026-09-08T00:00:00Z", "topics": _TOPICS},
        ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _specs() -> tuple[dict, ...]:
    if hashlib.sha256(_catalog_bytes()).hexdigest() != CATALOG_SHA256:
        raise PlayerHelpCatalogError("The frozen catalog checksum differs.")
    result = []
    for key, title, html in _TOPICS:
        if sanitize_help_html(html) != html:
            raise PlayerHelpCatalogError("Catalog HTML is not canonical.")
        result.append({
            "id": uuid5(NAMESPACE_URL, f"{CATALOG_ID}:{CATALOG_VERSION}:{CATALOG_LOCALE}:topic:{key}"),
            "code": f"G7-HELP-{key}", "version": CATALOG_VERSION, "stable_key": key,
            "title": title, "application_scope": HelpApplicationScope.PLAYER,
            "construct_version": "1.0.0", "term_version": "1.0.0",
            "locale": CATALOG_LOCALE, "sanitized_html": html,
            "content_sha256": sanitized_help_checksum(html),
            "publication_status": PublicationStatus.PUBLISHED, "published_at": _PUBLISHED_AT,
        })
    return tuple(result)


def _row_exact(row, spec: dict) -> bool:
    return all(getattr(row, name) == value for name, value in spec.items())


def _topic_rows(specs: tuple[dict, ...]) -> list[HelpTopic]:
    # Include identity/code collisions, not merely the happy-path namespace.
    return list(HelpTopic.objects.filter(
        Q(application_scope=HelpApplicationScope.PLAYER, locale=CATALOG_LOCALE,
          version=CATALOG_VERSION)
        | Q(pk__in=[spec["id"] for spec in specs])
        | Q(code__in=[spec["code"] for spec in specs], version=CATALOG_VERSION)
    ).order_by("pk"))


def require_player_help_catalog() -> tuple[HelpTopic, ...]:
    """Read-only exact catalog check. Later distinct versions may coexist."""
    specs = _specs()
    rows = _topic_rows(specs)
    indexed = {row.pk: row for row in rows}
    if len(rows) != len(specs) or any(
        spec["id"] not in indexed or not _row_exact(indexed[spec["id"]], spec)
        for spec in specs
    ):
        raise PlayerHelpCatalogError("The provisioned G7 topic catalog is not exact.")
    return tuple(indexed[spec["id"]] for spec in specs)


def _binding_specs(workspace: ProjectWorkspace, topics: tuple[HelpTopic, ...]) -> tuple[dict, ...]:
    return tuple({
        "id": uuid5(NAMESPACE_URL,
                    f"{CATALOG_ID}:{CATALOG_VERSION}:{workspace.pk}:{topic.stable_key}:{CATALOG_LOCALE}"),
        "code": f"G7-{workspace.pk}-{topic.stable_key}",
        "version": CATALOG_VERSION, "workspace_id": workspace.pk,
        "application_scope": HelpApplicationScope.PLAYER, "ui_key": topic.stable_key,
        "locale": CATALOG_LOCALE, "help_topic_id": topic.pk,
    } for topic in topics)


def _binding_rows(workspace: ProjectWorkspace, specs: tuple[dict, ...]) -> list[UIHelpBinding]:
    return list(UIHelpBinding.objects.filter(
        Q(workspace_id=workspace.pk, application_scope=HelpApplicationScope.PLAYER,
          locale=CATALOG_LOCALE, version=CATALOG_VERSION)
        | Q(pk__in=[spec["id"] for spec in specs])
        | Q(code__in=[spec["code"] for spec in specs], version=CATALOG_VERSION)
    ).order_by("pk"))


def verify_player_help_bindings(workspace: ProjectWorkspace) -> tuple[UIHelpBinding, ...]:
    """Validate only the frozen version namespace; do not repair anything."""
    specs = _binding_specs(workspace, require_player_help_catalog())
    rows = _binding_rows(workspace, specs)
    indexed = {row.pk: row for row in rows}
    if len(rows) != len(specs) or any(
        spec["id"] not in indexed or not _row_exact(indexed[spec["id"]], spec)
        for spec in specs
    ):
        raise PlayerHelpCatalogError("The Workspace G7 binding set is not exact.")
    return tuple(indexed[spec["id"]] for spec in specs)


def bind_player_help(workspace: ProjectWorkspace) -> int:
    """Called only by explicit provisioning or the outer Workspace transaction."""
    if not transaction.get_connection().in_atomic_block or workspace._state.adding:
        raise PlayerHelpCatalogError("Binding requires a persisted Workspace and an outer transaction.")
    specs = _binding_specs(workspace, require_player_help_catalog())
    existing = _binding_rows(workspace, specs)
    if existing:
        verify_player_help_bindings(workspace)
        return 0
    for spec in specs:
        # Instance-save preserves the accepted immutable model validation.
        UIHelpBinding(**spec).save(force_insert=True)
    verify_player_help_bindings(workspace)
    return len(specs)


def _provision() -> dict:
    with transaction.atomic():
        specs = _specs()
        rows = _topic_rows(specs)
        created_topics = 0
        if rows:
            require_player_help_catalog()
        else:
            for spec in specs:
                HelpTopic(**spec).save(force_insert=True)
                created_topics += 1
        created_bindings = 0
        # Topics are immutable; ordinary Workspace operations never lock these
        # global rows, so independent projects retain independent write lanes.
        workspaces = list(ProjectWorkspace.objects.select_for_update().order_by("project_id", "pk"))
        for workspace in workspaces:
            created_bindings += bind_player_help(workspace)
        return {
            "catalog": CATALOG_ID, "version": CATALOG_VERSION, "locale": CATALOG_LOCALE,
            "catalog_sha256": CATALOG_SHA256, "topics_created": created_topics,
            "bindings_created": created_bindings, "topics_total": len(specs),
            "workspaces_total": len(workspaces),
        }


def provision_player_help() -> dict:
    """Explicit, atomic, idempotent deployment command; no structure or audit writes."""
    try:
        return _provision()
    except (IntegrityError, ValidationError) as exc:
        # No optimistic retry: classify only a fully persisted exact winner.
        try:
            with transaction.atomic():
                require_player_help_catalog()
                workspaces = list(ProjectWorkspace.objects.order_by("project_id", "pk"))
                for workspace in workspaces:
                    verify_player_help_bindings(workspace)
        except (PlayerHelpCatalogError, ValidationError, IntegrityError):
            raise PlayerHelpCatalogError("Atomic provisioning conflicts with persisted content.") from exc
        return {
            "catalog": CATALOG_ID, "version": CATALOG_VERSION, "locale": CATALOG_LOCALE,
            "catalog_sha256": CATALOG_SHA256, "topics_created": 0, "bindings_created": 0,
            "topics_total": len(PLAYER_HELP_KEYS), "workspaces_total": len(workspaces),
        }
