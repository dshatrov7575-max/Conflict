# PR-2 Player Integration

`Experiment → CalculationSnapshot → CalculationRun → Result View` поверх
неизменённого `calculation` (`POLARIZATION_V1_BETA / 1.0.0`).

## Запуск

Из `software/conflict_analysis` в существующем Python 3.12 окружении:

```text
python manage.py check
python manage.py runserver
```

Для локальной раздачи CSS через runserver задайте `DJANGO_DEBUG=true`.
Для развёртывания используйте обычный Django staticfiles/collectstatic процесс
с тем же профилем настроек. Подключение к PostgreSQL задаётся существующими
переменными `POSTGRES_*`; интеграция не создаёт базу и не меняет миграции.

Откройте `/player/calculations/` с заранее выданной Django session Player G8.
Введите UUID эксперимента, выберите его временной срез, укажите явные beta-веса
или оставьте UNKNOWN и нажмите «Рассчитать». HUMAN/AI и профиль эксперта берутся
из допущенного Foundation эксперимента, а не из запроса.

`player_integration` входит в корневой wheel и штатный
`conflict_analysis.settings`. Маршрут `/player/calculations/` подключён к единому
composition root рядом с `/player/`, `/studio/` и `/api/foundation/`.
`player_integration.settings` и `player_integration.project_urls` оставлены только
как совместимые алиасы для старых команд и тестов.

## Граница интеграции

- `admit_assessment_scope()` — существующая Foundation authority для session,
  точного набора Player permissions, доступа к проекту и assessment projection.
- Сервис повторяет admission под общим Project lock, затем вызывает существующий
  `capture_snapshot()` для одного точного Experiment/TimeSlice.
- Только `calculation.calculate()` вычисляет результат. Представление использует
  Core JSON без округления, формул, подстановок весов или агрегации HUMAN/AI.
- POS/SAL читаются из существующих терминальных ParameterValue revisions.
  Веса RGU/KVPTN передаются только через существующий `BetaWeights`; отсутствующие
  значения остаются UNKNOWN. Веса привязаны к Experiment/TimeSlice и topology.
- Расчёт не создаёт и не обновляет ParameterValue, Experiment, Assessment или
  ImportRun. Для нового baseline-расчёта создаются две append-only записи AuditEvent
  в одной транзакции: payload-light receipt `PLAYER_CALCULATION_RUN_RECEIPT_V2`
  и обязательный companion `PLAYER_CALCULATION_REPLAY_ARTIFACT_V2`. Receipt не
  дублирует snapshot/run/input values; companion хранит исходный snapshot, входной
  metadata-envelope и versioned quality, необходимые для точного idempotent replay.
  Старые receipt V1 не переписываются. Новых ORM-моделей и миграций этот патч не требует.
- HTML показывает отдельную lane, provenance/pins, UNO, все PTN-метрики,
  completeness, предупреждения, trace, исходные статусы и source ID/version.
  Временная ось показывается отдельно от evidence-status: количество входов
  `RETROSPECTIVE_KNOWLEDGE` видно даже при REQUIRED_INPUTS_MISSING или DISPUTED.
  Поля «Вычисление», «Входы», «Временная ось» и «Научный допуск» не смешиваются:
  `COMPLETE` не означает научной подтверждённости, а temporal-status не заменяет
  value/evidence-status.
  Ноль отображается как `0`, отсутствие результата — как `—`/«Недостаточно данных».
- POST защищён стандартным Django CSRF. Ответы обработчиков имеют `no-store`,
  `Vary: Cookie`, CSP и `nosniff`. Caller identity/role override headers отклоняются.
- Receipt V2 остаётся payload-light: actor, scope/pins, request/snapshot/input/result
  digests, quality contract/hash, обязательная ссылка на companion и время. Полный
  replay-material хранится отдельно в `PLAYER_CALCULATION_REPLAY_ARTIFACT_V2`:
  snapshot JSON, input metadata envelope, versioned quality и lane display. По решению
  владельца эта append-only копия хранится бессрочно. PostgreSQL защищает AuditEvent
  от UPDATE/DELETE триггером миграции 0021; SQLite-тесты дополнительно проверяют
  fail-closed при tamper/удалении companion.
