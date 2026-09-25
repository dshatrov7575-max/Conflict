# PR-2: результаты проверки

Дата: 2026-09-25. База реализации:
`dcf7013e1d2a2525916f25b6c7b1ec869bb5ff55`, tree
`e97634cbbb39da409e394da78b76de853d2f0e5c`.
Ветка: `codex/pr-2-player-integration`.

## Среда

- Windows x64, Python 3.12.10, Django 5.2.17, pytest 8.4.2.
- PostgreSQL 18.6: отдельный временный кластер, localhost:55482; существующая
  рабочая база не использовалась. Миграции применены с нуля.
- Node 24.16.0 и реальный Chromium через существующий CDP helper проекта.
- SQLite: отдельная тестовая БД Django, явный `USE_SQLITE=true`.
- `PYTHONDONTWRITEBYTECODE=1`, pytest cache отключён.

## Результаты

| Проверка | Результат |
|---|---|
| Чистые PostgreSQL migrations + `manage.py check --settings=player_integration.settings` | PASS, ошибок нет |
| `calculation/tests` на SQLite | 51 passed, 39.81 s |
| Финальный `player_integration/tests` на SQLite | 16 passed, 1 skipped, 156.16 s |
| PostgreSQL: интеграция + Core + Foundation experiments/projection + Production Player G8 | 107 passed, 418.24 s |
| Финальный `player_integration/tests` на PostgreSQL с `PLAYER_INTEGRATION_BROWSER=1` | 17 passed, 158.10 s |
| `git diff --check` и Python AST parsing | PASS |
| Изменения вне `software/conflict_analysis/player_integration/**` | Нет |

SQLite skip — только opt-in Chromium test; он выполнен успешно в обоих
PostgreSQL-прогонах. Общий прогон содержит 51 тест Core, 40 существующих
Foundation/Player regression tests и первоначальные 16 integration tests.
Финальный прогон повторяет интеграцию и добавляет регрессию неподдерживаемого
multipart/повторных form fields. Всего проверены **108 уникальных тестов** на
PostgreSQL; перекрывающиеся прогоны не следует суммировать как 124 теста.

Точный исторический PostgreSQL 18.4 gate не запускался: фактическая версия
доступного тестового сервера — 18.6. SQLite не доказывает поведение row locks.

## Воспроизведение

Из `software/conflict_analysis`, после настройки одноразовой PostgreSQL через
`POSTGRES_*`, с `USE_SQLITE=false` и `PLAYER_INTEGRATION_BROWSER=1`:

```text
python manage.py migrate --noinput --settings=player_integration.settings
python manage.py check --settings=player_integration.settings
python -m pytest -c player_integration/pytest.ini player_integration/tests calculation/tests domain/tests/test_player_experiments.py domain/tests/test_player_projection.py production_player/tests/test_player_g8.py -q -p no:cacheprovider
python -m pytest -c player_integration/pytest.ini player_integration/tests -q -p no:cacheprovider
```

На финальном дереве первый набор содержит 108 тестов. Для SQLite задайте
`USE_SQLITE=true`, отключите `PLAYER_INTEGRATION_BROWSER` и выполните:

```text
python -m pytest -c player_integration/pytest.ini player_integration/tests -q -p no:cacheprovider
python -m pytest calculation/tests -q -p no:cacheprovider
```

## Что подтверждено

- Реальные Foundation HTTP операции создают только тестовые исходные оценки;
  интеграционные GET/POST не выполняют SQL INSERT/UPDATE/DELETE. Проверено
  сохранение всех полей и количества ParameterValue.
- HUMAN и AI получают собственные snapshot/run и не дополняют отсутствующие
  значения друг друга. Точно так же изолированы временные срезы.
- COMPLETE, PARTIAL, NOT_COMPUTABLE, нули, UNKNOWN и отсутствующий KVPTN
  доходят до Result View без подмены или повторного вычисления метрик.
- Snapshot воспроизводится через неизменённый Core после successor correction,
  freeze и archive. Источник/версия исправленного POS и сохранённый SAL корректны.
- Session, Foundation permissions и project access проверяются заново; CSRF
  действует для native form и JSON POST; ошибочные запросы не создают записи.
- Реальный браузер выбирает эксперимент и срез, отправляет форму, видит
  HUMAN UNO=100, AI UNO=0 и отсутствие результата при UNKNOWN. CSS загружен,
  обращения страницы остаются в одном origin, localStorage/sessionStorage пусты.
- Calculation Core, формула, доменные модели/миграции и исходный Player не изменены.

Локальные JUnit XML находятся в игнорируемом `player_integration/.artifacts/`
(`postgres-e2e.xml`, `postgres-final.xml`, `sqlite-e2e.xml`). Временный кластер
после проверки остановлен и удалён. Коммит содержит только исходники,
тесты и документацию разрешённого каталога.
