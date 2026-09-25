# PR-5 — проверка Case Mapping Layer

Дата: 2026-09-25. Ветка: `codex/pr-5-case-mapping-layer`.
База HEAD: `4cee2e8b7972c1678e6d4b4028f611182eaf7c7d` (PR-4).
База tree: `cffaefcdb3cecd3001dd055d188da72d17a2d221`.
Рабочее дерево перед началом было чистым; конфликт имени ветки отсутствовал.
Доступ к origin и dry-run push проверены; доставка — `LIVE_BRANCH`, Draft PR
в `codex/pr-4-scientific-foundation` с diff только данного слоя.

## Результаты

Среда: Windows x64, Python 3.12.10, Django 5.2.17, pytest 8.4.2,
pytest-django 4.14.0, SQLite 3.49.1, jsonschema 4.26.0.

| Проверка | Результат |
| --- | --- |
| Calculation Core: `calculation/tests` | **51 passed, 0 skipped, 38.41 s**, exit 0. |
| JSON Schema Draft 2020-12 и пример | PASS с `FormatChecker`; factor_id согласованы с каталогом PR-4. |
| 21 положительный вариант схемы | PASS: несколько факторов и источников, несколько кейсов/эпизодов, повтор одного фактора с самостоятельной интерпретацией, 16 сочетаний статуса и уверенности, null factor_id, корректная дата. |
| 30 отрицательных вариантов схемы | PASS: отклонены посторонние статусы/факторы, числовая уверенность/индикатор/эскалация, поля weight/UNO, неполное обоснование, повтор Evidence-ссылки, отсутствие обязательного поля, неправильные даты и фактическое заполнение STRUCTURE_ONLY. |
| Семантическая проверка связей | PASS: пример и синтетическая структура проходят; восемь вариантов с дублирующимися ID, неразрешимой ссылкой и неправильными границами дат отклонены отдельной проверкой ниже. |
| Структурный пример без новых фактов | PASS: страна, даты, описание, границы, индикаторы и исходы null; источники/Evidence пусты; confidence и mapping_status UNKNOWN. |
| Пути, локальные ссылки и diff | PASS: четыре новых файла в `docs/scientific/`; ссылки разрешаются; `git diff --check` проходит. |
| Существующий код и datasets | PASS: все прежние tracked-файлы совпадают с базой, включая Core, POLARIZATION_V1_BETA, Scenario Modeling и исторические Evidence datasets. |

Синтетические варианты использовались только в памяти валидатора и не
сохранялись как исторические данные или факты ZHANAOZEN_2011. Не выполнены
новые исторические оценки, подбор весов, рейтинги или replay по кейсу.
Core tests выполняют существующие синтетические регрессионные проверки;
они не являются расчётом исторического примера или эмпирической валидацией.
Результаты локальные; PostgreSQL concurrency и удалённый CI не заявляются.

## Воспроизведение проверки схемы и связей

Из корня репозитория в PowerShell, с существующей средой проекта:

```powershell
@'
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

root = Path('docs/scientific')
schema = json.loads((root / 'CASE_MAPPING_SCHEMA.json').read_text(encoding='utf-8'))
document = json.loads((root / 'ZHANAOZEN_2011_EXAMPLE.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())

def unique(rows, key):
    values = [row[key] for row in rows]
    if len(values) != len(set(values)):
        raise ValueError(f'Duplicate {key}')

def ordered(start, end):
    if start is not None and end is not None and start > end:
        raise ValueError('Reversed date boundaries')

def validate_mapping(data):
    validator.validate(data)
    unique(data['cases'], 'case_id')
    for case in data['cases']:
        period = case['time_period']
        ordered(period['start_date'], period['end_date'])
        unique(case['episodes'], 'episode_id')
        for episode in case['episodes']:
            ordered(episode['start_date'], episode['end_date'])
            for date in (episode['start_date'], episode['end_date']):
                ordered(period['start_date'], date)
                ordered(date, period['end_date'])
            unique(episode['evidence'], 'evidence_id')
            unique(episode['factor_mappings'], 'mapping_id')
            evidence_ids = {row['evidence_id'] for row in episode['evidence']}
            for mapping in episode['factor_mappings']:
                if not set(mapping['evidence_reference']) <= evidence_ids:
                    raise ValueError('Unresolved evidence_reference in episode')

validate_mapping(document)
print('Case Mapping schema and references: PASS')
'@ | .\software\conflict_analysis\.venv\Scripts\python.exe -
```

Эта проверка не импортирует приложение, не читает БД, не переходит по внешним
ссылкам и не пишет файлы. Проверка доступности/версии источника и качества
обоснования остаётся отдельной исследовательской работой.

## Воспроизведение регрессии и границы diff

Из `software/conflict_analysis`:

```powershell
$env:USE_SQLITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest calculation/tests -p no:cacheprovider --junitxml="$env:TEMP/pr5-case-mapping-core-results.xml"
```

Django использует отдельную тестовую in-memory SQLite БД. Рабочая БД не
используется; pytest cache отключён. XML-отчёт не добавляется в репозиторий.

Из корня репозитория после commit:

```powershell
git diff --name-status 4cee2e8b7972c1678e6d4b4028f611182eaf7c7d HEAD
git diff --exit-code 4cee2e8b7972c1678e6d4b4028f611182eaf7c7d HEAD -- . ':(exclude)docs/scientific'
git diff --check 4cee2e8b7972c1678e6d4b4028f611182eaf7c7d HEAD
```

Первая команда показывает только четыре добавленных файла; две следующие
завершаются с кодом 0. Изменения существующих файлов отсутствуют также внутри
`docs/scientific/`.

## Созданные файлы

- [CASE_MAPPING_MODEL.md](CASE_MAPPING_MODEL.md)
- [CASE_MAPPING_SCHEMA.json](CASE_MAPPING_SCHEMA.json)
- [ZHANAOZEN_2011_EXAMPLE.json](ZHANAOZEN_2011_EXAMPLE.json)
- [CASE_MAPPING_VALIDATION.md](CASE_MAPPING_VALIDATION.md)
