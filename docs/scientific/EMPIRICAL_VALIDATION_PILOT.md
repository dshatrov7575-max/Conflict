# Empirical Validation Pilot — Conflict Analysis MVP7

Пилот: `ZHANAOZEN_2011_VALIDATION_PILOT`. Версия контракта: `1.0.0`.
Статус поставки: подготовка, `STRUCTURE_ONLY`. База PR-6:
`2b5d40351c8c78d301379d3a8550d77125fcb28e`.

## Цель и границы

Создать первый слой подготовки эмпирической валидации на существующем кейсе
Zhanaozen 2011: связать артефакты, явно оставить пробелы и задать условия
допустимости будущих входных сведений.

```text
Evidence Package
    ↓
Case Mapping
    ↓
Factor Mapping
    ↓
Historical Assessment
    ↓
Validation Record
```

Это схема зависимостей, а не выполненная последовательность исследования.
Результат PR-7 — метаданные и технические проверки. Calculation Core,
`POLARIZATION_V1_BETA`, веса, формула, факторы, Scenario Modeling и существующие
Evidence datasets остаются без изменений. Исторический replay, новые UNO,
рейтинг, прогноз и оценка страны не создаются.

## Почему Zhanaozen 2011

1. **Зрелость evidence package.** Уже существует
   [ZHANAOZEN_V4_2011_SEALED_EVIDENCE_PACKET_CP3.xlsx](https://docs.google.com/spreadsheets/d/1QbPyyXk09RrMoFiFsxXknZyiky4TTFyM/edit?usp=drivesdk&ouid=100628083284865869908&rtpof=true&sd=true).
   Он содержит отдельные реестры источников, документов и версий, фрагментов,
   фактов и связей. Это основание выбрать его для подготовки пилота, а не
   заключение о полноте, достоверности или пригодности всех его данных.
2. **Provenance.**
   [Существующая спецификация пакета](https://docs.google.com/document/d/1eaRA29j41kv_O5BeruHkUy9KlHbjDhMNHgFxL7avmeA/edit?usp=drivesdk)
   задаёт идентификаторы, версии, происхождение, фиксацию содержимого,
   временную допустимость и группы независимости источников.
   [Foundation package](../../software/conflict_analysis/docs/foundation-package-v2.md)
   уже описывает сохранение этой цепочки при переносе.
3. **Fragment/fact chain.** В пакете представлены связи
   `CodingItem → Fact → TextFragment → DocumentVersion → Document → Source`.
   Они позволяют планировать проверку происхождения интерпретации и отдельно
   отражать поддерживающие, оспаривающие и контекстные сведения.

[Существующий отчёт Evidence Readiness CP3](https://docs.google.com/spreadsheets/d/1XH_yF2WYFqNetzMFHRscGQemXa7Hsrlk/edit?usp=drivesdk&ouid=100628083284865869908&rtpof=true&sd=true)
сам отделяет `EVIDENCE_READY` от `CONFIRMED` и указывает на незавершённое HUMAN
coding. Его показатели и числовые оценки не переносятся в шаблон пилота.
Доступ к этим трём артефактам подтверждён чтением через Google Drive 2026-09-25;
аудит истинности фактов, целостности каждой связи и исторической доступности
источников в эту поставку не входит.

## Метод

```text
Information cutoff
    ↓
Available evidence
    ↓
Historical assessment
    ↓
Observed outcome
```

1. **Information cutoff.** Перед исследованием зарегистрировать окно исхода
   `event_period` и точную `information_cutoff_date`. По
   [Validation Protocol](VALIDATION_PROTOCOL.md) cutoff обозначает конец дня
   UTC и должен быть строго раньше начала окна: `cutoff < start_date <= end_date`.
   Дата в день начала события не допускается. Год из имени кейса и дата
   существующего seed/time slice не устанавливают границы этого пилота.
2. **Available evidence.** Для каждого используемого свидетельства подтвердить
   доступность конкретной версии до cutoff включительно. Ранняя дата описанного
   факта, дата публикации без проверки редакции, дата загрузки в Drive или
   `captured_at` сами по себе этого не доказывают. Поздняя редакция раннего
   документа считается поздней информацией. Неизвестная доступность исключает
   свидетельство из входов до уточнения; пробел сохраняется в limitations.
3. **Historical assessment.** Будущая оценка должна ссылаться на зафиксированные
   Case Mapping / Factor Mapping и допустимые версии Evidence. Исход скрывается
   от процедуры оценки; выбор акторов, эпизодов и рубрик также проверяется на
   утечку. В PR-7 не создаются интерпретации, оценки факторов или snapshot.
4. **Observed outcome.** Исторический исход размечается отдельно по
   [существующему справочнику](OBSERVED_OUTCOME_CLASSIFICATION.md). Материалы
   после события допустимы только для независимого описания исхода. Они не
   возвращаются в входы, mapping, историческую оценку или выбор весов.

Таким образом, input после cutoff запрещён даже до начала события; input
в день события или позже также запрещён. Проверка дат не заменяет проверки
версий, полноты списка использованных источников и независимости разметки.

## ValidationPilot и ссылки

Контракт: [EMPIRICAL_VALIDATION_SCHEMA.json](EMPIRICAL_VALIDATION_SCHEMA.json),
JSON Schema Draft 2020-12. Все 12 полей обязательны; неизвестное обозначается
`null`, а не вымышленной датой, нулём или фиктивным артефактом.

| Поле | Смысл и состояние шаблона |
| --- | --- |
| `pilot_id` | `ZHANAOZEN_2011_VALIDATION_PILOT`, идентификатор подготовки. |
| `case_id` | `ZHANAOZEN_2011_EXAMPLE`, точный ID существующего кейса PR-5. Это структурный placeholder, не новый исторический dataset. |
| `country` | Контекст, пока null; не страновая оценка. |
| `event_period` | Обязательные `start_date` и `end_date`, обе пока null. |
| `information_cutoff_date` | Обязательное поле; null только в неисполняемом STRUCTURE_ONLY. |
| `evidence_package_reference` | Ссылка на существующий CP3 XLSX, тип DATA. |
| `case_mapping_reference` | PR-5 JSON, указатель `/cases/0`, тип STRUCTURE_ONLY. |
| `factor_mapping_reference` | Тот же JSON, указатель `/cases/0/episodes/0/factor_mappings`, тип STRUCTURE_ONLY. |
| `historical_assessment_reference` | Null: согласованный с пилотом артефакт пока не установлен. |
| `observed_outcome_reference` | Null: независимая разметка исхода для пилота пока не установлена. |
| `limitations` | Непустой список пробелов и пределов интерпретации. |
| `status` | STRUCTURE_ONLY либо PREPARATION; статусов завершённой валидации здесь нет. |

Каждая ссылка содержит `reference`, `sha256`, `artifact_kind` и `json_pointer`.
Локальный путь отсчитывается от корня репозитория; внешний адрес — HTTPS.
SHA-256 относится к полным байтам артефакта, а JSON Pointer — к его разделу;
null pointer означает весь артефакт. Для PR-5 JSON проверены байты и оба
указателя. Файл сохранён с LF; изменение окончаний строк изменит его хеш.

У внешнего XLSX `sha256=null`: проверены существование и читаемая структура,
но исходные байты файла не закреплены. Внутренний `source_manifest_hash`,
хеш схемы и хеш текстового извлечения не подставляются вместо хеша XLSX.
URL не гарантирует неизменность содержимого; доступ требует прав Google Drive.
Перед будущим исследованием нужны архивная версия и проверенный хеш байтов.

**STRUCTURE_ONLY** запрещает заполнять страну, даты, историческую оценку и исход.
Он допускает инвентаризацию ссылок, но не является входом исследования.
**PREPARATION** требует дату cutoff, страну, обе границы окна и закреплённые
DATA-ссылки на пакет и оба mapping. Нельзя просто сменить статус или объявить
структурный пример PR-5 данными. Историческая оценка и исход могут оставаться
null с пояснением в limitations. Даже полная PREPARATION не означает готовность
к расчёту или завершённую эмпирическую проверку.

Будущая Validation Record оформляется отдельно по
[VALIDATION_SCHEMA.json](VALIDATION_SCHEMA.json) и
[VALIDATION_PROTOCOL.md](VALIDATION_PROTOCOL.md). Pilot связывает подготовку;
он не заменяет модельную версию, snapshot, отчёт сравнения и review из PR-6.
Связь сохраняет case_id и ссылки на конкретные артефакты. PR-7 не создаёт
Validation Record и не присваивает `VALIDATED`.

## Ограничения

- Это не доказательство качества модели. Корректная схема или provenance
  не доказывают валидность факторов, причинность либо точность UNO.
- Один кейс не является валидацией модели. Выбор зрелого пакета удобен для
  подготовки, но не обеспечивает независимую или репрезентативную выборку.
- Результат нельзя обобщать на другие события, периоды или страны.
- Case Mapping и Factor Mapping пока структурные; Historical Assessment и
  Observed outcome не заполнены. Недостаток данных не равен отсутствию события.
- Знание исследователем исхода и поздняя подготовка пакета создают риск утечки.
  Метка `CONTEMPORANEOUS` или название SEALED сами по себе его не устраняют.
- Текущая поставка не выполняет фактическую валидацию модели, пересчёт UNO,
  изменение факторов, формулы или весов.

## Технические проверки и воспроизведение

Локальная проверка 2026-09-25: Windows, Python 3.12.10, jsonschema 4.26.0,
Django 5.2.17, pytest 8.4.2.

| Проверка | Результат |
| --- | --- |
| Контракт, шаблон, даты и локальные ссылки | **12 tests passed**, включая положительные и отрицательные варианты. |
| Calculation Core | **51 passed, 0 skipped, 38.18 s**, exit 0. |
| Evidence-ссылки | Пакет CP3, спецификация и Readiness доступны через Google Drive; байтовый хеш XLSX не проверен. |
| Локальные Markdown-ссылки | Все разрешаются. |
| Граница изменений | Только четыре новых файла в `docs/scientific/`; прежние tracked-файлы не изменены. |

[check_empirical_validation_pilot.py](check_empirical_validation_pilot.py)
проверяет JSON Schema с `FormatChecker`, шаблон, обязательные поля, запрет
эмпирического заполнения STRUCTURE_ONLY, временные границы, локальные хеши,
JSON Pointer и совпадение case_id. Отрицательные варианты проверяют пропущенный,
null и некорректный cutoff, равенство cutoff началу окна, поздние входы,
обратный период, отсутствующие файлы, неверные хеши и ссылки, подмену шаблона
данными и добавление чисел/весов/результатов за пределами контракта.

Синтетические даты и идентификаторы создаются только в памяти тестов; они не
являются фактами Zhanaozen и не записываются в dataset. `check_input_dates`
проверяет переданные даты доступности версий; он не доказывает их происхождение
или полноту. `check_local_references` возвращает внешние URL как непроверенные
локально. Сетевой доступ, приложение и БД скриптом не используются.

Из корня репозитория, существующей средой проекта:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
.\software\conflict_analysis\.venv\Scripts\python.exe docs/scientific/check_empirical_validation_pilot.py
```

Регрессия Core из `software/conflict_analysis`:

```powershell
$env:USE_SQLITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
.\.venv\Scripts\python.exe -m pytest calculation/tests -p no:cacheprovider --junitxml="$env:TEMP/pr7-empirical-validation-core-results.xml"
```

Это существующие синтетические тесты на отдельной тестовой in-memory SQLite БД,
а не расчёт исторического кейса. Рабочая БД и Evidence datasets не используются.
Результаты локальные; удалённый CI и PostgreSQL concurrency не заявляются.

После commit, из корня репозитория:

```powershell
git diff --name-status 2b5d40351c8c78d301379d3a8550d77125fcb28e HEAD
git diff --exit-code 2b5d40351c8c78d301379d3a8550d77125fcb28e HEAD -- . ':(exclude)docs/scientific'
git diff --name-status --diff-filter=DMRTUXB 2b5d40351c8c78d301379d3a8550d77125fcb28e HEAD
git diff --check 2b5d40351c8c78d301379d3a8550d77125fcb28e HEAD
```

Первая команда должна показать только четыре добавления из этой поставки;
третья — пустой вывод, подтверждающий отсутствие изменений прежних файлов,
включая прежние научные документы. Вторая и четвёртая завершаются с кодом 0.
