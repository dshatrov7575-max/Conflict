# PR-4 — проверка Scientific Foundation

Дата: 2026-09-25. Область изменения: только новые файлы `docs/scientific/`.

## База и доставка

- Ветка: `codex/pr-4-scientific-foundation`.
- База HEAD: `f12cfd2c76d54068f5b6cc98511bc0be84dd079e`.
- База tree: `e4907d68289f18a54ce0c211ffc808c5034a4be6`.
- База PR: `codex/pr-3-scenario-modeling` (PR #113).
- Рабочее дерево до начала было чистым; база разрешается; конфликт имени
  ветки отсутствовал локально и на origin.
- Доступ к origin и dry-run push проверены; способ доставки — `LIVE_BRANCH`.
- Добавлены только документация, описательный JSON-каталог и его отдельная
  схема. Calculation Core, стратегия, приложение, миграции, импорт и структуры
  исторических данных не редактировались.

## Результаты

Среда: Windows x64, Python 3.12.10, Django 5.2.17, pytest 8.4.2,
pytest-django 4.14.0, SQLite 3.49.1, jsonschema 4.26.0.

| Проверка | Результат |
| --- | --- |
| `calculation/tests` | **51 passed, 0 skipped, 42.88 s**, код завершения 0. |
| JSON Schema Draft 2020-12 и каталог | PASS: схема корректна; четыре записи соответствуют схеме. |
| Некорректные метаданные | PASS: отклонены семь вариантов — нет source, нет methodology_version, повтор ID, неизвестный фактор, HIGH без rationale, другая версия стратегии, историческое value в описательной записи. |
| Поля и происхождение | PASS: четыре входа сверены с AST существующих dataclass; все source paths существуют в зафиксированном commit. |
| Неподтверждённое содержание | PASS: confidence UNKNOWN, methodology_version null, theoretical_basis/indicators пусты во всех четырёх записях. |
| Пути документов и относительные ссылки | PASS: все семь новых файлов находятся в `docs/scientific/`; локальные ссылки разрешаются. |
| Неизменность существующего кода и данных | PASS: diff относительно базы содержит только добавления в `docs/scientific/`; существующие tracked-файлы совпадают с базой. |
| `git diff --cached --check` | PASS. |

Это локальные проверки. PostgreSQL concurrency, полный продуктовый набор и
удалённый CI здесь не проверялись; изменения не касаются исполняемого кода.
Тесты не являются эмпирической валидацией научной модели.

Первый запуск выполнил 51 тест без ошибок в проверках, но завершился с ошибкой
при записи XML за пределами рабочей папки. После исправления пути выполнен
полный повторный прогон, результат которого указан выше. Код и тесты для
устранения этой ошибки не менялись; прогоны не суммируются.

## Воспроизведение

Из `software/conflict_analysis` в PowerShell, с существующей средой проекта:

```powershell
$env:USE_SQLITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest calculation/tests -p no:cacheprovider --junitxml="$env:TEMP/pr4-scientific-core-results.xml"
```

Используется тестовая in-memory БД Django с миграциями; рабочая БД не
используется. Pytest cache отключён. XML является локальным результатом
проверки и не добавляется в репозиторий.

Из корня репозитория, проверка схемы и каталога:

```powershell
@'
import json
from pathlib import Path
from jsonschema import Draft202012Validator

path = Path('docs/scientific')
schema = json.loads((path / 'factor-metadata.schema.json').read_text(encoding='utf-8'))
catalog = json.loads((path / 'factors.metadata.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(schema)
Draft202012Validator(schema).validate(catalog)
print('Scientific metadata: PASS')
'@ | .\software\conflict_analysis\.venv\Scripts\python.exe -
```

Проверка границы изменений после commit:

```powershell
git diff --name-status f12cfd2c76d54068f5b6cc98511bc0be84dd079e HEAD
git diff --exit-code f12cfd2c76d54068f5b6cc98511bc0be84dd079e HEAD -- . ':(exclude)docs/scientific'
git diff --check f12cfd2c76d54068f5b6cc98511bc0be84dd079e HEAD
```

Первая команда должна показать только семь добавленных файлов ниже; вторая
и третья — завершиться с кодом 0 без diff и ошибок.

## Созданные файлы

- [THEORETICAL_FOUNDATION.md](THEORETICAL_FOUNDATION.md) — назначение,
  разграничение понятий, пять научных направлений и шаблоны факторов.
- [FACTOR_ONTOLOGY.md](FACTOR_ONTOLOGY.md) — поля, четыре подтверждённых входа
  и правила сохранения неизвестного.
- [MODEL_LIMITATIONS.md](MODEL_LIMITATIONS.md) — ограничения и предложение
  программы эмпирической проверки с Gold Dataset.
- [SCIENTIFIC_METADATA.md](SCIENTIFIC_METADATA.md) — происхождение,
  основание выбора, версии и граница с историческими данными.
- [factors.metadata.json](factors.metadata.json) — текущий описательный каталог.
- [factor-metadata.schema.json](factor-metadata.schema.json) — самостоятельная
  схема каталога, не подключённая к приложению.
- [VALIDATION.md](VALIDATION.md) — этот отчёт.
