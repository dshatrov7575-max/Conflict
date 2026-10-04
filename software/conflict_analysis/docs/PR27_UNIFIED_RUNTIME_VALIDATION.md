# PR-27 — Unified Package and Runtime Validation

Дата проверки: 2026-10-04. База: `89d1cf6523f650313ab37caf5f7fa831d86e0f65` (PR-26). Ветка: `codex/pr-27-unified-package-runtime`.

## Реализованная граница

- `player_integration` и `scenario_modeling` включены в корневой wheel `conflict-analysis`.
- Их templates/static перечислены в package-data и доступны после установки wheel.
- Штатный `conflict_analysis.settings` устанавливает оба приложения.
- Штатный `conflict_analysis.urls` монтирует `/player/calculations/` и `/player/calculations/scenarios/` рядом с Studio и основным Player.
- `player_integration.settings` и `player_integration.project_urls` оставлены только как совместимые алиасы единого графа.
- Calculation Core, `domain/**`, миграции, формула, научные результаты и RunReceipt-контракты не изменялись.

## Выполненные проверки

| Проверка | Результат |
|---|---|
| Новый unified-runtime contract test | 3 passed |
| SQLite: `conflict_analysis.tests + calculation + player_integration + scenario_modeling` | 43 passed, 2 browser skips, 178.882 s |
| PostgreSQL 18.6: тот же набор с Player/Scenario Chromium | 43 passed, 0 skipped, 245.966 s |
| Existing Player G7/G8 + shared Panel UI | 32 passed, 4 unrelated opt-in skips, 55.611 s |
| Python compile, Django system check, `git diff --check` | PASS |

## Wheel acceptance

Финальный wheel: `conflict_analysis-0.1.0-py3-none-any.whl`.

- размер: `880575` bytes;
- SHA-256: `252b8baa5989a2a3695861bd2751bdb15855d12937aeea598c3bf229354b658d`;
- ZIP entries: `205`;
- проверены все 35 `.py`/template/static файлов двух composition-приложений: missing `0`, duplicates `0`;
- `__pycache__`, `.artifacts`, `.pyc`, SQLite-файлы в wheel отсутствуют;
- установленный wheel загружал `conflict_analysis`, `player_integration` и `scenario_modeling` только из отдельного install-target;
- installed-wheel smoke подтвердил оба URL, три шаблона, три обязательных static-ресурса и обновлённую contextual help;
- `collectstatic` из установленного wheel собрал 180 файлов, включая все три обязательных composition-assets;
- `manage.py check`/Django `check` на установленном wheel — PASS.

Временный PostgreSQL-кластер `127.0.0.1:55490` остановлен и удалён. Рабочие и пользовательские БД не использовались.

## Ограничения

Этот PR закрывает только единый устанавливаемый package/settings/URL graph. Он не является production deployment hardening и не вводит required GitHub CI gate — это отдельные последующие изменения. HUMAN validation/reliability остаётся `NOT_PERFORMED`; historical snapshot — `NOT_ESTABLISHED`; historical area UNO — `NOT_COMPUTED/BLOCKED`; predictive validity — `NOT_CLAIMED`. Публикация, release и deployment не выполнялись.