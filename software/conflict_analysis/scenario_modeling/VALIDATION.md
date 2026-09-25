# PR-3 — проверка Scenario Modeling

Дата: 2026-09-25. Задача: `PR-3-SCENARIO-MODELING-MVP`.

## G0 и область

- База HEAD: `acc24d66b053af14244216a199e1ba951c8d1dd9` (PR-2 Player Integration).
- База tree: `f80137fd5a9b799ea1189019081a667ac631dc29`.
- BASE_RESOLVES: PASS; рабочее дерево перед началом чистое.
- TARGET_BRANCH: `codex/pr-3-scenario-modeling`; конфликтов имени не было.
- ALLOWED_PATHS: `software/conflict_analysis/scenario_modeling/**` и точки
  подключения в `software/conflict_analysis/player_integration/`.
- REMOTE_PUSH_AVAILABLE / PR_CREATION_AVAILABLE: PASS (dry-run push и ADMIN
  permission проверены до реализации). SELECTED_DELIVERY: LIVE_BRANCH.
- TEST_ENVIRONMENT_AVAILABLE / TARGET_OS_RUNNER_AVAILABLE: Windows x64,
  Python 3.12.10, Django 5.2.17, pytest 8.4.2, Node 24.16.0 и Chromium.
- IMPLEMENTATION_SLICE: immutable model, isolated adapter, подписанная форма,
  UI input/slider, сравнение UNO и объяснения через существующий Core.

## Среда и результаты

Рабочая база не использовалась. PostgreSQL 18.4 запущен отдельным временным
кластером на `127.0.0.1:55483`; pytest создал свою БД с миграциями с нуля.
SQLite-прогоны использовали отдельную in-memory БД Django.
`PYTHONDONTWRITEBYTECODE=1`; pytest cache отключён.

| Проверка | Результат |
|---|---|
| Первичный Scenario Model | 34 passed, 0.22 s |
| SQLite: Scenario Model + HTTP + Core + PR-2 HTTP до завершающих проверок точности/лимитов | 109 passed, 188.08 s |
| PostgreSQL: Scenario + Chromium PR-3 + Chromium PR-2 до завершающих проверок | 44 passed, 106.63 s |
| Финальная модель, включая малые Decimal и пределы точности | 37 passed, 0.22 s |
| Финальное дерево, PostgreSQL 18.4: все Scenario + Core + PR-2, оба Chromium E2E | **115 passed, 0 skipped, 241.09 s** |
| Django system check, Python AST, Node syntax, `git diff --check` | PASS |

Финальный прогон содержит 37 тестов модели сценария, 9 Scenario HTTP,
1 Scenario Chromium, 51 Calculation Core и 17 PR-2 (включая Chromium).
Всего **115 уникальных тестов**. Временный PostgreSQL-кластер штатно остановлен
после выполнения. Финальный JUnit: `.artifacts/postgres-final.xml`.

Промежуточные прогоны перекрываются; их количества не суммируются.
Первый SQLite HTTP-прогон выявил ошибку заполнения UNKNOWN в test fixture;
после исправления сценарий прошёл. Первый Chromium-прогон на SQLite прошёл
UI assertions, но завершился ошибкой стандартного flush из-за существующего
`FD08_CANONICAL_PROJECTION_MUTATION_FORBIDDEN`. Browser test переведён на
PostgreSQL; защитные триггеры не менялись и не отключались.

## Подтверждённые свойства

- Baseline остаётся побайтно тем же после set/remove/reset/recalculate;
  immutable baseline и независимые сценарии не разделяют изменяемое состояние.
- Reordered override дают тот же canonical model и run; JSON roundtrip,
  повторный HTTP POST и Core offline replay сохраняют результат и digest.
- Все четыре отсутствующих статуса проверены для POS/KVS/RGU/KVPTN:
  статус, null и source identity сохраняются. Прямой override отсутствующего
  значения отклоняется. W=0 даёт NOT_COMPUTABLE и null UNO/delta.
- RGU применяется ко всем PTN одного actor; POS/KVS привязаны к relation.
  Исходные source/version/status остаются в baseline; сценарные значения
  отдельно помечены источником SCENARIO и PROVISIONAL.
- HUMAN/AI и два независимых сценария изолированы. После correction,
  freeze/archive сценарий продолжает использовать исходный snapshot.
- Каждый измеренный scenario и baseline HTTP-запрос проверяется через
  CaptureQueriesContext: нет INSERT/UPDATE/DELETE. Проверяется неизменность
  всех полей ParameterValue и AssessmentSet. Исходные тестовые оценки создаются
  только fixture через существующий Foundation API.
- Session binding, подпись, expiry, CSRF и повторный admission проверены.
  Ввод отвергает неизвестные targets, повторные/лишние поля и неверные числа.
- Реальный Chromium выполняет native forms: создание из PR-2, ввод числа,
  slider, повторный пересчёт, удаление override и reset. Показаны UNO
  100 → 50 → 0 и соответствующие delta, baseline не меняется.
  Проверяются CSS, отсутствие JS/CSP ошибок, same-origin и пустые
  localStorage/sessionStorage. Раскладка проверена при 1280×1000 и 390×844.
- Визуально просмотрены desktop/mobile PNG. Скриншоты и JUnit находятся в
  игнорируемом `scenario_modeling/.artifacts/` и не входят в коммит.
- `git diff` против базы подтверждает отсутствие изменений в `calculation/`,
  `domain/`, `production_player/`, формуле, миграциях и основной конфигурации.

## Воспроизведение

Из `software/conflict_analysis`, после настройки отдельного PostgreSQL через
`POSTGRES_*`, с `USE_SQLITE=false`, `SCENARIO_BROWSER=1` и
`PLAYER_INTEGRATION_BROWSER=1`:

```text
python manage.py check --settings=player_integration.settings
python -m pytest -c scenario_modeling/pytest.ini scenario_modeling/tests calculation/tests player_integration/tests -q -p no:cacheprovider
```

Существующий GitHub workflow не подписан на ветку PR-3 или её PR-2 base;
CI-конфигурация не менялась. Эти результаты — выполненные локальные проверки,
а не утверждение о GitHub CI, production release или owner acceptance.
Состав файлов, ограничения хранения и профиль запуска — в `README.md`.
