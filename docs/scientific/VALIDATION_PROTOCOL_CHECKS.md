# PR-6 — техническая проверка Validation Protocol Layer

Дата: 2026-09-25. Ветка: `codex/pr-6-validation-protocol-layer`.
База HEAD: `eb97d722e46b99b52eb81afb7ccbe31bafdcf5a8` (PR-5).
База tree: `cfa7bccfefe29f6e3b00a7151990d6ee70c20c33`.
Рабочее дерево до начала было чистым; имя новой ветки свободно локально
и на origin. Remote read и dry-run push прошли. Доставка — `LIVE_BRANCH`,
Draft PR в `codex/pr-5-case-mapping-layer`.

## Результаты

Среда: Windows x64, Python 3.12.10, Django 5.2.17, pytest 8.4.2,
SQLite 3.49.1, jsonschema 4.26.0.

| Проверка | Результат |
| --- | --- |
| Calculation Core: `calculation/tests` | **51 passed, 0 skipped, 39.71 s**, exit 0. |
| JSON Schema Draft 2020-12 | PASS: схема корректна, пустой шаблон соответствует ей с FormatChecker, все запрошенные поля обязательны. |
| 16 положительных вариантов схемы | PASS: четыре статуса с двумя типами сравнения, все шесть категорий исхода, совместимые метки и сохранение неизвестного. |
| 56 отрицательных вариантов схемы | PASS: отклонены отсутствующий/null/некорректный cutoff в рабочих записях, неполный VALIDATED/PARTIAL, незавершённый статус без limitations, подмена типа сравнения Calibration, недопустимые исходы/ссылки, числовой результат, поля весов/рейтингов/прогноза и эмпирическое заполнение TEMPLATE. |
| Семантика дат | PASS: шаблон и пять допустимых временных конфигураций приняты; пять случаев равенства cutoff границе, информации после начала окна и обратного периода отклонены отдельной проверкой ниже. |
| Пустота демонстрационного шаблона | PASS: реальные case_id, country, даты, версии модели, ссылки, результаты и исходы отсутствуют; статус INSUFFICIENT_DATA. |
| Пути и относительные ссылки | PASS: пять новых файлов только в `docs/scientific/`, локальные ссылки разрешаются. |
| Существующие файлы | PASS: отсутствуют изменения прежних tracked-файлов, включая все научные документы PR-4/PR-5, Core, стратегию, Scenario Modeling и Evidence datasets. |
| `git diff --check` | PASS. |

Синтетические значения использовались только в памяти при проверке формы;
они не сохранены как исторические сведения. Новых UNO, оценок стран,
рейтингов или прогнозов нет. Core tests запускают только существующие
синтетические регрессионные проверки; веса и формулы не менялись.

Это технические проверки нового слоя, а не эмпирическая валидация MVP7.
Результаты локальные; удалённый CI, PostgreSQL concurrency и достоверность
внешних источников не проверялись. Прохождение схемы и дат не подтверждает
доступность каждой версии источника до cutoff, независимость выборки или
неизменность артефактов по ссылкам — это отдельные обязательные проверки
исследовательского протокола перед присвоением VALIDATED.

## Воспроизведение проверки шаблона и временных границ

Из корня репозитория в PowerShell:

```powershell
@'
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

root = Path('docs/scientific')
schema = json.loads((root / 'VALIDATION_SCHEMA.json').read_text(encoding='utf-8'))
template = json.loads((root / 'VALIDATION_EXAMPLE_TEMPLATE.json').read_text(encoding='utf-8'))
Draft202012Validator.check_schema(schema)
validator = Draft202012Validator(schema, format_checker=FormatChecker())

def validate_record_structure(data):
    validator.validate(data)
    if data['record_kind'] == 'TEMPLATE':
        return
    cutoff = data['information_cutoff_date']
    start = data['event_period']['start_date']
    end = data['event_period']['end_date']
    if start is not None and end is not None and start > end:
        raise ValueError('Reversed event_period')
    for boundary in (start, end):
        if boundary is not None and cutoff >= boundary:
            raise ValueError('Cutoff must precede every known event boundary')

validate_record_structure(template)
print('Validation schema/template and date structure: PASS; no empirical validation performed')
'@ | .\software\conflict_analysis\.venv\Scripts\python.exe -
```

При неизвестной границе проверяются только известные ограничения; успешная
проверка такой записи не делает её завершённой. VALIDATED требует обе даты
по JSON-схеме и дополнительного содержательного review. Скрипт не загружает
внешние артефакты, не импортирует Core и не обращается к БД.

## Воспроизведение Core tests и границы изменений

Из `software/conflict_analysis`:

```powershell
$env:USE_SQLITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest calculation/tests -p no:cacheprovider --junitxml="$env:TEMP/pr6-validation-protocol-core-results.xml"
```

Используется отдельная тестовая in-memory SQLite БД Django; рабочая БД
не используется. Pytest cache отключён, XML-отчёт остаётся локальным.

Из корня репозитория после commit:

```powershell
git diff --name-status eb97d722e46b99b52eb81afb7ccbe31bafdcf5a8 HEAD
git diff --exit-code eb97d722e46b99b52eb81afb7ccbe31bafdcf5a8 HEAD -- . ':(exclude)docs/scientific'
git diff --check eb97d722e46b99b52eb81afb7ccbe31bafdcf5a8 HEAD
```

Первый вывод должен содержать только пять добавлений ниже. Существующие
файлы внутри `docs/scientific/` также не изменены.

## Созданные файлы

- [VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md)
- [VALIDATION_SCHEMA.json](VALIDATION_SCHEMA.json)
- [OBSERVED_OUTCOME_CLASSIFICATION.md](OBSERVED_OUTCOME_CLASSIFICATION.md)
- [VALIDATION_EXAMPLE_TEMPLATE.json](VALIDATION_EXAMPLE_TEMPLATE.json)
- [VALIDATION_PROTOCOL_CHECKS.md](VALIDATION_PROTOCOL_CHECKS.md)
