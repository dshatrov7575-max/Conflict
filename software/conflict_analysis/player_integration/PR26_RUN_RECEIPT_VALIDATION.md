# PR-26 — проверка digest-квитанций запусков

Дата проверки: 2026-10-04. База: PR-25 / `391b163b1dd265a69a065c65681e8df98cde798a`.
Ветка: `codex/pr-26-calculation-run-receipts`.

## Область

PR добавляет журнал технических запусков baseline и scenario через существующую модель `AuditEvent`:

- один канонический UUIDv4 является idempotency key и identity квитанции;
- точный повтор возвращает ту же квитанцию без второго `INSERT`;
- иной запрос с тем же UUID закрывается `PLAYER_OPERATION_KEY_REUSE`;
- сохраняются actor, project/workspace/definition/time-slice/experiment/assessment identities, strategy, snapshot/input/result digests, quality statuses и timestamp;
- Snapshot, Run, значения входов, UNO и scenario token в БД не копируются;
- список ограничен 200 последними квитанциями и сообщает `total`/`truncated`;
- каждое чтение повторно проверяет канонический hash квитанции.

Новых моделей и миграций нет. Calculation Core, формула, веса, scientific admission и frozen результаты не менялись.

## Результаты

| Проверка | Результат |
|---|---|
| Targeted SQLite после финальных правок: receipts + scenario HTTP | **13 passed**, 61.719 s |
| Полный SQLite: Calculation + Player Integration + Scenario | **40 passed, 2 browser skips**, 171.728 s |
| PostgreSQL 18.6: повторный Player + Scenario Chromium E2E | **2 passed**, 37.664 s |
| Финальный PostgreSQL 18.6: Calculation + Player Integration + Scenario, оба Chromium | **40 passed, 0 skipped**, 235.504 s |
| Python compilation изменённых модулей/тестов | PASS |
| Node syntax обоих browser E2E | PASS |
| `manage.py check --settings=player_integration.settings` | PASS |
| `git diff --check` | PASS |
| Изменения в `calculation/**` и `domain/**` | Нет |

Первый PostgreSQL full run выявил дефект самого browser-assertion: скрипт проверял поля receipt, не считав `#receipt-json` из DOM. Исправлен только E2E-скрипт; отдельный двухбраузерный прогон и затем полный PostgreSQL-прогон прошли.

SQLite browser tests намеренно пропущены: Foundation FD08 triggers несовместимы со штатным `TransactionTestCase.flush` SQLite. Полный browser gate выполнен на временном PostgreSQL 18.6; кластер после проверки остановлен и удалён.

## Границы утверждений

`AuditEvent` неизменяем через штатный ORM (`save`, `QuerySet.update/delete`) и квитанция tamper-evident: ручная raw-SQL подмена обнаруживается как `PLAYER_OPERATION_RESULT_DRIFT` при чтении. Этот PR не добавляет DB-trigger на `domain_auditevent`, поэтому абсолютная защита от привилегированной raw-SQL модификации не заявляется.

Квитанция доказывает техническую identity выполненного расчёта и его digests, но не заменяет сохранение исходного Snapshot/Run JSON, не подтверждает истинность входов и не повышает научный статус. Сохраняются:

- HUMAN validation/reliability: `NOT_PERFORMED`;
- historical snapshot: `NOT_ESTABLISHED`;
- historical area UNO: `NOT_COMPUTED / BLOCKED`;
- predictive/probability/risk validation: `NOT_CLAIMED`;
- publication, release и deployment: `NOT_EXECUTED`.