- Legacy `PLAYER_CALCULATION_RUN_RECEIPT_V1` остаётся читаемым побайтно как прежде.
  Для V1 без companion нельзя реконструировать исторический payload после изменения
  источника: такой receipt идёт по legacy exact-current пути и не «апгрейдится» в V2.

## HTTP и Python

```text
GET /player/calculations/
GET /player/calculations/experiments/<experiment_uuid>/
GET /player/calculations/experiments/<experiment_uuid>/time-slices/<time_slice_uuid>/
POST /player/calculations/experiments/<experiment_uuid>/time-slices/<time_slice_uuid>/
GET /player/calculations/experiments/<experiment_uuid>/receipts/
GET /player/calculations/experiments/<experiment_uuid>/receipts/<operation_uuid>/
```

GET последнего маршрута открывает форму. Form-urlencoded POST возвращает HTML.
JSON POST требует канонический UUIDv4 `Idempotency-Key`. Новый baseline receipt V2
возвращается в `PLAYER_CALCULATION_RESULT_V4` с `lane`, `snapshot`, `run`,
`input_metadata`, `quality`, `result_digest`, `receipt` и `receipt_replayed`.
Legacy replay receipt V1 остаётся совместим с `PLAYER_CALCULATION_RESULT_V3`.
Pure Python composition без receipt сохраняет прежний `PLAYER_CALCULATION_RESULT_V2`
и не получает новые durable-поля. `run.status` остаётся только вычислительным
статусом Core.
`quality` отдельно фиксирует состояние входов, научный допуск, HUMAN validation и
predictive validity; эти поля не входят в формулу и не меняют digest Core. Обе формы вызывают один сервис. JSON-запрос требует существующей
session и стандартного cookie/header CSRF, как HTML-форма. Form flow передаёт
тот же UUIDv4 в скрытом поле. Точный повтор возвращает ту же receipt; иной запрос
с тем же ключом получает `PLAYER_OPERATION_KEY_REUSE`.

Диагностическая классификация idempotency/replay:

- `PLAYER_OPERATION_KEY_REUSE` — тот же UUID операции уже принадлежит другому caller-controlled запросу, lane/scope или иному immutable operation identity;
- `PLAYER_OPERATION_RESULT_DRIFT` — операция и scope совпали, но обязательный V2 companion отсутствует/повреждён либо receipt/artifact/hash/metadata не согласованы;
- `PLAYER_NOT_FOUND` — list/detail скрывает receipt вне текущего допущенного experiment.

Тело JSON ограничено 256 KiB; дополнительные/повторные поля отклоняются:

```json
{
  "experiment_id": "<experiment_uuid>",
  "time_slice_id": "<time_slice_uuid>",
  "rgu": {
    "<projected_actor_uuid>": {
      "status": "PROVISIONAL",
      "value": "1",
      "source_id": "beta-rgu-source",
      "source_version": "1"
    }
  },
  "kvptn": {
    "<projected_element_uuid>": {
      "status": "PROVISIONAL",
      "value": "1",
      "source_id": "beta-q-source",
      "source_version": "1"
    }
  }
}
```

Можно передать пустые `rgu`/`kvptn`. Каждая группа содержит до 1000 объектов.
Числа передаются обычными десятичными строками на шкале 0…10 (до 32 знаков после
точки), не JSON float и не экспонентой. UNKNOWN/INSUFFICIENT_DATA/
NOT_APPLICABLE/OPEN_METHOD требуют `null`. Источники и версии — непустые строки
до 255 символов. Числовой вес требует явного source_id, отличного от `ABSENT`.
Это ограничения HTTP-адаптера, не изменение числового контракта Core.

```python
from uuid import uuid4
from player_integration.services import calculate_and_record_experiment, calculate_experiment
from calculation import CalculationSnapshot, calculate

view = calculate_experiment(
    user=user, experiment_id=experiment_id, time_slice_id=time_slice_id,
    beta_weights=weights,  # существующий calculation.foundation.BetaWeights
)
payload = view.as_dict()  # pure/offline composition; receipt intentionally absent
replayed = calculate(CalculationSnapshot.from_json(view.snapshot.to_json()))
assert replayed.to_json() == view.run.to_json()

view, receipt = calculate_and_record_experiment(
    user=user, experiment_id=experiment_id, time_slice_id=time_slice_id,
    beta_weights=weights, operation_id=uuid4(),
)
assert receipt.payload["result_digest"] == view.run.result_digest
```

## Тесты

Корневой pytest testpaths не изменён. Явный локальный entry point включает все
новые тесты и профиль интеграции. Быстрый прогон PowerShell:

```powershell
$env:USE_SQLITE = 'true'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -c player_integration/pytest.ini player_integration/tests -p no:cacheprovider
python -m pytest calculation/tests -p no:cacheprovider
```

HTTP E2E создают тестовые эксперименты и оценки через реальный Foundation API,
затем проходят admission, Core capture/calculate и HTML/JSON Result View без
моков. Новый baseline V2 выполняет ровно два разрешённых
`INSERT domain_auditevent`: receipt + replay companion; scenario V1 — один receipt.
Остальные domain writes запрещены, ParameterValue остаются неизменными.
Точный idempotent replay не выполняет повторный INSERT. Создание тестовых оценок
в fixture не является поведением расчёта.

Покрытие: раздельные computation/evidence/admission statuses; COMPLETE/PARTIAL/NOT_COMPUTABLE; HUMAN/AI; отдельные временные срезы;
UNKNOWN и нули; отсутствующий KVPTN при доступных PTN-метриках; successor
correction и сохранение SAL lineage; replay после freeze/archive; scope,
permissions, CSRF, ошибки ввода; HTML escaping и точная сериализация.

Настоящий Chromium E2E использует существующий CDP helper проекта. Нужны Node
22+ и установленный Chrome/Chromium/Edge; при необходимости задайте
`STUDIO_CHROME_BIN` и `NODE_BIN`. В тесте запускается отдельный браузерный профиль,
а Django StaticLiveServer работает с тестовой БД:

```powershell
$env:PLAYER_INTEGRATION_BROWSER = '1'
python -m pytest -c player_integration/pytest.ini player_integration/tests -p no:cacheprovider
```

Без opt-in только browser-тест явно пропускается. Он проходит UI-выбор
эксперимента и среза, native form submit с CSRF, независимые результаты HUMAN=100
и AI=0, UNKNOWN без подстановок, загрузку CSS и отсутствие browser storage.

Для PostgreSQL задайте `USE_SQLITE=false` и `POSTGRES_*` для **одноразовой** базы,
примените миграции с нуля и выполните check и тот же набор. SQLite не проверяет
PostgreSQL row locks. Версия и фактические результаты проверки перечислены
в `VALIDATION.md`.

## Изменённые файлы

| Файлы внутри `player_integration/` | Назначение |
|---|---|
| `services.py` | Foundation admission, snapshot → run и recorded/pure composition |
| `receipts.py` | Legacy receipt V1 + payload-light baseline receipt V2, list/detail и scope |
| `inputs.py` | Ограниченный JSON-контракт и форма beta-весов |
| `views.py`, `urls.py` | HTML/JSON HTTP-путь и защита запросов |
| `apps.py`, `settings.py`, `project_urls.py`, `__init__.py` | Подключаемый профиль без правок вне каталога |
| `templates/player_integration/*.html` | Выбор эксперимента/среза, форма и Result View |
| `static/player_integration/result.css` | Адаптивное оформление таблиц и результата |
| `tests/test_e2e.py`, `tests/test_receipts.py` | HTTP flows, receipt replay/scope/immutability |
| `tests/test_browser.py`, `tests/browser_e2e.mjs` | Настоящий браузерный E2E |
| `pytest.ini`, `.gitignore` | Локальный вход тестов и исключение временных артефактов |
| `README.md`, `VALIDATION.md` | Подключение, контракты, состав файлов и результаты проверки |
